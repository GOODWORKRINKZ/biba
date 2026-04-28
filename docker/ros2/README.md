# ROS2-стек композиции C (Pi + STM32)

Minimal-профиль docker-compose, поднимаемый на Pi Zero 2W (или старше) поверх legacy `biba-controller` или вместо него.

## Сервисы

| Сервис                 | Команда                                                          | Что делает                                                |
| ---------------------- | ---------------------------------------------------------------- | --------------------------------------------------------- |
| `zenoh-router`         | `ros2 run rmw_zenoh_cpp rmw_zenohd`                              | Bootstrap discovery для всех ROS2-нод этого Pi            |
| `biba-stm32-bridge`    | `ros2 run biba_stm32_bridge biba_stm32_bridge_node`              | SPI ↔ ROS2: `/cmd_vel` → STM32, telemetry → ROS2-топики   |
| `robot-state-publisher`| `ros2 launch biba_description robot_state_publisher.launch.py`   | Публикует TF из `biba_description/urdf/biba.urdf.xacro`   |

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
docker compose logs -f biba-stm32-bridge
```

## Топики и сервисы

- `/cmd_vel` (sub, `geometry_msgs/Twist`) — вход управления
- `/biba/stm32/telemetry` (pub, `biba_msgs/Stm32Telemetry`)
- `/biba/crsf/status` (pub, `biba_msgs/CrsfStatus`)
- `/biba/arm` (srv, `std_srvs/SetBool`)

## Переменные окружения

См. [`.env.example`](.env.example). Ключевые:

- `BIBA_ROS2_IMAGE_TAG` — тег сервисного образа (`latest` / `dev` / `<sha>`)
- `ROS_DOMAIN_ID`, `ROS_AUTOMATIC_DISCOVERY_RANGE` — настройка Zenoh
- `BIBA_WHEEL_SEPARATION`, `BIBA_MAX_WHEEL_SPEED` — геометрия дифф-привода (плейсхолдеры; синхронизировать с `biba_description/urdf/biba.urdf.xacro` после калибровки)

## Совместимость с legacy-стеком

Этот compose НЕ запускает `biba-controller` legacy (`docker/legacy-pi/`). На текущем этапе они взаимоисключающие — оба претендуют на SPI/GPIO. Композиция C, при которой один Pi одновременно гоняет legacy-RC и ROS2, описана в [`docs/system_architecture.md`](../../docs/system_architecture.md) и реализуется отдельным эпиком (split SPI владельца).

Дизайн: [`docs/plans/2026-04-28-sbc-architecture-redesign-design.md`](../../docs/plans/2026-04-28-sbc-architecture-redesign-design.md).
