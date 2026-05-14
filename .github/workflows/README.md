# GitHub Actions Workflows

## Naming

- `G-` — global build workflows on GitHub-hosted runners

## Workflows

- `G-Build-Controller-Image.yml` — lint, pytest, build and optional push of the arm64 controller image to GHCR (композиции A и C)
- `G-Build-STM32F103.yml` — `pio test -e native_test` + матрица `pio run` по `target × mode` для прошивки STM32F103 (композиции B и C)
- `G-Build-ROS2-Bases.yml` — сборка и push в GHCR базовых ROS2-образов `biba-ros2-zenoh` и `biba-ros2-control` (используются в композиции C поверх ros2_ws/)
- `G-Build-ROS2-Stack.yml` — сборка и push сервисного образа `biba-ros2` (поверх `biba-ros2-control`, содержит colcon-сборку `ros2_ws/` и vendored `biba-controller/stm32_link/`)
- `G-Build-All.yml` — top-level workflow, который параллельно запускает controller-image, STM32-firmware, ROS2-base-images и ROS2-stack-image, и сводит финальный статус

Соответствие композициям робота:

| Композиция | Что собирается                                  | Workflow                              |
| ---------- | ----------------------------------------------- | ------------------------------------- |
| A. Pi-only | controller image                                | `G-Build-Controller-Image.yml`        |
| B. STM32-only | прошивка STM32F103 (env `standalone`)        | `G-Build-STM32F103.yml`               |
| C. Pi + STM32 | controller image + прошивка (env `companion`) | оба, через `G-Build-All.yml`        |

## Usage

Manual global build:

```bash
gh workflow run "G-Build-All.yml"
```

Manual build with custom tag:

```bash
gh workflow run "G-Build-All.yml" -f image_tag=staging
```

## Deployment model

The image is built and pushed on GitHub Actions runners. Raspberry Pi nodes are expected to run:

```bash
docker compose -f docker/legacy-pi/docker-compose.yml pull
docker compose -f docker/legacy-pi/docker-compose.yml up -d
```
