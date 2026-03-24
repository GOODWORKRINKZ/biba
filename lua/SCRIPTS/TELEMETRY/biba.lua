-- BiBa Telemetry Screen
-- Front-view robot with battery state, wheel indicators, connection status

local CELL_COUNT = 6
local LOW_CELL_VOLTAGE = 3.5

-- Sound state tracking
local prev_connected = nil  -- nil = first run, true/false after
local low_bat_sound_at = 0  -- getTime() of last low-bat alert

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
  if #c > 0 then return c end
  if pack_v and pack_v > 0 then
    local fb = pack_v / CELL_COUNT
    for i = 1, CELL_COUNT do c[i] = fb end
  end
  return c
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
  if rssi == 0 then return false end
  local vfas = sensor({ "VFAS", "RxBt" }, 0)
  return vfas > 0
end

-- ──────────────────────────────────────────────────
-- Wheel direction/speed from RC channels
-- ──────────────────────────────────────────────────

local function read_drive()
  local thr = sensor("ch2", 0)
  local str = sensor("ch1", 0)
  -- ch values are -1024..1024 in EdgeTX
  local thr_n = thr / 1024
  local str_n = str / 1024
  local left  = clamp(thr_n + str_n, -1, 1)
  local right = clamp(thr_n - str_n, -1, 1)
  return left, right
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

-- ──────────────────────────────────────────────────
-- Drawing: wheel indicator (vertical bar with arrows)
--   x,y = top-left, w/h = size, spd = -1..1
-- ──────────────────────────────────────────────────

local function draw_wheel(x, y, ww, wh, spd)
  -- Wheel outline (filled dark rectangle)
  lcd.drawFilledRectangle(x, y, ww, wh)

  if math.abs(spd) < 0.05 then return end

  -- Draw tread marks / motion arrows inside wheel
  local mid_x = x + math.floor(ww / 2)
  local slots = 4
  local slot_h = math.floor(wh / (slots + 1))
  -- Animation phase based on time and speed
  local phase = math.floor(getTime() / math.max(4, math.floor(20 / (math.abs(spd) + 0.01)))) % slots

  for i = 0, slots - 1 do
    local sy = y + 2 + ((i + phase) % slots) * slot_h
    if sy + 2 < y + wh - 1 then
      if spd > 0 then
        -- Forward: upward chevron ↑
        lcd.drawLine(mid_x - 2, sy + 2, mid_x, sy, SOLID, ERASE)
        lcd.drawLine(mid_x, sy, mid_x + 2, sy + 2, SOLID, ERASE)
      else
        -- Reverse: downward chevron ↓
        lcd.drawLine(mid_x - 2, sy, mid_x, sy + 2, SOLID, ERASE)
        lcd.drawLine(mid_x, sy + 2, mid_x + 2, sy, SOLID, ERASE)
      end
    end
  end
end

-- ──────────────────────────────────────────────────
-- Drawing: battery bar
-- ──────────────────────────────────────────────────

local function draw_bat_bar(x, y, w, h, pct)
  local fill = math.floor((w - 2) * clamp(pct or 0, 0, 100) / 100)
  lcd.drawRectangle(x, y, w, h)
  if fill > 0 then
    lcd.drawFilledRectangle(x + 1, y + 1, fill, h - 2)
  end
end

-- ──────────────────────────────────────────────────
-- Drawing: compact connected (128×64)
-- ──────────────────────────────────────────────────

local function draw_compact(voltage, current, pct, rssi, cells, mn, mx, delta, left_spd, right_spd)
  local w = sw()

  -- Header
  lcd.drawText(0, 0, "BiBa", SMLSIZE)
  lcd.drawText(w - 34, 0, string.format("R:%d", rssi), SMLSIZE)

  -- Robot body: front view centred
  -- Layout: [wheel] [  body  ] [wheel]
  local wheel_w = 8
  local wheel_h = 36
  local body_w  = w - wheel_w * 2 - 8
  local body_h  = 30
  local body_x  = wheel_w + 4
  local body_y  = 10
  local wheel_y = body_y + math.floor((body_h - wheel_h) / 2)

  -- Left wheel
  draw_wheel(0, wheel_y, wheel_w, wheel_h, left_spd)
  -- Right wheel
  draw_wheel(w - wheel_w, wheel_y, wheel_w, wheel_h, right_spd)

  -- Body outline
  lcd.drawRectangle(body_x, body_y, body_w, body_h)

  -- Inside body: voltage + SOC bar + current
  local inner_x = body_x + 2
  local inner_y = body_y + 2
  lcd.drawText(inner_x, inner_y, string.format("%.1fV", voltage), MIDSIZE)
  lcd.drawText(inner_x + 52, inner_y + 2, string.format("%d%%", pct), SMLSIZE)

  -- SOC bar inside body
  local bar_w = body_w - 6
  draw_bat_bar(inner_x, inner_y + 14, bar_w, 6, pct)

  lcd.drawText(inner_x, inner_y + 22, string.format("%.1fA", current), SMLSIZE)

  -- Bottom: cells + stats
  local cy = body_y + body_h + 4
  -- Compact cell row
  for i = 1, math.min(#cells, CELL_COUNT) do
    local cx = 1 + (i - 1) * 21
    lcd.drawText(cx, cy, string.format("%.2f", cells[i] or 0), SMLSIZE)
  end

  -- Min/max/delta
  local sy = cy + 8
  if sy + 6 <= sh() then
    lcd.drawText(0, sy, string.format("m%.2f", mn), SMLSIZE)
    lcd.drawText(40, sy, string.format("M%.2f", mx), SMLSIZE)
    lcd.drawText(80, sy, string.format("d%.2f", delta), SMLSIZE)
  end

  -- Low voltage warning
  if mn > 0 and mn < LOW_CELL_VOLTAGE and math.floor(getTime() / 50) % 2 == 0 then
    lcd.drawFilledRectangle(w - 28, 0, 28, 8)
    lcd.drawText(w - 26, 0, "LOW", INVERS + SMLSIZE)
  end
end

-- ──────────────────────────────────────────────────
-- Drawing: wide connected (≥212×128)
-- ──────────────────────────────────────────────────

local function draw_wide(voltage, current, pct, rssi, cells, mn, mx, delta, left_spd, right_spd)
  local w, h = sw(), sh()

  -- Header
  lcd.drawText(4, 2, "BiBa", DBLSIZE)
  lcd.drawText(w - 64, 4, string.format("RSSI %d", rssi), SMLSIZE)

  -- Robot body: front view centred
  local wheel_w  = 18
  local wheel_h  = 70
  local body_w   = w - wheel_w * 2 - 24
  local body_h   = 56
  local body_x   = wheel_w + 12
  local body_y   = 24
  local wheel_y  = body_y + math.floor((body_h - wheel_h) / 2)

  -- Wheels
  draw_wheel(4, wheel_y, wheel_w, wheel_h, left_spd)
  draw_wheel(w - wheel_w - 4, wheel_y, wheel_w, wheel_h, right_spd)

  -- Body
  lcd.drawRectangle(body_x, body_y, body_w, body_h)

  -- Inside body
  local ix = body_x + 4
  local iy = body_y + 3

  lcd.drawText(ix, iy, string.format("%.2fV", voltage), MIDSIZE)
  lcd.drawText(ix + 90, iy + 2, string.format("%d%%", pct), SMLSIZE)
  lcd.drawText(ix + 120, iy + 2, string.format("%.1fA", current), SMLSIZE)

  -- SOC bar
  draw_bat_bar(ix, iy + 18, body_w - 10, 8, pct)

  -- Cells inside body (2 rows × 3 cols)
  local cell_y = iy + 30
  local col_w = math.floor((body_w - 10) / 3)
  for i = 1, math.min(#cells, CELL_COUNT) do
    local col = (i - 1) % 3
    local row = math.floor((i - 1) / 3)
    lcd.drawText(ix + col * col_w, cell_y + row * 12,
      string.format("C%d %.2fV", i, cells[i] or 0), SMLSIZE)
  end

  -- Bottom stats
  local bottom_y = body_y + body_h + 4
  lcd.drawText(4, bottom_y, string.format("Min %.2fV", mn), SMLSIZE)
  lcd.drawText(math.floor(w / 3), bottom_y, string.format("Max %.2fV", mx), SMLSIZE)
  lcd.drawText(math.floor(w * 2 / 3), bottom_y, string.format("Delta %.3fV", delta), SMLSIZE)

  -- Low warning
  if mn > 0 and mn < LOW_CELL_VOLTAGE and math.floor(getTime() / 50) % 2 == 0 then
    lcd.drawFilledRectangle(w - 48, 0, 48, 14)
    lcd.drawText(w - 44, 2, "LOW!", INVERS + SMLSIZE)
  end

  -- Speed labels beside wheels
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

  -- Connection state change sounds
  if prev_connected ~= nil then
    if connected and not prev_connected then
      snd_connected()
    elseif not connected and prev_connected then
      snd_disconnected()
    end
  end
  prev_connected = connected

  if not connected then
    draw_disconnected()
    return 0
  end

  local voltage = sensor({ "VFAS", "RxBt" }, 0)
  local current = sensor("Curr", 0)
  local pct     = sensor({ "Bat%", "Fuel" }, 0)
  local rssi    = sensor("RSSI", 0)
  local cells   = read_cells(voltage)
  local mn, mx, delta = cell_stats(cells)
  local left_spd, right_spd = read_drive()

  if sw() >= 212 and sh() >= 128 then
    draw_wide(voltage, current, pct, rssi, cells, mn, mx, delta, left_spd, right_spd)
  else
    draw_compact(voltage, current, pct, rssi, cells, mn, mx, delta, left_spd, right_spd)
  end

  -- Low battery sound (every ~10 seconds)
  if mn > 0 and mn < LOW_CELL_VOLTAGE then
    local now = getTime()
    if now - low_bat_sound_at >= 1000 then  -- 1000 = 10s in centiseconds
      low_bat_sound_at = now
      snd_low_battery()
    end
  end

  return 0
end

local function init()
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