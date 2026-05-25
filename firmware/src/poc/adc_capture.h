#pragma once
#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

#define ADC_CAPTURE_MAX_SAMPLES  4096u

/* Initialise RP2040 ADC clock divider for the target sample rate.
 * Must be called before adc_capture_burst().
 * sample_rate_sps: desired rate (e.g. 10000 = 10 kSPS). */
void adc_capture_init(uint32_t sample_rate_sps);

/* DMA burst capture on a single ADC channel.
 * channel: 0 = IS_LEFT (GP26 / BIBA_ADC_CHAN_IS_LEFT)
 *          1 = IS_RIGHT (GP27 / BIBA_ADC_CHAN_IS_RIGHT)
 * n_samples: number of 12-bit samples (max ADC_CAPTURE_MAX_SAMPLES).
 * out_buf: caller buffer, size >= n_samples uint16_t.
 * Returns true on success, false on DMA timeout (> 500 ms). */
bool adc_capture_burst(uint8_t channel, uint16_t n_samples, uint16_t *out_buf);

#ifdef __cplusplus
}
#endif
