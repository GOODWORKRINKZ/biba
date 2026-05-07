# Target: RPICO_RP2040

Compact RP2040 board (USB-C, dual Cortex-M0+ @ 125 MHz, 264 KB SRAM, 2 MB Flash).
Compatible with the standard Raspberry Pi Pico pin numbering.
PlatformIO board ID: **`rpipico`**.

Board pinout reference (save the image next to this file as `board_pinout.png`):

```
                         ┌─────USB-C─────┐
                    LED ◄─ GP25          │
                         │               │
  CRSF TX  UART0_TX  GP0 ┤             ├ VREF
  CRSF RX  UART0_RX  GP1 ┤  RP2040     ├ Vout
                     GND ┤             ├ Vin / GND
  L_RPWM   PWM1A     GP2 ┤             ├ GP23
  L_LPWM   PWM1B     GP3 ┤             ├ 3V3
  L_REN    GPIO OUT  GP4 ┤             ├ GP29  ADC3
  L_LEN    GPIO OUT  GP5 ┤  ┌──────┐   ├ GP28  ADC2  R_IS
                     GND ┤  │      │   ├ AGND
  R_RPWM   PWM3A     GP6 ┤  │      │   ├ GP27  ADC1  L_IS
  R_LPWM   PWM3B     GP7 ┤  └──────┘   ├ GP26  ADC0  VBAT
  R_REN    GPIO OUT  GP8 ┤             ├ GP22  IMU INT1
  R_LEN    GPIO OUT  GP9 ┤             ├ GP21  I2C0_SCL  IMU
                     GND ┤             ├ GP20  I2C0_SDA  IMU
  SBC SCK  SPI1_SCK GP10 ┤             ├ GP19
  SBC MISO SPI1_TX  GP11 ┤     RGB     ├ GP18
  SBC MOSI SPI1_RX  GP12 ┤             ├ GP17
  SBC NSS  SPI1_CSn GP13 ┤             ├ GP16
                     GND ┤             ├ GND
  DATA_RDY GPIO OUT GP14 ┤             ├ GP17
  MODE_SEL GPIO IN  GP15 ┤             ├ GP16
                    3V3 ─┘             └─ GND
                        SWDIO       SWCLK
```

## Pin groups

### Left BTS7960 driver connector — GP2…GP5 (consecutive)

| Pin | Signal  | Direction | Note               |
|-----|---------|-----------|--------------------|
| GP2 | L_RPWM  | OUT PWM   | PWM slice 1, ch A  |
| GP3 | L_LPWM  | OUT PWM   | PWM slice 1, ch B  |
| GP4 | L_REN   | OUT GPIO  | Enable right half  |
| GP5 | L_LEN   | OUT GPIO  | Enable left half   |

### Right BTS7960 driver connector — GP6…GP9 (consecutive)

| Pin | Signal  | Direction | Note               |
|-----|---------|-----------|--------------------|
| GP6 | R_RPWM  | OUT PWM   | PWM slice 3, ch A  |
| GP7 | R_LPWM  | OUT PWM   | PWM slice 3, ch B  |
| GP8 | R_REN   | OUT GPIO  | Enable right half  |
| GP9 | R_LEN   | OUT GPIO  | Enable left half   |

### CRSF receiver — GP0…GP1

| Pin | Signal   | Direction | Note              |
|-----|----------|-----------|-------------------|
| GP0 | CRSF_TX  | OUT UART0 | To receiver RX    |
| GP1 | CRSF_RX  | IN  UART0 | From receiver TX  |

### SBC SPI slave — GP10…GP13

| Pin  | Signal      | Direction | Note                   |
|------|-------------|-----------|------------------------|
| GP10 | SPI1_SCK    | IN        | SPI1 clock             |
| GP11 | SPI1_TX     | OUT       | MISO (RP2040 → SBC)    |
| GP12 | SPI1_RX     | IN        | MOSI (SBC → RP2040)    |
| GP13 | SPI1_CSn    | IN        | Chip select            |
| GP14 | DATA_READY  | OUT GPIO  | Rising edge = new data |
| GP15 | MODE_SEL    | IN  GPIO  | Pull-up; low=companion |

### IMU — GP20…GP22 (right side, consecutive)

| Pin  | Signal    | Direction | Note                   |
|------|-----------|-----------|------------------------|
| GP20 | I2C0_SDA  | I/O       | I2C0 data              |
| GP21 | I2C0_SCL  | OUT       | I2C0 clock             |
| GP22 | IMU_INT1  | IN  GPIO  | Interrupt from IMU     |

### ADC — GP26…GP28

| Pin  | ADC ch | Signal      | Note                              |
|------|--------|-------------|-----------------------------------|
| GP26 | CH0    | VBAT        | Voltage divider (see target_config.h) |
| GP27 | CH1    | Left IS     | BTS7960 left driver IS output     |
| GP28 | CH2    | Right IS    | BTS7960 right driver IS output    |

### Misc

| Pin  | Signal      | Note                      |
|------|-------------|---------------------------|
| GP25 | STATUS_LED  | Onboard LED, active high  |

## PWM carrier frequency

Both PWM slices are configured at **20 kHz** (wrap = 6249 at 125 MHz sys-clock,
integer divider = 1). Both channels of a slice share the same carrier — this
is sufficient for the BTS7960 which only needs one PWM per half-bridge.

## Current sense

Each BTS7960 exposes one IS (current sense) pin for its half-bridge. The
firmware reads CH1 for the left motor and CH2 for the right motor. The R and L
sub-channel aliases in `target.h` both point to the same ADC channel since
there is a single IS pin per chip.

## Build

```
pio run -e rpico_rp2040_standalone
pio run -e rpico_rp2040_companion
```

Flash via USB (hold BOOTSEL, connect USB, release):
```
pio run -e rpico_rp2040_standalone --target upload
```
