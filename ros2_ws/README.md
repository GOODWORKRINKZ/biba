# ros2_ws — рабочее пространство ROS2-стека композиции C

> Статус: **skeleton.** Пакеты содержат каркас (`package.xml`, `CMakeLists.txt` / `setup.py`), но без логики. Реализация ведётся отдельными планами. Канонический контекст — [docs/ros2_stack.md](../docs/ros2_stack.md) и [docs/system_architecture.md](../docs/system_architecture.md).

## Состав

Основные пакеты в [`src/`](src/):

| Пакет                  | Тип сборки    | Роль                                                                  |
| ---------------------- | ------------- | --------------------------------------------------------------------- |
| `biba_description`     | `ament_cmake` | URDF/xacro дифф-привода BiBa                                          |
| `biba_msgs`            | `ament_cmake` (`rosidl`) | Кастомные сообщения `CrsfStatus`, `Stm32Telemetry`, `MotorAudio` |
| `biba_stm32_bridge`    | `ament_python` | SPI ↔ ROS2 bridge поверх `biba-controller/stm32_link/`                |
| `biba_hardware_stm32`  | `ament_cmake` (C++) | `ros2_control` `SystemInterface` поверх bridge'а                  |
| `biba_bringup`         | `ament_cmake` | launch-файлы и конфиги controller_manager / twist_mux / TF            |

Hook-points (директории-плейсхолдеры с `COLCON_IGNORE`, чтобы colcon их пропускал):

- `biba_manipulator/` — будущий пакет манипулятора.
- `biba_uwb_follow/` — follow-the-tag через BU4.
- `biba_remote_bridge/` — Zenoh / WebRTC / VPN bridge.
- `biba_camera/` — FPV-stream и опциональный ML inference.
- `biba_autonomy/` — SLAM / Nav2 / waypoints / mission scripting.

## Сборка

Сборка предполагается внутри ROS2-окружения (Humble). На текущем этапе ни один из core-пакетов не несёт рабочей логики, так что `colcon build` собирает только структурные артефакты (msg-генерация, пустые launch-каталоги).

```bash
source /opt/ros/humble/setup.bash
cd ros2_ws
colcon build --symlink-install
source install/setup.bash
```

CI на этом этапе не запускает `colcon build`; smoke-тесты структуры лежат в [tests/test_ros2_ws_skeleton.py](../tests/test_ros2_ws_skeleton.py).

## Что дальше

Каждый core-пакет наполняется по отдельному implementation-plan'у согласно эпикам из [design-doc](../docs/plans/2026-04-28-sbc-architecture-redesign-design.md).
