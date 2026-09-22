# Phase 08 Context — Session Flight Recorder (Black Box)

**Created:** 2026-05-25
**Phase:** 08 — Запись телеметрии сессии на flash RP2040 с доступом через USB CDC
**Source:** discuss-phase session (interactive)
**Status:** context captured, ready for research + planning

---

## Phase Goal

Добавить чёрный ящик на RP2040: оператор включает тумблер (CH8) → бибика
играет SOS-мелодию → при арминге начинается запись бинарного файла сессии на
LittleFS flash. При подключении к компьютеру — Python-скрипт скачивает файлы
через USB CDC (уже есть, `/dev/ttyACM0`).

---

## Architecture Decisions

### 1. Носитель — LittleFS на внутреннем flash RP2040

**Решение:** LittleFS на внутреннем 2MB flash Pico.

**Обоснование:**
- На плате нет SD-слота и свободных SPI-пинов под него
- Firmware занимает ~113KB → ~1.9MB свободно под данные
- earlephilhower/arduino-pico включает LittleFS из коробки (`SPIFFS`/`LittleFS` API)
- Wear leveling в LittleFS защищает flash от преждевременного износа
- При 10 Hz и ~80 байт/запись: 60 мин сессия ≈ 2.9MB — нужен ring-over механизм

**Конфигурация flash layout:**
- Firmware partition: первые 256KB (запас; реально 113KB)
- LittleFS partition: остаток (настраивается через `board_build.filesystem_size` в `platformio.ini`)
- Целевой размер FS: 1MB (баланс между данными и надёжностью)

---

### 2. CRSF-канал — CH8

**Решение:** CH8 управляет чёрным ящиком (тумблер на пульте).

**Текущее использование каналов:**
- CH1: throttle, CH2: yaw/rudder, CH3/CH4: pitch/roll (не используется)
- CH5: arming (тумблер арминга)
- CH6: speed_sel (3-позиционный переключатель скоростей)
- CH7: trim_save (кнопка сохранения трима)
- **CH8: blackbox_enable** — новый, этот фаза

**Порог:** CRSF > 1500 μs = включён, ≤ 1500 μs = выключен (стандартный для тумблеров).

---

### 3. Логика включения/записи

**Полная последовательность:**

```
1. CH8 HIGH (до арма):
   a. Flash не полон → играем biba_melody_sos + RGB индикация (синий мигает)
   b. Flash полон    → играем biba_melody_failsafe (ошибка)
                       CH8 HIGH второй раз → перезаписываем самую старую сессию

2. Арминг (CH5 HIGH) при CH8 HIGH:
   → открываем новый файл session_NNNN.bbd
   → начинаем запись с частотой BIBA_BLACKBOX_RATE_HZ

3. Разарминг или CH8 LOW:
   → закрываем файл (flush + close)
   → LED гаснет
```

**Нет записи при дисарме** — чёрный ящик пишет только пока armed == true.

---

### 4. Формат файла — бинарный .bbd

**Имя файла:** `session_NNNN.bbd` (NNNN — 4-значный порядковый номер, хранится в `blackbox_meta.bin`)

**Заголовок файла (32 байта):**
```c
typedef struct {
    uint8_t  magic[4];        /* "BBD1" */
    uint32_t created_tick_ms; /* biba_hal_now_ms() при создании */
    uint16_t field_mask;      /* битовая маска записываемых полей */
    uint8_t  rate_hz;         /* BIBA_BLACKBOX_RATE_HZ */
    uint8_t  reserved[21];    /* pad to 32 bytes */
} biba_blackbox_header_t;
```

**Одна запись (переменный размер по field_mask, максимум ~44 байта):**

| Бит | Поле | Тип | Размер |
|-----|------|-----|--------|
| 0 | `timestamp_ms` | uint32_t | 4 |
| 1 | `throttle` | int16_t (×1000) | 2 |
| 2 | `rudder` | int16_t (×1000) | 2 |
| 3 | `duty_left` | int16_t (×1000) | 2 |
| 4 | `duty_right` | int16_t (×1000) | 2 |
| 5 | `rpm_left_hz10` | uint16_t | 2 |
| 6 | `rpm_right_hz10` | uint16_t | 2 |
| 7 | `active_blocks_l` | uint8_t | 1 |
| 8 | `active_blocks_r` | uint8_t | 1 |
| 9 | `mean_is_l` | uint16_t | 2 |
| 10 | `mean_is_r` | uint16_t | 2 |
| 11 | `latch_resets` | uint8_t (накопленный) | 1 |
| 12 | `vbat_mv` | uint16_t | 2 |
| 13 | `pi_integral_l` | int16_t (×10000) | 2 |
| 14 | `pi_integral_r` | int16_t (×10000) | 2 |
| 15 | `pi_meas_ema_l` | uint16_t (Hz×10) | 2 |

**Конфигурация через `#define BIBA_BLACKBOX_FIELD_MASK`** — по умолчанию все поля включены (0xFFFF).
Для длинных сессий оператор может уменьшить маску чтобы писать меньше данных.

**Оценка размера при полной маске и 10 Hz:**
- ~40 байт/запись × 10 в сек = 400 байт/сек = 24 KB/мин → 60 мин ≈ 1.4 MB

---

### 5. Flash-менеджмент — ring через самую старую сессию

**При первом попытке записи когда места < BIBA_BLACKBOX_MIN_FREE_KB (64KB):**
- Играем `biba_melody_failsafe` (звук ошибки)
- Флаг `s_blackbox_full_warned = true`

**При второй попытке (CH8 HIGH снова, флаг уже выставлен):**
- Удаляем самую старую сессию (наименьший NNNN из `blackbox_meta.bin`)
- Начинаем запись в освободившееся место

---

### 6. Звуковая индикация

| Событие | Мелодия |
|---------|---------|
| CH8 HIGH, flash не полон | `biba_melody_sos` (SOS-сигнал — характерный) |
| CH8 HIGH, flash полон | `biba_melody_failsafe` (предупреждение) |
| CH8 LOW (выкл) | *(тишина)* |

---

### 7. Доступ с компьютера — CDC + Python-скрипт

**Транспорт:** USB CDC (уже поднят для `printf` и debug shell — `/dev/ttyACM0`).

**Новые shell-команды в `mode_standalone.c` / `usb_shell.c`:**
```
bb list                 → список файлов: session_0001.bbd 14520 bytes
bb get session_0001.bbd → XMODEM или raw binary stream с заголовком размера
bb del session_0001.bbd → удалить файл
bb info                 → размер FS, свободное место, текущая сессия
```

**Python-скрипт `scripts/biba_blackbox_download.py`:**
```python
# Использование:
# python3 scripts/biba_blackbox_download.py [--port /dev/ttyACM0] [--all] [--session 0001]
# Автоматически:
# 1. Подключается к порту
# 2. Запрашивает bb list
# 3. Скачивает выбранные (или все) файлы в ./artifacts/blackbox/
# 4. Конвертирует .bbd → .csv (декодер по field_mask)
```

**Выходной формат скрипта:** CSV с заголовком (имена полей из field_mask).

---

### 8. Частота записи — параметр

**Решение:** `#define BIBA_BLACKBOX_RATE_HZ 10` в `config.h` (или `target.h`).
Пользователь меняет define и пересобирает для другой частоты.

**Реализация:** счётчик DMA-окон в `on_adc_pair_done()` — запись каждые
`(20kHz / (512 sps × 2 ch)) / BIBA_BLACKBOX_RATE_HZ` окон ≈ каждые
`floor(19.5 / RATE_HZ)` вызовов IRQ. При 10 Hz — каждые ~2 DMA-окна (~100ms).

---

## Canonical Refs

- `firmware/targets/RPICO_RP2040/target.h` — пины, ADC mapping
- `firmware/src/modes/mode_standalone.c` — основной режим (точка интеграции)
- `firmware/src/app/melody.h` — каталог мелодий (biba_melody_sos, biba_melody_failsafe)
- `firmware/src/app/rpm_pi.h` — biba_rpm_pi_state_t (integral, meas_ema, prev_duty, primed)
- `firmware/platformio.ini` — env конфигурация (board_build.filesystem_size)
- `biba-controller/config.py` — образец конфигурации параметров (паттерн для BIBA_BLACKBOX_*)
- `scripts/vcp_capture.py` — образец Python CDC-скрипта (паттерн для download-скрипта)

---

## Deferred Ideas

- Запись сырых IS-буферов (ADC samples) — слишком большой объём, отдельная фаза
- Передача по CRSF телеметрии в реальном времени — TELEM-01 в backlog
- Web-просмотрщик сессий — отдельный milestone
- RTC-timestamp в именах файлов — нет RTC на плате, откладываем
