# GitHub Actions Workflows

## Naming

- `G-` — global build workflows on GitHub-hosted runners

## Workflows

- `G-Build-Controller-Image.yml` — lint, pytest, build and optional push of the arm64 controller image to GHCR (композиции A и C)
- `G-Build-STM32F103.yml` — `pio test -e native_test` + матрица `pio run` по `target × mode` для прошивки STM32F103 (композиции B и C)
- `G-Build-All.yml` — top-level workflow, который параллельно запускает controller-image и STM32-firmware и сводит финальный статус

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
