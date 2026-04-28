# ROS2-стек композиции C (Pi + STM32)

> **Статус:** в разработке. Дизайн зафиксирован в
> [docs/plans/2026-04-28-sbc-architecture-redesign-design.md](../../docs/plans/2026-04-28-sbc-architecture-redesign-design.md).

Когда стек будет реализован, здесь будут лежать `docker-compose.yaml`, конфиги Zenoh router'а и launch-обёртки для контейнеров `biba-stm32-bridge`, `robot-state-publisher`, `ros2-control` и `twist-mux`.

Реальные исходники узлов будут жить в `ros2_ws/src/`.
