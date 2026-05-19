#include "voltage_sense.h"

#include "biba_board.h"
#include "biba_config.h"
#include "hal/biba_hal.h"

uint16_t biba_voltage_sense_vbat_mv(void)
{
    uint16_t raw = biba_hal_adc_sample(BIBA_ADC_CHAN_VBAT);
    float pin_v = biba_hal_adc_volts(raw);
    float bus_v = pin_v * BIBA_VBAT_DIVIDER_RATIO;
    if (bus_v < 0.0f) bus_v = 0.0f;
    if (bus_v > 65.0f) bus_v = 65.0f;
    return (uint16_t)(bus_v * 1000.0f);
}

float biba_voltage_sense_ibat_a(void)
{
#ifdef BIBA_ADC_CHAN_IBAT
    uint16_t raw = biba_hal_adc_sample(BIBA_ADC_CHAN_IBAT);
    float pin_v = biba_hal_adc_volts(raw);
    float amps = (pin_v - BIBA_IBAT_ZERO_OFFSET_V) * BIBA_IBAT_AMPS_PER_VOLT;
    if (amps < 0.0f) amps = 0.0f;
    return amps;
#else
    return 0.0f;
#endif
}

uint16_t biba_voltage_sense_rail_mv(void)
{
#ifdef BIBA_TARGET_HAS_CHASSIS_NTC
    /* On boards where PA5 is a chassis-temperature NTC (Rev A and
     * later) the channel does not represent a voltage rail at all.
     * Decoding the NTC into a temperature belongs in a future driver;
     * meanwhile we report 0 mV so downstream telemetry consumers do not
     * mistake the NTC reading for a real 12 V tap. */
    return 0;
#else
    uint16_t raw = biba_hal_adc_sample(BIBA_ADC_CHAN_RAIL_12V);
    /* Rail uses its own divider so boards with a different tap on PA5
     * (e.g. higher / lower voltage rail) can override
     * BIBA_RAIL_12V_DIVIDER_RATIO without touching VBAT. */
    float pin_v = biba_hal_adc_volts(raw);
    float bus_v = pin_v * BIBA_RAIL_12V_DIVIDER_RATIO;
    if (bus_v < 0.0f) bus_v = 0.0f;
    if (bus_v > 20.0f) bus_v = 20.0f;
    return (uint16_t)(bus_v * 1000.0f);
#endif
}
