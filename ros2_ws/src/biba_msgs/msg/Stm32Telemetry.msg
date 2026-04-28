# Raw SPI telemetry snapshot from the STM32 add-on for diagnostics.
#
# Final field set is locked together with the SPI protocol implementation;
# this skeleton exposes a minimal subset that is already known.
std_msgs/Header header
uint32 firmware_revision
uint16 spi_link_uptime_ms
uint8 mode            # 0 = standalone, 1 = companion, 2 = combined
uint8 flags           # bitfield: armed, failsafe, motor_fault, …
float32 vbat_volts
float32 left_current_amps
float32 right_current_amps
float32 mcu_temp_celsius
