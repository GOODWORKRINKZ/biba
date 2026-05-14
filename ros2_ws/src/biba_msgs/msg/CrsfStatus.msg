# CRSF link status reported by STM32 over SPI telemetry.
#
# rssi_dbm is signed dBm (negative). link_quality is 0..100.
# failsafe is true when receiver lost the signal and entered failsafe.
std_msgs/Header header
int16 rssi_dbm
uint8 link_quality
int8 snr_db
bool failsafe
