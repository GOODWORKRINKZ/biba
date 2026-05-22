#include "poc/adc_capture.h"

#include <hardware/adc.h>
#include <hardware/dma.h>
#include <pico/time.h>

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
    /* Clock divider formula (Pitfall 2: subtract 1 to get the correct
     * divisor — the RP2040 ADC clock is 48 MHz, each conversion takes
     * 96 ADC clocks, so: div = (48e6 / (96 * sps)) - 1              */
    float div = (float)48000000u / (96.0f * (float)sample_rate_sps) - 1.0f;
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
