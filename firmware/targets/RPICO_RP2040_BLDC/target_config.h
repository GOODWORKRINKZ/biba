#ifndef BIBA_TARGET_CONFIG_H
#define BIBA_TARGET_CONFIG_H

/* Target-specific overrides for RPICO_RP2040_BLDC.
 *
 * RP2040 runs at 125 MHz (PLL configured by pico-sdk before main).
 *
 * On this target, motor drive is delegated entirely to ODrive. The
 * BTS7960 IS-pin calibration values, motor current limits, motor power
 * limits, and dead-time pre/post here would have no effect — the BLDC
 * backend (drivers/odrive_can.c) uses these values to drive the ODrive
 * controllers over CAN instead.
 *
 * The values below are sensible defaults for a 'first-light' bench
 * test on the user's two ODrive Pro / S1 units. Tune after measuring
 * actual velocity ceilings at the wheel.
 */

#define BIBA_SYS_CLOCK_HZ            125000000u
#define BIBA_PWM_FREQUENCY_HZ        20000   /* 20 kHz — sanity default; no PWM is wired */

/* --- ODrive drive envelope --------------------------------------------
 *
 * The control loop in src/modes/mode_standalone.c computes a normalised
 * duty in [-1.0, +1.0] from CRSF throttle + steering. biba_odrive_drive
 * multiplies this by BIBA_ODRIVE_*_MAX_VEL_REV_S and packs the result
 * into float32 little-endian as part of a CANSimple Set_Input_Vel frame
 * (cmd_id 0x0D).
 *
 * ODrive will additionally enforce current_limit and velocity_limit set
 * via Set_Limits (cmd_id 0x0F) at boot. Defaults below are conservative
 * — tune after bench-testing the pair.
 */

#define BIBA_ODRIVE_LEFT_NODE_ID       0   /* maps to LEFT wheel */
#define BIBA_ODRIVE_RIGHT_NODE_ID      1   /* maps to RIGHT wheel */
#define BIBA_ODRIVE_DISCOVERY_NODE_ID  0x3F    /* broadcast (cmd_id 0x06, RTR=1) */

#define BIBA_ODRIVE_LEFT_MAX_VEL_REV_S    6.0f   /* ≈ 360 rpm @ wheel */
#define BIBA_ODRIVE_RIGHT_MAX_VEL_REV_S   6.0f
#define BIBA_ODRIVE_LEFT_TORQUE_FF_NM      0.0f   /* feed-forward torque */
#define BIBA_ODRIVE_RIGHT_TORQUE_FF_NM     0.0f

/* Polarities: matches the biBa BTS7960 convention — positive duty =
 * "forward" on both wheels. If a particular ODrive is mounted in the
 * reverse direction relative to the wheel it drives, flip its macro to
 * -1.0 so the rest of the firmware does not change. */
#define BIBA_ODRIVE_LEFT_DIR   -1.0f
#define BIBA_ODRIVE_RIGHT_DIR  1.0f

/* Current / torque limits sent to ODrive at boot via Set_Limits. */
#define BIBA_ODRIVE_MAX_CURRENT_A        30.0f   /* per axis; ODrive enforces */
#define BIBA_ODRIVE_MAX_VEL_LIMIT_REV_S  10.0f   /* hard ceiling; 6 rad ≈ 60 rad/s */

/* --- CAN bus timing -------------------------------------------------- */

/* MCP2515 is set to 250 kbps by default; the formula in §6.2 of the
 * research gives 87.5 % sample point with SJW=1.
 *
 * 8 time quanta per bit, BRP=4 → 125 MHz clk_peri yields 7.8125 MHz
 * clk for the SPI to MCP2515. The MCP2515 itself runs from a 8 MHz
 * crystal; we configure BRP divisor inside the MCP2515 (CNF1) so the
 * target bit-rate is 250 kbps (see drivers/mcp2515.c init).
 */

#define BIBA_CAN_BITRATE_BPS            250000u   /* CAN 2.0B bit-rate */

/* --- Watchdog / failsafe --------------------------------------------- */

/* How long the firmware tolerates a missing ODrive heartbeat before it
 * stops sending Set_Input_Vel (relying on the ODrive's own watchdog
 * for the actual motor disarm). */
#define BIBA_ODRIVE_HEARTBEAT_TIMEOUT_MS    250

/* Minimum interval between Set_Input_Vel commands per ODrive. Anything
 * faster than 50 Hz (20 ms) is wasteful on CAN. We send at 50 Hz to
 * match the CRSF control loop period. */
#define BIBA_ODRIVE_SETPOINT_RATE_HZ        50

/* --- Current / power limits (bts7960 macros kept as no-ops) ----------
 *
 * The BTS7960 IS-pin calibration and limit macros from
 * include/biba_config.h are referenced by src/app/control_loop.c and
 * src/modes/mode_standalone.c. On this target, motor current is read
 * from ODrive via Get_Iq (cmd_id 0x14) instead. We define the
 * defaults to zero so any code that cross-checks against these values
 * short-circuits cleanly. Real limits live inside the ODrive firmware
 * and are enforced by Set_Limits (above).
 */

#define BIBA_IS_AMPS_PER_VOLT         1.0f
#define BIBA_IS_ZERO_OFFSET_V         0.0f
#define BIBA_IBAT_AMPS_PER_VOLT       1.0f
#define BIBA_IBAT_ZERO_OFFSET_V       0.0f
#define BIBA_VBAT_DIVIDER_RATIO       1.0f
#define BIBA_LEFT_MAX_CURRENT_A       0.0f
#define BIBA_RIGHT_MAX_CURRENT_A      0.0f
#define BIBA_LEFT_MAX_POWER_W         0.0f
#define BIBA_RIGHT_MAX_POWER_W        0.0f

/* ADCs are not wired on this target (BIBA_ADC_SCAN_LEN = 0 in
 * target.h).  Provide the IS channel macros as 0 so any cross-target
 * code that references `BIBA_ADC_CHAN_IS_*` still compiles.  Runtime
 * behaviour is a no-op because `biba_hal_adc_sample` returns 0 for
 * indices past `BIBA_ADC_SCAN_LEN`. */
#define BIBA_ADC_CHAN_IS_LEFT         0U
#define BIBA_ADC_CHAN_IS_RIGHT        0U

#endif /* BIBA_TARGET_CONFIG_H */
