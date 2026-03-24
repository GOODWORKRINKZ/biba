local CELL_COUNT = 6
local LOW_CELL_VOLTAGE = 3.5

local function screen_width()
  return LCD_W or 128
end

local function screen_height()
  return LCD_H or 64
end

local function sensor_value(names, fallback)
  local list = names
  if type(names) ~= "table" then
    list = { names }
  end

  for _, name in ipairs(list) do
    local value = getValue(name)
    if type(value) == "number" and value ~= 0 then
      return value
    end
  end

  return fallback
end

local function clamp(value, min_value, max_value)
  if value < min_value then
    return min_value
  end
  if value > max_value then
    return max_value
  end
  return value
end

local function draw_battery_bar(x, y, width, height, percentage)
  local clamped = clamp(percentage or 0, 0, 100)
  local fill_width = math.floor((width - 2) * clamped / 100)
  lcd.drawRectangle(x, y, width, height)
  if fill_width > 0 then
    lcd.drawFilledRectangle(x + 1, y + 1, fill_width, height - 2)
  end
end

local function cell_list_from_sensor(sensor)
  if type(sensor) ~= "table" then
    return {}
  end

  local source = sensor
  if type(sensor.values) == "table" then
    source = sensor.values
  elseif type(sensor.cells) == "table" then
    source = sensor.cells
  end

  local cells = {}
  for index = 1, CELL_COUNT do
    local value = source[index]
    if type(value) == "number" and value > 0 then
      cells[#cells + 1] = value
    end
  end

  return cells
end

local function read_cells(pack_voltage)
  local cells = cell_list_from_sensor(getValue("Cels"))
  if #cells > 0 then
    return cells
  end

  if pack_voltage and pack_voltage > 0 then
    local fallback = pack_voltage / CELL_COUNT
    for index = 1, CELL_COUNT do
      cells[index] = fallback
    end
  end

  return cells
end

local function cell_stats(cells)
  if #cells == 0 then
    return 0, 0, 0
  end

  local min_cell = cells[1]
  local max_cell = cells[1]
  for index = 2, #cells do
    min_cell = math.min(min_cell, cells[index])
    max_cell = math.max(max_cell, cells[index])
  end

  return min_cell, max_cell, max_cell - min_cell
end

local function warning_visible(lowest_cell)
  return lowest_cell > 0 and lowest_cell < LOW_CELL_VOLTAGE and math.floor(getTime() / 50) % 2 == 0
end

local function draw_cells_compact(x, y, width, cells)
  local col_width = math.floor(width / 3)
  for index = 1, CELL_COUNT do
    local col = (index - 1) % 3
    local row = math.floor((index - 1) / 3)
    local cx = x + col * col_width
    local cy = y + row * 8
    lcd.drawText(cx, cy, string.format("C%d %.2f", index, cells[index] or 0), SMLSIZE)
  end
end

local function draw_cells_wide(x, y, cells)
  for row = 0, 2 do
    for col = 0, 1 do
      local index = row * 2 + col + 1
      local cx = x + col * 88
      local cy = y + row * 12
      lcd.drawText(cx, cy, string.format("C%d", index), SMLSIZE)
      lcd.drawText(cx + 18, cy, string.format("%.2fV", cells[index] or 0), SMLSIZE)
    end
  end
end

local function draw_warning_banner(width)
  lcd.drawFilledRectangle(width - 36, 0, 36, 10)
  lcd.drawText(width - 33, 1, "LOW", INVERS + SMLSIZE)
end

local function draw_compact_layout(voltage, current, percentage, rssi, cells, min_cell, max_cell, delta)
  local width = screen_width()
  lcd.drawText(2, 0, "BiBa", MIDSIZE)
  lcd.drawText(width - 34, 2, string.format("R:%d", rssi), SMLSIZE)
  lcd.drawText(2, 12, string.format("%.2fV", voltage), DBLSIZE)
  lcd.drawText(74, 16, string.format("%.1fA", current), SMLSIZE)
  lcd.drawText(74, 26, string.format("SOC %d%%", percentage), SMLSIZE)
  draw_battery_bar(74, 36, 50, 8, percentage)
  draw_cells_compact(2, 32, 68, cells)
  lcd.drawText(2, 50, string.format("min %.2f", min_cell), SMLSIZE)
  lcd.drawText(46, 50, string.format("max %.2f", max_cell), SMLSIZE)
  lcd.drawText(92, 50, string.format("d %.02f", delta), SMLSIZE)
end

local function draw_wide_layout(voltage, current, percentage, rssi, cells, min_cell, max_cell, delta)
  local width = screen_width()
  lcd.drawText(6, 0, "BiBa", DBLSIZE)
  lcd.drawText(width - 54, 4, string.format("RSSI %d", rssi), SMLSIZE)
  lcd.drawText(6, 18, string.format("Pack %.2fV", voltage), MIDSIZE)
  lcd.drawText(6, 34, string.format("Current %.1fA", current), 0)
  lcd.drawText(6, 46, string.format("SOC %d%%", percentage), 0)
  draw_battery_bar(74, 44, width - 82, 10, percentage)
  draw_cells_wide(6, 60, cells)
  lcd.drawText(width - 88, 18, string.format("Min %.2f", min_cell), SMLSIZE)
  lcd.drawText(width - 88, 30, string.format("Max %.2f", max_cell), SMLSIZE)
  lcd.drawText(width - 88, 42, string.format("Delta %.02f", delta), SMLSIZE)
end

local function run(event)
  local voltage = sensor_value({ "VFAS", "RxBt" }, 0)
  local current = sensor_value("Curr", 0)
  local percentage = sensor_value({ "Bat%", "Fuel" }, 0)
  local rssi = sensor_value("RSSI", 0)
  local cells = read_cells(voltage)
  local min_cell, max_cell, delta = cell_stats(cells)
  local width = screen_width()
  local height = screen_height()

  lcd.clear()

  if width >= 212 and height >= 128 then
    draw_wide_layout(voltage, current, percentage, rssi, cells, min_cell, max_cell, delta)
  else
    draw_compact_layout(voltage, current, percentage, rssi, cells, min_cell, max_cell, delta)
  end

  if warning_visible(min_cell) then
    draw_warning_banner(width)
  end

  return 0
end

local function init()
  return 0
end

local function background()
end

return {
  init = init,
  run = run,
  background = background,
}