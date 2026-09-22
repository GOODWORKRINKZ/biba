#ifndef BIBA_TARGET_CONFIG_H
#define BIBA_TARGET_CONFIG_H

/* Target-specific overrides for RP2040_DC_BTS7960_PWM.
 *
 * RP2040 runs at 125 MHz (PLL configured by pico-sdk before main).
 * ADC is 12-bit / 3.3 V reference.
 *
 * Native ADC topology — three channels on-board (no external ADC):
 *   - GP26 / ADC0: IS_RIGHT — BTS7960 right IS pins → 1kΩ‖1kΩ + 0.1µF RC filter
 *     R_eff = 500Ω, kILIS = 8500 → VIS = IL / 17 → BIBA_IS_AMPS_PER_VOLT = 17.0 A/V
 *   - GP27 / ADC1: IS_LEFT  — BTS7960 left  IS pins → 1kΩ‖1kΩ + 0.1µF RC filter
 *     Same calibration as IS_RIGHT.
 *   - GP28 / ADC2: VBAT     — resistive voltage divider → BIBA_VBAT_DIVIDER_RATIO
 *     Tune BIBA_VBAT_DIVIDER_RATIO from measured Vbat vs ADC reading.
 */

#define BIBA_SYS_CLOCK_HZ            125000000u
#define BIBA_PWM_FREQUENCY_HZ        20000   /* 20 kHz carrier, above audible */

/* BTS7960 IS-pin calibration (Phase 06: RC-filtered native ADC path).
 * R_eff = 500Ω (1kΩ ‖ 1kΩ), kILIS = 8500.
 * VIS = IL × R_eff / kILIS = IL / 17 → IL = VIS × 17.0 A/V         */
#define BIBA_IS_AMPS_PER_VOLT        17.0f
#define BIBA_IS_ZERO_OFFSET_V        0.0f

/* VBAT — GP28 / ADC2, native RP2040 ADC (3.3 V reference, 12-bit).
 * Resistive divider ratio — tune BIBA_VBAT_DIVIDER_RATIO from measured
 * Vbat vs ADC reading once the divider is wired to GP28.
 * Placeholder: 10.1× matches a standard 10kΩ/1kΩ divider for ~33 V max.
 * At 6S full charge (25.2 V): 25.2 / 10.1 = 2.49 V — within 3.3 V ADC ref. */
#define BIBA_VBAT_DIVIDER_RATIO      10.1f

/* IBAT — GP29 / ADC3, battery pack current sensor output.
 * Calibrate BIBA_IBAT_AMPS_PER_VOLT and BIBA_IBAT_ZERO_OFFSET_V from
 * the actual sensor module datasheet (e.g. ACS712-30A: 66 mV/A, Voffset=1.65V;
 * ACS758-100B: 20 mV/A, Voffset=0.6V). Placeholders below — MUST be tuned. */
#define BIBA_IBAT_AMPS_PER_VOLT      15.15f  /* placeholder — tune to sensor */
#define BIBA_IBAT_ZERO_OFFSET_V      1.65f   /* placeholder — Vout at 0 A    */

/* Phase 06 HW not yet wired: native ADC GP26/GP27 carry noise/old VBAT
 * divider until 1k‖1k + 0.1µF RC filter is installed on BTS7960 IS pins.
 * Disable per-motor current AND power limiters so spurious IS readings
 * don't throttle PWM (power limiter uses the same current sample).
 * Restore to 18.0f / 180.0f after Phase 06 hardware rework. */
#define BIBA_LEFT_MAX_CURRENT_A      0.0f
#define BIBA_RIGHT_MAX_CURRENT_A     0.0f
#define BIBA_LEFT_MAX_POWER_W        0.0f
#define BIBA_RIGHT_MAX_POWER_W       0.0f

/* Open-loop duty ramp (no speed feedback on this board).  Soft PWM braking
 * keeps the braking current — which flows through the static low-side
 * switch (U2 burned, kicad/variants/brushed-bts7960/analysis/) and back
 * into the 6S pack (BTN7970 over-voltage lockout at 28 V) — bounded.
 * NOTE: the current limiter is off on this board (MAX_CURRENT_A = 0 above
 * disables it), so this ramp is the only firmware-side protection.
 *
 * Field test 2026-09-20 (first run with the ramp): steering became
 * unusable.  A wheel asked to flip sign sat at zero for
 * |duty| / REVERSE_DECEL_RATE + ZERO_HOLD_MS — with 0.5f / 400 ms that is
 * 2.4 s at full duty — while the other wheel kept pulling, so the machine
 * yawed away on its own.  Re-centring and driving off paid the penalty a
 * second time.
 *
 * Three changes:
 *  - ZERO_HOLD_MS 400 → 30.  The hold happens at zero duty with the wheel
 *    already stopped or coasting; there is no braking current left to
 *    bound, so it was pure latency.  It also hurt most exactly where there
 *    is no energy to dump at all: turning in place from a standstill.
 *    30 ms still covers electrical settling (motor L/R is ~ms).
 *  - REVERSE_DECEL_RATE 0.5f → 4.0f.  Being SLOWER than DECEL_RATE was
 *    never defensible — winding duty down ahead of a reversal is the same
 *    electrical event as an ordinary throttle release.  Going past
 *    DECEL_RATE to 4.0f does widen the regen envelope, and is deliberate:
 *    it rides on the snubber / TVS / bulk-ceramic rework (2084a2f) fitted
 *    after U2 burned, which clamps exactly the rail transient the old
 *    rate was substituting for.
 *  - ACCEL_RATE untouched.  It is the only constant bounding current INTO
 *    a stalled or back-driven motor, and nothing in the field report
 *    pointed at it.
 * Worst case reversal is now ~280 ms at full duty instead of 2400 ms.
 *
 * Field test 2026-09-21 (with the above): reversal-based steering is good
 * — figure-eights, obstacles it could not clear the day before — but with
 * the throttle HELD the machine will not change course at all; the driver
 * has to release the stick first, then it turns.  That is the other half
 * of the same bug.  Steering under throttle never flips a sign: the mixer
 * keeps the outer wheel where it is and asks the inner one for a SMALLER
 * duty of the SAME sign, so it goes down the plain DECEL_RATE path, not
 * the reversal path that was just made fast.  At full stick (deadband
 * 0.20 → s = 0.8) the mixer asks the inner wheel for 0.111 while it sits
 * at 1.0: 0.889 / 1.0f = 890 ms to develop the differential, against
 * 250 ms for the same wind-down when it happens to be a reversal.  A
 * correction held for a few hundred ms therefore never arrives, while
 * releasing the throttle drops both wheels into the fast path.
 *  - DECEL_RATE 1.0f → 4.0f, i.e. equal to REVERSE_DECEL_RATE.  The two
 *    are the same electrical event — duty winding down, motor feeding the
 *    rail — and the reversal path already runs at 4.0f, so the PEAK regen
 *    the pack sees is unchanged; this only stops the ramp from deciding
 *    which of two identical events is allowed to be fast.  Inner-wheel
 *    response drops 890 ms → 222 ms.
 *    Exposure that does change: an ordinary throttle release is far more
 *    frequent than a reversal, so the board now meets that 4.0f envelope
 *    many times per run instead of occasionally.  It is the same envelope
 *    the snubber / TVS / bulk-ceramic rework (2084a2f) was fitted for.
 *  - ACCEL_RATE still untouched, and now deliberately so: the 2026-09-21
 *    report also has the drivers running hot enough to drop a wheel on a
 *    climb with an 80 kg load, and ACCEL_RATE is the only constant
 *    bounding current INTO a stalled or back-driven motor.
 *
 * If the pack rail trips the 28 V BTN7970 lockout under hard reversals or
 * hard stops, back off from build_flags before editing this file:
 *   -D BIBA_RAMP_DECEL_RATE=1.0f -D BIBA_RAMP_REVERSE_DECEL_RATE=1.0f
 *   -D BIBA_RAMP_ZERO_HOLD_MS=50
 * (= pre-rework regen envelope; steering under throttle goes back to
 * unusable, so treat it as a diagnostic, not a setting).  The other lever
 * is the current limiter, still disabled above. */
/* #ifndef, unlike the rest of this file: these four are the knobs the
 * back-off line above tells you to reach for, and a plain #define here would
 * silently win over the -D (redefinition warning only, no -Werror). */
#ifndef BIBA_RAMP_ACCEL_RATE
#  define BIBA_RAMP_ACCEL_RATE         2.0f
#endif
#ifndef BIBA_RAMP_DECEL_RATE
#  define BIBA_RAMP_DECEL_RATE         4.0f
#endif
#ifndef BIBA_RAMP_REVERSE_DECEL_RATE
#  define BIBA_RAMP_REVERSE_DECEL_RATE 4.0f
#endif
#ifndef BIBA_RAMP_ZERO_HOLD_MS
#  define BIBA_RAMP_ZERO_HOLD_MS       30u
#endif

/* Speed mode scales (3-position switch, brushed variant).
 * Old first gear (1/3) was too slow, so:
 *   1st gear = old 2nd (2/3), 2nd gear = halfway between old 2nd and 3rd
 *   (5/6), 3rd gear unchanged at 1.0 (global default). */
#define BIBA_SPEED_MODE_SLOW_SCALE       (2.0f / 3.0f)
#define BIBA_SPEED_MODE_MEDIUM_SCALE     (5.0f / 6.0f)
/* BIBA_SPEED_MODE_FAST_SCALE stays at the global default 1.0f */

/* --- Feature toggle overrides (D-07) ----------------------------------- */
/* Reverse backup beep is OFF on RP2040 by default (match legacy behaviour). */
#define BIBA_FEATURE_REVERSE_PIP          0

#endif /* BIBA_TARGET_CONFIG_H */
