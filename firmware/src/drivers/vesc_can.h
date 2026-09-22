#ifndef BIBA_VESC_CAN_H
#define BIBA_VESC_CAN_H

/* VESC CAN protocol constants (the subset BiBa speaks).
 *
 * This header only carries the CAN packet ids and their payload
 * scaling.  The transport-agnostic driver API lives in drivers/bldc.h
 * (see there for the full contract).  Mode / hal code should include
 * drivers/bldc.h; only the VESC backend and bench tools need the
 * VESC_PKT_* table below.
 *
 * Envelope (bldc firmware, comm_can.c):
 *
 *   ext_id = controller_id | (packet_id << 8)      — 29-bit EXTENDED id
 *
 * so the node id occupies the low 8 bits and the packet id the next 8.
 * This is why RP2040_BLDC_VESC sets BIBA_MCP2515_ACCEPT_ALL: a
 * standard-ID acceptance filter cannot mask an extended id's high
 * bytes without the extended mask registers, and on a two-node bus
 * software demux is cheaper than the register juggling.
 *
 * Endianness: every VESC payload is BIG-endian (buffer_append_int32 &
 * friends).  This is the opposite of ODrive CANSimple — do not copy
 * the packing helpers between the two backends.
 *
 * Transport: SPI0 → MCP2515 → CAN @ BIBA_CAN_BITRATE_BPS (500 kbps
 * default, matching VESC Tool → App Settings → General → CAN baud).
 */

#include "bldc.h"

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* --- Commands we send (BiBa → VESC) ---------------------------------- */

#define VESC_PKT_SET_DUTY          0u   /* int32  duty    × 100000      */
#define VESC_PKT_SET_CURRENT       1u   /* int32  amps    × 1000        */
#define VESC_PKT_SET_CURRENT_BRAKE 2u   /* int32  amps    × 1000        */
#define VESC_PKT_SET_RPM           3u   /* int32  ERPM    (no scaling)  */
#define VESC_PKT_SET_POS           4u   /* int32  degrees × 1000000     */
#define VESC_PKT_PING             17u   /* no payload; VESC replies PONG */
#define VESC_PKT_PONG             18u   /* no payload                    */

/* --- Status frames we decode (VESC → BiBa) ---------------------------
 *
 * These are broadcast by the VESC only when "CAN status message mode"
 * is enabled in VESC Tool (App Settings → General).  BiBa needs at
 * least CAN_STATUS_1_4_5:
 *
 *   STATUS   → ERPM + motor current  (liveness + biba_bldc_iq_measured)
 *   STATUS_4 → FET / motor temperature
 *   STATUS_5 → input voltage         (biba_bldc_bus_voltage)
 *
 * With status messages off, the wheels still turn but every node reads
 * as dead and the fail-safe disarms the robot.  See the target README.
 */

#define VESC_PKT_STATUS            9u   /* i32 erpm, i16 cur×10, i16 duty×1000 */
#define VESC_PKT_STATUS_2         14u   /* i32 Ah×1e4, i32 Ah_chg×1e4          */
#define VESC_PKT_STATUS_3         15u   /* i32 Wh×1e4, i32 Wh_chg×1e4          */
#define VESC_PKT_STATUS_4         16u   /* i16 t_fet×10, t_mot×10, i_in×10, pid×50 */
#define VESC_PKT_STATUS_5         27u   /* i32 tacho, i16 v_in×10              */

/* --- Control mode selector (target_config.h: BIBA_VESC_CONTROL_MODE) - */

#define BIBA_VESC_MODE_DUTY     0
#define BIBA_VESC_MODE_ERPM     1
#define BIBA_VESC_MODE_CURRENT  2

#ifdef __cplusplus
}
#endif

#endif /* BIBA_VESC_CAN_H */
