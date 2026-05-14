# Базовые Docker-образы

Общие base-образы для ROS2-стека BiBa. Собираются под `linux/arm64` (Pi Zero 2W / Pi 4 / Pi 5) и публикуются в GHCR. Используются как `FROM` в сервисных Dockerfile-ах из [`../ros2/`](../ros2/).

## Образы

| Образ                            | Dockerfile                                               | Состав                                                                           |
| -------------------------------- | -------------------------------------------------------- | -------------------------------------------------------------------------------- |
| `biba-ros2-zenoh:<tag>`          | [`Dockerfile.ros2-zenoh`](Dockerfile.ros2-zenoh)         | `ros:humble-ros-base` + `rmw_zenoh_cpp` + python3-pip + colcon                   |
| `biba-ros2-control:<tag>`        | [`Dockerfile.ros2-control`](Dockerfile.ros2-control)     | `biba-ros2-zenoh` + `ros2_control` + `diff_drive_controller` + `twist_mux` + xacro |

`biba-ros2-control` строится поверх `biba-ros2-zenoh` (FROM-аргумент `ROS2_ZENOH_IMAGE`/`ROS2_ZENOH_TAG`), поэтому в CI порядок: сначала zenoh, потом control.

## Теги

Резолвятся в [`G-Build-ROS2-Bases.yml`](../../.github/workflows/G-Build-ROS2-Bases.yml):

- `latest` — push в `main`
- `dev` — push в `develop`
- `test` — push в произвольную ветку
- `v*` — git tag
- `<sha>` — short commit SHA (всегда)

## Локальная сборка

```bash
# zenoh-база (без push, под текущую архитектуру)
docker build -f docker/base/Dockerfile.ros2-zenoh -t biba-ros2-zenoh:dev docker/base/

# ros2_control поверх локально собранного zenoh
docker build -f docker/base/Dockerfile.ros2-control \
    --build-arg ROS2_ZENOH_IMAGE=biba-ros2-zenoh \
    --build-arg ROS2_ZENOH_TAG=dev \
    -t biba-ros2-control:dev docker/base/
```

Дизайн-документ: [`docs/plans/2026-04-28-sbc-architecture-redesign-design.md`](../../docs/plans/2026-04-28-sbc-architecture-redesign-design.md).
