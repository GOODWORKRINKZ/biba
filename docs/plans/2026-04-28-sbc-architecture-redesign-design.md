# SBC architecture redesign: три композиции, ROS2-стек и hook-points под новые задачи

> Дизайн-документ. Реализация выносится в отдельные планы (`writing-plans`).

## Контекст

Текущее состояние проекта на момент дизайна:

- `biba-controller/` — Python-runtime, который умеет всё: CRSF UART, mixer,
  ramping, current-control, BTS7960 PWM, BMS, voice, web. Запускается одним
  `docker-compose.yml` в корне репозитория.
- `firmware/` — PlatformIO-проект для STM32F103 с режимами
  `standalone` / `companion` / `combined`. Прошивка может работать
  самостоятельно (CRSF → PWM → BTS7960) или быть SPI-slave'ом для SBC.
- `biba-controller/stm32_link/` — Python-каркас SPI-клиента к STM32,
  включается флагом `STM32_LINK_ENABLED=1`. В `main.py` реальной интеграции
  пока нет.

Новые входные требования (от пользователя):

- Возможность установки манипулятора.
- Подключение к стеку ROS2.
- Управление через интернет.
- Внешние сенсоры: LiDAR, ToF, дополнительные IMU.
- Камера / FPV-stream / ML-inference.
- Локальная автономия (SLAM, waypoints).
- UWB-модуль (BU4) — режим follow-the-tag.
- Mission scripting / scenario engine.

Архитектура должна **допускать** все эти направления, но **не реализовывать**
их в этой итерации. Цель — чёткие точки расширения и чистое разделение
ответственности между SBC и STM32 в трёх возможных композициях робота.

## Три композиции робота

Проект поддерживает три аппаратные композиции одновременно. Это не три
разных продукта, а три совместимых конфигурации одного и того же
репозитория.

| Композиция            | Железо                       | Кто читает CRSF | Кто крутит PWM | High-level стек        |
| --------------------- | ---------------------------- | --------------- | -------------- | ---------------------- |
| **A. Pi-only**        | Pi Zero 2W                   | Pi (UART)       | Pi (BTS7960)   | сегодняшний `biba-controller/` |
| **B. STM32-only**     | STM32F103, без SBC           | STM32 (USART3)  | STM32          | нет                    |
| **C. Pi + STM32**     | SBC + STM32F103              | STM32 (USART3)  | STM32          | новый ROS2-стек        |

Правило маршрутизации CRSF (фиксируется): **где есть STM32, туда и идёт
CRSF UART**. SBC получает каналы / RSSI / LQ / failsafe-флаг только через
SPI-телеметрию от STM32. Pi-only композиция читает CRSF сама — как сегодня.

Композиция C (Pi+STM32) на Pi Zero 2W поддерживается только в «minimal»
профиле (см. ниже). Для тяжёлых узлов (SLAM, видео, WebRTC, ML) требуется
Pi 4/5 или Orange Pi/Radxa — это явно фиксируется в документации.

## Принципиальное архитектурное решение

Не превращать существующий `biba-controller/` в ROS2-стек и не ломать
композицию A. Вместо этого ввести **второй высокоуровневый стек** для
композиции C, основанный на ROS2, и держать оба стека в репозитории
рядом друг с другом.

Причины:

- Композиция A работает и проверена на реальном железе. Любая
  переделка `biba-controller/` под ROS2 — это риск регрессии без
  компенсирующей пользы для тех, у кого STM32 нет.
- Pi Zero 2W (1 ГБ RAM, 4×Cortex-A53) тянет ROS2 + voice + web с трудом.
  Делать ROS2 единственным путём — значит резать Zero 2W.
- ROS2 даёт стандартные интерфейсы (`/cmd_vel`, `/odom`,
  `/battery_state`, `/joint_states`, TF, URDF) — это ровно то, во что
  естественно ложатся все новые направления (Nav2, манипулятор,
  UWB-follower, internet-bridge, ML, Foxglove).
- В композиции C тяжёлая низкоуровневая работа уже снята с SBC и живёт
  на STM32, поэтому SBC-сторона естественно становится «оркестратором
  узлов», а ROS2 — это и есть оркестратор узлов.

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
│   ├── system_architecture.md      # NEW: единый обзор всех композиций
│   ├── stm32_architecture.md       # как сейчас (с обновлёнными ссылками)
│   ├── ros2_stack.md               # NEW: пакеты, топики, launch
│   ├── deployment.md               # дополнен per-композиция
│   └── wiring.md                   # обновить заголовки секций по композициям
└── README.md                       # переписать как архитектурный hub
```

Текущий `docker-compose.yml` в корне переезжает в `docker/legacy-pi/`. На его
месте появляется тонкий wrapper или ссылка из README на оба варианта.

## ROS2-стек: контейнеры и узлы

Шаблон контейнеризации копируется с проекта `rob_box_project`:

- Один контейнер на ROS2-узел (или тесно связанную группу).
- Zenoh router (`eclipse/zenoh`) как RMW-транспорт; ROS2 поверх
  `rmw_zenoh_cpp`. Это даёт естественный мост в облако и в internet-bridge.
- Базовые образы строятся отдельно (`docker/base/Dockerfile.ros2-zenoh`,
  `Dockerfile.ros2-control` и т.д.), сервисные — поверх них. Образы
  публикуются в GHCR с тегом `<service>-<distro>-<branch>`.

Состав композиции C (Pi+STM32), профиль **minimal** (доступен и на
Pi Zero 2W при ужатой воле):

| Контейнер              | Узел / роль                                                   |
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

Профили реализуются через docker-compose `profiles:` или через отдельные
override-файлы (`docker-compose.yml` + `docker-compose.minimal.yml` /
`docker-compose.full.yml`) — выбор делается на этапе реализации.

## Контракт `biba_stm32_bridge` ↔ STM32

Узел `biba_stm32_bridge` — единственный, кто разговаривает с STM32 по SPI.
Он повторно использует `biba-controller/stm32_link/protocol.py` и
`stm32_link/client.py` без копирования (либо ставится как локальная
Python-зависимость, либо подмонтирован в контейнер read-only).

Публикуемые ROS2-топики (предварительный список, доточить в реализации):

| Топик                          | Тип сообщения                          | Источник                              |
| ------------------------------ | -------------------------------------- | ------------------------------------- |
| `/joint_states`                | `sensor_msgs/JointState`               | echo setpoint + measured currents     |
| `/battery_state`               | `sensor_msgs/BatteryState`             | агрегация из BMS (по-прежнему через Pi-side BMS poller) и из STM32 telemetry rail |
| `/imu/data_raw`                | `sensor_msgs/Imu`                      | gyro/accel из STM32 telemetry         |
| `/biba/crsf/status`            | `biba_msgs/CrsfStatus`                 | RSSI/LQ/SNR/failsafe-flag             |
| `/biba/stm32/telemetry`        | `biba_msgs/Stm32Telemetry`             | сырая SPI-snapshot для диагностики    |

Подписки (входы):

| Топик                          | Тип                                    | Действие                              |
| ------------------------------ | -------------------------------------- | ------------------------------------- |
| `/cmd_vel`                     | `geometry_msgs/Twist`                  | → `SET_SETPOINT` (через mixer)        |
| `/biba/arm` (service)          | `std_srvs/SetBool`                     | → `ARM` / `DISARM`                    |
| `/biba/motor_audio`            | `biba_msgs/MotorAudio`                 | → `SET_MOTOR_AUDIO` (если target умеет) |

Mixer twist→left/right остаётся в `biba_stm32_bridge` (или в
controller-side через `diff_drive_controller`, окончательное решение в
плане реализации).

## High-level задачи SBC по композициям

### A. Pi-only

Сегодняшний набор без изменений: CRSF, mixer, ramping, current-control,
BTS7960 PWM, BMS-poller, voice, web, system-stats. Документация явно
говорит, что новые направления (ROS2/манипулятор/UWB/интернет) в этой
композиции **не поддерживаются** — для них нужно перейти на композицию C.

### B. STM32-only

SBC отсутствует. Высокоуровневых задач нет вообще. Документируется как
минимальная сборка для людей без Pi: только драйв, телеметрия по CRSF
обратно оператору, motor-audio.

### C. Pi+STM32

Низкоуровневая часть полностью на STM32. На SBC — только high-level:

1. **Drive-bridge** — `biba_stm32_bridge` + `ros2_control`. MUST.
2. **Robot description** — URDF/TF через `robot_state_publisher`. MUST.
3. **Twist arbitration** — `twist_mux` с приоритетами CRSF > teleop > autonomy. MUST.
4. **BMS aggregation** — отдельный узел или часть bridge'а, публикует
   `/battery_state`. MUST (или MAY, если на STM32-target есть VBAT-sense
   и хватает её).
5. **Telemetry-out** — Zenoh router; внешний `foxglove_bridge` опционально.
6. **Voice runtime** — переезд из `biba-controller/buzzer/voice` в
   отдельный ROS2-узел `biba_voice` (вне scope этого дизайна, отдельный
   план). На время миграции — допустимо запускать `biba-controller`
   рядом с ROS2-стеком на одной Pi для voice, но это переходное решение.
7. **Web UI** — то же: остаётся в `biba-controller` до отдельной миграции.

Расширения (отдельные планы, отдельные дизайны):

- Манипулятор: `biba_manipulator` как `ros2_control` системой поверх
  USB/I2C servo-контроллера. Топики `/manipulator/joint_states` и
  `/manipulator/joint_trajectory_controller/...`.
- Internet remote control: `biba_remote_bridge` через Zenoh→облачный
  Zenoh-router (как в `rob_box_project`) и/или WebRTC для видео.
- Камера и ML: `biba_camera`, отдельный контейнер, требует Pi 4/5.
- Автономия: `biba_autonomy` (rtabmap или Nav2), требует Pi 4/5 и LiDAR.
- UWB-follower: `biba_uwb_follow`, отдельный контейнер; читает BU4 по
  USB/UART, публикует pose тага и/или прямо `cmd_vel` с низким
  приоритетом в `twist_mux`.
- Mission scripting: `biba_autonomy` или отдельный пакет; использует
  ROS2 actions поверх `nav_to_pose` и пользовательских действий.

## Failsafe и приоритеты команд (композиция C)

- **Independent failsafe (STM32):** STM32 отвечает за немедленный
  cut-off моторов при потере CRSF и при истечении SPI watchdog
  (`SPI_LINK_TIMEOUT_MS`). SBC может упасть полностью — это допустимо.
- **Twist arbitration (SBC):** `twist_mux` строит приоритетную лестницу,
  но это уже вторичный уровень. Манипулятор работает в своей цепи
  ros2_control и не пересекается с drive twist'ом.
- **Arm/Disarm:** owner — STM32 (по CRSF-каналам). SBC может только
  запросить disarm (`/biba/arm` service → `DISARM` cmd), но не может
  принудительно армить, если CRSF в failsafe.

## Документация: что и куда

| Файл                                | Действие                                                                 |
| ----------------------------------- | ------------------------------------------------------------------------ |
| `README.md`                         | Переписать как архитектурный hub с матрицей композиций A/B/C, краткий quick-start на каждую |
| `docs/system_architecture.md`       | NEW: расширенный обзор, UML-картинки/ASCII, описание интерфейсов SBC↔STM32, профили minimal/full, hook-points |
| `docs/stm32_architecture.md`        | Оставить, добавить cross-link на `system_architecture.md`; уточнить, что роль «standalone» = композиция B, «companion» = композиция C |
| `docs/ros2_stack.md`                | NEW: список ROS2-пакетов, описание контейнеров, перечень топиков/сервисов, схема Zenoh, инструкции по добавлению нового пакета |
| `docs/deployment.md`                | Расщепить на «Композиция A: Pi-only», «Композиция B: STM32-only», «Композиция C: Pi+STM32 с ROS2». Каждая со своим quick-start |
| `docs/wiring.md`                    | Добавить отметки, какие пины используются в каких композициях             |
| `docker-compose.yml` (корневой)     | Удалить или превратить в symlink/forwarder на `docker/legacy-pi/`         |

## Что не входит в этот дизайн

Следующие пункты упомянуты, но **не проектируются здесь** — для каждого
будет отдельный дизайн-документ при подходе к реализации:

- Внутреннее устройство `biba_manipulator` (выбор контроллера, протокол).
- Конкретный механизм internet-bridge (Zenoh-облако vs MQTT vs WebRTC vs VPN).
- Конкретный SLAM-стек (rtabmap vs cartographer vs Nav2-only).
- Миграция voice-runtime в ROS2.
- Миграция web-UI в ROS2 (Foxglove vs кастомное).
- Маршрут OTA-обновлений STM32 через SBC.
- Как именно переезжает `biba-controller/main.py` BMS-логика в ROS2-узел.

## Список задач (epic-уровень) для последующих планов

После принятия этого дизайна каждая из следующих задач превращается в
отдельный implementation plan через `writing-plans`:

1. **Документация-первого-шага** — переписать README, создать
   `system_architecture.md` и `ros2_stack.md` (заглушка-структура),
   обновить `stm32_architecture.md` и `deployment.md`. Перенос
   `docker-compose.yml` в `docker/legacy-pi/`.
2. **ROS2 base images** — `docker/base/Dockerfile.ros2-zenoh` и
   `Dockerfile.ros2-control` (можно сразу скопировать паттерн из
   `rob_box_project` и адаптировать).
3. **`biba_description`** — URDF/xacro для двухколёсного дифф-привода,
   robot_state_publisher launch.
4. **`biba_msgs`** — кастомные сообщения `CrsfStatus`, `Stm32Telemetry`,
   `MotorAudio`.
5. **`biba_stm32_bridge`** — Python ROS2-узел; реюз `stm32_link/`;
   публикация телеметрии, подписка на `/cmd_vel`, сервисы arm/disarm.
6. **`biba_hardware_stm32`** — `ros2_control` SystemInterface (C++),
   `diff_drive_controller` поверх него, controller_manager launch.
7. **`twist_mux`** — конфиг приоритетов, интеграция с bridge.
8. **`docker/ros2/docker-compose.yml`** — minimal-профиль, поднимается
   на Pi Zero 2W при наличии STM32.
9. **CI** — workflow для сборки ROS2-образов в GHCR.
10. **Bringup-скрипт композиции C** — аналог `scripts/setup/setup_node.sh`,
    но для ROS2-стека. Возможно — единый скрипт с флагом выбора композиции.

После пункта 10 база готова, и далее каждое из направлений
(манипулятор / UWB / внешние сенсоры / камера / автономия /
internet-bridge / mission scripting) становится отдельным дизайном и
отдельным пакетом в `ros2_ws/src/`.
