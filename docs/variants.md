# Hardware Variants Matrix

Canonical source of hardware variant readiness across BiBa platforms.

Имя таргета прошивки кодирует три правых колонки:
`<MCU>_<MOTOR>_<DRIVER>_<LINK>` — см.
`docs/adr/0002-target-naming-and-vesc.md`.

| platform | board | motor_type | driver_type | link | optional_modules | status | implementation_link |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Pi Zero 2W | Raspberry Pi Zero 2W | brushed DC | BTS7960 (dual module) | direct PWM (GPIO) | ADS1115, Daly BMS BLE/UART, IMU | ready | [Pi-only stack](../docker/legacy-pi/docker-compose.yml) |
| RP2040 | YD RP2040 / RPi Pico-class | brushed DC | BTS7960 (dual module) | direct PWM | IMU, current sense | WIP | [RP2040 target](../firmware/targets/RP2040_DC_BTS7960_PWM/target.md) |
| RP2040 (BLDC) | YD RP2040 / RPi Pico-class | BLDC (paired) | ODrive Pro/S1/Micro | CAN 250k, CANSimple 11-bit (MCP2515+TJA1050 SPI→CAN) | IMU | designed (ADR-0001) | [RP2040_BLDC_ODRIVE_CAN](../firmware/targets/RP2040_BLDC_ODRIVE_CAN/target.md) |
| RP2040 (BLDC) | YD RP2040 / RPi Pico-class | BLDC (paired) | ODrive Pro/S1/Micro | UART1 ASCII 115200 (GP4/GP5) | IMU | designed (ADR-0001), предпочтительный линк | [RP2040_BLDC_ODRIVE_UART](../firmware/targets/RP2040_BLDC_ODRIVE_UART/target.md) |
| RP2040 (BLDC) | YD RP2040 / RPi Pico-class | BLDC (paired) | Flipsky dual FSESC (VESC ×2) | CAN 500k, 29-bit ext ID (MCP2515+TJA1050 SPI→CAN) | IMU | designed (ADR-0002) | [RP2040_BLDC_VESC_CAN](../firmware/targets/RP2040_BLDC_VESC_CAN/target.md) |
