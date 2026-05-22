/* Phase 06 IS-Signal RPM PoC — USB CDC command shell.
 *
 * Commands (over USB CDC, 115200 baud, line-terminated by '\n'):
 *   PING                                 -> "PONG"
 *   STOP                                 -> stops motors, disarms SSR + enables, "OK stopped"
 *   CAPTURE <FWD|REV> <duty_pct> <n> <sps> ->
 *       Drives the left motor PWM at the requested direction/duty, waits
 *       500 ms for the IS signal to settle, then DMA-bursts <n> samples
 *       from BIBA_ADC_CHAN_IS_LEFT at <sps> samples/second.
 *
 *       Response format:
 *         CAPTURE_START duty=<pct> dir=<FWD|REV> chan=<n> sps=<sps> n=<n>
 *         <comma-separated 12-bit ADC values, one line>
 *         CAPTURE_END
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
}
#include "poc/adc_capture.h"

static uint16_t s_buf[ADC_CAPTURE_MAX_SAMPLES];

static void cmd_capture(float signed_duty, bool is_fwd,
                        uint8_t adc_chan, uint16_t n_samples, uint32_t sps)
{
    if (signed_duty > 1.0f)  signed_duty = 1.0f;
    if (signed_duty < -1.0f) signed_duty = -1.0f;
    if (n_samples > ADC_CAPTURE_MAX_SAMPLES) n_samples = ADC_CAPTURE_MAX_SAMPLES;

    /* Issue 1 fix: use biba_hal_motor_pwm_left/right (the original plan
     * referenced a nonexistent HAL setter). */
    if (adc_chan == BIBA_ADC_CHAN_IS_LEFT) {
        biba_hal_motor_pwm_left(signed_duty);
    } else {
        biba_hal_motor_pwm_right(signed_duty);
    }

    delay(500);

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

    /* Issue 2 fix: include dir=FWD|REV in CAPTURE_START header. */
    Serial.printf("CAPTURE_START duty=%d dir=%s chan=%d sps=%lu n=%u\n",
                  (int)(fabsf(signed_duty) * 100.0f),
                  is_fwd ? "FWD" : "REV",
                  (int)adc_chan,
                  (unsigned long)sps,
                  (unsigned)n_samples);

    for (uint16_t i = 0; i < n_samples; i++) {
        Serial.print(s_buf[i]);
        Serial.print((i + 1) < n_samples ? ',' : '\n');
    }
    Serial.println("CAPTURE_END");
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
        /* Issue 2 fix: "CAPTURE <FWD|REV> <duty_pct> <n_samples> <sps>" —
         * direction token FIRST, then 3 numeric args.
         * Issue 3 fix: dual-channel capture removed per D-04. */
        String rest = line.substring(8);             /* after "CAPTURE " */
        bool is_fwd = rest.startsWith("FWD");
        rest = rest.substring(4);                    /* skip "FWD " or "REV " */
        int duty_pct = 50;
        uint16_t n = 2048;
        uint32_t sps = 10000;
        sscanf(rest.c_str(), "%d %hu %lu", &duty_pct, &n, &sps);
        if (duty_pct < 0)   duty_pct = 0;
        if (duty_pct > 100) duty_pct = 100;
        float signed_duty = is_fwd ? (duty_pct / 100.0f) : -(duty_pct / 100.0f);
        /* The Python --motor left/right flag selects which unit to run;
         * this firmware always drives the IS_LEFT channel. */
        uint8_t adc_chan = BIBA_ADC_CHAN_IS_LEFT;
        cmd_capture(signed_duty, is_fwd, adc_chan, n, sps);
        return;
    }

    if (line.length() > 0) {
        Serial.print("ERR unknown: ");
        Serial.println(line);
    }
}
