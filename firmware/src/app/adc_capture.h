#pragma once
#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

#define ADC_CAPTURE_MAX_SAMPLES  4096u

/* Initialise RP2040 ADC clock divider for the target sample rate.
 * Must be called before adc_capture_burst() or adc_capture_start_async().
 * sample_rate_sps: desired rate (e.g. 10000 = 10 kSPS). */
void adc_capture_init(uint32_t sample_rate_sps);

/* DMA burst capture on a single ADC channel — BLOCKING (≈100 ms @
 * 1024 samples @ 10 kSPS). Use ONLY in PoC env / Unity tests / calibration,
 * never in mode_standalone_tick().
 *
 * channel: 0 = IS_LEFT (GP26 / BIBA_ADC_CHAN_IS_LEFT)
 *          1 = IS_RIGHT (GP27 / BIBA_ADC_CHAN_IS_RIGHT)
 * n_samples: number of 12-bit samples (max ADC_CAPTURE_MAX_SAMPLES).
 * out_buf: caller buffer, size >= n_samples uint16_t.
 * Returns true on success, false on DMA timeout (> 500 ms). */
bool adc_capture_burst(uint8_t channel, uint16_t n_samples, uint16_t *out_buf);

/* Async completion callback. Invoked from DMA_IRQ_0 context (core0) when
 * the requested transfer completes. MUST NOT block or allocate.
 * channel: same channel passed to adc_capture_start_async()
 * buf:     same buffer passed in
 * n:       n_samples (number of valid uint16_t entries) */
typedef void (*adc_capture_done_cb_t)(uint8_t channel, const uint16_t *buf, uint16_t n);
typedef void (*adc_capture_pair_done_cb_t)(const uint16_t *interleaved_buf,
                                           uint16_t samples_per_channel);

/* Non-blocking variant — starts DMA and returns immediately. Calls callback
 * from DMA_IRQ_0 context (core0) when n_samples transferred.
 * Returns false if DMA already in flight (caller must wait or check
 * adc_capture_busy()). */
bool adc_capture_start_async(uint8_t channel, uint16_t n_samples,
                             uint16_t *out_buf, adc_capture_done_cb_t callback);

/* Non-blocking two-channel round-robin capture. The ADC runs at the aggregate
 * rate configured by adc_capture_init(); for 10 kSPS per channel with two
 * channels, call adc_capture_init(20000). The output buffer receives samples
 * interleaved as A0,B0,A1,B1,... */
bool adc_capture_start_async_pair(uint8_t channel_a, uint8_t channel_b,
                                  uint16_t samples_per_channel,
                                  uint16_t *out_interleaved_buf,
                                  adc_capture_pair_done_cb_t callback);

/* Returns true while an async capture is in flight (DMA channel still
 * claimed). False indicates the buffer from the last adc_capture_start_async()
 * is safe to read and a new capture can be started. */
bool adc_capture_busy(void);

/* --- 4-channel round-robin (Phase 11: IS_L + IS_R + VBAT + IBAT) --------- */
void adc_capture_init_4ch(uint32_t sample_rate_sps);
bool adc_capture_burst_4ch(uint16_t n_per_ch, uint16_t *out_buf);

#ifdef __cplusplus
}
#endif
