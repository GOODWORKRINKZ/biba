# ROS2-стек композиции C (Pi + STM32)

> Статус: **в разработке**. Этот файл фиксирует целевую структуру ROS2-стека композиции C; реализация пакетов и контейнеров вынесена в отдельные планы. Канонический контекст — [system_architecture.md](system_architecture.md) и исходный [design-doc](plans/2026-04-28-sbc-architecture-redesign-design.md).

## Пакеты `ros2_ws/src/`

Целевые пакеты (создаются в момент реализации, в репозитории пока отсутствуют):

| Пакет                  | Язык     | Роль                                                                  |
| ---------------------- | -------- | --------------------------------------------------------------------- |
| `biba_description`     | xacro    | URDF/xacro дифф-привода BiBa (геометрия, joints, TF-tree)             |
| `biba_msgs`            | msg      | кастомные сообщения: `CrsfStatus`, `Stm32Telemetry`, `MotorAudio`, … |
| `biba_stm32_bridge`    | Python   | SPI ↔ ROS2 bridge поверх `biba-controller/stm32_link/`                |
| `biba_hardware_stm32`  | C++      | `ros2_control` `SystemInterface`, использует bridge как backend       |
| `biba_bringup`         | launch   | launch-файлы и конфиги controller_manager / twist_mux / TF            |

Hook-points (пустые директории-плейсхолдеры под будущие пакеты):

- `biba_manipulator` — пакет манипулятора (ros2_control hardware).
- `biba_uwb_follow` — follow-the-tag через BU4.
- `biba_remote_bridge` — Zenoh / WebRTC / VPN bridge для управления через интернет.
- `biba_camera` — FPV-stream и опциональный ML inference.
- `biba_autonomy` — SLAM / Nav2 / waypoints / mission scripting.

## Контейнеры (`docker/ros2/`)

Один контейнер на ROS2-узел или тесно связанную группу. RMW-транспорт — Zenoh (`rmw_zenoh_cpp`). Базовые образы строятся в `docker/base/`, сервисные — поверх них и публикуются в GHCR с тегом `<service>-<distro>-<branch>`.

### Профиль minimal (включая Pi Zero 2W)

| Контейнер              | Узел / роль                                                    |
| ---------------------- | -------------------------------------------------------------- |
| `zenoh-router`         | Zenoh маршрутизация + точка для облачного bridge               |
| `robot-state-publisher`| URDF → TF из `biba_description`                                |
| `biba-stm32-bridge`    | `biba_stm32_bridge`: SPI ↔ ROS2-топики                         |
| `ros2-control`         | controller_manager + `diff_drive_controller` + `joint_state_broadcaster`; hardware = `biba_hardware_stm32` |
| `twist-mux`            | приоритизация источников `cmd_vel`: CRSF → teleop → autonomy   |

### Профиль full (Pi 4/5+)

Опционально добавляются `biba-camera`, `biba-autonomy`, `biba-manipulator`, `biba-uwb-follow`, `biba-remote-bridge`, `foxglove-bridge`. Профили реализуются через docker-compose `profiles:` или через override-файлы — окончательный механизм выбирается на этапе реализации.

## Контракт SPI ↔ ROS2 (предварительный)

Узел `biba_stm32_bridge` — единственный, кто разговаривает с STM32. Полный список топиков и сервисов — в [system_architecture.md](system_architecture.md#контракт-biba_stm32_bridge--stm32). Здесь — кратко:

- Публикация: `/joint_states`, `/battery_state`, `/imu/data_raw`, `/biba/crsf/status`, `/biba/stm32/telemetry`.
- Подписка: `/cmd_vel`, `/biba/arm` (service), `/biba/motor_audio`.

## Что из текущего runtime переезжает сюда

| Функция текущего `biba-controller/`        | Куда переезжает в композиции C                |
| ------------------------------------------ | ---------------------------------------------- |
| CRSF UART, mixer, ramping, current-control | STM32 (firmware `companion`)                   |
| Drive (PWM → BTS7960)                      | STM32                                          |
| BMS-poller                                 | `biba_stm32_bridge` или отдельный ROS2-узел    |
| Voice runtime                              | новый узел `biba_voice` (отдельный план)       |
| Web UI                                     | `biba-controller` рядом с ROS2 на время миграции, далее — Foxglove или кастомный ROS2-узел |

## Failsafe в ROS2-стеке

- Hardware-failsafe полностью на STM32: cut-off моторов при потере CRSF и истечении SPI watchdog. SBC может упасть — это допустимо.
- ROS2-уровень — только вторичная арбитрация через `twist_mux`. Подробнее: [system_architecture.md](system_architecture.md#failsafe-и-приоритеты-команд-композиция-c).

## Как добавлять новый пакет

Эта секция будет дополнена при реализации первого ROS2-пакета. До тех пор смотреть `rob_box_project` как референс шаблона контейнеризации и сборки.

## Связанные документы

- [system_architecture.md](system_architecture.md) — обзор всех композиций.
- [stm32_architecture.md](stm32_architecture.md) — STM32-сторона SPI-контракта.
- [deployment.md](deployment.md) — развёртывание per-композиция.
- [plans/2026-04-28-sbc-architecture-redesign-design.md](plans/2026-04-28-sbc-architecture-redesign-design.md) — исходный design-doc.
