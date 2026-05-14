// Copyright 2026 BiBa maintainers. MIT license.
//
// Unit tests for SpiTransport and Stm32Link using a fake transport.
// These tests do NOT depend on ros2_control — they exercise pure logic
// + the vendored biba_proto C library, so they run on any Linux dev box.
#include <gtest/gtest.h>

#include <cstring>
#include <memory>
#include <vector>

#include "biba_hardware_stm32/spi_transport.hpp"
#include "biba_hardware_stm32/stm32_link.hpp"

extern "C" {
#include "biba_proto.h"
}

using biba_hardware_stm32::ISpiTransport;
using biba_hardware_stm32::SpiConfig;
using biba_hardware_stm32::SpiTransportLinux;
using biba_hardware_stm32::Setpoint;
using biba_hardware_stm32::Stm32Link;
using biba_hardware_stm32::Telemetry;

namespace
{

class FakeTransport : public ISpiTransport
{
public:
  bool open(const SpiConfig & cfg) override
  {
    open_ = true;
    last_cfg_ = cfg;
    return true;
  }
  void close() override { open_ = false; }
  bool is_open() const override { return open_; }

  bool transfer(const uint8_t * tx, uint8_t * rx, size_t len) override
  {
    if (!open_) {
      return false;
    }
    last_tx_.assign(tx, tx + len);
    if (rx_to_send_.size() == len) {
      std::memcpy(rx, rx_to_send_.data(), len);
    } else {
      std::memset(rx, 0, len);
    }
    transfer_count_++;
    return true;
  }

  bool open_ = false;
  SpiConfig last_cfg_{};
  std::vector<uint8_t> last_tx_;
  std::vector<uint8_t> rx_to_send_;
  int transfer_count_ = 0;
};

// Build a valid telemetry reply frame the link should accept.
std::vector<uint8_t> make_telemetry_reply(uint8_t seq, uint8_t flags)
{
  biba_proto_telemetry_t tlm{};
  tlm.setpoint_left_q15 = 16384;     // ~0.5
  tlm.setpoint_right_q15 = -16384;
  tlm.current_left_ma = 1500;        // 1.5 A
  tlm.current_right_ma = -1500;
  tlm.vbat_mv = 25200;               // 25.2 V (6S nominal)
  tlm.rail_12v_mv = 12000;
  tlm.gyro_z_cdps = 9000;            // 90 dps
  tlm.crsf_rssi = 200;
  tlm.crsf_link_quality = 99;
  tlm.crsf_snr_db = 7;
  tlm.error_flags = flags;
  tlm.uptime_ms = 1234;

  std::vector<uint8_t> buffer(BIBA_PROTO_FRAME_SIZE, 0);
  EXPECT_EQ(
    biba_proto_encode_telemetry(seq, flags, &tlm, buffer.data(), buffer.size()),
    BIBA_PROTO_OK);
  return buffer;
}

}  // namespace

// -------------------------------------------------------------------- SpiTransport

TEST(SpiTransport, OpenNonExistentDeviceReturnsFalse)
{
  SpiTransportLinux t;
  SpiConfig cfg;
  cfg.device = "/tmp/nonexistent_biba_spidev_xyzzy";
  EXPECT_FALSE(t.open(cfg));
  EXPECT_FALSE(t.is_open());
}

TEST(SpiTransport, TransferOnUnopenedReturnsFalse)
{
  SpiTransportLinux t;
  uint8_t tx[1] = {0};
  uint8_t rx[1] = {0};
  EXPECT_FALSE(t.transfer(tx, rx, 1));
}

// -------------------------------------------------------------------- Stm32Link

TEST(Stm32Link, OpenWithoutTransportFails)
{
  Stm32Link link(nullptr);
  EXPECT_FALSE(link.open(SpiConfig{}));
  EXPECT_FALSE(link.is_open());
}

TEST(Stm32Link, OpenForwardsToTransport)
{
  auto fake = std::make_unique<FakeTransport>();
  auto * raw = fake.get();
  Stm32Link link(std::move(fake));
  SpiConfig cfg;
  cfg.device = "/dev/null";
  cfg.speed_hz = 500000;
  ASSERT_TRUE(link.open(cfg));
  EXPECT_TRUE(link.is_open());
  EXPECT_EQ(raw->last_cfg_.speed_hz, 500000u);
}

TEST(Stm32Link, PingTxFrameHasCorrectCommandSyncAndCrc)
{
  auto fake = std::make_unique<FakeTransport>();
  auto * raw = fake.get();
  raw->rx_to_send_ = make_telemetry_reply(0, 0);
  Stm32Link link(std::move(fake));
  ASSERT_TRUE(link.open(SpiConfig{}));

  Telemetry tlm;
  ASSERT_TRUE(link.ping(tlm));
  ASSERT_EQ(raw->last_tx_.size(), static_cast<size_t>(BIBA_PROTO_FRAME_SIZE));

  // Sync bytes.
  EXPECT_EQ(raw->last_tx_[0], BIBA_PROTO_SYNC_0);
  EXPECT_EQ(raw->last_tx_[1], BIBA_PROTO_SYNC_1);
  // Version + cmd.
  EXPECT_EQ(raw->last_tx_[2], BIBA_PROTO_VERSION);
  EXPECT_EQ(raw->last_tx_[3], static_cast<uint8_t>(BIBA_CMD_PING));
  // CRC validates round-trip via decode().
  biba_proto_frame_t decoded{};
  EXPECT_EQ(
    biba_proto_decode(raw->last_tx_.data(), raw->last_tx_.size(), &decoded),
    BIBA_PROTO_OK);
  EXPECT_EQ(decoded.cmd, BIBA_CMD_PING);
}

TEST(Stm32Link, SetpointEncodesQ15LittleEndian)
{
  auto fake = std::make_unique<FakeTransport>();
  auto * raw = fake.get();
  raw->rx_to_send_ = make_telemetry_reply(1, 0);
  Stm32Link link(std::move(fake));
  ASSERT_TRUE(link.open(SpiConfig{}));

  Telemetry tlm;
  Setpoint sp{0.5, -0.5};
  ASSERT_TRUE(link.set_setpoint(sp, tlm));

  biba_proto_frame_t decoded{};
  ASSERT_EQ(
    biba_proto_decode(raw->last_tx_.data(), raw->last_tx_.size(), &decoded),
    BIBA_PROTO_OK);
  EXPECT_EQ(decoded.cmd, BIBA_CMD_SET_SETPOINT);
  ASSERT_EQ(decoded.payload_len, 4);

  // 0.5 -> round(0.5 * 32767) = 16384 (little-endian).
  int16_t left = static_cast<int16_t>(decoded.payload[0] | (decoded.payload[1] << 8));
  int16_t right = static_cast<int16_t>(decoded.payload[2] | (decoded.payload[3] << 8));
  EXPECT_EQ(left, 16384);
  EXPECT_EQ(right, -16384);
}

TEST(Stm32Link, SetpointClampsOutOfRangeValues)
{
  auto fake = std::make_unique<FakeTransport>();
  auto * raw = fake.get();
  raw->rx_to_send_ = make_telemetry_reply(2, 0);
  Stm32Link link(std::move(fake));
  ASSERT_TRUE(link.open(SpiConfig{}));

  Telemetry tlm;
  Setpoint sp{2.0, -10.0};
  ASSERT_TRUE(link.set_setpoint(sp, tlm));

  biba_proto_frame_t decoded{};
  ASSERT_EQ(
    biba_proto_decode(raw->last_tx_.data(), raw->last_tx_.size(), &decoded),
    BIBA_PROTO_OK);
  int16_t left = static_cast<int16_t>(decoded.payload[0] | (decoded.payload[1] << 8));
  int16_t right = static_cast<int16_t>(decoded.payload[2] | (decoded.payload[3] << 8));
  EXPECT_EQ(left, 32767);
  EXPECT_EQ(right, -32768);
}

TEST(Stm32Link, ArmCommandSelectsCorrectCmdByte)
{
  auto fake = std::make_unique<FakeTransport>();
  auto * raw = fake.get();
  Stm32Link link(std::move(fake));
  ASSERT_TRUE(link.open(SpiConfig{}));

  Telemetry tlm;
  raw->rx_to_send_ = make_telemetry_reply(0, BIBA_PROTO_FLAG_ARMED);
  ASSERT_TRUE(link.arm(true, tlm));
  EXPECT_EQ(raw->last_tx_[3], static_cast<uint8_t>(BIBA_CMD_ARM));

  raw->rx_to_send_ = make_telemetry_reply(1, 0);
  ASSERT_TRUE(link.arm(false, tlm));
  EXPECT_EQ(raw->last_tx_[3], static_cast<uint8_t>(BIBA_CMD_DISARM));
}

TEST(Stm32Link, TelemetryDecodesPhysicalUnits)
{
  auto fake = std::make_unique<FakeTransport>();
  auto * raw = fake.get();
  raw->rx_to_send_ = make_telemetry_reply(7, BIBA_PROTO_FLAG_ARMED | BIBA_PROTO_FLAG_CRSF_ALIVE);
  Stm32Link link(std::move(fake));
  ASSERT_TRUE(link.open(SpiConfig{}));

  Telemetry tlm;
  ASSERT_TRUE(link.ping(tlm));

  EXPECT_NEAR(tlm.setpoint_left, 16384.0 / 32767.0, 1e-6);
  EXPECT_NEAR(tlm.setpoint_right, -16384.0 / 32767.0, 1e-6);
  EXPECT_NEAR(tlm.current_left_a, 1.5, 1e-6);
  EXPECT_NEAR(tlm.current_right_a, -1.5, 1e-6);
  EXPECT_NEAR(tlm.vbat_v, 25.2, 1e-6);
  EXPECT_NEAR(tlm.rail_12v_v, 12.0, 1e-6);
  EXPECT_NEAR(tlm.gyro_z_dps, 90.0, 1e-6);
  EXPECT_EQ(tlm.crsf_rssi, 200u);
  EXPECT_EQ(tlm.crsf_link_quality, 99u);
  EXPECT_EQ(tlm.crsf_snr_db, 7);
  EXPECT_EQ(tlm.uptime_ms, 1234u);
  EXPECT_TRUE(tlm.flags & BIBA_PROTO_FLAG_ARMED);
  EXPECT_TRUE(tlm.flags & BIBA_PROTO_FLAG_CRSF_ALIVE);
}

TEST(Stm32Link, TransferFailureBubblesUp)
{
  class FailingTransport : public ISpiTransport
  {
  public:
    bool open(const SpiConfig &) override { open_ = true; return true; }
    void close() override { open_ = false; }
    bool is_open() const override { return open_; }
    bool transfer(const uint8_t *, uint8_t *, size_t) override { return false; }
    bool open_ = false;
  };

  Stm32Link link(std::make_unique<FailingTransport>());
  ASSERT_TRUE(link.open(SpiConfig{}));
  Telemetry tlm;
  EXPECT_FALSE(link.ping(tlm));
}

TEST(Stm32Link, CorruptReplyRejected)
{
  auto fake = std::make_unique<FakeTransport>();
  auto * raw = fake.get();
  raw->rx_to_send_ = make_telemetry_reply(0, 0);
  // Flip a CRC byte.
  raw->rx_to_send_[BIBA_PROTO_FRAME_SIZE - 1] ^= 0xFFu;
  Stm32Link link(std::move(fake));
  ASSERT_TRUE(link.open(SpiConfig{}));
  Telemetry tlm;
  EXPECT_FALSE(link.ping(tlm));
}

TEST(Stm32Link, SequenceCounterMonotonic)
{
  auto fake = std::make_unique<FakeTransport>();
  auto * raw = fake.get();
  Stm32Link link(std::move(fake));
  ASSERT_TRUE(link.open(SpiConfig{}));

  std::vector<uint8_t> seqs;
  for (int i = 0; i < 4; ++i) {
    raw->rx_to_send_ = make_telemetry_reply(static_cast<uint8_t>(i), 0);
    Telemetry tlm;
    ASSERT_TRUE(link.ping(tlm));
    seqs.push_back(raw->last_tx_[4]);  // seq is byte 4 in header
  }
  EXPECT_EQ(seqs[0], 0);
  EXPECT_EQ(seqs[1], 1);
  EXPECT_EQ(seqs[2], 2);
  EXPECT_EQ(seqs[3], 3);
}
