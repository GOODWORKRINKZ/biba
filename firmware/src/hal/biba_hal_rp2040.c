/* RP2040 HAL implementation for BiBa firmware.
 *
 * Implements the same biba_hal.h API as the STM32Cube version, but uses
 * pico-sdk primitives throughout.  Compiled only when
 * BIBA_TARGET_RPICO_RP2040 is defined (see platformio.ini src_filter).
 *
 * printf() is routed to USB CDC by the earlephilhower arduino-pico
 * framework — no _write() override is needed here.
 */

#include "biba_hal.h"

#include "biba_board.h"
#include "biba_config.h"
#include "biba_proto.h"
#include "drivers/aht30.h"

#include "hardware/gpio.h"
#include "hardware/uart.h"
#include "hardware/spi.h"
#include "hardware/i2c.h"
#include "hardware/adc.h"
#include "hardware/dma.h"
#include "hardware/irq.h"
#include "hardware/pio.h"
#include "hardware/clocks.h"
#include "pico/time.h"

#include <string.h>

/* --- CRSF ring buffer (interrupt-driven, 256-byte power-of-two ring) ---- */

#define CRSF_RING_BITS  8u
#define CRSF_RING_SIZE  (1u << CRSF_RING_BITS)   /* 256 */
#define CRSF_RING_MASK  (CRSF_RING_SIZE - 1u)

static uint8_t          s_crsf_ring[CRSF_RING_SIZE];
/* Both indices are uint8_t so arithmetic naturally wraps at 256 (the ring
 * size), giving lock-free single-producer / single-consumer semantics when
 * s_crsf_write_idx is volatile. */
static volatile uint8_t s_crsf_write_idx;
static uint8_t          s_crsf_read_idx;

static void crsf_uart_isr(void)
{
    while (uart_is_readable(BIBA_CRSF_UART_INST)) {
        s_crsf_ring[s_crsf_write_idx++] = (uint8_t)uart_getc(BIBA_CRSF_UART_INST);
    }
}

/* --- ADC (polled on demand) --------------------------------------------- */

static volatile uint32_t s_adc_scan_count;

/* --- SPI slave (DMA-driven, non-blocking) ------------------------------- *
 * SPI1 frequency ignored in slave mode; set to 1 MHz as a placeholder. */

#if BIBA_TARGET_HAS_SPI_SLAVE
static int  s_spi_dma_tx = -1;
static int  s_spi_dma_rx = -1;
static bool s_spi_init_done;
static volatile bool s_spi_busy;

static void spi_rx_dma_isr(void)
{
    if (dma_channel_get_irq0_status(s_spi_dma_rx)) {
        dma_channel_acknowledge_irq0(s_spi_dma_rx);
        s_spi_busy = false;
    }
}

static void spi_slave_init(void)
{
    /* SPI1 frequency ignored in slave mode; set to 1 MHz as a placeholder. */
    spi_init(BIBA_SPI_INST, 1000000u);
    spi_set_slave(BIBA_SPI_INST, true);

    gpio_set_function(BIBA_PIN_SPI_SCK_GPIO, GPIO_FUNC_SPI);
    gpio_set_function(BIBA_PIN_SPI_TX_GPIO,  GPIO_FUNC_SPI);
    gpio_set_function(BIBA_PIN_SPI_RX_GPIO,  GPIO_FUNC_SPI);
    gpio_set_function(BIBA_PIN_SPI_CSN_GPIO, GPIO_FUNC_SPI);

    s_spi_dma_tx = dma_claim_unused_channel(true);
    s_spi_dma_rx = dma_claim_unused_channel(true);

    /* Completion IRQ on the RX channel (RX done = full transaction done). */
    dma_channel_set_irq0_enabled(s_spi_dma_rx, true);
    irq_set_exclusive_handler(DMA_IRQ_0, spi_rx_dma_isr);
    irq_set_enabled(DMA_IRQ_0, true);

    s_spi_init_done = true;
}
#endif /* BIBA_TARGET_HAS_SPI_SLAVE */

/* --- Mode-select latch -------------------------------------------------- */

static bool s_mode_sel_latched_companion;

/* --- WS2812 forward declarations ---------------------------------------- */

static void ws2812_init(void);
static uint ws2812_claim_sm(uint gpio);

/* --- Public API --------------------------------------------------------- */

void biba_hal_init(void)
{
    /* GPIO outputs -------------------------------------------------------- */
    gpio_init(BIBA_PIN_STATUS_LED_GPIO);
    gpio_set_dir(BIBA_PIN_STATUS_LED_GPIO, GPIO_OUT);
    biba_hal_status_led_set(false);

#if BIBA_TARGET_HAS_BTS7960_2CH
    /* BTS7960 enables: output, start disabled. */
    const uint en_pins[] = {
        BIBA_PIN_LEFT_REN_GPIO, BIBA_PIN_LEFT_LEN_GPIO,
        BIBA_PIN_RIGHT_REN_GPIO, BIBA_PIN_RIGHT_LEN_GPIO,
    };
    for (unsigned i = 0; i < 4u; i++) {
        gpio_init(en_pins[i]);
        gpio_set_dir(en_pins[i], GPIO_OUT);
        gpio_put(en_pins[i], 0);
    }
#endif

#if BIBA_TARGET_HAS_SPI_SLAVE
    /* DATA_READY output, start low. */
#if !BIBA_TARGET_HAS_BLDC_2CH
    gpio_init(BIBA_PIN_DATA_READY_GPIO);
    gpio_set_dir(BIBA_PIN_DATA_READY_GPIO, GPIO_OUT);
    gpio_put(BIBA_PIN_DATA_READY_GPIO, 0);

    /* MODE_SEL input with pull-up; sample once here. */
    gpio_init(BIBA_PIN_MODE_SEL_GPIO);
    gpio_set_dir(BIBA_PIN_MODE_SEL_GPIO, GPIO_IN);
    gpio_pull_up(BIBA_PIN_MODE_SEL_GPIO);
    s_mode_sel_latched_companion = !gpio_get(BIBA_PIN_MODE_SEL_GPIO);
#endif /* !BLDC */
#endif /* BIBA_TARGET_HAS_SPI_SLAVE */

    /* IMU interrupt input, no pull (external pull on board). */
    gpio_init(BIBA_PIN_IMU_INT1_GPIO);
    gpio_set_dir(BIBA_PIN_IMU_INT1_GPIO, GPIO_IN);

    /* Motor PWM (topology: two slices, each pair shares a carrier).
     * On the BLDC target this brings up MCP2515 + ODrive CAN. */
    biba_hal_motor_pwm_init();
    biba_hal_ssr_init();   /* D-13: SSR LOW before any mode code runs */

#if BIBA_TARGET_HAS_BLDC_2CH
    /* No native ADC channels are wired on the BLDC target — the
     * ODrive unit reports Bus_Voltage / Bus_Current via CAN.  We keep
     * ADC init active only so unrelated code that calls
     * `biba_hal_adc_sample(...)` behaves correctly (returns 0 and
     * doesn't touch GPIOs that are wired as SPI0 / CAN). */
    (void)0;
#else
    /* ADC --------------------------------------------------------------- */
    adc_init();
    /* Phase 06: GP26 = ADC0 = IS_LEFT (RC-filtered), GP27 = ADC1 = IS_RIGHT (RC-filtered). */
    adc_gpio_init(26u);   /* GP26 = ADC0 = BIBA_ADC_CHAN_IS_LEFT  */
    adc_gpio_init(27u);   /* GP27 = ADC1 = BIBA_ADC_CHAN_IS_RIGHT */
#endif

    /* I2C0 for IMU and AHT30 (0x38) ------------------------------------ */
    i2c_init(BIBA_I2C_INST, 400000u);
    gpio_set_function(BIBA_PIN_I2C_SDA_GPIO, GPIO_FUNC_I2C);
    gpio_set_function(BIBA_PIN_I2C_SCL_GPIO, GPIO_FUNC_I2C);
    gpio_pull_up(BIBA_PIN_I2C_SDA_GPIO);
    gpio_pull_up(BIBA_PIN_I2C_SCL_GPIO);

    (void)aht30_init();

    /* CRSF and SPI slave are initialised lazily on first use. */

    /* WS2812 RGB LED on GP23. */
#if BIBA_HAS_RGB_LED
    ws2812_init();
    biba_hal_rgb_led_set(0, 0, 0); /* start off */
#endif

    /* Front indicator panels (second WS2812 chain, own pin + DMA). */
    biba_hal_led_strip_init();
}

uint32_t biba_hal_now_ms(void)
{
    return to_ms_since_boot(get_absolute_time());
}

void biba_hal_delay_ms(uint32_t ms)
{
    sleep_ms(ms);
}

void biba_hal_delay_us(uint32_t us)
{
    sleep_us(us);
}

void biba_hal_status_led_set(bool on)
{
#if BIBA_STATUS_LED_ACTIVE_LOW
    gpio_put(BIBA_PIN_STATUS_LED_GPIO, on ? 0u : 1u);
#else
    gpio_put(BIBA_PIN_STATUS_LED_GPIO, on ? 1u : 0u);
#endif
}

/* --- WS2812 RGB LED (PIO-based, GP23) ----------------------------------- *
 *
 * Pre-assembled PIO program for WS2812 800 kHz GRB protocol:
 *   T1=2, T2=5, T3=3 cycles; PIO clock = 8 MHz (divider = SYS_CLK / 8e6)
 *
 *   0: out  x, 1       side 0 [2]  ; shift 1 bit, drive low for T3 cycles
 *   1: jmp  !x, 3      side 1 [1]  ; rising edge (T1 cycles high)
 *   2: jmp  0          side 1 [4]  ; 1-bit: stay high T2 more, loop
 *   3: nop             side 0 [4]  ; 0-bit: drop low for T2 cycles, loop
 */
static const uint16_t s_ws2812_insn[] = { 0x6221u, 0x1123u, 0x1400u, 0xa442u };
static const struct pio_program s_ws2812_prog = {
    .instructions = s_ws2812_insn, .length = 4, .origin = -1,
};
static PIO  s_ws2812_pio;
static int  s_ws2812_offset = -1;   /* program is loaded once, shared by all SMs */
static uint s_ws2812_sm;            /* status NeoPixel (BIBA_PIN_RGB_LED_GPIO)   */

/* Claim one PIO state machine running the WS2812 program on `gpio`.
 * The program itself is added to pio0 on first use and reused after
 * that, so the status NeoPixel and the indicator-panel chain cost two
 * state machines but only one instruction-memory slot. */
static uint ws2812_claim_sm(uint gpio)
{
    s_ws2812_pio = pio0;
    if (s_ws2812_offset < 0) {
        s_ws2812_offset = (int)pio_add_program(s_ws2812_pio, &s_ws2812_prog);
    }
    const uint offset = (uint)s_ws2812_offset;
    const uint sm     = pio_claim_unused_sm(s_ws2812_pio, true);

    pio_sm_config c = pio_get_default_sm_config();
    sm_config_set_wrap(&c, offset, offset + 3u);
    sm_config_set_sideset(&c, 1u, false, false);
    sm_config_set_sideset_pins(&c, gpio);
    /* Shift left (MSB first), autopull at 24 bits. */
    sm_config_set_out_shift(&c, false, true, 24u);
    sm_config_set_fifo_join(&c, PIO_FIFO_JOIN_TX);
    /* 8 MHz PIO clock → 800 kHz WS2812 × 10 cycles/bit. */
    float div = (float)clock_get_hz(clk_sys) / (800000.0f * 10.0f);
    sm_config_set_clkdiv(&c, div);

    pio_gpio_init(s_ws2812_pio, gpio);
    pio_sm_set_consecutive_pindirs(s_ws2812_pio, sm, gpio, 1u, true);
    pio_sm_init(s_ws2812_pio, sm, offset, &c);
    pio_sm_set_enabled(s_ws2812_pio, sm, true);
    return sm;
}

static void ws2812_init(void)
{
    s_ws2812_sm = ws2812_claim_sm(BIBA_PIN_RGB_LED_GPIO);
}

void biba_hal_rgb_led_set(uint8_t r, uint8_t g, uint8_t b)
{
#if BIBA_HAS_RGB_LED
    /* WS2812 expects GRB order, packed in the top 24 bits of a 32-bit word. */
    uint32_t grb = ((uint32_t)g << 24u) | ((uint32_t)r << 16u) | ((uint32_t)b << 8u);
    pio_sm_put_blocking(s_ws2812_pio, s_ws2812_sm, grb);
#else
    (void)r; (void)g; (void)b;
#endif
}

/* --- Indicator LED panels (WS2812 chain, PIO + DMA) --------------------- *
 *
 * Same PIO program as the status NeoPixel above, on its own state
 * machine and its own pin, fed by DMA so a 32-LED frame (~1 ms on the
 * wire at 800 kHz) never blocks the control loop.
 */

#if BIBA_HAS_LED_PANEL

static uint     s_strip_sm;
static int      s_strip_dma = -1;
/* Pre-shifted GRB words: the PIO autopulls 24 bits MSB-first, so the
 * colour lives in the top 24 bits and the low byte is padding. */
static uint32_t s_strip_words[BIBA_LED_PANEL_TOTAL];

void biba_hal_led_strip_init(void)
{
    if (s_strip_dma >= 0) return;   /* already up */

    s_strip_sm  = ws2812_claim_sm(BIBA_PIN_LED_PANEL_GPIO);
    s_strip_dma = (int)dma_claim_unused_channel(true);

    dma_channel_config c = dma_channel_get_default_config((uint)s_strip_dma);
    channel_config_set_transfer_data_size(&c, DMA_SIZE_32);
    channel_config_set_read_increment(&c, true);
    channel_config_set_write_increment(&c, false);
    channel_config_set_dreq(&c, pio_get_dreq(s_ws2812_pio, s_strip_sm, true));
    dma_channel_configure((uint)s_strip_dma, &c,
                          &s_ws2812_pio->txf[s_strip_sm],
                          s_strip_words, BIBA_LED_PANEL_TOTAL, false);

    /* Push one blank frame so the panels are dark from boot rather than
     * showing whatever the LEDs powered up with. */
    memset(s_strip_words, 0, sizeof(s_strip_words));
    dma_channel_set_read_addr((uint)s_strip_dma, s_strip_words, true);
}

bool biba_hal_led_strip_busy(void)
{
    return (s_strip_dma >= 0) && dma_channel_is_busy((uint)s_strip_dma);
}

void biba_hal_led_strip_write(const uint8_t *rgb, size_t led_count)
{
    if (rgb == NULL || s_strip_dma < 0) return;
    /* Previous frame still on the wire — drop this one (see biba_hal.h). */
    if (dma_channel_is_busy((uint)s_strip_dma)) return;

    const size_t n = (led_count > (size_t)BIBA_LED_PANEL_TOTAL)
                     ? (size_t)BIBA_LED_PANEL_TOTAL : led_count;
    for (size_t i = 0; i < n; i++) {
        const uint32_t r = rgb[(3u * i) + 0u];
        const uint32_t g = rgb[(3u * i) + 1u];
        const uint32_t b = rgb[(3u * i) + 2u];
        s_strip_words[i] = (g << 24u) | (r << 16u) | (b << 8u);
    }
    /* Short frames blank the tail rather than leaving stale pixels lit. */
    for (size_t i = n; i < (size_t)BIBA_LED_PANEL_TOTAL; i++) {
        s_strip_words[i] = 0u;
    }

    /* RP2040 does not reload TRANS_COUNT on its own, so restate it
     * before every re-trigger. */
    dma_channel_set_trans_count((uint)s_strip_dma, BIBA_LED_PANEL_TOTAL, false);
    dma_channel_set_read_addr((uint)s_strip_dma, s_strip_words, true);
}

#else  /* !BIBA_HAS_LED_PANEL */

void biba_hal_led_strip_init(void) {}
bool biba_hal_led_strip_busy(void) { return false; }
void biba_hal_led_strip_write(const uint8_t *rgb, size_t led_count)
{
    (void)rgb; (void)led_count;
}

#endif /* BIBA_HAS_LED_PANEL */

#if !BIBA_TARGET_HAS_BLDC_2CH
void biba_hal_data_ready_set(bool on)
{
#if BIBA_TARGET_HAS_SPI_SLAVE
    gpio_put(BIBA_PIN_DATA_READY_GPIO, on ? 1u : 0u);
#else
    (void)on;
#endif
}
#endif /* !BLDC */

#if !BIBA_TARGET_HAS_BLDC_2CH
void biba_hal_data_ready_pulse(void)
{
    biba_hal_data_ready_set(true);
    sleep_us(1u);
    biba_hal_data_ready_set(false);
}
#else
/* No SBC link on the BLDC target — DATA_READY has no consumer. */
void biba_hal_data_ready_pulse(void) { (void)0; }
#endif

bool biba_hal_mode_sel_is_companion(void)
{
#if BIBA_TARGET_HAS_BLDC_2CH
    /* BLDC targets are always built in standalone mode (BIBA_MODE_*
     * compile-time flag selects).  Returning false here keeps the
     * mode dispatcher on the standalone path even for envs that try
     * to use MODE_SEL for runtime selection. */
    return false;
#else
    return s_mode_sel_latched_companion;
#endif
}

#if BIBA_TARGET_HAS_BTS7960_2CH
void biba_hal_left_enable(bool enabled)
{
    gpio_put(BIBA_PIN_LEFT_REN_GPIO, enabled ? 1u : 0u);
    gpio_put(BIBA_PIN_LEFT_LEN_GPIO, enabled ? 1u : 0u);
}

void biba_hal_right_enable(bool enabled)
{
    gpio_put(BIBA_PIN_RIGHT_REN_GPIO, enabled ? 1u : 0u);
    gpio_put(BIBA_PIN_RIGHT_LEN_GPIO, enabled ? 1u : 0u);
}
#endif

void biba_hal_ssr_init(void)  {}

void biba_hal_ssr_set(bool enabled)  { (void)enabled; }

/* --- ADC ---------------------------------------------------------------- */

uint16_t biba_hal_adc_sample(unsigned channel_index)
{
    if (channel_index >= BIBA_ADC_SCAN_LEN) return 0u;
    adc_select_input(channel_index);
    uint16_t v = adc_read();
    s_adc_scan_count++;
    return v;
}

uint32_t biba_hal_adc_scan_count(void)
{
    return s_adc_scan_count;
}

float biba_hal_adc_volts(uint16_t raw)
{
    return ((float)raw * BIBA_ADC_VREF_V) / (float)BIBA_ADC_MAX_COUNTS;
}

/* --- CRSF (UART0 + interrupt ring) ------------------------------------- */

void biba_hal_crsf_begin(uint32_t baud)
{
    uart_init(BIBA_CRSF_UART_INST, baud);
    gpio_set_function(BIBA_PIN_CRSF_TX_GPIO, GPIO_FUNC_UART);
    gpio_set_function(BIBA_PIN_CRSF_RX_GPIO, GPIO_FUNC_UART);

    /* Enable 32-byte hardware FIFO to reduce ISR frequency. */
    uart_set_fifo_enabled(BIBA_CRSF_UART_INST, true);

    irq_set_exclusive_handler(BIBA_CRSF_UART_IRQ, crsf_uart_isr);
    irq_set_enabled(BIBA_CRSF_UART_IRQ, true);
    uart_set_irq_enables(BIBA_CRSF_UART_INST, true /* RX */, false /* TX */);

    s_crsf_read_idx  = 0;
    s_crsf_write_idx = 0;
}

size_t biba_hal_crsf_read(uint8_t *dst, size_t cap)
{
    if (!dst || !cap) return 0u;
    size_t copied = 0u;
    uint8_t w = s_crsf_write_idx;   /* single volatile read; ISR only writes */
    while (s_crsf_read_idx != w && copied < cap) {
        dst[copied++] = s_crsf_ring[s_crsf_read_idx++];
    }
    return copied;
}

uint32_t biba_hal_crsf_write(const uint8_t *data, size_t len)
{
    if (!data || !len) return 0u;
    /* uart_write_blocking feeds the TX FIFO and blocks only until all
     * bytes are accepted (not until the last bit is shifted out).  This
     * is fine for CRSF ping frames — the FIFO is 32 bytes and a ping
     * frame is 6 bytes. */
    uart_write_blocking(BIBA_CRSF_UART_INST, data, len);
    return 0u;
}

biba_hal_crsf_diag_t biba_hal_crsf_diag(void)
{
    biba_hal_crsf_diag_t d;
    memset(&d, 0, sizeof(d));
    /* Report bytes in the ring (bytes available to read). */
    d.dma_ndtr        = (uint32_t)(uint8_t)(s_crsf_write_idx - s_crsf_read_idx);
    d.dma_init_status = 0u;   /* always 0 = ok (ISR init has no return code) */
    /* uart_sr / uart_cr1 / rcc_apb1enr: STM32-specific, return 0. */
    return d;
}

/* --- SPI2 slave --------------------------------------------------------- */

#if BIBA_TARGET_HAS_SPI_SLAVE
void biba_hal_spi_slave_arm(const uint8_t *tx, uint8_t *rx)
{
    if (!s_spi_init_done) {
        spi_slave_init();
    }

    s_spi_busy = true;

    /* TX: memory → SPI1 DR (sent to master as MISO). */
    dma_channel_config tx_cfg = dma_channel_get_default_config(s_spi_dma_tx);
    channel_config_set_transfer_data_size(&tx_cfg, DMA_SIZE_8);
    channel_config_set_dreq(&tx_cfg, spi_get_dreq(BIBA_SPI_INST, true));
    channel_config_set_read_increment(&tx_cfg, true);
    channel_config_set_write_increment(&tx_cfg, false);
    dma_channel_configure(s_spi_dma_tx, &tx_cfg,
                          &spi_get_hw(BIBA_SPI_INST)->dr, tx,
                          BIBA_PROTO_FRAME_SIZE, false);

    /* RX: SPI1 DR → memory (received from master as MOSI). */
    dma_channel_config rx_cfg = dma_channel_get_default_config(s_spi_dma_rx);
    channel_config_set_transfer_data_size(&rx_cfg, DMA_SIZE_8);
    channel_config_set_dreq(&rx_cfg, spi_get_dreq(BIBA_SPI_INST, false));
    channel_config_set_read_increment(&rx_cfg, false);
    channel_config_set_write_increment(&rx_cfg, true);
    dma_channel_configure(s_spi_dma_rx, &rx_cfg,
                          rx, &spi_get_hw(BIBA_SPI_INST)->dr,
                          BIBA_PROTO_FRAME_SIZE, false);

    /* Start both simultaneously. */
    dma_start_channel_mask((1u << (uint)s_spi_dma_tx) |
                           (1u << (uint)s_spi_dma_rx));
}

bool biba_hal_spi_slave_poll(void)
{
    return !s_spi_busy;
}
#else /* !BIBA_TARGET_HAS_SPI_SLAVE */
void biba_hal_spi_slave_arm(const uint8_t *tx, uint8_t *rx)
{
    (void)tx; (void)rx;
}
bool biba_hal_spi_slave_poll(void) { return true; }
#endif

/* --- I2C0 (IMU) --------------------------------------------------------- */

bool biba_hal_i2c_write(uint8_t addr, const uint8_t *data, size_t len)
{
    int r = i2c_write_blocking(BIBA_I2C_INST, addr, data, (uint)len, false);
    return r == (int)len;
}

bool biba_hal_i2c_read(uint8_t addr, uint8_t reg, uint8_t *data, size_t len)
{
    int r = i2c_write_blocking(BIBA_I2C_INST, addr, &reg, 1u, true /* no stop */);
    if (r != 1) return false;
    r = i2c_read_blocking(BIBA_I2C_INST, addr, data, (uint)len, false);
    return r == (int)len;
}
