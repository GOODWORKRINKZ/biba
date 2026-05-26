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
    /* Clock divider formula.  pico-sdk: sample period = (1 + div) cycles
     * of the 48 MHz ADC clock.  Minimum conversion time is 96 cycles
     * (≈500 kSPS hard cap), but the divisor itself does NOT include the
     * /96 — that is the conversion-time floor, not a frequency divider.
     *
     * For 10 kSPS:  div = 48e6/10e3 - 1 = 4799.
     *
     * Previous version had an extra /96 in here which made the ADC run
     * 50× faster than requested.  CAPTURE windows were 4 ms instead of
     * 205 ms, which silently shrank the ZC window so far that the RPMRUN
     * loop could never see the 2-25 Hz fundamental and produced random
     * meas_hz from noise crossings. */
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

/* --- 4-channel round-robin (Phase 11: IS_L + IS_R + VBAT + IBAT) --------- */

void adc_capture_init_4ch(uint32_t sample_rate_sps)
{
    adc_init();
    adc_gpio_init(26);  /* GP26 = ADC0 = IS_LEFT  */
    adc_gpio_init(27);  /* GP27 = ADC1 = IS_RIGHT */
    adc_gpio_init(28);  /* GP28 = ADC2 = VBAT     */
    adc_gpio_init(29);  /* GP29 = ADC3 = IBAT     */

    adc_set_round_robin(
        (1u << 0) |     /* ADC0 = IS_LEFT  */
        (1u << 1) |     /* ADC1 = IS_RIGHT */
        (1u << 2) |     /* ADC2 = VBAT     */
        (1u << 3)       /* ADC3 = IBAT     */
    );

    adc_fifo_setup(
        true,   /* en: enable FIFO */
        true,   /* shift: enable DREQ */
        1,      /* dreq_thresh: DMA request per sample */
        false,  /* err_in_fifo */
        false   /* byte_shift: keep 12-bit */
    );

    float div = (float)48000000u / (float)sample_rate_sps - 1.0f;
    if (div < 0.0f) div = 0.0f;
    adc_set_clkdiv(div);
}

/* Capture N samples PER CHANNEL (total DMA transfer = N*4 samples).
 * Interleaved order: IS_L, IS_R, VBAT, IBAT, IS_L, IS_R, ...
 * Output: out[0..N-1]=IS_L, out[N..2N-1]=IS_R, out[2N..3N-1]=VBAT, out[3N..4N-1]=IBAT */
bool adc_capture_burst_4ch(uint16_t n_per_ch, uint16_t *out_buf)
{
    uint32_t total = (uint32_t)n_per_ch * 4u;
    if (total > ADC_CAPTURE_MAX_SAMPLES) return false;

    int dma_ch = dma_claim_unused_channel(true);
    dma_channel_config cfg = dma_channel_get_default_config(dma_ch);
    channel_config_set_transfer_data_size(&cfg, DMA_SIZE_16);
    channel_config_set_read_increment(&cfg, false);
    channel_config_set_write_increment(&cfg, true);
    channel_config_set_dreq(&cfg, DREQ_ADC);

    /* Capture interleaved into temp buffer, then deinterleave */
    static uint16_t tmp[ADC_CAPTURE_MAX_SAMPLES];
    dma_channel_configure(dma_ch, &cfg, tmp, &adc_hw->fifo, total, true);
    adc_run(true);

    uint32_t t0 = to_ms_since_boot(get_absolute_time());
    while (dma_channel_is_busy(dma_ch)) {
        if (to_ms_since_boot(get_absolute_time()) - t0 > 500u) {
            adc_run(false); adc_fifo_drain();
            dma_channel_abort(dma_ch);
            dma_channel_unclaim(dma_ch);
            return false;
        }
    }

    adc_run(false);
    adc_fifo_drain();
    dma_channel_unclaim(dma_ch);

    /* Deinterleave: tmp[0,4,8,...]=IS_L  tmp[1,5,9,...]=IS_R
     *               tmp[2,6,10,...]=VBAT  tmp[3,7,11,...]=IBAT */
    for (uint16_t i = 0; i < n_per_ch; ++i) {
        out_buf[i]                = tmp[(uint32_t)i * 4u];
        out_buf[n_per_ch + i]     = tmp[(uint32_t)i * 4u + 1u];
        out_buf[n_per_ch * 2 + i] = tmp[(uint32_t)i * 4u + 2u];
        out_buf[n_per_ch * 3 + i] = tmp[(uint32_t)i * 4u + 3u];
    }
    return true;
}
