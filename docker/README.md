# docker/

Этот каталог содержит compose-стеки и базовые образы для всех аппаратных композиций BiBa. См. [docs/system_architecture.md](../docs/system_architecture.md).

| Подкаталог | Композиция | Описание |
| --- | --- | --- |
| [`legacy-pi/`](legacy-pi/) | A. Pi-only | Текущий рабочий compose с `biba-controller` Python-runtime |
| [`ros2/`](ros2/) | C. Pi + STM32 | ROS2-стек (в разработке) |
| [`base/`](base/) | общий | Базовые Docker-образы (в разработке) |

Композиция B (STM32-only) не содержит SBC и compose-стека не имеет — её прошивка живёт в [`firmware/`](../firmware/).
