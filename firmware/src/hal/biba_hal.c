/* Concrete STM32Cube HAL implementation for BiBa.
 *
 * This file is only compiled for the firmware PlatformIO envs
 * (standalone / companion / combined); the native_test env excludes it
 * via platformio.ini src_filter. */

#include "biba_hal.h"

#include "biba_board.h"
#include "biba_config.h"
#include "biba_proto.h"

#include "stm32f1xx_hal.h"

#include <string.h>

/* --- Peripheral handles ------------------------------------------------- */

static ADC_HandleTypeDef hadc1;     /* current/voltage scan */
static DMA_HandleTypeDef hdma_adc1;
static UART_HandleTypeDef huart_crsf;  /* CRSF — instance set by target macros */
static DMA_HandleTypeDef hdma_crsf_rx;
static SPI_HandleTypeDef hspi2;     /* SBC slave link */
static DMA_HandleTypeDef hdma_spi2_tx;
static DMA_HandleTypeDef hdma_spi2_rx;
static I2C_HandleTypeDef hi2c1;     /* IMU */

/* --- Scan buffers ------------------------------------------------------- */

#define CRSF_RING_SIZE 256
static uint8_t s_crsf_ring[CRSF_RING_SIZE];
static volatile uint16_t s_crsf_read_idx;

static uint16_t s_adc_scan[BIBA_ADC_SCAN_LEN];
static volatile uint32_t s_adc_scan_count;

static volatile bool s_spi_busy;
static bool s_mode_sel_latched_companion;

/* --- Forward declarations ----------------------------------------------- */

static void clock_config(void);
static void gpio_init(void);
static void adc1_init(void);
static void crsf_uart_init(uint32_t baud);
static void spi2_slave_init(void);
static void i2c1_init(void);

/* Last-resort error trap. Lights the status LED solid and busy-loops.
 * Called from any HAL init that returns != HAL_OK so a hardware misconfig
 * never silently degrades into junk telemetry. The status LED is the
 * only side-channel we have on every board variant, so it doubles as
 * the panic indicator. */
static void biba_hal_panic(void)
{
    /* Make sure both motor enables are LOW first: a clock or PWM init
     * failure must not leave the BTS7960 driving with stale duty. */
    HAL_GPIO_WritePin(BIBA_PIN_LEFT_REN_PORT,  BIBA_PIN_LEFT_REN_PIN,  GPIO_PIN_RESET);
    HAL_GPIO_WritePin(BIBA_PIN_LEFT_LEN_PORT,  BIBA_PIN_LEFT_LEN_PIN,  GPIO_PIN_RESET);
    HAL_GPIO_WritePin(BIBA_PIN_RIGHT_REN_PORT, BIBA_PIN_RIGHT_REN_PIN, GPIO_PIN_RESET);
    HAL_GPIO_WritePin(BIBA_PIN_RIGHT_LEN_PORT, BIBA_PIN_RIGHT_LEN_PIN, GPIO_PIN_RESET);
    biba_hal_status_led_set(true);
    for (;;) { __NOP(); }
}

/* --- Public API --------------------------------------------------------- */

void biba_hal_init(void)
{
    /* Disable write buffer so imprecise BusFaults become precise:
     * makes fault address recoverable in the debugger (debug only).
     * On Cortex-M3 this bit lives in the ACTLR register. */
    SCnSCB->ACTLR |= SCnSCB_ACTLR_DISDEFWBUF_Msk;

    HAL_Init();
    clock_config();

    /* Release JTAG so PB3/PB4/PA15 become available as GPIO/AF. On
     * BIBA_F103_REV_A this also frees PA15 for TIM2_CH1 (L_LPWM via
     * TIM2 partial remap 1). */
    __HAL_RCC_AFIO_CLK_ENABLE();
    __HAL_AFIO_REMAP_SWJ_NOJTAG();

    /* Bulk clock gates needed by the peripherals below. */
    __HAL_RCC_GPIOA_CLK_ENABLE();
    __HAL_RCC_GPIOB_CLK_ENABLE();
    __HAL_RCC_GPIOC_CLK_ENABLE();
    __HAL_RCC_DMA1_CLK_ENABLE();

    gpio_init();

    /* Sample MODE_SEL once at boot: pulled up, driven low = companion. */
    s_mode_sel_latched_companion =
        (HAL_GPIO_ReadPin(BIBA_PIN_MODE_SEL_PORT, BIBA_PIN_MODE_SEL_PIN) == GPIO_PIN_RESET);

    /* Motor PWM init lives in biba_hal_motor.c so the topology (single
     * shared timer vs. per-channel timers) can vary per target. */
    biba_hal_motor_pwm_init();
    adc1_init();
    i2c1_init();
    /* USART3 and SPI2 are brought up lazily by the first call from the
     * mode layer: only standalone needs CRSF, only companion needs SPI. */
}

uint32_t biba_hal_now_ms(void) { return HAL_GetTick(); }
void     biba_hal_delay_ms(uint32_t ms) { HAL_Delay(ms); }

void biba_hal_status_led_set(bool on)
{
    /* Honour the target's active-level so targets like BIBA_F103_REV_A
     * (active-high LED on PB5) and BLUEPILL_F103C8 (active-low LED on
     * PC13) share the same call site. */
    GPIO_PinState lit   = BIBA_STATUS_LED_ACTIVE_LOW ? GPIO_PIN_RESET : GPIO_PIN_SET;
    GPIO_PinState unlit = BIBA_STATUS_LED_ACTIVE_LOW ? GPIO_PIN_SET   : GPIO_PIN_RESET;
    HAL_GPIO_WritePin(BIBA_PIN_STATUS_LED_PORT, BIBA_PIN_STATUS_LED_PIN,
                      on ? lit : unlit);
}

void biba_hal_data_ready_set(bool on)
{
    HAL_GPIO_WritePin(BIBA_PIN_DATA_READY_PORT, BIBA_PIN_DATA_READY_PIN,
                      on ? GPIO_PIN_SET : GPIO_PIN_RESET);
}

void biba_hal_data_ready_pulse(void)
{
    biba_hal_data_ready_set(true);
    /* ~1 µs pulse is plenty for an SBC GPIO IRQ. */
    for (volatile int i = 0; i < 72; ++i) { __NOP(); }
    biba_hal_data_ready_set(false);
}

bool biba_hal_mode_sel_is_companion(void) { return s_mode_sel_latched_companion; }

void biba_hal_left_enable(bool enabled)
{
    GPIO_PinState s = enabled ? GPIO_PIN_SET : GPIO_PIN_RESET;
    HAL_GPIO_WritePin(BIBA_PIN_LEFT_REN_PORT, BIBA_PIN_LEFT_REN_PIN, s);
    HAL_GPIO_WritePin(BIBA_PIN_LEFT_LEN_PORT, BIBA_PIN_LEFT_LEN_PIN, s);
}

void biba_hal_right_enable(bool enabled)
{
    GPIO_PinState s = enabled ? GPIO_PIN_SET : GPIO_PIN_RESET;
    HAL_GPIO_WritePin(BIBA_PIN_RIGHT_REN_PORT, BIBA_PIN_RIGHT_REN_PIN, s);
    HAL_GPIO_WritePin(BIBA_PIN_RIGHT_LEN_PORT, BIBA_PIN_RIGHT_LEN_PIN, s);
}

/* Motor-PWM helpers moved to biba_hal_motor.c. */

uint16_t biba_hal_adc_sample(unsigned channel_index)
{
    if (channel_index >= BIBA_ADC_SCAN_LEN) return 0;
    return s_adc_scan[channel_index];
}

uint32_t biba_hal_adc_scan_count(void) { return s_adc_scan_count; }

float biba_hal_adc_volts(uint16_t raw)
{
    return ((float)raw * BIBA_ADC_VREF_V) / (float)BIBA_ADC_MAX_COUNTS;
}

/* CRSF ring buffer served from DMA RX interrupts (half + full transfer). */
static uint16_t crsf_write_idx(void)
{
    /* NDTR counts remaining transfers; convert to absolute write position. */
    uint32_t ndtr = __HAL_DMA_GET_COUNTER(&hdma_crsf_rx);
    return (uint16_t)(CRSF_RING_SIZE - ndtr);
}

size_t biba_hal_crsf_read(uint8_t *dst, size_t cap)
{
    if (dst == NULL || cap == 0) return 0;
    uint16_t write_idx = crsf_write_idx();
    size_t copied = 0;
    while (s_crsf_read_idx != write_idx && copied < cap) {
        dst[copied++] = s_crsf_ring[s_crsf_read_idx];
        s_crsf_read_idx = (uint16_t)((s_crsf_read_idx + 1u) % CRSF_RING_SIZE);
    }
    return copied;
}

uint32_t biba_hal_crsf_write(const uint8_t *data, size_t len)
{
    if (data == NULL || len == 0) return 0;
    /* Bypass HAL state machine: DMA RX marks gState as BUSY_RX which
     * causes HAL_UART_Transmit to return HAL_BUSY even though the TX
     * path is completely independent on a full-duplex UART. Write
     * directly to the peripheral registers instead. */
    for (size_t i = 0; i < len; i++) {
        uint32_t t = 10000u;
        while (!(BIBA_CRSF_UART_INSTANCE->SR & USART_SR_TXE) && --t) {}
        if (!t) return 1u;
        BIBA_CRSF_UART_INSTANCE->DR = data[i];
    }
    /* Wait for transmission complete so the last byte is fully shifted
     * out before the caller returns (important for half-duplex timing). */
    uint32_t t = 10000u;
    while (!(BIBA_CRSF_UART_INSTANCE->SR & USART_SR_TC) && --t) {}
    return t ? 0u : 1u;
}

static uint32_t s_crsf_dma_init_status = 0xFFFFFFFFu; /* sentinel = not called */

void biba_hal_crsf_begin(uint32_t baud)
{
    if (huart_crsf.Instance == NULL) {
        crsf_uart_init(baud);
    }
    HAL_StatusTypeDef st = HAL_UART_Receive_DMA(&huart_crsf, s_crsf_ring, CRSF_RING_SIZE);
    s_crsf_dma_init_status = (uint32_t)st;
    s_crsf_read_idx = 0;
}

biba_hal_crsf_diag_t biba_hal_crsf_diag(void)
{
    biba_hal_crsf_diag_t d;
    d.dma_ndtr        = __HAL_DMA_GET_COUNTER(&hdma_crsf_rx);
    d.uart_error_code = huart_crsf.ErrorCode;
    d.uart_rx_state   = huart_crsf.RxState;
    d.uart_tx_state   = huart_crsf.gState;
    d.uart_sr         = BIBA_CRSF_UART_INSTANCE->SR;
    d.uart_cr1        = BIBA_CRSF_UART_INSTANCE->CR1;
    d.rcc_apb1enr     = RCC->APB1ENR;
    d.dma_init_status = s_crsf_dma_init_status;
    return d;
}

void biba_hal_spi_slave_arm(const uint8_t *tx, uint8_t *rx)
{
    if (hspi2.Instance == NULL) {
        spi2_slave_init();
    }
    /* Set busy *before* arming the DMA so the TX-complete interrupt that
     * may fire on the very next clock edge sees the flag. If the call
     * fails we must clear it so the next tick can retry; otherwise the
     * companion-mode service loop deadlocks on a stale `busy` flag. */
    s_spi_busy = true;
    HAL_StatusTypeDef st =
        HAL_SPI_TransmitReceive_DMA(&hspi2, (uint8_t *)tx, rx, BIBA_PROTO_FRAME_SIZE);
    if (st != HAL_OK) {
        s_spi_busy = false;
    }
}

bool biba_hal_spi_slave_poll(void)
{
    return !s_spi_busy;
}

bool biba_hal_i2c_write(uint8_t addr, const uint8_t *data, size_t len)
{
    HAL_StatusTypeDef st = HAL_I2C_Master_Transmit(&hi2c1, (uint16_t)(addr << 1),
                                                   (uint8_t *)data, (uint16_t)len, 50);
    return st == HAL_OK;
}

bool biba_hal_i2c_read(uint8_t addr, uint8_t reg, uint8_t *data, size_t len)
{
    HAL_StatusTypeDef st = HAL_I2C_Mem_Read(&hi2c1, (uint16_t)(addr << 1), reg,
                                            I2C_MEMADD_SIZE_8BIT, data,
                                            (uint16_t)len, 50);
    return st == HAL_OK;
}

/* --- Interrupt glue ----------------------------------------------------- */

void HAL_ADC_ConvCpltCallback(ADC_HandleTypeDef *hadc)
{
    if (hadc == &hadc1) {
        s_adc_scan_count++;
    }
}

void HAL_SPI_TxRxCpltCallback(SPI_HandleTypeDef *hspi)
{
    if (hspi == &hspi2) {
        s_spi_busy = false;
    }
}

/* --- Peripheral init ---------------------------------------------------- */

static void clock_config(void)
{
    RCC_OscInitTypeDef osc = {0};
    RCC_ClkInitTypeDef clk = {0};

    osc.OscillatorType = RCC_OSCILLATORTYPE_HSE;
    osc.HSEState = RCC_HSE_ON;
    osc.HSEPredivValue = RCC_HSE_PREDIV_DIV1;
    osc.PLL.PLLState = RCC_PLL_ON;
    osc.PLL.PLLSource = RCC_PLLSOURCE_HSE;
    osc.PLL.PLLMUL = RCC_PLL_MUL9;   /* 8 MHz * 9 = 72 MHz */
    if (HAL_RCC_OscConfig(&osc) != HAL_OK) {
        biba_hal_panic();
    }

    clk.ClockType = RCC_CLOCKTYPE_HCLK | RCC_CLOCKTYPE_SYSCLK
                  | RCC_CLOCKTYPE_PCLK1 | RCC_CLOCKTYPE_PCLK2;
    clk.SYSCLKSource = RCC_SYSCLKSOURCE_PLLCLK;
    clk.AHBCLKDivider = RCC_SYSCLK_DIV1;
    clk.APB1CLKDivider = RCC_HCLK_DIV2;   /* 36 MHz */
    clk.APB2CLKDivider = RCC_HCLK_DIV1;   /* 72 MHz */
    if (HAL_RCC_ClockConfig(&clk, FLASH_LATENCY_2) != HAL_OK) {
        biba_hal_panic();
    }
}

static void gpio_init(void)
{
    GPIO_InitTypeDef g = {0};

    /* Status LED */
    g.Pin = BIBA_PIN_STATUS_LED_PIN;
    g.Mode = GPIO_MODE_OUTPUT_PP;
    g.Speed = GPIO_SPEED_FREQ_LOW;
    HAL_GPIO_Init(BIBA_PIN_STATUS_LED_PORT, &g);
    biba_hal_status_led_set(false);

    /* BTS7960 enables as output push-pull, start disabled. */
    g.Pin = BIBA_PIN_LEFT_REN_PIN;  HAL_GPIO_Init(BIBA_PIN_LEFT_REN_PORT, &g);
    g.Pin = BIBA_PIN_LEFT_LEN_PIN;  HAL_GPIO_Init(BIBA_PIN_LEFT_LEN_PORT, &g);
    g.Pin = BIBA_PIN_RIGHT_REN_PIN; HAL_GPIO_Init(BIBA_PIN_RIGHT_REN_PORT, &g);
    g.Pin = BIBA_PIN_RIGHT_LEN_PIN; HAL_GPIO_Init(BIBA_PIN_RIGHT_LEN_PORT, &g);
    biba_hal_left_enable(false);
    biba_hal_right_enable(false);

    /* DATA_READY output to SBC, driven low at boot. */
    g.Pin = BIBA_PIN_DATA_READY_PIN;
    HAL_GPIO_Init(BIBA_PIN_DATA_READY_PORT, &g);
    biba_hal_data_ready_set(false);

    /* MODE_SEL input pull-up. */
    g.Pin = BIBA_PIN_MODE_SEL_PIN;
    g.Mode = GPIO_MODE_INPUT;
    g.Pull = GPIO_PULLUP;
    HAL_GPIO_Init(BIBA_PIN_MODE_SEL_PORT, &g);

    /* TIM channel AF pin init and timer setup live in biba_hal_motor.c. */

    /* ADC analog inputs. PA7 is intentionally NOT in the bitmask on the
     * REV_A target because it is repurposed as MODE_SEL (digital input,
     * configured separately above). On BLUEPILL the pin is unused so
     * leaving it floating is fine. */
    g.Pin = GPIO_PIN_0 | GPIO_PIN_1 | GPIO_PIN_2 | GPIO_PIN_3
          | GPIO_PIN_4 | GPIO_PIN_5 | GPIO_PIN_6;
    g.Mode = GPIO_MODE_ANALOG;
    g.Pull = GPIO_NOPULL;
    HAL_GPIO_Init(GPIOA, &g);
}

static void adc1_init(void)
{
    __HAL_RCC_ADC1_CLK_ENABLE();

    hadc1.Instance = ADC1;
    hadc1.Init.ScanConvMode = ADC_SCAN_ENABLE;
    hadc1.Init.ContinuousConvMode = ENABLE;
    hadc1.Init.DiscontinuousConvMode = DISABLE;
    hadc1.Init.ExternalTrigConv = ADC_SOFTWARE_START;
    hadc1.Init.DataAlign = ADC_DATAALIGN_RIGHT;
    hadc1.Init.NbrOfConversion = BIBA_ADC_SCAN_LEN;
    if (HAL_ADC_Init(&hadc1) != HAL_OK) {
        biba_hal_panic();
    }

    static const uint32_t chans[BIBA_ADC_SCAN_LEN] = BIBA_ADC_CHANNEL_SEQ;
    for (unsigned i = 0; i < BIBA_ADC_SCAN_LEN; ++i) {
        ADC_ChannelConfTypeDef s = {0};
        s.Channel = chans[i];
        s.Rank = (uint32_t)(ADC_REGULAR_RANK_1 + i);
        s.SamplingTime = ADC_SAMPLETIME_55CYCLES_5;
        if (HAL_ADC_ConfigChannel(&hadc1, &s) != HAL_OK) {
            biba_hal_panic();
        }
    }

    hdma_adc1.Instance = DMA1_Channel1;
    hdma_adc1.Init.Direction = DMA_PERIPH_TO_MEMORY;
    hdma_adc1.Init.PeriphInc = DMA_PINC_DISABLE;
    hdma_adc1.Init.MemInc = DMA_MINC_ENABLE;
    hdma_adc1.Init.PeriphDataAlignment = DMA_PDATAALIGN_HALFWORD;
    hdma_adc1.Init.MemDataAlignment = DMA_MDATAALIGN_HALFWORD;
    hdma_adc1.Init.Mode = DMA_CIRCULAR;
    hdma_adc1.Init.Priority = DMA_PRIORITY_HIGH;
    if (HAL_DMA_Init(&hdma_adc1) != HAL_OK) {
        biba_hal_panic();
    }
    __HAL_LINKDMA(&hadc1, DMA_Handle, hdma_adc1);
    HAL_NVIC_SetPriority(DMA1_Channel1_IRQn, 1, 0);
    HAL_NVIC_EnableIRQ(DMA1_Channel1_IRQn);

    if (HAL_ADCEx_Calibration_Start(&hadc1) != HAL_OK) {
        biba_hal_panic();
    }
    if (HAL_ADC_Start_DMA(&hadc1, (uint32_t *)s_adc_scan, BIBA_ADC_SCAN_LEN) != HAL_OK) {
        biba_hal_panic();
    }
}

static void crsf_uart_init(uint32_t baud)
{
    BIBA_CRSF_CLK_ENABLE();
    BIBA_CRSF_AF_REMAP();

    GPIO_InitTypeDef g = {0};
    g.Pin = BIBA_PIN_CRSF_TX_PIN;
    g.Mode = GPIO_MODE_AF_PP;
    g.Speed = GPIO_SPEED_FREQ_HIGH;
    HAL_GPIO_Init(BIBA_PIN_CRSF_TX_PORT, &g);

    g.Pin = BIBA_PIN_CRSF_RX_PIN;
    g.Mode = GPIO_MODE_INPUT;
    g.Pull = GPIO_PULLUP;
    HAL_GPIO_Init(BIBA_PIN_CRSF_RX_PORT, &g);

    huart_crsf.Instance = BIBA_CRSF_UART_INSTANCE;
    huart_crsf.Init.BaudRate = baud;
    huart_crsf.Init.WordLength = UART_WORDLENGTH_8B;
    huart_crsf.Init.StopBits = UART_STOPBITS_1;
    huart_crsf.Init.Parity = UART_PARITY_NONE;
    huart_crsf.Init.Mode = UART_MODE_TX_RX;
    huart_crsf.Init.HwFlowCtl = UART_HWCONTROL_NONE;
    huart_crsf.Init.OverSampling = UART_OVERSAMPLING_16;
    if (HAL_UART_Init(&huart_crsf) != HAL_OK) {
        biba_hal_panic();
    }

    hdma_crsf_rx.Instance = BIBA_CRSF_DMA_CHANNEL_RX;
    hdma_crsf_rx.Init.Direction = DMA_PERIPH_TO_MEMORY;
    hdma_crsf_rx.Init.PeriphInc = DMA_PINC_DISABLE;
    hdma_crsf_rx.Init.MemInc = DMA_MINC_ENABLE;
    hdma_crsf_rx.Init.PeriphDataAlignment = DMA_PDATAALIGN_BYTE;
    hdma_crsf_rx.Init.MemDataAlignment = DMA_MDATAALIGN_BYTE;
    hdma_crsf_rx.Init.Mode = DMA_CIRCULAR;
    hdma_crsf_rx.Init.Priority = DMA_PRIORITY_MEDIUM;
    if (HAL_DMA_Init(&hdma_crsf_rx) != HAL_OK) {
        biba_hal_panic();
    }
    __HAL_LINKDMA(&huart_crsf, hdmarx, hdma_crsf_rx);
    HAL_NVIC_SetPriority(BIBA_CRSF_DMA_IRQn_RX, 2, 0);
    HAL_NVIC_EnableIRQ(BIBA_CRSF_DMA_IRQn_RX);
    HAL_NVIC_SetPriority(BIBA_CRSF_UART_IRQn, 2, 0);
    HAL_NVIC_EnableIRQ(BIBA_CRSF_UART_IRQn);
}

static void spi2_slave_init(void)
{
    __HAL_RCC_SPI2_CLK_ENABLE();

    GPIO_InitTypeDef g = {0};
    g.Pin = BIBA_PIN_SPI_SCK_PIN | BIBA_PIN_SPI_MOSI_PIN | BIBA_PIN_SPI_NSS_PIN;
    g.Mode = GPIO_MODE_INPUT;
    g.Pull = GPIO_PULLUP;
    HAL_GPIO_Init(GPIOB, &g);

    g.Pin = BIBA_PIN_SPI_MISO_PIN;
    g.Mode = GPIO_MODE_AF_PP;
    g.Speed = GPIO_SPEED_FREQ_HIGH;
    HAL_GPIO_Init(BIBA_PIN_SPI_MISO_PORT, &g);

    hspi2.Instance = SPI2;
    hspi2.Init.Mode = SPI_MODE_SLAVE;
    hspi2.Init.Direction = SPI_DIRECTION_2LINES;
    hspi2.Init.DataSize = SPI_DATASIZE_8BIT;
    hspi2.Init.CLKPolarity = SPI_POLARITY_LOW;
    hspi2.Init.CLKPhase = SPI_PHASE_1EDGE;
    hspi2.Init.NSS = SPI_NSS_HARD_INPUT;
    hspi2.Init.FirstBit = SPI_FIRSTBIT_MSB;
    hspi2.Init.TIMode = SPI_TIMODE_DISABLE;
    hspi2.Init.CRCCalculation = SPI_CRCCALCULATION_DISABLE;
    if (HAL_SPI_Init(&hspi2) != HAL_OK) {
        biba_hal_panic();
    }

    hdma_spi2_tx.Instance = DMA1_Channel5;
    hdma_spi2_tx.Init.Direction = DMA_MEMORY_TO_PERIPH;
    hdma_spi2_tx.Init.PeriphInc = DMA_PINC_DISABLE;
    hdma_spi2_tx.Init.MemInc = DMA_MINC_ENABLE;
    hdma_spi2_tx.Init.PeriphDataAlignment = DMA_PDATAALIGN_BYTE;
    hdma_spi2_tx.Init.MemDataAlignment = DMA_MDATAALIGN_BYTE;
    hdma_spi2_tx.Init.Mode = DMA_NORMAL;
    hdma_spi2_tx.Init.Priority = DMA_PRIORITY_HIGH;
    if (HAL_DMA_Init(&hdma_spi2_tx) != HAL_OK) {
        biba_hal_panic();
    }
    __HAL_LINKDMA(&hspi2, hdmatx, hdma_spi2_tx);

    hdma_spi2_rx.Instance = DMA1_Channel4;
    hdma_spi2_rx.Init.Direction = DMA_PERIPH_TO_MEMORY;
    hdma_spi2_rx.Init.PeriphInc = DMA_PINC_DISABLE;
    hdma_spi2_rx.Init.MemInc = DMA_MINC_ENABLE;
    hdma_spi2_rx.Init.PeriphDataAlignment = DMA_PDATAALIGN_BYTE;
    hdma_spi2_rx.Init.MemDataAlignment = DMA_MDATAALIGN_BYTE;
    hdma_spi2_rx.Init.Mode = DMA_NORMAL;
    hdma_spi2_rx.Init.Priority = DMA_PRIORITY_HIGH;
    if (HAL_DMA_Init(&hdma_spi2_rx) != HAL_OK) {
        biba_hal_panic();
    }
    __HAL_LINKDMA(&hspi2, hdmarx, hdma_spi2_rx);

    HAL_NVIC_SetPriority(DMA1_Channel4_IRQn, 1, 0);
    HAL_NVIC_EnableIRQ(DMA1_Channel4_IRQn);
    HAL_NVIC_SetPriority(DMA1_Channel5_IRQn, 1, 0);
    HAL_NVIC_EnableIRQ(DMA1_Channel5_IRQn);
    HAL_NVIC_SetPriority(SPI2_IRQn, 1, 0);
    HAL_NVIC_EnableIRQ(SPI2_IRQn);
}

static void i2c1_init(void)
{
    __HAL_RCC_I2C1_CLK_ENABLE();

    GPIO_InitTypeDef g = {0};
    g.Pin = BIBA_PIN_I2C_SCL_PIN | BIBA_PIN_I2C_SDA_PIN;
    g.Mode = GPIO_MODE_AF_OD;
    g.Pull = GPIO_PULLUP;
    g.Speed = GPIO_SPEED_FREQ_HIGH;
    HAL_GPIO_Init(GPIOB, &g);

    hi2c1.Instance = I2C1;
    hi2c1.Init.ClockSpeed = 400000;
    hi2c1.Init.DutyCycle = I2C_DUTYCYCLE_2;
    hi2c1.Init.OwnAddress1 = 0;
    hi2c1.Init.AddressingMode = I2C_ADDRESSINGMODE_7BIT;
    hi2c1.Init.DualAddressMode = I2C_DUALADDRESS_DISABLE;
    hi2c1.Init.OwnAddress2 = 0;
    hi2c1.Init.GeneralCallMode = I2C_GENERALCALL_DISABLE;
    hi2c1.Init.NoStretchMode = I2C_NOSTRETCH_DISABLE;
    if (HAL_I2C_Init(&hi2c1) != HAL_OK) {
        biba_hal_panic();
    }
}

/* --- IRQ handlers (declared in startup_stm32f103xb.s) ------------------- */

void DMA1_Channel1_IRQHandler(void) { HAL_DMA_IRQHandler(&hdma_adc1); }
void BIBA_CRSF_DMA_IRQ_HANDLER(void) { HAL_DMA_IRQHandler(&hdma_crsf_rx); }
void DMA1_Channel4_IRQHandler(void) { HAL_DMA_IRQHandler(&hdma_spi2_rx); }
void DMA1_Channel5_IRQHandler(void) { HAL_DMA_IRQHandler(&hdma_spi2_tx); }
void BIBA_CRSF_UART_IRQ_HANDLER(void) { HAL_UART_IRQHandler(&huart_crsf); }
void SPI2_IRQHandler(void)          { HAL_SPI_IRQHandler(&hspi2); }

void SysTick_Handler(void) { HAL_IncTick(); }
