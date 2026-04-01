from __future__ import annotations

import importlib
import json
import threading
import urllib.error
import urllib.request

import pytest


def test_parse_motor_test_request_accepts_valid_payload() -> None:
    motor_test_api = importlib.import_module("motor_test_api")

    request = motor_test_api.parse_motor_test_request(
        {
            "pwm_mode": "SOFTWARE",
            "left_frequency_hz": 1000,
            "left_duty_percent": 40,
            "right_frequency_hz": 1200,
            "right_duty_percent": 55,
            "duration_ms": 2000,
        }
    )

    assert request.pwm_mode == "SOFTWARE"
    assert request.left_frequency_hz == 1000
    assert request.left_duty_percent == 40
    assert request.right_frequency_hz == 1200
    assert request.right_duty_percent == 55
    assert request.duration_ms == 2000


def test_parse_motor_test_request_defaults_pwm_mode_to_software() -> None:
    motor_test_api = importlib.import_module("motor_test_api")

    request = motor_test_api.parse_motor_test_request(
        {
            "left_frequency_hz": 1000,
            "left_duty_percent": 40,
            "right_frequency_hz": 1200,
            "right_duty_percent": 55,
            "duration_ms": 2000,
        }
    )

    assert request.pwm_mode == "SOFTWARE"


def test_parse_motor_test_request_rejects_out_of_range_values() -> None:
    motor_test_api = importlib.import_module("motor_test_api")

    with pytest.raises(ValueError, match="left_frequency_hz"):
        motor_test_api.parse_motor_test_request(
            {
                "left_frequency_hz": 99,
                "left_duty_percent": 40,
                "right_frequency_hz": 1200,
                "right_duty_percent": 55,
                "duration_ms": 2000,
            }
        )


def test_percent_to_motor_synth_duty_scales_to_pigpio_range() -> None:
    motor_test_api = importlib.import_module("motor_test_api")

    assert motor_test_api.percent_to_motor_synth_duty(0) == 0
    assert motor_test_api.percent_to_motor_synth_duty(12.5) == 125_000
    assert motor_test_api.percent_to_motor_synth_duty(100) == 1_000_000


def test_executor_calls_synth_and_always_stops() -> None:
    motor_test_api = importlib.import_module("motor_test_api")
    calls: list[tuple[int, int, int, int, int]] = []
    stops: list[str] = []

    class FakeSynth:
        def play_manual_split_pwm(
            self,
            left_frequency_hz: int,
            left_duty_cycle: int,
            right_frequency_hz: int,
            right_duty_cycle: int,
            duration_ms: int,
        ) -> None:
            calls.append(
                (
                    left_frequency_hz,
                    left_duty_cycle,
                    right_frequency_hz,
                    right_duty_cycle,
                    duration_ms,
                )
            )

        def off(self) -> None:
            stops.append("off")

    executor = motor_test_api.MotorTestExecutor(FakeSynth())
    request = motor_test_api.parse_motor_test_request(
        {
            "pwm_mode": "SOFTWARE",
            "left_frequency_hz": 1000,
            "left_duty_percent": 40,
            "right_frequency_hz": 1200,
            "right_duty_percent": 55,
            "duration_ms": 2000,
        }
    )

    executor.run(request)

    assert calls == [(1000, 400_000, 1200, 550_000, 2000)]
    assert stops == ["off"]


def test_executor_uses_requested_pwm_mode_synth_factory() -> None:
    motor_test_api = importlib.import_module("motor_test_api")
    default_calls: list[tuple[int, int, int, int, int]] = []
    hardware_calls: list[tuple[int, int, int, int, int]] = []

    class DefaultSynth:
        _pwm_mode = "SOFTWARE"

        def play_manual_split_pwm(
            self,
            left_frequency_hz: int,
            left_duty_cycle: int,
            right_frequency_hz: int,
            right_duty_cycle: int,
            duration_ms: int,
        ) -> None:
            default_calls.append(
                (
                    left_frequency_hz,
                    left_duty_cycle,
                    right_frequency_hz,
                    right_duty_cycle,
                    duration_ms,
                )
            )

        def off(self) -> None:
            pass

    class HardwareSynth:
        _pwm_mode = "HARDWARE"

        def play_manual_split_pwm(
            self,
            left_frequency_hz: int,
            left_duty_cycle: int,
            right_frequency_hz: int,
            right_duty_cycle: int,
            duration_ms: int,
        ) -> None:
            hardware_calls.append(
                (
                    left_frequency_hz,
                    left_duty_cycle,
                    right_frequency_hz,
                    right_duty_cycle,
                    duration_ms,
                )
            )

        def off(self) -> None:
            pass

    executor = motor_test_api.MotorTestExecutor(
        DefaultSynth(),
        synth_factory=lambda pwm_mode: HardwareSynth() if pwm_mode == "HARDWARE" else DefaultSynth(),
    )
    request = motor_test_api.parse_motor_test_request(
        {
            "pwm_mode": "HARDWARE",
            "left_frequency_hz": 1000,
            "left_duty_percent": 40,
            "right_frequency_hz": 1200,
            "right_duty_percent": 55,
            "duration_ms": 2000,
        }
    )

    executor.run(request)

    assert default_calls == []
    assert hardware_calls == [(1000, 400_000, 1200, 550_000, 2000)]


def test_executor_stops_even_when_synth_raises() -> None:
    motor_test_api = importlib.import_module("motor_test_api")
    stops: list[str] = []

    class FakeSynth:
        def play_manual_split_pwm(
            self,
            left_frequency_hz: int,
            left_duty_cycle: int,
            right_frequency_hz: int,
            right_duty_cycle: int,
            duration_ms: int,
        ) -> None:
            del left_frequency_hz, left_duty_cycle, right_frequency_hz, right_duty_cycle, duration_ms
            raise RuntimeError("boom")

        def off(self) -> None:
            stops.append("off")

    executor = motor_test_api.MotorTestExecutor(FakeSynth())
    request = motor_test_api.parse_motor_test_request(
        {
            "left_frequency_hz": 1000,
            "left_duty_percent": 40,
            "right_frequency_hz": 1200,
            "right_duty_percent": 55,
            "duration_ms": 2000,
        }
    )

    with pytest.raises(RuntimeError, match="boom"):
        executor.run(request)

    assert stops == ["off"]


def test_executor_rejects_concurrent_requests() -> None:
    motor_test_api = importlib.import_module("motor_test_api")
    entered = threading.Event()
    release = threading.Event()

    class FakeSynth:
        def play_manual_split_pwm(
            self,
            left_frequency_hz: int,
            left_duty_cycle: int,
            right_frequency_hz: int,
            right_duty_cycle: int,
            duration_ms: int,
        ) -> None:
            del left_frequency_hz, left_duty_cycle, right_frequency_hz, right_duty_cycle, duration_ms
            entered.set()
            release.wait(timeout=2.0)

        def off(self) -> None:
            pass

    executor = motor_test_api.MotorTestExecutor(FakeSynth())
    request = motor_test_api.parse_motor_test_request(
        {
            "left_frequency_hz": 1000,
            "left_duty_percent": 40,
            "right_frequency_hz": 1200,
            "right_duty_percent": 55,
            "duration_ms": 2000,
        }
    )

    worker = threading.Thread(target=executor.run, args=(request,), daemon=True)
    worker.start()
    assert entered.wait(timeout=1.0)

    with pytest.raises(motor_test_api.MotorTestBusyError):
        executor.run(request)

    release.set()
    worker.join(timeout=1.0)
    assert not worker.is_alive()


def test_executor_reports_active_and_runs_before_run_callback() -> None:
    motor_test_api = importlib.import_module("motor_test_api")
    entered = threading.Event()
    release = threading.Event()
    before_run_calls: list[str] = []

    class FakeSynth:
        def play_manual_split_pwm(
            self,
            left_frequency_hz: int,
            left_duty_cycle: int,
            right_frequency_hz: int,
            right_duty_cycle: int,
            duration_ms: int,
        ) -> None:
            del left_frequency_hz, left_duty_cycle, right_frequency_hz, right_duty_cycle, duration_ms
            entered.set()
            release.wait(timeout=2.0)

        def off(self) -> None:
            pass

    executor = motor_test_api.MotorTestExecutor(
        FakeSynth(),
        before_run=lambda: before_run_calls.append("before_run"),
    )
    request = motor_test_api.parse_motor_test_request(
        {
            "left_frequency_hz": 1000,
            "left_duty_percent": 40,
            "right_frequency_hz": 1200,
            "right_duty_percent": 55,
            "duration_ms": 2000,
        }
    )

    worker = threading.Thread(target=executor.run, args=(request,), daemon=True)
    worker.start()
    assert entered.wait(timeout=1.0)

    assert executor.is_active is True
    assert before_run_calls == ["before_run"]

    release.set()
    worker.join(timeout=1.0)
    assert not worker.is_alive()
    assert executor.is_active is False


def test_build_control_page_contains_expected_inputs() -> None:
    motor_test_api = importlib.import_module("motor_test_api")

    page = motor_test_api.build_control_page()

    assert "ALLOWED_FREQUENCIES_HZ" in page
    assert "pwm_mode" in page
    assert 'value="SOFTWARE"' in page
    assert 'value="HARDWARE"' in page
    assert "[100, 160, 200, 250, 320, 400, 500, 800, 1000, 1600, 2000, 4000, 8000]" in page
    assert "left_frequency_hz" in page
    assert 'id="left_frequency_hz_input"' in page
    assert 'name="left_frequency_hz_input"' in page
    assert 'id="left_frequency_hz_input" name="left_frequency_hz_input" type="number" min="100" max="8000" step="1"' in page
    assert 'id="left_frequency_hz" name="left_frequency_hz" type="range" min="0"' in page
    assert "document.getElementById('left_frequency_hz_input').value" in page
    assert "document.getElementById('pwm_mode').value" in page
    assert "left_duty_percent" in page
    assert "right_frequency_hz" in page
    assert 'id="right_frequency_hz_input"' in page
    assert 'name="right_frequency_hz_input"' in page
    assert 'id="right_frequency_hz_input" name="right_frequency_hz_input" type="number" min="100" max="8000" step="1"' in page
    assert 'id="right_frequency_hz" name="right_frequency_hz" type="range" min="0"' in page
    assert "document.getElementById('right_frequency_hz_input').value" in page
    assert "right_duty_percent" in page
    assert "duration_ms" in page
    assert "/api/motor-test" in page
    assert "fetch(" in page
    assert "Type any integer frequency; the slider stays on preset steps." in page


def test_http_server_serves_control_page() -> None:
    motor_test_api = importlib.import_module("motor_test_api")

    class FakeExecutor:
        def run(self, request) -> None:
            del request

    server = motor_test_api.create_motor_test_server(FakeExecutor(), host="127.0.0.1", port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{server.server_port}/motor-test", timeout=2.0) as response:
            body = response.read().decode("utf-8")

        assert response.status == 200
        assert "left_frequency_hz" in body
        assert "right_duty_percent" in body
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=1.0)


def test_http_server_posts_request_to_executor() -> None:
    motor_test_api = importlib.import_module("motor_test_api")
    captured: list[object] = []

    class FakeExecutor:
        def run(self, request) -> None:
            captured.append(request)

    server = motor_test_api.create_motor_test_server(FakeExecutor(), host="127.0.0.1", port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        payload = json.dumps(
            {
                "pwm_mode": "SOFTWARE",
                "left_frequency_hz": 1000,
                "left_duty_percent": 40,
                "right_frequency_hz": 1200,
                "right_duty_percent": 55,
                "duration_ms": 2000,
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            f"http://127.0.0.1:{server.server_port}/api/motor-test",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=2.0) as response:
            body = json.loads(response.read().decode("utf-8"))

        assert response.status == 200
        assert body == {"status": "ok"}
        assert len(captured) == 1
        assert captured[0].left_frequency_hz == 1000
        assert captured[0].right_duty_percent == 55
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=1.0)


def test_http_server_returns_409_when_executor_is_busy() -> None:
    motor_test_api = importlib.import_module("motor_test_api")

    class FakeExecutor:
        def run(self, request) -> None:
            del request
            raise motor_test_api.MotorTestBusyError("busy")

    server = motor_test_api.create_motor_test_server(FakeExecutor(), host="127.0.0.1", port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        payload = json.dumps(
            {
                "pwm_mode": "SOFTWARE",
                "left_frequency_hz": 1000,
                "left_duty_percent": 40,
                "right_frequency_hz": 1200,
                "right_duty_percent": 55,
                "duration_ms": 2000,
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            f"http://127.0.0.1:{server.server_port}/api/motor-test",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(request, timeout=2.0)

        assert exc_info.value.code == 409
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=1.0)