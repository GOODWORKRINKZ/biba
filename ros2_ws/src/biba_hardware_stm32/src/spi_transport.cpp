// Copyright 2026 BiBa maintainers. MIT license.
#include "biba_hardware_stm32/spi_transport.hpp"

#include <fcntl.h>
#include <linux/spi/spidev.h>
#include <sys/ioctl.h>
#include <unistd.h>

#include <cerrno>
#include <cstring>

namespace biba_hardware_stm32
{

SpiTransportLinux::~SpiTransportLinux()
{
  close();
}

bool SpiTransportLinux::open(const SpiConfig & cfg)
{
  if (fd_ >= 0) {
    close();
  }
  fd_ = ::open(cfg.device.c_str(), O_RDWR);
  if (fd_ < 0) {
    return false;
  }

  uint8_t mode = cfg.mode;
  if (::ioctl(fd_, SPI_IOC_WR_MODE, &mode) < 0) {
    close();
    return false;
  }

  uint8_t bits = cfg.bits;
  if (::ioctl(fd_, SPI_IOC_WR_BITS_PER_WORD, &bits) < 0) {
    close();
    return false;
  }

  uint32_t speed = cfg.speed_hz;
  if (::ioctl(fd_, SPI_IOC_WR_MAX_SPEED_HZ, &speed) < 0) {
    close();
    return false;
  }
  speed_hz_ = speed;
  return true;
}

bool SpiTransportLinux::transfer(const uint8_t * tx, uint8_t * rx, size_t len)
{
  if (fd_ < 0 || tx == nullptr || rx == nullptr || len == 0) {
    return false;
  }
  struct spi_ioc_transfer xfer{};
  xfer.tx_buf = reinterpret_cast<__u64>(tx);
  xfer.rx_buf = reinterpret_cast<__u64>(rx);
  xfer.len = static_cast<__u32>(len);
  xfer.speed_hz = speed_hz_;
  xfer.bits_per_word = 8;
  xfer.delay_usecs = 0;

  return ::ioctl(fd_, SPI_IOC_MESSAGE(1), &xfer) >= 0;
}

void SpiTransportLinux::close()
{
  if (fd_ >= 0) {
    ::close(fd_);
    fd_ = -1;
  }
  speed_hz_ = 0;
}

}  // namespace biba_hardware_stm32
