from __future__ import annotations

from pathlib import Path

LUA_PATH = Path("lua/SCRIPTS/TELEMETRY/biba.lua")


def _lua_source() -> str:
    return LUA_PATH.read_text(encoding="utf-8")


def _extract_function(source: str, name: str) -> str:
    marker = f"local function {name}("
    start = source.index(marker)
    tail = source[start:]
    end = tail.index("\nend\n") + len("\nend\n")
    return tail[:end]


# ── Connection detection ──────────────────────────


def test_is_connected_does_not_require_battery_voltage() -> None:
    body = _extract_function(_lua_source(), "is_connected")

    assert 'sensor("RSSI", 0)' in body
    assert "VFAS" not in body
    assert "RxBt" not in body


# ── read_cells returns data source indicator ──────


def test_read_cells_returns_source_indicator() -> None:
    """read_cells must return a second value: 'BMS', 'PCK', or empty string."""
    body = _extract_function(_lua_source(), "read_cells")

    assert '"BMS"' in body, "should return 'BMS' when Cels sensor has real data"
    assert '"PCK"' in body, "should return 'PCK' when using pack_v / CELL_COUNT"


# ── Status bar shows link quality (RQly) ─────────


def test_draw_compact_shows_rqly() -> None:
    """Compact layout must display RQly link quality metric."""
    body = _extract_function(_lua_source(), "draw_compact")

    assert "rqly" in body.lower(), "draw_compact should use rqly parameter"


def test_draw_wide_shows_rqly() -> None:
    """Wide layout must display RQly link quality metric."""
    body = _extract_function(_lua_source(), "draw_wide")

    assert "rqly" in body.lower(), "draw_wide should use rqly parameter"


# ── Status bar shows battery data source ──────────


def test_draw_compact_shows_cell_source() -> None:
    """Compact layout must display cell data source (BMS/PCK)."""
    body = _extract_function(_lua_source(), "draw_compact")

    assert "cell_src" in body, "draw_compact should use cell_src parameter"


def test_draw_wide_shows_cell_source() -> None:
    """Wide layout must display cell data source (BMS/PCK)."""
    body = _extract_function(_lua_source(), "draw_wide")

    assert "cell_src" in body, "draw_wide should use cell_src parameter"


def test_system_stats_are_zero_padded() -> None:
    """CPU/RAM values should use fixed-width 2-digit formatting to avoid jitter."""
    compact = _extract_function(_lua_source(), "draw_compact")
    wide = _extract_function(_lua_source(), "draw_wide")

    assert "%02d" in compact, "compact system stats should use zero-padded 2-digit formatting"
    assert "%02d" in wide, "wide system stats should use zero-padded 2-digit formatting"


# ── run() reads RQly and passes state to drawers ──


def test_run_reads_rqly() -> None:
    """run() must read RQly sensor and pass it to draw functions."""
    body = _extract_function(_lua_source(), "run")

    assert "RQly" in body, "run() should read RQly sensor"


def test_lua_declares_battery_holdoff_state() -> None:
    source = _lua_source()

    assert "local BATTERY_HOLDOFF_CS" in source
    assert "local battery_holdoff_until = 0" in source


def test_run_applies_battery_holdoff_on_startup_and_reconnect() -> None:
    body = _extract_function(_lua_source(), "run")

    assert "battery_holdoff_until" in body
    assert "prev_connected == nil" in body
    assert "connected and not prev_connected" in body
    assert "now + BATTERY_HOLDOFF_CS" in body
    assert "if now < battery_holdoff_until then" in body