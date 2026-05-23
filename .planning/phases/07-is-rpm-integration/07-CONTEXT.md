# Phase 07 Context — IS-RPM Integration into Main Firmware

**Created:** 2026-05-23  
**Phase:** 07 — Перенос A2 Sub-window ZC-детектора и FF+PI контура в основную прошивку  
**Source:** discuss-phase session (interactive)  
**Status:** context captured, ready for research + planning

---

## Phase Goal

Перенести A2 Sub-window Schmitt ZC-детектор и FF+PI контур RPM из PoC
(`firmware/src/poc/is_rpm_poc_main.cpp`, env `rpico_rp2040_is_poc`) в основную
прошивку (`firmware/src/`, env `rpico_rp2040_standalone`).

Результат: оба мотора управляются по замкнутому контуру скорости на RP2040,
wheel_rpm_hz уходит в biba_proto телеметрию, Pi Python пересчитывает в m/s.

---

## Architecture Decisions

### 1. Где замыкается контур — RP2040 firmware

**Решение:** PI+FF loop живёт целиком в firmware на RP2040, не в biba-controller Python.

**Обоснование:**
- DMA-буфер 1024@10kSPS = 100 мс период — ZC обновляется в ISR, без SPI round-trip latency
- Низкоуровневый доступ к `biba_hal_motor_pwm_left/right(float [-1,1])` прямой, без USB CDC
- Pi Python только получает wheel_rpm_hz из proto телеметрии (наблюдение, не управление)

### 2. Интеграция с biba_ramp_t — PI заменяет рамп

**Решение:** PI+FF заменяет `biba_ramp_t` в firmware.

**Контекст:**
- `biba_ramp_t` (`firmware/src/app/ramp.h`) использовался из `mode_standalone.c`
- Плавность разгона/торможения теперь обеспечивается FF dead-zone + PI integral clamp
- Существующий `biba_pid_step` / `biba_pid_config_t` из `firmware/src/app/control_loop.h` —
  базовый примитив для переиспользования (или адаптации под FF+I)

**Замечание:** MOTOR-03 (ramping) формально выполнялся через рамп; PI+FF обеспечивает
эквивалентную мягкость — нужно это зафиксировать в трейсинге требований.

### 3. Scope — оба колеса IS_LEFT + IS_RIGHT

**Решение:** Phase 7 реализует ZC+PI для обоих каналов одновременно.

**ADC mapping (из Phase 5/06-FINDINGS):**
- GP26 = ADC0 = IS_LEFT (левый мотор)
- GP27 = ADC1 = IS_RIGHT (правый мотор)

**Замечание:** PoC использовал только одну ось. Phase 7 должна показать независимость
обоих контуров (разные Kp/Ki если нужно — мотор + редуктор могут различаться).

### 4. Proto — добавить wheel_rpm_hz в biba_proto

**Решение:** Расширить `biba_proto_telemetry_t` двумя полями:
- `uint16_t wheel_rpm_left_hz10`   — левое колесо, RPM в Hz × 10 (0.1 Hz resolution)
- `uint16_t wheel_rpm_right_hz10`  — правое колесо

**Затрагивает:**
- `firmware/include/biba_proto.h` — struct layout
- `firmware/src/stm32_*` или эквивалентный encode
- `biba-controller/stm32_link/protocol.py` — decode + Python `TelemetryFrame`
- `tests/test_stm32_link_protocol.py` — покрыть новые поля

**Wire encoding:** `uint16_t` LE, 0 = нет данных / ZC невалиден.

### 5. Gain scheduling для малых RPM

**Решение:** В Phase 7, если `target_hz < 200`, Ki = Ki_low (уменьшенный).

**Обоснование:** Step-response из Phase 06 при 200 Hz показал OS = 49% с Ki = 0.010.
Уменьшение в 2× (Ki_low = 0.005) должно снизить перерегулирование.

**Параметры (начальные, требуют hardware tuning):**
```c
#define ZC_PI_KP             0.002f
#define ZC_PI_KI             0.010f
#define ZC_PI_KI_LOW         0.005f   // gain scheduling: target < 200 Hz
#define ZC_PI_KI_LOW_THRESH  200.0f   // Hz
#define ZC_PI_FF_SLOPE       10.13f   // Hz per % duty (K from calibration)
#define ZC_PI_FF_DEAD        74.6f    // Hz dead-zone offset
```

### 6. Тестируемость — Unity C tests в firmware/test/

**Решение:** Все новые C-модули (zc_detector, rpm_pi) покрыты Unity unit-тестами в
`firmware/test/`.

**Паттерн:** существующий `firmware/test/` использует PlatformIO native env для Unity.
Новые тесты:
- `firmware/test/test_zc_detector/` — синтетический IS-сигнал → правильная Hz ±5%
- `firmware/test/test_rpm_pi/` — step-response mock → OS < 20% при 400 Hz, < 30% при 200 Hz

---

## Calibration Workflow

**Проблема:** K = 10.13 Hz/% получен из PoC с конкретным мотором и RC-фильтром.
Нужен повторяемый способ верифицировать/обновить K с реальным тахометром.

**Решение — offline calibration flow:**

1. **CALRUN команда** (или расширение SWEEP) в тестовой прошивке:
   - Крутит мотор на заданных duty-точках (например 30%, 50%, 70%, 90%)
   - Логирует `is_hz` по ZC для каждой точки

2. **Скрипт `scripts/is_rpm_calibrate.py`**:
   - Автоматически запускает CALRUN и собирает is_hz
   - Запрашивает у пользователя показание прибора для каждой точки
   - Считает K = polyfit(duty, tach_hz), сохраняет в `scripts/artifacts/calibration/`
   - Опционально: проверяет R² > 0.95, предупреждает если хуже

**Формат вывода:**
```json
{
  "wheel": "left",
  "date": "2026-05-XX",
  "K_hz_per_pct": 10.13,
  "dead_hz": 74.6,
  "r_squared": 0.97,
  "points": [
    {"duty_pct": 30, "is_hz": 228, "tach_hz": 231},
    ...
  ]
}
```

---

## Speed Estimation (m/s)

**Решение:** Pi Python пересчитывает `wheel_rpm_hz10` из proto в m/s.

**Формула:** `v_m_s = (rpm_hz × 2π × WHEEL_RADIUS_M) / GEAR_RATIO`

**Config (biba-controller/config.py):**
```python
WHEEL_RADIUS_M = float(os.getenv("WHEEL_RADIUS_M", "0.100"))  # m, default 10cm
GEAR_RATIO     = float(os.getenv("GEAR_RATIO", "1.0"))        # dimensionless
```

Значения по умолчанию — placeholder. Пользователь измеряет колесо и задаёт через env.

---

## Key Constraints

| Constraint | Value |
|-----------|-------|
| ADC sample rate | 10 kSPS (10 kHz, RP2040 DMA) |
| DMA window | 1024 samples = 100 ms |
| ZC loop rate | ~10 Hz |
| ZC valid range | 80 – 2500 Hz |
| IS frequency range @ 25–100% duty | ~180 – 940 Hz |
| PI update period | ~100 ms (dt ≈ 0.104 s measured) |
| FF formula | `ff = dir × (target_hz + 74.6) / (10.13 × 100)` |
| Transient blanking | |Δduty| > 0.08 → skip 512 samples; > 0.03 → skip 256 |
| HAL range | `biba_hal_motor_pwm_left/right(float [-1.0, 1.0])` |
| GP26 / GP27 conflict | Phase 5 uses these for VBAT/IBAT on ADS1115 variant — check pinout |

---

## ADC Conflict Note

Phase 5 ADC remap assigned GP26=ADC0 to IS_LEFT and GP27=ADC1 to IS_RIGHT for RPM PoC.
In the Phase 5 standalone config, GP26/GP27 were used for VBAT/IBAT via ADS1115 I2C.

**Resolution needed in planning:** confirm ADC pinout for production standalone env.
The IS-signal path uses internal ADC (no ADS1115). If ADS1115 is present and handles
VBAT/IBAT, the RP2040 internal ADC0/ADC1 are free for IS_LEFT/IS_RIGHT.

---

## Phase 06 PoC Reference

Key files to port/adapt:
- `firmware/src/poc/is_rpm_poc_main.cpp` — ZC detector (A2 Schmitt), PI+FF, USB CDC shell
- `scripts/is_poc_analyse.py` — FFT/ZC/autocorr algorithms (Python reference)

Key parameters confirmed in PoC:
- ZC_SUBWIN_K = 8 blocks × 128 samples, local min/max/hyst per block, ≥2 active blocks
- ZC_MIN_VALID_HZ = 80, ZC_MAX_VALID_HZ = target×2.5 + 300
- EMA alpha = 0.7 on measured hz
- Stiction floor = 20% duty

---

## Not In Scope (Phase 7)

- UART CDC shell в production firmware (только для тестовой прошивки)
- FFT / autocorr алгоритмы (только A2 Schmitt ZC)
- Heading-hold / yaw correction (Phase 2)
- ROS2 velocity state (open-loop пока, real velocity — Phase 8+)

---

## Canonical Refs

- `firmware/src/poc/is_rpm_poc_main.cpp` — source to port
- `firmware/src/app/control_loop.h` — `biba_pid_step`, `biba_mix_differential`
- `firmware/src/app/ramp.h` — to be replaced by PI in standalone
- `firmware/include/biba_proto.h` — extend telemetry struct
- `biba-controller/stm32_link/protocol.py` — extend Python decoder
- `tests/test_stm32_link_protocol.py` — update for new proto fields
- `.planning/phases/06-is-rpm-poc/06-FINDINGS.md` — calibrated params, algorithm notes
- `.planning/phases/06-is-rpm-poc/06-SUMMARY.md` — Phase 07 architectural notes section
