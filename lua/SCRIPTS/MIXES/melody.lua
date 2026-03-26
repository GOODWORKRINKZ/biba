-- BiBa Melody Selector mix script
-- Maps a 6-position switch (or pot) to CH8 for melody selection
--
-- Install: copy to /SCRIPTS/MIXES/ on SD card, then enable in
-- EdgeTX Model Setup → Custom Scripts.
--
-- Configure the switch source below (default: "sc" — switch C).
-- Each position selects one of the 8 melodies from FUN_PLAYLIST.
-- The output is mapped to CH8 via the mix script system.

local SWITCH_SOURCE = "sc"   -- change to your switch/pot name

local input = {
  { "Source", SOURCE },       -- override switch in EdgeTX UI
}

local output = { "Melody" }

local last_value = nil

local function run(source)
  -- source: -1024..+1024 from the configured input
  -- pass through directly; the robot divides into 8 equal zones
  local val = source or getValue(SWITCH_SOURCE)
  last_value = val
  return val
end

return { input = input, output = output, run = run }
