#ifndef BIBA_ODRIVE_CAN_H
#define BIBA_ODRIVE_CAN_H

/* ODrive CAN protocol driver (CANSimple subset).
 *
 * What lives here:
 *   - Encoding helpers for Set_Input_Vel, Set_Axis_State, Set_Limits,
 *     Get_Encoder_Estimates, Get_Iq, Get_Bus_Voltage_Current,
 *     Get_Temperature, Heartbeat consumption, Address broadcast.
 *   - Per-node heartbeat liveness tracking.
 *   - High-level OO-ish API used by src/modes/* and src/hal/biba_hal_motor_bldc.c
 *     (biba_odrive_set_enabled / biba_odrive_drive / biba_odrive_thermal_reset).
 *
 * Single transport assumed: SPI0 → MCP2515 → CAN.  UART ASCII fallback
 * from ADR §3 is a v2 feature (compile-time gated by ODRIVE_LINK,
 * not wired in v1).
 *
 * Tick contract:
 *   biba_odrive_can_init()        — once at boot, after mcp2515_init()
 *   biba_odrive_can_tick_50hz()   — every control-loop period (50 Hz)
 *   biba_odrive_can_drain_rx()    — drain RX queue whenever the main
 *                                    loop sees fit (we call from tick)
 */

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* IDs we keep *inside* this driver.  Mirrors the ODrive CANSimple table. */
#define OD_CMD_SET_AXIS_STATE          0x07u
#define OD_CMD_GET_ENCODER_ESTIMATES   0x09u
#define OD_CMD_SET_INPUT_VEL           0x0Du
#define OD_CMD_SET_LIMITS              0x0Fu
#define OD_CMD_GET_IQ                  0x14u
#define OD_CMD_GET_BUS_VOLTAGE_CURRENT 0x17u
#define OD_CMD_GET_TEMPERATURE         0x18u
#define OD_CMD_ADDRESS                 0x06u
#define OD_CMD_HEARTBEAT               0x01u

void biba_odrive_can_init(void);

/* High-level (matches BTS7960 API shape, ADR-0001 §1.5). */
void biba_odrive_set_enabled(bool enabled);
/* left_duty / right_duty in [-1, +1], ±1.0 = BIBA_ODRIVE_*_MAX_VEL_REV_S. */
void biba_odrive_drive(float left_duty, float right_duty);
/* BLDC has no thermal latch; we just zero the setpoints and let the
 * ODrive-side watchdog disarm the motors. */
void biba_odrive_thermal_reset(uint32_t pulse_us);

/* Periodic tick at the control-loop rate (50 Hz default).
 *
 * Internally:
 *   - issues Set_Input_Vel once per ODrive (rate-limited)
 *   - re-issues Set_Axis_State on arm edge
 *   - re-issues Set_Limits once at boot
 *   - drains can_queue.rx via mcp2515_rx_pop(), decodes Heartbeat /
 *     Get_Iq / Get_Bus_Voltage_Current / Get_Temperature / Address
 *
 * Safe to call at slower or faster rates (rate limiting happens inside).
 * Calling faster than BIBA_ODRIVE_SETPOINT_RATE_HZ is rate-limited. */
void biba_odrive_can_tick_50hz(void);

/* If you want to drain RX outside the tick (e.g. before reporting),
 * this is the public entry-point.  Always a no-op if not initialised. */
void biba_odrive_can_drain_rx(void);

/* Last-known liveness per node.  Used by mode_dispatcher /
 * mode_companion to decide whether to fail-safe. */
bool biba_odrive_node_alive(uint8_t node_id);

/* ---- Debug counters (saturating) ------------------------------------- */

uint32_t biba_odrive_tx_count(void);
uint32_t biba_odrive_rx_count(void);
uint32_t biba_odrive_decode_errors(void);

#ifdef __cplusplus
}
#endif

#endif /* BIBA_ODRIVE_CAN_H */
