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

## Поддерживаемые таргеты

| Target                  | Плата                                                       |
| ----------------------- | ----------------------------------------------------------- |
| `RPICO_RP2040`          | Pico с BTS7960 и SBC по UART1 (default `env`); см. его `target.md` |
| `RPICO_RP2040_BLDC`     | Альтернативный таргет на той же board: пара BLDC через ODrive по CAN (MCP2515 на SPI0 GP16–19, INT=GP15). BTS7960 и native ADC отключены. Архитектура — `docs/adr/0001-pico-bldc-target.md`. |

STM32-таргеты (`BLUEPILL_F103C8`, `BLUEPILL_F103C8_CLONE`,
`BIBA_F103_REV_A`) удалены — проект не собирает прошивку под STM32.

## Матрица сборки

Каждый таргет комбинируется со всеми режимами прошивки
(`standalone` / `companion` / `combined`). Имя env'а —
`<target_lowercase>_<mode>`:

```bash
# Pico с BTS7960
pio run -e rpico_rp2040_standalone
pio run -e rpico_rp2040_companion

# RP2040 BLDC/CAN вариант (alias на ту же board, но другой backend)
pio run -e rpico_rp2040_bldc_standalone
pio run -e rpico_rp2040_bldc_companion
pio run -e rpico_rp2040_bldc_combined

# переносимые хостовые тесты (без таргета)
pio test -e native_test
```

CI-workflow `.github/workflows/G-Build-Firmware-Native-Tests.yml`
запускает только `pio test -e native_test`; сборка под конкретный
таргет прошивки в CI не производится и делается локально.

## Как добавить новый таргет

1. **Скопируй ближайший по распиновке таргет.** Возьми тот, чья
   распиновка ближе всего к твоей плате, и скопируй директорию:

   ```bash
   cp -r firmware/targets/RPICO_RP2040 firmware/targets/<YOUR_TARGET>
   ```

2. **Отредактируй `target.h`.** Поставь свой `BIBA_TARGET_NAME`,
   переключи флаги `BIBA_TARGET_HAS_*` под своё железо (например,
   отключи IMU, если на плате нет I²C-шины) и поправь все макросы
   `BIBA_PIN_*_PORT/PIN`. Не убирай комментарии-секции — код в
   `src/hal/biba_hal.c` ищет именно эти имена макросов.

3. **Отредактируй `target_config.h`.** Переопредели калибровочные
   константы (масштаб тока, делитель батареи, лимит тока на сторону).
   Переопределяй только то, что реально отличается — `include/biba_config.h`
   подставляет дефолты через `#ifndef`-гарды.

4. **Зарегистрируй таргет в `platformio.ini`.** Добавь одну секцию
   `[target_*]` и по одному блоку `[env:*_<mode>]` на каждый режим
   прошивки — скопируй `rpico_rp2040_*` env'ы и переименуй. Пример
   для нового `MY_BOARD_RP2040`:

   ```ini
   [target_my_board_rp2040]
   board = rpipico
   target_include = targets/MY_BOARD_RP2040
   build_flags = -DBIBA_TARGET_MY_BOARD_RP2040=1

   [env:my_board_rp2040_standalone]
   platform = https://github.com/maxgerhardt/platform-raspberrypi.git
   framework = arduino
   board = ${target_my_board_rp2040.board}
   upload_protocol = picotool
   debug_tool = cmsis-dap
   build_src_filter = ${rp2040_src_filter.build_src_filter}
   build_flags =
       -Iinclude
       -Isrc
       -Isrc/proto
       -I${target_my_board_rp2040.target_include}
       ${target_my_board_rp2040.build_flags}
       ${mode_standalone.build_flags}
       -Wl,-u,_printf_float
   ```

5. **Добавь строку в таблицу выше.** CI собирает только
   `pio test -e native_test` (см.
   `.github/workflows/G-Build-Firmware-Native-Tests.yml`); сборка под
   конкретный таргет делается локально командой `pio run -e ...`.

6. **Опиши плату** в `target.md` — как минимум разницу по пинам с
   каким-нибудь существующим таргетом. Это держит знание «чем особенна
   эта плата?» рядом с кодом, который её реализует.

## Контракт переносимого кода

Перечисленные ниже макросы заголовка считаются **ABI таргета**.
Добавление, удаление или переименование любого из них — ломающее
изменение; имена должны полностью совпадать с тем, как они написаны в
`RPICO_RP2040/target.h`:

- `BIBA_TARGET_NAME`
- `BIBA_TARGET_HAS_BTS7960_2CH` — `1`, если две BTS7960-линии +
  токовые шунты присутствуют и режим `biba_bts7960_*` собирается; `0`,
  если используется альтернативный motor backend (ODrive/CAN на
  `RPICO_RP2040_BLDC`).
- `BIBA_TARGET_HAS_BLDC_2CH` — `1`, если таргет компонуется с
  `biba_odrive_*` API (ODrive / иной BLDC-контроллер по CAN). Только
  один из `BTS7960_2CH` / `BLDC_2CH` может быть `1` одновременно.
  Введён ADR-0001.
- `BIBA_TARGET_HAS_MCP2515` — `1`, если на плате есть
  аппаратный мост SPI↔CAN (MCP2515). Используется
  `biba_odrive_can_state_init` для условной инициализации. Введён
  ADR-0001.
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
