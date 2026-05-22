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

extern "C" {
#include "hal/biba_hal.h"
#include "biba_board.h"
#include "biba_config.h"
}
#include "poc/adc_capture.h"

static uint16_t s_buf[ADC_CAPTURE_MAX_SAMPLES];

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
/* Per-iteration capture parameters: 200 ms window → 5 Hz update rate. */
#define RPMRUN_N_SAMPLES   2048u
#define RPMRUN_SPS         10000u
#define RPMRUN_DT_S        ((float)RPMRUN_N_SAMPLES / (float)RPMRUN_SPS)
#define RPMRUN_MAX_DUR_MS  60000u
#define ADC_VREF_V         3.3f
#define ADC_FULLSCALE      4095.0f

/* On-device Schmitt-trigger zero-crossing rate over s_buf[0..n-1].
 * Returns 0.0 when the signal has no detectable AC content. */
static float zc_freq_hz(const uint16_t *buf, uint16_t n, uint32_t sps)
{
    if (n < 4) return 0.0f;

    /* Pass 1: mean + min/max for hysteresis sizing. */
    uint32_t sum = 0;
    uint16_t mn = buf[0], mx = buf[0];
    for (uint16_t i = 0; i < n; ++i) {
        sum += buf[i];
        if (buf[i] < mn) mn = buf[i];
        if (buf[i] > mx) mx = buf[i];
    }
    float mean = (float)sum / (float)n;
    float pk_pk = (float)(mx - mn);
    /* Noise floor: ADC quiescent noise on the IS line with the motor off
     * is ~10-15 LSB pk-pk; require well above that before declaring a
     * detectable AC signal.  Previously 8 LSB — ZC was reporting random
     * 10-30 Hz at duty=0 from pure noise, which fooled the PI controller
     * into thinking the motor was spinning when it was not. */
    if (pk_pk < 40.0f) return 0.0f;
    float hi = 0.25f * pk_pk;
    float lo = -hi;

    /* Pass 2: count up-crossings of +hi after dropping below -lo (Schmitt). */
    bool state_high = false;
    uint16_t crossings = 0;
    uint32_t first = 0, last = 0;
    for (uint16_t i = 0; i < n; ++i) {
        float v = (float)buf[i] - mean;
        if (state_high) {
            if (v < lo) state_high = false;
        } else {
            if (v > hi) {
                state_high = true;
                if (crossings == 0) first = i;
                last = i;
                crossings++;
            }
        }
    }
    if (crossings < 2) return 0.0f;
    float period_samples = (float)(last - first) / (float)(crossings - 1);
    if (period_samples <= 0.0f) return 0.0f;
    return (float)sps / period_samples;
}

static float adc_to_amps(float adc_mean)
{
    /* Convert mean ADC raw to current via BIBA_IS_AMPS_PER_VOLT.
     * Baseline (IS at duty=0) is subtracted in cmd_rpmrun() before this
     * function is called, so adc_mean here is already baseline-relative. */
    float v = adc_mean * ADC_VREF_V / ADC_FULLSCALE;
    return v * BIBA_IS_AMPS_PER_VOLT;
}

static void cmd_rpmrun(float target_hz, uint32_t duration_ms,
                       float kp, float ki)
{
    if (duration_ms > RPMRUN_MAX_DUR_MS) duration_ms = RPMRUN_MAX_DUR_MS;
    if (target_hz < 0.0f) target_hz = 0.0f;
    if (target_hz > 50.0f) target_hz = 50.0f;

    /* 1. Baseline IS reading with motor off — DC offset on the IS line. */
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

    Serial.printf("RPMRUN_START target=%.2f duration_ms=%lu kp=%.4f ki=%.4f baseline_adc=%.1f\n",
                  target_hz, (unsigned long)duration_ms, kp, ki, baseline_adc);
    Serial.println("RPM_DATA t_ms,target_hz,meas_hz,duty_pct,curr_a,err_hz,i_term,p_term");

    float duty = 0.0f;
    float integral = 0.0f;
    uint32_t t_start = millis();

    while ((millis() - t_start) < duration_ms) {
        /* Capture window — drives loop period (200 ms @ N=2048, sps=10k). */
        if (!adc_capture_burst(BIBA_ADC_CHAN_IS_LEFT, RPMRUN_N_SAMPLES, s_buf)) {
            Serial.println("ERROR capture timeout");
            break;
        }
        float meas_hz = zc_freq_hz(s_buf, RPMRUN_N_SAMPLES, RPMRUN_SPS);

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
        if (can_integrate && meas_hz > 0.0f) {
            integral += err * RPMRUN_DT_S;
        }
        if (integral > 1.5f / (ki + 1e-6f)) integral = 1.5f / (ki + 1e-6f);
        if (integral < 0.0f) integral = 0.0f;
        float p_term = kp * err;
        float i_term = ki * integral;
        duty = p_term + i_term;
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
        if (target_hz > 0.0f && duty > 0.0f && duty < 0.20f) {
            duty = 0.20f;
        }
        if (target_hz > 0.0f && wheel_spinning && duty < 0.20f) {
            duty = 0.20f;
        }
        if (duty < 0.0f) duty = 0.0f;
        if (duty > 1.0f) duty = 1.0f;
        biba_hal_motor_pwm_left(duty);

        Serial.printf("RPM_DATA %lu,%.2f,%.2f,%.1f,%.2f,%.2f,%.3f,%.3f\n",
                      (unsigned long)(millis() - t_start),
                      target_hz, meas_hz, duty * 100.0f, curr_a,
                      err, i_term, p_term);

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

    biba_hal_motor_pwm_left(0.0f);
    Serial.println("RPMRUN_END");
}

void setup(void)
{
    Serial.begin(115200);
    Serial.ignoreFlowControl(true);
    biba_hal_init();
    /* Issue 6 fix: ARM the BTS7960. SSR powers the bridge, REN/LEN enables
     * activate the half-bridges. Without these, PWM drives nothing and the
     * IS signal is zero. */
    biba_hal_ssr_set(true);
    biba_hal_left_enable(true);
    biba_hal_right_enable(true);
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
        /* The Python --motor left/right flag selects which unit to run;
         * this firmware always drives the IS_LEFT channel. */
        uint8_t adc_chan = BIBA_ADC_CHAN_IS_LEFT;
        cmd_capture(signed_duty, is_fwd, adc_chan, n, sps, settle_ms);
        return;
    }

    if (line.startsWith("RPMRUN ")) {
        /* "RPMRUN <target_hz> <duration_ms> [kp_x1000 ki_x1000]" */
        String rest = line.substring(7);
        float target_hz = 10.0f;
        uint32_t duration_ms = 10000;
        int kp_mil = 50;     /* default Kp = 0.050 (%-duty per Hz of error) */
        int ki_mil = 1000;   /* default Ki = 1.000 */
        sscanf(rest.c_str(), "%f %lu %d %d",
               &target_hz, &duration_ms, &kp_mil, &ki_mil);
        cmd_rpmrun(target_hz, duration_ms,
                   (float)kp_mil / 1000.0f, (float)ki_mil / 1000.0f);
        return;
    }

    if (line.length() > 0) {
        Serial.print("ERR unknown: ");
        Serial.println(line);
    }
}
