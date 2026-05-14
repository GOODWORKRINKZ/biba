// Copyright 2026 BiBa maintainers. MIT license.
//
// Thin wrapper around Linux spidev for SBC↔STM32 SPI traffic. The
// hardware plugin owns one instance and treats each transfer as a
// fixed-size full-duplex exchange.
#ifndef BIBA_HARDWARE_STM32__SPI_TRANSPORT_HPP_
#define BIBA_HARDWARE_STM32__SPI_TRANSPORT_HPP_

#include <cstddef>
#include <cstdint>
#include <string>

namespace biba_hardware_stm32
{

struct SpiConfig
{
  std::string device = "/dev/spidev0.0";
  uint32_t speed_hz = 1'000'000;
  uint8_t mode = 0;     // SPI_MODE_0
  uint8_t bits = 8;
};

// Pure-virtual seam so unit tests can inject a fake without touching
// /dev. Production code uses SpiTransportLinux.
class ISpiTransport
{
public:
  virtual ~ISpiTransport() = default;
  virtual bool open(const SpiConfig & cfg) = 0;
  virtual bool transfer(const uint8_t * tx, uint8_t * rx, size_t len) = 0;
  virtual void close() = 0;
  virtual bool is_open() const = 0;
};

class SpiTransportLinux : public ISpiTransport
{
public:
  SpiTransportLinux() = default;
  ~SpiTransportLinux() override;

  SpiTransportLinux(const SpiTransportLinux &) = delete;
  SpiTransportLinux & operator=(const SpiTransportLinux &) = delete;

  bool open(const SpiConfig & cfg) override;
  bool transfer(const uint8_t * tx, uint8_t * rx, size_t len) override;
  void close() override;
  bool is_open() const override { return fd_ >= 0; }

private:
  int fd_ = -1;
  uint32_t speed_hz_ = 0;
};

}  // namespace biba_hardware_stm32

#endif  // BIBA_HARDWARE_STM32__SPI_TRANSPORT_HPP_
