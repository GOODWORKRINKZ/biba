// Copyright 2026 BiBa maintainers. MIT license.
//
// C++ port of biba-controller/stm32_link/client.py: encodes a request,
// performs one fixed-size SPI exchange via ISpiTransport, decodes the
// reply, validates CRC + sync + version. Pure logic — no rclcpp.
#ifndef BIBA_HARDWARE_STM32__STM32_LINK_HPP_
#define BIBA_HARDWARE_STM32__STM32_LINK_HPP_

#include <cstdint>
#include <memory>

#include "biba_hardware_stm32/spi_transport.hpp"

extern "C" {
#include "biba_proto.h"
}

namespace biba_hardware_stm32
{

struct Setpoint
{
  // Normalised wheel commands in [-1.0, 1.0]. Converted to int16_t Q15
  // before transmission to mirror biba_proto wire format.
  double left = 0.0;
  double right = 0.0;
};

struct Telemetry
{
  // Echoed setpoints (-1..1).
  double setpoint_left = 0.0;
  double setpoint_right = 0.0;
  // Wheel currents in amperes.
  double current_left_a = 0.0;
  double current_right_a = 0.0;
  // Battery voltage in volts.
  double vbat_v = 0.0;
  double rail_12v_v = 0.0;
  // Gyro / accel.
  double gyro_x_dps = 0.0;
  double gyro_y_dps = 0.0;
  double gyro_z_dps = 0.0;
  double accel_x_g = 0.0;
  double accel_y_g = 0.0;
  double accel_z_g = 0.0;
  // CRSF link.
  uint8_t crsf_rssi = 0;
  uint8_t crsf_link_quality = 0;
  int8_t crsf_snr_db = 0;
  // Status flags (BIBA_PROTO_FLAG_*).
  uint8_t flags = 0;
  uint32_t uptime_ms = 0;
};

class Stm32Link
{
public:
  // Takes ownership of the transport. Tests inject a fake; production
  // wires SpiTransportLinux.
  explicit Stm32Link(std::unique_ptr<ISpiTransport> transport);

  bool open(const SpiConfig & cfg);
  void close();
  bool is_open() const;

  // Send PING, parse reply.
  bool ping(Telemetry & out);
  // Send normalised wheel setpoints, parse reply telemetry.
  bool set_setpoint(const Setpoint & sp, Telemetry & out);
  // Send ARM (true) / DISARM (false), parse reply.
  bool arm(bool armed, Telemetry & out);

private:
  bool exchange_(uint8_t cmd, const uint8_t * payload, size_t payload_len, Telemetry & out);
  static void parse_(const biba_proto_frame_t & frame, Telemetry & out);

  std::unique_ptr<ISpiTransport> transport_;
  uint8_t seq_ = 0;
};

}  // namespace biba_hardware_stm32

#endif  // BIBA_HARDWARE_STM32__STM32_LINK_HPP_
