/* PWM → CRSF bridge — RP2040 entry point (env: rp2040_bridge_pwm2crsf).
 *
 * Measures servo-PWM high times on PWM2CRSF_INPUT_PINS with GPIO edge
 * interrupts and streams CRSF RC-channel frames out of UART0 at
 * PWM2CRSF_RC_PERIOD_MS. When any mapped input goes quiet the bridge
 * stops transmitting, which is exactly what BiBa sees when an ELRS
 * receiver loses its link, so BiBa's existing failsafe takes over.
 *
 * All the decision logic lives in pwm2crsf.c (native-tested); this file
 * only owns pins, timers and the UART. */

#include <Arduino.h>

#include "target.h"
#include "target_config.h"

extern "C" {
#include "pwm2crsf.h"
}

static const uint8_t kInputPins[PWM2CRSF_INPUT_COUNT] = PWM2CRSF_INPUT_PINS;

static const pwm2crsf_config_t kConfig = {
    .input_count      = PWM2CRSF_INPUT_COUNT,
    .min_us           = PWM2CRSF_MIN_US,
    .max_us           = PWM2CRSF_MAX_US,
    .valid_min_us     = PWM2CRSF_VALID_MIN_US,
    .valid_max_us     = PWM2CRSF_VALID_MAX_US,
    .input_timeout_us = PWM2CRSF_INPUT_TIMEOUT_MS * 1000u,
    .required_mask    = PWM2CRSF_REQUIRED_MASK,
    .map              = PWM2CRSF_CHANNEL_MAP,
    .idle             = PWM2CRSF_IDLE_VALUES,
    .invert_mask      = PWM2CRSF_INPUT_INVERT_MASK,
    .center_deadband_mask = PWM2CRSF_CENTER_DEADBAND_MASK,
    .center_deadband_us   = PWM2CRSF_CENTER_DEADBAND_US,
    .button_high_us   = PWM2CRSF_BUTTON_HIGH_US,
    .button_low_us    = PWM2CRSF_BUTTON_LOW_US,
    .button_min_interval_us = PWM2CRSF_BUTTON_MIN_INTERVAL_MS * 1000u,
    .buttons = {
        { PWM2CRSF_SPEED_BUTTON_INPUT, PWM2CRSF_SPEED_CRSF_CH,
          PWM2CRSF_SPEED_STEPS, PWM2CRSF_SPEED_BUTTON_LATCHING != 0 },
        { PWM2CRSF_DRIVE_BUTTON_INPUT, PWM2CRSF_DRIVE_CRSF_CH,
          2, PWM2CRSF_DRIVE_BUTTON_LATCHING != 0 },
        { PWM2CRSF_UNMAPPED, 0, 0, false },
        { PWM2CRSF_UNMAPPED, 0, 0, false },
    },
    .arm_input        = PWM2CRSF_ARM_INPUT,
    .arm_crsf_ch      = PWM2CRSF_ARM_CRSF_CH,
};

enum { kSlotSpeed = 0, kSlotDrive = 1 };

/* --- Pulse capture (ISR side) ------------------------------------------ */

static uint64_t          s_rise_us[PWM2CRSF_INPUT_COUNT];
static volatile uint32_t s_width_us[PWM2CRSF_INPUT_COUNT];
static volatile uint32_t s_pulse_seq[PWM2CRSF_INPUT_COUNT];

static void on_gpio_edge(uint gpio, uint32_t events)
{
    uint64_t now = time_us_64();
    for (unsigned i = 0; i < PWM2CRSF_INPUT_COUNT; ++i) {
        if (kInputPins[i] != gpio) continue;

        bool rise = (events & GPIO_IRQ_EDGE_RISE) != 0;
        bool fall = (events & GPIO_IRQ_EDGE_FALL) != 0;
        if (rise && fall) {
            /* Both edges latched before we got here: the pulse width is
             * unknown. Resync on the current level. */
            rise = gpio_get(gpio);
            fall = false;
            s_rise_us[i] = 0;
        }
        if (rise) {
            s_rise_us[i] = now;
        } else if (fall && s_rise_us[i] != 0) {
            s_width_us[i] = (uint32_t)(now - s_rise_us[i]);
            s_pulse_seq[i]++;
            s_rise_us[i] = 0;
        }
        return;
    }
}

/* --- Main-loop state --------------------------------------------------- */

static pwm2crsf_state_t s_state;
static uint32_t         s_seen_seq[PWM2CRSF_INPUT_COUNT];
static uint64_t         s_next_rc_us;
static uint64_t         s_next_stats_us;
static uint64_t         s_next_debug_us;
static uint32_t         s_rc_frames_sent;
static bool             s_last_link_ok;
static uint8_t          s_last_speed_step;
static uint8_t          s_last_drive_step;
static uint32_t         s_rx_bytes;      /* bytes from BiBa: proves the RX wire */

static void ingest_pulses(uint64_t now_us)
{
    for (unsigned i = 0; i < PWM2CRSF_INPUT_COUNT; ++i) {
        uint32_t save = save_and_disable_interrupts();
        uint32_t seq   = s_pulse_seq[i];
        uint32_t width = s_width_us[i];
        restore_interrupts(save);

        if (seq == s_seen_seq[i]) continue;
        s_seen_seq[i] = seq;
        pwm2crsf_on_pulse(&s_state, &kConfig, (uint8_t)i, width, now_us);
    }
}

static void crsf_send(const uint8_t *frame, size_t len)
{
    if (len == 0) return;
    uart_write_blocking(PWM2CRSF_CRSF_UART_INST, frame, len);
}

static void drain_crsf_rx(void)
{
    /* BiBa pings the "receiver" at 5 Hz; nothing here needs answering. */
    while (uart_is_readable(PWM2CRSF_CRSF_UART_INST)) {
        (void)uart_getc(PWM2CRSF_CRSF_UART_INST);
        s_rx_bytes++;
    }
}

static void update_led(bool link_ok, uint64_t now_us)
{
    bool on = link_ok ? true : ((now_us / 250000u) & 1u) != 0;
    gpio_put(PWM2CRSF_PIN_LED_GPIO, on);
}

#if PWM2CRSF_DEBUG_PRINT
static void debug_print(bool link_ok, uint64_t now_us)
{
    uint16_t ch[CRSF_RC_CHANNEL_COUNT];
    pwm2crsf_channels(&s_state, &kConfig, now_us, ch);

    /* What BiBa will do with the channels we send (biba_config.h). */
    const char *arm = !s_state.arm_ready ? "LOCK"
                    : (ch[PWM2CRSF_ARM_CRSF_CH] > 1238u ? "ARM" : "disarm");   /* > +0.3 */
    Serial.printf("[pwm2crsf] %s %s spd=%u %s tx=%lu rx_from_biba=%lu glitch=%lu |",
                  link_ok ? "LINK" : "FAILSAFE", arm,
                  (unsigned)pwm2crsf_button_step(&s_state, kSlotSpeed) + 1u,
                  pwm2crsf_button_step(&s_state, kSlotDrive) ? "HOLD" : "MANUAL",
                  (unsigned long)s_rc_frames_sent,
                  (unsigned long)s_rx_bytes,
                  (unsigned long)s_state.glitches);
    for (unsigned i = 0; i < PWM2CRSF_INPUT_COUNT; ++i) {
        bool fresh = pwm2crsf_input_fresh(&s_state, &kConfig, (uint8_t)i, now_us);
        Serial.printf(" in%u=%4u%s", i + 1, (unsigned)s_state.width_us[i],
                      fresh ? " " : "!");
    }
    Serial.printf(" | ch2=%u ch4=%u ch5=%u ch6=%u ch8=%u ch10=%u\r\n",
                  ch[1], ch[3], ch[4], ch[5], ch[7], ch[9]);
}
#endif

void setup()
{
    Serial.begin(115200);

    gpio_init(PWM2CRSF_PIN_LED_GPIO);
    gpio_set_dir(PWM2CRSF_PIN_LED_GPIO, GPIO_OUT);
    gpio_put(PWM2CRSF_PIN_LED_GPIO, false);

    uart_init(PWM2CRSF_CRSF_UART_INST, PWM2CRSF_CRSF_BAUD);
    uart_set_format(PWM2CRSF_CRSF_UART_INST, 8, 1, UART_PARITY_NONE);
    uart_set_fifo_enabled(PWM2CRSF_CRSF_UART_INST, true);
    gpio_set_function(PWM2CRSF_PIN_CRSF_TX_GPIO, GPIO_FUNC_UART);
    gpio_set_function(PWM2CRSF_PIN_CRSF_RX_GPIO, GPIO_FUNC_UART);

    pwm2crsf_init(&s_state);

    for (unsigned i = 0; i < PWM2CRSF_INPUT_COUNT; ++i) {
        uint8_t pin = kInputPins[i];
        gpio_init(pin);
        gpio_set_dir(pin, GPIO_IN);
        /* Unplugged input reads a steady low → no pulses → failsafe. */
        gpio_pull_down(pin);
        if (i == 0) {
            gpio_set_irq_enabled_with_callback(
                pin, GPIO_IRQ_EDGE_RISE | GPIO_IRQ_EDGE_FALL, true, &on_gpio_edge);
        } else {
            gpio_set_irq_enabled(pin, GPIO_IRQ_EDGE_RISE | GPIO_IRQ_EDGE_FALL, true);
        }
    }

    uint64_t now = time_us_64();
    s_next_rc_us    = now;
    s_next_stats_us = now;
    s_next_debug_us = now;
}

void loop()
{
    drain_crsf_rx();

    uint64_t now = time_us_64();
    ingest_pulses(now);
    bool link_ok = pwm2crsf_link_ok(&s_state, &kConfig, now);

    if (link_ok != s_last_link_ok) {
        Serial.printf("[pwm2crsf] %s\r\n", link_ok ? "link up" : "link lost -> failsafe");
        /* Come back from a dropout disarmed, slow and MANUAL. */
        if (!link_ok) pwm2crsf_reset_on_link_loss(&s_state);
        s_last_link_ok = link_ok;
    }

    uint8_t speed = pwm2crsf_button_step(&s_state, kSlotSpeed);
    if (speed != s_last_speed_step) {
        s_last_speed_step = speed;
        Serial.printf("[pwm2crsf] speed %u/%u\r\n",
                      (unsigned)speed + 1u, (unsigned)PWM2CRSF_SPEED_STEPS);
    }
    uint8_t drive = pwm2crsf_button_step(&s_state, kSlotDrive);
    if (drive != s_last_drive_step) {
        s_last_drive_step = drive;
        Serial.printf("[pwm2crsf] drive mode %s\r\n", drive ? "HOLD" : "MANUAL");
    }

    uint8_t frame[CRSF_MAX_FRAME_SIZE];

    if (now >= s_next_rc_us) {
        s_next_rc_us = now + (uint64_t)PWM2CRSF_RC_PERIOD_MS * 1000u;
        size_t len = pwm2crsf_build_rc_frame(&s_state, &kConfig, now,
                                             frame, sizeof(frame));
        if (len > 0) {
            crsf_send(frame, len);
            s_rc_frames_sent++;
        }
    }

    /* Link stats only while the link is up: a real ELRS receiver goes
     * silent on disconnect too. */
    if (link_ok && now >= s_next_stats_us) {
        s_next_stats_us = now + (uint64_t)PWM2CRSF_LINK_STATS_PERIOD_MS * 1000u;
        crsf_send(frame, pwm2crsf_build_link_stats_frame(true, frame, sizeof(frame)));
    }

    update_led(link_ok, now);

#if PWM2CRSF_DEBUG_PRINT
    if (now >= s_next_debug_us) {
        s_next_debug_us = now + (uint64_t)PWM2CRSF_DEBUG_PERIOD_MS * 1000u;
        debug_print(link_ok, now);
    }
#endif
}
