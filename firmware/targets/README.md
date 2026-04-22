# Firmware targets

The BiBa STM32 firmware is organised the same way Betaflight and ELRS
organise theirs: everything portable lives in `src/`, and each supported
**hardware configuration** (pin map, current-sense scale, peripheral
availability) gets its own directory under `targets/<TARGET>/`.

A target is fully described by three files:

```
targets/<TARGET>/
├── target.h            # pin map + BIBA_TARGET_HAS_* feature flags
├── target_config.h     # per-board calibration / limits
└── target.md           # documentation, what differs from other targets
```

The portable code in `src/` only ever includes `biba_board.h` and
`biba_config.h`, which are thin shims that include `target.h` /
`target_config.h` via the `-I targets/<TARGET>` path PlatformIO injects
per-env. No `#ifdef TARGET == …` ladders anywhere in `src/`.

## Supported targets

| Target            | Board                                         |
| ----------------- | --------------------------------------------- |
| `BLUEPILL_F103C8` | Reference: stock STM32F103C8T6 "Blue Pill"    |
| `BIBA_F103_REV_A` | Example custom PCB (prototype revision A)     |

## Build matrix

Every target is combined with every firmware mode
(`standalone` / `companion` / `combined`). Env name is
`<target_lowercase>_<mode>`:

```bash
# default targets
pio run -e bluepill_f103c8_standalone
pio run -e bluepill_f103c8_companion
pio run -e bluepill_f103c8_combined

# custom PCB
pio run -e biba_f103_rev_a_standalone
pio run -e biba_f103_rev_a_companion

# portable host tests (no target needed)
pio test -e native_test
```

The CI workflow `.github/workflows/G-Build-STM32F103.yml` iterates over
all `<target, mode>` pairs and uploads `<target>-<mode>.bin` artefacts.

## Adding a new target

1. **Copy a close neighbour.** Pick the target with a pinout closest to
   your board and copy its directory:

   ```bash
   cp -r firmware/targets/BLUEPILL_F103C8 firmware/targets/<YOUR_TARGET>
   ```

2. **Edit `target.h`.** Set `BIBA_TARGET_NAME`, flip the
   `BIBA_TARGET_HAS_*` flags to match your hardware (e.g. disable IMU if
   the board has no I²C bus), and adjust every `BIBA_PIN_*_PORT/PIN`
   macro. Keep the section comments — the `src/hal/biba_hal.c` code
   looks them up by exactly those macro names.

3. **Edit `target_config.h`.** Override calibration constants (current
   scale, battery divider, per-side I-limit). Only redefine the values
   that actually differ — `include/biba_config.h` supplies defaults
   through `#ifndef` guards.

4. **Register the target in `platformio.ini`.** Add one `[target_*]`
   stanza and one `[env:*_<mode>]` block per firmware mode — copy the
   `biba_f103_rev_a_*` envs in-place and rename. Example for a new
   `MY_BOARD_F103`:

   ```ini
   [target_my_board_f103]
   build_flags = -DBIBA_TARGET_SELECTED=MY_BOARD_F103
   target_include = targets/MY_BOARD_F103

   [env:my_board_f103_standalone]
   extends = env, fw_common, target_my_board_f103, mode_standalone
   board = ${target_my_board_f103.board}
   build_flags =
       ${fw_common.build_flags}
       -I${target_my_board_f103.target_include}
       ${target_my_board_f103.build_flags}
       ${mode_standalone.build_flags}
   ```

5. **Update the CI matrix** in
   `.github/workflows/G-Build-STM32F103.yml` if you want CI coverage,
   and add a row to the table above.

6. **Document the board** in `target.md` with at least the pin diffs
   against an existing target. That keeps the "what's special about
   this board?" knowledge co-located with the code that implements it.

## Portable-code contract

The following header macros are treated as the **target ABI**. Adding,
removing, or renaming any of them is a breaking change; keep them
spelled exactly as they appear in `BLUEPILL_F103C8/target.h`:

- `BIBA_TARGET_NAME`
- `BIBA_TARGET_HAS_BTS7960_2CH`
- `BIBA_TARGET_HAS_CRSF`
- `BIBA_TARGET_HAS_IMU`
- `BIBA_TARGET_HAS_SPI_SLAVE`
- `BIBA_PIN_{LEFT,RIGHT}_{RPWM,LPWM,REN,LEN}_{PORT,PIN}`
- `BIBA_ADC_CHAN_*` and `BIBA_ADC_SCAN_LEN`
- `BIBA_PIN_{CRSF_TX,CRSF_RX,SPI_*,DATA_READY,MODE_SEL,I2C_*,IMU_INT1,STATUS_LED,AUX_TONE}_{PORT,PIN}`
- `BIBA_STATUS_LED_ACTIVE_LOW`

If your board fundamentally can't provide one of the listed pins
(e.g. no SPI slave, no IMU), set the matching `BIBA_TARGET_HAS_*` flag
to 0 and leave the pin macros undefined; the HAL layer already guards
the affected init code with the feature flag.
