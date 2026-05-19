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
#include "drivers/ads1115.h"
#include "drivers/aht30.h"

#include "pico/stdlib.h"
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

/* --- SPI slave (DMA-driven, non-blocking) ------------------------------- */

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

/* --- Mode-select latch -------------------------------------------------- */

static bool s_mode_sel_latched_companion;

/* --- WS2812 forward declaration ---------------------------------------- */

static void ws2812_init(void);

/* --- Public API --------------------------------------------------------- */

void biba_hal_init(void)
{
    /* GPIO outputs -------------------------------------------------------- */
    gpio_init(BIBA_PIN_STATUS_LED_GPIO);
    gpio_set_dir(BIBA_PIN_STATUS_LED_GPIO, GPIO_OUT);
    biba_hal_status_led_set(false);

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

    /* DATA_READY output, start low. */
    gpio_init(BIBA_PIN_DATA_READY_GPIO);
    gpio_set_dir(BIBA_PIN_DATA_READY_GPIO, GPIO_OUT);
    gpio_put(BIBA_PIN_DATA_READY_GPIO, 0);

    /* MODE_SEL input with pull-up; sample once here. */
    gpio_init(BIBA_PIN_MODE_SEL_GPIO);
    gpio_set_dir(BIBA_PIN_MODE_SEL_GPIO, GPIO_IN);
    gpio_pull_up(BIBA_PIN_MODE_SEL_GPIO);
    s_mode_sel_latched_companion = !gpio_get(BIBA_PIN_MODE_SEL_GPIO);

    /* IMU interrupt input, no pull (external pull on board). */
    gpio_init(BIBA_PIN_IMU_INT1_GPIO);
    gpio_set_dir(BIBA_PIN_IMU_INT1_GPIO, GPIO_IN);

    /* Motor PWM (topology: two slices, each pair shares a carrier). */
    biba_hal_motor_pwm_init();
    biba_hal_ssr_init();   /* D-13: SSR LOW before any mode code runs */

    /* ADC --------------------------------------------------------------- */
    adc_init();
    /* ADC-capable pins: GP26 = ADC0 (VBAT), GP27 = ADC1 (Ibat). */
    adc_gpio_init(26u);   /* GP26 = ADC0 = BIBA_ADC_CHAN_VBAT */
    adc_gpio_init(27u);   /* GP27 = ADC1 = BIBA_ADC_CHAN_IBAT */

    /* I2C0 for IMU, ADS1115 (0x48), AHT30 (0x38) ----------------------- */
    i2c_init(BIBA_I2C_INST, 400000u);
    gpio_set_function(BIBA_PIN_I2C_SDA_GPIO, GPIO_FUNC_I2C);
    gpio_set_function(BIBA_PIN_I2C_SCL_GPIO, GPIO_FUNC_I2C);
    gpio_pull_up(BIBA_PIN_I2C_SDA_GPIO);
    gpio_pull_up(BIBA_PIN_I2C_SCL_GPIO);

    /* Initialise ADS1115 (BTS7960 IS pins) and AHT30 (temp/humidity). */
    (void)ads1115_init(ADS1115_ADDR, ADS1115_FSR_4096MV);
    (void)aht30_init();

    /* CRSF and SPI slave are initialised lazily on first use. */

    /* WS2812 RGB LED on GP23. */
#if BIBA_HAS_RGB_LED
    ws2812_init();
    biba_hal_rgb_led_set(0, 0, 0); /* start off */
#endif
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
static uint s_ws2812_sm;

static void ws2812_init(void)
{
    s_ws2812_pio = pio0;
    uint offset  = pio_add_program(s_ws2812_pio, &s_ws2812_prog);
    s_ws2812_sm  = pio_claim_unused_sm(s_ws2812_pio, true);

    pio_sm_config c = pio_get_default_sm_config();
    sm_config_set_wrap(&c, offset, offset + 3u);
    sm_config_set_sideset(&c, 1u, false, false);
    sm_config_set_sideset_pins(&c, BIBA_PIN_RGB_LED_GPIO);
    /* Shift left (MSB first), autopull at 24 bits. */
    sm_config_set_out_shift(&c, false, true, 24u);
    sm_config_set_fifo_join(&c, PIO_FIFO_JOIN_TX);
    /* 8 MHz PIO clock → 800 kHz WS2812 × 10 cycles/bit. */
    float div = (float)clock_get_hz(clk_sys) / (800000.0f * 10.0f);
    sm_config_set_clkdiv(&c, div);

    pio_gpio_init(s_ws2812_pio, BIBA_PIN_RGB_LED_GPIO);
    pio_sm_set_consecutive_pindirs(s_ws2812_pio, s_ws2812_sm,
                                   BIBA_PIN_RGB_LED_GPIO, 1u, true);
    pio_sm_init(s_ws2812_pio, s_ws2812_sm, offset, &c);
    pio_sm_set_enabled(s_ws2812_pio, s_ws2812_sm, true);
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

void biba_hal_data_ready_set(bool on)
{
    gpio_put(BIBA_PIN_DATA_READY_GPIO, on ? 1u : 0u);
}

void biba_hal_data_ready_pulse(void)
{
    biba_hal_data_ready_set(true);
    sleep_us(1u);
    biba_hal_data_ready_set(false);
}

bool biba_hal_mode_sel_is_companion(void)
{
    return s_mode_sel_latched_companion;
}

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

void biba_hal_ssr_init(void)
{
    gpio_init(BIBA_PIN_SSR_GPIO);
    gpio_set_dir(BIBA_PIN_SSR_GPIO, GPIO_OUT);
    gpio_put(BIBA_PIN_SSR_GPIO, 0);   /* LOW = SSR off = BTS7960 power off */
}

void biba_hal_ssr_set(bool enabled)
{
    gpio_put(BIBA_PIN_SSR_GPIO, enabled ? 1u : 0u);
}

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
