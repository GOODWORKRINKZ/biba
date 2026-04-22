# Target: BIBA_F103_REV_A

Custom BiBa driver PCB (prototype revision A) built around an
STM32F103C8T6. Exists mainly as a live example of how to add a new
target without touching any portable code.

## What differs from BLUEPILL_F103C8

| Area             | BLUEPILL_F103C8                 | BIBA_F103_REV_A                     |
| ---------------- | ------------------------------- | ----------------------------------- |
| Enable pins      | PB3 / PB4 / PB5 / PB8 (JTAG-released) | PB0 / PB1 / PB2 / PB9 (JTAG stays live) |
| MODE_SEL         | PB9                             | PB8                                 |
| Status LED       | PC13 (active low)               | PB5 (active high)                   |
| IMU INT1         | PB2                             | PB3                                 |
| Current sense    | pull-down, 8.5 A/V, 0.1 V bias  | op-amp, 10 A/V, 0 V bias            |
| Battery divider  | 1 : 11 (~33 V max)              | 1 : 20 (~66 V max)                  |
| Default I-limit  | 18 A per side                   | 25 A per side                       |
| PA5 on ADC       | 12 V rail tap                   | chassis NTC                         |

## Adding more targets

Copy this directory, rename it to `<YOUR_TARGET>` (`SCREAMING_SNAKE`),
edit `target.h` and `target_config.h`, then register the target with a
single stanza in `firmware/stm32f103/platformio.ini` — see
`targets/README.md` for the template.
