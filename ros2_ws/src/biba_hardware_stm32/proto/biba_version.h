#ifndef BIBA_VERSION_H
#define BIBA_VERSION_H

/* Firmware version numbers. Bumped whenever the SPI protocol or firmware
 * behaviour changes in an operator-visible way. */

#define BIBA_FW_VERSION_MAJOR 0
#define BIBA_FW_VERSION_MINOR 1
#define BIBA_FW_VERSION_PATCH 0

/* Wire-format version carried inside biba_proto frames. Must match
 * biba-controller/stm32_link/protocol.py::PROTOCOL_VERSION. */
#define BIBA_PROTO_VERSION 0x01

#endif /* BIBA_VERSION_H */
