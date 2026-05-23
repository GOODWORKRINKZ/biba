#include "app/adc_capture.h"

#include <hardware/adc.h>
#include <hardware/dma.h>
#include <hardware/irq.h>
#include <pico/time.h>

/* Async DMA capture state — single in-flight transfer at a time.
 * s_dma_ch == -1 marks "idle" (no DMA claimed). All other state is only
 * valid while s_dma_ch >= 0. */
static adc_capture_done_cb_t s_done_cb;
static int      s_dma_ch  = -1;
static uint8_t  s_last_ch;
static uint16_t s_last_n;
static uint16_t *s_buf_ptr;

void adc_capture_init(uint32_t sample_rate_sps)
{
    adc_init();
    adc_gpio_init(26);  /* GP26 = IS_LEFT  (BIBA_ADC_CHAN_IS_LEFT)  */
    adc_gpio_init(27);  /* GP27 = IS_RIGHT (BIBA_ADC_CHAN_IS_RIGHT) */
    /* Single-channel mode only. Multi-channel interleaving is intentionally
     * disabled — it would distort the single-channel time-domain signal
     * needed for RPM frequency analysis. */
    adc_fifo_setup(
        true,   /* en: enable FIFO */
        true,   /* shift: shift 8-bit result into FIFO (dreq_en) */
        1,      /* dreq_thresh: generate DMA request per sample */
        false,  /* err_in_fifo: don't insert error flag */
        false   /* byte_shift: keep 12-bit samples */
    );
    /* Clock divider formula.  pico-sdk: sample period = (1 + div) cycles
     * of the 48 MHz ADC clock.  For 10 kSPS:  div = 48e6/10e3 - 1 = 4799. */
    float div = (float)48000000u / (float)sample_rate_sps - 1.0f;
    if (div < 0.0f) div = 0.0f;
    adc_set_clkdiv(div);
}

bool adc_capture_burst(uint8_t channel, uint16_t n_samples, uint16_t *out_buf)
{
    if (n_samples > ADC_CAPTURE_MAX_SAMPLES) {
        n_samples = ADC_CAPTURE_MAX_SAMPLES;
    }

    adc_select_input(channel);

    int dma_ch = dma_claim_unused_channel(true);

    dma_channel_config cfg = dma_channel_get_default_config(dma_ch);
    channel_config_set_transfer_data_size(&cfg, DMA_SIZE_16);
    channel_config_set_read_increment(&cfg, false);
    channel_config_set_write_increment(&cfg, true);
    channel_config_set_dreq(&cfg, DREQ_ADC);

    dma_channel_configure(
        dma_ch,
        &cfg,
        out_buf,            /* write address  */
        &adc_hw->fifo,      /* read address   */
        n_samples,          /* transfer count */
        true                /* start immediately */
    );

    adc_run(true);

    /* Wait for DMA to complete with a 500 ms timeout. */
    uint32_t t0 = to_ms_since_boot(get_absolute_time());
    while (dma_channel_is_busy(dma_ch)) {
        if (to_ms_since_boot(get_absolute_time()) - t0 > 500u) {
            adc_run(false);
            adc_fifo_drain();
            dma_channel_abort(dma_ch);
            dma_channel_unclaim(dma_ch);
            return false;
        }
    }

    adc_run(false);
    adc_fifo_drain();
    dma_channel_unclaim(dma_ch);
    return true;
}

/* DMA completion ISR — runs in IRQ context on core0.
 * Acknowledges the IRQ, stops ADC, drains FIFO, releases the channel,
 * then dispatches the user callback. Idle-marks (s_dma_ch=-1) BEFORE
 * the callback so the callback can synchronously start the next capture. */
static void dma_irq_handler(void)
{
    if (s_dma_ch >= 0 && dma_channel_get_irq0_status(s_dma_ch)) {
        dma_channel_acknowledge_irq0(s_dma_ch);
        adc_run(false);
        adc_fifo_drain();
        int ch = s_dma_ch;
        s_dma_ch = -1;
        dma_channel_unclaim(ch);
        if (s_done_cb) {
            s_done_cb(s_last_ch, s_buf_ptr, s_last_n);
        }
    }
}

bool adc_capture_start_async(uint8_t channel, uint16_t n_samples,
                             uint16_t *out_buf, adc_capture_done_cb_t callback)
{
    /* Busy guard — single in-flight transfer at a time. */
    if (s_dma_ch >= 0) return false;
    if (n_samples > ADC_CAPTURE_MAX_SAMPLES) {
        n_samples = ADC_CAPTURE_MAX_SAMPLES;
    }

    s_last_ch = channel;
    s_last_n  = n_samples;
    s_buf_ptr = out_buf;
    s_done_cb = callback;

    adc_select_input(channel);

    s_dma_ch = dma_claim_unused_channel(true);

    dma_channel_config cfg = dma_channel_get_default_config(s_dma_ch);
    channel_config_set_transfer_data_size(&cfg, DMA_SIZE_16);
    channel_config_set_read_increment(&cfg, false);
    channel_config_set_write_increment(&cfg, true);
    channel_config_set_dreq(&cfg, DREQ_ADC);

    dma_channel_configure(
        s_dma_ch,
        &cfg,
        out_buf,            /* write address  */
        &adc_hw->fifo,      /* read address   */
        n_samples,          /* transfer count */
        false               /* do NOT start yet — IRQ enable first */
    );

    /* Enable per-channel IRQ on DMA_IRQ_0 and register the shared handler.
     * irq_add_shared_handler is idempotent for the same handler pointer —
     * subsequent calls are no-ops. */
    dma_channel_set_irq0_enabled(s_dma_ch, true);
    irq_add_shared_handler(DMA_IRQ_0, dma_irq_handler,
                           PICO_SHARED_IRQ_HANDLER_DEFAULT_ORDER_PRIORITY);
    irq_set_enabled(DMA_IRQ_0, true);

    dma_channel_start(s_dma_ch);
    adc_run(true);
    return true;
}

bool adc_capture_busy(void)
{
    return s_dma_ch >= 0;
}
