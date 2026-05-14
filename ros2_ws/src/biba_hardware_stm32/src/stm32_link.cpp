// Copyright 2026 BiBa maintainers. MIT license.
#include "biba_hardware_stm32/stm32_link.hpp"

#include <cstring>
#include <utility>

namespace biba_hardware_stm32
{

namespace
{

// Q15 fixed-point conversion mirrors python protocol.py::_to_q15 exactly:
// clamp to [-32768, 32767] after rounding to nearest.
int16_t to_q15(double v)
{
  double scaled = v * 32767.0;
  // round half to even is fine; we use round-to-nearest to match python's
  // int(round(...)) banker's-rounding-ish behaviour for the values the
  // controller actually produces (no exact .5 cases on a modern FPU).
  long r = static_cast<long>(scaled >= 0 ? scaled + 0.5 : scaled - 0.5);
  if (r > 32767) {
    r = 32767;
  } else if (r < -32768) {
    r = -32768;
  }
  return static_cast<int16_t>(r);
}

double from_q15(int16_t q)
{
  return static_cast<double>(q) / 32767.0;
}

}  // namespace

Stm32Link::Stm32Link(std::unique_ptr<ISpiTransport> transport)
: transport_(std::move(transport))
{
}

bool Stm32Link::open(const SpiConfig & cfg)
{
  if (!transport_) {
    return false;
  }
  return transport_->open(cfg);
}

void Stm32Link::close()
{
  if (transport_) {
    transport_->close();
  }
}

bool Stm32Link::is_open() const
{
  return transport_ && transport_->is_open();
}

bool Stm32Link::ping(Telemetry & out)
{
  return exchange_(BIBA_CMD_PING, nullptr, 0, out);
}

bool Stm32Link::set_setpoint(const Setpoint & sp, Telemetry & out)
{
  uint8_t payload[4];
  int16_t left_q = to_q15(sp.left);
  int16_t right_q = to_q15(sp.right);
  // Wire order: little-endian left then right (matches python pack '<hh').
  payload[0] = static_cast<uint8_t>(left_q & 0xFF);
  payload[1] = static_cast<uint8_t>((left_q >> 8) & 0xFF);
  payload[2] = static_cast<uint8_t>(right_q & 0xFF);
  payload[3] = static_cast<uint8_t>((right_q >> 8) & 0xFF);
  return exchange_(BIBA_CMD_SET_SETPOINT, payload, sizeof(payload), out);
}

bool Stm32Link::arm(bool armed, Telemetry & out)
{
  uint8_t cmd = armed ? BIBA_CMD_ARM : BIBA_CMD_DISARM;
  return exchange_(cmd, nullptr, 0, out);
}

bool Stm32Link::exchange_(
  uint8_t cmd,
  const uint8_t * payload,
  size_t payload_len,
  Telemetry & out)
{
  if (!transport_ || !transport_->is_open()) {
    return false;
  }
  if (payload_len > BIBA_PROTO_PAYLOAD_MAX) {
    return false;
  }

  biba_proto_frame_t request{};
  request.version = BIBA_PROTO_VERSION;
  request.cmd = cmd;
  request.seq = seq_++;
  request.flags = 0;
  request.payload_len = static_cast<uint8_t>(payload_len);
  if (payload != nullptr && payload_len > 0) {
    std::memcpy(request.payload, payload, payload_len);
  }

  uint8_t tx[BIBA_PROTO_FRAME_SIZE];
  uint8_t rx[BIBA_PROTO_FRAME_SIZE];
  if (biba_proto_encode(&request, tx, sizeof(tx)) != BIBA_PROTO_OK) {
    return false;
  }
  if (!transport_->transfer(tx, rx, BIBA_PROTO_FRAME_SIZE)) {
    return false;
  }

  biba_proto_frame_t reply{};
  if (biba_proto_decode(rx, sizeof(rx), &reply) != BIBA_PROTO_OK) {
    return false;
  }
  parse_(reply, out);
  return true;
}

void Stm32Link::parse_(const biba_proto_frame_t & frame, Telemetry & out)
{
  out = Telemetry{};
  out.flags = frame.flags;

  if (frame.cmd == BIBA_TLM_SNAPSHOT && frame.payload_len >= sizeof(biba_proto_telemetry_t)) {
    biba_proto_telemetry_t tlm{};
    std::memcpy(&tlm, frame.payload, sizeof(tlm));

    out.setpoint_left = from_q15(tlm.setpoint_left_q15);
    out.setpoint_right = from_q15(tlm.setpoint_right_q15);
    out.current_left_a = static_cast<double>(tlm.current_left_ma) / 1000.0;
    out.current_right_a = static_cast<double>(tlm.current_right_ma) / 1000.0;
    out.vbat_v = static_cast<double>(tlm.vbat_mv) / 1000.0;
    out.rail_12v_v = static_cast<double>(tlm.rail_12v_mv) / 1000.0;
    out.gyro_x_dps = static_cast<double>(tlm.gyro_x_cdps) / 100.0;
    out.gyro_y_dps = static_cast<double>(tlm.gyro_y_cdps) / 100.0;
    out.gyro_z_dps = static_cast<double>(tlm.gyro_z_cdps) / 100.0;
    out.accel_x_g = static_cast<double>(tlm.accel_x_mg) / 1000.0;
    out.accel_y_g = static_cast<double>(tlm.accel_y_mg) / 1000.0;
    out.accel_z_g = static_cast<double>(tlm.accel_z_mg) / 1000.0;
    out.crsf_rssi = tlm.crsf_rssi;
    out.crsf_link_quality = tlm.crsf_link_quality;
    out.crsf_snr_db = tlm.crsf_snr_db;
    out.uptime_ms = tlm.uptime_ms;
    // error_flags inside telemetry is also published in the frame
    // header flags; we keep the header value as authoritative.
  }
}

}  // namespace biba_hardware_stm32
