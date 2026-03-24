local function sensor_value(name, fallback)
  local value = getValue(name)
  if value == nil or value == 0 then
    return fallback
  end
  return value
end

local function draw_battery_bar(x, y, width, height, percentage)
  local clamped = math.max(0, math.min(100, percentage or 0))
  local fill_width = math.floor((width - 2) * clamped / 100)
  lcd.drawRectangle(x, y, width, height)
  lcd.drawFilledRectangle(x + 1, y + 1, fill_width, height - 2)
end

local function draw_cells(x, y, pack_voltage)
  local per_cell = 0
  if pack_voltage and pack_voltage > 0 then
    per_cell = pack_voltage / 6.0
  end

  for row = 0, 2 do
    for col = 0, 1 do
      local index = row * 2 + col + 1
      local cx = x + col * 60
      local cy = y + row * 12
      lcd.drawText(cx, cy, string.format("C%d", index), SMLSIZE)
      lcd.drawText(cx + 18, cy, string.format("%.2fV", per_cell), SMLSIZE)
    end
  end
end

local function run(event)
  local voltage = sensor_value("VFAS", 0)
  local current = sensor_value("Curr", 0)
  local percentage = sensor_value("Bat%", sensor_value("Fuel", 0))

  lcd.clear()
  lcd.drawText(54, 0, "BiBa", DBLSIZE)
  lcd.drawText(2, 18, string.format("Pack %.2fV", voltage), MIDSIZE)
  lcd.drawText(2, 34, string.format("Current %.1fA", current), 0)
  lcd.drawText(2, 46, string.format("SOC %d%%", percentage), 0)
  draw_battery_bar(2, 58, 120, 8, percentage)
  draw_cells(2, 72, voltage)

  if voltage > 0 and (voltage / 6.0) < 3.5 then
    lcd.drawFilledRectangle(110, 0, 18, 10)
    lcd.drawText(112, 1, "!", INVERS)
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