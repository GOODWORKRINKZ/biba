#ifndef BIBA_TARGET_CONFIG_H
#define BIBA_TARGET_CONFIG_H

/* Target-specific overrides for RP2040_BLDC_VESC_CAN.
 *
 * RP2040 runs at 125 MHz (PLL configured by pico-sdk before main).
 *
 * On this target, motor drive is delegated entirely to a Flipsky dual
 * FSESC. The BTS7960 IS-pin calibration values, motor current limits,
 * motor power limits and dead-time pre/post here have no effect — the
 * BLDC backend (drivers/vesc_can.c) sends the normalised setpoint over
 * CAN and the VESC clamps it against its own motor configuration.
 *
 * IMPORTANT: the real limits live in VESC Tool, not here. Run motor
 * detection and set Motor Settings → Current / ERPM / Wattage before
 * the first powered run; the values below only shape how BiBa's
 * [-1, +1] command maps onto the wire.
 */

#define BIBA_SYS_CLOCK_HZ            125000000u
#define BIBA_PWM_FREQUENCY_HZ        20000   /* 20 kHz — sanity default; no PWM is wired */

/* --- Node addressing ---------------------------------------------------
 *
 * Both halves of a dual FSESC ship as VESC ID 0. Set the right-hand
 * one to 1 in VESC Tool (App Settings → General → VESC ID) or the
 * firmware cannot address them separately — and, worse, both wheels
 * answer every command.
 */

#define BIBA_BLDC_LEFT_NODE_ID       0   /* maps to LEFT wheel  */
#define BIBA_BLDC_RIGHT_NODE_ID      1   /* maps to RIGHT wheel */

/* --- Control mode ------------------------------------------------------
 *
 * How biba_bldc_drive()'s [-1, +1] becomes a VESC command:
 *
 *   BIBA_VESC_MODE_DUTY    → CAN_PACKET_SET_DUTY    (open loop, default)
 *   BIBA_VESC_MODE_ERPM    → CAN_PACKET_SET_RPM     (closed-loop speed)
 *   BIBA_VESC_MODE_CURRENT → CAN_PACKET_SET_CURRENT (torque)
 *
 * DUTY is the default because it works on any motor the VESC has
 * completed detection for — no encoder, no PID tuning, no hall
 * sensors. It behaves like the BTS7960 targets did, so the existing
 * ramp / trim / fail-safe tuning in src/modes carries over unchanged.
 *
 * Switch to ERPM once the hall sensors on the FSESC "SENSE" connector
 * are wired and hall detection has run: the wheels then hold speed on
 * slopes instead of slowing down, which is what the RPM PI loop in
 * src/app/rpm_pi.c wants. Values are symbolic constants from
 * src/drivers/vesc_can.h.
 */
#ifndef BIBA_VESC_CONTROL_MODE
#  define BIBA_VESC_CONTROL_MODE     0   /* BIBA_VESC_MODE_DUTY */
#endif

/* --- Drive envelope ----------------------------------------------------
 *
 * Each of these is the value that a full-scale command (±1.0) maps to
 * in the corresponding control mode. Only the one matching
 * BIBA_VESC_CONTROL_MODE is used; the others stay defined so switching
 * modes is a one-line change.
 */

/* Duty mode: 0.85 keeps a margin below 100 % so the VESC always has
 * headroom for its own current limiting. Raising this past ~0.95 makes
 * the controller run out of modulation range under load. */
#define BIBA_VESC_MAX_DUTY           0.85f

/* ERPM mode: electrical RPM = mechanical RPM × pole pairs. For a 14-pole
 * (7 pole-pair) hub motor, 12000 ERPM ≈ 1700 motor RPM. Set this from
 * the measured no-load ERPM in VESC Tool, minus ~15 % margin. */
#define BIBA_VESC_MAX_ERPM           12000

/* Current mode: amps at full stick. Must stay at or below the VESC's
 * own Motor Current Max, which remains the enforcing limit. */
#define BIBA_VESC_MAX_CURRENT_A      30.0f

/* Wheel gearbox reduction ratio (motor turns : wheel turns).
 *
 * The VESC measures and commands the MOTOR shaft. The wheel turns this
 * many times slower through the gearbox:
 *
 *   wheel_rev_s = motor_rev_s / BIBA_VESC_GEAR_RATIO
 *
 * Mirrors BIBA_ODRIVE_GEAR_RATIO on the ODrive targets. */
#define BIBA_VESC_GEAR_RATIO         6.0f

/* Polarities: matches the BiBa BTS7960 convention — positive duty =
 * "forward" on both wheels. If a FSESC half is wired to its motor in
 * the reverse direction, flip its macro to -1.0 so the rest of the
 * firmware does not change. (Reversing two of the three phases works
 * too, but this is the one you can do without a soldering iron.) */
#define BIBA_VESC_LEFT_DIR          -1.0f
#define BIBA_VESC_RIGHT_DIR          1.0f

/* --- CAN bus timing ----------------------------------------------------
 *
 * 500 kbps is the VESC default (VESC Tool → App Settings → General →
 * CAN baud rate). drivers/mcp2515.c derives CNF1/CNF2/CNF3 from this
 * for an 87.5 % sample point; supported values are 100000, 250000 and
 * 500000. Change both ends together or the bus will not come up.
 */

#define BIBA_CAN_BITRATE_BPS         500000u

/* VESC ids are 29-bit extended and carry the node id in the low byte,
 * which the MCP2515's standard-ID acceptance filters cannot express.
 * Run the controller in accept-all mode and demux in software — see
 * src/drivers/vesc_can.h. */
#define BIBA_MCP2515_ACCEPT_ALL      1

/* --- Watchdog / failsafe -----------------------------------------------
 *
 * How long the firmware tolerates a VESC that has stopped broadcasting
 * status frames before biba_bldc_node_alive() reports it dead and the
 * mode code fail-safes.
 *
 * This assumes VESC Tool → App Settings → General → "CAN status
 * message mode" is set to CAN_STATUS_1_4_5 (or _1_2_3_4_5) at 50 Hz.
 * With status messages OFF the wheels still turn, but every node reads
 * as dead and the robot refuses to arm. That is deliberate: without
 * status frames there is no voltage, no current and no liveness.
 */
#define BIBA_VESC_STATUS_TIMEOUT_MS         250

/* Minimum interval between drive commands per VESC. 50 Hz matches the
 * CRSF control loop period; anything faster is wasted bus time. Keep
 * this comfortably below the VESC's own command timeout (App Settings
 * → General → Timeout, 1 s by default) — that timeout is the backstop
 * that stops the wheels if BiBa goes silent. */
#define BIBA_VESC_SETPOINT_RATE_HZ          50

/* --- Current / power limits (BTS7960 macros kept as no-ops) -----------
 *
 * The BTS7960 IS-pin calibration and limit macros from
 * include/biba_config.h are referenced by src/app/control_loop.c and
 * src/modes/mode_standalone.c. On this target, motor current is read
 * from the VESC status frames instead. We define the defaults to zero
 * so any code that cross-checks against these values short-circuits
 * cleanly. Real limits live inside the VESC configuration.
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
 * target.h). Provide the IS channel macros as 0 so any cross-target
 * code that references `BIBA_ADC_CHAN_IS_*` still compiles. Runtime
 * behaviour is a no-op because `biba_hal_adc_sample` returns 0 for
 * indices past `BIBA_ADC_SCAN_LEN`. */
#define BIBA_ADC_CHAN_IS_LEFT         0U
#define BIBA_ADC_CHAN_IS_RIGHT        0U

#endif /* BIBA_TARGET_CONFIG_H */
