from __future__ import annotations

from datetime import datetime, timezone
from io import StringIO
from pathlib import Path
import importlib.util


SCRIPT_PATH = Path("scripts/vcp_capture.py")


def _load_module():
    spec = importlib.util.spec_from_file_location("vcp_capture", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_format_log_line_prefixes_wall_time_and_epoch() -> None:
    module = _load_module()

    line = module.format_log_line(
        "T=43599 CON=1",
        datetime(2026, 3, 28, 21, 45, 6, 123456, tzinfo=timezone.utc),
        1774730706.123456,
    )

    assert line == (
        "2026-03-28T21:45:06.123456+00:00 epoch=1774730706.123456 T=43599 CON=1\n"
    )


def test_capture_stream_writes_timestamped_lines() -> None:
    module = _load_module()

    class FakeReader:
        def __init__(self, lines: list[bytes]) -> None:
            self._lines = list(lines)

        def readline(self) -> bytes:
            if self._lines:
                return self._lines.pop(0)
            return b""

    moments = iter(
        [
            datetime(2026, 3, 28, 21, 45, 6, tzinfo=timezone.utc),
            datetime(2026, 3, 28, 21, 45, 7, tzinfo=timezone.utc),
        ]
    )
    epochs = iter([1774730706.0, 1774730707.0])
    output = StringIO()

    module.capture_stream(
        FakeReader([b"first line\n", b"second line\n"]),
        output,
        now_fn=lambda: next(moments),
        epoch_fn=lambda: next(epochs),
        max_empty_reads=1,
    )

    assert output.getvalue().splitlines() == [
        "2026-03-28T21:45:06+00:00 epoch=1774730706.000000 first line",
        "2026-03-28T21:45:07+00:00 epoch=1774730707.000000 second line",
    ]


def test_default_output_path_targets_telemetry_capture_dir() -> None:
    module = _load_module()

    path = module.default_output_path(
        datetime(2026, 3, 28, 21, 44, 54, tzinfo=timezone.utc)
    )

    assert path == Path("artifacts/telemetry-captures/vcp-20260328-214454.log")