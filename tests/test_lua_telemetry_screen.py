from __future__ import annotations

from pathlib import Path


def _extract_function(source: str, name: str) -> str:
    marker = f"local function {name}()"
    start = source.index(marker)
    tail = source[start:]
    end = tail.index("\nend\n") + len("\nend\n")
    return tail[:end]


def test_is_connected_does_not_require_battery_voltage() -> None:
    source = Path("lua/SCRIPTS/TELEMETRY/biba.lua").read_text(encoding="utf-8")
    body = _extract_function(source, "is_connected")

    assert 'sensor("RSSI", 0)' in body
    assert 'VFAS' not in body
    assert 'RxBt' not in body