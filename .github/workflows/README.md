# GitHub Actions Workflows

## Naming

- `G-` — global build workflows on GitHub-hosted runners

## Workflows

- `G-Build-Controller-Image.yml` — lint, pytest, build and optional push of the arm64 controller image to GHCR (композиции A и C)
- `G-Build-Firmware-Native-Tests.yml` — `pio test -e native_test` (портируемый код прошивки, без сборки под конкретный таргет)
- `G-Build-ROS2-Bases.yml` — сборка и push в GHCR базовых ROS2-образов `biba-ros2-zenoh` и `biba-ros2-control` (используются в композиции C поверх ros2_ws/)
- `G-Build-ROS2-Stack.yml` — сборка и push сервисного образа `biba-ros2` (поверх `biba-ros2-control`, содержит colcon-сборку `ros2_ws/` и vendored `biba-controller/stm32_link/`)
- `G-Build-All.yml` — top-level workflow, который параллельно запускает controller-image, firmware native tests, ROS2-base-images и ROS2-stack-image, и сводит финальный статус

Прошивка (RP2040-таргеты, см. `firmware/targets/README.md`) в CI не собирается под конкретный таргет — только `pio test -e native_test` для портируемого кода. Сборка `pio run -e <target>_<mode>` выполняется локально, см. `firmware/README.md`.

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
