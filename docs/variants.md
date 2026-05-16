# Hardware Variants Matrix

Canonical source of hardware variant readiness across BiBa platforms.

| platform | board | motor_type | driver_type | optional_modules | status | implementation_link |
| --- | --- | --- | --- | --- | --- | --- |
| Pi Zero 2W | Raspberry Pi Zero 2W | brushed DC | BTS7960 (dual module) | ADS1115, Daly BMS BLE/UART, IMU | ready | [Pi-only stack](../docker/legacy-pi/docker-compose.yml) |
| RP2040 | YD RP2040 / RPi Pico-class | brushed DC | BTS7960 (dual module) | IMU, current sense | WIP | [RP2040 target](../firmware/targets/RPICO_RP2040/target.md) |
| STM32F103 | Blue Pill / BIBA_F103_REV_A | brushed DC | BTS7960 (dual module) | IMU, SPI companion link, current sense | planned | [BIBA_F103_REV_A target](../firmware/targets/BIBA_F103_REV_A/target.md) |
