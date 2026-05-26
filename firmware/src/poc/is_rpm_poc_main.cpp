/* Phase 06 IS-Signal RPM PoC — USB CDC command shell.
 *
 * Commands (over USB CDC, 115200 baud, line-terminated by '\n'):
 *   PING                                 -> "PONG"
 *   STOP                                 -> stops motors, disarms SSR + enables, "OK stopped"
 *   CAPTURE <FWD|REV> <duty_pct> <n> <sps> [settle_ms] ->
 *       Drives the left motor PWM at the requested direction/duty, settles,
 *       then DMA-bursts <n> samples from BIBA_ADC_CHAN_IS_LEFT at <sps> sps.
 *
 *       Response format:
 *         CAPTURE_START duty=<pct> dir=<FWD|REV> chan=<n> sps=<sps> n=<n> settle_ms=<m>
 *         <comma-separated 12-bit ADC values, one line>
 *         CAPTURE_END
 *
 *   RPMRUN <target_hz> <duration_ms> [kp_x1000 ki_x1000] ->
 *       Closed-loop PI controller: setpoint is IS-frequency in Hz; plant is
 *       the left motor PWM duty; measurement is on-device Schmitt-trigger
 *       zero-crossing of a 2048-sample @ 10 kSPS burst (200 ms window →
 *       5 Hz loop rate).  Live CSV stream over USB:
 *         RPMRUN_START target=<hz> duration_ms=<m> kp=<f> ki=<f>
 *         RPM_DATA t_ms,target_hz,meas_hz,duty_pct,curr_a
 *         ...
 *         RPMRUN_END
 *       Kp/Ki are passed as integers ×1000 (e.g. 50 1000 → 0.05 / 1.0).
 *       Defaults: Kp=0.05, Ki=1.0.
 *
 * The firmware always drives the IS_LEFT channel. The Python orchestrator's
 * --motor {left|right} flag selects which physical unit is run; this firmware
 * variant is intended to be flashed per-unit.
 */

#include <Arduino.h>
#include <math.h>
#include <hardware/adc.h>

extern "C" {
#include "hal/biba_hal.h"
#include "biba_board.h"
#include "biba_config.h"
#include "app/motor_bridge.h"
#include "app/adc_capture.h"
}

static uint16_t s_buf[ADC_CAPTURE_MAX_SAMPLES];
static uint16_t s_pair_buf[ADC_CAPTURE_MAX_SAMPLES];
static volatile bool s_capture_pair_done;

static void on_capture_pair_done(const uint16_t *, uint16_t)
{
    s_capture_pair_done = true;
}

#define IS_POC_REARM_SETTLE_MS  5u

/* Re-arm the motor bridge for the next command. This mirrors the
 * standalone arm edge by pulsing BTS7960 enables first, which clears a
 * possible thermal latch after a stalled/aborted previous run. */
static void ensure_armed(void)
{
    biba_motor_bridge_rearm();
    delay(IS_POC_REARM_SETTLE_MS);
}

/* Default spin-up settle window before sampling. Motor inertia + RC-filter
 * settling on the IS line takes longer than initially assumed: bench scope
 * shows the IS waveform stabilises ~1 s after a duty step. Host can
 * override via the 5th CAPTURE arg. */
#define IS_POC_DEFAULT_SETTLE_MS  1500u
#define IS_POC_MAX_SETTLE_MS      10000u

static void cmd_capture(float signed_duty, bool is_fwd,
                        uint8_t adc_chan, uint16_t n_samples, uint32_t sps,
                        uint32_t settle_ms)
{
    if (signed_duty > 1.0f)  signed_duty = 1.0f;
    if (signed_duty < -1.0f) signed_duty = -1.0f;
    if (n_samples > ADC_CAPTURE_MAX_SAMPLES) n_samples = ADC_CAPTURE_MAX_SAMPLES;
    if (settle_ms == 0u)               settle_ms = IS_POC_DEFAULT_SETTLE_MS;
    if (settle_ms > IS_POC_MAX_SETTLE_MS) settle_ms = IS_POC_MAX_SETTLE_MS;

    ensure_armed();

    /* Issue 1 fix: use biba_hal_motor_pwm_left/right (the original plan
     * referenced a nonexistent HAL setter). */
    if (adc_chan == BIBA_ADC_CHAN_IS_LEFT) {
        biba_hal_motor_pwm_left(signed_duty);
    } else {
        biba_hal_motor_pwm_right(signed_duty);
    }

    delay(settle_ms);

    adc_capture_init(sps);
    bool ok = adc_capture_burst(adc_chan, n_samples, s_buf);

    /* Always stop the motor after capture. */
    if (adc_chan == BIBA_ADC_CHAN_IS_LEFT) {
        biba_hal_motor_pwm_left(0.0f);
    } else {
        biba_hal_motor_pwm_right(0.0f);
    }

    if (!ok) {
        Serial.println("ERROR capture timeout");
        return;
    }

    /* Issue 2 fix: include dir=FWD|REV in CAPTURE_START header.
     * settle_ms is echoed so post-hoc analysis knows the spin-up window. */
    Serial.printf("CAPTURE_START duty=%d dir=%s chan=%d sps=%lu n=%u settle_ms=%lu\n",
                  (int)(fabsf(signed_duty) * 100.0f),
                  is_fwd ? "FWD" : "REV",
                  (int)adc_chan,
                  (unsigned long)sps,
                  (unsigned)n_samples,
                  (unsigned long)settle_ms);

    for (uint16_t i = 0; i < n_samples; i++) {
        Serial.print(s_buf[i]);
        Serial.print((i + 1) < n_samples ? ',' : '\n');
    }
    Serial.println("CAPTURE_END");
}

/* --- Closed-loop PI controller --------------------------------------- */
/* Per-iteration capture parameters: 100 ms window → 10 Hz update rate.
 * Halved from 2048 to reduce felt jerk: plant τ < 200 ms so the old
 * 200 ms period was slower than the plant, causing large discrete steps. */
#define RPMRUN_N_SAMPLES   1024u
#define RPMRUN_SPS         10000u
#define RPMRUN_DT_S        ((float)RPMRUN_N_SAMPLES / (float)RPMRUN_SPS)
#define RPMRUN_MAX_DUR_MS  60000u
#define ADC_VREF_V         3.3f
#define ADC_FULLSCALE      4095.0f

/* Sub-window Schmitt-trigger ZC detector (A2 algorithm).
 *
 * Splits the input into ZC_SUBWIN_K equal blocks; computes local min/max/mean
 * per block and counts Schmitt crossings within that block.  Local baselines
 * remove low-frequency DC drift that ruins a single global-mean detector
 * during PWM transients (verified on bench: A2 mean-error 43 Hz vs A1
 * 92 Hz on TRAP sweep, 44 vs 164 on SIN sweep).
 *
 * Frequency estimate = total_crossings * 0.5 * sps / n  (each commutation
 * period contributes two crossings).
 *
 * Returns 0.0 when no block has enough AC content.
 */
#define ZC_SUBWIN_K          8u
#define ZC_SUBWIN_MIN_PKPK   120u /* per-block AC threshold (LSB); 30 was too low — PWM noise gives pkpk≈117 which produced ~110 Hz false readings */

static float zc_freq_hz(const uint16_t *buf, uint16_t n, uint32_t sps)
{
    if (n < ZC_SUBWIN_K * 4u) return 0.0f;
    uint16_t blk = n / (uint16_t)ZC_SUBWIN_K;
    uint16_t total = 0;
    uint16_t active_blocks = 0;
    for (uint16_t b = 0; b < ZC_SUBWIN_K; ++b) {
        const uint16_t *seg = buf + (uint32_t)b * blk;
        uint16_t mn = seg[0], mx = seg[0];
        for (uint16_t i = 1; i < blk; ++i) {
            if (seg[i] < mn) mn = seg[i];
            if (seg[i] > mx) mx = seg[i];
        }
        uint16_t pkpk = (uint16_t)(mx - mn);
        if (pkpk < ZC_SUBWIN_MIN_PKPK) continue;
        active_blocks++;
        int32_t mid  = ((int32_t)mn + (int32_t)mx) / 2;
        int32_t hyst = (int32_t)pkpk / 4;
        int32_t up = mid + hyst, dn = mid - hyst;
        int state = (seg[0] > (uint16_t)mid) ? 1 : -1;
        for (uint16_t i = 1; i < blk; ++i) {
            int32_t v = (int32_t)seg[i];
            if (state > 0 && v < dn) { state = -1; total++; }
            else if (state < 0 && v > up) { state = 1; total++; }
        }
    }
    /* Require evidence from at least 2 blocks to call it real signal. */
    if (active_blocks < 2u || total < 2u) return 0.0f;
    return (float)total * 0.5f * (float)sps / (float)n;
}

static float adc_to_amps(float adc_mean)
{
    /* Convert mean ADC raw to current via BIBA_IS_AMPS_PER_VOLT.
     * Baseline (IS at duty=0) is subtracted in cmd_rpmrun() before this
     * function is called, so adc_mean here is already baseline-relative. */
    float v = adc_mean * ADC_VREF_V / ADC_FULLSCALE;
    return v * BIBA_IS_AMPS_PER_VOLT;
}

/* Feed-forward calibration constants (measured via STEPRUN 20→50):
 * freq_hz ≈ FF_SLOPE * duty_pct - FF_DEAD
 * duty_ff = (target_hz + FF_DEAD) / (FF_SLOPE * 100) */
#define RPMRUN_FF_SLOPE_DEFAULT  10.13f   /* Hz per percent duty */
#define RPMRUN_FF_DEAD_DEFAULT   74.6f    /* Hz dead-zone offset  */

static void cmd_rpmrun(float target_hz, uint32_t duration_ms,
                       float kp, float ki, float stiction_floor,
                       float ff_slope, float ff_dead,
                       uint8_t motor)   /* 0=LEFT, 1=RIGHT */
{
    if (duration_ms > RPMRUN_MAX_DUR_MS) duration_ms = RPMRUN_MAX_DUR_MS;
    if (target_hz < 0.0f)    target_hz = 0.0f;
    if (target_hz > 2000.0f) target_hz = 2000.0f;
    const uint8_t adc_chan = motor ? BIBA_ADC_CHAN_IS_RIGHT : BIBA_ADC_CHAN_IS_LEFT;

    ensure_armed();

    /* 1. Baseline IS reading with motor off — DC offset on the IS line. */
    if (motor) biba_hal_motor_pwm_right(0.0f); else biba_hal_motor_pwm_left(0.0f);
    delay(200);
    adc_capture_init(RPMRUN_SPS);
    if (!adc_capture_burst(adc_chan, RPMRUN_N_SAMPLES, s_buf)) {
        Serial.println("ERROR baseline capture timeout");
        return;
    }
    uint32_t bl_sum = 0;
    for (uint16_t i = 0; i < RPMRUN_N_SAMPLES; ++i) bl_sum += s_buf[i];
    float baseline_adc = (float)bl_sum / (float)RPMRUN_N_SAMPLES;

    /* Feed-forward duty for target_hz (open-loop calibration). */
    float ff_duty = 0.0f;
    if (ff_slope > 0.0f && target_hz > 0.0f) {
        ff_duty = (target_hz + ff_dead) / (ff_slope * 100.0f);
        if (ff_duty < 0.0f) ff_duty = 0.0f;
        if (ff_duty > 1.0f) ff_duty = 1.0f;
    }

    Serial.printf("RPMRUN_START target=%.2f duration_ms=%lu kp=%.4f ki=%.4f stiction=%.2f ff_duty=%.3f baseline_adc=%.1f\n",
                  target_hz, (unsigned long)duration_ms, kp, ki, stiction_floor, ff_duty, baseline_adc);
    Serial.println("RPM_DATA t_ms,target_hz,meas_hz,duty_pct,curr_a,err_hz,i_term,p_term");

    float duty = 0.0f;
    float prev_duty = 0.0f;
    float integral = 0.0f;
    /* EMA filter for ZC frequency.  Alpha=0.7 → each new reading gets 70 %
     * weight.  Fast convergence: 2 loop cycles (200 ms) to track a step.
     * Transient blanking (zc_skip) already prevents noisy settle readings
     * from entering; P/I clamps bound any residual noise impact. */
    float meas_ema = 0.0f;
    const float EMA_ALPHA = 0.7f;
    uint32_t t_start = millis();

    while ((millis() - t_start) < duration_ms) {
        /* Capture window — drives loop period (100 ms @ N=1024, sps=10k). */
        if (!adc_capture_burst(adc_chan, RPMRUN_N_SAMPLES, s_buf)) {
            Serial.println("ERROR capture timeout");
            break;
        }
        /* Transient blanking: A2 sub-window ZC handles slow drift, but it
         * still can't measure commutation period when the duty itself is
         * changing mid-window (period non-stationary).  Skip a chunk of
         * leading samples proportional to the duty step:
         *   Δduty > 3 pp  → skip 256 samples (25 ms)
         *   Δduty > 8 pp  → skip 512 samples (50 ms)
         * Below 3 pp the change is small enough that the rest of the window
         * still contains usable periodicity. */
        float d_step = fabsf(duty - prev_duty);
        uint16_t zc_skip = 0u;
        if      (d_step > 0.08f) zc_skip = 512u;
        else if (d_step > 0.03f) zc_skip = 256u;
        float meas_raw = zc_freq_hz(s_buf + zc_skip,
                                    RPMRUN_N_SAMPLES - zc_skip,
                                    RPMRUN_SPS);
        /* EMA update with two-sided validity gate.
         *
         * Low-side: at no-load high speed back-EMF ≈ Vbat → IS current → 0
         * → noise-floor ZC returns spurious ≈20-80 Hz instead of 0.
         * Reject raw below 80 Hz (below stiction operating point).
         *
         * High-side: when the wheel is stalled under load, full current flows
         * at PWM switching rate → IS-pin shows large current ripple at PWM
         * frequency → ZC detector can return 500-1200 Hz even though the
         * wheel is stationary.  Cap at target_hz * 2.5 + 300 Hz; any reading
         * above that is physically impossible at the commanded duty point.
         *
         * When raw == 0 (no ZC at all — wheel stopped or transient blanked):
         * decay EMA by ×0.5 each cycle so that if the wheel truly stalls the
         * controller sees meas → 0 and can raise duty to restart.  Without
         * this decay the EMA stays frozen at the last high value and the
         * integral winds negative, cutting motor power permanently. */
        const float ZC_MIN_VALID_HZ = 80.0f;
        const float ZC_MAX_VALID_HZ = target_hz * 2.5f + 300.0f;
        if (meas_raw >= ZC_MIN_VALID_HZ && meas_raw <= ZC_MAX_VALID_HZ) {
            meas_ema = EMA_ALPHA * meas_raw + (1.0f - EMA_ALPHA) * meas_ema;
        } else if (meas_raw == 0.0f) {
            /* Wheel stopped / no ZC: decay slowly toward 0 so the controller
             * can eventually recover if the wheel truly stalls.
             * Factor 0.9 per cycle (100 ms) → half-life ≈ 660 ms (6-7 cycles).
             * The previous 0.5 factor (half-life = 1 cycle) caused the EMA to
             * collapse during normal transient-blanking (2 zero cycles after a
             * duty step), making the controller think the wheel stopped every
             * time it changed duty. */
            meas_ema *= 0.9f;
        }
        /* else: out-of-range noise spike — hold current EMA unchanged. */
        /* Use filtered value for control; expose both in telemetry. */
        float meas_hz = meas_ema;

        uint32_t sum = 0;
        for (uint16_t i = 0; i < RPMRUN_N_SAMPLES; ++i) sum += s_buf[i];
        float mean_adc = (float)sum / (float)RPMRUN_N_SAMPLES;
        float curr_a = adc_to_amps(mean_adc - baseline_adc);

        /* PI update with conditional integration (anti-windup).
         * Three rules:
         *  1. Don't integrate while the duty is saturated at 0 or 1 —
         *     pumping the I term during saturation creates the 100%/0%
         *     limit cycle we observed ("колесо стучит").
         *  2. Don't integrate when meas_hz==0 from the noise floor —
         *     otherwise the controller pumps duty when the wheel is
         *     not yet moving and overshoots wildly.
         *  3. Soft integral clamp keeps the I contribution to duty in
         *     [0, +1.5] regardless of Ki. */
        float err = target_hz - meas_hz;
        bool sat_high = duty >= 0.999f;
        bool sat_low  = duty <= 0.001f;
        bool can_integrate =
            !(sat_high && err > 0.0f) &&
            !(sat_low  && err < 0.0f);
        /* Only integrate when the measurement is plausibly stable: require
         * meas_hz above a minimum threshold so that transient spin-up ZC
         * readings (< 50 Hz) don't accumulate a large integral before the
         * motor has actually reached steady state. */
        if (can_integrate && meas_hz > 50.0f) {
            integral += err * RPMRUN_DT_S;
        }
        /* Asymmetric integral clamp: PI can add up to +3 pp duty to fight
         * load, but can only subtract up to -1 pp below FF.  FF is already
         * calibrated to within ±8 Hz; there is almost never a need to
         * reduce duty significantly below FF.  A symmetric -3 pp clamp
         * caused the motor to stall after stall-noise spiked the EMA high:
         * I(-3%) + P(-5%) pulled duty to 9 %, below the real stiction
         * threshold, and the motor could not restart for 700+ ms. */
        float i_clamp_pos = 0.03f / (ki + 1e-6f);
        float i_clamp_neg = 0.01f / (ki + 1e-6f);
        if (integral >  i_clamp_pos) integral =  i_clamp_pos;
        if (integral < -i_clamp_neg) integral = -i_clamp_neg;
        float p_term = kp * err;
        float i_term = ki * integral;
        /* When meas==0 the ZC has no measurement (motor not yet spinning or
         * transient blanked).  Trust the feed-forward alone — adding P on
         * top when err=target produces large overshoot that causes the
         * same limit-cycle we just fixed.  Once the wheel is spinning the
         * P term corrects small residuals around the FF operating point.
         * Also clamp P contribution to ±10 % duty so a single bad ZC read
         * cannot cause a large step. */
        if (meas_hz == 0.0f) p_term = 0.0f;
        if (p_term >  0.05f) p_term =  0.05f;
        if (p_term < -0.05f) p_term = -0.05f;
        duty = ff_duty + p_term + i_term;
        /* Dead-zone / stiction handling.  Open-loop measurement:
         * the brushed motor + BTS7960 needs ~20 %% duty to break stiction,
         * and below that produces no measurable IS modulation.  Two rules:
         *
         *  - If the controller asks for duty in (0, 0.20) and target > 0,
         *    snap up to 0.20 (stiction kick).  Without this the requested
         *    duty would heat the FETs without spinning the wheel.
         *  - If the wheel is already spinning (meas_hz > 0) and the
         *    controller asks for duty < 0.20, hold at 0.20 instead of
         *    falling to 0 \u2014 dropping to 0 causes the wheel to coast
         *    down then need another stiction kick, producing the
         *    pulsing limit cycle we observed at unreachable targets.
         *  - True full stop only when target == 0. */
        bool wheel_spinning = (meas_hz > 0.0f);
        if (target_hz > 0.0f && duty > 0.0f && duty < stiction_floor) {
            duty = stiction_floor;
        }
        if (target_hz > 0.0f && wheel_spinning && duty < stiction_floor) {
            duty = stiction_floor;
        }
        if (duty < 0.0f) duty = 0.0f;
        if (duty > 1.0f) duty = 1.0f;
        prev_duty = duty;
        if (motor) biba_hal_motor_pwm_right(duty); else biba_hal_motor_pwm_left(duty);

        Serial.printf("RPM_DATA %lu,%.2f,%.2f,%.1f,%.2f,%.2f,%.3f,%.3f\n",
                      (unsigned long)(millis() - t_start),
                      target_hz, meas_hz, duty * 100.0f, curr_a,
                      err, i_term, p_term);
        /* raw ZC value (pre-filter) logged as comment for diagnostics */
        if (meas_raw != meas_hz) {
            Serial.printf("# raw_hz=%.2f\n", meas_raw);
        }

        /* Check for STOP request between iterations (single-char peek). */
        if (Serial.available()) {
            String line = Serial.readStringUntil('\n');
            line.trim();
            if (line == "STOP") {
                Serial.println("RPMRUN_ABORT stop requested");
                break;
            }
        }
    }

    if (motor) biba_hal_motor_pwm_right(0.0f); else biba_hal_motor_pwm_left(0.0f);
    Serial.println("RPMRUN_END");
}

/* --- CAPTURE_BOTH: drives BOTH motors, captures raw waveform on each ----
 * CAPTURE_BOTH <FWD|REV> <duty_pct> [n_samples [sps [settle_ms]]]
 *
 * Drives both motors at the same duty, waits settle_ms, then DMA-captures
 * IS_LEFT (chan 0) and IS_RIGHT (chan 1) back-to-back while both motors
 * remain running.  Both motors are stopped after the second capture.
 *
 * Response:
 *   CAPTURE2_START duty=<pct> dir=<FWD|REV> sps=<sps> n=<n> settle_ms=<m>
 *   CAPTURE2_CHAN 0
 *   <n comma-separated 12-bit ADC values>
 *   CAPTURE2_CHAN 1
 *   <n comma-separated 12-bit ADC values>
 *   CAPTURE2_END
 */
static void cmd_capture_both(float signed_duty, bool is_fwd,
                              uint16_t n_samples, uint32_t sps,
                              uint32_t settle_ms)
{
    if (signed_duty > 1.0f)  signed_duty = 1.0f;
    if (signed_duty < -1.0f) signed_duty = -1.0f;
    if (n_samples > (ADC_CAPTURE_MAX_SAMPLES / 2u)) {
        n_samples = ADC_CAPTURE_MAX_SAMPLES / 2u;
    }
    if (settle_ms == 0u)                    settle_ms = IS_POC_DEFAULT_SETTLE_MS;
    if (settle_ms > IS_POC_MAX_SETTLE_MS)   settle_ms = IS_POC_MAX_SETTLE_MS;

    ensure_armed();

    biba_hal_motor_pwm_left(signed_duty);
    biba_hal_motor_pwm_right(signed_duty);
    delay(settle_ms);

    adc_capture_init(sps * 2u);

    Serial.printf("CAPTURE2_START duty=%d dir=%s sps=%lu n=%u settle_ms=%lu\n",
                  (int)(fabsf(signed_duty) * 100.0f),
                  is_fwd ? "FWD" : "REV",
                  (unsigned long)sps,
                  (unsigned)n_samples,
                  (unsigned long)settle_ms);

    s_capture_pair_done = false;
    if (!adc_capture_start_async_pair(BIBA_ADC_CHAN_IS_LEFT,
                                      BIBA_ADC_CHAN_IS_RIGHT,
                                      n_samples,
                                      s_pair_buf,
                                      on_capture_pair_done)) {
        biba_hal_motor_pwm_left(0.0f);
        biba_hal_motor_pwm_right(0.0f);
        Serial.println("ERROR capture busy");
        return;
    }

    uint32_t t0 = millis();
    while (!s_capture_pair_done) {
        if ((millis() - t0) > 500u) {
            biba_hal_motor_pwm_left(0.0f);
            biba_hal_motor_pwm_right(0.0f);
            Serial.println("ERROR capture timeout");
            return;
        }
    }

    for (uint8_t ch = 0; ch < 2u; ++ch) {
        Serial.printf("CAPTURE2_CHAN %u\n", (unsigned)ch);
        for (uint16_t i = 0; i < n_samples; ++i) {
            const uint32_t idx = (uint32_t)i * 2u + (uint32_t)ch;
            Serial.print(s_pair_buf[idx]);
            Serial.print((i + 1u) < n_samples ? ',' : '\n');
        }
    }

    biba_hal_motor_pwm_left(0.0f);
    biba_hal_motor_pwm_right(0.0f);
    Serial.println("CAPTURE2_END");
}

/* --- CHANTEST: drives one or both motors; captures BOTH ADC channels ----
 * CHANTEST <L|R|BOTH> FWD <duty_pct> [settle_ms]
 * Drives the specified motor(s), then captures ADC chan 0 AND chan 1 and
 * reports ZC Hz + peak-to-peak for each — lets you confirm which physical
 * ADC channel corresponds to which wheel's IS signal. */
static void cmd_chantest(uint8_t run_left, uint8_t run_right,
                         float signed_duty, uint32_t settle_ms)
{
    if (settle_ms == 0u) settle_ms = IS_POC_DEFAULT_SETTLE_MS;
    if (settle_ms > IS_POC_MAX_SETTLE_MS) settle_ms = IS_POC_MAX_SETTLE_MS;
    ensure_armed();
    if (run_left)  biba_hal_motor_pwm_left(signed_duty);
    if (run_right) biba_hal_motor_pwm_right(signed_duty);
    delay(settle_ms);
    adc_capture_init(RPMRUN_SPS);
    Serial.printf("CHANTEST motors=%s%s duty=%.0f settle=%lu\n",
                  run_left  ? "L" : "",
                  run_right ? "R" : "",
                  signed_duty * 100.0f,
                  (unsigned long)settle_ms);
    Serial.println("CHANTEST_DATA chan,hz,pkpk,label");
    for (uint8_t ch = 0; ch < 2; ++ch) {
        bool ok = adc_capture_burst(ch, RPMRUN_N_SAMPLES, s_buf);
        if (!ok) { Serial.println("ERROR capture timeout"); break; }
        float hz = zc_freq_hz(s_buf, RPMRUN_N_SAMPLES, RPMRUN_SPS);
        uint16_t mn = s_buf[0], mx = s_buf[0];
        for (uint16_t i = 1; i < RPMRUN_N_SAMPLES; ++i) {
            if (s_buf[i] < mn) mn = s_buf[i];
            if (s_buf[i] > mx) mx = s_buf[i];
        }
        uint16_t pkpk = (uint16_t)(mx - mn);
        const char *label = (ch == BIBA_ADC_CHAN_IS_LEFT) ? "IS_LEFT" : "IS_RIGHT";
        Serial.printf("CHANTEST_DATA %u,%.2f,%u,%s\n", (unsigned)ch, hz, (unsigned)pkpk, label);
    }
    biba_hal_motor_pwm_left(0.0f);
    biba_hal_motor_pwm_right(0.0f);
    Serial.println("CHANTEST_END");
}

/* --- RPMRUN_BOTH: dual closed-loop PI on both wheels simultaneously ------
 * RPMRUN_BOTH <L_target_hz> <R_target_hz> <duration_ms>
 *             [kp_x1000000 ki_x1000000 [stiction_x100]]
 *
 * Captures LEFT then RIGHT IS channel each iteration (~200 ms loop @ 10 Hz
 * per wheel).  Streams CSV:
 *   RPM2_DATA t_ms,tgt_L,tgt_R,meas_L,meas_R,duty_L_pct,duty_R_pct
 */
static void cmd_rpmrun_both(float tgt_l, float tgt_r, uint32_t duration_ms,
                             float kp, float ki, float stiction,
                             float ff_slope, float ff_dead)
{
    if (duration_ms > RPMRUN_MAX_DUR_MS) duration_ms = RPMRUN_MAX_DUR_MS;
    if (tgt_l < 0.0f) tgt_l = 0.0f;
    if (tgt_r < 0.0f) tgt_r = 0.0f;
    if (tgt_l > 2000.0f) tgt_l = 2000.0f;
    if (tgt_r > 2000.0f) tgt_r = 2000.0f;

    ensure_armed();

    /* Baseline: both motors off */
    biba_hal_motor_pwm_left(0.0f);
    biba_hal_motor_pwm_right(0.0f);
    delay(200);
    adc_capture_init(RPMRUN_SPS);
    /* baseline left */
    if (!adc_capture_burst(BIBA_ADC_CHAN_IS_LEFT, RPMRUN_N_SAMPLES, s_buf)) {
        Serial.println("ERROR baseline_L"); return;
    }
    uint32_t bl = 0;
    for (uint16_t i = 0; i < RPMRUN_N_SAMPLES; ++i) bl += s_buf[i];
    float bl_l = (float)bl / (float)RPMRUN_N_SAMPLES;
    /* baseline right */
    if (!adc_capture_burst(BIBA_ADC_CHAN_IS_RIGHT, RPMRUN_N_SAMPLES, s_buf)) {
        Serial.println("ERROR baseline_R"); return;
    }
    bl = 0;
    for (uint16_t i = 0; i < RPMRUN_N_SAMPLES; ++i) bl += s_buf[i];
    float bl_r = (float)bl / (float)RPMRUN_N_SAMPLES;

    Serial.printf("RPMRUN2_START tgt_L=%.1f tgt_R=%.1f duration_ms=%lu kp=%.4f ki=%.4f stiction=%.2f bl_L=%.0f bl_R=%.0f\n",
                  tgt_l, tgt_r, (unsigned long)duration_ms,
                  kp, ki, stiction, bl_l, bl_r);
    Serial.println("RPM2_DATA t_ms,tgt_L,tgt_R,meas_L,meas_R,duty_L_pct,duty_R_pct,raw_L,raw_R");

    /* PI state */
    float duty_l = 0.0f, duty_r = 0.0f;
    float prev_l = 0.0f, prev_r = 0.0f;
    float int_l  = 0.0f, int_r  = 0.0f;
    float ema_l  = 0.0f, ema_r  = 0.0f;
    const float EMA_A = 0.7f;
    const float ff_l = (ff_slope > 0.0f && tgt_l > 0.0f)
                       ? (tgt_l + ff_dead) / (ff_slope * 100.0f) : 0.0f;
    const float ff_r = (ff_slope > 0.0f && tgt_r > 0.0f)
                       ? (tgt_r + ff_dead) / (ff_slope * 100.0f) : 0.0f;
    uint32_t t0 = millis();

    while ((millis() - t0) < duration_ms) {
        /* --- capture LEFT channel --- */
        if (!adc_capture_burst(BIBA_ADC_CHAN_IS_LEFT, RPMRUN_N_SAMPLES, s_buf)) {
            Serial.println("ERROR cap_L"); break;
        }
        float dl = fabsf(duty_l - prev_l);
        uint16_t sk = (dl > 0.08f) ? 512u : (dl > 0.03f) ? 256u : 0u;
        float raw_l = zc_freq_hz(s_buf + sk, RPMRUN_N_SAMPLES - sk, RPMRUN_SPS);
        const float hi_l = tgt_l * 2.5f + 300.0f;
        if (raw_l >= 80.0f && raw_l <= hi_l) ema_l = EMA_A * raw_l + (1.0f - EMA_A) * ema_l;
        else if (raw_l == 0.0f) ema_l *= 0.9f;

        /* --- capture RIGHT channel --- */
        if (!adc_capture_burst(BIBA_ADC_CHAN_IS_RIGHT, RPMRUN_N_SAMPLES, s_buf)) {
            Serial.println("ERROR cap_R"); break;
        }
        float dr = fabsf(duty_r - prev_r);
        sk = (dr > 0.08f) ? 512u : (dr > 0.03f) ? 256u : 0u;
        float raw_r = zc_freq_hz(s_buf + sk, RPMRUN_N_SAMPLES - sk, RPMRUN_SPS);
        const float hi_r = tgt_r * 2.5f + 300.0f;
        if (raw_r >= 80.0f && raw_r <= hi_r) ema_r = EMA_A * raw_r + (1.0f - EMA_A) * ema_r;
        else if (raw_r == 0.0f) ema_r *= 0.9f;

        /* --- PI update LEFT --- */
        {
            float err = tgt_l - ema_l;
            float i_clamp_p = 0.03f / (ki + 1e-6f);
            float i_clamp_n = 0.01f / (ki + 1e-6f);
            bool sat_h = duty_l >= 0.999f, sat_l2 = duty_l <= 0.001f;
            if (!(sat_h && err > 0.0f) && !(sat_l2 && err < 0.0f) && ema_l > 50.0f)
                int_l += err * RPMRUN_DT_S;
            if (int_l >  i_clamp_p) int_l =  i_clamp_p;
            if (int_l < -i_clamp_n) int_l = -i_clamp_n;
            float p = (ema_l == 0.0f) ? 0.0f : kp * err;
            if (p >  0.05f) p =  0.05f;
            if (p < -0.05f) p = -0.05f;
            prev_l = duty_l;
            duty_l = ff_l + p + ki * int_l;
            if (tgt_l > 0.0f && duty_l > 0.0f && duty_l < stiction) duty_l = stiction;
            if (tgt_l > 0.0f && ema_l > 0.0f && duty_l < stiction) duty_l = stiction;
            if (duty_l < 0.0f) duty_l = 0.0f;
            if (duty_l > 1.0f) duty_l = 1.0f;
        }
        /* --- PI update RIGHT --- */
        {
            float err = tgt_r - ema_r;
            float i_clamp_p = 0.03f / (ki + 1e-6f);
            float i_clamp_n = 0.01f / (ki + 1e-6f);
            bool sat_h = duty_r >= 0.999f, sat_l2 = duty_r <= 0.001f;
            if (!(sat_h && err > 0.0f) && !(sat_l2 && err < 0.0f) && ema_r > 50.0f)
                int_r += err * RPMRUN_DT_S;
            if (int_r >  i_clamp_p) int_r =  i_clamp_p;
            if (int_r < -i_clamp_n) int_r = -i_clamp_n;
            float p = (ema_r == 0.0f) ? 0.0f : kp * err;
            if (p >  0.05f) p =  0.05f;
            if (p < -0.05f) p = -0.05f;
            prev_r = duty_r;
            duty_r = ff_r + p + ki * int_r;
            if (tgt_r > 0.0f && duty_r > 0.0f && duty_r < stiction) duty_r = stiction;
            if (tgt_r > 0.0f && ema_r > 0.0f && duty_r < stiction) duty_r = stiction;
            if (duty_r < 0.0f) duty_r = 0.0f;
            if (duty_r > 1.0f) duty_r = 1.0f;
        }
        biba_hal_motor_pwm_left(duty_l);
        biba_hal_motor_pwm_right(duty_r);

        Serial.printf("RPM2_DATA %lu,%.1f,%.1f,%.1f,%.1f,%.1f,%.1f,%.1f,%.1f\n",
                      (unsigned long)(millis() - t0),
                      tgt_l, tgt_r, ema_l, ema_r,
                      duty_l * 100.0f, duty_r * 100.0f,
                      raw_l, raw_r);

        if (Serial.available()) {
            String ln = Serial.readStringUntil('\n');
            ln.trim();
            if (ln == "STOP") { Serial.println("RPMRUN2_ABORT"); break; }
        }
    }
    biba_hal_motor_pwm_left(0.0f);
    biba_hal_motor_pwm_right(0.0f);
    Serial.println("RPMRUN2_END");
}

/* --- Closed-loop tracking: time-varying setpoint --------------------- */
/* RPMTRACK <SIN|TRAP> <base_hz> <amp_hz> <p_start_ms> <p_end_ms>
 *          <duration_ms> [kp_x1000000 ki_x1000000 [stiction_x100]]
 *
 * Same PI+FF controller as RPMRUN but the setpoint follows a sin or
 * trapezoidal profile with a linear chirp on the period.  Useful to
 * stress-test the closed-loop response to ramp/step/hold sequences.
 *
 * target_hz(t) = base_hz + amp_hz × shape(phase(t))
 * period(t)    = p_start + (p_end - p_start) × t / duration     (linear chirp)
 *
 * Output: same format as RPMRUN (RPM_DATA t,target,meas,duty,curr,err,i,p)
 */
static void cmd_rpmtrack(const char *shape,
                         float base_hz, float amp_hz,
                         uint32_t p_start_ms, uint32_t p_end_ms,
                         uint32_t duration_ms,
                         float kp, float ki, float stiction_floor,
                         float ff_slope, float ff_dead)
{
    bool is_sin  = (strcmp(shape, "SIN")  == 0);
    bool is_trap = (strcmp(shape, "TRAP") == 0);
    if (!is_sin && !is_trap) {
        Serial.println("ERR rpmtrack shape must be SIN or TRAP");
        return;
    }
    if (duration_ms > RPMRUN_MAX_DUR_MS) duration_ms = RPMRUN_MAX_DUR_MS;
    if (p_start_ms < 200u)   p_start_ms = 200u;
    if (p_end_ms   < 200u)   p_end_ms   = 200u;

    ensure_armed();

    /* Baseline */
    biba_hal_motor_pwm_left(0.0f);
    delay(200);
    adc_capture_init(RPMRUN_SPS);
    if (!adc_capture_burst(BIBA_ADC_CHAN_IS_LEFT, RPMRUN_N_SAMPLES, s_buf)) {
        Serial.println("ERROR baseline capture timeout");
        return;
    }
    uint32_t bl_sum = 0;
    for (uint16_t i = 0; i < RPMRUN_N_SAMPLES; ++i) bl_sum += s_buf[i];
    float baseline_adc = (float)bl_sum / (float)RPMRUN_N_SAMPLES;

    Serial.printf("RPMTRACK_START shape=%s base=%.1f amp=%.1f p_start=%lu p_end=%lu"
                  " duration=%lu kp=%.4f ki=%.4f stiction=%.2f baseline_adc=%.1f\n",
                  shape, base_hz, amp_hz,
                  (unsigned long)p_start_ms, (unsigned long)p_end_ms,
                  (unsigned long)duration_ms, kp, ki, stiction_floor, baseline_adc);
    Serial.println("RPM_DATA t_ms,target_hz,meas_hz,duty_pct,curr_a,err_hz,i_term,p_term");

    float duty       = 0.0f;
    float prev_duty  = 0.0f;
    float integral   = 0.0f;
    float meas_ema   = 0.0f;
    float prev_dir   = 1.0f;   /* last commanded direction (+1 / -1) */
    const float EMA_ALPHA = 0.7f;
    uint32_t t_start = millis();

    while (true) {
        uint32_t t_now = millis() - t_start;
        if (t_now >= duration_ms) break;

        /* Time-varying setpoint with linear period chirp */
        float frac = (float)t_now / (float)duration_ms;
        float period_ms = (float)p_start_ms
                          + frac * ((float)p_end_ms - (float)p_start_ms);
        if (period_ms < 200.0f) period_ms = 200.0f;
        float phase = fmodf((float)t_now, period_ms) / period_ms;
        float shape_val;
        if (is_sin) {
            shape_val = sinf(2.0f * (float)M_PI * phase);
        } else {
            if      (phase < 0.125f) shape_val =  (phase / 0.125f);
            else if (phase < 0.375f) shape_val =  1.0f;
            else if (phase < 0.500f) shape_val =  (1.0f - (phase - 0.375f) / 0.125f);
            else if (phase < 0.625f) shape_val = -((phase - 0.500f) / 0.125f);
            else if (phase < 0.875f) shape_val = -1.0f;
            else                     shape_val = -(1.0f - (phase - 0.875f) / 0.125f);
        }
        float target_hz = base_hz + amp_hz * shape_val;
        if (target_hz >  2000.0f) target_hz =  2000.0f;
        if (target_hz < -2000.0f) target_hz = -2000.0f;

        /* Direction and magnitude of signed setpoint */
        float tdir = (target_hz >= 0.0f) ? 1.0f : -1.0f;
        float target_mag = fabsf(target_hz);

        /* Direction change → reset integral + EMA so the controller starts
         * clean in the new direction.  Motor coasts (duty=0) this window. */
        if (tdir != prev_dir) {
            integral  = 0.0f;
            meas_ema  = 0.0f;
            duty      = 0.0f;
            prev_duty = 0.0f;
            biba_hal_motor_pwm_left(0.0f);
            prev_dir  = tdir;
            /* Still run ADC so we keep time, but skip ZC computation. */
            adc_capture_burst(BIBA_ADC_CHAN_IS_LEFT, RPMRUN_N_SAMPLES, s_buf);
            uint32_t s2 = 0;
            for (uint16_t i = 0; i < RPMRUN_N_SAMPLES; ++i) s2 += s_buf[i];
            float curr_a2 = adc_to_amps((float)s2 / (float)RPMRUN_N_SAMPLES - baseline_adc);
            Serial.printf("RPM_DATA %lu,%.2f,%.2f,%.1f,%.2f,%.2f,%.3f,%.3f\n",
                          (unsigned long)t_now,
                          target_hz, 0.0f, 0.0f, curr_a2, target_hz, 0.0f, 0.0f);
            continue;
        }

        /* FF — magnitude, then apply direction sign */
        float ff_duty = 0.0f;
        if (ff_slope > 0.0f && target_mag > 0.0f) {
            ff_duty = tdir * (target_mag + ff_dead) / (ff_slope * 100.0f);
            if (ff_duty >  1.0f) ff_duty =  1.0f;
            if (ff_duty < -1.0f) ff_duty = -1.0f;
        }

        /* Capture */
        if (!adc_capture_burst(BIBA_ADC_CHAN_IS_LEFT, RPMRUN_N_SAMPLES, s_buf)) {
            Serial.println("ERROR capture timeout");
            break;
        }

        /* Transient blanking — use signed duty change magnitude */
        float d_step = fabsf(duty - prev_duty);
        uint16_t zc_skip = 0u;
        if      (d_step > 0.08f) zc_skip = 512u;
        else if (d_step > 0.03f) zc_skip = 256u;
        float meas_raw = zc_freq_hz(s_buf + zc_skip,
                                    RPMRUN_N_SAMPLES - zc_skip,
                                    RPMRUN_SPS);

        /* EMA (magnitude) + validity gate */
        const float ZC_MIN_VALID_HZ = 80.0f;
        const float ZC_MAX_VALID_HZ = (target_mag > 0.0f ? target_mag : amp_hz)
                                      * 2.5f + 300.0f;
        if (meas_raw >= ZC_MIN_VALID_HZ && meas_raw <= ZC_MAX_VALID_HZ) {
            meas_ema = EMA_ALPHA * meas_raw + (1.0f - EMA_ALPHA) * meas_ema;
        } else if (meas_raw == 0.0f) {
            meas_ema *= 0.9f;
        }
        /* Signed measurement: attribute ZC magnitude to commanded direction */
        float meas_hz = tdir * meas_ema;

        uint32_t sum = 0;
        for (uint16_t i = 0; i < RPMRUN_N_SAMPLES; ++i) sum += s_buf[i];
        float curr_a = adc_to_amps((float)sum / (float)RPMRUN_N_SAMPLES - baseline_adc);

        /* Signed PI */
        float err = target_hz - meas_hz;
        bool sat_high = duty >= 0.999f;
        bool sat_low  = duty <= -0.999f;
        bool can_integrate =
            !(sat_high && err > 0.0f) &&
            !(sat_low  && err < 0.0f);
        if (can_integrate && fabsf(meas_hz) > 50.0f)
            integral += err * RPMRUN_DT_S;
        /* Symmetric I-clamp (directional integral handled by sign of err) */
        float i_clamp = 0.03f / (ki + 1e-6f);
        if (integral >  i_clamp) integral =  i_clamp;
        if (integral < -i_clamp) integral = -i_clamp;
        float p_term = kp * err;
        float i_term = ki * integral;
        if (meas_ema == 0.0f) p_term = 0.0f;   /* no P when wheel stopped */
        if (p_term >  0.05f) p_term =  0.05f;
        if (p_term < -0.05f) p_term = -0.05f;
        duty = ff_duty + p_term + i_term;
        /* Stiction floor: snap to ±floor when in deadband */
        bool wheel_spinning = (meas_ema > 0.0f);
        float duty_abs = fabsf(duty);
        if (target_mag > 0.0f && duty_abs > 0.0f && duty_abs < stiction_floor)
            duty = tdir * stiction_floor;
        if (target_mag > 0.0f && wheel_spinning && duty_abs < stiction_floor)
            duty = tdir * stiction_floor;
        if (duty >  1.0f) duty =  1.0f;
        if (duty < -1.0f) duty = -1.0f;
        prev_duty = duty;
        biba_hal_motor_pwm_left(duty);

        Serial.printf("RPM_DATA %lu,%.2f,%.2f,%.1f,%.2f,%.2f,%.3f,%.3f\n",
                      (unsigned long)t_now,
                      target_hz, meas_hz, duty * 100.0f, curr_a,
                      err, i_term, p_term);
        if (meas_raw != meas_ema)
            Serial.printf("# raw_hz=%.2f\n", meas_raw);

        if (Serial.available()) {
            String ln = Serial.readStringUntil('\n');
            ln.trim();
            if (ln == "STOP") { Serial.println("RPMTRACK_ABORT stop requested"); break; }
        }
    }
    biba_hal_motor_pwm_left(0.0f);
    Serial.println("RPMTRACK_END");
}

/* --- Open-loop step response ----------------------------------------- */
/* STEPRUN <duty_start_pct> <duty_end_pct> <pre_windows> <post_windows>
 *
 * Holds duty_start for pre_windows capture-windows, then instantly steps to
 * duty_end and holds for post_windows.  Each window is 200 ms (2048 @ 10kSPS).
 * Streams ZC frequency + current — no controller, pure plant response.
 *
 * Response format:
 *   STEPRUN_START from=<pct> to=<pct> pre=<n> post=<n>
 *   STEP_DATA t_ms,phase,duty_pct,meas_hz,curr_a
 *   ...
 *   STEPRUN_END
 */
static void cmd_steprun(int duty_start_pct, int duty_end_pct,
                        uint16_t pre_windows, uint16_t post_windows)
{
    if (duty_start_pct < 0)   duty_start_pct = 0;
    if (duty_start_pct > 100) duty_start_pct = 100;
    if (duty_end_pct < 0)     duty_end_pct = 0;
    if (duty_end_pct > 100)   duty_end_pct = 100;
    if (pre_windows  < 1)  pre_windows  = 1;
    if (pre_windows  > 50) pre_windows  = 50;
    if (post_windows < 1)  post_windows = 1;
    if (post_windows > 100) post_windows = 100;

    ensure_armed();

    /* Baseline with motor off */
    biba_hal_motor_pwm_left(0.0f);
    delay(200);
    adc_capture_init(RPMRUN_SPS);
    if (!adc_capture_burst(BIBA_ADC_CHAN_IS_LEFT, RPMRUN_N_SAMPLES, s_buf)) {
        Serial.println("ERROR baseline capture timeout");
        return;
    }
    uint32_t bl_sum = 0;
    for (uint16_t i = 0; i < RPMRUN_N_SAMPLES; ++i) bl_sum += s_buf[i];
    float baseline_adc = (float)bl_sum / (float)RPMRUN_N_SAMPLES;

    Serial.printf("STEPRUN_START from=%d to=%d pre=%u post=%u baseline_adc=%.1f\n",
                  duty_start_pct, duty_end_pct,
                  (unsigned)pre_windows, (unsigned)post_windows,
                  baseline_adc);
    Serial.println("STEP_DATA t_ms,phase,duty_pct,meas_hz,curr_a");

    float duty_start = duty_start_pct / 100.0f;
    float duty_end   = duty_end_pct   / 100.0f;
    uint32_t t_start = millis();

    for (uint16_t w = 0; w < pre_windows + post_windows; ++w) {
        float duty = (w < pre_windows) ? duty_start : duty_end;
        const char *phase = (w < pre_windows) ? "PRE" : "POST";
        /* Apply step exactly at the window boundary */
        biba_hal_motor_pwm_left(duty);

        /* Skip first 512 samples (50 ms) after the step to let IS settle */
        uint16_t skip = (w == pre_windows) ? 512u : 0u;
        if (!adc_capture_burst(BIBA_ADC_CHAN_IS_LEFT, RPMRUN_N_SAMPLES, s_buf)) {
            Serial.println("ERROR capture timeout");
            break;
        }
        float meas_hz = zc_freq_hz(s_buf + skip, RPMRUN_N_SAMPLES - skip, RPMRUN_SPS);

        uint32_t sum = 0;
        for (uint16_t i = 0; i < RPMRUN_N_SAMPLES; ++i) sum += s_buf[i];
        float curr_a = adc_to_amps((float)sum / (float)RPMRUN_N_SAMPLES - baseline_adc);

        Serial.printf("STEP_DATA %lu,%s,%.1f,%.2f,%.2f\n",
                      (unsigned long)(millis() - t_start),
                      phase, duty * 100.0f, meas_hz, curr_a);

        if (Serial.available()) {
            String ln = Serial.readStringUntil('\n');
            ln.trim();
            if (ln == "STOP") { Serial.println("STEPRUN_ABORT stop requested"); goto done; }
        }
    }
done:
    biba_hal_motor_pwm_left(0.0f);
    Serial.println("STEPRUN_END");
}

/* --- Open-loop duty sweep (waveform / trapezoid) --------------------- *
 *
 * SWEEP <shape> <amp_pct> <p_start_ms> <p_end_ms> <duration_ms>
 *
 *   shape:        SIN  — bidirectional sinusoid, signed duty in [-amp, +amp]
 *                 TRAP — trapezoid: rise(p/4) hold+(p/4) fall(p/4) hold-(p/4)
 *   amp_pct:      peak |duty| in % (0..80)
 *   p_start_ms:   initial modulation period in ms
 *   p_end_ms:     final period in ms (linear chirp p_start → p_end)
 *   duration_ms:  total run time
 *
 * Each loop iteration drives one 100 ms ADC window.  Per-window output:
 *   SWEEP_DATA t_ms,duty_cmd_pct,meas_hz,curr_a,pkpk_adc,zc_count
 *
 * pkpk_adc and zc_count expose the raw waveform statistics that drive
 * the ZC detector — useful for diagnosing why ZC fails during transients.
 */
static uint16_t adc_pkpk(const uint16_t *buf, uint16_t n)
{
    if (n == 0) return 0;
    uint16_t lo = buf[0], hi = buf[0];
    for (uint16_t i = 1; i < n; ++i) {
        if (buf[i] < lo) lo = buf[i];
        if (buf[i] > hi) hi = buf[i];
    }
    return (uint16_t)(hi - lo);
}

/* Same Schmitt-trigger ZC as zc_freq_hz but also reports crossing count. */
static uint16_t zc_count_only(const uint16_t *buf, uint16_t n)
{
    if (n < 2) return 0;
    uint16_t lo = buf[0], hi = buf[0];
    for (uint16_t i = 1; i < n; ++i) {
        if (buf[i] < lo) lo = buf[i];
        if (buf[i] > hi) hi = buf[i];
    }
    uint16_t pkpk = (uint16_t)(hi - lo);
    if (pkpk < 40) return 0;
    int32_t mid = ((int32_t)lo + (int32_t)hi) / 2;
    int32_t hyst = (int32_t)pkpk / 4;
    int32_t up = mid + hyst, dn = mid - hyst;
    int state = (buf[0] > (uint16_t)mid) ? 1 : -1;
    uint16_t crossings = 0;
    for (uint16_t i = 1; i < n; ++i) {
        int32_t v = (int32_t)buf[i];
        if (state > 0 && v < dn) { state = -1; crossings++; }
        else if (state < 0 && v > up) { state = 1; crossings++; }
    }
    return crossings;
}

static void cmd_sweep(const char *shape, int amp_pct,
                      uint32_t p_start_ms, uint32_t p_end_ms,
                      uint32_t duration_ms)
{
    if (amp_pct < 0)  amp_pct = 0;
    if (amp_pct > 80) amp_pct = 80;
    if (p_start_ms < 100u)   p_start_ms = 100u;
    if (p_start_ms > 10000u) p_start_ms = 10000u;
    if (p_end_ms   < 100u)   p_end_ms   = 100u;
    if (p_end_ms   > 10000u) p_end_ms   = 10000u;
    if (duration_ms > RPMRUN_MAX_DUR_MS) duration_ms = RPMRUN_MAX_DUR_MS;
    bool is_sin = (strcmp(shape, "SIN") == 0);
    bool is_trap = (strcmp(shape, "TRAP") == 0);
    if (!is_sin && !is_trap) {
        Serial.println("ERR sweep shape must be SIN or TRAP");
        return;
    }

    ensure_armed();

    /* Baseline with motor off */
    biba_hal_motor_pwm_left(0.0f);
    delay(200);
    adc_capture_init(RPMRUN_SPS);
    if (!adc_capture_burst(BIBA_ADC_CHAN_IS_LEFT, RPMRUN_N_SAMPLES, s_buf)) {
        Serial.println("ERROR baseline capture timeout");
        return;
    }
    uint32_t bl_sum = 0;
    for (uint16_t i = 0; i < RPMRUN_N_SAMPLES; ++i) bl_sum += s_buf[i];
    float baseline_adc = (float)bl_sum / (float)RPMRUN_N_SAMPLES;

    Serial.printf("SWEEP_START shape=%s amp=%d p_start=%lu p_end=%lu duration=%lu baseline_adc=%.1f\n",
                  shape, amp_pct,
                  (unsigned long)p_start_ms, (unsigned long)p_end_ms,
                  (unsigned long)duration_ms, baseline_adc);
    Serial.println("SWEEP_DATA t_ms,duty_cmd_pct,meas_hz,curr_a,pkpk_adc,zc_count");

    float amp = amp_pct / 100.0f;
    uint32_t t_start = millis();

    while (true) {
        uint32_t t_now = millis() - t_start;
        if (t_now >= duration_ms) break;

        /* Linear chirp: period(t) = p_start + (p_end - p_start) * t/duration */
        float frac = (float)t_now / (float)duration_ms;
        float period_ms = (float)p_start_ms + frac * ((float)p_end_ms - (float)p_start_ms);
        if (period_ms < 50.0f) period_ms = 50.0f;
        /* Phase in [0, 1) within current period */
        float phase = fmodf((float)t_now, period_ms) / period_ms;

        float duty;
        if (is_sin) {
            duty = amp * sinf(2.0f * (float)M_PI * phase);
        } else {
            /* Trapezoid cycle: 0 → +amp → +hold → 0 → -amp → -hold → 0
             * Eight equal phase slices (0.125 each):
             *   [0.000,0.125)  rise  0 → +amp
             *   [0.125,0.375)  hold  +amp
             *   [0.375,0.500)  fall  +amp → 0
             *   [0.500,0.625)  fall  0 → -amp
             *   [0.625,0.875)  hold  -amp
             *   [0.875,1.000]  rise  -amp → 0   */
            if      (phase < 0.125f) duty =  amp * (phase / 0.125f);
            else if (phase < 0.375f) duty =  amp;
            else if (phase < 0.500f) duty =  amp * (1.0f - (phase - 0.375f) / 0.125f);
            else if (phase < 0.625f) duty = -amp * ((phase - 0.500f) / 0.125f);
            else if (phase < 0.875f) duty = -amp;
            else                     duty = -amp * (1.0f - (phase - 0.875f) / 0.125f);
        }
        biba_hal_motor_pwm_left(duty);

        if (!adc_capture_burst(BIBA_ADC_CHAN_IS_LEFT, RPMRUN_N_SAMPLES, s_buf)) {
            Serial.println("ERROR capture timeout");
            break;
        }
        /* No transient blank in raw diagnostic mode — we WANT to see the
         * commutation spike behaviour during fast duty changes. */
        float meas_hz = zc_freq_hz(s_buf, RPMRUN_N_SAMPLES, RPMRUN_SPS);
        uint16_t zc_n = zc_count_only(s_buf, RPMRUN_N_SAMPLES);
        uint16_t pkpk = adc_pkpk(s_buf, RPMRUN_N_SAMPLES);
        uint32_t sum = 0;
        for (uint16_t i = 0; i < RPMRUN_N_SAMPLES; ++i) sum += s_buf[i];
        float curr_a = adc_to_amps((float)sum / (float)RPMRUN_N_SAMPLES - baseline_adc);

        Serial.printf("SWEEP_DATA %lu,%.1f,%.2f,%.2f,%u,%u\n",
                      (unsigned long)t_now,
                      duty * 100.0f, meas_hz, curr_a,
                      (unsigned)pkpk, (unsigned)zc_n);

        if (Serial.available()) {
            String ln = Serial.readStringUntil('\n');
            ln.trim();
            if (ln == "STOP") { Serial.println("SWEEP_ABORT stop requested"); break; }
        }
    }

    biba_hal_motor_pwm_left(0.0f);
    Serial.println("SWEEP_END");
}

/* --- SWEEPRAW --------------------------------------------------------
 * Single-period sweep with FULL raw waveform dump for offline algorithm
 * benchmarking.  Captures N consecutive 1024-sample windows into a big
 * RAM buffer (max 30 windows = 60 KB), then streams them out.
 *
 * Usage: SWEEPRAW <SIN|TRAP> <amp_pct> <period_ms> <n_windows>
 *
 * Output:
 *   SWEEPRAW_START shape=<S> amp=<p> period_ms=<m> n_windows=<n> baseline_adc=<f>
 *   SWEEPRAW_WIN <idx> <t_ms> <duty_pct>
 *   <1024 comma-separated ADC values>
 *   ... (repeat per window)
 *   SWEEPRAW_END
 */
/* Streaming sweep: no big static buffers — each window is sent over USB
 * immediately after capture.  n_windows can be up to 65535. */
#define SWEEPRAW_N_MAX  65535u
static uint16_t s_win_r[RPMRUN_N_SAMPLES]; /* RIGHT-channel window (BOTH mode) */

/* Compute duty for one sweep window given elapsed time. */
static float _sweep_duty(bool is_sin, float amp,
                         uint32_t t_now, uint32_t period_ms)
{
    float phase = fmodf((float)t_now, (float)period_ms) / (float)period_ms;
    if (is_sin) {
        return amp * sinf(2.0f * (float)M_PI * phase);
    }
    /* TRAP */
    if      (phase < 0.125f) return  amp * (phase / 0.125f);
    else if (phase < 0.375f) return  amp;
    else if (phase < 0.500f) return  amp * (1.0f - (phase - 0.375f) / 0.125f);
    else if (phase < 0.625f) return -amp * ((phase - 0.500f) / 0.125f);
    else if (phase < 0.875f) return -amp;
    else                     return -amp * (1.0f - (phase - 0.875f) / 0.125f);
}

/* Stream one window's samples as a comma-separated line. */
static void _print_win(const uint16_t *buf, uint16_t n)
{
    for (uint16_t i = 0; i < n; ++i) {
        Serial.print(buf[i]);
        Serial.print((i + 1) < n ? ',' : '\n');
    }
}

static void cmd_sweepraw(const char *shape, int amp_pct,
                         uint32_t period_ms, uint32_t n_windows)
{
    if (amp_pct < 0)  amp_pct = 0;
    if (amp_pct > 80) amp_pct = 80;
    if (period_ms < 200u)    period_ms = 200u;
    if (period_ms > 300000u) period_ms = 300000u;
    if (n_windows < 1u)          n_windows = 1u;
    if (n_windows > SWEEPRAW_N_MAX) n_windows = SWEEPRAW_N_MAX;
    bool is_sin  = (strcmp(shape, "SIN")  == 0);
    bool is_trap = (strcmp(shape, "TRAP") == 0);
    if (!is_sin && !is_trap) { Serial.println("ERR sweepraw shape must be SIN or TRAP"); return; }

    ensure_armed();
    biba_hal_motor_pwm_left(0.0f);
    delay(200);
    adc_capture_init(RPMRUN_SPS);
    if (!adc_capture_burst(BIBA_ADC_CHAN_IS_LEFT, RPMRUN_N_SAMPLES, s_buf)) {
        Serial.println("ERROR baseline capture timeout"); return;
    }
    uint32_t bl = 0;
    for (uint16_t i = 0; i < RPMRUN_N_SAMPLES; ++i) bl += s_buf[i];
    float baseline_adc = (float)bl / RPMRUN_N_SAMPLES;

    Serial.printf("SWEEPRAW_START shape=%s amp=%d period_ms=%lu n_windows=%lu baseline_adc=%.1f\n",
                  shape, amp_pct, (unsigned long)period_ms, (unsigned long)n_windows, baseline_adc);

    float amp = amp_pct / 100.0f;
    uint32_t t_start = millis();
    for (uint32_t w = 0; w < n_windows; ++w) {
        uint32_t t_now = millis() - t_start;
        float duty = _sweep_duty(is_sin, amp, t_now, period_ms);
        biba_hal_motor_pwm_left(duty);
        if (!adc_capture_burst(BIBA_ADC_CHAN_IS_LEFT, RPMRUN_N_SAMPLES, s_buf)) {
            biba_hal_motor_pwm_left(0.0f);
            Serial.println("ERROR capture timeout"); return;
        }
        Serial.printf("SWEEPRAW_WIN %lu %lu %.1f\n",
                      (unsigned long)w, (unsigned long)t_now, duty * 100.0f);
        _print_win(s_buf, RPMRUN_N_SAMPLES);
        if (Serial.available()) {
            String ln = Serial.readStringUntil('\n'); ln.trim();
            if (ln == "STOP") {
                biba_hal_motor_pwm_left(0.0f);
                Serial.println("SWEEPRAW_ABORT stop requested"); return;
            }
        }
    }
    biba_hal_motor_pwm_left(0.0f);
    Serial.println("SWEEPRAW_END");
}

/* SWEEPRAW_R: same protocol but RIGHT motor + IS_RIGHT channel */
static void cmd_sweepraw_r(const char *shape, int amp_pct,
                           uint32_t period_ms, uint32_t n_windows)
{
    if (amp_pct < 0)  amp_pct = 0;
    if (amp_pct > 80) amp_pct = 80;
    if (period_ms < 200u)    period_ms = 200u;
    if (period_ms > 300000u) period_ms = 300000u;
    if (n_windows < 1u)          n_windows = 1u;
    if (n_windows > SWEEPRAW_N_MAX) n_windows = SWEEPRAW_N_MAX;
    bool is_sin  = (strcmp(shape, "SIN")  == 0);
    bool is_trap = (strcmp(shape, "TRAP") == 0);
    if (!is_sin && !is_trap) { Serial.println("ERR shape must be SIN or TRAP"); return; }

    ensure_armed();
    biba_hal_motor_pwm_right(0.0f);
    delay(200);
    adc_capture_init(RPMRUN_SPS);
    if (!adc_capture_burst(BIBA_ADC_CHAN_IS_RIGHT, RPMRUN_N_SAMPLES, s_buf)) {
        Serial.println("ERROR baseline capture timeout"); return;
    }
    uint32_t bl = 0;
    for (uint16_t i = 0; i < RPMRUN_N_SAMPLES; ++i) bl += s_buf[i];
    float baseline_adc = (float)bl / RPMRUN_N_SAMPLES;

    Serial.printf("SWEEPRAW_START shape=%s amp=%d period_ms=%lu n_windows=%lu baseline_adc=%.1f\n",
                  shape, amp_pct, (unsigned long)period_ms, (unsigned long)n_windows, baseline_adc);

    float amp = amp_pct / 100.0f;
    uint32_t t_start = millis();
    for (uint32_t w = 0; w < n_windows; ++w) {
        uint32_t t_now = millis() - t_start;
        float duty = _sweep_duty(is_sin, amp, t_now, period_ms);
        biba_hal_motor_pwm_right(duty);
        if (!adc_capture_burst(BIBA_ADC_CHAN_IS_RIGHT, RPMRUN_N_SAMPLES, s_buf)) {
            biba_hal_motor_pwm_right(0.0f);
            Serial.println("ERROR capture timeout"); return;
        }
        Serial.printf("SWEEPRAW_WIN %lu %lu %.1f\n",
                      (unsigned long)w, (unsigned long)t_now, duty * 100.0f);
        _print_win(s_buf, RPMRUN_N_SAMPLES);
        if (Serial.available()) {
            String ln = Serial.readStringUntil('\n'); ln.trim();
            if (ln == "STOP") {
                biba_hal_motor_pwm_right(0.0f);
                Serial.println("SWEEPRAW_ABORT"); return;
            }
        }
    }
    biba_hal_motor_pwm_right(0.0f);
    Serial.println("SWEEPRAW_END");
}

/* SWEEPRAW_BOTH: BOTH motors + VBAT/IBAT in 4-channel round-robin DMA.
 * Protocol: SWEEPRAW2_START / SWEEPRAW2_WIN <idx> <t> <duty> L <vbat> <ibat>
 * / samples / SWEEPRAW2_WIN <idx> <t> <duty> R / samples / ... */
static void cmd_sweepraw_both(const char *shape, int amp_pct,
                               uint32_t period_ms, uint32_t n_windows)
{
    if (amp_pct < 0)  amp_pct = 0;
    if (amp_pct > 80) amp_pct = 80;
    if (period_ms < 200u)    period_ms = 200u;
    if (period_ms > 300000u) period_ms = 300000u;
    if (n_windows < 1u)          n_windows = 1u;
    if (n_windows > SWEEPRAW_N_MAX) n_windows = SWEEPRAW_N_MAX;
    bool is_sin  = (strcmp(shape, "SIN")  == 0);
    bool is_trap = (strcmp(shape, "TRAP") == 0);
    if (!is_sin && !is_trap) { Serial.println("ERR shape must be SIN or TRAP"); return; }

    ensure_armed();
    biba_hal_motor_pwm_left(0.0f);
    biba_hal_motor_pwm_right(0.0f);
    delay(200);

    /* 4-channel round-robin @ RPMRUN_SPS per channel = 40 kSPS total */
    adc_capture_init_4ch(RPMRUN_SPS * 4u);
    if (!adc_capture_burst_4ch(RPMRUN_N_SAMPLES, s_buf)) {
        Serial.println("ERROR baseline"); return;
    }
    uint32_t bl_l = 0, bl_r = 0;
    for (uint16_t i = 0; i < RPMRUN_N_SAMPLES; ++i) {
        bl_l += s_buf[i];
        bl_r += s_buf[RPMRUN_N_SAMPLES + i];
    }
    float bl_lf = (float)bl_l / RPMRUN_N_SAMPLES;
    float bl_rf = (float)bl_r / RPMRUN_N_SAMPLES;

    Serial.printf("SWEEPRAW2_START shape=%s amp=%d period_ms=%lu n_windows=%lu bl_L=%.1f bl_R=%.1f\n",
                  shape, amp_pct, (unsigned long)period_ms, (unsigned long)n_windows, bl_lf, bl_rf);

    float amp = amp_pct / 100.0f;
    uint32_t t_start = millis();
    for (uint32_t w = 0; w < n_windows; ++w) {
        uint32_t t_now = millis() - t_start;
        float duty = _sweep_duty(is_sin, amp, t_now, period_ms);
        biba_hal_motor_pwm_left(duty);
        biba_hal_motor_pwm_right(duty);

        /* 4-channel round-robin: IS_L, IS_R, VBAT, IBAT in one DMA burst */
        if (!adc_capture_burst_4ch(RPMRUN_N_SAMPLES, s_buf)) {
            biba_hal_motor_pwm_left(0.0f); biba_hal_motor_pwm_right(0.0f);
            Serial.println("ERROR cap_4ch"); return;
        }

        /* Compute per-channel DC means for VBAT/IBAT */
        uint32_t sum_vbat = 0, sum_ibat = 0;
        for (uint16_t i = 0; i < RPMRUN_N_SAMPLES; ++i) {
            sum_vbat += s_buf[RPMRUN_N_SAMPLES * 2 + i];
            sum_ibat += s_buf[RPMRUN_N_SAMPLES * 3 + i];
        }
        uint16_t vbat_raw = (uint16_t)(sum_vbat / RPMRUN_N_SAMPLES);
        uint16_t ibat_raw = (uint16_t)(sum_ibat / RPMRUN_N_SAMPLES);

        /* Print LEFT IS channel + VBAT/IBAT means in header */
        Serial.printf("SWEEPRAW2_WIN %lu %lu %.1f L %u %u\n",
                      (unsigned long)w, (unsigned long)t_now, duty * 100.0f,
                      (unsigned)vbat_raw, (unsigned)ibat_raw);
        _print_win(s_buf, RPMRUN_N_SAMPLES);  /* IS_LEFT samples */

        /* Print RIGHT IS channel */
        Serial.printf("SWEEPRAW2_WIN %lu %lu %.1f R\n",
                      (unsigned long)w, (unsigned long)t_now, duty * 100.0f);
        _print_win(&s_buf[RPMRUN_N_SAMPLES], RPMRUN_N_SAMPLES);  /* IS_RIGHT samples */

        if (Serial.available()) {
            String ln = Serial.readStringUntil('\n'); ln.trim();
            if (ln == "STOP") {
                biba_hal_motor_pwm_left(0.0f); biba_hal_motor_pwm_right(0.0f);
                Serial.println("SWEEPRAW2_ABORT"); return;
            }
        }
    }
    biba_hal_motor_pwm_left(0.0f);
    biba_hal_motor_pwm_right(0.0f);
    Serial.println("SWEEPRAW2_END");
}

/* CALRUN <duty_pct> <settle_ms>
 * Drive IS_LEFT motor at duty_pct% forward, wait settle_ms, then capture
 * 1024 samples @ 10 kSPS five times, compute median ZC frequency, and
 * report "IS_HZ <duty_pct> <median_hz_x100>" (×100 for 0.01 Hz resolution).
 * Always stops the motor before returning. */
static void cmd_calrun(int duty_pct, uint32_t settle_ms)
{
    if (duty_pct < 0 || duty_pct > 100 ||
        settle_ms < 100u || settle_ms > IS_POC_MAX_SETTLE_MS) {
        Serial.println("ERROR bad args");
        return;
    }

    const uint16_t n_samples = 1024u;
    const uint32_t sps = 10000u;

    ensure_armed();

    biba_hal_motor_pwm_left((float)duty_pct / 100.0f);
    delay(settle_ms);

    adc_capture_init(sps);

    float hz[5];
    bool any_fail = false;
    for (int i = 0; i < 5; ++i) {
        if (!adc_capture_burst(BIBA_ADC_CHAN_IS_LEFT, n_samples, s_buf)) {
            any_fail = true;
            break;
        }
        hz[i] = zc_freq_hz(s_buf, n_samples, sps);
    }

    biba_hal_motor_pwm_left(0.0f);

    if (any_fail) {
        Serial.println("ERROR capture timeout");
        return;
    }

    /* Insertion-sort the 5 values, take the middle (median). */
    for (int i = 1; i < 5; ++i) {
        float v = hz[i];
        int j = i - 1;
        while (j >= 0 && hz[j] > v) {
            hz[j + 1] = hz[j];
            --j;
        }
        hz[j + 1] = v;
    }
    float median_hz = hz[2];

    Serial.printf("IS_HZ %d %d\n",
                  duty_pct, (int)(median_hz * 100.0f + 0.5f));
}

void setup(void)
{
    Serial.begin(115200);
    Serial.ignoreFlowControl(true);
    biba_hal_init();
    ensure_armed();
    Serial.println("IS_POC_READY");
}

void loop(void)
{
    if (!Serial.available()) return;

    String line = Serial.readStringUntil('\n');
    line.trim();

    if (line == "PING") {
        Serial.println("PONG");
        return;
    }

    if (line == "ARM") {
        ensure_armed();
        Serial.println("OK armed");
        return;
    }

    if (line == "STOP") {
        /* Issue 6 fix: disarm on STOP. */
        biba_hal_motor_pwm_left(0.0f);
        biba_hal_motor_pwm_right(0.0f);
        biba_hal_left_enable(false);
        biba_hal_right_enable(false);
        biba_hal_ssr_set(false);
        Serial.println("OK stopped");
        return;
    }

    if (line.startsWith("CAPTURE ")) {
        /* "CAPTURE <FWD|REV> <duty_pct> <n_samples> <sps> [settle_ms]" —
         * direction token FIRST, then numeric args.  settle_ms is optional
         * (defaults to IS_POC_DEFAULT_SETTLE_MS = 1500 ms). */
        String rest = line.substring(8);             /* after "CAPTURE " */
        bool is_fwd = rest.startsWith("FWD");
        rest = rest.substring(4);                    /* skip "FWD " or "REV " */
        int duty_pct = 50;
        uint16_t n = 2048;
        uint32_t sps = 10000;
        uint32_t settle_ms = 0u;                     /* 0 → use default */
        sscanf(rest.c_str(), "%d %hu %lu %lu", &duty_pct, &n, &sps, &settle_ms);
        if (duty_pct < 0)   duty_pct = 0;
        if (duty_pct > 100) duty_pct = 100;
        float signed_duty = is_fwd ? (duty_pct / 100.0f) : -(duty_pct / 100.0f);
        uint8_t adc_chan = BIBA_ADC_CHAN_IS_LEFT;
        cmd_capture(signed_duty, is_fwd, adc_chan, n, sps, settle_ms);
        return;
    }

    if (line.startsWith("CAPTURE_R ")) {
        /* "CAPTURE_R <FWD|REV> <duty_pct> <n_samples> <sps> [settle_ms]" — right motor */
        String rest = line.substring(10);
        bool is_fwd = rest.startsWith("FWD");
        rest = rest.substring(4);
        int duty_pct = 50;
        uint16_t n = 2048;
        uint32_t sps = 10000;
        uint32_t settle_ms = 0u;
        sscanf(rest.c_str(), "%d %hu %lu %lu", &duty_pct, &n, &sps, &settle_ms);
        if (duty_pct < 0)   duty_pct = 0;
        if (duty_pct > 100) duty_pct = 100;
        float signed_duty = is_fwd ? (duty_pct / 100.0f) : -(duty_pct / 100.0f);
        cmd_capture(signed_duty, is_fwd, BIBA_ADC_CHAN_IS_RIGHT, n, sps, settle_ms);
        return;
    }

    if (line.startsWith("CAPTURE_BOTH ")) {
        /* "CAPTURE_BOTH <FWD|REV> <duty_pct> [n_samples [sps [settle_ms]]]"
         * Drives BOTH motors and captures IS_LEFT then IS_RIGHT raw waveforms
         * with both motors running throughout. */
        String rest = line.substring(13);
        bool is_fwd = rest.startsWith("FWD");
        rest = rest.substring(4);
        int duty_pct = 50;
        uint16_t n = 4096;
        uint32_t sps = 10000;
        uint32_t settle_ms = 0u;
        sscanf(rest.c_str(), "%d %hu %lu %lu", &duty_pct, &n, &sps, &settle_ms);
        if (duty_pct < 0)   duty_pct = 0;
        if (duty_pct > 100) duty_pct = 100;
        float signed_duty = is_fwd ? (duty_pct / 100.0f) : -(duty_pct / 100.0f);
        cmd_capture_both(signed_duty, is_fwd, n, sps, settle_ms);
        return;
    }

    if (line.startsWith("CHANTEST ")) {
        /* "CHANTEST <L|R|BOTH> <FWD|REV> <duty_pct> [settle_ms]" */
        String rest = line.substring(9);
        uint8_t run_l = 0, run_r = 0;
        if (rest.startsWith("BOTH")) { run_l = 1; run_r = 1; rest = rest.substring(5); }
        else if (rest.startsWith("L"))  { run_l = 1; rest = rest.substring(2); }
        else if (rest.startsWith("R"))  { run_r = 1; rest = rest.substring(2); }
        else { Serial.println("ERR: CHANTEST needs L/R/BOTH"); return; }
        bool is_fwd = rest.startsWith("FWD");
        rest = rest.substring(4);
        int duty_pct = 40;
        uint32_t settle_ms = 0;
        sscanf(rest.c_str(), "%d %lu", &duty_pct, &settle_ms);
        if (duty_pct < 0) duty_pct = 0;
        if (duty_pct > 100) duty_pct = 100;
        float sd = is_fwd ? (duty_pct / 100.0f) : -(duty_pct / 100.0f);
        cmd_chantest(run_l, run_r, sd, settle_ms);
        return;
    }

    if (line.startsWith("RPMRUN ")) {
        /* "RPMRUN <target_hz> <duration_ms> [kp_x1000000 ki_x1000000 [stiction_x100 [ff_slope_x100 ff_dead_x10]]]" */
        String rest = line.substring(7);
        float target_hz = 10.0f;
        uint32_t duration_ms = 10000;
        int kp_mil      = 2000;   /* default Kp = 0.002 */
        int ki_mil      = 10000;  /* default Ki = 0.010 */
        int stiction_pct = 12;  /* default stiction floor = 12% */
        int ff_slope_x100 = (int)(RPMRUN_FF_SLOPE_DEFAULT * 100.0f + 0.5f);  /* 1013 */
        int ff_dead_x10   = (int)(RPMRUN_FF_DEAD_DEFAULT  * 10.0f  + 0.5f);  /* 746  */
        sscanf(rest.c_str(), "%f %lu %d %d %d %d %d",
               &target_hz, &duration_ms, &kp_mil, &ki_mil,
               &stiction_pct, &ff_slope_x100, &ff_dead_x10);
        if (stiction_pct < 0)    stiction_pct = 0;
        if (stiction_pct > 50)   stiction_pct = 50;
        if (ff_slope_x100 < 0)   ff_slope_x100 = 0;
        cmd_rpmrun(target_hz, duration_ms,
                   (float)kp_mil      / 1000000.0f,
                   (float)ki_mil      / 1000000.0f,
                   (float)stiction_pct / 100.0f,
                   (float)ff_slope_x100 / 100.0f,
                   (float)ff_dead_x10   / 10.0f,
                   0 /* motor=LEFT */);
        return;
    }

    if (line.startsWith("RPMRUN_R ")) {
        /* Same as RPMRUN but drives the RIGHT motor */
        String rest = line.substring(9);
        float target_hz = 10.0f;
        uint32_t duration_ms = 10000;
        int kp_mil = 2000, ki_mil = 10000, stiction_pct = 12;
        int ff_slope_x100 = (int)(RPMRUN_FF_SLOPE_DEFAULT * 100.0f + 0.5f);
        int ff_dead_x10   = (int)(RPMRUN_FF_DEAD_DEFAULT  * 10.0f  + 0.5f);
        sscanf(rest.c_str(), "%f %lu %d %d %d %d %d",
               &target_hz, &duration_ms, &kp_mil, &ki_mil,
               &stiction_pct, &ff_slope_x100, &ff_dead_x10);
        if (stiction_pct < 0) stiction_pct = 0;
        if (stiction_pct > 50) stiction_pct = 50;
        cmd_rpmrun(target_hz, duration_ms,
                   (float)kp_mil      / 1000000.0f,
                   (float)ki_mil      / 1000000.0f,
                   (float)stiction_pct / 100.0f,
                   (float)ff_slope_x100 / 100.0f,
                   (float)ff_dead_x10   / 10.0f,
                   1 /* motor=RIGHT */);
        return;
    }

    if (line.startsWith("RPMRUN_BOTH ")) {
        /* "RPMRUN_BOTH <L_hz> <R_hz> <duration_ms>
         *              [kp_x1000000 ki_x1000000 [stiction_x100]]" */
        String rest = line.substring(11);
        float tgt_l = 300.0f, tgt_r = 300.0f;
        uint32_t dur = 30000;
        int kp_mil = 2000, ki_mil = 10000, stiction_pct = 12;
        int ff_slope_x100 = (int)(RPMRUN_FF_SLOPE_DEFAULT * 100.0f + 0.5f);
        int ff_dead_x10   = (int)(RPMRUN_FF_DEAD_DEFAULT  * 10.0f  + 0.5f);
        sscanf(rest.c_str(), "%f %f %lu %d %d %d %d %d",
               &tgt_l, &tgt_r, &dur,
               &kp_mil, &ki_mil, &stiction_pct,
               &ff_slope_x100, &ff_dead_x10);
        if (stiction_pct < 0) stiction_pct = 0;
        if (stiction_pct > 50) stiction_pct = 50;
        cmd_rpmrun_both(tgt_l, tgt_r, dur,
                        (float)kp_mil / 1000000.0f,
                        (float)ki_mil / 1000000.0f,
                        (float)stiction_pct / 100.0f,
                        (float)ff_slope_x100 / 100.0f,
                        (float)ff_dead_x10   / 10.0f);
        return;
    }

    if (line.startsWith("RPMTRACK ")) {
        /* "RPMTRACK <SIN|TRAP> <base_hz> <amp_hz> <p_start_ms> <p_end_ms>
         *           <duration_ms> [kp_x1000000 ki_x1000000 [stiction_x100]]" */
        String rest = line.substring(9);
        char shape[8] = {0};
        float base_hz = 300.0f, amp_hz = 150.0f;
        unsigned long p0 = 3000, p1 = 1000, dur = 20000;
        int kp_mil = 2000, ki_mil = 10000, stiction_pct = 12;
        int ff_slope_x100 = (int)(RPMRUN_FF_SLOPE_DEFAULT * 100.0f + 0.5f);
        int ff_dead_x10   = (int)(RPMRUN_FF_DEAD_DEFAULT  * 10.0f  + 0.5f);
        sscanf(rest.c_str(), "%7s %f %f %lu %lu %lu %d %d %d %d %d",
               shape, &base_hz, &amp_hz, &p0, &p1, &dur,
               &kp_mil, &ki_mil, &stiction_pct, &ff_slope_x100, &ff_dead_x10);
        if (stiction_pct < 0)  stiction_pct = 0;
        if (stiction_pct > 50) stiction_pct = 50;
        cmd_rpmtrack(shape, base_hz, amp_hz, (uint32_t)p0, (uint32_t)p1,
                     (uint32_t)dur,
                     (float)kp_mil       / 1000000.0f,
                     (float)ki_mil       / 1000000.0f,
                     (float)stiction_pct / 100.0f,
                     (float)ff_slope_x100 / 100.0f,
                     (float)ff_dead_x10   / 10.0f);
        return;
    }

    if (line.startsWith("STEPRUN ")) {
        /* "STEPRUN <duty_start_pct> <duty_end_pct> [pre_windows post_windows]" */
        String rest = line.substring(8);
        int ds = 0, de = 40;
        int pre = 5, post = 15;
        sscanf(rest.c_str(), "%d %d %d %d", &ds, &de, &pre, &post);
        cmd_steprun(ds, de, (uint16_t)pre, (uint16_t)post);
        return;
    }

    if (line.startsWith("CALRUN ")) {
        /* "CALRUN <duty_pct> <settle_ms>" */
        String rest = line.substring(7);
        int duty_pct = 50;
        unsigned long settle_ms = 3000;
        sscanf(rest.c_str(), "%d %lu", &duty_pct, &settle_ms);
        cmd_calrun(duty_pct, (uint32_t)settle_ms);
        return;
    }

    if (line.startsWith("SWEEP ")) {
        /* "SWEEP <SIN|TRAP> <amp_pct> <p_start_ms> <p_end_ms> <duration_ms>" */
        String rest = line.substring(6);
        char shape[8] = {0};
        int amp = 30;
        unsigned long p0 = 3000, p1 = 500, dur = 15000;
        sscanf(rest.c_str(), "%7s %d %lu %lu %lu", shape, &amp, &p0, &p1, &dur);
        cmd_sweep(shape, amp, (uint32_t)p0, (uint32_t)p1, (uint32_t)dur);
        return;
    }

    if (line.startsWith("SWEEPRAW ")) {
        /* "SWEEPRAW <SIN|TRAP> <amp_pct> <period_ms> <n_windows>" */
        String rest = line.substring(9);
        char shape[8] = {0};
        int amp = 30;
        unsigned long per = 2000, n_win = 20;
        sscanf(rest.c_str(), "%7s %d %lu %lu", shape, &amp, &per, &n_win);
        cmd_sweepraw(shape, amp, (uint32_t)per, (uint32_t)n_win);
        return;
    }

    if (line.startsWith("SWEEPRAW_R ")) {
        /* "SWEEPRAW_R <SIN|TRAP> <amp_pct> <period_ms> <n_windows>" */
        String rest = line.substring(11);
        char shape[8] = {0};
        int amp = 30;
        unsigned long per = 2000, n_win = 20;
        sscanf(rest.c_str(), "%7s %d %lu %lu", shape, &amp, &per, &n_win);
        cmd_sweepraw_r(shape, amp, (uint32_t)per, (uint32_t)n_win);
        return;
    }

    if (line.startsWith("SWEEPRAW_BOTH ")) {
        /* "SWEEPRAW_BOTH <SIN|TRAP> <amp_pct> <period_ms> <n_windows>" */
        String rest = line.substring(14);
        char shape[8] = {0};
        int amp = 30;
        unsigned long per = 2000, n_win = 20;
        sscanf(rest.c_str(), "%7s %d %lu %lu", shape, &amp, &per, &n_win);
        cmd_sweepraw_both(shape, amp, (uint32_t)per, (uint32_t)n_win);
        return;
    }

    if (line.length() > 0) {
        Serial.print("ERR unknown: ");
        Serial.println(line);
    }
}
