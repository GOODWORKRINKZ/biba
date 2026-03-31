"""Manual motor PWM test helpers and lightweight HTTP UI primitives."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Event, Lock
from typing import Any


_MIN_FREQUENCY_HZ = 100
_MAX_FREQUENCY_HZ = 8_000
_MIN_DUTY_PERCENT = 0.0
_MAX_DUTY_PERCENT = 100.0
_MIN_DURATION_MS = 100
_MAX_DURATION_MS = 10_000
_PIGPIO_DUTY_RANGE = 1_000_000


LOGGER = logging.getLogger(__name__)


class MotorTestBusyError(RuntimeError):
    """Raised when a motor test is requested while another one is active."""


@dataclass(frozen=True)
class MotorTestRequest:
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


def _validate_range(name: str, value: float, minimum: float, maximum: float) -> None:
    if value < minimum or value > maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")


def parse_motor_test_request(payload: dict[str, Any]) -> MotorTestRequest:
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
        left_frequency_hz=left_frequency_hz,
        left_duty_percent=left_duty_percent,
        right_frequency_hz=right_frequency_hz,
        right_duty_percent=right_duty_percent,
        duration_ms=duration_ms,
    )


def percent_to_motor_synth_duty(duty_percent: float) -> int:
    return round(duty_percent * _PIGPIO_DUTY_RANGE / 100.0)


class MotorTestExecutor:
    def __init__(self, synth, before_run=None) -> None:
        self._synth = synth
        self._before_run = before_run
        self._lock = Lock()
        self._active_event = Event()

    @property
    def is_active(self) -> bool:
        return self._active_event.is_set()

    def run(self, request: MotorTestRequest) -> None:
        if not self._lock.acquire(blocking=False):
            raise MotorTestBusyError("motor test already active")

        try:
            self._active_event.set()
            if self._before_run is not None:
                self._before_run()
            LOGGER.info(
                "Manual motor test started left=%sHz/%s%% right=%sHz/%s%% duration=%sms",
                request.left_frequency_hz,
                request.left_duty_percent,
                request.right_frequency_hz,
                request.right_duty_percent,
                request.duration_ms,
            )
            self._synth.play_manual_split_pwm(
                request.left_frequency_hz,
                percent_to_motor_synth_duty(request.left_duty_percent),
                request.right_frequency_hz,
                percent_to_motor_synth_duty(request.right_duty_percent),
                request.duration_ms,
            )
        finally:
            self._synth.off()
            self._active_event.clear()
            self._lock.release()
            LOGGER.info("Manual motor test finished")


def build_control_page() -> str:
    return """<!DOCTYPE html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\">
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
  <title>BiBa Motor Test</title>
    <style>
        body { font-family: sans-serif; max-width: 42rem; margin: 2rem auto; padding: 0 1rem; }
        form { display: grid; gap: 1rem; }
        label { display: grid; gap: 0.35rem; }
        output { font-weight: 600; }
        button { padding: 0.8rem 1rem; }
        #status { min-height: 1.5rem; }
    </style>
</head>
<body>
  <form id=\"motor-test-form\">
        <label for=\"left_frequency_hz\">Left frequency (Hz)
            <input id=\"left_frequency_hz\" name=\"left_frequency_hz\" type=\"range\" min=\"100\" max=\"8000\" value=\"1000\">
            <output for=\"left_frequency_hz\" id=\"left_frequency_hz_value\">1000</output>
        </label>
        <label for=\"left_duty_percent\">Left duty (%)
            <input id=\"left_duty_percent\" name=\"left_duty_percent\" type=\"range\" min=\"0\" max=\"100\" value=\"40\">
            <output for=\"left_duty_percent\" id=\"left_duty_percent_value\">40</output>
        </label>
        <label for=\"right_frequency_hz\">Right frequency (Hz)
            <input id=\"right_frequency_hz\" name=\"right_frequency_hz\" type=\"range\" min=\"100\" max=\"8000\" value=\"1200\">
            <output for=\"right_frequency_hz\" id=\"right_frequency_hz_value\">1200</output>
        </label>
        <label for=\"right_duty_percent\">Right duty (%)
            <input id=\"right_duty_percent\" name=\"right_duty_percent\" type=\"range\" min=\"0\" max=\"100\" value=\"55\">
            <output for=\"right_duty_percent\" id=\"right_duty_percent_value\">55</output>
        </label>
        <label for=\"duration_ms\">Duration (ms)
            <input id=\"duration_ms\" name=\"duration_ms\" type=\"number\" min=\"100\" max=\"10000\" value=\"2000\">
        </label>
    <button type=\"submit\">Send</button>
        <div id=\"status\" aria-live=\"polite\"></div>
  </form>
    <script>
        const form = document.getElementById('motor-test-form');
        const statusNode = document.getElementById('status');
        for (const id of ['left_frequency_hz', 'left_duty_percent', 'right_frequency_hz', 'right_duty_percent']) {
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
                left_frequency_hz: Number(document.getElementById('left_frequency_hz').value),
                left_duty_percent: Number(document.getElementById('left_duty_percent').value),
                right_frequency_hz: Number(document.getElementById('right_frequency_hz').value),
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


def _write_json_response(handler: BaseHTTPRequestHandler, status: int, payload: dict[str, Any]) -> None:
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def create_motor_test_server(executor, *, host: str, port: int) -> ThreadingHTTPServer:
    class MotorTestRequestHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path != "/motor-test":
                self.send_error(HTTPStatus.NOT_FOUND)
                return

            body = build_control_page().encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self) -> None:
            if self.path != "/api/motor-test":
                self.send_error(HTTPStatus.NOT_FOUND)
                return

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

        def log_message(self, format: str, *args: object) -> None:
            del format, args

    return ThreadingHTTPServer((host, port), MotorTestRequestHandler)