"""Manual motor PWM test helpers and lightweight HTTP UI primitives."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Event, Lock
from typing import Any

from pid_tuning import PidTuningSnapshot, snapshot_from_mapping


_MIN_FREQUENCY_HZ = 100
_MAX_FREQUENCY_HZ = 8_000
_MIN_DUTY_PERCENT = 0.0
_MAX_DUTY_PERCENT = 100.0
_MIN_DURATION_MS = 100
_MAX_DURATION_MS = 10_000
_PIGPIO_DUTY_RANGE = 1_000_000
_SOFTWARE_PWM_FREQUENCY_OPTIONS_HZ = [100, 160, 200, 250, 320, 400, 500, 800, 1000, 1600, 2000, 4000, 8000]
_DEFAULT_PWM_MODE = "SOFTWARE"
_PWM_MODE_CHOICES = {"SOFTWARE", "HARDWARE"}


LOGGER = logging.getLogger(__name__)


class MotorTestBusyError(RuntimeError):
    """Raised when a motor test is requested while another one is active."""


@dataclass(frozen=True)
class MotorTestRequest:
    pwm_mode: str
    left_frequency_hz: int
    left_duty_percent: float
    right_frequency_hz: int
    right_duty_percent: float
    duration_ms: int


def _require_int(payload: dict[str, Any], name: str) -> int:
    value = payload.get(name)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")
    return value


def _require_number(payload: dict[str, Any], name: str) -> float:
    value = payload.get(name)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a number")
    return float(value)


def _require_pwm_mode(payload: dict[str, Any]) -> str:
    value = payload.get("pwm_mode", _DEFAULT_PWM_MODE)
    if not isinstance(value, str):
        raise ValueError("pwm_mode must be SOFTWARE or HARDWARE")
    normalized = value.strip().upper()
    if normalized not in _PWM_MODE_CHOICES:
        raise ValueError("pwm_mode must be SOFTWARE or HARDWARE")
    return normalized


def _validate_range(name: str, value: float, minimum: float, maximum: float) -> None:
    if value < minimum or value > maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")


def parse_motor_test_request(payload: dict[str, Any]) -> MotorTestRequest:
    pwm_mode = _require_pwm_mode(payload)
    left_frequency_hz = _require_int(payload, "left_frequency_hz")
    left_duty_percent = _require_number(payload, "left_duty_percent")
    right_frequency_hz = _require_int(payload, "right_frequency_hz")
    right_duty_percent = _require_number(payload, "right_duty_percent")
    duration_ms = _require_int(payload, "duration_ms")

    _validate_range("left_frequency_hz", left_frequency_hz, _MIN_FREQUENCY_HZ, _MAX_FREQUENCY_HZ)
    _validate_range("left_duty_percent", left_duty_percent, _MIN_DUTY_PERCENT, _MAX_DUTY_PERCENT)
    _validate_range("right_frequency_hz", right_frequency_hz, _MIN_FREQUENCY_HZ, _MAX_FREQUENCY_HZ)
    _validate_range("right_duty_percent", right_duty_percent, _MIN_DUTY_PERCENT, _MAX_DUTY_PERCENT)
    _validate_range("duration_ms", duration_ms, _MIN_DURATION_MS, _MAX_DURATION_MS)

    return MotorTestRequest(
        pwm_mode=pwm_mode,
        left_frequency_hz=left_frequency_hz,
        left_duty_percent=left_duty_percent,
        right_frequency_hz=right_frequency_hz,
        right_duty_percent=right_duty_percent,
        duration_ms=duration_ms,
    )


def percent_to_motor_synth_duty(duty_percent: float) -> int:
    return round(duty_percent * _PIGPIO_DUTY_RANGE / 100.0)


def _nearest_frequency_option_index(frequency_hz: int) -> int:
    return min(
        range(len(_SOFTWARE_PWM_FREQUENCY_OPTIONS_HZ)),
        key=lambda index: abs(_SOFTWARE_PWM_FREQUENCY_OPTIONS_HZ[index] - frequency_hz),
    )


class MotorTestExecutor:
    def __init__(self, synth, before_run=None, synth_factory=None) -> None:
        self._synth = synth
        self._before_run = before_run
        self._synth_factory = synth_factory
        self._lock = Lock()
        self._active_event = Event()

    @property
    def is_active(self) -> bool:
        return self._active_event.is_set()

    def run(self, request: MotorTestRequest) -> None:
        if not self._lock.acquire(blocking=False):
            raise MotorTestBusyError("motor test already active")

        synth = self._resolve_synth(request.pwm_mode)
        try:
            self._active_event.set()
            if self._before_run is not None:
                self._before_run()
            LOGGER.info(
                "Manual motor test started mode=%s left=%sHz/%s%% right=%sHz/%s%% duration=%sms",
                request.pwm_mode,
                request.left_frequency_hz,
                request.left_duty_percent,
                request.right_frequency_hz,
                request.right_duty_percent,
                request.duration_ms,
            )
            synth.play_manual_split_pwm(
                request.left_frequency_hz,
                percent_to_motor_synth_duty(request.left_duty_percent),
                request.right_frequency_hz,
                percent_to_motor_synth_duty(request.right_duty_percent),
                request.duration_ms,
            )
        finally:
            synth.off()
            self._active_event.clear()
            self._lock.release()
            LOGGER.info("Manual motor test finished")

    def _resolve_synth(self, pwm_mode: str):
        current_mode = str(getattr(self._synth, "_pwm_mode", _DEFAULT_PWM_MODE)).upper()
        if pwm_mode == current_mode:
            return self._synth
        if self._synth_factory is None:
            raise ValueError(f"pwm_mode {pwm_mode} is not supported")
        synth = self._synth_factory(pwm_mode)
        if synth is None:
            raise ValueError(f"pwm_mode {pwm_mode} is not supported")
        return synth


def build_control_page() -> str:
    allowed_frequencies_json = json.dumps(_SOFTWARE_PWM_FREQUENCY_OPTIONS_HZ)
    left_default_frequency_hz = 1000
    right_default_frequency_hz = 1200
    left_default_index = _nearest_frequency_option_index(left_default_frequency_hz)
    right_default_index = _nearest_frequency_option_index(right_default_frequency_hz)
    last_frequency_index = len(_SOFTWARE_PWM_FREQUENCY_OPTIONS_HZ) - 1

    page = """<!DOCTYPE html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\">
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
  <title>BiBa Motor Test</title>
    <style>
        body { font-family: sans-serif; max-width: 42rem; margin: 2rem auto; padding: 0 1rem; }
        form { display: grid; gap: 1rem; }
        label { display: grid; gap: 0.35rem; }
        .input-row { display: grid; gap: 0.75rem; grid-template-columns: minmax(0, 1fr) 7rem; align-items: center; }
        .input-row input[type=number] { width: 100%; }
        output { font-weight: 600; }
        button { padding: 0.8rem 1rem; }
        #status { min-height: 1.5rem; }
    </style>
</head>
<body>
  <form id=\"motor-test-form\">
        <label for=\"left_frequency_hz\">Left frequency (Hz)
            <div class=\"input-row\">
                <input id=\"left_frequency_hz\" name=\"left_frequency_hz\" type=\"range\" min=\"0\" max=\"__LAST_FREQUENCY_INDEX__\" step=\"1\" value=\"__LEFT_DEFAULT_INDEX__\">
                <input id="left_frequency_hz_input" name="left_frequency_hz_input" type="number" min="100" max="8000" step="1" value="__LEFT_DEFAULT_FREQUENCY_HZ__">
            </div>
            <small>Type any integer frequency; the slider stays on preset steps.</small>
            <output for=\"left_frequency_hz\" id=\"left_frequency_hz_value\">__LEFT_DEFAULT_FREQUENCY_HZ__</output>
        </label>
        <label for=\"left_duty_percent\">Left duty (%)
            <input id=\"left_duty_percent\" name=\"left_duty_percent\" type=\"range\" min=\"0\" max=\"100\" value=\"40\">
            <output for=\"left_duty_percent\" id=\"left_duty_percent_value\">40</output>
        </label>
        <label for=\"right_frequency_hz\">Right frequency (Hz)
            <div class=\"input-row\">
                <input id=\"right_frequency_hz\" name=\"right_frequency_hz\" type=\"range\" min=\"0\" max=\"__LAST_FREQUENCY_INDEX__\" step=\"1\" value=\"__RIGHT_DEFAULT_INDEX__\">
                <input id="right_frequency_hz_input" name="right_frequency_hz_input" type="number" min="100" max="8000" step="1" value="__RIGHT_DEFAULT_FREQUENCY_HZ__">
            </div>
            <small>Type any integer frequency; the slider stays on preset steps.</small>
            <output for=\"right_frequency_hz\" id=\"right_frequency_hz_value\">__RIGHT_DEFAULT_FREQUENCY_HZ__</output>
        </label>
        <label for=\"right_duty_percent\">Right duty (%)
            <input id=\"right_duty_percent\" name=\"right_duty_percent\" type=\"range\" min=\"0\" max=\"100\" value=\"55\">
            <output for=\"right_duty_percent\" id=\"right_duty_percent_value\">55</output>
        </label>
        <label for=\"pwm_mode\">PWM mode
            <select id=\"pwm_mode\" name=\"pwm_mode\">
                <option value=\"SOFTWARE\" selected>SOFTWARE</option>
                <option value=\"HARDWARE\">HARDWARE</option>
            </select>
        </label>
        <label for=\"duration_ms\">Duration (ms)
            <input id=\"duration_ms\" name=\"duration_ms\" type=\"number\" min=\"100\" max=\"10000\" value=\"2000\">
        </label>
    <button type=\"submit\">Send</button>
        <div id=\"status\" aria-live=\"polite\"></div>
  </form>
    <script>
        const form = document.getElementById('motor-test-form');
        const pwmModeInput = document.getElementById('pwm_mode');
        const statusNode = document.getElementById('status');
        const ALLOWED_FREQUENCIES_HZ = __ALLOWED_FREQUENCIES_JSON__;
        const MODE_CONFIG = {
            SOFTWARE: {
                discrete: true,
                minFrequencyHz: ALLOWED_FREQUENCIES_HZ[0],
                maxFrequencyHz: ALLOWED_FREQUENCIES_HZ[ALLOWED_FREQUENCIES_HZ.length - 1],
            },
            HARDWARE: {
                discrete: false,
                minFrequencyHz: 100,
                maxFrequencyHz: 8000,
            },
        };

        function currentMode() {
            return MODE_CONFIG[pwmModeInput.value] ? pwmModeInput.value : 'SOFTWARE';
        }

        function clampFrequency(mode, value) {
            const config = MODE_CONFIG[mode];
            if (!Number.isFinite(value)) {
                return config.minFrequencyHz;
            }
            return Math.min(config.maxFrequencyHz, Math.max(config.minFrequencyHz, value));
        }

        function nearestFrequencyIndex(value) {
            const clampedValue = clampFrequency('SOFTWARE', value);
            let nearestIndex = 0;
            let nearestDistance = Math.abs(ALLOWED_FREQUENCIES_HZ[0] - clampedValue);
            for (let index = 1; index < ALLOWED_FREQUENCIES_HZ.length; index += 1) {
                const distance = Math.abs(ALLOWED_FREQUENCIES_HZ[index] - clampedValue);
                if (distance < nearestDistance) {
                    nearestIndex = index;
                    nearestDistance = distance;
                }
            }
            return nearestIndex;
        }

        function syncFrequencyInputs(rangeId, numberId) {
            const rangeInput = document.getElementById(rangeId);
            const numberInput = document.getElementById(numberId);
            const output = document.getElementById(`${rangeId}_value`);

            const updateRangeAttributes = () => {
                const mode = currentMode();
                if (MODE_CONFIG[mode].discrete) {
                    rangeInput.min = '0';
                    rangeInput.max = String(ALLOWED_FREQUENCIES_HZ.length - 1);
                    rangeInput.step = '1';
                    rangeInput.value = String(nearestFrequencyIndex(Number(numberInput.value)));
                    return;
                }

                rangeInput.min = String(MODE_CONFIG[mode].minFrequencyHz);
                rangeInput.max = String(MODE_CONFIG[mode].maxFrequencyHz);
                rangeInput.step = '1';
                rangeInput.value = String(clampFrequency(mode, Number(numberInput.value)));
            };

            const updateFromIndex = (index) => {
                const frequency = ALLOWED_FREQUENCIES_HZ[Number(index)];
                rangeInput.value = String(index);
                numberInput.value = String(frequency);
                output.textContent = String(frequency);
            };

            const updateFromNumber = (value) => {
                const mode = currentMode();
                const numericValue = clampFrequency(mode, Number(value));
                numberInput.value = String(numericValue);
                output.textContent = String(numericValue);
                if (MODE_CONFIG[mode].discrete) {
                    rangeInput.value = String(nearestFrequencyIndex(numericValue));
                    return;
                }
                rangeInput.value = String(numericValue);
            };

            const previewFromNumber = (value) => {
                if (value === '') {
                    output.textContent = numberInput.value;
                    return;
                }

                const numericValue = Number(value);
                if (!Number.isFinite(numericValue)) {
                    output.textContent = numberInput.value;
                    return;
                }

                output.textContent = String(numericValue);
                if (MODE_CONFIG[currentMode()].discrete) {
                    rangeInput.value = String(nearestFrequencyIndex(numericValue));
                    return;
                }
                rangeInput.value = String(clampFrequency(currentMode(), numericValue));
            };

            rangeInput.addEventListener('input', () => {
                if (!MODE_CONFIG[currentMode()].discrete) {
                    updateFromNumber(rangeInput.value);
                    return;
                }
                updateFromIndex(rangeInput.value);
            });

            numberInput.addEventListener('input', () => {
                previewFromNumber(numberInput.value);
            });

            numberInput.addEventListener('change', () => {
                updateFromNumber(numberInput.value);
            });

            pwmModeInput.addEventListener('change', () => {
                updateRangeAttributes();
                updateFromNumber(numberInput.value);
            });

            updateRangeAttributes();
            updateFromNumber(numberInput.value);
        }

        syncFrequencyInputs('left_frequency_hz', 'left_frequency_hz_input');
        syncFrequencyInputs('right_frequency_hz', 'right_frequency_hz_input');

        for (const id of ['left_duty_percent', 'right_duty_percent']) {
            const input = document.getElementById(id);
            const output = document.getElementById(`${id}_value`);
            input.addEventListener('input', () => {
                output.textContent = input.value;
            });
        }

        form.addEventListener('submit', async (event) => {
            event.preventDefault();
            statusNode.textContent = 'Sending...';
            const payload = {
                pwm_mode: document.getElementById('pwm_mode').value,
                left_frequency_hz: Number(document.getElementById('left_frequency_hz_input').value),
                left_duty_percent: Number(document.getElementById('left_duty_percent').value),
                right_frequency_hz: Number(document.getElementById('right_frequency_hz_input').value),
                right_duty_percent: Number(document.getElementById('right_duty_percent').value),
                duration_ms: Number(document.getElementById('duration_ms').value),
            };

            try {
                const response = await fetch('/api/motor-test', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload),
                });
                const body = await response.json();
                if (!response.ok) {
                    throw new Error(body.error || `HTTP ${response.status}`);
                }
                statusNode.textContent = 'Command sent';
            } catch (error) {
                statusNode.textContent = `Error: ${error.message}`;
            }
        });
    </script>
</body>
</html>
"""

    return (
        page.replace("__ALLOWED_FREQUENCIES_JSON__", allowed_frequencies_json)
        .replace("__LEFT_DEFAULT_INDEX__", str(left_default_index))
        .replace("__RIGHT_DEFAULT_INDEX__", str(right_default_index))
        .replace("__LEFT_DEFAULT_FREQUENCY_HZ__", str(left_default_frequency_hz))
        .replace("__RIGHT_DEFAULT_FREQUENCY_HZ__", str(right_default_frequency_hz))
        .replace("__LAST_FREQUENCY_INDEX__", str(last_frequency_index))
    )


def build_pid_tuning_page(defaults: PidTuningSnapshot) -> str:
        defaults_json = json.dumps(defaults.to_dict())
        return f"""<!DOCTYPE html>
<html lang=\"en\">
<head>
    <meta charset=\"utf-8\">
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
    <title>BiBa PID Tuning</title>
    <style>
        body {{ font-family: sans-serif; max-width: 46rem; margin: 2rem auto; padding: 0 1rem; }}
        nav {{ margin-bottom: 1rem; }}
        form {{ display: grid; gap: 1rem; }}
        fieldset {{ display: grid; gap: 0.75rem; }}
        label {{ display: grid; gap: 0.35rem; }}
        input[type=number] {{ width: 100%; max-width: 12rem; }}
        .actions {{ display: flex; gap: 0.75rem; flex-wrap: wrap; }}
        .status {{ min-height: 1.5rem; }}
        .meta {{ display: grid; gap: 0.35rem; margin-bottom: 1rem; }}
    </style>
</head>
<body>
    <nav><a href=\"/motor-test\">Motor test</a></nav>
    <h1>BiBa PID Tuning</h1>
    <div class=\"meta\">
        <div id=\"armed_state\">State: unknown</div>
        <div id=\"applied_revision\">Applied revision: n/a</div>
        <div id=\"pending_revision\">Pending revision: none</div>
    </div>
    <form id=\"pid-tuning-form\">
        <fieldset>
            <legend>Yaw-rate PID</legend>
            <label for=\"yaw_rate_kp\">Kp<input id=\"yaw_rate_kp\" name=\"yaw_rate_kp\" type=\"number\" min=\"0\" max=\"1\" step=\"0.001\"></label>
            <label for=\"yaw_rate_ki\">Ki<input id=\"yaw_rate_ki\" name=\"yaw_rate_ki\" type=\"number\" min=\"0\" max=\"1\" step=\"0.001\"></label>
            <label for=\"yaw_rate_kd\">Kd<input id=\"yaw_rate_kd\" name=\"yaw_rate_kd\" type=\"number\" min=\"0\" max=\"1\" step=\"0.001\"></label>
        </fieldset>
        <fieldset>
            <legend>Yaw-rate shaping</legend>
            <label for=\"yaw_rate_deadband_dps\">Deadband (dps)<input id=\"yaw_rate_deadband_dps\" name=\"yaw_rate_deadband_dps\" type=\"number\" min=\"0\" max=\"45\" step=\"0.1\"></label>
            <label for=\"yaw_rate_filter_hz\">Filter (Hz)<input id=\"yaw_rate_filter_hz\" name=\"yaw_rate_filter_hz\" type=\"number\" min=\"0\" max=\"30\" step=\"0.1\"></label>
        </fieldset>
        <fieldset>
            <legend>Low-speed stabilization</legend>
            <label for=\"stabilization_min_throttle\">Min throttle<input id=\"stabilization_min_throttle\" name=\"stabilization_min_throttle\" type=\"number\" min=\"0\" max=\"1\" step=\"0.01\"></label>
            <label for=\"neutral_stabilization_steering_limit\">Steering limit<input id=\"neutral_stabilization_steering_limit\" name=\"neutral_stabilization_steering_limit\" type=\"number\" min=\"0\" max=\"1\" step=\"0.01\"></label>
            <label for=\"neutral_stabilization_max_throttle\">Max throttle<input id=\"neutral_stabilization_max_throttle\" name=\"neutral_stabilization_max_throttle\" type=\"number\" min=\"0\" max=\"1\" step=\"0.01\"></label>
        </fieldset>
        <div class=\"actions\">
            <button type=\"submit\">Apply tuning</button>
            <button type=\"button\" id=\"load-defaults\">Load defaults</button>
        </div>
        <div id=\"status\" class=\"status\" aria-live=\"polite\"></div>
    </form>
    <script>
        const DEFAULT_TUNING = {defaults_json};
        const form = document.getElementById('pid-tuning-form');
        const applyButton = form.querySelector('button[type="submit"]');
        const statusNode = document.getElementById('status');
        const armedStateNode = document.getElementById('armed_state');
        const appliedRevisionNode = document.getElementById('applied_revision');
        const pendingRevisionNode = document.getElementById('pending_revision');
        const fields = Object.keys(DEFAULT_TUNING);

        function applyValues(values) {{
            for (const field of fields) {{
                if (values[field] !== undefined) {{
                    document.getElementById(field).value = values[field];
                }}
            }}
        }}

        function renderStatus(payload) {{
            armedStateNode.textContent = `State: ${{payload.armed ? 'armed' : 'disarmed'}}`;
            appliedRevisionNode.textContent = `Applied revision: ${{payload.applied_revision}}`;
            pendingRevisionNode.textContent = `Pending revision: ${{payload.pending_revision ?? 'none'}}`;
            applyButton.disabled = payload.armed;
            applyValues(payload.pending || payload.current || DEFAULT_TUNING);
            if (payload.armed) {{
                statusNode.textContent = 'Disarm the platform to apply tuning changes';
            }} else if (payload.pending_revision !== null) {{
                statusNode.textContent = 'Tuning update queued';
            }}
        }}

        async function refreshStatus() {{
            const response = await fetch('/api/pid-tuning');
            const body = await response.json();
            renderStatus(body);
            return body;
        }}

        document.getElementById('load-defaults').addEventListener('click', () => {{
            applyValues(DEFAULT_TUNING);
            statusNode.textContent = 'Loaded defaults into the form';
        }});

        form.addEventListener('submit', async (event) => {{
            event.preventDefault();
            statusNode.textContent = 'Applying...';
            const payload = Object.fromEntries(fields.map((field) => [field, Number(document.getElementById(field).value)]));
            try {{
                const response = await fetch('/api/pid-tuning', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify(payload),
                }});
                const body = await response.json();
                if (!response.ok) {{
                    throw new Error(body.error || `HTTP ${{response.status}}`);
                }}
                renderStatus(body);
                statusNode.textContent = 'Tuning update queued';
            }} catch (error) {{
                statusNode.textContent = `Error: ${{error.message}}`;
            }}
        }});

        refreshStatus();
        setInterval(refreshStatus, 1000);
    </script>
</body>
</html>
"""


def _write_json_response(handler: BaseHTTPRequestHandler, status: int, payload: dict[str, Any]) -> None:
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _write_html_response(handler: BaseHTTPRequestHandler, body: str) -> None:
    encoded = body.encode("utf-8")
    handler.send_response(HTTPStatus.OK)
    handler.send_header("Content-Type", "text/html; charset=utf-8")
    handler.send_header("Content-Length", str(len(encoded)))
    handler.end_headers()
    handler.wfile.write(encoded)


def _serialize_pid_tuning_status(status) -> dict[str, Any]:
    return {
        "armed": status.armed,
        "applied_revision": status.applied_revision,
        "pending_revision": status.pending_revision,
        "current": status.current.to_dict(),
        "defaults": status.defaults.to_dict(),
        "pending": None if status.pending is None else status.pending.to_dict(),
        "last_error": status.last_error,
    }


def create_motor_test_server(executor, *, host: str, port: int, pid_tuning_store=None) -> ThreadingHTTPServer:
    class MotorTestRequestHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path == "/motor-test":
                _write_html_response(self, build_control_page())
                return
            if self.path == "/pid-tuning":
                if pid_tuning_store is None:
                    self.send_error(HTTPStatus.NOT_FOUND)
                    return
                status = pid_tuning_store.snapshot_status()
                _write_html_response(self, build_pid_tuning_page(status.defaults))
                return
            if self.path == "/api/pid-tuning":
                if pid_tuning_store is None:
                    self.send_error(HTTPStatus.NOT_FOUND)
                    return
                _write_json_response(self, HTTPStatus.OK, _serialize_pid_tuning_status(pid_tuning_store.snapshot_status()))
                return
            self.send_error(HTTPStatus.NOT_FOUND)

        def do_POST(self) -> None:
            if self.path == "/api/motor-test":
                content_length = int(self.headers.get("Content-Length", "0"))
                raw_body = self.rfile.read(content_length)
                try:
                    payload = json.loads(raw_body.decode("utf-8"))
                    request = parse_motor_test_request(payload)
                    executor.run(request)
                except json.JSONDecodeError:
                    _write_json_response(self, HTTPStatus.BAD_REQUEST, {"error": "invalid json"})
                    return
                except ValueError as exc:
                    _write_json_response(self, HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                    return
                except MotorTestBusyError as exc:
                    _write_json_response(self, HTTPStatus.CONFLICT, {"error": str(exc)})
                    return

                _write_json_response(self, HTTPStatus.OK, {"status": "ok"})
                return

            if self.path == "/api/pid-tuning":
                if pid_tuning_store is None:
                    self.send_error(HTTPStatus.NOT_FOUND)
                    return

                content_length = int(self.headers.get("Content-Length", "0"))
                raw_body = self.rfile.read(content_length)
                try:
                    payload = json.loads(raw_body.decode("utf-8"))
                    status = pid_tuning_store.snapshot_status()
                    snapshot = snapshot_from_mapping(payload, defaults=status.current)
                    pid_tuning_store.request_update(snapshot)
                except json.JSONDecodeError:
                    _write_json_response(self, HTTPStatus.BAD_REQUEST, {"error": "invalid json"})
                    return
                except ValueError as exc:
                    _write_json_response(self, HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                    return
                except RuntimeError as exc:
                    _write_json_response(self, HTTPStatus.CONFLICT, {"error": str(exc)})
                    return

                _write_json_response(self, HTTPStatus.OK, _serialize_pid_tuning_status(pid_tuning_store.snapshot_status()))
                return

            self.send_error(HTTPStatus.NOT_FOUND)

        def log_message(self, format: str, *args: object) -> None:
            del format, args

    return ThreadingHTTPServer((host, port), MotorTestRequestHandler)