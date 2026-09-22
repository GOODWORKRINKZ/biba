#ifndef BIBA_ODRIVE_CAN_H
#define BIBA_ODRIVE_CAN_H

/* ODrive CAN protocol constants (CANSimple subset).
 *
 * This header only carries the CAN-specific command IDs and encoding
 * notes.  The transport-agnostic driver API lives in drivers/bldc.h
 * (see there for the full contract).  Mode / hal code should include
 * drivers/bldc.h; only the CAN backend and the CAN-loopback PoC need
 * this header for the OD_CMD_* table below.
 *
 * Single CAN transport assumed: SPI0 → MCP2515 → CAN @ 250 kbps.  The
 * UART ASCII fallback (drivers/odrive_uart.c) shares the same
 * high-level API but none of the constants below.
 */

#include "bldc.h"

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* IDs the CAN backend keeps internal.  Mirrors the ODrive CANSimple
 * cmd_id table (lower 5 bits of the 11-bit CAN ID; node_id in bits 5:10). */
#define OD_CMD_SET_AXIS_STATE          0x07u
#define OD_CMD_GET_ENCODER_ESTIMATES   0x09u
#define OD_CMD_SET_INPUT_VEL           0x0Du
#define OD_CMD_SET_LIMITS              0x0Fu
#define OD_CMD_GET_IQ                  0x14u
#define OD_CMD_RESET_ODRIVE            0x16u   /* NVIC_SystemReset() */
#define OD_CMD_GET_BUS_VOLTAGE_CURRENT 0x17u
#define OD_CMD_CLEAR_ERRORS            0x18u   /* ODrive CANSimple Clear_Errors */
#define OD_CMD_GET_TEMPERATURE         0x18u
#define OD_CMD_ADDRESS                 0x06u
#define OD_CMD_HEARTBEAT               0x01u

#ifdef __cplusplus
}
#endif

#endif /* BIBA_ODRIVE_CAN_H */
