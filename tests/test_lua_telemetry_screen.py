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


def test_read_motor_currents_uses_gps_heading_and_altitude_sensors() -> None:
    body = _extract_function(_lua_source(), "read_motor_currents")

    assert 'sensor("Hdg", 0)' in body
    assert 'sensor("Alt", 0)' in body


def test_read_battery_direction_uses_capacity_sensor_flag() -> None:
    body = _extract_function(_lua_source(), "read_battery_direction")

    assert 'sensor({ "Capa", "Mah", "mAh" }, 0)' in body
    assert 'return "CHG"' in body
    assert 'return "DIS"' in body


def test_read_battery_direction_masks_status_bits_from_capacity_sensor() -> None:
    body = _extract_function(_lua_source(), "read_battery_direction")

    assert "BATTERY_DIRECTION_MASK" in body
    assert "bit32.band(" in body


def test_lua_declares_status_icon_helper() -> None:
    source = _lua_source()

    assert "local function read_status_icons()" in source


def test_read_status_icons_emits_a_m_b_letters() -> None:
    body = _extract_function(_lua_source(), "read_status_icons")

    assert 'icons = icons .. "A"' in body
    assert 'icons = icons .. "M"' in body
    assert 'icons = icons .. "B"' in body


def test_read_status_icons_appends_charging_icon_only_for_charge_direction() -> None:
    body = _extract_function(_lua_source(), "read_status_icons")

    assert 'read_battery_direction() == "CHG"' in body
    assert 'icons = icons .. "C"' in body


def test_draw_compact_displays_motor_currents() -> None:
    body = _extract_function(_lua_source(), "draw_compact")

    assert "left_current" in body
    assert "right_current" in body
    assert "format_current_ma" in body


def test_draw_compact_formats_total_current_in_milliamps() -> None:
    body = _extract_function(_lua_source(), "draw_compact")

    assert "format_current_ma(current)" in body


def test_draw_compact_displays_battery_direction_label() -> None:
    body = _extract_function(_lua_source(), "draw_compact")

    assert 'lcd.drawText(49, 34, battery_direction' not in body


def test_draw_compact_uses_current_format_helper() -> None:
    body = _extract_function(_lua_source(), "draw_compact")

    assert "format_current_ma" in body


def test_draw_wide_displays_motor_currents() -> None:
    body = _extract_function(_lua_source(), "draw_wide")

    assert "left_current" in body
    assert "right_current" in body


def test_draw_wide_formats_wheel_currents_in_milliamps() -> None:
    body = _extract_function(_lua_source(), "draw_wide")

    assert body.count("format_current_ma(") >= 3


def test_draw_wide_displays_battery_direction_label() -> None:
    body = _extract_function(_lua_source(), "draw_wide")

    assert 'lcd.drawText(ix + 42, current_row_y, battery_direction' not in body


def test_draw_wide_uses_current_format_helper() -> None:
    body = _extract_function(_lua_source(), "draw_wide")

    assert "format_current_ma" in body


def test_draw_wide_uses_compact_header_style_without_rssi_text() -> None:
    body = _extract_function(_lua_source(), "draw_wide")

    assert "Q%03d" in body or "draw_header_wide(" in body
    assert 'string.format("  R %d"' not in body


def test_draw_wide_uses_rounded_rect_body() -> None:
    body = _extract_function(_lua_source(), "draw_wide")

    assert "draw_rounded_rect(" in body


def test_draw_wide_does_not_prefix_wheel_currents_with_lr_labels() -> None:
    body = _extract_function(_lua_source(), "draw_wide")

    assert 'string.format("L %s"' not in body
    assert 'string.format("R %s"' not in body


def test_draw_wheel_keeps_idle_forward_and_reverse_logic() -> None:
    body = _extract_function(_lua_source(), "draw_wheel")

    assert "math.abs(spd) < 0.05" in body
    assert "if spd > 0 then" in body
    assert "else" in body


def test_draw_wheel_caps_at_seven_arrows() -> None:
    body = _extract_function(_lua_source(), "draw_wheel")

    assert "math.min(7" in body or "math.min(max_arrows" in body


def test_draw_wheel_uses_bottom_up_for_forward_and_top_down_for_reverse() -> None:
    body = _extract_function(_lua_source(), "draw_wheel")

    assert "y + wh" in body, "forward arrows should be anchored near wheel bottom"
    assert "- i * arrow_step" in body, "forward arrows should grow upward"
    assert "y + 3" in body, "reverse arrows should start from wheel top"
    assert "+ i * arrow_step" in body, "reverse arrows should grow downward"
    assert "draw_wheel_arrow(arrow_x, arrow_y, false)" in body
    assert "draw_wheel_arrow(arrow_x, arrow_y, true)" in body


def test_draw_rounded_rect_is_separate_function() -> None:
    source = _lua_source()

    assert "local function draw_rounded_rect(" in source


def test_draw_wheel_delegates_frame_to_draw_rounded_rect() -> None:
    body = _extract_function(_lua_source(), "draw_wheel")

    assert "draw_rounded_rect(x, y, ww, wh)" in body


def test_draw_compact_keeps_six_cell_loop() -> None:
    body = _extract_function(_lua_source(), "draw_cell_frame")

    assert "math.min(#cells, CELL_COUNT)" in body
    assert 'string.format("%.2f"' in body


def test_draw_wide_keeps_six_cell_loop() -> None:
    body = _extract_function(_lua_source(), "draw_wide")

    assert "math.min(#cells, CELL_COUNT)" in body
    assert 'string.format("C%d %.2fV"' in body


def test_run_reads_motor_currents() -> None:
    body = _extract_function(_lua_source(), "run")

    assert "read_motor_currents()" in body


def test_run_reads_battery_direction() -> None:
    body = _extract_function(_lua_source(), "run")

    assert "read_battery_direction()" in body


def test_lua_declares_current_format_helper() -> None:
    source = _lua_source()

    assert "local function format_current_ma(" in source


def test_format_current_ma_zero_pads_to_five_digits() -> None:
    body = _extract_function(_lua_source(), "format_current_ma")

    assert "%05d" in body, "mA values should be zero-padded to 5 digits"


def test_draw_wheel_arrows_use_visible_draw_mode() -> None:
    body = _extract_function(_lua_source(), "draw_wheel")

    assert "SOLID, ERASE" not in body, "arrows drawn with ERASE are invisible on unfilled background"


def test_draw_compact_cell_voltage_frame() -> None:
    """draw_compact delegates cell voltages to draw_cell_frame."""
    body = _extract_function(_lua_source(), "draw_compact")
    assert "draw_cell_frame(" in body


def test_draw_cell_frame_uses_dotted_top_and_dividers() -> None:
    body = _extract_function(_lua_source(), "draw_cell_frame")
    assert "DOTTED" in body, "cell frame top/dividers must be DOTTED"


def test_draw_cell_frame_has_solid_bottom() -> None:
    body = _extract_function(_lua_source(), "draw_cell_frame")
    assert "SOLID" in body, "cell frame bottom border must be SOLID"


def test_draw_header_is_separate_function() -> None:
    source = _lua_source()
    assert "local function draw_header(" in source


def test_draw_header_formats_quality_and_appends_source_once() -> None:
    body = _extract_function(_lua_source(), "draw_header")

    assert 'string.format("Q%03d"' in body
    assert 'string.format("Q%03d PCK"' not in body
    assert 'hdr = hdr .. " " .. cell_src' in body


def test_draw_header_appends_status_icons() -> None:
    body = _extract_function(_lua_source(), "draw_header")

    assert "status_icons" in body
    assert 'hdr = hdr .. " " .. status_icons' in body


def test_draw_header_wide_appends_status_icons() -> None:
    body = _extract_function(_lua_source(), "draw_header_wide")

    assert "status_icons" in body
    assert 'hdr = hdr .. " " .. status_icons' in body


def test_draw_soc_bar_is_separate_function() -> None:
    source = _lua_source()
    assert "local function draw_soc_bar(" in source


def test_draw_compact_delegates_to_sub_functions() -> None:
    body = _extract_function(_lua_source(), "draw_compact")
    assert "draw_header(" in body
    assert "draw_cell_frame(" in body
    assert "draw_wheel(" in body
    assert "draw_soc_bar(" in body


def test_run_calls_only_one_draw_branch_and_passes_motor_currents() -> None:
    body = _extract_function(_lua_source(), "run")

    assert "if sw() >= 212 and sh() >= 128 then" in body
    assert body.count("draw_compact(") == 1
    assert body.count("draw_wide(") == 1
    assert "status_icons = read_status_icons()" in body
    assert "draw_wide(voltage, current, battery_direction, pct, rssi, rqly, cell_src, status_icons, cells, mn, mx, delta, left_spd, right_spd, cpu, ram, left_current, right_current)" in body
    assert "draw_compact(voltage, current, battery_direction, pct, rssi, rqly, cell_src, status_icons, cells, mn, mx, delta, left_spd, right_spd, cpu, ram, left_current, right_current)" in body