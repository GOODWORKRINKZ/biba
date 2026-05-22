# Phase 06: IS-Signal RPM Proof of Concept — PLAN

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

---
wave: 1
depends_on: []
files_modified:
  - firmware/targets/RPICO_RP2040/target.h
  - firmware/targets/RPICO_RP2040/target_config.h
  - firmware/src/drivers/voltage_sense.c
  - firmware/platformio.ini
  - firmware/src/poc/adc_capture.h
  - firmware/src/poc/adc_capture.c
  - firmware/src/poc/is_rpm_poc_main.cpp
  - scripts/is_poc_capture.py
  - scripts/is_poc_analyse.py
  - requirements-dev.txt
  - tests/test_is_poc_algorithms.py
autonomous: true
requirements:
  - RPM-POC-01
---

**Goal:** Доказать что пульсации тока через IS-пины BTS7960 + RC-фильтр достаточно для оценки RPM мотора MY1016Z. Снять сырые ADC-данные при разных duty и направлениях, построить спектры, выбрать алгоритм частотной оценки.

**Architecture:** Отдельный PlatformIO env `rpico_rp2040_is_poc` с USB CDC shell. По команде `CAPTURE <FWD|REV> <duty_pct> <n_samples> <sps>` прошивка устанавливает PWM с нужным направлением, ждёт 500 мс, снимает single-channel ADC DMA-буфером и дампит отсчёты. Python-скрипт с `--motor {left|right}` оркестрирует серию из 8 захватов ([25,50,75,100]% × {FWD,REV}), сохраняет CSV с заголовком `duty,dir,sample_idx,adc_raw`, строит FFT-графики и сравнивает три алгоритма RPM (FFT, ZC, autocorr).

**Hardware remapping vs Phase 05:**
```
БЫЛО (Phase 05):               СТАНЕТ (Phase 06):
GP26 = VBAT (3DR PM)           GP26 = IS_LEFT  (1kΩ‖1kΩ + 0.1µF RC)
GP27 = IBAT (3DR PM)           GP27 = IS_RIGHT (1kΩ‖1kΩ + 0.1µF RC)
ADS1115 AIN0-3 = IS_L/R        ADS1115 AIN0 = VBAT, AIN1 = IBAT
```

---

## must_haves

- [ ] `pio run -e rpico_rp2040_standalone` passes (ADC remap + voltage_sense.c fix do not break Phase 05 env)
- [ ] `pio run -e rpico_rp2040_is_poc` passes
- [ ] PING → PONG over USB CDC
- [ ] `CAPTURE FWD 50 2048 10000` → firmware emits CAPTURE_START with `dir=FWD`, 2048 ADC values, CAPTURE_END
- [ ] `scripts/is_poc_capture.py --help` runs; `--motor` arg present
- [ ] 8 CSVs created in `artifacts/is-capture/` with header `duty,dir,sample_idx,adc_raw`
- [ ] `pytest tests/test_is_poc_algorithms.py` passes: all 3 algorithms within ±5% on synthetic signals
- [ ] `is_poc_analyse.py` outputs scatter PNG + R² per direction per algorithm

---

## Wave 1 — Firmware

> Execute Tasks 1–4 sequentially; each task must compile before proceeding to the next.

---

### Task 1 — Переназначить ADC в target.h/target_config.h + исправить voltage_sense.c

**Files:**
- Modify: `firmware/targets/RPICO_RP2040/target.h`
- Modify: `firmware/targets/RPICO_RP2040/target_config.h`
- Modify: `firmware/src/drivers/voltage_sense.c`

<read_first>
- `firmware/targets/RPICO_RP2040/target.h` — текущие `BIBA_ADC_CHAN_*` и `BIBA_ADS1115_CHAN_*` определения; нужно понять что удалить и что добавить
- `firmware/targets/RPICO_RP2040/target_config.h` — калибровочные константы (нужно понять текущие значения перед изменением)
- `firmware/src/drivers/voltage_sense.c` — текущее использование `BIBA_ADC_CHAN_VBAT` и `BIBA_ADC_CHAN_IBAT`; после удаления этих define из target.h файл не скомпилируется без правки (Issue 7)
- `firmware/src/drivers/voltage_sense.h` — сигнатуры функций `biba_voltage_sense_vbat_mv()` и `biba_voltage_sense_ibat_a()`
- `firmware/src/drivers/ads1115.h` — сигнатура `ads1115_read_channel_v(addr, channel, float *out_v)` и константа `ADS1115_ADDR`
</read_first>

<action>
**target.h — ADC channel defines (Phase 06 topology):**

Удалить: `BIBA_ADC_CHAN_VBAT`, `BIBA_ADC_CHAN_IBAT`, `BIBA_ADS1115_CHAN_IS_L_FWD`, `BIBA_ADS1115_CHAN_IS_L_REV`, `BIBA_ADS1115_CHAN_IS_R_FWD`, `BIBA_ADS1115_CHAN_IS_R_REV`.

Добавить:
- `BIBA_ADC_CHAN_IS_LEFT   0U`   — GP26, RC-filtered L_FWD + L_REV IS
- `BIBA_ADC_CHAN_IS_RIGHT  1U`   — GP27, RC-filtered R_FWD + R_REV IS
- `BIBA_ADS1115_CHAN_VBAT  0U`   — AIN0: 3DR PM voltage out
- `BIBA_ADS1115_CHAN_IBAT  1U`   — AIN1: 3DR PM current out

**target_config.h — калибровки:**

Добавить или заменить:
- `BIBA_IS_AMPS_PER_VOLT 17.0f`  — R_eff=500Ω (два 1kΩ параллельно), kILIS=8500: V=IL/8500×500=IL/17
- `BIBA_IS_ZERO_OFFSET_V 0.0f`
- `BIBA_VBAT_DIVIDER_RATIO 10.1f` — оставить как было
- `BIBA_IBAT_AMPS_PER_VOLT 18.18f` — оставить как было
- `BIBA_IBAT_ZERO_OFFSET_V 0.0f` — оставить как было

**voltage_sense.c — Issue 7 fix — заменить direct ADC reads на ADS1115 (без `#ifdef` guard не скомпилируется):**

В `biba_voltage_sense_vbat_mv()`:
- Удалить вызов `biba_hal_adc_sample(BIBA_ADC_CHAN_VBAT)` (define больше не существует)
- Заменить на: `float v = 0.0f; (void)ads1115_read_channel_v(ADS1115_ADDR, BIBA_ADS1115_CHAN_VBAT, &v); float bus_v = v * BIBA_VBAT_DIVIDER_RATIO; if (bus_v < 0.0f) bus_v = 0.0f; if (bus_v > 30.0f) bus_v = 30.0f; return (uint16_t)(bus_v * 1000.0f);`
- Добавить `#include "drivers/ads1115.h"` если отсутствует

В `biba_voltage_sense_ibat_a()`:
- Удалить вызов с `BIBA_ADC_CHAN_IBAT`
- Заменить на: `float v = 0.0f; (void)ads1115_read_channel_v(ADS1115_ADDR, BIBA_ADS1115_CHAN_IBAT, &v); float a = (v - BIBA_IBAT_ZERO_OFFSET_V) * BIBA_IBAT_AMPS_PER_VOLT; return a < 0.0f ? 0.0f : a;`

Проверить сборку: `cd firmware && pio run -e rpico_rp2040_standalone` — ожидаем SUCCESS.
</action>

<acceptance_criteria>
- `grep -r "BIBA_ADC_CHAN_VBAT\|BIBA_ADC_CHAN_IBAT" firmware/` returns 0 matches
- `grep "BIBA_ADC_CHAN_IS_LEFT" firmware/targets/RPICO_RP2040/target.h` → line with `0U`
- `grep "BIBA_ADC_CHAN_IS_RIGHT" firmware/targets/RPICO_RP2040/target.h` → line with `1U`
- `grep "BIBA_ADS1115_CHAN_VBAT" firmware/targets/RPICO_RP2040/target.h` → line with `0U`
- `grep "ads1115_read_channel_v" firmware/src/drivers/voltage_sense.c` → ≥ 2 matches (VBAT + IBAT)
- `grep "BIBA_ADC_CHAN_VBAT\|BIBA_ADC_CHAN_IBAT" firmware/src/drivers/voltage_sense.c` → 0 matches
- `cd firmware && pio run -e rpico_rp2040_standalone` → SUCCESS
</acceptance_criteria>

**Commit:**
`git commit -m "feat(06-task1): remap ADC — IS_LEFT/RIGHT to GP26/27, VBAT/IBAT to ADS1115"`

---

### Task 2 — Новый PlatformIO env `rpico_rp2040_is_poc`

**Files:**
- Modify: `firmware/platformio.ini`

<read_first>
- `firmware/platformio.ini` — текущие env секции и `[target_rpico_rp2040]` конфиг; нужно скопировать board/platform/upload_protocol/debug_tool/build_flags паттерны и проверить имя STM32-specific HAL файлов для фильтра
</read_first>

<action>
Добавить в конец `firmware/platformio.ini`:

```ini
[rp2040_poc_src_filter]
build_src_filter =
    +<*>
    -<hal/biba_hal.c>
    -<hal/biba_hal_motor.c>
    -<hal/biba_hal_debug.c>
    -<main.c>
    -<main_rp2040.cpp>
    -<modes/>
    -<app/>
    +<poc/>

[env:rpico_rp2040_is_poc]
platform = file:///home/ros2/.platformio/platforms/rp2040
framework = arduino
board = ${target_rpico_rp2040.board}
upload_protocol = picotool
debug_tool = cmsis-dap
build_src_filter = ${rp2040_poc_src_filter.build_src_filter}
build_flags =
    -Iinclude
    -Isrc
    -Isrc/proto
    -I${target_rpico_rp2040.target_include}
    ${target_rpico_rp2040.build_flags}
    -DBIBA_IS_POC=1
    -DBIBA_MODE_STANDALONE
```

Затем: `mkdir -p firmware/src/poc`

Проверить: `cd firmware && pio project data --json-output 2>&1 | grep is_poc`

NOTE: `hal/biba_hal_motor.c` исключён (STM32-specific), но `hal/biba_hal_motor_rp2040.c` попадает под `+<*>` — это верно, `biba_hal_motor_pwm_left/right()` определены там.
</action>

<acceptance_criteria>
- `grep "env:rpico_rp2040_is_poc" firmware/platformio.ini` → found
- `grep "DBIBA_IS_POC" firmware/platformio.ini` → found
- `cd firmware && pio project data --json-output 2>&1 | grep -c is_poc` → ≥ 1
- `test -d firmware/src/poc` → exit code 0
</acceptance_criteria>

**Commit:**
`git commit -m "feat(06-task2): add rpico_rp2040_is_poc PlatformIO env"`

---

### Task 3 — ADC DMA burst capture driver (single-channel only, per D-04)

**Files:**
- Create: `firmware/src/poc/adc_capture.h`
- Create: `firmware/src/poc/adc_capture.c`

<read_first>
- `firmware/targets/RPICO_RP2040/target.h` — verify `BIBA_ADC_CHAN_IS_LEFT=0U`, `BIBA_ADC_CHAN_IS_RIGHT=1U` after Task 1
- `firmware/include/` — check existing pico-sdk include patterns to match project style
</read_first>

<action>
**adc_capture.h** — single-channel API only (CAPTURE_BOTH removed per D-04, no channel=2):

```
#pragma once
#include <stdint.h>
#include <stdbool.h>

#define ADC_CAPTURE_MAX_SAMPLES  4096u

/* Initialise RP2040 ADC clock divider for the target sample rate.
 * Must be called before adc_capture_burst().
 * sample_rate_sps: desired rate (e.g. 10000 = 10 kSPS). */
void adc_capture_init(uint32_t sample_rate_sps);

/* DMA burst capture on a single ADC channel.
 * channel: 0 = IS_LEFT (GP26 / BIBA_ADC_CHAN_IS_LEFT)
 *          1 = IS_RIGHT (GP27 / BIBA_ADC_CHAN_IS_RIGHT)
 * n_samples: number of 12-bit samples (max ADC_CAPTURE_MAX_SAMPLES).
 * out_buf: caller buffer, size >= n_samples uint16_t.
 * Returns true on success, false on DMA timeout (> 500 ms). */
bool adc_capture_burst(uint8_t channel, uint16_t n_samples, uint16_t *out_buf);
```

**adc_capture.c** — реализация:

Includes: `<hardware/adc.h>`, `<hardware/dma.h>`, `<pico/time.h>`, `"poc/adc_capture.h"`

`adc_capture_init(uint32_t sps)`:
- `adc_init()`
- `adc_gpio_init(26)` — GP26 = IS_LEFT
- `adc_gpio_init(27)` — GP27 = IS_RIGHT
- DO NOT call `adc_set_round_robin()` — single-channel only, round-robin interferes
- `adc_fifo_setup(true, true, 1, false, false)` — enable, dreq_en=true, shift=true, thresh=1, no ERR
- Clkdiv formula (Pitfall 2: must subtract 1): `float div = (float)48000000u / (96.0f * (float)sps) - 1.0f; if (div < 0.0f) div = 0.0f; adc_set_clkdiv(div);`

`adc_capture_burst(uint8_t channel, uint16_t n_samples, uint16_t *out_buf)`:
- `adc_select_input(channel)` — select channel 0 or 1
- `int dma_ch = dma_claim_unused_channel(true)`
- Build config: `DMA_SIZE_16`, read_increment=false, write_increment=true, dreq=`DREQ_ADC`
- `dma_channel_configure(dma_ch, &cfg, out_buf, &adc_hw->fifo, n_samples, true)`
- `adc_run(true)`
- 500ms timeout loop: `uint32_t t0 = to_ms_since_boot(get_absolute_time()); while (dma_channel_is_busy(dma_ch)) { if (to_ms_since_boot(get_absolute_time()) - t0 > 500) { adc_run(false); adc_fifo_drain(); dma_channel_abort(dma_ch); dma_channel_unclaim(dma_ch); return false; } }`
- `adc_run(false); adc_fifo_drain(); dma_channel_unclaim(dma_ch); return true;`

Partial compile check (expect "undefined reference to setup/loop" only — that is OK, main not yet created):
`cd firmware && pio run -e rpico_rp2040_is_poc 2>&1 | grep -v "setup\|loop" | tail -5`
</action>

<acceptance_criteria>
- `grep "adc_capture_burst" firmware/src/poc/adc_capture.h` → signature with `uint8_t channel` — no mention of channel=2, no "both", no "interleaved"
- `grep "round_robin" firmware/src/poc/adc_capture.c` → 0 matches
- `grep "adc_set_clkdiv" firmware/src/poc/adc_capture.c` → line contains `- 1.0f` or `- 1)`
- `grep "DREQ_ADC" firmware/src/poc/adc_capture.c` → found
- `grep "dma_claim_unused_channel\|dma_channel_configure\|dma_channel_unclaim" firmware/src/poc/adc_capture.c` → 3 matches
- `grep "CAPTURE_BOTH\|channel == 2\|n_samples \* 2" firmware/src/poc/adc_capture.c` → 0 matches
</acceptance_criteria>

**Commit:**
`git commit -m "feat(06-task3): ADC DMA burst capture driver — single-channel, IS_LEFT/RIGHT"`

---

### Task 4 — USB CDC command shell `is_rpm_poc_main.cpp` (CORRECTED)

> **7 corrections applied:** (1) `biba_hal_motor_pwm_left/right()` replaces nonexistent `biba_hal_pwm_set_duty()`; (2) CAPTURE parser: direction first `CAPTURE <FWD|REV> <duty> <n> <sps>`; (3) CAPTURE_BOTH removed entirely; (4) CAPTURE_START header includes `dir=FWD|REV`; (5) SSR + enables armed in setup(); (6) STOP handler disarms SSR + enables; (7) no channel=2 ADC call.

**Files:**
- Create: `firmware/src/poc/is_rpm_poc_main.cpp`

<read_first>
- `firmware/src/hal/biba_hal.h` — exact signatures of `biba_hal_init()`, `biba_hal_ssr_set(bool)`, `biba_hal_left_enable(bool)`, `biba_hal_right_enable(bool)`, `biba_hal_motor_pwm_left(float)`, `biba_hal_motor_pwm_right(float)` — verify names before using
- `firmware/src/poc/adc_capture.h` — `ADC_CAPTURE_MAX_SAMPLES`, `adc_capture_init()`, `adc_capture_burst()` signatures
- `firmware/targets/RPICO_RP2040/target.h` — `BIBA_ADC_CHAN_IS_LEFT`, `BIBA_ADC_CHAN_IS_RIGHT` values
</read_first>

<action>
Create `firmware/src/poc/is_rpm_poc_main.cpp`:

**Includes:**
```
#include <Arduino.h>
#include <math.h>
extern "C" {
#include "hal/biba_hal.h"
}
#include "poc/adc_capture.h"
#include "targets/RPICO_RP2040/target.h"
```

**Static buffer:**
```
static uint16_t s_buf[ADC_CAPTURE_MAX_SAMPLES];
```

**`cmd_capture(float signed_duty, bool is_fwd, uint8_t adc_chan, uint16_t n_samples, uint32_t sps)`:**
- Clamp duty: `if (signed_duty > 1.0f) signed_duty = 1.0f; if (signed_duty < -1.0f) signed_duty = -1.0f;`
- Clamp n: `if (n_samples > ADC_CAPTURE_MAX_SAMPLES) n_samples = ADC_CAPTURE_MAX_SAMPLES;`
- Drive motor — Issue 1 fix — USE CORRECT HAL (biba_hal_pwm_set_duty DOES NOT EXIST):
  - `if (adc_chan == BIBA_ADC_CHAN_IS_LEFT) biba_hal_motor_pwm_left(signed_duty); else biba_hal_motor_pwm_right(signed_duty);`
- `delay(500);`
- `adc_capture_init(sps);`
- `bool ok = adc_capture_burst(adc_chan, n_samples, s_buf);`
- Stop: `if (adc_chan == BIBA_ADC_CHAN_IS_LEFT) biba_hal_motor_pwm_left(0.0f); else biba_hal_motor_pwm_right(0.0f);`
- `if (!ok) { Serial.println("ERROR capture timeout"); return; }`
- Header (Issue 2 — include dir=): `Serial.printf("CAPTURE_START duty=%d dir=%s chan=%d sps=%lu n=%u\n", (int)(fabsf(signed_duty)*100.0f), is_fwd ? "FWD" : "REV", (int)adc_chan, (unsigned long)sps, (unsigned)n_samples);`
- Data: loop `i=0..n_samples-1`: `Serial.print(s_buf[i]); Serial.print(i+1 < n_samples ? ',' : '\n');`
- `Serial.println("CAPTURE_END");`

**`setup()`:**
```
Serial.begin(115200);
Serial.ignoreFlowControl(true);
biba_hal_init();
/* Issue 6 fix: ARM BTS7960 — SSR powers bridge, enables activate REN/LEN.
 * Without these, PWM drives nothing and IS signal is zero. */
biba_hal_ssr_set(true);
biba_hal_left_enable(true);
biba_hal_right_enable(true);
Serial.println("IS_POC_READY");
```

**`loop()` — command parser (Issue 2,3 fix):**
```
if (!Serial.available()) return;
String line = Serial.readStringUntil('\n');
line.trim();

if (line == "PING") {
    Serial.println("PONG");

} else if (line == "STOP") {
    /* Issue 6 fix: disarm on STOP */
    biba_hal_motor_pwm_left(0.0f);
    biba_hal_motor_pwm_right(0.0f);
    biba_hal_left_enable(false);
    biba_hal_right_enable(false);
    biba_hal_ssr_set(false);
    Serial.println("OK stopped");

} else if (line.startsWith("CAPTURE ")) {
    /* Issue 2 fix: "CAPTURE <FWD|REV> <duty_pct> <n_samples> <sps>"
     * Direction token FIRST, then 3 numeric args.
     * Issue 3 fix: No CAPTURE_BOTH branch — removed entirely per D-04. */
    String rest = line.substring(8);        /* after "CAPTURE " */
    bool is_fwd = rest.startsWith("FWD");
    rest = rest.substring(4);               /* skip "FWD " or "REV " */
    int duty_pct = 50; uint16_t n = 2048; uint32_t sps = 10000;
    sscanf(rest.c_str(), "%d %hu %lu", &duty_pct, &n, &sps);
    if (duty_pct < 0) duty_pct = 0;
    if (duty_pct > 100) duty_pct = 100;
    float signed_duty = is_fwd ? (duty_pct / 100.0f) : -(duty_pct / 100.0f);
    /* Motor channel: left motor IS pin (Python --motor left/right selects which
     * unit to run; this firmware always drives the IS_LEFT channel). */
    uint8_t adc_chan = BIBA_ADC_CHAN_IS_LEFT;
    cmd_capture(signed_duty, is_fwd, adc_chan, n, sps);

} else if (line.length() > 0) {
    Serial.print("ERR unknown: "); Serial.println(line);
}
```

Full build: `cd firmware && pio run -e rpico_rp2040_is_poc` → SUCCESS.
Flash + PING check: `python3 -c "import serial,time; s=serial.Serial('/dev/ttyACM0',115200,timeout=2); time.sleep(1); s.write(b'PING\n'); print(s.readline())"` → `b'PONG\n'`
</action>

<acceptance_criteria>
- `grep -c "biba_hal_pwm_set_duty" firmware/src/poc/is_rpm_poc_main.cpp` → `0` (function does not exist; must not appear)
- `grep "biba_hal_motor_pwm_left\|biba_hal_motor_pwm_right" firmware/src/poc/is_rpm_poc_main.cpp` → ≥ 4 matches (FWD/REV drive + 2× stop calls)
- `grep "CAPTURE_BOTH" firmware/src/poc/is_rpm_poc_main.cpp` → 0 matches
- `grep "biba_hal_ssr_set(true)" firmware/src/poc/is_rpm_poc_main.cpp` → found in setup()
- `grep "biba_hal_left_enable(true)\|biba_hal_right_enable(true)" firmware/src/poc/is_rpm_poc_main.cpp` → 2 matches in setup()
- `grep "CAPTURE_START.*dir=" firmware/src/poc/is_rpm_poc_main.cpp` → found (header includes dir=FWD|REV)
- `grep "startsWith.*FWD\|startsWith.*CAPTURE " firmware/src/poc/is_rpm_poc_main.cpp` → direction parsed from line
- `cd firmware && pio run -e rpico_rp2040_is_poc` → SUCCESS
</acceptance_criteria>

**Commit:**
`git commit -m "feat(06-task4): IS PoC USB shell — CAPTURE FWD|REV, biba_hal_motor_pwm, SSR arm"`

---

## Wave 2 — Python

> Start after Task 4 compiles successfully (no hardware required for Python tasks).

---

### Task 5 — Скрипт `scripts/is_poc_capture.py` (CORRECTED)

> **4 corrections vs old plan:** (1) `--motor {left|right}` required arg (D-02); (2) direction sweep FWD+REV × 4 duties = 8 captures (D-09); (3) CSV header `duty,dir,sample_idx,adc_raw` (D-13); (4) multi-readline accumulation until CAPTURE_END (Pitfall 4). No `--both`/CAPTURE_BOTH.

**Files:**
- Create: `scripts/is_poc_capture.py`

<read_first>
- `firmware/src/poc/is_rpm_poc_main.cpp` — exact command format (`CAPTURE FWD 50 2048 10000`) and response format (`CAPTURE_START duty=50 dir=FWD chan=0 sps=10000 n=2048` then data lines then `CAPTURE_END`)
- `biba-controller/requirements.txt` — verify pyserial present (no need to add)
</read_first>

<action>
Create `scripts/is_poc_capture.py`:

**Imports:** `argparse`, `csv`, `time`, `pathlib.Path`, `serial`

**Constants:**
- `DUTY_POINTS_DEFAULT = [25, 50, 75, 100]`
- `DIRECTIONS = ["FWD", "REV"]`  — per D-09
- `N_SAMPLES_DEFAULT = 2048`
- `SPS_DEFAULT = 10000`

**`wait_for_ready(ser, timeout=10.0)`:** read lines until `IS_POC_READY` or TimeoutError.

**`capture_one(ser, duty: int, direction: str, n: int, sps: int) -> list[int]`:**
- `cmd = f"CAPTURE {direction} {duty} {n} {sps}\n"` — direction first per D-01
- `ser.write(cmd.encode())`
- Wait for CAPTURE_START: loop readline; break on `startsWith("CAPTURE_START")`; raise RuntimeError on `startsWith("ERROR")`
- Accumulate data (Issue 4 / Pitfall 4 fix — do NOT assume single readline):
  ```
  raw_tokens = []
  while True:
      line = ser.readline().decode(errors="replace").strip()
      if line == "CAPTURE_END":
          break
      raw_tokens.extend(line.split(","))
  return [int(x) for x in raw_tokens if x.strip().lstrip('-').isdigit()]
  ```

**`main()`:**
- argparse: `--port` (default="/dev/ttyACM0"), `--out` (default="artifacts/is-capture"), `--duty` (nargs="+", type=int, default=DUTY_POINTS_DEFAULT), `--n` (type=int, default=N_SAMPLES_DEFAULT), `--sps` (type=int, default=SPS_DEFAULT), `--motor` (choices=["left","right"], required=True, help="Motor to drive: left uses IS_LEFT (GP26), right uses IS_RIGHT (GP27)")
- `out_dir = Path(args.out); out_dir.mkdir(parents=True, exist_ok=True)`
- `serial.Serial(args.port, 115200, timeout=10)`, sleep 1.5s, PING/PONG check
- Sweep — 8 total captures: `for duty in args.duty: for direction in DIRECTIONS:`
  - `samples = capture_one(ser, duty, direction, args.n, args.sps)`
  - `fname = out_dir / f"duty_{duty:03d}_{direction}_sps{args.sps}.csv"` — filename includes direction
  - CSV write with header `["duty", "dir", "sample_idx", "adc_raw"]` per D-13
  - CSV rows: `[duty, direction, i, v]` for i,v in enumerate(samples)
  - Print progress line
  - `time.sleep(0.5)` — 500ms between captures per D-10
- After sweep: `ser.write(b"STOP\n"); ser.readline()`

Verify without hardware: `python3 scripts/is_poc_capture.py --help` → exit 0, `--motor` visible in usage.
</action>

<acceptance_criteria>
- `python3 scripts/is_poc_capture.py --help` → exit code 0, output contains `--motor` and `{left,right}`
- `grep "CAPTURE_BOTH\|--both" scripts/is_poc_capture.py` → 0 matches
- `grep '"CAPTURE {direction}' scripts/is_poc_capture.py` → found (direction first in command string)
- `grep '"duty", "dir", "sample_idx", "adc_raw"' scripts/is_poc_capture.py` → found (D-13 header)
- `grep "raw_tokens.extend\|raw_tokens +=" scripts/is_poc_capture.py` → found (multi-readline accumulation)
- `grep "CAPTURE_END" scripts/is_poc_capture.py` → found inside accumulation loop
- `grep "for direction in DIRECTIONS\|for direction in \[" scripts/is_poc_capture.py` → found
- `grep "duty_{duty:03d}_{direction}" scripts/is_poc_capture.py` → found (direction in filename)
</acceptance_criteria>

**Commit:**
`git commit -m "feat(06-task5): is_poc_capture.py — --motor, FWD/REV sweep, correct CSV header"`

---

### Task 6 — Скрипт `scripts/is_poc_analyse.py` (CORRECTED)

> **Correction vs old plan:** `load_csv()` reads `adc_raw` column from new `duty,dir,sample_idx,adc_raw` format; R² computed and printed per direction (FWD separate from REV); scatter plot groups by direction.

**Files:**
- Create: `scripts/is_poc_analyse.py`

<read_first>
- `scripts/is_poc_capture.py` — exact CSV format (`duty,dir,sample_idx,adc_raw`) and filename pattern (`duty_050_FWD_sps10000.csv`) to parse correctly
</read_first>

<action>
Create `scripts/is_poc_analyse.py`:

**Imports:** `argparse`, `csv`, `pathlib.Path`, `numpy as np`, `matplotlib.pyplot as plt`, `scipy.signal.welch`

**`load_csv(path: Path) -> tuple[np.ndarray, int, str]`** — returns (samples, duty, direction):
- Open CSV with `csv.DictReader`
- Read `adc_raw` column as float; read `duty` (int) and `dir` (str) from first data row
- Fallback if columns missing: parse filename with regex `duty_(\d+)_(FWD|REV)` via `re`
- Return `(np.array(values, dtype=float), duty, direction)`

**`freq_fft(samples: np.ndarray, sps: int) -> float`:**
- `window = np.hanning(len(samples))`; `spectrum = np.abs(np.fft.rfft(samples * window))`
- `freqs = np.fft.rfftfreq(len(samples), d=1.0/sps)`
- `mask = (freqs >= 100) & (freqs <= 5000)` — skip DC, cap below Nyquist
- Return `float(freqs[mask][np.argmax(spectrum[mask])])` if `mask.any()` else `0.0`

**`freq_zero_crossing(samples: np.ndarray, sps: int) -> float`:**
- `ac = samples - samples.mean()`; `threshold = ac.std() * 0.1`
- Detect rising crossings; if < 2 → return 0.0
- `return float(sps / np.median(np.diff(crossings)))`

**`freq_autocorr(samples: np.ndarray, sps: int) -> float`:**
- `ac = samples - samples.mean()`;  `corr = np.correlate(ac, ac, mode="full")[len(ac)-1:]`
- `min_lag = max(int(sps * 0.0002), 1)`, `max_lag = int(sps * 0.01)`
- `peak_idx = int(np.argmax(corr[min_lag:max_lag])) + min_lag`
- Return `float(sps / peak_idx)` if peak_idx > 0 else `0.0`

**`r_squared(x: list, y: list) -> float`:** `np.polyfit` residuals → `1 - ss_res/ss_tot`; return 0.0 if len < 2.

**`main()`:**
- args: `--dir` (default="artifacts/is-capture"), `--sps` (type=int, default=10000)
- Load all `duty_*.csv`; for each: call load_csv, compute 3 frequencies
- Console output per capture (D-15): `f"duty={duty:3d}%  dir={direction}  FFT={f_fft:7.1f}Hz  ZC={f_zc:7.1f}Hz  AC={f_ac:7.1f}Hz"`
- Compute R² separately for FWD and REV (D-15): filter results by dir, compute r_squared for each of 3 algorithms
- Console: `f"R² FWD — FFT:{r2_fwd_fft:.3f}  ZC:{r2_fwd_zc:.3f}  AC:{r2_fwd_ac:.3f}"` and `f"R² REV — ..."`
- **PNG (D-14):** 2 subplots:
  - Left: Welch PSD per file; legend `duty={d}% {dir}`; xlabel "Frequency (Hz)", ylabel "PSD (mV²/Hz)"
  - Right (scatter): duty vs f_peak; FWD solid markers, REV hollow markers; 3 algorithm lines; R² in legend labels; xlabel "Duty (%)", ylabel "IS frequency (Hz)"
  - `plt.savefig(Path(args.dir) / "is_spectrum_analysis.png", dpi=150)`

Verify without hardware via synthetic test in acceptance_criteria below.
</action>

<acceptance_criteria>
- `python3 scripts/is_poc_analyse.py --help` → exit code 0
- `grep "def freq_fft\|def freq_zero_crossing\|def freq_autocorr" scripts/is_poc_analyse.py` → 3 matches
- `grep "r_squared\|r2_fwd\|r2_rev" scripts/is_poc_analyse.py` → ≥ 2 matches (computed per direction)
- `grep "adc_raw" scripts/is_poc_analyse.py` → found in load_csv (reads correct CSV column)
- `grep "sample_index" scripts/is_poc_analyse.py` → 0 matches (old wrong column name absent)
- Synthetic verify (no hardware): create 2 CSVs at 900Hz → all 3 algorithms return ~900Hz:
  ```bash
  python3 -c "
  import csv, pathlib, numpy as np
  p = pathlib.Path('/tmp/is_test'); p.mkdir(exist_ok=True)
  sps=10000; n=2048; f=900.0
  t=np.arange(n)/sps; sig=(2048+300*np.sin(2*np.pi*f*t)+np.random.default_rng(42).normal(0,30,n)).astype(int)
  for direction in ['FWD','REV']:
      fname = p / f'duty_050_{direction}_sps10000.csv'
      with open(fname,'w') as fh:
          w=csv.writer(fh); w.writerow(['duty','dir','sample_idx','adc_raw'])
          for i,v in enumerate(sig): w.writerow([50,direction,i,v])
  "
  python3 scripts/is_poc_analyse.py --dir /tmp/is_test --sps 10000
  ```
  → Output shows FFT, ZC, AC values all near 900Hz; R² lines printed for FWD and REV
</acceptance_criteria>

**Commit:**
`git commit -m "feat(06-task6): is_poc_analyse.py — FFT/ZC/autocorr, R² per direction, PNG output"`

---

### Task 7 — requirements-dev.txt + unit tests алгоритмов

**Files:**
- Modify: `requirements-dev.txt`
- Create: `tests/test_is_poc_algorithms.py`

<read_first>
- `requirements-dev.txt` — current content: `pytest>=8,<9`, `ruff>=0.11,<1`, `matplotlib>=3.9,<4`, `PyYAML>=6,<7`; numpy and scipy are NOT present → add both
- `scripts/is_poc_analyse.py` — exact signatures `freq_fft(samples, sps)`, `freq_zero_crossing(samples, sps)`, `freq_autocorr(samples, sps)` to test (from Task 6)
</read_first>

<action>
**requirements-dev.txt** — add after `matplotlib>=3.9,<4`:
```
numpy>=1.24
scipy>=1.10
```

**`tests/test_is_poc_algorithms.py`:**

Imports: `numpy as np`, `pytest`, `sys`, `os`; `sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))`; `from is_poc_analyse import freq_fft, freq_zero_crossing, freq_autocorr`

Helper `make_signal(freq_hz: float, sps: int = 10000, n: int = 2048, amplitude: float = 300.0, noise_std: float = 30.0) -> np.ndarray`:
- Fixed seed: `rng = np.random.default_rng(42)`
- `return 2048.0 + amplitude * np.sin(2*np.pi*freq_hz*np.arange(n)/sps) + rng.normal(0, noise_std, n)`

Parametrized tests `@pytest.mark.parametrize("freq", [300, 500, 800, 1000])` (D-12: ±5% criterion):
- `test_fft_recovers_frequency(freq)`: `abs(freq_fft(make_signal(freq), 10000) - freq) / freq < 0.05`
- `test_zero_crossing_recovers_frequency(freq)`: same with `freq_zero_crossing`
- `test_autocorr_recovers_frequency(freq)`: same with `freq_autocorr`

Edge case tests:
- `test_fft_ignores_dc_offset()`: `sig = make_signal(1000.0) + 1000.0` → `freq_fft(sig, 10000) > 100.0`
- `test_zero_crossing_flat_signal()`: `np.full(2048, 2048.0)` → `freq_zero_crossing(sig, 10000) == 0.0`
- `test_autocorr_flat_signal()`: `np.full(2048, 2048.0)` → `freq_autocorr(sig, 10000) == 0.0`

Run: `python3 -m pytest tests/test_is_poc_algorithms.py -v` → 15 passed.
</action>

<acceptance_criteria>
- `grep "numpy>=1.24" requirements-dev.txt` → found
- `grep "scipy>=1.10" requirements-dev.txt` → found
- `grep "pytest.mark.parametrize" tests/test_is_poc_algorithms.py` → ≥ 3 matches (one per algorithm)
- `grep "0.05" tests/test_is_poc_algorithms.py` → found (±5% criterion D-12)
- `grep "300.*500.*800\|parametrize.*freq" tests/test_is_poc_algorithms.py` → test frequencies include [300, 500, 800, 1000]
- `grep "default_rng(42)" tests/test_is_poc_algorithms.py` → found (fixed seed, reproducible)
- `python3 -m pytest tests/test_is_poc_algorithms.py -v` → all 15 PASSED, exit code 0
</acceptance_criteria>

**Commit:**
`git commit -m "test(06-task7): unit tests FFT/ZC/autocorr ±5%, add numpy/scipy to requirements-dev.txt"`

---

## Финальная верификация

### Task 8 — Полный билд + регрессионный тест-прогон

<action>
1. Regression tests: `python3 -m pytest tests/ -q` — new tests green, pre-existing failures unchanged.
2. Both firmware builds: `cd firmware && pio run -e rpico_rp2040_standalone && pio run -e rpico_rp2040_is_poc`
3. Help checks: `python3 scripts/is_poc_capture.py --help` and `python3 scripts/is_poc_analyse.py --help`
</action>

<acceptance_criteria>
- `python3 -m pytest tests/test_is_poc_algorithms.py` → exit code 0, all passed
- `cd firmware && pio run -e rpico_rp2040_standalone` → SUCCESS
- `cd firmware && pio run -e rpico_rp2040_is_poc` → SUCCESS
- Total FAILED count in `pytest tests/ -q` does not increase vs pre-Phase-06 baseline
</acceptance_criteria>

**Commit:**
`git commit -m "feat(06): IS-signal RPM PoC complete — firmware + Python capture/analysis + tests"`

---

## Критерии успеха фазы

| # | ID | Критерий | Метод проверки |
|---|-----|----------|----------------|
| SC-1 | RPM-POC-01 | `rpico_rp2040_standalone` не сломан после ADC remap | `pio run -e rpico_rp2040_standalone` → SUCCESS |
| SC-2 | RPM-POC-01 | Алгоритмы дают ±5% на синтетическом сигнале | `pytest tests/test_is_poc_algorithms.py` → all passed |
| SC-3 | RPM-POC-01 | `CAPTURE FWD 50 2048 10000` → `CAPTURE_START dir=FWD`, 2048 values, `CAPTURE_END` | USB CDC manual check |
| SC-4 | RPM-POC-01 | 8 CSV с header `duty,dir,sample_idx,adc_raw` в `artifacts/is-capture/` | `ls artifacts/is-capture/*.csv | wc -l` ≥ 8; `head -1` проверяет header |
| SC-5 | RPM-POC-01 | R² > 0.9 (duty vs f_peak, per direction) | `is_poc_analyse.py` console output |
| SC-6 | RPM-POC-01 | PNG со спектрами + scatter создан | `test -f artifacts/is-capture/is_spectrum_analysis.png` |

---

## Сводная таблица файлов

| Файл | Действие | Задача | Ключевые исправления |
|------|----------|--------|----------------------|
| `firmware/targets/RPICO_RP2040/target.h` | Modify | Task 1 | ADC remap: IS_LEFT/RIGHT вместо VBAT/IBAT |
| `firmware/targets/RPICO_RP2040/target_config.h` | Modify | Task 1 | IS калибровки, ADS1115 VBAT/IBAT |
| `firmware/src/drivers/voltage_sense.c` | Modify | Task 1 | Issue 7: BIBA_ADC_CHAN_VBAT → ADS1115 |
| `firmware/platformio.ini` | Modify | Task 2 | Env rpico_rp2040_is_poc |
| `firmware/src/poc/adc_capture.h` | Create | Task 3 | Single-channel API (нет channel=2/CAPTURE_BOTH) |
| `firmware/src/poc/adc_capture.c` | Create | Task 3 | Нет round-robin; clkdiv -1.0f корректный |
| `firmware/src/poc/is_rpm_poc_main.cpp` | Create | Task 4 | Issues 1,2,3,6: HAL API, direction parser, no CAPTURE_BOTH, SSR arm |
| `scripts/is_poc_capture.py` | Create | Task 5 | Issues 4,5: --motor, FWD+REV sweep, D-13 CSV header |
| `scripts/is_poc_analyse.py` | Create | Task 6 | R² per direction, load_csv reads adc_raw column |
| `requirements-dev.txt` | Modify | Task 7 | numpy>=1.24, scipy>=1.10 |
| `tests/test_is_poc_algorithms.py` | Create | Task 7 | ±5% criterion D-12, parametrized |
