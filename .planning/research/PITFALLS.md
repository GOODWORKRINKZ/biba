---
doc: PITFALLS-RESEARCH
last_mapped: 2026-05-14
---

# Pitfalls Research: RP2040 Robot Firmware Port

Sources: firmware/src/ code inspection, Python reference implementation
(biba-controller/), PROJECT.md, CONCERNS.md, plus embedded systems
community patterns. Confidence levels noted per section.

---

## Critical Pitfalls (Can Cause Hardware Damage or Loss of Control)

### Motor Pins Float During MCU Boot / Reflash
- **What goes wrong:** BTS7960 L_EN/R_EN are active-high. During RP2040
  power-on or USB reflash, GPIO pins are high-Z (pulled up by internal
  pull-ups or left floating). If a pull-up drives EN high before firmware
  configures them as outputs, the driver is enabled with an undefined PWM
  signal — motor can spin unexpectedly.
- **Warning signs:** Robot jerks on power-on; motors spin briefly during
  firmware upload.
- **Prevention:** HAL must drive L_EN/R_EN LOW as the very first GPIO
  operation, before UART/I2C/SPI init. Add an explicit `bts7960_set_enabled(false)`
  at the top of `main_rp2040.cpp` before any other init. Use hardware pull-down
  resistors (4.7kΩ) on EN pins as a second line of defence.
- **Phase:** RP2040-PORT-02 (BTS7960 PWM phase)

### Inrush Current Spike on BTS7960 Enable
- **What goes wrong:** Calling `bts7960_set_enabled(true)` while PWM duty
  is non-zero causes an inrush spike through the motor winding. The BTS7960
  internal current sense (IS pin) can saturate or trip the IC's overcurrent
  latch. This also stresses the power supply and can reset the MCU via
  a brownout if the battery wiring has high impedance.
- **Warning signs:** Motor stutters on arm; MCU randomly reboots at arm time.
- **Prevention:** Always set PWM duty = 0 before enabling. Enforce the sequence
  in `biba_bts7960_set_enabled`: clear PWM → assert enable. The current
  `bts7960.c` clears PWM only when *disabling* — the enable path needs the
  same guard.
- **Phase:** RP2040-PORT-02

### Failsafe UART ISR Enabled Before `failsafe_init`
- **What goes wrong:** If UART NVIC is enabled before `biba_failsafe_init()`
  is called, the ISR fires and may call `failsafe_mark_fresh` on an
  uninitialized struct. The `primed` flag stays false but `last_ok_ms`
  gets a valid timestamp, causing `failsafe_tick` to believe the link is good
  before the app is ready.
- **Warning signs:** Robot is controllable for ~500 ms after boot even with
  no transmitter present.
- **Prevention:** Complete all `_init()` calls before enabling UART interrupts.
  In `main_rp2040.cpp` the order must be: init structs → init HAL → enable ISR.
- **Phase:** RP2040-PORT-06 (Failsafe)

### Soft Failsafe Timeout Not Respected When I2C Blocks
- **What goes wrong:** The Python reference had this exact bug (documented in
  CONCERNS.md). The C port reproduces it if IMU or ADS1115 I2C calls are
  blocking and called from the same loop that ticks the failsafe. A 860 µs
  ADS1115 conversion at 860 SPS, plus BMI160 burst read, can easily exceed
  the 500 ms failsafe window if multiple reads are chained with retries.
- **Warning signs:** Failsafe fires late during bench I2C stress tests.
- **Prevention:** Run `biba_failsafe_tick()` from a hardware timer ISR (RP2040
  has 4 hardware alarms). The main loop only calls `mark_fresh` when a valid
  CRSF frame is received. Timer ISR independently trips the motor disable.
  Alternatively use the RP2040's second core (core1) exclusively for UART/CRSF
  with the failsafe, keeping core0 for slow I2C work.
- **Phase:** RP2040-PORT-06

### uint32_t Timestamp Rollover in Failsafe (Latent Bug)
- **What goes wrong:** `biba_failsafe_tick` computes `delta = now_ms - last_ok_ms`.
  This works correctly for rollover *only if both values are the same unsigned
  type and subtraction wraps*. If `now_ms` is ever cast to int32_t anywhere in
  the call chain (e.g., passed through a log helper), the subtraction becomes
  signed and produces a large negative delta ~every 24.8 days. Not a field
  issue for Phase 1 but bites during long soak tests.
- **Warning signs:** Failsafe fires spuriously after exactly 2^31 ms of uptime.
- **Prevention:** Keep all time values `uint32_t`. Add a static assert:
  `_Static_assert(sizeof(now_ms) == 4, "timestamp must be uint32_t")`.
- **Phase:** RP2040-PORT-06

---

## Common Python→C Porting Mistakes

### `volatile` Missing on ISR-Shared Variables
- **What goes wrong:** Variables written in a UART ISR and read in the main
  loop must be `volatile`. Without it, the compiler legally caches the value
  in a register and the main loop never sees new data. Python asyncio had no
  such concept.
- **Warning signs:** Works at `-O0`, breaks at `-O2`; intermittent "no frames
  received" on bench with transmitter clearly linked.
- **Prevention:** All ring-buffer head/tail indices and the `crsf_frame_ready`
  flag must be `volatile`. Prefer `volatile uint8_t` flags or a proper ISR
  queue with a critical-section wrapper (`__disable_irq`/`__enable_irq`).
- **Phase:** RP2040-PORT-01 (CRSF)

### Integer Overflow in Channel Scaling
- **What goes wrong:** CRSF channels are 11-bit values (172–1811). Python ints
  are arbitrary precision; C `int16_t` overflows silently when you scale
  or apply trim. Example: `int16_t val = raw - 992; val *= 1000; val /= 819;`
  — the intermediate `val * 1000` overflows int16_t at raw > 820.
- **Warning signs:** One motor direction works fine; the other clips at maximum
  or goes to minimum.
- **Prevention:** Use `int32_t` for intermediate channel arithmetic. Scale,
  then clamp, then store into the narrower type. Add unit tests on boundary
  values 172 and 1811.
- **Phase:** RP2040-PORT-01, RP2040-PORT-05 (trim)

### Float Literal Without `f` Suffix
- **What goes wrong:** `float x = 1.0 / 819.0;` — both literals are `double`,
  the division is `double`, then truncated to `float`. On ARM Cortex-M0+
  (RP2040) there is no hardware double FPU; double arithmetic uses soft-float
  and is ~40× slower. The Python port used floats throughout; naive C
  translation copies the values as double literals.
- **Warning signs:** Control loop is slower than expected; profiling shows
  `__aeabi_ddiv` calls in hot path.
- **Prevention:** Append `f` to all float literals in control code:
  `1.0f / 819.0f`. Enable `-Wdouble-promotion` in PlatformIO build flags
  to catch these at compile time.
- **Phase:** All phases using float math

### Stack Overflow from Local Buffers
- **What goes wrong:** RP2040 core0 default stack is 2 KB. A single
  `uint8_t buf[512]` in a function called from within several nested
  calls can silently corrupt adjacent stack frames. Python had no stack
  limit for local variables.
- **Warning signs:** Intermittent crashes with no obvious cause; hardfault
  at a seemingly unrelated instruction.
- **Prevention:** Declare large buffers as `static` (moves them to BSS/data
  segment). Enable stack-canary support in the SDK (`pico_enable_stdio_usb`
  debug builds). Keep local arrays small (< 64 bytes) inside ISR handlers.
- **Phase:** All phases

### Calibration Constants Silently Truncated
- **What goes wrong:** Porting Python calibration constants like
  `AMPS_PER_VOLT = 18.3` to C as `int` or `uint8_t` fields truncates to 18.
  The current `current_sense.c` uses `float amps_per_volt` correctly, but
  if `biba_config.h` defines these as integer macros, the formula silently
  produces integer arithmetic.
- **Warning signs:** Current readings are slightly off in one direction; unit
  tests pass because they use the same integer constants.
- **Prevention:** Audit every numeric constant in `biba_config.h`. Mark
  float constants with `f` suffix. Add a compile-time check:
  `_Static_assert(BIBA_IS_AMPS_PER_VOLT > 1.0f, "must be float")` — note
  this only works if the macro expands to a float literal.
- **Phase:** RP2040-PORT-04 (current sense)

---

## CRSF/ELRS Specific Pitfalls

### UART Baud Rate Not Exactly 420000
- **What goes wrong:** ELRS uses 420000 baud. The RP2040 UART clock divider
  is `sys_clk / (16 * baud)`. At 125 MHz sys_clk, the ideal divisor is
  ~18.601. The hardware rounds to the nearest integer or fractional value;
  the actual rate may be 420168 baud (~0.04% error). ELRS's receiver-side
  UART tolerance is ±1.5%, so this is fine — *but only at 125 MHz*.
  If `set_sys_clock_khz()` changes the system clock, the baud rate silently
  changes too unless re-initialized after the clock change.
- **Warning signs:** Sporadic CRC errors at a fixed pattern, e.g., every
  time a certain peripheral is active (SPI clock might be changing PLL).
- **Prevention:** Call `uart_init()` *after* the final `set_sys_clock_khz()`.
  Log the actual measured baud from `uart_get_baudrate()` at startup.
- **Phase:** RP2040-PORT-01

### `memmove`-Based Ring Buffer Is O(N) at 420 kbaud
- **What goes wrong:** `biba_crsf_pop_frame` calls `memmove` to compact the
  buffer after every consumed frame. At 420 kbaud with 26-byte RC frames
  arriving every 4 ms, this is ~6500 memmove calls/second, each shifting up
  to `CRSF_MAX_FRAME_SIZE` bytes. At 125 MHz this is cheap in isolation, but
  it runs in the main loop while holding the buffer lock — increasing latency
  for every other subsystem tick.
- **Warning signs:** Control loop jitter > 1 ms at high-frequency frame rates.
- **Prevention:** Replace with a true circular (ring) buffer with head/tail
  indices. The current API (`pop_frame` modifying `buffer_len`) makes this a
  contained change inside `crsf.c`.
- **Phase:** RP2040-PORT-01

### Frame Boundary Lost After Noise Byte
- **What goes wrong:** The current `biba_crsf_pop_frame` discards the sync
  byte on a bad CRC and retries from the next byte. This is correct for single
  noise bytes but fails if a valid frame arrives immediately after a truncated
  frame — the `length` field of the bad frame may be large enough to skip over
  the start of the next valid frame.
- **Warning signs:** After a brief RF interruption, no frames are decoded for
  several hundred milliseconds despite signal recovery; failsafe fires late.
- **Prevention:** After a bad CRC or bad length, scan forward for the *next*
  `CRSF_SYNC_BYTE` rather than advancing by one byte. Add a test case: inject
  `[0xC8, 0xFF, 0xC8, valid_frame...]` and assert the valid frame is decoded.
- **Phase:** RP2040-PORT-01

### ELRS Link Quality ≠ RSSI — Treating Them the Same
- **What goes wrong:** The Python telemetry code logs both LQ and RSSI. On
  ELRS, LQ (0–100 %) is the more actionable metric: LQ < 70 means packets
  are being lost; LQ < 50 means pre-failsafe conditions. If the C port only
  exposes the RSSI field for range alarms, the operator gets no warning until
  full link loss.
- **Warning signs:** Robot drops into failsafe without any prior telemetry
  warning.
- **Prevention:** Expose LQ in the telemetry struct alongside RSSI. Set a
  pre-failsafe audible alarm at LQ < 60 (buzzer).
- **Phase:** RP2040-PORT-06

### CRSF Channels Bit-Unpacking Endianness Error
- **What goes wrong:** CRSF RC_CHANNELS_PACKED packs 16 × 11-bit channels
  LSB-first across 22 bytes. The correct shift for channel N is:
  `bit_offset = N * 11; byte = bit_offset / 8; shift = bit_offset % 8;
  val = (buf[byte] | (buf[byte+1] << 8)) >> shift & 0x7FF`.
  Off-by-one on the shift or treating it as big-endian gives channels that
  appear to work (values in range) but are offset by 1 channel for every
  other channel.
- **Warning signs:** Throttle controls steering; steering controls throttle;
  channels 1 and 2 appear swapped.
- **Prevention:** Port the Python `_decode_channels` test cases directly to
  C unit tests. Test against the known raw bytes in `tests/test_crsf.py`.
- **Phase:** RP2040-PORT-01

---

## IMU Integration Pitfalls

### Gyro Integration With Variable `dt` Produces Drift
- **What goes wrong:** Heading hold integrates `angle += gyro_z * dt`. If
  `dt` is computed from wall time but the loop is sometimes blocked by I2C,
  `dt` spikes. The Python code measured real elapsed time; a C port that uses
  a fixed `dt = 1/loop_hz` accumulates error whenever the loop misses its
  deadline.
- **Warning signs:** Robot drifts in a slow circle after any operation that
  causes loop latency (e.g., first I2C burst after power-on).
- **Prevention:** Always compute `dt` from the actual timestamp difference
  (`time_us_32()` before and after the full loop body). Cap `dt` at 2× the
  nominal period to prevent integration spikes during startup.
- **Phase:** RP2040-PORT-03

### Missing Gyro Zero-Offset Calibration at Startup
- **What goes wrong:** BMI160 and LSM6DS3 have a static gyro bias (typically
  ±1–3 °/s). The Python code averaged N samples at startup to compute the
  offset. If the C port uses raw readings without this calibration, the
  integrated heading drifts at a constant rate from the moment of power-on.
- **Warning signs:** Robot slowly turns in one direction with no stick input;
  drift is repeatable and roughly constant.
- **Prevention:** On boot, collect 100 gyro samples with the robot stationary
  (detect stationary by accelerometer RMS < threshold). Subtract the mean as
  `gyro_offset`. Store in RAM; do not persist across boots (temperature
  changes offset).
- **Phase:** RP2040-PORT-03

### IMU Axis Mapping Not Replicated from Python
- **What goes wrong:** The Python `imu_factory` applied axis sign corrections
  for the physical mounting orientation of the IMU board. If the C port reads
  the raw Z-axis gyro without the same sign flip, the heading hold will fight
  the operator rather than assist.
- **Warning signs:** Heading hold makes robot spin; increasing Kp makes it
  worse.
- **Prevention:** Read the axis remapping in `biba-controller/imu/` and
  replicate in `firmware/src/drivers/imu.c`. Add a bench test: apply a known
  CW rotation, assert heading increases (or decreases) in the expected direction.
- **Phase:** RP2040-PORT-03

### BMI160 vs LSM6DS3 Different ODR/Filter Defaults
- **What goes wrong:** The two supported IMUs have different power-on default
  output data rates and low-pass filter settings. BMI160 defaults to 100 Hz
  ODR; LSM6DS3 defaults to power-down. If the C HAL only configures one chip's
  registers, the other will either be completely silent or noisier than
  expected.
- **Warning signs:** Works on one hardware variant; gyro data is stuck at 0
  or maximum on the other.
- **Prevention:** The `imu.c` must implement chip detection (via WHO_AM_I
  register) and apply chip-specific initialization sequences. Match the ODR and
  filter bandwidth used in the Python version (250 Hz with 100 Hz LPF was
  typical).
- **Phase:** RP2040-PORT-03

### SPI vs I2C IMU: CS Pin Must Be Driven Before Any SPI Transaction
- **What goes wrong:** If the IMU chip select (CS) pin is not driven low before
  the first SPI clock, the IMU ignores the transaction but the SPI bus stalls
  waiting for MISO to settle. Subsequent reads return stale data or all-zeros.
- **Warning signs:** First 1–3 register reads after boot return 0x00 or 0xFF;
  WHO_AM_I check fails; IMU "works" after a few seconds when the bus recovers.
- **Prevention:** Drive CS high in HAL init before enabling SPI peripheral.
  Toggle CS low/high around every transaction, not just "enable once".
- **Phase:** RP2040-PORT-03

---

## Thermal / Power Pitfalls

### No Software Thermal Throttle = Hardware Damage Repeats
- **What goes wrong:** The BTS7960 overheated at 20–30 min of driving
  (confirmed in field test 2026-05-09). Fixing the heatsink (THERMAL-01)
  buys margin; without THERMAL-02 (software throttle), the same failure mode
  recurs in longer sessions or hot weather. The current `bts7960.c` has no
  current-based power reduction.
- **Warning signs:** Motor driver gets progressively hotter; no audible alarm;
  driver eventually enters thermal shutdown and enables both outputs simultaneously
  (dangerous: can brake hard or spin uncontrolled).
- **Prevention:** Implement THERMAL-02: sample the current sense every 100 ms,
  maintain a rolling average, and reduce `max_duty` linearly when average current
  exceeds a threshold. Add a hard disable at a higher threshold (BTS7960 rated
  43A peak, 27A continuous). Use the buzzer for a thermal warning alarm.
- **Phase:** THERMAL-02

### Current Sense IS Pin Saturates at High Load
- **What goes wrong:** The BTS7960's IS pin outputs a current proportional to
  motor current via an internal mirror (ratio ~8500:1 typical). The sense
  resistor converts this to a voltage. At high currents the IS pin saturates;
  the ADC reading clips at 3.3V (RP2040 ADC max) and `amps_per_volt` scaling
  reports a value lower than the actual current. The thermal throttle then
  under-estimates load.
- **Warning signs:** Measured current never exceeds ~15 A even at full stall;
  driver overheats at "moderate" measured current.
- **Prevention:** Know the IS pin saturation current for the specific BTS7960
  variant. Add a saturation flag: if ADC reads > 90% of full scale, set
  `current.valid = false` and apply maximum thermal penalty (treat as overcurrent).
  The current `current_sense.c` does not set `valid = false` for saturation.
- **Phase:** RP2040-PORT-04, THERMAL-02

### Single ADC Sample per Loop Has ~±50 mV Noise on RP2040
- **What goes wrong:** The RP2040 internal ADC has significant noise (~±2 LSB
  at 12-bit, ~±1.2 mV at 3.3V Vref) due to the ADC sharing the 3.3V supply
  with digital logic. Motor PWM switching couples noise into the supply.
  Single-sample current readings can have 50–100 mV noise spikes that translate
  to ±1–2 A false current spikes, triggering spurious throttle-back.
- **Warning signs:** Current reading jitters ±2 A even at steady throttle;
  false thermal throttle activations when motor transitions direction.
- **Prevention:** Oversample: average 4–16 ADC samples per measurement (RP2040
  SDK supports hardware averaging via FIFO). Add a software low-pass filter
  with τ = 100–200 ms for the thermal throttle calculation (fast spikes should
  not trigger thermal action). The existing `current_sense.c` does no averaging.
- **Phase:** RP2040-PORT-04

### Power Supply Voltage Divider Not Calibrated for RP2040 3.3V ADC
- **What goes wrong:** The Python version used ADS1115 with its own 4.096V
  reference to measure battery voltage. The RP2040 internal ADC reference is
  the 3.3V supply, which varies with load. A voltage divider designed for
  ADS1115 may push battery voltage (up to 25.2V for 6S) out of the RP2040
  ADC's 0–3.3V range, or the divider ratio may be wrong for the new reference
  voltage.
- **Warning signs:** Battery voltage reads 20% high or low; low-voltage cutoff
  fires at wrong level.
- **Prevention:** Recalculate the divider for 0–3.3V at 6S full charge (25.2V).
  Use a precision 3.3V reference (e.g., LM4040) separate from the supply rail
  for the ADC Vref if accurate voltage measurement is needed.
- **Phase:** RP2040-PORT-04

---

## Testing Pitfalls (Field vs Unit Test)

### Existing pytest Suite Does Not Cover C Firmware
- **What goes wrong:** The 40+ Python tests in `tests/` validate the Python
  reference implementation. None run against the RP2040 firmware. A passing
  pytest run gives false confidence that the RP2040 port is correct.
- **Warning signs:** CI passes; robot behaves unexpectedly in field.
- **Prevention:** Create a `firmware/test/` suite (separate from the existing
  `test/` in firmware which appears to be PlatformIO native tests). For logic
  that is testable on host (CRSF parsing, failsafe state machine, channel
  scaling), use a CMake host-build target that links the driver .c files with
  a stub HAL. Cross-verify boundary values against `tests/test_crsf.py`.
- **Phase:** RP2040-PORT-01 through PORT-06

### Bench Tests Miss PWM-Induced ADC Noise
- **What goes wrong:** Current sense tests on the bench with a bench power
  supply read correctly. In the field, the motor PWM switching injects noise
  into the 3.3V rail and ADC. The bench test environment does not reproduce
  this.
- **Warning signs:** Current readings are clean on bench; erratic in field.
- **Prevention:** Run a dedicated noise characterization test: full PWM duty
  cycle into a motor (or motor equivalent resistor), sample ADC at 1 kHz for
  1 second, plot the histogram. Set software filter coefficients from this data,
  not from bench measurements.
- **Phase:** RP2040-PORT-04

### Failsafe Tested Only With Clean Link Loss
- **What goes wrong:** The Python failsafe was tested by powering off the
  transmitter. Real-world failsafe events include: CRC errors without full
  frame loss, partial UART overrun (some bytes received, not a full frame),
  and ELRS mid-frame corruption. The C `pop_frame` handles these differently
  from a clean timeout.
- **Warning signs:** Failsafe works when transmitter is off; does not trigger
  when RF is degraded (LQ 20–40 %).
- **Prevention:** Inject test cases: buffer containing a partial frame followed
  by silence; buffer with valid sync byte but invalid length; buffer with good
  frame but bad CRC. Assert that none of these cause `mark_fresh` to be called.
- **Phase:** RP2040-PORT-06

### PID Gains Tuned on Pi Need Re-Tuning on RP2040
- **What goes wrong:** PID gains from the Python web-UI tuning session were
  tuned against the Pi's ~50 Hz control loop with asyncio scheduling jitter.
  The RP2040 runs a tighter, deterministic loop at a potentially different rate.
  The same Kp/Ki/Kd will produce different behaviour — possibly oscillation or
  sluggish response — on the RP2040.
- **Warning signs:** Heading hold oscillates or is noticeably more/less
  aggressive than on Pi reference.
- **Prevention:** Treat Pi PID gains as a starting point only. Plan a PID
  re-tuning session specifically for the RP2040 firmware before declaring the
  port complete. The RP2040 port should log the actual control loop rate so
  gains can be normalized.
- **Phase:** RP2040-PORT-03

### Field Test Before Thermal Fix Masks Real Performance
- **What goes wrong:** If a field test is conducted with the heatsink fix
  (THERMAL-01) but without software thermal protection (THERMAL-02), the
  session may be declared a success until a longer or hotter run occurs.
  A 15-minute drive in 15°C may pass; a 25-minute drive in 30°C may fail.
- **Warning signs:** First field tests always pass; failure only on second or
  third longer session.
- **Prevention:** Require THERMAL-02 to be implemented and tested before any
  field test declared as "thermal issue resolved". Use a thermal camera or
  NTC thermistor on the driver heatsink during the first post-fix field test.
- **Phase:** THERMAL-01, THERMAL-02
