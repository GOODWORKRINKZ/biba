#ifndef BIBA_BLDC_H
#define BIBA_BLDC_H

/* BLDC motor-backend interface (driver- and transport-agnostic).
 *
 * Every target with BIBA_TARGET_HAS_BLDC_2CH == 1 links exactly one
 * implementation of this API.  Which one is picked by the target's
 * BIBA_TARGET_BLDC_BACKEND_* flags plus the env's build_src_filter:
 *
 *   RP2040_BLDC_ODRIVE_CAN  → drivers/odrive_can.c   (ODrive CANSimple, 11-bit ID)
 *                       → drivers/odrive_uart.c  (ODrive ASCII over UART1)
 *   RP2040_BLDC_VESC    → drivers/vesc_can.c     (VESC CAN, 29-bit ext ID)
 *
 * The ODrive pair is further narrowed at compile time by
 * BIBA_ODRIVE_LINK_UART (0 = CAN, 1 = UART): each backend's TU
 * self-excludes when its transport is not selected, so both can live
 * in the same src_filter without a linker collision.
 *
 * Contract (shaped after the BTS7960 API, ADR-0001 §1.5):
 *   biba_bldc_init()          — once at boot (transport bring-up)
 *   biba_bldc_set_enabled()   — arm / disarm the pair
 *   biba_bldc_drive()         — left/right command in [-1, +1]
 *   biba_bldc_thermal_reset() — zero setpoints + disarm
 *   biba_bldc_tick_50hz()     — every control-loop period (50 Hz)
 *   biba_bldc_drain_rx()      — service transport RX (called from tick)
 *   biba_bldc_node_alive()    — per-node liveness for fail-safe
 *
 * `left_duty` / `right_duty` are normalised to [-1.0, +1.0].  What
 * ±1.0 maps to on the wire is the backend's business: ODrive scales it
 * to BIBA_ODRIVE_*_MAX_VEL_REV_S, VESC to duty / ERPM / current
 * depending on BIBA_VESC_CONTROL_MODE.  Mode code never needs to know.
 *
 * Node ids come from the target's target_config.h as
 * BIBA_BLDC_LEFT_NODE_ID / BIBA_BLDC_RIGHT_NODE_ID.
 */

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

void biba_bldc_init(void);
void biba_bldc_set_enabled(bool enabled);
void biba_bldc_drive(float left_duty, float right_duty);
void biba_bldc_thermal_reset(uint32_t pulse_us);
void biba_bldc_clear_errors(void);

/* Periodic tick at the control-loop rate (50 Hz default).  Rate
 * limiting happens inside, so it is safe to call faster or slower. */
void biba_bldc_tick_50hz(void);

/* Drain transport RX outside the tick (e.g. before reporting).  Always
 * a no-op before biba_bldc_init(). */
void biba_bldc_drain_rx(void);

/* Last-known liveness per node.  Used by the mode code to fail-safe. */
bool biba_bldc_node_alive(uint8_t node_id);

/* ---- Telemetry getters ------------------------------------------------
 *
 * Last-known bus voltage (V) and per-node motor current (A), refreshed
 * by the periodic poll.  Consumed by the telemetry uplink
 * (biba_voltage_sense_vbat_mv / biba_current_sense_* stubs in
 * hal/biba_hal_motor_bldc.c). */
float biba_bldc_bus_voltage(void);
float biba_bldc_iq_measured(uint8_t node_id);

/* ---- Debug counters (saturating) ------------------------------------- */

uint32_t biba_bldc_tx_count(void);
uint32_t biba_bldc_rx_count(void);
uint32_t biba_bldc_decode_errors(void);
uint32_t biba_bldc_recovery_count(void);
uint32_t biba_bldc_reset_count(void);

#ifdef __cplusplus
}
#endif

#endif /* BIBA_BLDC_H */
