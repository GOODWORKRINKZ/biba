# Phase 06: IS-Signal RPM Proof of Concept — PLAN

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Доказать что пульсации тока через IS-пины BTS7960 + RC-фильтр достаточно для оценки RPM мотора MY1016Z. Снять сырые ADC-данные при разных duty, построить спектры, выбрать алгоритм частотной оценки.

**Architecture:** Отдельный PlatformIO env `rpico_rp2040_is_poc` с USB CDC shell. По команде `CAPTURE <duty_pct> <n_samples>` прошивка устанавливает PWM, ждёт 500 мс, снимает ADC DMA-буфером и дампит отсчёты. Python-скрипт оркестрирует серию захватов, сохраняет CSV, строит FFT-графики и сравнивает алгоритмы RPM.

**Hardware change vs Phase 05:**
```
БЫЛО (Phase 05):               СТАНЕТ (Phase 06):
GP26 = VBAT (3DR PM)           GP26 = IS_LEFT  (1kΩ‖1kΩ + 0.1µF RC)
GP27 = IBAT (3DR PM)           GP27 = IS_RIGHT (1kΩ‖1kΩ + 0.1µF RC)
ADS1115 AIN0-3 = IS_L/R FWD/REV  ADS1115 AIN0 = VBAT, AIN1 = IBAT, AIN2-3 = free
```

**RC filter:** IS_L_FWD + IS_L_REV через 1kΩ каждый → узел → 0.1µF → GND.
R_eff = 500Ω, f_c = 1/(2π×500×0.1e-6) ≈ 3.2 кГц. ШИМ 20кГц: -14 дБ. IS-рябь ~1кГц: -0.4 дБ.

**Tech Stack:** RP2040 Arduino (earlephilhower), RP2040 hardware ADC+DMA, USB CDC, Python 3 + pyserial + numpy + matplotlib + scipy.

---

## Топология ADC после Phase 06

```
BTS7960 L FWD IS ──── 1kΩ ──┐
                              ├── узел ── 0.1µF ── GND   GP26 / ADC0 = IS_LEFT
BTS7960 L REV IS ──── 1kΩ ──┘

BTS7960 R FWD IS ──── 1kΩ ──┐
                              ├── узел ── 0.1µF ── GND   GP27 / ADC1 = IS_RIGHT
BTS7960 R REV IS ──── 1kΩ ──┘

ADS1115 AIN0 ← VBAT (3DR PM voltage out, делитель 10.1×)
ADS1115 AIN1 ← IBAT (3DR PM current out)
```

---

## Wave 1 — Firmware: конфигурация и ADC DMA capture

### Task 1 — Обновить target.h: переназначить GP26/GP27

**Files:**
- Modify: `firmware/targets/RPICO_RP2040/target.h`
- Modify: `firmware/targets/RPICO_RP2040/target_config.h`

**Step 1: Открыть файлы и понять текущее состояние**

Текущее (Phase 05):
```c
#define BIBA_ADC_CHAN_VBAT     0U  /* GP26 */
#define BIBA_ADC_CHAN_IBAT     1U  /* GP27 */
#define BIBA_ADS1115_CHAN_IS_L_FWD  0U  /* AIN0 */
...
```

**Step 2: Заменить ADC-определения в target.h**

```c
/* ADC channels — Phase 06 IS-PoC topology
 *
 *   GP26 (ADC0) = IS_LEFT  — RC-filtered sum of L_FWD + L_REV IS pins
 *   GP27 (ADC1) = IS_RIGHT — RC-filtered sum of R_FWD + R_REV IS pins
 *
 * VBAT and IBAT moved to ADS1115 AIN0/AIN1 (I2C).
 */
#define BIBA_ADC_CHAN_IS_LEFT        0U   /* GP26 */
#define BIBA_ADC_CHAN_IS_RIGHT       1U   /* GP27 */

#define BIBA_ADC_SCAN_LEN           2U
#define BIBA_ADC_CHANNEL_SEQ        { 0, 1 }

/* ADS1115 — VBAT + IBAT (moved from native ADC) */
#define BIBA_ADS1115_CHAN_VBAT       0U   /* AIN0: 3DR PM voltage out */
#define BIBA_ADS1115_CHAN_IBAT       1U   /* AIN1: 3DR PM current out */
/* AIN2, AIN3 — reserved */
```

Удалить старые: `BIBA_ADC_CHAN_VBAT`, `BIBA_ADC_CHAN_IBAT`, `BIBA_ADS1115_CHAN_IS_L_FWD/REV`, `BIBA_ADS1115_CHAN_IS_R_FWD/REV`.

**Step 3: Обновить target_config.h — калибровки IS**

```c
/* IS-pin RC-filtered signal calibration.
 * kILIS = 8500, RIS_each = 1kΩ, two resistors in parallel → R_eff = 500Ω
 * VIS = (IL / kILIS) × R_eff = IL / 17.0 A/V
 * At 50A: VIS = 2.94V — within RP2040 ADC 3.3V max.           */
#define BIBA_IS_AMPS_PER_VOLT       17.0f   /* was 8.5f (single IS path) */
#define BIBA_IS_ZERO_OFFSET_V       0.0f

/* ADS1115 — VBAT (AIN0). Same divider ratio as before.         */
#define BIBA_VBAT_DIVIDER_RATIO     10.1f
/* ADS1115 — IBAT (AIN1). Placeholder — tune from measurement.  */
#define BIBA_IBAT_AMPS_PER_VOLT     18.18f
#define BIBA_IBAT_ZERO_OFFSET_V     0.0f
```

**Step 4: Проверить сборку**

```bash
cd firmware && pio run -e rpico_rp2040_standalone
```
Ожидаем: SUCCESS или ошибки которые нужно исправить (скорее всего — ссылки на `BIBA_ADC_CHAN_VBAT` в voltage_sense.c и biba_hal_rp2040.c).

**Step 5: Исправить voltage_sense.c**

`biba_voltage_sense_vbat_mv()` теперь читает VBAT через ADS1115 AIN0:
```c
#include "drivers/ads1115.h"

uint16_t biba_voltage_sense_vbat_mv(void)
{
#ifdef BIBA_ADS1115_CHAN_VBAT
    float v = 0.0f;
    (void)ads1115_read_channel_v(ADS1115_ADDR, BIBA_ADS1115_CHAN_VBAT, &v);
    float bus_v = v * BIBA_VBAT_DIVIDER_RATIO;
    if (bus_v < 0.0f) bus_v = 0.0f;
    if (bus_v > 30.0f) bus_v = 30.0f;
    return (uint16_t)(bus_v * 1000.0f);
#else
    return 0;
#endif
}
```

Аналогично `biba_voltage_sense_ibat_a()` — заменить `BIBA_ADC_CHAN_IBAT` на `ads1115_read_channel_v(..., BIBA_ADS1115_CHAN_IBAT, ...)`.

**Step 6: Исправить biba_hal_rp2040.c — gpio init**

Было: `adc_gpio_init(26u); adc_gpio_init(27u);` — остаётся (GP26, GP27 всё ещё ADC).

**Step 7: Проверить сборку ещё раз**

```bash
pio run -e rpico_rp2040_standalone
```
Ожидаем: SUCCESS.

**Step 8: Commit**

```bash
git add firmware/targets/RPICO_RP2040/target.h \
        firmware/targets/RPICO_RP2040/target_config.h \
        firmware/src/drivers/voltage_sense.c \
        firmware/src/drivers/voltage_sense.h
git commit -m "feat(06-task1): remap ADC — IS_LEFT/RIGHT to GP26/27, VBAT/IBAT to ADS1115"
```

---

### Task 2 — Новый PlatformIO env `rpico_rp2040_is_poc`

**Files:**
- Modify: `firmware/platformio.ini`

**Step 1: Добавить новый env в конец platformio.ini**

```ini
; --- IS RPM Proof-of-Concept env ----------------------------------------
; Standalone firmware with USB CDC ADC-capture shell for IS-signal
; RPM feasibility study. Excludes normal mode_dispatcher, uses its own
; main entry point: src/poc/is_rpm_poc_main.cpp
; Build: pio run -e rpico_rp2040_is_poc
; Flash: pio run -e rpico_rp2040_is_poc --target upload

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

**Step 2: Создать директорию src/poc/**

```bash
mkdir -p firmware/src/poc
```

**Step 3: Проверить что новый env парсится**

```bash
cd firmware && pio project data --json-output 2>&1 | grep is_poc
```

**Step 4: Commit**

```bash
git add firmware/platformio.ini
git commit -m "feat(06-task2): add rpico_rp2040_is_poc PlatformIO env"
```

---

### Task 3 — ADC DMA capture driver

**Files:**
- Create: `firmware/src/poc/adc_capture.h`
- Create: `firmware/src/poc/adc_capture.c`

**Step 1: Написать заголовок**

```c
/* adc_capture.h — DMA-driven burst ADC capture for IS-signal PoC.
 *
 * Samples both GP26 (IS_LEFT) and GP27 (IS_RIGHT) at a fixed sample
 * rate using RP2040 ADC FIFO + DMA.  The two channels are interleaved
 * in the DMA buffer: buf[0]=IS_L, buf[1]=IS_R, buf[2]=IS_L, ...
 */
#pragma once
#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>

/* Maximum supported samples PER CHANNEL per capture burst. */
#define ADC_CAPTURE_MAX_SAMPLES  4096u

/* Initialise RP2040 ADC+DMA for two-channel interleaved capture.
 * Must be called once before adc_capture_burst().
 * sample_rate_sps: desired rate per channel (e.g. 10000 = 10 kSPS).
 * Actual rate is rounded to the nearest achievable RP2040 ADC rate. */
void adc_capture_init(uint32_t sample_rate_sps);

/* Start a burst capture.
 * channel: 0 = IS_LEFT (GP26), 1 = IS_RIGHT (GP27), 2 = both interleaved.
 * n_samples: number of samples PER CHANNEL (max ADC_CAPTURE_MAX_SAMPLES).
 * out_buf: caller-provided buffer, size >= n_samples * (channel==2 ? 2 : 1).
 * Returns true when DMA complete, false on timeout (>500 ms). */
bool adc_capture_burst(uint8_t channel, uint16_t n_samples,
                       uint16_t *out_buf);
```

**Step 2: Реализовать adc_capture.c**

Ключевые RP2040 API:
```c
#include <hardware/adc.h>
#include <hardware/dma.h>

void adc_capture_init(uint32_t sample_rate_sps) {
    adc_init();
    adc_gpio_init(26);  /* IS_LEFT  → ADC0 */
    adc_gpio_init(27);  /* IS_RIGHT → ADC1 */
    adc_set_round_robin(0b11);   /* alternate ADC0, ADC1 */
    adc_fifo_setup(true, true, 1, false, false);
    /* RP2040 ADC clock = 48 MHz. Conversion takes 96 cycles.
     * sample_rate = 48e6 / (96 * divider)
     * divider = round(48e6 / (96 * sample_rate_sps)) */
    uint32_t div = (48000000u + sample_rate_sps * 48u) / (96u * sample_rate_sps);
    if (div < 1) div = 1;
    adc_set_clkdiv((float)(div - 1));
}

bool adc_capture_burst(uint8_t channel, uint16_t n_samples, uint16_t *out_buf) {
    /* single channel: disable round-robin, select channel */
    /* two channels: enable round-robin 0b11, input_select = 0 */
    int dma_chan = dma_claim_unused_channel(true);
    dma_channel_config cfg = dma_channel_get_default_config(dma_chan);
    channel_config_set_transfer_data_size(&cfg, DMA_SIZE_16);
    channel_config_set_read_increment(&cfg, false);
    channel_config_set_write_increment(&cfg, true);
    channel_config_set_dreq(&cfg, DREQ_ADC);
    dma_channel_configure(dma_chan, &cfg,
        out_buf, &adc_hw->fifo,
        (channel == 2) ? n_samples * 2 : n_samples,
        true);
    adc_run(true);
    /* busy-wait with 500ms timeout */
    uint32_t t0 = to_ms_since_boot(get_absolute_time());
    while (dma_channel_is_busy(dma_chan)) {
        if (to_ms_since_boot(get_absolute_time()) - t0 > 500) {
            adc_run(false); adc_fifo_drain();
            dma_channel_abort(dma_chan);
            dma_channel_unclaim(dma_chan);
            return false;
        }
    }
    adc_run(false); adc_fifo_drain();
    dma_channel_unclaim(dma_chan);
    return true;
}
```

**Step 3: Проверить что компилируется в is_poc env**

```bash
cd firmware && pio run -e rpico_rp2040_is_poc
```
Ожидаем: ошибку "undefined reference to setup/loop" — нормально, main ещё не создан.

**Step 4: Commit**

```bash
git add firmware/src/poc/adc_capture.h firmware/src/poc/adc_capture.c
git commit -m "feat(06-task3): ADC DMA burst capture driver for IS-signal PoC"
```

---

### Task 4 — USB CDC command shell + is_rpm_poc_main.cpp

**Files:**
- Create: `firmware/src/poc/is_rpm_poc_main.cpp`

**Step 1: Создать main с command loop**

Поддерживаемые команды (принимаются по USB Serial):
- `CAPTURE <duty_pct> <n_samples> <sps>` — захват IS_LEFT при заданном duty
- `CAPTURE_BOTH <duty_pct> <n_samples> <sps>` — обоих каналов interleaved
- `STOP` — duty=0, моторы off
- `PING` — ответ `PONG\n` (проверка связи)

Формат вывода для CAPTURE:
```
CAPTURE_START duty=25 channel=0 sps=10000 n=2048
1842,1901,1856,1923,...(2048 чисел через запятую)...
CAPTURE_END
```

```cpp
#include <Arduino.h>
extern "C" {
#include "hal/biba_hal.h"
#include "drivers/bts7960.h"
}
#include "poc/adc_capture.h"

static uint16_t s_buf[ADC_CAPTURE_MAX_SAMPLES * 2];

static void cmd_capture(uint8_t channel, int duty_pct,
                        uint16_t n_samples, uint32_t sps) {
    /* clamp */
    if (duty_pct < 0) duty_pct = 0;
    if (duty_pct > 100) duty_pct = 100;
    if (n_samples > ADC_CAPTURE_MAX_SAMPLES) n_samples = ADC_CAPTURE_MAX_SAMPLES;

    /* set PWM duty (only LEFT motor for single-motor PoC) */
    float duty = duty_pct / 100.0f;
    /* bts7960_set_duty(LEFT, duty) — use existing driver */
    biba_hal_pwm_set_duty(BIBA_PIN_LEFT_RPWM_GPIO, duty > 0 ? duty : 0.0f);
    biba_hal_pwm_set_duty(BIBA_PIN_LEFT_LPWM_GPIO, 0.0f);

    /* wait for motor to spin up */
    delay(500);

    /* capture */
    adc_capture_init(sps);
    bool ok = adc_capture_burst(channel, n_samples, s_buf);

    /* stop motor immediately after capture */
    biba_hal_pwm_set_duty(BIBA_PIN_LEFT_RPWM_GPIO, 0.0f);

    if (!ok) { Serial.println("ERROR capture timeout"); return; }

    /* dump header */
    Serial.printf("CAPTURE_START duty=%d channel=%d sps=%lu n=%u\n",
                  duty_pct, channel, (unsigned long)sps, n_samples);
    uint32_t total = (channel == 2) ? (uint32_t)n_samples * 2 : n_samples;
    for (uint32_t i = 0; i < total; i++) {
        Serial.print(s_buf[i]);
        Serial.print(i + 1 < total ? ',' : '\n');
    }
    Serial.println("CAPTURE_END");
}

void setup() {
    Serial.begin(115200);
    Serial.ignoreFlowControl(true);
    biba_hal_init();
    Serial.println("IS_POC_READY");
}

void loop() {
    if (!Serial.available()) return;
    String line = Serial.readStringUntil('\n');
    line.trim();

    if (line == "PING") {
        Serial.println("PONG");
    } else if (line == "STOP") {
        biba_hal_pwm_set_duty(BIBA_PIN_LEFT_RPWM_GPIO, 0.0f);
        biba_hal_pwm_set_duty(BIBA_PIN_LEFT_LPWM_GPIO, 0.0f);
        Serial.println("OK stopped");
    } else if (line.startsWith("CAPTURE")) {
        /* parse: CAPTURE <duty> <n> <sps>  or  CAPTURE_BOTH <duty> <n> <sps> */
        uint8_t ch = line.startsWith("CAPTURE_BOTH") ? 2 : 0;
        int duty = 0; uint16_t n = 1024; uint32_t sps = 10000;
        sscanf(line.c_str() + (ch == 2 ? 13 : 8), "%d %hu %lu",
               &duty, &n, &sps);
        cmd_capture(ch, duty, n, sps);
    } else {
        Serial.print("ERR unknown: "); Serial.println(line);
    }
}
```

**Step 2: Собрать и проверить**

```bash
cd firmware && pio run -e rpico_rp2040_is_poc
```
Ожидаем: SUCCESS (или ошибки линковки — разобрать по сообщению).

**Step 3: Прошить и проверить PING**

```bash
pio run -e rpico_rp2040_is_poc --target upload
# в другом терминале:
python3 -c "
import serial, time
s = serial.Serial('/dev/ttyACM0', 115200, timeout=2)
time.sleep(1)
s.write(b'PING\n')
print(s.readline())
"
```
Ожидаем: `b'PONG\n'`

**Step 4: Commit**

```bash
git add firmware/src/poc/is_rpm_poc_main.cpp
git commit -m "feat(06-task4): IS PoC USB shell — CAPTURE/STOP/PING commands"
```

---

## Wave 2 — Python: оркестратор захвата и анализ

### Task 5 — Скрипт `scripts/is_poc_capture.py`

**Files:**
- Create: `scripts/is_poc_capture.py`

**Step 1: Написать скрипт**

```python
#!/usr/bin/env python3
"""IS-signal PoC capture orchestrator.

Usage:
    python3 scripts/is_poc_capture.py --port /dev/ttyACM0 --out artifacts/is-capture/
    python3 scripts/is_poc_capture.py --port /dev/ttyACM0 --duty 25 50 75 100
                                      --n 2048 --sps 10000
"""
import argparse
import csv
import os
import time
from pathlib import Path
import serial

DUTY_POINTS_DEFAULT = [25, 50, 75, 100]
N_SAMPLES_DEFAULT = 2048
SPS_DEFAULT = 10000


def wait_for_ready(ser: serial.Serial, timeout: float = 10.0) -> None:
    t0 = time.time()
    while time.time() - t0 < timeout:
        line = ser.readline().decode(errors="replace").strip()
        if line == "IS_POC_READY":
            return
    raise TimeoutError("Firmware did not send IS_POC_READY")


def capture_one(ser: serial.Serial, duty: int, n: int, sps: int,
                channel: int = 0) -> list[int]:
    cmd = f"CAPTURE{'_BOTH' if channel == 2 else ''} {duty} {n} {sps}\n"
    ser.write(cmd.encode())
    # wait for CAPTURE_START
    while True:
        line = ser.readline().decode(errors="replace").strip()
        if line.startswith("CAPTURE_START"):
            break
        if line.startswith("ERROR"):
            raise RuntimeError(line)
    # read data line
    data_line = ser.readline().decode(errors="replace").strip()
    # wait for CAPTURE_END
    while True:
        line = ser.readline().decode(errors="replace").strip()
        if line == "CAPTURE_END":
            break
    return [int(x) for x in data_line.split(",") if x]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default="/dev/ttyACM0")
    ap.add_argument("--out", default="artifacts/is-capture")
    ap.add_argument("--duty", nargs="+", type=int, default=DUTY_POINTS_DEFAULT)
    ap.add_argument("--n", type=int, default=N_SAMPLES_DEFAULT)
    ap.add_argument("--sps", type=int, default=SPS_DEFAULT)
    ap.add_argument("--both", action="store_true",
                    help="capture both channels interleaved")
    args = ap.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    with serial.Serial(args.port, 115200, timeout=10) as ser:
        time.sleep(1.5)  # wait for USB CDC enumerate
        # drain any startup noise
        ser.reset_input_buffer()
        ser.write(b"PING\n")
        pong = ser.readline().decode(errors="replace").strip()
        if pong != "PONG":
            raise RuntimeError(f"Expected PONG, got: {pong!r}")
        print("Connected.")

        for duty in args.duty:
            print(f"  Capturing duty={duty}%  n={args.n}  sps={args.sps}...")
            ch = 2 if args.both else 0
            samples = capture_one(ser, duty, args.n, args.sps, ch)
            fname = out_dir / f"duty_{duty:03d}_sps{args.sps}.csv"
            with open(fname, "w", newline="") as f:
                w = csv.writer(f)
                w.writerow(["sample_index", "adc_raw"])
                for i, v in enumerate(samples):
                    w.writerow([i, v])
            print(f"    Saved {len(samples)} samples → {fname}")

        ser.write(b"STOP\n")
        ser.readline()  # drain OK
    print("Done. Run is_poc_analyse.py to plot spectra.")


if __name__ == "__main__":
    main()
```

**Step 2: Проверить что скрипт запускается без железа (--help)**

```bash
python3 scripts/is_poc_capture.py --help
```
Ожидаем: usage без ошибок.

**Step 3: Commit**

```bash
git add scripts/is_poc_capture.py
git commit -m "feat(06-task5): is_poc_capture.py — USB capture orchestrator"
```

---

### Task 6 — Скрипт `scripts/is_poc_analyse.py`

**Files:**
- Create: `scripts/is_poc_analyse.py`

**Step 1: Написать анализатор**

```python
#!/usr/bin/env python3
"""IS-signal PoC spectrum analyser.

Reads CSV files from is_poc_capture.py, computes FFT per duty point,
overlays spectra on one plot, and reports the dominant frequency for
three algorithms:
  1. FFT peak
  2. Zero-crossing (AC-coupled, adaptive threshold)
  3. Autocorrelation peak

Usage:
    python3 scripts/is_poc_analyse.py --dir artifacts/is-capture/ --sps 10000
    python3 scripts/is_poc_analyse.py --dir artifacts/is-capture/ --sps 10000 \
        --tacho rpm_ground_truth.csv
"""
import argparse
import csv
import math
from pathlib import Path
import numpy as np
import matplotlib.pyplot as plt
from scipy.signal import welch


def load_csv(path: Path) -> np.ndarray:
    rows = []
    with open(path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(int(row["adc_raw"]))
    return np.array(rows, dtype=np.float32)


def freq_fft(samples: np.ndarray, sps: int) -> float:
    """Return dominant frequency (Hz) above 100 Hz using FFT peak."""
    n = len(samples)
    window = np.hanning(n)
    spectrum = np.abs(np.fft.rfft(samples * window))
    freqs = np.fft.rfftfreq(n, d=1.0 / sps)
    # mask below 100 Hz (DC + low-freq noise) and above 5 kHz
    mask = (freqs >= 100) & (freqs <= 5000)
    if not mask.any():
        return 0.0
    idx = np.argmax(spectrum[mask])
    return float(freqs[mask][idx])


def freq_zero_crossing(samples: np.ndarray, sps: int) -> float:
    """Return dominant frequency using zero-crossing of AC-coupled signal."""
    ac = samples - samples.mean()
    threshold = ac.std() * 0.1  # 10% of std as hysteresis band
    crossings = []
    above = ac[0] > threshold
    for i in range(1, len(ac)):
        now_above = ac[i] > threshold
        if not above and now_above:
            crossings.append(i)
        above = now_above
    if len(crossings) < 2:
        return 0.0
    periods = np.diff(crossings)
    avg_period_samples = float(np.median(periods))
    return sps / avg_period_samples if avg_period_samples > 0 else 0.0


def freq_autocorr(samples: np.ndarray, sps: int) -> float:
    """Return dominant frequency using autocorrelation peak."""
    ac = samples - samples.mean()
    corr = np.correlate(ac, ac, mode="full")
    corr = corr[len(corr) // 2:]  # keep positive lags
    # find first minimum, then first peak after it
    min_lag = max(int(sps * 0.0002), 1)  # ignore lags < 0.2ms (> 5kHz)
    max_lag = int(sps * 0.01)            # ignore lags > 10ms  (< 100Hz)
    search = corr[min_lag:max_lag]
    if len(search) < 3:
        return 0.0
    peak_idx = int(np.argmax(search)) + min_lag
    return float(sps / peak_idx) if peak_idx > 0 else 0.0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="artifacts/is-capture")
    ap.add_argument("--sps", type=int, default=10000)
    ap.add_argument("--tacho", default=None,
                    help="CSV with columns duty,rpm_measured (from tachometer)")
    args = ap.parse_args()

    files = sorted(Path(args.dir).glob("duty_*.csv"))
    if not files:
        print(f"No CSV files found in {args.dir}")
        return

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    ax_spec = axes[0]
    ax_algo = axes[1]

    results = []
    for fpath in files:
        duty = int(fpath.stem.split("_")[1])
        samples = load_csv(fpath)
        # ADC raw → millivolts (3300 mV / 4096 counts)
        mv = samples * (3300.0 / 4096.0)

        f_fft = freq_fft(mv, args.sps)
        f_zc = freq_zero_crossing(mv, args.sps)
        f_ac = freq_autocorr(mv, args.sps)

        results.append({"duty": duty, "f_fft": f_fft,
                         "f_zc": f_zc, "f_ac": f_ac})
        print(f"duty={duty:3d}%  FFT={f_fft:7.1f}Hz  ZC={f_zc:7.1f}Hz"
              f"  AC={f_ac:7.1f}Hz")

        # plot Welch PSD
        freqs, psd = welch(mv, fs=args.sps, nperseg=min(256, len(mv)))
        ax_spec.semilogy(freqs, psd, label=f"{duty}%")

    ax_spec.set_xlabel("Frequency (Hz)")
    ax_spec.set_ylabel("PSD (mV²/Hz)")
    ax_spec.set_title("IS-signal spectrum by duty")
    ax_spec.set_xlim(0, args.sps / 2)
    ax_spec.legend()
    ax_spec.axvline(1000, color="gray", linestyle="--", alpha=0.5,
                    label="1kHz reference")

    duties = [r["duty"] for r in results]
    ax_algo.plot(duties, [r["f_fft"] for r in results], "o-", label="FFT peak")
    ax_algo.plot(duties, [r["f_zc"] for r in results], "s-", label="Zero-cross")
    ax_algo.plot(duties, [r["f_ac"] for r in results], "^-", label="Autocorr")

    if args.tacho:
        tacho = {}
        with open(args.tacho) as f:
            for row in csv.DictReader(f):
                tacho[int(row["duty"])] = float(row["rpm_measured"])
        # derive expected IS frequency: f = RPM * k_lam / 60
        # k_lam unknown — show RPM on second y-axis for visual comparison
        ax2 = ax_algo.twinx()
        td = sorted(tacho.keys())
        ax2.plot(td, [tacho[d] for d in td], "D--k", label="Tachometer RPM")
        ax2.set_ylabel("RPM (tachometer)")
        ax2.legend(loc="upper left")

    ax_algo.set_xlabel("Duty (%)")
    ax_algo.set_ylabel("Estimated IS frequency (Hz)")
    ax_algo.set_title("Algorithm comparison")
    ax_algo.legend()

    plt.tight_layout()
    out_png = Path(args.dir) / "is_spectrum_analysis.png"
    plt.savefig(out_png, dpi=150)
    print(f"\nPlot saved → {out_png}")
    plt.show()

    # summary table
    print("\n--- Results summary ---")
    print(f"{'duty':>6}  {'FFT Hz':>10}  {'ZC Hz':>10}  {'AC Hz':>10}")
    for r in results:
        print(f"{r['duty']:>6}  {r['f_fft']:>10.1f}  {r['f_zc']:>10.1f}"
              f"  {r['f_ac']:>10.1f}")


if __name__ == "__main__":
    main()
```

**Step 2: Добавить зависимости в requirements-dev.txt**

Проверить что есть: `numpy`, `matplotlib`, `scipy`, `pyserial`. Добавить отсутствующие.

```bash
grep -E "numpy|matplotlib|scipy|pyserial" requirements-dev.txt
```

**Step 3: Проверить скрипт на синтетических данных**

```bash
python3 - <<'EOF'
import csv, pathlib, numpy as np
p = pathlib.Path("/tmp/test_capture")
p.mkdir(exist_ok=True)
sps = 10000; n = 2048; duty = 50; f_test = 900.0
t = np.arange(n) / sps
signal = 2048 + 300 * np.sin(2 * np.pi * f_test * t) + np.random.randn(n) * 20
with open(p / "duty_050_sps10000.csv", "w") as f:
    w = csv.writer(f)
    w.writerow(["sample_index", "adc_raw"])
    for i, v in enumerate(signal.astype(int)):
        w.writerow([i, v])
EOF
python3 scripts/is_poc_analyse.py --dir /tmp/test_capture --sps 10000
```
Ожидаем: все три алгоритма дают ~900 Гц.

**Step 4: Commit**

```bash
git add scripts/is_poc_analyse.py requirements-dev.txt
git commit -m "feat(06-task6): is_poc_analyse.py — FFT/ZC/autocorr spectrum analyser"
```

---

## Wave 3 — Верификация и артефакты

### Task 7 — Тест синтетических данных для алгоритмов

**Files:**
- Create: `tests/test_is_poc_algorithms.py`

**Step 1: Написать тесты**

```python
"""Unit tests for IS-signal frequency estimation algorithms.

Tests run against synthetic signals (pure sine + noise) so they
don't require hardware.  Each algorithm must recover the injected
frequency within ±5%.
"""
import numpy as np
import pytest
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
from is_poc_analyse import freq_fft, freq_zero_crossing, freq_autocorr

SPS = 10000
N = 2048
NOISE_STD = 30  # ADC counts — ~24 mV at 3.3V/4096 scale


def make_signal(freq_hz: float, amplitude: float = 300.0) -> np.ndarray:
    t = np.arange(N) / SPS
    rng = np.random.default_rng(42)
    return 2048.0 + amplitude * np.sin(2 * np.pi * freq_hz * t) + \
           rng.normal(0, NOISE_STD, N)


@pytest.mark.parametrize("freq", [500, 800, 1000, 1200])
def test_fft_recovers_frequency(freq: int) -> None:
    sig = make_signal(freq)
    estimated = freq_fft(sig, SPS)
    assert abs(estimated - freq) / freq < 0.05, \
        f"FFT: expected ~{freq}Hz, got {estimated:.1f}Hz"


@pytest.mark.parametrize("freq", [500, 800, 1000, 1200])
def test_zero_crossing_recovers_frequency(freq: int) -> None:
    sig = make_signal(freq)
    estimated = freq_zero_crossing(sig, SPS)
    assert abs(estimated - freq) / freq < 0.05, \
        f"ZC: expected ~{freq}Hz, got {estimated:.1f}Hz"


@pytest.mark.parametrize("freq", [500, 800, 1000, 1200])
def test_autocorr_recovers_frequency(freq: int) -> None:
    sig = make_signal(freq)
    estimated = freq_autocorr(sig, SPS)
    assert abs(estimated - freq) / freq < 0.05, \
        f"AC: expected ~{freq}Hz, got {estimated:.1f}Hz"


def test_fft_ignores_dc_component() -> None:
    """Large DC offset must not shift the FFT peak below 100 Hz."""
    sig = make_signal(1000.0)
    sig += 1000.0  # add extra DC
    estimated = freq_fft(sig, SPS)
    assert estimated > 100.0


def test_zero_crossing_returns_zero_on_flat_signal() -> None:
    sig = np.full(N, 2048.0)
    assert freq_zero_crossing(sig, SPS) == 0.0


def test_autocorr_returns_zero_on_flat_signal() -> None:
    sig = np.full(N, 2048.0)
    assert freq_autocorr(sig, SPS) == 0.0
```

**Step 2: Запустить тесты**

```bash
cd /home/ros2/Downloads/biba && python3 -m pytest tests/test_is_poc_algorithms.py -v
```
Ожидаем: 14 passed.

**Step 3: Commit**

```bash
git add tests/test_is_poc_algorithms.py
git commit -m "test(06-task7): unit tests for FFT/ZC/autocorr frequency algorithms"
```

---

### Task 8 — Финальный билд и проверка

**Step 1: Полный тест-прогон**

```bash
cd /home/ros2/Downloads/biba
python3 -m pytest tests/ --ignore=tests/test_imu_factory.py -q
```
Ожидаем: те же 94 pre-existing failures, новые тесты — зелёные.

**Step 2: Билд прошивки (обе env)**

```bash
cd firmware
pio run -e rpico_rp2040_standalone
pio run -e rpico_rp2040_is_poc
```
Ожидаем: оба SUCCESS.

**Step 3: Обновить 06-SUMMARY (после полевых замеров)**

После физического теста: запустить `is_poc_capture.py`, затем `is_poc_analyse.py`, сохранить `is_spectrum_analysis.png` в `artifacts/is-capture/`, добавить вывод алгоритмов в summary.

**Step 4: Финальный commit**

```bash
git add .
git commit -m "feat(06): IS-signal RPM PoC complete — firmware + Python capture + analysis"
```

---

## Критерии успеха фазы

| # | Критерий | Метод проверки |
|---|----------|----------------|
| 1 | Сборка `rpico_rp2040_standalone` не сломана после переназначения ADC | `pio run` → SUCCESS |
| 2 | Сборка `rpico_rp2040_is_poc` проходит | `pio run` → SUCCESS |
| 3 | Алгоритмы дают ±5% на синтетическом сигнале | pytest test_is_poc_algorithms.py |
| 4 | `PING` → `PONG` через USB CDC | ручная проверка с питоном |
| 5 | CAPTURE дампит N чисел в правильном формате | ручная проверка |
| 6 | Спектр при duty=100% показывает пик выше 500 Гц | is_poc_analyse.py |
| 7 | Частота из IS линейно зависит от duty (R² > 0.9) | график алго-сравнения |

---

## Сводная таблица файлов

| Файл | Действие | Задача |
|------|----------|--------|
| `firmware/targets/RPICO_RP2040/target.h` | Modify | Task 1 |
| `firmware/targets/RPICO_RP2040/target_config.h` | Modify | Task 1 |
| `firmware/src/drivers/voltage_sense.c` | Modify | Task 1 |
| `firmware/platformio.ini` | Modify | Task 2 |
| `firmware/src/poc/adc_capture.h` | Create | Task 3 |
| `firmware/src/poc/adc_capture.c` | Create | Task 3 |
| `firmware/src/poc/is_rpm_poc_main.cpp` | Create | Task 4 |
| `scripts/is_poc_capture.py` | Create | Task 5 |
| `scripts/is_poc_analyse.py` | Create | Task 6 |
| `tests/test_is_poc_algorithms.py` | Create | Task 7 |
