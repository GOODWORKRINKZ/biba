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


def test_lua_declares_wheel_current_adapter_helpers() -> None:
    source = _lua_source()

    assert "local function read_left_wheel_current_ma()" in source
    assert "local function read_right_wheel_current_ma()" in source


def test_read_left_wheel_current_ma_uses_heading_sensor_and_returns_ma() -> None:
    body = _extract_function(_lua_source(), "read_left_wheel_current_ma")

    assert 'sensor("Hdg", 0)' in body
    assert "* 100" in body
    assert "math.max(0" in body


def test_read_right_wheel_current_ma_normalizes_altitude_offset() -> None:
    body = _extract_function(_lua_source(), "read_right_wheel_current_ma")
    source = _lua_source()

    assert 'sensor("Alt", 0)' in body
    assert "RIGHT_WHEEL_CURRENT_ALTITUDE_OFFSET" in body
    assert "RIGHT_WHEEL_CURRENT_ALTITUDE_SCALE" in body
    assert "math.max(0" in body
    assert "local RIGHT_WHEEL_CURRENT_ALTITUDE_OFFSET = 1000.0" in source
    assert "local RIGHT_WHEEL_CURRENT_ALTITUDE_SCALE = 100.0" in source


def test_read_motor_currents_delegates_to_canonical_wheel_current_helpers() -> None:
    body = _extract_function(_lua_source(), "read_motor_currents")

    assert "read_left_wheel_current_ma()" in body
    assert "read_right_wheel_current_ma()" in body


def test_read_battery_direction_uses_capacity_sensor_flag() -> None:
    body = _extract_function(_lua_source(), "read_battery_direction")

    assert 'sensor({ "Capa", "Mah", "mAh" }, 0)' in body
    assert 'return "CHG"' in body
    assert 'return "DIS"' in body


def test_read_battery_direction_masks_status_bits_from_capacity_sensor() -> None:
    body = _extract_function(_lua_source(), "read_battery_direction")

    assert "BATTERY_DIRECTION_MASK" in body
    assert "bit32.band(" in body


def test_lua_declares_local_status_badge_helper() -> None:
    source = _lua_source()

    assert "local function read_local_status_badges()" in source


def test_lua_declares_local_app_channel_constants() -> None:
    source = _lua_source()

    assert 'local APP_ARM_CHANNEL = "ch5"' in source
    assert 'local APP_BEACON_CHANNEL = "ch8"' in source
    assert 'local APP_DRIVE_MODE_CHANNEL = "ch7"' in source
    assert 'local APP_MUTE_CHANNEL = "ch10"' in source


def test_lua_declares_speed_mode_constants() -> None:
    source = _lua_source()

    assert 'local APP_SPEED_MODE_CHANNEL = "ch6"' in source
    assert "local APP_SPEED_MODE_SLOW_SCALE" in source
    assert "local APP_SPEED_MODE_MEDIUM_SCALE" in source
    assert "local APP_SPEED_MODE_FAST_SCALE" in source
    assert "local APP_SPEED_MODE_LOW_THRESHOLD" in source
    assert "local APP_SPEED_MODE_HIGH_THRESHOLD" in source


def test_lua_declares_drive_mode_helper() -> None:
    source = _lua_source()

    assert "local function read_drive_mode()" in source


def test_read_drive_mode_reads_selector_channel_and_returns_all_modes() -> None:
    body = _extract_function(_lua_source(), "read_drive_mode")

    assert 'sensor(APP_DRIVE_MODE_CHANNEL, 0)' in body
    assert "APP_SWITCH_THRESHOLD" in body
    assert 'return "m"' in body
    assert 'return "s"' in body
    assert 'return "h"' in body


def test_lua_declares_speed_mode_helper() -> None:
    source = _lua_source()

    assert "local function read_speed_mode()" in source


def test_read_speed_mode_reads_selector_channel_and_returns_all_modes() -> None:
    body = _extract_function(_lua_source(), "read_speed_mode")

    assert 'sensor(APP_SPEED_MODE_CHANNEL, 0)' in body
    assert "APP_SPEED_MODE_LOW_THRESHOLD" in body
    assert "APP_SPEED_MODE_HIGH_THRESHOLD" in body
    assert 'return "1", APP_SPEED_MODE_SLOW_SCALE' in body
    assert 'return "2", APP_SPEED_MODE_MEDIUM_SCALE' in body
    assert 'return "3", APP_SPEED_MODE_FAST_SCALE' in body


def test_read_local_status_badges_reads_app_switch_channels() -> None:
    body = _extract_function(_lua_source(), "read_local_status_badges")

    assert 'sensor(APP_ARM_CHANNEL, 0)' in body
    assert 'sensor(APP_BEACON_CHANNEL, 0)' in body
    assert 'sensor(APP_MUTE_CHANNEL, 0)' in body
    assert 'read_drive_mode()' in body
    assert 'read_speed_mode()' in body
    assert 'badges[#badges + 1] = "a"' in body
    assert 'badges[#badges + 1] = "b"' in body
    assert 'badges[#badges + 1] = "m"' in body
    assert 'badges[#badges + 1] = drive_mode' in body
    assert 'badges[#badges + 1] = speed_mode' in body


def test_read_local_status_badges_restores_local_mute_switch_badge() -> None:
    body = _extract_function(_lua_source(), "read_local_status_badges")

    assert 'APP_MUTE_CHANNEL' in body


def test_read_drive_keeps_raw_stick_normalization_for_indicator() -> None:
    body = _extract_function(_lua_source(), "read_drive")

    assert 'local _, speed_scale = read_speed_mode()' not in body
    assert 'local thr_scaled = thr * speed_scale' not in body
    assert 'local str_scaled = str * speed_scale' not in body
    assert 'local thr_n = thr / 1024' in body
    assert 'local str_n = str / 1024' in body
    assert 'local left  = clamp(thr_n + str_n, -1, 1)' in body
    assert 'local right = clamp(thr_n - str_n, -1, 1)' in body


def test_lua_declares_trim_mode_status_bit_constant() -> None:
    source = _lua_source()

    assert "local BATTERY_STATUS_TRIM_MODE" in source


def test_lua_declares_robot_status_badge_helper() -> None:
    source = _lua_source()

    assert "local function read_robot_status_badges()" in source


def test_read_robot_status_badges_reads_trim_mode_flag() -> None:
    body = _extract_function(_lua_source(), "read_robot_status_badges")

    assert 'sensor({ "Capa", "Mah", "mAh" }, 0)' in body
    assert "BATTERY_STATUS_TRIM_MODE" in body
    assert 'badges[#badges + 1] = "t"' in body


def test_lua_declares_charge_lightning_helper() -> None:
    source = _lua_source()

    assert "local function draw_charge_icon(" in source


def test_draw_charge_icon_uses_line_segments() -> None:
    body = _extract_function(_lua_source(), "draw_charge_icon")

    assert "lcd.drawLine(" in body


def test_draw_compact_displays_motor_currents() -> None:
    body = _extract_function(_lua_source(), "draw_compact")

    assert "left_current" in body
    assert "right_current" in body
    assert "format_milliamps" in body


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

    assert "format_milliamps(left_current)" in body
    assert "format_milliamps(right_current)" in body
    assert "format_current_ma(current)" in body


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


def test_lua_declares_vcp_serial_logging_state() -> None:
    source = _lua_source()

    assert "local LOG_SERIAL_BAUD" in source
    assert "local LOG_INTERVAL_CS" in source
    assert "local next_log_at = 0" in source


def test_lua_declares_telemetry_serial_log_helper() -> None:
    source = _lua_source()
    body = _extract_function(source, "log_telemetry")

    assert "serialWrite(" in body
    assert "string.format(" in body


def test_format_cells_for_log_does_not_depend_on_table_library() -> None:
    body = _extract_function(_lua_source(), "format_cells_for_log")

    assert "table.concat" not in body


def test_init_configures_lua_serial_baudrate() -> None:
    body = _extract_function(_lua_source(), "init")

    assert "setSerialBaudrate(" in body


def test_run_emits_vcp_telemetry_logs() -> None:
    body = _extract_function(_lua_source(), "run")

    assert "log_telemetry(" in body
    assert "battery_holdoff_until" in body


def test_log_telemetry_defensively_formats_missing_values() -> None:
    body = _extract_function(_lua_source(), "log_telemetry")

    assert "raw_rqly or 0" in body
    assert "raw_voltage or 0" in body
    assert "raw_current or 0" in body
    assert "raw_pct or 0" in body
    assert "text_or_dash(raw_battery_direction)" in body
    assert "text_or_dash(raw_cell_src)" in body
    assert "format_cells_for_log(raw_cells)" in body
    assert "format_milliamps(raw_left_current)" in body
    assert "format_milliamps(raw_right_current)" in body


def test_run_handles_disconnected_state_before_battery_reads() -> None:
    body = _extract_function(_lua_source(), "run")
    disconnected_branch = body.split("if not connected then", 1)[1].split("local raw_voltage", 1)[0]

    assert "log_telemetry(now, connected, false," in disconnected_branch
    assert "draw_disconnected()" in disconnected_branch
    assert "return 0" in disconnected_branch


def test_run_reads_battery_sensors_only_after_connection_guard() -> None:
    body = _extract_function(_lua_source(), "run")

    assert body.index("if not connected then") < body.index('local raw_voltage = sensor({ "VFAS", "RxBt" }, 0)')


def test_lua_declares_current_format_helper() -> None:
    source = _lua_source()

    assert "local function format_current_ma(" in source


def test_lua_declares_milliamps_format_helper() -> None:
    source = _lua_source()

    assert "local function format_milliamps(" in source


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

    assert "draw_status_badges(" in body
    assert 'hdr = hdr .. " " .. status_icons' not in body


def test_draw_header_wide_appends_status_icons() -> None:
    body = _extract_function(_lua_source(), "draw_header_wide")

    assert "draw_status_badges(" in body
    assert 'hdr = hdr .. " " .. status_icons' not in body


def test_lua_declares_status_badge_draw_helpers() -> None:
    source = _lua_source()

    assert "local function draw_status_badge(" in source
    assert "local function draw_status_badges(" in source


def test_draw_status_badge_uses_rounded_rect_and_lowercase_text() -> None:
    body = _extract_function(_lua_source(), "draw_status_badge")

    assert "draw_rounded_rect(" in body
    assert "lcd.drawText(" in body


def test_draw_status_badge_offsets_speed_mode_digits_down_by_one_pixel() -> None:
    body = _extract_function(_lua_source(), "draw_status_badge")

    assert 'if label == "1" or label == "2" or label == "3" then' in body
    assert 'lcd.drawText(x + 3, y + 1, label, SMLSIZE)' in body
    assert 'lcd.drawText(x + 3, y, label, SMLSIZE)' in body


def test_draw_status_badges_draws_charging_badge_separately() -> None:
    body = _extract_function(_lua_source(), "draw_status_badges")

    assert "draw_charge_icon(" in body
    assert "charging_active" in body


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
    assert "status_badges = read_local_status_badges()" in body
    assert "read_robot_status_badges()" in body
    assert 'charging_active = battery_direction == "CHG"' in body
    assert "draw_wide(voltage, current, battery_direction, pct, rssi, rqly, cell_src, status_badges, charging_active, cells, mn, mx, delta, left_spd, right_spd, cpu, ram, left_current, right_current)" in body
    assert "draw_compact(voltage, current, battery_direction, pct, rssi, rqly, cell_src, status_badges, charging_active, cells, mn, mx, delta, left_spd, right_spd, cpu, ram, left_current, right_current)" in body