# Системная архитектура BiBa

Этот документ — канонический обзор всех трёх аппаратных композиций робота, ответственности SBC и STM32, профилей ROS2-стека и точек расширения. Он рассчитан на тех, кто открывает репозиторий впервые и хочет за один проход понять «что где живёт». Низкоуровневая часть STM32 описана в [stm32_architecture.md](stm32_architecture.md), будущий ROS2-стек — в [ros2_stack.md](ros2_stack.md), развёртывание — в [deployment.md](deployment.md). Исходный design-doc, из которого выведен этот текст, — [plans/2026-04-28-sbc-architecture-redesign-design.md](plans/2026-04-28-sbc-architecture-redesign-design.md).

## Контекст

Текущее состояние проекта:

- `biba-controller/` — Python-runtime, который умеет всё: CRSF UART, mixer, ramping, current-control, BTS7960 PWM, BMS, voice, web. Работает в одном compose-стеке (`docker/legacy-pi/docker-compose.yml`).
- `firmware/` — PlatformIO-проект для STM32F103 с режимами `standalone` / `companion` / `combined`. Прошивка может работать самостоятельно (CRSF → PWM → BTS7960) или быть SPI-slave'ом для SBC.
- `biba-controller/stm32_link/` — Python-каркас SPI-клиента к STM32, включается флагом `STM32_LINK_ENABLED=1`.

Новые входные требования, которые должна допускать архитектура (но необязательно реализовывать в этой итерации): манипулятор, ROS2, управление через интернет, внешние сенсоры (LiDAR, ToF, IMU), камера и FPV-stream, локальная автономия (SLAM, waypoints), UWB-модуль (BU4) для follow-the-tag, mission scripting.

## Три композиции робота

Проект поддерживает три аппаратные композиции одновременно. Это не три разных продукта, а три совместимых конфигурации одного и того же репозитория.

| Композиция            | Железо                       | Кто читает CRSF | Кто крутит PWM | High-level стек        |
| --------------------- | ---------------------------- | --------------- | -------------- | ---------------------- |
| **A. Pi-only**        | Pi Zero 2W                   | Pi (UART)       | Pi (BTS7960)   | сегодняшний `biba-controller/` |
| **B. STM32-only**     | STM32F103, без SBC           | STM32 (USART3)  | STM32          | нет                    |
| **C. Pi + STM32**     | SBC + STM32F103              | STM32 (USART3)  | STM32          | новый ROS2-стек        |

Правило маршрутизации CRSF (зафиксировано): **где есть STM32, туда и идёт CRSF UART.** SBC получает каналы / RSSI / LQ / failsafe-флаг только через SPI-телеметрию от STM32. Pi-only композиция читает CRSF сама — как сегодня.

Композиция C на Pi Zero 2W поддерживается только в профиле minimal (см. ниже). Для тяжёлых узлов (SLAM, видео, WebRTC, ML) требуется Pi 4/5 или Orange Pi/Radxa — это явно фиксируется в документации развёртывания.

## Принципиальное архитектурное решение

Не превращать существующий `biba-controller/` в ROS2-стек и не ломать композицию A. Вместо этого ввести **второй высокоуровневый стек** для композиции C, основанный на ROS2, и держать оба стека в репозитории рядом друг с другом.

Причины:

- Композиция A работает и проверена на реальном железе. Любая переделка `biba-controller/` под ROS2 — это риск регрессии без компенсирующей пользы для тех, у кого STM32 нет.
- Pi Zero 2W (1 ГБ RAM, 4×Cortex-A53) тянет ROS2 + voice + web с трудом. Делать ROS2 единственным путём — значит резать Zero 2W.
- ROS2 даёт стандартные интерфейсы (`/cmd_vel`, `/odom`, `/battery_state`, `/joint_states`, TF, URDF) — это ровно то, во что естественно ложатся все новые направления (Nav2, манипулятор, UWB-follower, internet-bridge, ML, Foxglove).
- В композиции C тяжёлая низкоуровневая работа уже снята с SBC и живёт на STM32, поэтому SBC-сторона естественно становится «оркестратором узлов», а ROS2 — это и есть оркестратор узлов.

## Целевая структура репозитория

```
biba/
├── biba-controller/        # композиция A: Python-runtime, как сейчас
├── firmware/               # композиции B и C: STM32F103 PlatformIO
├── docker/
│   ├── base/               # общие base-образы (ROS2+Zenoh, ros2_control)
│   ├── legacy-pi/          # композиция A: docker-compose.yml + .env
│   └── ros2/               # композиция C: ROS2 docker-compose + сервисы
├── ros2_ws/
│   └── src/
│       ├── biba_description/        # URDF/xacro дифф-привода BiBa
│       ├── biba_msgs/               # кастомные сообщения (BMS, CRSF, motor-audio)
│       ├── biba_stm32_bridge/       # SPI ↔ ROS2 (Python, реюз stm32_link)
│       ├── biba_hardware_stm32/     # ros2_control SystemInterface (C++)
│       ├── biba_bringup/            # launch + конфиги controller_manager
│       └── (hook-points)            # пустые директории-плейсхолдеры:
│           biba_manipulator/        #   будущий пакет манипулятора
│           biba_uwb_follow/         #   follow-the-tag через BU4
│           biba_remote_bridge/      #   Zenoh / WebRTC / VPN bridge
│           biba_camera/             #   FPV stream и ML inference
│           biba_autonomy/           #   SLAM / Nav2 / waypoints / mission
├── docs/
│   ├── system_architecture.md      # этот файл
│   ├── stm32_architecture.md       # детали STM32-стороны
│   ├── ros2_stack.md               # пакеты, топики, launch
│   ├── deployment.md               # дополнен per-композиция
│   └── wiring.md                   # отметки по пинам каждой композиции
└── README.md                       # архитектурный hub
```

## ROS2-стек: контейнеры и узлы

Шаблон контейнеризации копируется с проекта `rob_box_project`:

- Один контейнер на ROS2-узел (или тесно связанную группу).
- Zenoh router (`eclipse/zenoh`) как RMW-транспорт; ROS2 поверх `rmw_zenoh_cpp`. Это даёт естественный мост в облако и в internet-bridge.
- Базовые образы строятся отдельно (`docker/base/Dockerfile.ros2-zenoh`, `Dockerfile.ros2-control` и т.д.), сервисные — поверх них. Образы публикуются в GHCR с тегом `<service>-<distro>-<branch>`.

Состав композиции C, профиль **minimal** (доступен и на Pi Zero 2W при ужатой воле):

| Контейнер              | Узел / роль                                                    |
| ---------------------- | -------------------------------------------------------------- |
| `zenoh-router`         | Zenoh маршрутизация + точка для облачного bridge               |
| `robot-state-publisher`| URDF → TF из `biba_description`                                |
| `biba-stm32-bridge`    | `biba_stm32_bridge`: SPI ↔ топики (`/cmd_vel`, `/joint_states`, `/battery_state`, `/crsf/status`, `/motor_audio`) |
| `ros2-control`         | controller_manager + `diff_drive_controller` + `joint_state_broadcaster`; hardware interface = `biba_hardware_stm32` |
| `twist-mux`            | приоритизация источников `cmd_vel`: CRSF → manual → autonomy   |

Профиль **full** (Pi 4/5+) добавляет опционально:

| Контейнер              | Источник                                                        |
| ---------------------- | --------------------------------------------------------------- |
| `biba-camera`          | `biba_camera`: FPV-stream, опционально ML inference             |
| `biba-autonomy`        | `biba_autonomy`: SLAM (rtabmap/cartographer) и/или Nav2         |
| `biba-manipulator`     | `biba_manipulator`: ros2_control hardware для servo-контроллера |
| `biba-uwb-follow`      | `biba_uwb_follow`: BU4 → tag pose → `cmd_vel`                   |
| `biba-remote-bridge`   | `biba_remote_bridge`: Zenoh-bridge / MQTT / WebRTC outward      |
| `foxglove-bridge`      | штатный `foxglove_bridge` для удалённой диагностики             |

Профили реализуются через docker-compose `profiles:` или через override-файлы — выбор делается на этапе реализации.

## Контракт `biba_stm32_bridge` ↔ STM32

Узел `biba_stm32_bridge` — единственный, кто разговаривает с STM32 по SPI. Он повторно использует `biba-controller/stm32_link/protocol.py` и `stm32_link/client.py` без копирования.

Публикуемые ROS2-топики (предварительный список, доточить в реализации):

| Топик                          | Тип сообщения                          | Источник                              |
| ------------------------------ | -------------------------------------- | ------------------------------------- |
| `/joint_states`                | `sensor_msgs/JointState`               | echo setpoint + measured currents     |
| `/battery_state`               | `sensor_msgs/BatteryState`             | агрегация из BMS и из STM32 telemetry rail |
| `/imu/data_raw`                | `sensor_msgs/Imu`                      | gyro/accel из STM32 telemetry         |
| `/biba/crsf/status`            | `biba_msgs/CrsfStatus`                 | RSSI/LQ/SNR/failsafe-flag             |
| `/biba/stm32/telemetry`        | `biba_msgs/Stm32Telemetry`             | сырая SPI-snapshot для диагностики    |

Подписки (входы):

| Топик                          | Тип                                    | Действие                              |
| ------------------------------ | -------------------------------------- | ------------------------------------- |
| `/cmd_vel`                     | `geometry_msgs/Twist`                  | → `SET_SETPOINT` (через mixer)        |
| `/biba/arm` (service)          | `std_srvs/SetBool`                     | → `ARM` / `DISARM`                    |
| `/biba/motor_audio`            | `biba_msgs/MotorAudio`                 | → `SET_MOTOR_AUDIO` (если target умеет) |

Mixer twist→left/right остаётся в `biba_stm32_bridge` (или в controller-side через `diff_drive_controller`, окончательное решение в плане реализации).

## High-level задачи SBC по композициям

### A. Pi-only

Сегодняшний набор без изменений: CRSF, mixer, ramping, current-control, BTS7960 PWM, BMS-poller, voice, web, system-stats. Новые направления (ROS2/манипулятор/UWB/интернет) в этой композиции **не поддерживаются** — для них нужно перейти на композицию C.

### B. STM32-only

SBC отсутствует. Высокоуровневых задач нет вообще. Это минимальная сборка для людей без Pi: только драйв, телеметрия по CRSF обратно оператору, motor-audio.

### C. Pi+STM32

Низкоуровневая часть полностью на STM32. На SBC — только high-level:

1. **Drive-bridge** — `biba_stm32_bridge` + `ros2_control`. MUST.
2. **Robot description** — URDF/TF через `robot_state_publisher`. MUST.
3. **Twist arbitration** — `twist_mux` с приоритетами CRSF > teleop > autonomy. MUST.
4. **BMS aggregation** — отдельный узел или часть bridge'а, публикует `/battery_state`. MUST (или MAY, если на STM32-target есть VBAT-sense и хватает её).
5. **Telemetry-out** — Zenoh router; внешний `foxglove_bridge` опционально.
6. **Voice runtime** — переезд из `biba-controller/buzzer/voice` в отдельный ROS2-узел `biba_voice` (вне scope этого документа). На время миграции допустимо запускать `biba-controller` рядом с ROS2-стеком на одной Pi для voice.
7. **Web UI** — то же: остаётся в `biba-controller` до отдельной миграции.

Расширения (отдельные планы, отдельные дизайны):

- Манипулятор: `biba_manipulator` как `ros2_control` системой поверх USB/I2C servo-контроллера. Топики `/manipulator/joint_states` и `/manipulator/joint_trajectory_controller/...`.
- Internet remote control: `biba_remote_bridge` через Zenoh→облачный Zenoh-router и/или WebRTC для видео.
- Камера и ML: `biba_camera`, отдельный контейнер, требует Pi 4/5.
- Автономия: `biba_autonomy` (rtabmap или Nav2), требует Pi 4/5 и LiDAR.
- UWB-follower: `biba_uwb_follow`, отдельный контейнер; читает BU4 по USB/UART, публикует pose тага и/или прямо `cmd_vel` с низким приоритетом в `twist_mux`.
- Mission scripting: `biba_autonomy` или отдельный пакет; использует ROS2 actions поверх `nav_to_pose` и пользовательских действий.

## Failsafe и приоритеты команд (композиция C)

- **Independent failsafe (STM32):** STM32 отвечает за немедленный cut-off моторов при потере CRSF и при истечении SPI watchdog (`SPI_LINK_TIMEOUT_MS`). SBC может упасть полностью — это допустимо.
- **Twist arbitration (SBC):** `twist_mux` строит приоритетную лестницу, но это уже вторичный уровень. Манипулятор работает в своей цепи `ros2_control` и не пересекается с drive twist'ом.
- **Arm/Disarm:** owner — STM32 (по CRSF-каналам). SBC может только запросить disarm (`/biba/arm` service → `DISARM` cmd), но не может принудительно армить, если CRSF в failsafe.

## Куда смотреть дальше

- [stm32_architecture.md](stm32_architecture.md) — STM32-сторона: SPI-протокол, режимы прошивки, контракт телеметрии.
- [ros2_stack.md](ros2_stack.md) — ROS2-стек композиции C: пакеты, контейнеры, топики.
- [deployment.md](deployment.md) — развёртывание per-композиция.
- [wiring.md](wiring.md) — пины и подключение.
- [plans/2026-04-28-sbc-architecture-redesign-design.md](plans/2026-04-28-sbc-architecture-redesign-design.md) — исходный design-doc с историей решений и списком эпиков.
