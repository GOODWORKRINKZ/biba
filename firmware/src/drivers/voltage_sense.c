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

uint16_t biba_voltage_sense_rail_mv(void)
{
    uint16_t raw = biba_hal_adc_sample(BIBA_ADC_CHAN_RAIL_12V);
    /* Rail uses its own divider so boards with a different tap on PA5
     * (e.g. higher / lower voltage rail, or a chassis NTC bias network)
     * can override BIBA_RAIL_12V_DIVIDER_RATIO without touching VBAT. */
    float pin_v = biba_hal_adc_volts(raw);
    float bus_v = pin_v * BIBA_RAIL_12V_DIVIDER_RATIO;
    if (bus_v < 0.0f) bus_v = 0.0f;
    if (bus_v > 20.0f) bus_v = 20.0f;
    return (uint16_t)(bus_v * 1000.0f);
}
