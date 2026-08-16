#!/usr/bin/env python3
"""
BIBA Eye - FPV web UI + ONVIF PTZ control for V380 Q8 cameras.

First run: the web page asks for the camera IP (or scans the local network),
saves everything to config.json, then streams video and controls PTZ.

Run:     python tools/biba_eye/server.py
Page:    http://127.0.0.1:8081/  (port from config.json / BIBA_WEB_PORT)

Config file: tools/biba_eye/config.json (created automatically on first run).
Env overrides: BIBA_CAM_IP, BIBA_CAM_PASS, BIBA_WEB_PORT.

Stream quality profiles (selectable in the UI):
  fast      - sub-stream, 12 fps, heavy JPEG compression  -> min latency
  balanced  - sub-stream, 20 fps, medium compression      -> default
  quality   - main stream 720p, 20 fps, high JPEG quality -> best image
"""
import base64
import hashlib
import json
import os
import re
import shutil
import socket
import subprocess
import threading
import time
import webbrowser
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(HERE, 'config.json')

PROFILES = {
    'ultra':    {'rtsp_path': 'onvif2', 'fps': 10, 'q': 12, 'scale': 480,
                 'label': 'Ultra', 'desc': 'sub-stream 10fps 480p, absolute min latency'},
    'fast':     {'rtsp_path': 'onvif2', 'fps': 12, 'q': 8, 'scale': 640,
                 'label': 'Fast', 'desc': 'sub-stream 12fps, min latency'},
    'balanced': {'rtsp_path': 'onvif2', 'fps': 20, 'q': 5, 'scale': 0,
                 'label': 'Balanced', 'desc': 'sub-stream 20fps'},
    'quality':  {'rtsp_path': 'onvif1', 'fps': 20, 'q': 3, 'scale': 0,
                 'label': 'Quality', 'desc': 'main stream 720p'},
}
PTZ_PROFILE_BY_STREAM = {'onvif1': 'PROFILE_000', 'onvif2': 'PROFILE_001'}

DEFAULTS = {
    'camera_ip': '',
    'camera_user': 'admin',
    'camera_pass': '888888',
    'rtsp_port': 554,
    'onvif_port': 8899,
    'profile': 'balanced',
    'web_port': 8081,
    'ptz_speed': 0.5,
    'flip_x': 0,
    'flip_y': 0,
    'auto_open': True,
}

# ---------------------------------------------------------------- config ---
def load_config():
    cfg = dict(DEFAULTS)
    cfg['camera_ip'] = os.environ.get('BIBA_CAM_IP', cfg['camera_ip'])
    cfg['camera_pass'] = os.environ.get('BIBA_CAM_PASS', cfg['camera_pass'])
    cfg['web_port'] = int(os.environ.get('BIBA_WEB_PORT', cfg['web_port']))
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, encoding='utf-8') as fh:
                cfg.update(json.load(fh))
        except (OSError, ValueError):
            pass
    return cfg


def save_config(cfg):
    try:
        with open(CONFIG_PATH, 'w', encoding='utf-8') as fh:
            json.dump(cfg, fh, ensure_ascii=False, indent=2)
        return True
    except OSError:
        return False


def rtsp_url(cfg, profile_key=None):
    key = profile_key or cfg.get('profile', 'balanced')
    prof = PROFILES.get(key, PROFILES['balanced'])
    return 'rtsp://%s:%s@%s:%d/%s' % (
        cfg.get('camera_user', 'admin'), cfg.get('camera_pass', ''),
        cfg.get('camera_ip', ''), int(cfg.get('rtsp_port', 554)),
        prof['rtsp_path'])


def ptz_url(cfg):
    return 'http://%s:%d/onvif/ptz' % (
        cfg.get('camera_ip', ''), int(cfg.get('onvif_port', 8899)))


def find_ffmpeg():
    path = shutil.which('ffmpeg')
    if path:
        return path
    try:
        out = subprocess.run('where ffmpeg', shell=True, capture_output=True,
                             text=True).stdout.splitlines()
        for line in out:
            if line.strip().lower().endswith('ffmpeg.exe'):
                return line.strip()
    except OSError:
        pass
    return 'ffmpeg'


FFMPEG = find_ffmpeg()

# --------------------------------------------------------------- onvif -----
def soap_envelope(body, user=None, password=None):
    if user is not None and password is not None:
        nonce = os.urandom(16)
        nonce_b64 = base64.b64encode(nonce).decode()
        created = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
        digest = base64.b64encode(
            hashlib.sha1(nonce + created.encode() + password.encode()).digest()
        ).decode()
        header = (
            '<s:Header><Security s:mustUnderstand="1" '
            'xmlns="http://docs.oasis-open.org/wss/2004/01/'
            'oasis-200401-wss-wssecurity-secext-1.0.xsd">'
            '<UsernameToken><Username>%s</Username>'
            '<Password Type="http://docs.oasis-open.org/wss/2004/01/'
            'oasis-200401-wss-username-token-profile-1.0#PasswordDigest">%s</Password>'
            '<Nonce EncodingType="http://docs.oasis-open.org/wss/2004/01/'
            'oasis-200401-wss-soap-message-security-1.0#Base64Binary">%s</Nonce>'
            '<Created xmlns="http://docs.oasis-open.org/wss/2004/01/'
            'oasis-200401-wss-wssecurity-utility-1.0.xsd">%s</Created>'
            '</UsernameToken></Security></s:Header>'
        ) % (user, digest, nonce_b64, created)
    else:
        header = ''
    return ('<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope">'
            '%s<s:Body>%s</s:Body></s:Envelope>' % (header, body))


def onvif_post(ip, port, body, path='/onvif/ptz', user=None, password=None,
               timeout=5.0):
    req = Request(
        'http://%s:%d%s' % (ip, port, path),
        data=soap_envelope(body, user, password).encode('utf-8'),
        headers={'Content-Type': 'application/soap+xml'},
        method='POST',
    )
    with urlopen(req, timeout=timeout) as resp:
        text = resp.read().decode('utf-8', 'replace')
        if 'Fault' in text:
            raise RuntimeError('SOAP fault: %s' % text[-300:])
        return text


def onvif_get_profiles(ip, port=8899, timeout=4.0):
    """No auth needed on V380 for GetProfiles."""
    text = onvif_post(
        ip, port,
        '<GetProfiles xmlns="http://www.onvif.org/ver10/media/wsdl"/>',
        path='/onvif/media_service', timeout=timeout)
    tokens = re.findall(r'token="([^"]+)"', text)
    names = re.findall(r'<tt:Name>(.*?)</tt:Name>', text)
    return {'tokens': tokens, 'names': names}


def ptz_move(cfg, x, y):
    prof = PROFILES.get(cfg.get('profile', 'balanced'), PROFILES['balanced'])
    token = PTZ_PROFILE_BY_STREAM.get(prof['rtsp_path'], 'PROFILE_000')
    body = (
        '<ContinuousMove xmlns="http://www.onvif.org/ver20/ptz/wsdl">'
        '<ProfileToken>%s</ProfileToken>'
        '<Velocity><PanTilt x="%.2f" y="%.2f" '
        'xmlns="http://www.onvif.org/ver10/schema"/></Velocity>'
        '</ContinuousMove>'
    ) % (token, x, y)
    onvif_post(cfg['camera_ip'], int(cfg.get('onvif_port', 8899)), body,
               user=cfg.get('camera_user', 'admin'),
               password=cfg.get('camera_pass', ''))


def ptz_stop(cfg):
    prof = PROFILES.get(cfg.get('profile', 'balanced'), PROFILES['balanced'])
    token = PTZ_PROFILE_BY_STREAM.get(prof['rtsp_path'], 'PROFILE_000')
    body = (
        '<Stop xmlns="http://www.onvif.org/ver20/ptz/wsdl">'
        '<ProfileToken>%s</ProfileToken>'
        '<PanTilt>true</PanTilt><Zoom>false</Zoom></Stop>'
    ) % token
    onvif_post(cfg['camera_ip'], int(cfg.get('onvif_port', 8899)), body,
               user=cfg.get('camera_user', 'admin'),
               password=cfg.get('camera_pass', ''))


def tcp_open(ip, port, timeout=0.35):
    try:
        with socket.create_connection((ip, port), timeout=timeout):
            return True
    except OSError:
        return False


def local_subnets():
    """All local IPv4 /24 subnets (Wi-Fi, Ethernet), skipping loopback/APIPA."""
    subnets = set()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None):
            ip = info[4][0]
            if not re.match(r'^\d{1,3}(\.\d{1,3}){3}$', ip):
                continue
            parts = ip.split('.')
            if parts[0] == '127' or (parts[0] == '169' and parts[1] == '254'):
                continue
            subnets.add('.'.join(parts[:3]) + '.')
    except OSError:
        pass
    if not subnets:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(('8.8.8.8', 80))
            ip = s.getsockname()[0]
        except OSError:
            ip = '127.0.0.1'
        finally:
            s.close()
        parts = ip.split('.')
        subnets.add('.'.join(parts[:3]) + '.')
    return sorted(subnets)


def discover_cameras(tcp_timeout=0.25, onvif_timeout=1.2):
    """Scan local /24s for V380 cameras.

    In some networks every IP answers TCP (router/VPN artefacts), so the only
    reliable discriminator is a successful ONVIF GetProfiles response.
    The scan stops as soon as the first confirmed camera is found.
    """
    subnets = sorted(local_subnets(),
                     key=lambda s: (not s.startswith('192.168.'),
                                    not s.startswith('10.'), s))
    tasks = [s + str(i) for s in subnets for i in range(1, 255)]
    configured = app.cfg.get('camera_ip')
    if configured:
        tasks = [configured] + [t for t in tasks if t != configured]

    results = {}
    lock = threading.Lock()
    stop = threading.Event()

    def probe(ip):
        if stop.is_set():
            return
        # cheap TCP gate: skip clearly closed hosts without touching ONVIF
        if not (tcp_open(ip, 8899, tcp_timeout)
                or tcp_open(ip, 554, tcp_timeout)):
            return
        item = {'ip': ip, 'onvif': False, 'profiles': None}
        try:
            info = onvif_get_profiles(ip, timeout=onvif_timeout)
            item['onvif'] = True
            item['profiles'] = [n for n in info['names']
                                if n.endswith('_000')]
            stop.set()
        except (HTTPError, URLError, OSError, RuntimeError):
            pass
        with lock:
            results[ip] = item

    with ThreadPoolExecutor(max_workers=64) as pool:
        pool.map(probe, tasks)

    confirmed = [r for r in results.values() if r['onvif']]
    others = [r for r in results.values() if not r['onvif']]
    confirmed.sort(key=lambda c: socket.inet_aton(c['ip']))
    others.sort(key=lambda c: socket.inet_aton(c['ip']))
    # show unconfirmed "ports open" hosts only when there are few (else noise)
    if len(others) <= 8:
        return confirmed + others
    return confirmed


# ---------------------------------------------------------------- stream ---
class Streamer:
    def __init__(self, app):
        self.app = app
        self.cond = threading.Condition()
        self.frame = None
        self.seq = 0
        self.alive = False
        self.gen = 0
        self.running = True
        threading.Thread(target=self._run, daemon=True).start()

    def restart(self):
        with self.cond:
            self.gen += 1
            self.cond.notify_all()

    def _ffmpeg_cmd(self, cfg, prof):
        vf = []
        if prof.get('scale'):
            vf.append('scale=%d:-2' % prof['scale'])
        vf.append('fps=%d' % prof['fps'])
        return [
            FFMPEG, '-hide_banner', '-loglevel', 'error',
            '-rtsp_transport', 'tcp',
            '-fflags', 'nobuffer', '-flags', 'low_delay',
            '-i', rtsp_url(cfg),
            '-vf', ','.join(vf),
            '-q:v', str(prof['q']),
            '-f', 'mjpeg', 'pipe:1',
        ]

    def _run(self):
        while self.running:
            with self.cond:
                my_gen = self.gen
                self.alive = False
            with self.app.lock:
                cfg = dict(self.app.cfg)
                prof = PROFILES.get(cfg.get('profile', 'balanced'),
                                    PROFILES['balanced'])
            if not cfg.get('camera_ip'):
                time.sleep(1)
                continue
            proc = None
            try:
                proc = subprocess.Popen(self._ffmpeg_cmd(cfg, prof),
                                        stdout=subprocess.PIPE,
                                        stderr=subprocess.DEVNULL)
                buf = b''
                while self.running and proc.poll() is None:
                    with self.cond:
                        if self.gen != my_gen:
                            break
                    chunk = proc.stdout.read(65536)
                    if not chunk:
                        break
                    buf += chunk
                    while True:
                        start = buf.find(b'\xff\xd8')
                        end = buf.find(b'\xff\xd9', start + 2)
                        if start < 0 or end < 0:
                            if start >= 0 and len(buf) > 1 << 20:
                                buf = buf[start:]
                            break
                        with self.cond:
                            self.frame = buf[start:end + 2]
                            self.seq += 1
                            self.alive = True
                            self.cond.notify_all()
                        buf = buf[end + 2:]
            except Exception:
                pass
            finally:
                with self.cond:
                    self.alive = False
                if proc and proc.poll() is None:
                    proc.kill()
            time.sleep(1)

    def wait_frame(self, last_seq, timeout=30.0):
        with self.cond:
            got = self.cond.wait_for(
                lambda: self.seq != last_seq and self.frame is not None,
                timeout)
            return (self.frame, self.seq) if got else (None, last_seq)


# ------------------------------------------------------------------- app ---
class App:
    def __init__(self):
        self.lock = threading.Lock()
        self.cfg = load_config()
        self.streamer = Streamer(self)

    def update_config(self, patch, save=True):
        with self.lock:
            self.cfg.update(patch)
            if save:
                save_config(self.cfg)
            self.streamer.restart()

    @property
    def configured(self):
        return bool(self.cfg.get('camera_ip'))


app = App()

# ------------------------------------------------------------------ web -----
class Handler(BaseHTTPRequestHandler):
    server_version = 'BIBAEye/1.0'

    def log_message(self, *args):
        pass

    def _json(self, obj, code=200):
        data = json.dumps(obj, ensure_ascii=False).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _read_json(self):
        try:
            length = int(self.headers.get('Content-Length', '0'))
            return json.loads(self.rfile.read(length).decode() or '{}')
        except (ValueError, json.JSONDecodeError):
            return None

    def do_GET(self):
        path = self.path.split('?')[0]
        if path in ('/', '/index.html'):
            self._serve_file(os.path.join(HERE, 'index.html'), 'text/html')
        elif path == '/stream':
            self._serve_mjpeg()
        elif path == '/api/config':
            cfg = dict(app.cfg)
            self._json({'configured': app.configured, 'config': cfg,
                        'profiles': PROFILES})
        elif path == '/api/discover':
            self._json({'subnets': local_subnets(),
                        'cameras': discover_cameras()})
        elif path == '/api/status':
            prof = PROFILES.get(app.cfg.get('profile', 'balanced'),
                                PROFILES['balanced'])
            self._json({
                'configured': app.configured,
                'camera_ip': app.cfg.get('camera_ip'),
                'profile': app.cfg.get('profile'),
                'profile_label': prof['label'],
                'stream': {'fps_target': prof['fps'], 'alive': app.streamer.alive,
                           'frames': app.streamer.seq},
                'ptz': {'speed': app.cfg.get('ptz_speed'),
                        'flip_x': app.cfg.get('flip_x'),
                        'flip_y': app.cfg.get('flip_y')},
            })
        else:
            self.send_error(404)

    def do_POST(self):
        path = self.path.split('?')[0]
        if path == '/api/config':
            self._handle_config()
        elif path == '/api/profile':
            self._handle_profile()
        elif path == '/api/ptz':
            self._handle_ptz()
        else:
            self.send_error(404)

    def _handle_config(self):
        body = self._read_json()
        if body is None:
            self.send_error(400, 'bad json')
            return
        ip = (body.get('camera_ip') or '').strip()
        if not ip:
            self._json({'ok': False, 'error': 'IP address is empty'}, 400)
            return
        patch = {
            'camera_ip': ip,
            'camera_pass': body.get('camera_pass', app.cfg.get('camera_pass')),
            'camera_user': body.get('camera_user', app.cfg.get('camera_user')),
            'onvif_port': int(body.get('onvif_port', app.cfg.get('onvif_port'))),
            'rtsp_port': int(body.get('rtsp_port', app.cfg.get('rtsp_port'))),
        }
        if body.get('profile') in PROFILES:
            patch['profile'] = body['profile']
        # validate against the camera before saving
        try:
            info = onvif_get_profiles(ip, int(patch['onvif_port']), timeout=4.0)
        except (HTTPError, URLError, OSError, RuntimeError) as exc:
            self._json({'ok': False, 'error': str(exc)}, 502)
            return
        app.update_config(patch)
        self._json({'ok': True, 'profiles': info.get('names', [])})

    def _handle_profile(self):
        body = self._read_json() or {}
        prof = body.get('profile')
        if prof not in PROFILES:
            self._json({'ok': False, 'error': 'unknown profile'}, 400)
            return
        app.update_config({'profile': prof})
        self._json({'ok': True, 'profile': prof})

    def _handle_ptz(self):
        if not app.configured:
            self._json({'ok': False, 'error': 'camera not configured'}, 409)
            return
        body = self._read_json()
        if body is None:
            self.send_error(400, 'bad json')
            return
        action = body.get('action', 'stop')
        speed = float(app.cfg.get('ptz_speed', 0.5))
        moves = {
            'up': (0.0, +speed),
            'down': (0.0, -speed),
            'left': (-speed, 0.0),
            'right': (+speed, 0.0),
        }
        try:
            if action == 'stop':
                ptz_stop(app.cfg)
            elif action in moves:
                x, y = moves[action]
                if app.cfg.get('flip_x'):
                    x = -x
                if app.cfg.get('flip_y'):
                    y = -y
                ptz_move(app.cfg, x, y)
            else:
                self._json({'ok': False, 'error': 'unknown action'}, 400)
                return
        except (HTTPError, URLError, RuntimeError, OSError) as exc:
            self._json({'ok': False, 'error': str(exc)}, 502)
            return
        self._json({'ok': True, 'action': action})

    def _serve_file(self, path, ctype):
        try:
            with open(path, 'rb') as fh:
                data = fh.read()
        except OSError:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header('Content-Type', ctype + '; charset=utf-8')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _serve_mjpeg(self):
        self.send_response(200)
        self.send_header('Content-Type',
                         'multipart/x-mixed-replace; boundary=frame')
        self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
        self.send_header('Pragma', 'no-cache')
        self.send_header('Expires', '0')
        self.end_headers()
        last = -1
        try:
            while True:
                frame, seq = app.streamer.wait_frame(last)
                if frame is None:
                    break
                last = seq
                self.wfile.write(
                    b'--frame\r\nContent-Type: image/jpeg\r\n'
                    b'Content-Length: %d\r\n\r\n' % len(frame))
                self.wfile.write(frame)
                self.wfile.write(b'\r\n')
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass


def main():
    web_port = int(app.cfg.get('web_port', 8081))
    srv = ThreadingHTTPServer(('0.0.0.0', web_port), Handler)
    print('BIBA Eye')
    print('  page:  http://127.0.0.1:%d/' % web_port)
    if app.configured:
        print('  rtsp:  %s' % rtsp_url(app.cfg))
        print('  ptz:   %s' % ptz_url(app.cfg))
    else:
        print('  camera not configured yet - enter IP on the page')
    print('Ctrl+C to stop')
    if app.cfg.get('auto_open', True):
        threading.Timer(1.0, lambda: webbrowser.open(
            'http://127.0.0.1:%d/' % web_port)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()


if __name__ == '__main__':
    main()
