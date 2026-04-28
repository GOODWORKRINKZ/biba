# Таргеты прошивки

Прошивка BiBa для STM32 организована так же, как у Betaflight и ELRS:
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
| `BLUEPILL_F103C8`       | Эталон: серийный STM32F103C8T6 «Blue Pill» (20 КБ ОЗУ)      |
| `BLUEPILL_F103C8_CLONE` | Та же распиновка, клон-чип с реальными 8 КБ ОЗУ             |
| `BIBA_F103_REV_A`       | Пример кастомной платы (прототип ревизии A)                 |

У варианта `_CLONE` нет отдельной директории внутри `targets/`. Он
переиспользует `BLUEPILL_F103C8/target.h` буква в букву и отличается
только линкер-скриптом и лимитом RAM в PlatformIO — обоснование
смотри в [`BLUEPILL_F103C8/target.md`](BLUEPILL_F103C8/target.md).

## Матрица сборки

Каждый таргет комбинируется со всеми режимами прошивки
(`standalone` / `companion` / `combined`). Имя env'а —
`<target_lowercase>_<mode>`:

```bash
# серийный Blue Pill
pio run -e bluepill_f103c8_standalone
pio run -e bluepill_f103c8_companion
pio run -e bluepill_f103c8_combined

# клон Blue Pill (линкер на 8 КБ ОЗУ)
pio run -e bluepill_f103c8_clone_standalone
pio run -e bluepill_f103c8_clone_companion
pio run -e bluepill_f103c8_clone_combined

# кастомная плата
pio run -e biba_f103_rev_a_standalone
pio run -e biba_f103_rev_a_companion

# переносимые хостовые тесты (без таргета)
pio test -e native_test
```

CI-workflow `.github/workflows/G-Build-STM32F103.yml` итерируется по
всем парам `<target, mode>` и публикует артефакты `<target>-<mode>.bin`.

## Как добавить новый таргет

1. **Скопируй ближайший по распиновке таргет.** Возьми тот, чья
   распиновка ближе всего к твоей плате, и скопируй директорию:

   ```bash
   cp -r firmware/targets/BLUEPILL_F103C8 firmware/targets/<YOUR_TARGET>
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
   прошивки — скопируй `biba_f103_rev_a_*` env'ы и переименуй. Пример
   для нового `MY_BOARD_F103`:

   ```ini
   [target_my_board_f103]
   build_flags = -DBIBA_TARGET_SELECTED=MY_BOARD_F103
   target_include = targets/MY_BOARD_F103

   [env:my_board_f103_standalone]
   extends = env, fw_common, target_my_board_f103, mode_standalone
   board = ${target_my_board_f103.board}
   build_flags =
       ${fw_common.build_flags}
       -I${target_my_board_f103.target_include}
       ${target_my_board_f103.build_flags}
       ${mode_standalone.build_flags}
   ```

5. **Обнови матрицу CI** в
   `.github/workflows/G-Build-STM32F103.yml`, если хочешь покрытие в
   CI, и добавь строку в таблицу выше.

6. **Опиши плату** в `target.md` — как минимум разницу по пинам с
   каким-нибудь существующим таргетом. Это держит знание «чем особенна
   эта плата?» рядом с кодом, который её реализует.

## Контракт переносимого кода

Перечисленные ниже макросы заголовка считаются **ABI таргета**.
Добавление, удаление или переименование любого из них — ломающее
изменение; имена должны полностью совпадать с тем, как они написаны в
`BLUEPILL_F103C8/target.h`:

- `BIBA_TARGET_NAME`
- `BIBA_TARGET_HAS_BTS7960_2CH`
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
