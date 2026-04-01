-- BiBa Telemetry Screen
-- Front-view robot with battery state, wheel indicators, connection status

local CELL_COUNT = 6
local LOW_CELL_VOLTAGE = 3.5
local BATTERY_HOLDOFF_CS = 1200
local BATTERY_DIRECTION_MASK = 0x03
local BATTERY_STATUS_TRIM_MODE = 0x20
local LOG_SERIAL_BAUD = 115200
local LOG_INTERVAL_CS = 20
local APP_ARM_CHANNEL = "ch5"
local APP_BEACON_CHANNEL = "ch8"
local APP_MUTE_CHANNEL = "ch7"
local APP_SWITCH_THRESHOLD = 300
local HEADER_BADGE_W = 10
local HEADER_BADGE_H = 8
local HEADER_BADGE_GAP = 2
local RIGHT_WHEEL_CURRENT_ALTITUDE_OFFSET = 1000.0
local RIGHT_WHEEL_CURRENT_ALTITUDE_SCALE = 100.0

-- Sound state tracking
local prev_connected = nil  -- nil = first run, true/false after
local low_bat_sound_at = 0  -- getTime() of last low-bat alert
local battery_holdoff_until = 0
local next_log_at = 0

-- ──────────────────────────────────────────────────
-- Utility helpers
-- ──────────────────────────────────────────────────

local function sw()
  return LCD_W or 128
end

local function sh()
  return LCD_H or 64
end

local function sensor(names, fallback)
  local list = names
  if type(names) ~= "table" then list = { names } end
  for _, n in ipairs(list) do
    local v = getValue(n)
    if type(v) == "number" and v ~= 0 then return v end
  end
  return fallback
end

local function clamp(v, lo, hi)
  if v < lo then return lo end
  if v > hi then return hi end
  return v
end

local function to_ma(current_a)
  return math.floor(((current_a or 0) * 1000) + 0.5)
end

local function format_current_ma(current_a)
  return string.format("%05dmA", to_ma(current_a))
end

local function format_milliamps(current_ma)
  return string.format("%05dmA", math.max(0, math.floor((current_ma or 0) + 0.5)))
end

local function text_or_dash(value)
  if value == nil or value == "" then return "-" end
  return value
end

local function format_cells_for_log(cells)
  if type(cells) ~= "table" or #cells == 0 then return "-" end

  local result = ""
  for i = 1, math.min(#cells, CELL_COUNT) do
    if i > 1 then
      result = result .. "/"
    end
    result = result .. string.format("%.2f", cells[i] or 0)
  end
  return result
end

local function log_telemetry(now, connected, holdoff_active,
  raw_voltage, raw_current, raw_pct, raw_rqly, raw_cell_src, raw_cells, raw_left_current, raw_right_current, raw_battery_direction,
  voltage, current, pct, cell_src, cells, left_current, right_current, battery_direction)
  if now < next_log_at then return end

  next_log_at = now + LOG_INTERVAL_CS
  serialWrite(string.format(
    "T=%d CON=%d HOLD=%d RQ=%d RAWV=%.2f RAWI=%.2f RAWP=%d RAWDIR=%s RAWSRC=%s RAWCELLS=%s RAWL=%s RAWR=%s DSPV=%.2f DSPI=%.2f DSPP=%d DSPDIR=%s DSPSRC=%s DSPCELLS=%s DSPL=%s DSPR=%s\n",
    now,
    connected and 1 or 0,
    holdoff_active and 1 or 0,
    raw_rqly or 0,
    raw_voltage or 0,
    raw_current or 0,
    raw_pct or 0,
    text_or_dash(raw_battery_direction),
    text_or_dash(raw_cell_src),
    format_cells_for_log(raw_cells),
    format_milliamps(raw_left_current),
    format_milliamps(raw_right_current),
    voltage or 0,
    current or 0,
    pct or 0,
    text_or_dash(battery_direction),
    text_or_dash(cell_src),
    format_cells_for_log(cells),
    format_milliamps(left_current),
    format_milliamps(right_current)
  ))
end

-- ──────────────────────────────────────────────────
-- Cell helpers
-- ──────────────────────────────────────────────────

local function cell_list(raw)
  if type(raw) ~= "table" then return {} end
  local src = raw
  if type(raw.values) == "table" then src = raw.values
  elseif type(raw.cells) == "table" then src = raw.cells end
  local c = {}
  for i = 1, CELL_COUNT do
    local v = src[i]
    if type(v) == "number" and v > 0 then c[#c + 1] = v end
  end
  return c
end

local function read_cells(pack_v)
  local c = cell_list(getValue("Cels"))
  if #c > 0 then return c, "BMS" end
  if pack_v and pack_v > 0 then
    local fb = pack_v / CELL_COUNT
    for i = 1, CELL_COUNT do c[i] = fb end
    return c, "PCK"
  end
  return c, ""
end

local function cell_stats(cells)
  if #cells == 0 then return 0, 0, 0 end
  local mn, mx = cells[1], cells[1]
  for i = 2, #cells do
    mn = math.min(mn, cells[i])
    mx = math.max(mx, cells[i])
  end
  return mn, mx, mx - mn
end

-- ──────────────────────────────────────────────────
-- Connection detection
-- ──────────────────────────────────────────────────

local function is_connected()
  local rssi = sensor("RSSI", 0)
  if rssi > 0 then return true end
  local rqly = sensor("RQly", 0)
  return rqly > 0
end

-- ──────────────────────────────────────────────────
-- Wheel direction/speed from RC channels
-- ──────────────────────────────────────────────────

local function read_drive()
  local thr = sensor("ch2", 0)
  local str = sensor("ch4", 0)
  -- ch values are -1024..1024 in EdgeTX
  local thr_n = thr / 1024
  local str_n = str / 1024
  local left  = clamp(thr_n + str_n, -1, 1)
  local right = clamp(thr_n - str_n, -1, 1)
  return left, right
end

-- ──────────────────────────────────────────────────
-- System stats from Pi (sent via GPS frame)
-- GSpd = CPU%, Sats = RAM%
-- ──────────────────────────────────────────────────

local function read_system()
  local cpu_raw = sensor("GSpd", 0)
  local ram = sensor("Sats", 0)
  -- GSpd arrives in km/h (CRSF decodes raw/10), we sent cpu%*10 so it arrives as cpu%
  return math.floor(cpu_raw + 0.5), math.floor(ram)
end

local function read_left_wheel_current_ma()
  return math.max(0, sensor("Hdg", 0) * 100)
end

local function read_right_wheel_current_ma()
  local altitude_current = sensor("Alt", 0)
  return math.max(0, (altitude_current - RIGHT_WHEEL_CURRENT_ALTITUDE_OFFSET) * RIGHT_WHEEL_CURRENT_ALTITUDE_SCALE)
end

local function read_motor_currents()
  local left_current = read_left_wheel_current_ma()
  local right_current = read_right_wheel_current_ma()
  return left_current, right_current
end

local function read_battery_direction()
  local direction_flag = bit32.band(sensor({ "Capa", "Mah", "mAh" }, 0), BATTERY_DIRECTION_MASK)
  if direction_flag == 1 then return "CHG" end
  if direction_flag == 2 then return "DIS" end
  return ""
end

local function read_local_status_badges()
  local badges = {}
  if sensor(APP_ARM_CHANNEL, 0) > APP_SWITCH_THRESHOLD then badges[#badges + 1] = "a" end
  if sensor(APP_MUTE_CHANNEL, 0) > APP_SWITCH_THRESHOLD then badges[#badges + 1] = "m" end
  if sensor(APP_BEACON_CHANNEL, 0) > APP_SWITCH_THRESHOLD then badges[#badges + 1] = "b" end
  return badges
end

local function read_robot_status_badges()
  local badges = {}
  local status_bits = sensor({ "Capa", "Mah", "mAh" }, 0)
  if bit32.band(status_bits, BATTERY_STATUS_TRIM_MODE) ~= 0 then badges[#badges + 1] = "t" end
  return badges
end

-- ──────────────────────────────────────────────────
-- Drawing: disconnected screen
-- ──────────────────────────────────────────────────

local function draw_disconnected()
  local w, h = sw(), sh()
  local cx = math.floor(w / 2)
  local cy = math.floor(h / 2)

  -- BiBa logo centred
  if w >= 212 then
    lcd.drawText(cx - 30, cy - 20, "BiBa", DBLSIZE)
  else
    lcd.drawText(cx - 18, cy - 14, "BiBa", MIDSIZE)
  end

  -- Flashing "НЕТ СВЯЗИ" / "NO LINK"
  if math.floor(getTime() / 50) % 2 == 0 then
    local label = "NO LINK"
    if w >= 212 then
      lcd.drawText(cx - 24, cy + 6, label, MIDSIZE + BLINK)
    else
      lcd.drawText(cx - 20, cy + 4, label, SMLSIZE + BLINK)
    end
  end
end

-- ────────────────────────────────────────────────
-- Drawing: wheel arrow helper
-- ──────────────────────────────────────────────────
local function draw_rounded_rect(x, y, w, h)
  lcd.drawLine(x, y + 2, x, y + h - 3, SOLID, 0)
  lcd.drawLine(x + w - 1, y + 2, x + w - 1, y + h - 3, SOLID, 0)

  lcd.drawLine(x + 2, y, x + w - 3, y, SOLID, 0)
  lcd.drawLine(x + 2, y + h - 1, x + w - 3, y + h - 1, SOLID, 0)

  lcd.drawPoint(x + 1, y + 1)
  lcd.drawPoint(x + w - 2, y + 1)
  lcd.drawPoint(x + 1, y - 2 + h)
  lcd.drawPoint(x + w - 2, y - 2 + h)
end

local function draw_wheel_arrow(x, y, is_flip)

  if is_flip then
    lcd.drawLine(x, y, x + 2, y + 2, SOLID, FORCE)
    lcd.drawLine(x + 3, y + 2, x + 5, y, SOLID, FORCE)
  else
    lcd.drawLine(x, y + 2, x + 2, y, SOLID, FORCE)
    lcd.drawLine(x + 3, y, x + 5, y + 2, SOLID, FORCE)
  end
end

-- ──────────────────────────────────────────────────
-- Drawing: wheel indicator (vertical bar with arrows)
--   x,y = top-left, w/h = size, spd = -1..1
-- ──────────────────────────────────────────────────

local function draw_wheel(x, y, ww, wh, spd, arrow_w)
  arrow_w = arrow_w or 2

  draw_rounded_rect(x, y, ww, wh)

  if math.abs(spd) < 0.05 then return end

  local max_arrows = 7
  local count = math.max(1, math.min(max_arrows, math.floor((math.abs(spd) * max_arrows) + 0.999)))
  local arrow_x = x + 2
  local arrow_step = 4

  for i = 0, count - 1 do
    if spd > 0 then
      local arrow_y = y + wh - 6 - i * arrow_step
      draw_wheel_arrow(arrow_x, arrow_y, false)
    else
      local arrow_y = y + 3 + i * arrow_step
      draw_wheel_arrow(arrow_x, arrow_y, true)
    end
  end
end

-- ──────────────────────────────────────────────────
-- Drawing: SOC bar
-- ──────────────────────────────────────────────────

local function draw_soc_bar(x, y, w, h, pct)
  local fill = math.floor((w - 2) * clamp(pct or 0, 0, 100) / 100)
  lcd.drawRectangle(x, y, w, h)
  if fill > 0 then
    lcd.drawFilledRectangle(x + 1, y + 1, fill, h - 2)
  end
end

local function draw_status_badge(x, y, label)
  lcd.drawText(x + 3, y, label, SMLSIZE)
  draw_rounded_rect(x, y, HEADER_BADGE_W, HEADER_BADGE_H)
  return x + HEADER_BADGE_W + HEADER_BADGE_GAP
end

local function draw_charge_icon(x, y)
  lcd.drawLine(x + 6, y + 1, x + 4, y + 4, SOLID, FORCE)
  lcd.drawLine(x + 4, y + 4, x + 6, y + 4, SOLID, FORCE)
  lcd.drawLine(x + 6, y + 4, x + 3, y + 7, SOLID, FORCE)
end

local function draw_status_badges(x, y, badges, charging_active)
  for _, badge in ipairs(badges) do
    x = draw_status_badge(x, y, badge)
  end
  if charging_active then
    draw_rounded_rect(x, y, HEADER_BADGE_W, HEADER_BADGE_H)
    draw_charge_icon(x, y)
    x = x + HEADER_BADGE_W + HEADER_BADGE_GAP
  end
  return x
end

-- ──────────────────────────────────────────────────
-- Drawing: header row (BiBa + quality + source)
-- ──────────────────────────────────────────────────

local function draw_header(w, rqly, cell_src, status_badges, charging_active)
  lcd.drawText(0, 0, "BiBa", SMLSIZE)
  draw_status_badges(23, 0, status_badges, charging_active)
  local hdr = string.format("Q%03d", rqly)
  if cell_src ~= "" then hdr = hdr .. " " .. cell_src end
  lcd.drawText(w - #hdr * 5, 0, hdr, SMLSIZE)
end

-- ──────────────────────────────────────────────────
-- Drawing: wide header row (BiBa + quality + source)
-- ──────────────────────────────────────────────────

local function draw_header_wide(w, rqly, cell_src, status_badges, charging_active)
  lcd.drawText(4, 2, "BiBa", DBLSIZE)
  draw_status_badges(38, 3, status_badges, charging_active)
  local hdr = string.format("Q%03d", rqly)
  if cell_src ~= "" then hdr = hdr .. " " .. cell_src end
  lcd.drawText(w - #hdr * 6, 4, hdr, SMLSIZE)
end

-- ──────────────────────────────────────────────────
-- Drawing: cell voltage frame (dotted top, solid bottom, dotted dividers)
-- ──────────────────────────────────────────────────

local function draw_cell_frame(w, cells)
  local y_top = 9
  local y_bot = 18
  -- Top border: DOTTED
  lcd.drawLine(2, y_top, w - 3, y_top, DOTTED, FORCE)
  -- Bottom border: SOLID
  lcd.drawLine(2, y_bot, w - 3, y_bot, SOLID, FORCE)
  -- Side borders
  lcd.drawLine(1, y_top, 1, y_bot, DOTTED, FORCE)
  lcd.drawLine(w - 3, y_top, w - 3, y_bot, DOTTED, FORCE)
  -- Cell texts and dotted dividers
  local cell_w = math.floor(w / CELL_COUNT)
  for i = 1, math.min(#cells, CELL_COUNT) do
    local cx = (i - 1) * cell_w
    if i > 1 then
      lcd.drawLine(cx, y_top, cx, y_bot, DOTTED, FORCE)
    end
    lcd.drawText(cx + 3, y_top + 2, string.format("%.2f", cells[i] or 0), SMLSIZE)
  end
end

-- ──────────────────────────────────────────────────
-- Drawing: compact connected (128×64)
-- ──────────────────────────────────────────────────

local function draw_compact(voltage, current, battery_direction, pct, rssi, rqly, cell_src, status_badges, charging_active, cells, mn, mx, delta, left_spd, right_spd, cpu, ram, left_current, right_current)
  local w = sw()

  draw_header(w, rqly, cell_src, status_badges, charging_active)
  draw_cell_frame(w, cells)

  -- Wheels: 10×42, flush to screen edges, top-aligned with body
  local wheel_w = 10
  local wheel_h = 33
  local wheel_y = 31
  draw_wheel(0, wheel_y, wheel_w, wheel_h, left_spd, 3)
  draw_wheel(w - wheel_w, wheel_y, wheel_w, wheel_h, right_spd, 3)

  -- Body rectangle between wheels
  local body_x = 11
  local body_y = 20
  local body_w = 106
  local body_h = 30
  draw_rounded_rect(body_x, body_y, body_w, body_h)

  -- Voltage (large) + CPU/RAM
  lcd.drawText(14, 22, string.format("%.1fV", voltage), MIDSIZE)
  if cpu > 0 or ram > 0 then
    lcd.drawText(49, 22, string.format("CPU%02d%%MEM%02d%%", cpu, ram), SMLSIZE)
  end

  -- Total current + SOC%
  lcd.drawText(14, 34, format_current_ma(current), SMLSIZE)
  lcd.drawText(59, 35, string.format("%d%%", pct), SMLSIZE)

  -- Wheel currents (left / right)
  lcd.drawText(12, 56, format_milliamps(left_current), SMLSIZE)
  lcd.drawText(81, 56, format_milliamps(right_current), SMLSIZE)

  -- SOC bar at bottom of body
  draw_soc_bar(14, 42, 100, 6, pct)

  -- LOW battery warning
  if mn > 0 and mn < LOW_CELL_VOLTAGE and math.floor(getTime() / 50) % 2 == 0 then
    lcd.drawFilledRectangle(w - 28, 0, 28, 8)
    lcd.drawText(w - 26, 0, "LOW", INVERS + SMLSIZE)
  end
end

-- ──────────────────────────────────────────────────
-- Drawing: wide connected (≥212×128)
-- ──────────────────────────────────────────────────

local function draw_wide(voltage, current, battery_direction, pct, rssi, rqly, cell_src, status_badges, charging_active, cells, mn, mx, delta, left_spd, right_spd, cpu, ram, left_current, right_current)
  local w = sw()
  local total_current = format_current_ma(current)

  draw_header_wide(w, rqly, cell_src, status_badges, charging_active)

  local wheel_w  = 18
  local wheel_h  = 76
  local body_w   = w - wheel_w * 2 - 30
  local body_h   = 82
  local body_x   = wheel_w + 15
  local body_y   = 22
  local wheel_y  = body_y + math.floor((body_h - wheel_h) / 2)

  draw_wheel(4, wheel_y, wheel_w, wheel_h, left_spd, 3)
  draw_wheel(w - wheel_w - 4, wheel_y, wheel_w, wheel_h, right_spd, 3)

  draw_rounded_rect(body_x, body_y, body_w, body_h)

  local ix = body_x + 4
  local iy = body_y + 3
  local current_row_y = iy + 31
  local wheel_current_row_y = iy + 42
  local right_current_x = body_x + body_w - 78

  -- Main battery metrics.
  lcd.drawText(ix, iy, string.format("%.2fV", voltage), MIDSIZE)
  lcd.drawText(body_x + body_w - 30, iy + 2, string.format("%d%%", pct), SMLSIZE)
  draw_soc_bar(ix, iy + 18, body_w - 10, 8, pct)

  -- Current + system stats.
  lcd.drawText(ix, current_row_y, total_current, SMLSIZE)
  if cpu > 0 or ram > 0 then
    lcd.drawText(ix + 74, current_row_y, string.format("CPU%02d MEM%02d", cpu, ram), SMLSIZE)
  end

  -- Wheel currents use position instead of L/R text prefixes.
  lcd.drawText(ix, wheel_current_row_y, format_milliamps(left_current), SMLSIZE)
  lcd.drawText(right_current_x, wheel_current_row_y, format_milliamps(right_current), SMLSIZE)

  local cell_y = iy + 55
  local col_w = math.floor((body_w - 12) / 3)
  for i = 1, math.min(#cells, CELL_COUNT) do
    local col = (i - 1) % 3
    local row = math.floor((i - 1) / 3)
    lcd.drawText(ix + col * col_w, cell_y + row * 12,
      string.format("C%d %.2fV", i, cells[i] or 0), SMLSIZE)
  end

  local bottom_y = body_y + body_h + 4
  lcd.drawText(4, bottom_y, string.format("Min %.2fV", mn), SMLSIZE)
  lcd.drawText(math.floor(w / 2) - 18, bottom_y, string.format("Max %.2fV", mx), SMLSIZE)
  lcd.drawText(w - 76, bottom_y, string.format("D %.3fV", delta), SMLSIZE)

  if mn > 0 and mn < LOW_CELL_VOLTAGE and math.floor(getTime() / 50) % 2 == 0 then
    lcd.drawFilledRectangle(w - 48, 0, 48, 14)
    lcd.drawText(w - 44, 2, "LOW!", INVERS + SMLSIZE)
  end

  if math.abs(left_spd) > 0.05 then
    lcd.drawText(4, wheel_y + wheel_h + 2,
      string.format("L%+.0f%%", left_spd * 100), SMLSIZE)
  end
  if math.abs(right_spd) > 0.05 then
    lcd.drawText(w - wheel_w - 4, wheel_y + wheel_h + 2,
      string.format("R%+.0f%%", right_spd * 100), SMLSIZE)
  end
end

-- ──────────────────────────────────────────────────
-- Sound effects (R2-D2 bip-bop via playTone)
-- playTone(freq, duration_ms, pause_ms, flags, freqIncr)
-- ──────────────────────────────────────────────────

local function snd_startup()
  -- "Bi↑ -- Baaa↓" signature jingle
  playTone(800, 100, 50)
  playTone(1600, 200, 30, 0, -3)
end

local function snd_connected()
  -- two happy chirps ↑↑
  playTone(1400, 60, 30)
  playTone(1800, 80, 0)
end

local function snd_disconnected()
  -- sad descending tone
  playTone(1200, 80, 20)
  playTone(600, 200, 0)
end

local function snd_low_battery()
  -- triple alarm beep
  playTone(900, 100, 60)
  playTone(900, 100, 60)
  playTone(900, 100, 0)
end

-- ──────────────────────────────────────────────────
-- Main run
-- ──────────────────────────────────────────────────

local function run(event)
  lcd.clear()

  local connected = is_connected()
  local now = getTime()
  local rqly = sensor("RQly", 0)

  -- Connection state change sounds
  if prev_connected ~= nil then
    if connected and not prev_connected then
      snd_connected()
    elseif not connected and prev_connected then
      snd_disconnected()
    end
  end

  if connected and (prev_connected == nil or not prev_connected) then
    battery_holdoff_until = now + BATTERY_HOLDOFF_CS
  end

  prev_connected = connected

  if not connected then
    log_telemetry(now, connected, false,
      0, 0, 0, rqly, "", {}, 0, 0, "",
      0, 0, 0, "", {}, 0, 0, "")
    draw_disconnected()
    return 0
  end

  local raw_voltage = sensor({ "VFAS", "RxBt" }, 0)
  local raw_current = sensor("Curr", 0)
  local raw_pct = sensor({ "Bat%", "Fuel" }, 0)
  local rssi = sensor("RSSI", 0)
  local raw_cells, raw_cell_src = read_cells(raw_voltage)
  local left_spd, right_spd = read_drive()
  local cpu, ram = read_system()
  local raw_left_current, raw_right_current = read_motor_currents()
  local raw_battery_direction = read_battery_direction()

  local voltage = raw_voltage
  local current = raw_current
  local pct = raw_pct
  local cells = raw_cells
  local cell_src = raw_cell_src
  local left_current = raw_left_current
  local right_current = raw_right_current
  local battery_direction = raw_battery_direction
  local status_badges = read_local_status_badges()
  for _, badge in ipairs(read_robot_status_badges()) do
    status_badges[#status_badges + 1] = badge
  end
  local mn, mx, delta = cell_stats(cells)
  local holdoff_active = false

  if now < battery_holdoff_until then
    holdoff_active = true
    voltage = 0
    current = 0
    battery_direction = ""
    pct = 0
    cells = {}
    left_current = 0
    right_current = 0
    cell_src = ""
    mn = 0
    mx = 0
    delta = 0
  end
  local charging_active = battery_direction == "CHG"

  log_telemetry(now, connected, holdoff_active,
    raw_voltage, raw_current, raw_pct, rqly, raw_cell_src, raw_cells, raw_left_current, raw_right_current, raw_battery_direction,
    voltage, current, pct, cell_src, cells, left_current, right_current, battery_direction)

  if sw() >= 212 and sh() >= 128 then
    draw_wide(voltage, current, battery_direction, pct, rssi, rqly, cell_src, status_badges, charging_active, cells, mn, mx, delta, left_spd, right_spd, cpu, ram, left_current, right_current)
  else
    draw_compact(voltage, current, battery_direction, pct, rssi, rqly, cell_src, status_badges, charging_active, cells, mn, mx, delta, left_spd, right_spd, cpu, ram, left_current, right_current)
  end

  -- Low battery sound (every ~10 seconds)
  if mn > 0 and mn < LOW_CELL_VOLTAGE then
    if now - low_bat_sound_at >= 1000 then  -- 1000 = 10s in centiseconds
      low_bat_sound_at = now
      snd_low_battery()
    end
  end

  return 0
end

local function init()
  setSerialBaudrate(LOG_SERIAL_BAUD)
  serialWrite("BIBA LUA VCP LOG READY\n")
  snd_startup()
  return 0
end

local function background()
end

return {
  init = init,
  run = run,
  background = background,
}