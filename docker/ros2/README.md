# ROS2-стек композиции C (Pi + STM32)

Minimal-профиль docker-compose, поднимаемый на Pi Zero 2W (или старше) поверх legacy `biba-controller` или вместо него.

## Сервисы

| Сервис                 | Команда                                                          | Что делает                                                |
| ---------------------- | ---------------------------------------------------------------- | --------------------------------------------------------- |
| `zenoh-router`         | `ros2 run rmw_zenoh_cpp rmw_zenohd`                              | Bootstrap discovery для всех ROS2-нод этого Pi            |
| `biba-control`         | `ros2 launch biba_bringup control.launch.py`                     | `controller_manager` + `diff_drive_controller` поверх `biba_hardware_stm32` SystemInterface; единственный владелец `/dev/spidev0.0`. Также поднимает `robot_state_publisher`. |
| `twist-mux`            | `ros2 launch biba_bringup twist_mux.launch.py`                   | Арбитраж `cmd_vel_*` источников → `/cmd_vel` (см. [config](../../ros2_ws/src/biba_bringup/config/twist_mux.yaml)) |

Python-узел `biba_stm32_bridge` исключён из композиции C: SPI теперь принадлежит C++-плагину `biba_hardware_stm32::BibaStm32SystemHardware`, и `diff_drive_controller` пишет в него напрямую через `velocity` command interface.

Все сервисы используют один и тот же образ `ghcr.io/goodworkrinkz/biba/biba-ros2:<tag>` ([Dockerfile](Dockerfile)), который собирается поверх `biba-ros2-control` ([../base/](../base/)) и содержит сборку `ros2_ws/` через `colcon`.

## Quick start

```bash
cd docker/ros2
cp .env.example .env             # подкрутить теги и параметры

# Вариант A: pull готового образа из GHCR (после первого CI-прогона G-Build-ROS2-Stack)
docker compose pull

# Вариант B: собрать локально (медленно на Pi Zero 2W; обычно делается на dev-машине через buildx + arm64)
docker compose build

docker compose up -d
docker compose logs -f biba-control
```

## Топики и сервисы

- `/cmd_vel` (sub, `geometry_msgs/Twist`) — вход `diff_drive_controller` (выход `twist-mux`)
- `cmd_vel_teleop`, `cmd_vel_uwb`, `cmd_vel_nav` — приоритезированные входы `twist-mux` (см. [biba_bringup/config/twist_mux.yaml](../../ros2_ws/src/biba_bringup/config/twist_mux.yaml))
- `/biba/estop` (sub, `std_msgs/Bool`) — `twist-mux` lock; `true` блокирует все twist-входы
- `/odom` (pub, `nav_msgs/Odometry`) — open-loop одометрия от `diff_drive_controller`
- `/joint_states` (pub, `sensor_msgs/JointState`) — состояние колёсных joint'ов
- `/tf` — `odom → base_link → wheels/imu/stm32` (RSP + diff_drive)
- `/controller_manager/*` (srv) — стандартные services управления контроллерами

## Переменные окружения

См. [`.env.example`](.env.example). Ключевые:

- `BIBA_ROS2_IMAGE_TAG` — тег сервисного образа (`latest` / `dev` / `<sha>`)
- `ROS_DOMAIN_ID`, `ROS_AUTOMATIC_DISCOVERY_RANGE` — настройка Zenoh

Геометрия дифф-привода (`wheel_separation`, `wheel_radius`, `max_wheel_speed`) теперь живёт в [`biba_description/urdf/biba.urdf.xacro`](../../ros2_ws/src/biba_description/urdf/biba.urdf.xacro) и [`biba_bringup/config/diff_drive_controller.yaml`](../../ros2_ws/src/biba_bringup/config/diff_drive_controller.yaml). Калибровать там, не через env.

## Совместимость с legacy-стеком

Этот compose НЕ запускает `biba-controller` legacy (`docker/legacy-pi/`). На текущем этапе они взаимоисключающие — оба претендуют на SPI/GPIO. Композиция C, при которой один Pi одновременно гоняет legacy-RC и ROS2, описана в [`docs/system_architecture.md`](../../docs/system_architecture.md) и реализуется отдельным эпиком (split SPI владельца).

Дизайн: [`docs/plans/2026-04-28-sbc-architecture-redesign-design.md`](../../docs/plans/2026-04-28-sbc-architecture-redesign-design.md).
