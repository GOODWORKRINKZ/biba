# Базовые Docker-образы

> **Статус:** в разработке. Дизайн зафиксирован в
> [docs/plans/2026-04-28-sbc-architecture-redesign-design.md](../../docs/plans/2026-04-28-sbc-architecture-redesign-design.md).

Здесь будут жить `Dockerfile.ros2-zenoh`, `Dockerfile.ros2-control` и прочие общие base-образы. Образы публикуются в GHCR и используются как `FROM` в сервисных Dockerfile-ах из [`../ros2/`](../ros2/).
