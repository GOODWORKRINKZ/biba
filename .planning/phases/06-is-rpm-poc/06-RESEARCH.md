# Phase 06: IS-Signal RPM Proof-of-Concept — Research

**Researched:** 2026-05-22
**Domain:** RP2040 ADC/DMA embedded capture + Python FFT/signal analysis
**Confidence:** HIGH (all claims verified against actual source files)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Команда захвата: `CAPTURE <FWD|REV> <duty_pct> <n_samples> <sps>`. Направление (FWD/REV) — обязательный параметр.
- **D-02:** Выбор мотора (LEFT/RIGHT) — **константа в Python-скрипте** (`--motor {left|right}`), не параметр прошивки.
- **D-03:** `STOP` и `PING` → `PONG` остаются.
- **D-04:** `CAPTURE_BOTH` — **убрать из scope**.
- **D-05:** Мотор — коллекторный редукторный DC. Формула: `f_ripple = N_seg × RPM_core / 60`.
- **D-06:** Передаточное число — уточнить по даташиту ДО запуска. Примерно ~33:1.
- **D-07:** Даташит в `artifacts/datasheets/` — **НЕ найден** (см. Open Questions).
- **D-08:** 10 kSPS, 2048 отсчётов/канал, Nyquist = 5 kHz.
- **D-09:** Python sweep: `[25, 50, 75, 100]% × {FWD, REV}` = 8 захватов.
- **D-10:** Задержка 500 мс между захватами (spin-up/down).
- **D-11:** Критерий R² > 0.9 между duty и пик-частотой.
- **D-12:** Синтетический тест: ±5%.
- **D-13:** CSV header: `duty,dir,sample_idx,adc_raw`. Хранить в `artifacts/is-capture/`.
- **D-14:** PNG: спектр + scatter `duty vs f_peak` (три линии FFT/ZC/autocorr) с R².
- **D-15:** Console output: duty, dir, f_peak, R². Только Python-скрипт, не Jupyter.

### Agent's Discretion
- Порядок волн (firmware → python) остаётся как в `06-PLAN.md`.
- Unit-тесты алгоритмов — агент пишет по своему усмотрению, покрывая критерий ±5%.
- Структура Python-скрипта — по усмотрению агента, лишь бы `--port` и `--motor {left|right}` были аргументами.

### Deferred Ideas (OUT OF SCOPE)
- CAPTURE_BOTH (оба мотора)
- Real-time RPM на RP2040 (Phase 7+)
- Абсолютная калибровка RPM
- SNR и computational cost алгоритмов
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| RPM-POC-01 | IS-сигнал через RC-фильтр пригоден для оценки RPM (R² > 0.9) | ADC DMA capture verified; FFT/ZC/autocorr patterns documented; CSV/PNG output specified |
</phase_requirements>

---

## Summary

Phase 6 builds an isolated PlatformIO environment (`rpico_rp2040_is_poc`) that repurposes RP2040 native ADC GP26/GP27 from VBAT/IBAT (Phase 5 role) to IS_LEFT/IS_RIGHT (RC-filtered commutator ripple). A USB CDC command shell receives `CAPTURE <FWD|REV> <duty> <n> <sps>` and DMA-dumps raw ADC data. A Python script orchestrates 8 captures ([25,50,75,100]% × {FWD,REV}), saves per-capture CSVs, and runs three frequency estimators (FFT peak, zero-crossing, autocorrelation). PoC succeeds when R² > 0.9 on field captures and all three estimators recover injected frequency within ±5% on synthetic data.

**Primary recommendation:** Execute the existing 06-PLAN.md but with targeted corrections to Task 4 (CAPTURE command signature, correct PWM API, SSR/enable handling, CAPTURE_BOTH removal) and Task 5 (add `--motor`/direction sweep, fix CSV header). All other plan content is valid and well-structured.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| ADC DMA burst capture | RP2040 firmware (embedded C) | — | Hardware-only; DMA is a peripheral on RP2040 |
| Motor PWM control (FWD/REV) | RP2040 firmware (embedded C) | — | Existing HAL owns PWM slices |
| USB CDC data transport | RP2040 firmware (Arduino serial) | — | arduino-pico routes printf/Serial to CDC automatically |
| Capture orchestration (sweeps) | Python host script | — | pyserial + argparse; hardware-agnostic |
| Frequency estimation (FFT/ZC/autocorr) | Python host script | — | numpy/scipy; no embedded constraint |
| CSV/PNG output | Python host script | — | Standard file I/O |
| Synthetic unit tests | Python pytest | — | Pure math, no hardware |

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| earlephilhower arduino-pico | local install | RP2040 Arduino framework | Project already uses it [VERIFIED: platformio.ini] |
| `hardware/adc.h` + `hardware/dma.h` | pico-sdk (bundled) | ADC FIFO + DMA capture | Native RP2040 SDK; zero overhead [VERIFIED: target.h includes] |
| pyserial | ≥3.5 (project uses) | USB CDC serial from Python | In biba-controller/requirements.txt [VERIFIED] |
| numpy | 2.2.6 installed | FFT, array math | Standard scientific Python [VERIFIED: `import numpy` OK] |
| scipy | 1.15.3 installed | `welch()` PSD | Standard; already imported in plan [VERIFIED] |
| matplotlib | 3.10.7 installed | PNG output | In requirements-dev.txt [VERIFIED] |
| pytest | ≥8,<9 | Unit tests | In requirements-dev.txt [VERIFIED] |

### Missing from requirements-dev.txt
| Library | Status | Action |
|---------|--------|--------|
| numpy | Installed on machine but **NOT in requirements-dev.txt** | Add `numpy>=1.24` |
| scipy | Installed on machine but **NOT in requirements-dev.txt** | Add `scipy>=1.10` |

**Installation:**
```bash
# Already installed; add to requirements-dev.txt for reproducibility:
echo "numpy>=1.24" >> requirements-dev.txt
echo "scipy>=1.10" >> requirements-dev.txt
```

---

## Architecture Patterns

### System Architecture Diagram

```
[Python host: is_poc_capture.py]
    --motor left/right (constant)
    --port /dev/ttyACM0
         │
         │  USB CDC (pyserial)
         │  "CAPTURE FWD 50 2048 10000\n"
         ▼
[RP2040: is_rpm_poc_main.cpp]
    setup()
      └─ biba_hal_init()   ← inits PWM, ADC GPIO, I2C, SSR
      └─ biba_hal_ssr_set(true)   ← powers BTS7960
      └─ biba_hal_left_enable(true) / right_enable(true)
      └─ Serial.println("IS_POC_READY")

    loop() parser:
      PING → "PONG"
      STOP → biba_hal_motor_pwm_left/right(0.0f)
      CAPTURE FWD 50 2048 10000
          └─ biba_hal_motor_pwm_left(+0.50f)   ← FWD
          └─ delay(500ms)
          └─ adc_capture_init(10000)
          └─ adc_capture_burst(IS_LEFT_CHAN, 2048, buf)
          └─ biba_hal_motor_pwm_left(0.0f)
          └─ "CAPTURE_START duty=50 dir=FWD ...\n"
          └─ "1842,1901,...\n"
          └─ "CAPTURE_END\n"
         │
         │  USB CDC (raw ADC values)
         ▼
[Python: parse CAPTURE_START/data/END]
    write artifacts/is-capture/duty_050_FWD_sps10000.csv
    (header: duty,dir,sample_idx,adc_raw)
         │
         ▼
[Python: is_poc_analyse.py]
    for each CSV:
      freq_fft()  freq_zero_crossing()  freq_autocorr()
      → R² fit: duty vs f_peak
    → PNG: spectra overlay + scatter duty vs f_peak
```

### Recommended Project Structure
```
firmware/src/poc/
├── adc_capture.h        # DMA burst capture API
├── adc_capture.c        # RP2040 ADC+DMA implementation
└── is_rpm_poc_main.cpp  # Arduino setup()/loop() entry point

scripts/
├── is_poc_capture.py    # capture orchestrator (new)
└── is_poc_analyse.py    # FFT/ZC/autocorr analyser (new)

tests/
└── test_is_poc_algorithms.py  # synthetic unit tests (new)

artifacts/is-capture/
├── duty_025_FWD_sps10000.csv   # raw ADC
├── duty_025_REV_sps10000.csv
├── ...
└── is_spectrum_analysis.png
```

### Pattern 1: RP2040 ADC Round-Robin DMA Capture

For single-channel capture (one IS pin per CAPTURE command):
```c
// Source: pico-sdk hardware/adc.h
void adc_capture_init(uint32_t sample_rate_sps) {
    adc_init();
    adc_gpio_init(26);  // GP26 = IS_LEFT  = ADC0
    adc_gpio_init(27);  // GP27 = IS_RIGHT = ADC1
    adc_fifo_setup(true, true, 1, false, false);
    // RP2040 ADC clock = 48 MHz, 96 cycles/conversion
    // divider = round(48e6 / (96 * sps)) - 1
    float div = (float)48000000u / (96.0f * (float)sample_rate_sps) - 1.0f;
    if (div < 0.0f) div = 0.0f;
    adc_set_clkdiv(div);
}

bool adc_capture_burst(uint8_t channel, uint16_t n_samples, uint16_t *buf) {
    adc_select_input(channel);  // 0=IS_LEFT, 1=IS_RIGHT
    int dma_ch = dma_claim_unused_channel(true);
    dma_channel_config cfg = dma_channel_get_default_config(dma_ch);
    channel_config_set_transfer_data_size(&cfg, DMA_SIZE_16);
    channel_config_set_read_increment(&cfg, false);
    channel_config_set_write_increment(&cfg, true);
    channel_config_set_dreq(&cfg, DREQ_ADC);
    dma_channel_configure(dma_ch, &cfg, buf, &adc_hw->fifo, n_samples, true);
    adc_run(true);
    uint32_t t0 = to_ms_since_boot(get_absolute_time());
    while (dma_channel_is_busy(dma_ch)) {
        if (to_ms_since_boot(get_absolute_time()) - t0 > 500) {
            adc_run(false); adc_fifo_drain();
            dma_channel_abort(dma_ch); dma_channel_unclaim(dma_ch);
            return false;
        }
    }
    adc_run(false); adc_fifo_drain();
    dma_channel_unclaim(dma_ch);
    return true;
}
```
**Note:** RP2040 ADC max rate is 500 kSPS (single channel). At 10 kSPS/channel the `adc_set_clkdiv` divider is 48e6/(96×10000) - 1 = 49.0. DMA_SIZE_16 is correct for 12-bit ADC samples.

### Pattern 2: Motor FWD/REV via existing HAL

**Correct API** (verified in `firmware/src/hal/biba_hal.h` and `biba_hal_motor_rp2040.c`):
```cpp
// FWD: positive duty → RPWM active
biba_hal_motor_pwm_left(+0.50f);   // 50% forward

// REV: negative duty → LPWM active
biba_hal_motor_pwm_left(-0.50f);   // 50% reverse

// Stop:
biba_hal_motor_pwm_left(0.0f);

// Enable required before driving:
biba_hal_left_enable(true);    // GP4 (REN) + GP5 (LEN) HIGH
biba_hal_ssr_set(true);        // GP16 SSR → BTS7960 powered
```
Higher-level wrapper (uses direction constant from `biba_config.h`):
```cpp
biba_bts7960_drive(+0.50f, 0.0f);  // left FWD at 50%, right stopped
```

### Pattern 3: CAPTURE command parser with direction

```cpp
// In loop():
if (line.startsWith("CAPTURE")) {
    // Protocol: "CAPTURE FWD 50 2048 10000"
    // Parse direction token after "CAPTURE "
    String rest = line.substring(8);  // after "CAPTURE "
    bool is_fwd = rest.startsWith("FWD");
    rest = rest.substring(is_fwd ? 4 : 4);  // skip "FWD " or "REV "
    int duty = 0; uint16_t n = 2048; uint32_t sps = 10000;
    sscanf(rest.c_str(), "%d %hu %lu", &duty, &n, &sps);
    float signed_duty = is_fwd ? (duty / 100.0f) : -(duty / 100.0f);
    cmd_capture(signed_duty, is_fwd, n, sps);
}
```

### Pattern 4: Python frequency estimation (FFT peak)

```python
# Source: numpy.fft — standard scipy-stack usage
def freq_fft(samples: np.ndarray, sps: int) -> float:
    n = len(samples)
    window = np.hanning(n)
    spectrum = np.abs(np.fft.rfft(samples * window))
    freqs = np.fft.rfftfreq(n, d=1.0 / sps)
    mask = (freqs >= 100) & (freqs <= 5000)  # skip DC, cap at Nyquist
    if not mask.any(): return 0.0
    return float(freqs[mask][np.argmax(spectrum[mask])])
```

### Anti-Patterns to Avoid

- **Using `biba_hal_pwm_set_duty()`** — this function does NOT exist in the HAL. Use `biba_hal_motor_pwm_left(float duty)` where duty is [-1, +1] and sign determines direction.
- **CAPTURE_BOTH** — removed per D-04; do not include in protocol or parser.
- **Calling `adc_capture_init()` without first calling `adc_gpio_init(26)` / `adc_gpio_init(27)`** — must initialize the GPIO analog input mode before the DMA run.
- **Not calling `biba_hal_ssr_set(true)` and `biba_hal_left_enable(true)` before driving** — BTS7960 is powered off at boot (SSR LOW, enables LOW). The PoC shell must arm both.
- **Unconditional `BIBA_ADC_CHAN_VBAT` in voltage_sense.c** — `biba_voltage_sense_vbat_mv()` references `BIBA_ADC_CHAN_VBAT` without `#ifdef` guard; when that define is removed from target.h, this will fail to compile the standalone env.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| ADC DMA setup | Custom DMA descriptor logic | `hardware/dma.h` pico-sdk API | Already battle-tested; DMA_SIZE_16 + DREQ_ADC is the canonical pattern |
| FFT | Custom FFT | `numpy.fft.rfft` | Cooley-Tukey is 500 lines; window functions, DC removal, bin precision all handled |
| PSD estimate | Custom power spectrum | `scipy.signal.welch` | Welch averages reduce variance; better for noisy IS signals |
| R² calculation | Hand loop | `numpy` polyfit residuals or `scipy.stats.pearsonr` | One-liner; handles edge cases |
| Serial readline with timeout | Custom buffer loop | `pyserial` `readline()` with `timeout=` param | Handles partial lines, USB CDC glitches |

---

## Issues Found in Existing 06-PLAN.md

**These are required corrections, not suggestions:**

### Issue 1 — Wrong PWM API in Task 4 `cmd_capture()`

**Plan has:** `biba_hal_pwm_set_duty(BIBA_PIN_LEFT_RPWM_GPIO, duty > 0 ? duty : 0.0f)`
**Problem:** `biba_hal_pwm_set_duty()` does **not exist** anywhere in the firmware. [VERIFIED: grep found zero matches]
**Fix:** Use `biba_hal_motor_pwm_left(float duty)` where:
- FWD at X%: `biba_hal_motor_pwm_left(+X/100.0f)`
- REV at X%: `biba_hal_motor_pwm_left(-X/100.0f)`
- Stop: `biba_hal_motor_pwm_left(0.0f)`

### Issue 2 — CAPTURE command signature in Task 4

**Plan has parser:** `CAPTURE <duty> <n> <sps>` (3 args, no direction)
**Required per D-01:** `CAPTURE <FWD|REV> <duty> <n> <sps>` (4 args, direction first)
**Fix:** Parser in `loop()` must extract direction token before the 3 numeric args.
**Also fix:** `CAPTURE_START` response header should include `dir=FWD|REV`.

### Issue 3 — CAPTURE_BOTH still present in Task 4

**Plan has:** `CAPTURE_BOTH` command with `ch = line.startsWith("CAPTURE_BOTH") ? 2 : 0`
**Required per D-04:** Remove entirely.
**Fix:** Delete `CAPTURE_BOTH` from parser and `cmd_capture()` signature.

### Issue 4 — Missing `--motor` argument and direction sweep in Task 5

**Plan has:** `scripts/is_poc_capture.py` with `--duty` list, no `--motor`, no direction.
**Required per D-02, D-09:**
- `--motor {left|right}` CLI arg that selects which motor to drive (and which IS channel to read)
- Sweep `[25, 50, 75, 100]% × {FWD, REV}` = 8 captures
- Command sent to firmware: `CAPTURE FWD 25 2048 10000`, then `CAPTURE REV 25 2048 10000`, etc.
**Fix:** Add `--motor` arg; change `capture_one()` to accept `direction` param; add direction loop.

### Issue 5 — CSV header wrong in Task 5

**Plan has:** `["sample_index", "adc_raw"]`
**Required per D-13:** `["duty", "dir", "sample_idx", "adc_raw"]`
**Fix:** Update `csv.writer.writerow` call in capture script; row data includes duty and dir.

### Issue 6 — Missing SSR arm and motor enable in Task 4

**Plan has:** No SSR arm, no enable call before driving.
**Problem:** At boot, `biba_hal_init()` sets SSR LOW and all enables LOW (BTS7960 powered off). Driving PWM into disabled BTS7960 produces no current, no IS signal.
**Fix:** In `setup()`, after `biba_hal_init()`, add:
```cpp
biba_hal_ssr_set(true);          // power BTS7960 via SSR (GP16)
biba_hal_left_enable(true);      // GP4+GP5 HIGH
biba_hal_right_enable(true);     // GP8+GP9 HIGH
```
Also add corresponding `biba_hal_ssr_set(false)` + enables low in `STOP` handler.

### Issue 7 — voltage_sense.c will fail standalone build after ADC remap

**Plan Task 1 Step 5** describes fixing `voltage_sense.c` — this is correct and necessary.
The `biba_voltage_sense_vbat_mv()` function references `BIBA_ADC_CHAN_VBAT` without `#ifdef` guard. After removing that define from target.h, the standalone env will fail to compile.
**Required fix (in plan):** Replace `biba_hal_adc_sample(BIBA_ADC_CHAN_VBAT)` with `ads1115_read_channel_v(ADS1115_ADDR, BIBA_ADS1115_CHAN_VBAT, &v)`.

---

## Common Pitfalls

### Pitfall 1: RP2040 ADC FIFO overrun

**What goes wrong:** ADC runs faster than DMA drains FIFO → overrun flag set → stale samples.
**Why it happens:** `adc_fifo_setup()` flags: `dreq_en=true` (DREQ to DMA) needed; `err_in_fifo=false`.
**How to avoid:** Use `adc_fifo_setup(true, true, 1, false, false)` — `dreq_en=true`, `shift=true` (12-bit shifted to 8 MSBs), `thresh=1`.
**Warning signs:** Captured signal looks like noise at any frequency.

### Pitfall 2: adc_set_clkdiv off-by-one

**What goes wrong:** Actual sample rate is wrong → frequency estimates scale-shifted.
**Why it happens:** `adc_set_clkdiv(div)` takes the fractional clock divider value where `actual_rate = 48MHz / (96 * (div+1))`. Passing `div=N` sets divisor to N+1.
**How to avoid:** `float div = 48e6f / (96.0f * sps) - 1.0f;` — subtract 1 before passing.
**Warning signs:** FFT peak at expected frequency × constant offset ratio.

### Pitfall 3: IS signal absent at low duty

**What goes wrong:** IS ripple undetectable below ~20% duty.
**Why it happens:** At low speeds, commutator ripple amplitude may be below noise floor of RC-filtered IS path.
**How to avoid:** Expected per D-07 in CONTEXT.md — this is not a bug. Report 0 Hz for non-detectable captures.
**Warning signs:** FFT peak near 0 at 25% duty — compare with R² computed only over the detectable range.

### Pitfall 4: Python serial readline timeout during data dump

**What goes wrong:** `capture_one()` hangs waiting for `CAPTURE_END` when 2048 comma-separated values overflow the USB CDC TX buffer.
**Why it happens:** RP2040 USB CDC has limited TX FIFO; `Serial.print()` in a tight loop can block or split output across multiple readline calls.
**How to avoid:** Read data as multiple readline calls, accumulating until `CAPTURE_END` is found. Do not assume all 2048 values arrive in a single line.
**Warning signs:** `ser.readline()` returns partial lines with `\r\n` mid-stream.

### Pitfall 5: voltage_sense.c fails to compile standalone after target.h remap

**What goes wrong:** `rpico_rp2040_standalone` build breaks with `BIBA_ADC_CHAN_VBAT` undeclared.
**Why it happens:** `biba_voltage_sense_vbat_mv()` uses this define without `#ifdef`. Once Phase 6 removes it from target.h, the compile fails.
**How to avoid:** Fix `voltage_sense.c` in Task 1 (as planned) before committing the target.h change.
**Warning signs:** Build error `'BIBA_ADC_CHAN_VBAT' undeclared` in voltage_sense.c.

### Pitfall 6: `hal/biba_hal_motor_rp2040.c` is excluded by rp2040_poc_src_filter

**What goes wrong:** `biba_hal_motor_pwm_left()` unresolved at link time in is_poc env.
**Why it happens:** `[rp2040_poc_src_filter]` in the plan includes `-<hal/biba_hal_motor.c>` which is the STM32 file, but the RP2040 version is `hal/biba_hal_motor_rp2040.c` which needs to be **included**.
**How to avoid:** The plan's filter correctly uses `+<*>` then subtracts only STM32-specific files. Verify: `biba_hal_motor_rp2040.c` matches `+<*>` and is NOT in the exclusion list.
**Warning signs:** Linker error `undefined reference to biba_hal_motor_pwm_left`.

---

## Code Examples

### RP2040: Full cmd_capture() with corrected API

```cpp
// Source: derived from firmware/src/hal/biba_hal_motor_rp2040.c patterns
static void cmd_capture(float signed_duty, bool is_fwd,
                        uint8_t adc_chan,  /* 0=IS_LEFT, 1=IS_RIGHT */
                        uint16_t n_samples, uint32_t sps) {
    float duty_abs = signed_duty < 0 ? -signed_duty : signed_duty;
    if (duty_abs > 1.0f) duty_abs = 1.0f;
    if (n_samples > ADC_CAPTURE_MAX_SAMPLES) n_samples = ADC_CAPTURE_MAX_SAMPLES;

    /* Drive selected motor */
    if (adc_chan == 0) {
        biba_hal_motor_pwm_left(signed_duty);
    } else {
        biba_hal_motor_pwm_right(signed_duty);
    }
    delay(500);  /* spin-up */

    adc_capture_init(sps);
    bool ok = adc_capture_burst(adc_chan, n_samples, s_buf);

    /* Stop immediately after capture */
    if (adc_chan == 0) biba_hal_motor_pwm_left(0.0f);
    else               biba_hal_motor_pwm_right(0.0f);

    if (!ok) { Serial.println("ERROR capture timeout"); return; }

    Serial.printf("CAPTURE_START duty=%d dir=%s chan=%d sps=%lu n=%u\n",
                  (int)(duty_abs * 100), is_fwd ? "FWD" : "REV",
                  adc_chan, (unsigned long)sps, n_samples);
    for (uint16_t i = 0; i < n_samples; i++) {
        Serial.print(s_buf[i]);
        Serial.print(i + 1 < n_samples ? ',' : '\n');
    }
    Serial.println("CAPTURE_END");
}
```

### Python: Correct CAPTURE command send + multi-line data read

```python
def capture_one(ser, duty: int, direction: str, n: int, sps: int,
                channel: int) -> list[int]:
    """direction: 'FWD' or 'REV'"""
    cmd = f"CAPTURE {direction} {duty} {n} {sps}\n"
    ser.write(cmd.encode())
    # wait for CAPTURE_START
    while True:
        line = ser.readline().decode(errors="replace").strip()
        if line.startswith("CAPTURE_START"):
            break
        if line.startswith("ERROR"):
            raise RuntimeError(line)
    # accumulate data lines until CAPTURE_END
    raw_tokens = []
    while True:
        line = ser.readline().decode(errors="replace").strip()
        if line == "CAPTURE_END":
            break
        raw_tokens.extend(line.split(","))
    return [int(x) for x in raw_tokens if x.strip().lstrip('-').isdigit()]
```

### Python: CSV write with D-13 header

```python
with open(fname, "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["duty", "dir", "sample_idx", "adc_raw"])
    for i, v in enumerate(samples):
        w.writerow([duty, direction, i, v])
```

### Python: R² calculation

```python
import numpy as np

def r_squared(x: list[float], y: list[float]) -> float:
    """Linear R² between x (duty) and y (f_peak Hz)."""
    if len(x) < 2: return 0.0
    xv, yv = np.array(x, dtype=float), np.array(y, dtype=float)
    coeffs = np.polyfit(xv, yv, 1)
    y_pred = np.polyval(coeffs, xv)
    ss_res = np.sum((yv - y_pred) ** 2)
    ss_tot = np.sum((yv - yv.mean()) ** 2)
    return float(1.0 - ss_res / ss_tot) if ss_tot > 0 else 0.0
```

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| PlatformIO + rp2040 platform | firmware build | ✓ | local install at `/home/ros2/.platformio/platforms/rp2040` [VERIFIED: platformio.ini] | — |
| picotool (upload) | firmware flash | ✓ (assumed) | — | cmsis-dap |
| Python 3 | scripts | ✓ | system | — |
| numpy | Python analysis | ✓ | 2.2.6 [VERIFIED] | — |
| scipy | Welch PSD | ✓ | 1.15.3 [VERIFIED] | — |
| matplotlib | PNG output | ✓ | 3.10.7 [VERIFIED] | — |
| pyserial | USB CDC | ✓ | installed [VERIFIED: `import serial` OK] | — |
| MY1016Z datasheet | N_seg, gear ratio | ✗ | not in `artifacts/datasheets/` | Use assumed values (see Open Questions) |

**Missing dependencies with no fallback:** MY1016Z datasheet (data-only, not a build blocker; PoC can run without it, but absolute RPM correlation requires it).

---

## Open Questions

### 1. MY1016Z: N_seg (commutator segments) and gear ratio

**What we know:** Motor is 24V brushed DC, 75 RPM output shaft. Gear ratio ~33:1 assumed (CONTEXT.md D-06). At 33:1: RPM_core at 100% duty ≈ 2475, f_ripple ≈ N_seg × 2475 / 60.
**What's unclear:** N_seg is unknown. Typical brushed DC motors have 7–15 segments. At N_seg=9: f_ripple ≈ 371 Hz. At N_seg=12: f_ripple ≈ 495 Hz. Both well within 5 kHz Nyquist.
**Impact on PoC:** Unknown N_seg doesn't block capture or R² test. It only blocks absolute RPM conversion. R² criterion (duty vs f_peak) works without knowing N_seg.
**Recommendation:** Proceed. Note expected f_ripple range (200–800 Hz at normal duty). If MY1016Z datasheet is located, add a comment in the analysis script.
**[ASSUMED]** Gear ratio ~33:1 and N_seg ~9–12, giving f_ripple 200–600 Hz at 25–100% duty.

### 2. PlatformIO `+<poc/>` filter with missing directory

**What we know:** `firmware/src/poc/` does not exist. [VERIFIED: ls shows directory absent]
**What's unclear:** Does PlatformIO fail or silently succeed with `+<poc/>` pointing to non-existent directory?
**Recommendation:** Task 2 must create `firmware/src/poc/` with a placeholder (or Task 3 creates files there) **before** running `pio project data` validation. Otherwise the build may fail with a confusing error.

### 3. RC filter frequency response at 20 kHz PWM

**What we know:** RC filter: R_eff = 500 Ω, C = 0.1 µF → f_c = 3.2 kHz. PWM carrier 20 kHz: attenuation -14 dB. IS ripple ~200-600 Hz: -0.4 dB pass-through.
**What's unclear:** Whether PWM switching noise alias folds into the IS ripple band after RC.
**Recommendation:** In analysis, mask frequencies above 2 kHz to exclude residual PWM artifacts. The PoC will show empirically whether the masking is sufficient.

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | MY1016Z gear ratio ~33:1 | Motor Characteristics | Expected f_ripple range off → sweep may miss signal at low duty. Low risk: range still < Nyquist. |
| A2 | N_seg ~9–12 → f_ripple 200–600 Hz | Motor Characteristics | Wrong f_ripple band → analysis masks wrong range. Can adjust in script. |
| A3 | picotool is available for firmware upload | Environment | Flash step blocked. Fallback: cmsis-dap. |

---

## State of the Art / Phase 5 → Phase 6 Transition

| Phase 5 (current firmware state) | Phase 6 (after remap) |
|-----------------------------------|----------------------|
| GP26 = VBAT (3DR PM voltage) | GP26 = IS_LEFT (RC-filtered) |
| GP27 = IBAT (3DR PM current) | GP27 = IS_RIGHT (RC-filtered) |
| ADS1115 AIN0-3 = IS_L_FWD/REV, IS_R_FWD/REV | ADS1115 AIN0 = VBAT, AIN1 = IBAT |
| voltage_sense.c reads GP26/GP27 via native ADC | voltage_sense.c reads ADS1115 AIN0/AIN1 |
| No PoC env | `rpico_rp2040_is_poc` env added |

**Compatibility constraint:** `rpico_rp2040_standalone` must still build after the remap (Success Criteria 4). The ADC remapping is shared — both envs use the same `target.h`. The `voltage_sense.c` fix must work for both.

---

## Sources

### Primary (HIGH confidence — verified against actual source files)
- `firmware/targets/RPICO_RP2040/target.h` — current ADC defines (BIBA_ADC_CHAN_VBAT/IBAT verified)
- `firmware/targets/RPICO_RP2040/target_config.h` — calibration constants (BIBA_IS_AMPS_PER_VOLT=8.5f)
- `firmware/src/hal/biba_hal.h` — motor PWM API: `biba_hal_motor_pwm_left/right(float duty)`
- `firmware/src/hal/biba_hal_motor_rp2040.c` — PWM implementation, ±duty → RPWM/LPWM
- `firmware/src/hal/biba_hal_rp2040.c` — `adc_gpio_init(26)` / `adc_gpio_init(27)`, SSR/enable init
- `firmware/src/drivers/voltage_sense.c` — unconditional BIBA_ADC_CHAN_VBAT usage confirmed
- `firmware/src/drivers/bts7960.c` — `biba_bts7960_drive()` wraps `biba_hal_motor_pwm_left/right()`
- `firmware/platformio.ini` — `[rp2040_src_filter]` structure, rpico_rp2040_standalone env definition
- `requirements-dev.txt` — numpy/scipy absent, matplotlib present
- `biba-controller/requirements.txt` — pyserial present
- `artifacts/datasheets/` — MY1016Z datasheet absent (only BTS7960 + ADS1115)
- Python environment — numpy 2.2.6, scipy 1.15.3, matplotlib 3.10.7 verified

### Secondary (MEDIUM confidence)
- `.planning/phases/06-is-rpm-poc/06-PLAN.md` — existing plan reviewed; issues documented
- `.planning/phases/05-current-sensing-adc/05-CONTEXT.md` — Phase 5 ADC topology decisions
- `scripts/vcp_capture.py` — pyserial usage patterns for capture scripts

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all verified against installed packages and source files
- Architecture (PWM/ADC/DMA): HIGH — verified against actual HAL source
- Plan issues: HIGH — verified by grepping for non-existent functions, checking actual function signatures
- Motor physics (N_seg/gear ratio): LOW — MY1016Z datasheet absent; estimates from CONTEXT.md D-06
- Python analysis algorithms: HIGH — standard numpy/scipy patterns

**Research date:** 2026-05-22
**Valid until:** 2026-06-22 (stable stack; firmware topology locked by Phase 5 decisions)
