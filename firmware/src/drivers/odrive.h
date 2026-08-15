#ifndef BIBA_ODRIVE_H
#define BIBA_ODRIVE_H

/* ODrive motor-backend interface (transport-agnostic).
 *
 * Two interchangeable transports implement this API:
 *   - drivers/odrive_can.c  — CANSimple over SPI0 → MCP2515 → CAN
 *   - drivers/odrive_uart.c — ASCII protocol over UART1 (GP4/GP5)
 *
 * Exactly one is compiled per build, selected by BIBA_ODRIVE_LINK_UART
 * in targets/<TARGET>/target_config.h (0 = CAN, 1 = UART).  Each
 * backend's TU self-excludes when its transport is not selected, so
 * both can live in the same src_filter without a linker collision.
 *
 * High-level API (matches the BTS7960 shape, ADR-0001 §1.5):
 *   biba_odrive_init()          — once at boot (transport bring-up)
 *   biba_odrive_set_enabled()   — arm (CLOSED_LOOP) / disarm (IDLE)
 *   biba_odrive_drive()         — left/right duty in [-1, +1]
 *   biba_odrive_thermal_reset() — zero setpoints + disarm
 *   biba_odrive_tick_50hz()     — every control-loop period (50 Hz)
 *   biba_odrive_drain_rx()      — service transport RX (called from tick)
 *   biba_odrive_node_alive()    — per-node liveness for fail-safe
 *
 * `left_duty` / `right_duty` are normalised to [-1.0, +1.0]; ±1.0 maps
 * to BIBA_ODRIVE_*_MAX_VEL_REV_S for the corresponding wheel.
 */

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

void biba_odrive_init(void);
void biba_odrive_set_enabled(bool enabled);
void biba_odrive_drive(float left_duty, float right_duty);
void biba_odrive_thermal_reset(uint32_t pulse_us);

/* Periodic tick at the control-loop rate (50 Hz default).  Rate
 * limiting happens inside, so it is safe to call faster or slower. */
void biba_odrive_tick_50hz(void);

/* Drain transport RX outside the tick (e.g. before reporting).  Always
 * a no-op before biba_odrive_init(). */
void biba_odrive_drain_rx(void);

/* Last-known liveness per node.  Used by the mode code to fail-safe. */
bool biba_odrive_node_alive(uint8_t node_id);

/* ---- Telemetry getters ------------------------------------------------
 *
 * Last-known ODrive bus voltage (V) and per-node motor current (A),
 * refreshed by the periodic poll.  Consumed by the telemetry uplink
 * (biba_voltage_sense_vbat_mv / biba_current_sense_* on the BLDC
 * target). */
float biba_odrive_bus_voltage(void);
float biba_odrive_iq_measured(uint8_t node_id);

/* ---- Debug counters (saturating) ------------------------------------- */

uint32_t biba_odrive_tx_count(void);
uint32_t biba_odrive_rx_count(void);
uint32_t biba_odrive_decode_errors(void);
uint32_t biba_odrive_recovery_count(void);
uint32_t biba_odrive_reset_count(void);

#ifdef __cplusplus
}
#endif

#endif /* BIBA_ODRIVE_H */
