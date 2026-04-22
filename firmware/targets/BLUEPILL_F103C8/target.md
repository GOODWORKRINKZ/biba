# Target: BLUEPILL_F103C8

Reference BiBa target on the stock STM32F103C8T6 "Blue Pill" dev board.
This is what you get if you wire a Blue Pill straight to two BTS7960
drivers, an ELRS receiver, an optional IMU on I²C, and (optionally) a
Raspberry Pi over SPI2. It is the default target of every CI build.

## Board

| Field        | Value                         |
| ------------ | ----------------------------- |
| MCU          | STM32F103C8T6                 |
| Flash        | 64 KB (often 128 KB on C6T6)  |
| RAM          | 20 KB                         |
| External XO  | 8 MHz (`HSE_VALUE=8000000`)   |
| PIO `board`  | `bluepill_f103c8`             |

## Pin map

| Function                                  | Pin         |
| ----------------------------------------- | ----------- |
| TIM1_CH1 — Left RPWM                      | PA8         |
| TIM1_CH2 — Left LPWM                      | PA9         |
| TIM1_CH3 — Right RPWM                     | PA10        |
| TIM1_CH4 — Right LPWM                     | PA11        |
| Left BTS7960 R_EN / L_EN                  | PB3 / PB4   |
| Right BTS7960 R_EN / L_EN                 | PB5 / PB8   |
| ADC1 IN0..IN3 — 4× BTS7960 `IS`           | PA0..PA3    |
| ADC1 IN4 — VBAT (1:11 divider)            | PA4         |
| ADC1 IN5 — 12 V rail (optional)           | PA5         |
| ADC1 IN6 — aux / spare                    | PA6         |
| USART3 TX / RX — CRSF                     | PB10 / PB11 |
| SPI2 NSS / SCK / MISO / MOSI              | PB12..PB15  |
| DATA_READY → SBC                          | PA12        |
| MODE_SEL (pull-up; GND = companion)       | PB9         |
| I2C1 SCL / SDA — IMU                      | PB6 / PB7   |
| IMU INT1                                  | PB2         |
| Status LED (active low)                   | PC13        |

## Caveats

- JTAG is released at boot so PB3 / PB4 / PA15 are usable as GPIOs —
  SWD stays available on PA13 / PA14 for programming and debug.
- USART1 on PA9 / PA10 is unavailable because those pins carry
  TIM1_CH2 / TIM1_CH3. CRSF therefore rides on USART3.
- BTS7960 drivers need an independent 5 V / 6 V power supply; ground
  must be shared with the MCU.
- **No motor-audio on this target.** All four PWM lines share TIM1, so
  they share a single carrier frequency. Use `BIBA_F103_REV_A` for
  sound-via-wheels playback.
