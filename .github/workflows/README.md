# GitHub Actions Workflows

## Naming

- `G-` — global build workflows on GitHub-hosted runners

## Workflows

- `G-Build-Controller-Image.yml` — lint, pytest, build and optional push of the arm64 controller image to GHCR
- `G-Build-All.yml` — top-level workflow that triggers the controller image build and reports final pipeline status

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
