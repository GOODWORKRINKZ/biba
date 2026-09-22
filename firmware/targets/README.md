# Таргеты прошивки

Прошивка BiBa организована так же, как у Betaflight и ELRS:
переносимый код лежит в `src/`, а каждая поддерживаемая **аппаратная
конфигурация** (распиновка, масштаб токового сенсора, наличие
периферии) получает собственную директорию `targets/<TARGET>/`.

Таргет полностью описывается тремя файлами:

```
targets/<TARGET>/
├── target.h            # распиновка + флаги BIBA_TARGET_HAS_*
├── target_config.h     # калибровки и лимиты под конкретную плату
└── target.md           # документация: чем этот таргет отличается от других
```

Переносимый код в `src/` подключает только `biba_board.h` и
`biba_config.h` — это тонкие шимы, которые включают `target.h` /
`target_config.h` через путь `-I targets/<TARGET>`, добавляемый
PlatformIO в каждом env. Никаких лесенок `#ifdef TARGET == …` в `src/`
нет.

## Стандарт имён

Имя таргета — это четыре слота через подчёркивание:

```
<MCU>_<MOTOR>_<DRIVER>_<LINK>
 │      │       │        └── как МК разговаривает с драйвером: PWM / CAN / UART
 │      │       └─────────── чем крутим: BTS7960 / ODRIVE / VESC
 │      └─────────────────── тип мотора: DC (щёточный) / BLDC
 └────────────────────────── микроконтроллер: RP2040
```

Читается слева направо как «RP2040, бесколлекторные моторы, драйверы
VESC, связь по CAN» → `RP2040_BLDC_VESC_CAN`.

Почему слот линка отдельный, а не флаг сборки: **линк меняет
распиновку**. У `RP2040_BLDC_ODRIVE_CAN` занят SPI0 под MCP2515, у
`RP2040_BLDC_ODRIVE_UART` эти пины свободны, зато занят UART1. Это
разное железо, а таргет в этом проекте описывает именно железо.
Обоснование — `docs/adr/0002-target-naming-and-vesc.md`.

Плата, которая **не крутит моторы**, слотов MOTOR/DRIVER не имеет и
называется `<MCU>_BRIDGE_<FUNCTION>` — сейчас это только
`RP2040_BRIDGE_PWM2CRSF`.

Имя env — то же самое в нижнем регистре плюс режим:
`<target_lowercase>_<mode>`.

## Поддерживаемые таргеты

| Target                    | Мотор | Драйвер | Линк | Плата / особенности |
| ------------------------- | ----- | ------- | ---- | ------------------- |
| `RP2040_DC_BTS7960_PWM`   | щёточный DC | BTS7960 ×2 | прямой PWM | Pico + BTS7960, SBC по UART1. Таргет по умолчанию (`default_envs`). |
| `RP2040_BLDC_ODRIVE_CAN`  | BLDC  | ODrive Pro/S1/Micro ×2 | CAN (MCP2515 на SPI0 GP16–19, INT=GP15) | 250 кбит/с, CANSimple, 11-bit ID. BTS7960 и native ADC отключены. Архитектура — `docs/adr/0001-pico-bldc-target.md`. |
| `RP2040_BLDC_ODRIVE_UART` | BLDC  | ODrive Pro/S1/Micro ×2 | UART1 ASCII (GP4/GP5) | Без MCP2515 (`BIBA_TARGET_HAS_MCP2515 = 0`). Сейчас предпочтительный production-линк: CANSimple в прошивке ODrive 0.5.6 залипает на холостом ходу. |
| `RP2040_BLDC_VESC_CAN`    | BLDC  | Flipsky dual FSESC (спаренный VESC) | CAN (тот же MCP2515-мост) | 500 кбит/с, 29-bit extended ID, big-endian, accept-all фильтры. Драйвер — `src/drivers/vesc_can.c`. |
| `RP2040_BRIDGE_PWM2CRSF`  | —     | —       | —    | Не контроллер бибы: отдельная Pico-мост, 6×PWM с приёмника HotRC → CRSF, ставится вместо ELRS-приёмника. Один env, без режимов. |

STM32-таргеты (`BLUEPILL_F103C8`, `BLUEPILL_F103C8_CLONE`,
`BIBA_F103_REV_A`) удалены — проект не собирает прошивку под STM32.

## Матрица сборки

Каждый таргет привода комбинируется с режимами прошивки
(`standalone` / `companion` / `combined`):

```bash
# щёточные DC на BTS7960
pio run -e rp2040_dc_bts7960_pwm_standalone
pio run -e rp2040_dc_bts7960_pwm_companion

# BLDC на ODrive по CAN
pio run -e rp2040_bldc_odrive_can_standalone
pio run -e rp2040_bldc_odrive_can_companion
pio run -e rp2040_bldc_odrive_can_combined

# BLDC на ODrive по UART (ASCII)
pio run -e rp2040_bldc_odrive_uart_standalone
pio run -e rp2040_bldc_odrive_uart_companion
pio run -e rp2040_bldc_odrive_uart_combined

# BLDC на VESC по CAN
pio run -e rp2040_bldc_vesc_can_standalone
pio run -e rp2040_bldc_vesc_can_companion
pio run -e rp2040_bldc_vesc_can_combined

# мост HotRC PWM → CRSF (отдельная плата, режимов нет)
pio run -e rp2040_bridge_pwm2crsf

# переносимые хостовые тесты (без таргета)
pio test -e native_test
```

Плюс два bring-up PoC-env'а, не входящих в матрицу режимов:

```bash
pio run -e rp2040_bldc_odrive_can_loopback_poc   # SPI↔MCP2515 self-test
pio run -e rp2040_dc_bts7960_pwm_is_poc          # IS-pin / RPM PoC
```

CI-workflow `.github/workflows/G-Build-Firmware-Native-Tests.yml`
запускает только `pio test -e native_test`; сборка под конкретный
таргет прошивки в CI не производится и делается локально.

## Как добавить новый таргет

1. **Выбери имя по стандарту** `<MCU>_<MOTOR>_<DRIVER>_<LINK>`
   (см. выше). Если отличается только линк — это всё равно новый
   таргет, а не флаг.

2. **Скопируй ближайший по распиновке таргет.** Возьми тот, чья
   распиновка ближе всего к твоей плате, и скопируй директорию:

   ```bash
   cp -r firmware/targets/RP2040_DC_BTS7960_PWM firmware/targets/<YOUR_TARGET>
   ```

3. **Отредактируй `target.h`.** Поставь свой `BIBA_TARGET_NAME`,
   переключи флаги `BIBA_TARGET_HAS_*` под своё железо (например,
   отключи IMU, если на плате нет I²C-шины) и поправь все макросы
   `BIBA_PIN_*_PORT/PIN`. Не убирай комментарии-секции — код в
   `src/hal/biba_hal.c` ищет именно эти имена макросов.

4. **Отредактируй `target_config.h`.** Переопредели калибровочные
   константы (масштаб тока, делитель батареи, лимит тока на сторону).
   Переопределяй только то, что реально отличается — `include/biba_config.h`
   подставляет дефолты через `#ifndef`-гарды.

5. **Зарегистрируй таргет в `platformio.ini`.** Добавь одну секцию
   `[target_*]`, при необходимости свой `[*_src_filter]`, и по одному
   блоку `[env:*_<mode>]` на каждый режим прошивки. Пример для нового
   `RP2040_DC_MYDRIVER_PWM`:

   ```ini
   [target_rp2040_dc_mydriver_pwm]
   board = rpipico
   target_include = targets/RP2040_DC_MYDRIVER_PWM
   build_flags = -DBIBA_TARGET_RP2040_DC_MYDRIVER_PWM=1

   [env:rp2040_dc_mydriver_pwm_standalone]
   platform = https://github.com/maxgerhardt/platform-raspberrypi.git
   framework = arduino
   board = ${target_rp2040_dc_mydriver_pwm.board}
   upload_protocol = picotool
   debug_tool = cmsis-dap
   build_src_filter = ${rp2040_dc_src_filter.build_src_filter}
   build_flags =
       -Iinclude
       -Isrc
       -Isrc/proto
       -I${target_rp2040_dc_mydriver_pwm.target_include}
       ${target_rp2040_dc_mydriver_pwm.build_flags}
       ${mode_standalone.build_flags}
       -Wl,-u,_printf_float
   ```

6. **Добавь строку в таблицу выше.** CI собирает только
   `pio test -e native_test` (см.
   `.github/workflows/G-Build-Firmware-Native-Tests.yml`); сборка под
   конкретный таргет делается локально командой `pio run -e ...`.

7. **Опиши плату** в `target.md` — как минимум разницу по пинам с
   каким-нибудь существующим таргетом. Это держит знание «чем особенна
   эта плата?» рядом с кодом, который её реализует.

8. **Обнови `docs/variants.md`** — матрица вариантов железа.

## Как добавить новый BLDC-драйвер

Все BLDC-бэкенды реализуют один контракт — `src/drivers/bldc.h`
(`biba_bldc_init` / `_set_enabled` / `_drive` / `_tick_50hz` / …).
Код режимов в `src/modes/*.c` вызывает только его и не знает, ODrive
там или VESC.

1. Напиши `src/drivers/<driver>_<link>.c`, реализующий все функции
   из `bldc.h`. В начале файла поставь `#error`-якорь на свой флаг
   бэкенда, чтобы файл нельзя было случайно собрать не туда
   (см. шапку `vesc_can.c`).
2. Заведи флаг `BIBA_TARGET_BLDC_BACKEND_<DRIVER>` в `target.h`
   нового таргета; ровно один из BACKEND-флагов должен быть `1`.
3. Заведи в `platformio.ini` свой `[*_src_filter]`: включи свой TU
   и **исключи остальные бэкенды** — иначе линкер получит несколько
   определений `biba_bldc_drive`.
4. Если линк — CAN, переиспользуй `drivers/mcp2515.c` +
   `drivers/can_queue.c`. Драйвер MCP2515 умеет 11- и 29-битные ID,
   100/250/500 кбит/с (`BIBA_CAN_BITRATE_BPS`) и режим accept-all
   (`BIBA_MCP2515_ACCEPT_ALL`).

## Контракт переносимого кода

Перечисленные ниже макросы заголовка считаются **ABI таргета**.
Добавление, удаление или переименование любого из них — ломающее
изменение; имена должны полностью совпадать с тем, как они написаны в
`RP2040_DC_BTS7960_PWM/target.h`:

- `BIBA_TARGET_NAME`
- `BIBA_TARGET_HAS_BTS7960_2CH` — `1`, если две BTS7960-линии +
  токовые шунты присутствуют и режим `biba_bts7960_*` собирается; `0`,
  если используется альтернативный motor backend (BLDC-таргеты).
- `BIBA_TARGET_HAS_BLDC_2CH` — `1`, если таргет компонуется с
  `biba_bldc_*` API (`src/drivers/bldc.h`). Только один из
  `BTS7960_2CH` / `BLDC_2CH` может быть `1` одновременно.
  Введён ADR-0001.
- `BIBA_TARGET_BLDC_BACKEND_ODRIVE` / `BIBA_TARGET_BLDC_BACKEND_VESC` —
  какой бэкенд реализует `bldc.h` на этом таргете. Ровно один может
  быть `1`; обязательны при `BIBA_TARGET_HAS_BLDC_2CH == 1`.
  Введены ADR-0002.
- `BIBA_TARGET_HAS_MCP2515` — `1`, если на плате есть
  аппаратный мост SPI↔CAN (MCP2515). По нему `hal/biba_hal_motor_bldc.c`
  условно разводит INT-пин на ISR. Введён ADR-0001.
- `BIBA_TARGET_HAS_CRSF`
- `BIBA_TARGET_HAS_IMU`
- `BIBA_TARGET_HAS_SPI_SLAVE`
- `BIBA_TARGET_HAS_PER_CHANNEL_TIMER_PWM` — `1`, если каждая из четырёх
  PWM-линий мотора висит на своём аппаратном таймере (это включает
  motor-audio); `0`, если все четыре делят один таймер
- `BIBA_PIN_{LEFT,RIGHT}_{RPWM,LPWM,REN,LEN}_{PORT,PIN}`
- При `BIBA_TARGET_HAS_PER_CHANNEL_TIMER_PWM == 1` дополнительно:
  `BIBA_PWM_{LEFT,RIGHT}_{RPWM,LPWM}_{TIM,CHANNEL,CLK_ENABLE,AF_REMAP}`
- `BIBA_ADC_CHAN_*` и `BIBA_ADC_SCAN_LEN`
- `BIBA_PIN_{CRSF_TX,CRSF_RX,SPI_*,DATA_READY,MODE_SEL,I2C_*,IMU_INT1,STATUS_LED}_{PORT,PIN}`
- `BIBA_STATUS_LED_ACTIVE_LOW`

Если плата принципиально не может предоставить какой-то из пинов
(нет SPI-slave, нет IMU и т. п.) — выставь соответствующий
`BIBA_TARGET_HAS_*` в 0 и не определяй макросы пинов; HAL уже
загораживает соответствующий init-код этим флагом.

Пин-макросы SPI0 (`BIBA_PIN_SPI0_MISO_GPIO`, `BIBA_PIN_SPI0_SCK_GPIO`,
`BIBA_PIN_SPI0_MOSI_GPIO`, `BIBA_PIN_SPI0_CS_GPIO`) и
`BIBA_PIN_MCP2515_INT_GPIO` обязательны только при
`BIBA_TARGET_HAS_MCP2515 == 1`; на остальных таргетах они не
определяются.

Адресация BLDC-узлов — `BIBA_BLDC_LEFT_NODE_ID` /
`BIBA_BLDC_RIGHT_NODE_ID` в `target_config.h`, одинаково для всех
бэкендов (у ODrive это node_id CANSimple, у VESC — controller id).
