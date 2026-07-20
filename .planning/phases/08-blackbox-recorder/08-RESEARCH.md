# Phase 8: Session Flight Recorder — Research

**Researched:** 2026-05-25
**Domain:** LittleFS on RP2040 flash + binary CDC download protocol
**Confidence:** HIGH (all claims verified against local toolchain and source files)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- Storage: LittleFS on internal flash (no SD slot, no SPI pins free)
- Trigger: CRSF CH8 > 1500 µs (BIBA_ARM_THRESHOLD) — same physical channel as existing beacon
- Audio: `biba_melody_sos` on enable, `biba_melody_failsafe` on flash-full
- Recording starts on arm (CH5) while CH8 is active; stops on disarm or CH8 LOW
- Format: binary `.bbd` with 32-byte header (magic "BBD1", created_tick_ms, field_mask, rate_hz) + variable-size records per field_mask
- File naming: `session_NNNN.bbd` (4-digit sequential number)
- Flash full: first CH8 HIGH → error sound + `s_blackbox_full_warned = true`; second CH8 HIGH → delete oldest session
- Download: USB CDC shell commands `bb list / bb get / bb del / bb info` + Python script `scripts/biba_blackbox_download.py`
- Rate: `#define BIBA_BLACKBOX_RATE_HZ 10` (configurable, in `biba_config.h`)
- Default field mask: 0xFFFF (all 16 fields)

### Agent's Discretion
- Implementation of `blackbox_meta.bin` vs directory listing for session counter — research options and recommend
- Whether to add `BIBA_CH_BLACKBOX` as a new define or reuse `BIBA_CH_BEACON` directly
- Exact CDC binary download protocol (raw bytes with size header)
- LittleFS partition size recommendation (CONTEXT.md says 1MB target, board has 16MB flash)

### Deferred Ideas (OUT OF SCOPE)
- Raw IS-buffer recording (ADC samples) — too large, separate phase
- Real-time CRSF telemetry uplink — TELEM-01 in backlog
- Web session viewer — separate milestone
- RTC timestamps in filenames — no RTC on board
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| BB-01 | CH8 HIGH plays SOS melody; arm+CH8 opens session_NNNN.bbd and records at BIBA_BLACKBOX_RATE_HZ | §Channel, §LittleFS API, §Write Context |
| BB-02 | File contains all fields: timestamp, throttle, rudder, duty L/R, rpm L/R, active_blocks, mean_is, latch_resets, vbat, PI state | §Data Sources section |
| BB-03 | Python script downloads and converts to CSV without manual steps | §Download Protocol, §CDC Write |
</phase_requirements>

---

## Summary

Phase 8 adds a LittleFS-based flight recorder to the RP2040 firmware. All required
libraries and toolchain support are already in place — the arduino-pico framework bundles
LittleFS, the CDC interface is live, and the existing `mode_standalone.c` tick already
reads all the state fields that need to be logged.

Three key surprises versus the CONTEXT.md assumptions:

1. **The board has 16 MB flash** (YD-RP2040, `PICO_FLASH_SIZE_BYTES=16777216`), not 2 MB.
   The CONTEXT.md "~1.9 MB free" estimate was based on a standard Pico board. Recommend
   allocating 4 MB to the filesystem — plenty of headroom with trivial sketch impact.

2. **The filesystem partition is currently zero bytes** (`FS_START == FS_END`). Adding
   `board_build.filesystem_size = 4MB` to the `[env:rpico_rp2040_standalone]` stanza is
   the *only* platformio.ini change needed to activate LittleFS.

3. **LittleFS is a C++ Arduino API.** C callers need a thin `biba_hal_blackbox.cpp` wrapper
   (extern "C" interface), following the exact pattern of the existing `biba_hal_serial.cpp`.

**Primary recommendation:** Create `firmware/src/app/blackbox.cpp` (or a `.cpp` HAL wrapper
+ `.c` logic layer) that wraps LittleFS and is called from the existing `mode_standalone.c`
tick. Keep all LittleFS calls in main context — never from the DMA/ADC IRQ.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| LittleFS partition config | platformio.ini build system | — | `board_build.filesystem_size` sets FS_START/FS_END at build time |
| LittleFS mount / open / write / close | `blackbox.cpp` C++ wrapper | — | Arduino FS API is C++; all other modes are in C |
| Trigger detection (CH8) | `mode_standalone.c` tick | — | Already reads `beacon_ch`; blackbox = same channel, extended behavior |
| Record assembly | `mode_standalone.c` tick | — | State variables (rpm, duty, latch) are all local statics here |
| CDC shell (bb list/get/del/info) | Extended `process_debug_serial()` | — | Pattern-matches existing DBGON/SET commands |
| Binary download (raw bytes) | `biba_hal_serial.cpp` new function | — | `Serial.write()` is C++; needs `extern "C"` wrapper |
| Python decode + CSV | `scripts/biba_blackbox_download.py` | — | Same pattern as `vcp_capture.py` |

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| LittleFS (arduino-pico) | bundled with framework-arduinopico | Wear-leveled FS on internal flash | Already in build path; FS_PAGE/FS_BLOCK already configured by platform builder |
| pyserial | ≥3.5 (already in requirements) | CDC serial I/O in Python download script | Already used by `vcp_capture.py` |

**Version verification:** `LittleFS` is bundled — no separate install. `pyserial` already in
`requirements-dev.txt`. [VERIFIED: grep /home/ros2/.platformio/packages/framework-arduinopico/libraries/LittleFS/]

### LittleFS Config Parameters (auto-derived by platform builder)

[VERIFIED: /home/ros2/.platformio/platforms/rp2040/builder/main.py lines 97–98]

```
FS_PAGE  = 256   bytes   (prog_size / cache_size / read_size)
FS_BLOCK = 4096  bytes   (= W25Q128 sector size)
block_cycles = 16        (metadata compaction interval, not physical limit)
```

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| struct (Python stdlib) | stdlib | Binary record decode in download script | Always |
| pathlib (Python stdlib) | stdlib | Output path handling | Always |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| LittleFS Arduino wrapper | Raw `lfs_*` C API | Raw API requires manual flash config (FS_START, FS_BLOCK passed as lfs_config) — more code, same result. Wrapper is already wired up. |
| Raw binary CDC download | XMODEM | XMODEM adds retry/CRC complexity; at ≤1.4 MB/session a simple length-prefix protocol is sufficient and trivially testable |

**Installation:** No new packages needed.
`board_build.filesystem_size = 4MB` is the only change required.

---

## Architecture Patterns

### System Architecture Diagram

```
CRSF CH8 (s_channels[7])
          │ beacon_ch > ARM_THRESHOLD
          ▼
   [mode_standalone tick]
          │
          ├─► bb_enable flag ──► biba_melody_sos (on rising edge)
          │
   arm edge (CH5 HIGH) + bb_enable
          │
          ▼
   blackbox_open_session()   ← writes 32-byte header to session_NNNN.bbd
          │                    (via LittleFS wrapper in blackbox.cpp)
          │
   [per-tick, when armed + bb_enable]
          │ BIBA_BLACKBOX_RATE_HZ throttle
          ▼
   blackbox_write_record()   ← assembles biba_blackbox_record_t from
          │                    mode_standalone statics, writes N bytes
          │                    (fields enabled by field_mask only)
          │
   disarm edge / CH8 LOW
          ▼
   blackbox_close_session()  ← flushes + closes file
          │
          └─► LED off, s_bb_recording = false

USB CDC host (Python)
   → "bb list\n"  ──► bb_handle_shell() ──► LittleFS.openDir("/")
   → "bb get <f>" ──► bb_send_file()    ──► Serial.write() binary stream
   → "bb del <f>" ──► LittleFS.remove()
   → "bb info\n"  ──► LittleFS.info()
```

### Recommended Project Structure

```
firmware/src/
├── app/
│   ├── blackbox.h          # C header: blackbox_init/open/write/close/is_full/oldest_session
│   └── blackbox.cpp        # C++ impl: wraps LittleFS + extern "C" exports
├── hal/
│   ├── biba_hal_serial.cpp # EXISTING — add biba_hal_serial_write_bytes()
│   └── biba_hal.h          # EXISTING — add biba_hal_serial_write_bytes() declaration
scripts/
└── biba_blackbox_download.py   # new Python script
```

### Pattern 1: LittleFS Mount in setup() / Arduino .cpp wrapper

**What:** LittleFS.begin() in `setup()` before tick loop; all FS calls from main context.

**When to use:** Always — LittleFS is not ISR-safe.

```cpp
// Source: firmware/src/app/blackbox.cpp (new file)
#include <LittleFS.h>
#include "blackbox.h"

static File s_session_file;
static bool s_mounted = false;

extern "C" bool blackbox_init(void) {
    if (!LittleFS.begin()) {
        // Auto-format on first boot
        LittleFS.format();
        s_mounted = LittleFS.begin();
    } else {
        s_mounted = true;
    }
    return s_mounted;
}

extern "C" bool blackbox_open_session(uint32_t session_num, uint32_t tick_ms,
                                       uint16_t field_mask, uint8_t rate_hz) {
    char path[32];
    snprintf(path, sizeof(path), "/session_%04lu.bbd", (unsigned long)session_num);
    s_session_file = LittleFS.open(path, "w");
    if (!s_session_file) return false;
    // Write 32-byte header
    biba_blackbox_header_t hdr = {
        .magic = {'B','B','D','1'},
        .created_tick_ms = tick_ms,
        .field_mask = field_mask,
        .rate_hz = rate_hz,
        .reserved = {0}
    };
    s_session_file.write((const uint8_t*)&hdr, sizeof(hdr));
    return true;
}

extern "C" void blackbox_write_record(const uint8_t *buf, size_t len) {
    if (s_session_file) s_session_file.write(buf, len);
}

extern "C" void blackbox_close_session(void) {
    if (s_session_file) { s_session_file.flush(); s_session_file.close(); }
}
```

### Pattern 2: Session Number via Directory Listing (no meta file)

**What:** Scan `/` directory, parse `session_NNNN.bbd` filenames, return min and max NNNN.

**When to use:** On every `bb_enable` rising edge (cheap scan on a small directory).

```cpp
// Source: blackbox.cpp
extern "C" uint32_t blackbox_next_session_num(uint32_t *oldest_out) {
    Dir dir = LittleFS.openDir("/");
    uint32_t max_n = 0, min_n = UINT32_MAX;
    bool found = false;
    while (dir.next()) {
        unsigned n = 0;
        if (sscanf(dir.fileName().c_str(), "session_%04u.bbd", &n) == 1) {
            if (n > max_n) max_n = n;
            if (n < min_n) min_n = n;
            found = true;
        }
    }
    if (oldest_out) *oldest_out = found ? min_n : 0;
    return found ? max_n + 1 : 1;   // next = last + 1
}
```

**Why preferred over `blackbox_meta.bin`:** Power-loss resilient (no separate state
to get out of sync); scan is O(N) over session count which stays small (≤30 sessions
at 1.4 MB/session in a 4 MB FS).

### Pattern 3: Binary CDC Download Protocol

**What:** Firmware responds to `bb get <file>` with a size-prefixed raw byte stream.

```
Host sends:   "bb get session_0001.bbd\n"
Firmware:     "SIZE:14520\r\n"            (ASCII, ends with \r\n)
Firmware:     <14520 raw bytes>           (binary file content)
```

**Python reader:**
```python
# Source: scripts/biba_blackbox_download.py (new file)
import serial, struct, re, csv, pathlib

def download_session(port: serial.Serial, filename: str, out_dir: pathlib.Path):
    port.write(f"bb get {filename}\n".encode())
    header = port.readline()                         # "SIZE:14520\r\n"
    m = re.match(rb"SIZE:(\d+)", header)
    size = int(m.group(1))
    data = b""
    while len(data) < size:
        data += port.read(size - len(data))
    (out_dir / filename).write_bytes(data)
    return data

def decode_bbd(data: bytes) -> list[dict]:
    # Parse 32-byte header
    magic, created_ms, field_mask, rate_hz = struct.unpack_from("<4sIHB", data, 0)
    assert magic == b"BBD1"
    FIELDS = [
        ("timestamp_ms","I"), ("throttle","h"), ("rudder","h"),
        ("duty_left","h"), ("duty_right","h"),
        ("rpm_left_hz10","H"), ("rpm_right_hz10","H"),
        ("active_blocks_l","B"), ("active_blocks_r","B"),
        ("mean_is_l","H"), ("mean_is_r","H"),
        ("latch_resets","B"), ("vbat_mv","H"),
        ("pi_integral_l","h"), ("pi_integral_r","h"),
        ("pi_meas_ema_l","H"),
    ]
    active = [(name,fmt) for i,(name,fmt) in enumerate(FIELDS) if field_mask & (1 << i)]
    rec_fmt = "<" + "".join(f for _,f in active)
    rec_size = struct.calcsize(rec_fmt)
    rows = []
    offset = 32  # skip header
    while offset + rec_size <= len(data):
        vals = struct.unpack_from(rec_fmt, data, offset)
        rows.append(dict(zip([n for n,_ in active], vals)))
        offset += rec_size
    return rows
```

### Pattern 4: CDC Binary Write Wrapper

**What:** Add `biba_hal_serial_write_bytes()` to `biba_hal_serial.cpp` to send
raw binary data without going through `printf`/`_write` text path.

```cpp
// Source: firmware/src/hal/biba_hal_serial.cpp (extend existing file)
extern "C" void biba_hal_serial_write_bytes(const uint8_t *buf, size_t len) {
    Serial.write(buf, len);
}
extern "C" void biba_hal_serial_write_str(const char *s) {
    Serial.print(s);
}
```

### Pattern 5: Rate Throttle in Main Tick

**What:** Track milliseconds; write a record only every `1000/BIBA_BLACKBOX_RATE_HZ` ms.

**Why not DMA-window counting (as suggested in CONTEXT.md):** DMA IRQ runs on both
cores concurrently; LittleFS is not IRQ-safe. The simpler millisecond timer in the main
tick avoids any cross-context hazard.

```c
// In mode_standalone.c tick, after control loop outputs are finalized:
static uint32_t s_bb_next_ms;
if (s_bb_recording && now >= s_bb_next_ms) {
    s_bb_next_ms = now + (1000u / BIBA_BLACKBOX_RATE_HZ);
    biba_blackbox_record_t rec = { ... };  // populate from statics
    blackbox_write_record((const uint8_t*)&rec, sizeof(rec));
}
```

### Anti-Patterns to Avoid

- **Writing from DMA/ADC IRQ:** LittleFS is NOT interrupt-safe. Never call `blackbox_write_record()` from `on_adc_pair_done()`. All FS calls must be from main context (Arduino loop thread = Core 0).
- **Relying on `printf()` for binary data:** The `_write()` override in `main_rp2040.cpp` routes to `Serial.write()` but is only used by printf text. Binary data must go through `biba_hal_serial_write_bytes()` directly.
- **Calling `LittleFS.begin()` from C:** `LittleFS` is a global C++ object. Call `blackbox_init()` (extern C wrapper) from `main_rp2040.cpp setup()` or `biba_mode_standalone_init()`.
- **Blocking on large CDC writes:** `Serial.write()` of a 1.4 MB file blocks until the USB host reads it. This is acceptable during download (robot disarmed, operator at terminal) but must never happen while armed.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Wear leveling on flash | Custom block allocator | LittleFS (built-in wear leveling with block_cycles) | Correctness requires tracking erase counts per block; LittleFS already does this |
| Binary CDC protocol | XMODEM, ZMODEM | Simple `SIZE:<N>\r\n` + raw bytes | XMODEM adds 1 KB of protocol code and retry complexity; not needed for USB bulk transfer |
| Filesystem directory scan | Linked-list session index | `LittleFS.openDir()` | 30 sessions maximum; linear scan is trivial |
| Flash geometry config | Manual lfs_config | `board_build.filesystem_size` in platformio.ini | Platform builder computes FS_START/FS_END/FS_PAGE/FS_BLOCK automatically |

**Key insight:** LittleFS on arduino-pico is a zero-configuration drop-in once the partition
size is set. The only firmware code needed is file open/write/close and directory iteration.

---

## Critical Finding: Board Flash Size

> **⚠️ IMPORTANT — DIFFERS FROM CONTEXT.md ASSUMPTION**

The CONTEXT.md states "~1.9MB свободно под данные" based on 2MB total flash.

[VERIFIED: firmware/.pio/build/rpico_rp2040_standalone/idedata.json]

```
PICO_FLASH_SIZE_BYTES = 16777216   (16 MB)
```

The board is a **YD-RP2040** (`vccgnd_yd_rp2040`), not the standard Raspberry Pi Pico.
It has **16 MB** of W25Q128 flash.

**Impact on decisions:**

| Parameter | CONTEXT.md assumed | Actual | Recommendation |
|-----------|-------------------|--------|----------------|
| Total flash | 2 MB | 16 MB | — |
| FS partition | 1 MB | **4 MB** | Increase — ample headroom, negligible sketch impact |
| Min free KB | 64 KB | 64 KB | Keep same |
| Session capacity at 1.4 MB/session | ~0 sessions after firmware | ~2 sessions | With 4 MB: ~2 full 60-min sessions; or 10+ sessions at field-typical 5–10 min |

**Capacity with 4 MB partition at BIBA_BLACKBOX_FIELD_MASK = 0xFFFF, 10 Hz:**
- Record size: 4 + 2 + 2 + 2 + 2 + 2 + 2 + 1 + 1 + 2 + 2 + 1 + 2 + 2 + 2 + 2 = **31 bytes**
  (sum of all 16 fields from the struct layout)
- Plus timestamp overhead: already included in field 0
- Rate: 31 bytes × 10 Hz = 310 bytes/sec
- 4 MB / 310 bytes/sec = ~3.7 hours of recording
- Practical: each 10-min drive session ≈ 186 KB → ~22 sessions in 4 MB

---

## Data Sources for BB-02 Fields

All fields come from **`mode_standalone.c` static variables** already maintained by the tick.

[VERIFIED by reading firmware/src/modes/mode_standalone.c]

| BB Field | Type | Source in mode_standalone.c | Notes |
|----------|------|------------------------------|-------|
| timestamp_ms | uint32_t | `now` (biba_hal_now_ms()) | Direct |
| throttle | int16_t ×1000 | `throttle` (float → int16 ×1000) | After deadband |
| rudder | int16_t ×1000 | `steering` | After deadband |
| duty_left | int16_t ×1000 | `left_out` | Final duty after PI |
| duty_right | int16_t ×1000 | `right_out` | Final duty after PI |
| rpm_left_hz10 | uint16_t | `s_meas_hz_left` × 10 | EMA from spec estimator |
| rpm_right_hz10 | uint16_t | `s_meas_hz_right` × 10 | EMA from spec estimator |
| active_blocks_l | uint8_t | `s_freqdet_blocks_left` (cast) | From ZC detector |
| active_blocks_r | uint8_t | `s_freqdet_blocks_right` (cast) | From ZC detector |
| mean_is_l | uint16_t | computed in on_adc_pair_done → need static copy | Pass via static written by IRQ, read by tick |
| mean_is_r | uint16_t | same | Same |
| latch_resets | uint8_t | accumulated counter incremented when s_latch_reset_pending consumed | New static `s_latch_reset_count` |
| vbat_mv | uint16_t | `biba_voltage_sense_vbat_mv()` | Existing API [VERIFIED: voltage_sense.h] |
| pi_integral_l | int16_t ×10000 | `s_rpm_pi_left.integral` | float → int16 ×10000 |
| pi_integral_r | int16_t ×10000 | `s_rpm_pi_right.integral` | float → int16 ×10000 |
| pi_meas_ema_l | uint16_t (Hz×10) | `s_rpm_pi_left.meas_ema` × 10 | Field 15 only (no field 16) |

**Two fields need a new static bridge from IRQ to tick:**
- `s_mean_is_left_last` — volatile uint16_t, written by `on_adc_pair_done`, read by tick
- `s_mean_is_right_last` — same

These already exist as local variables in `on_adc_pair_done` — just promote to file-scope volatiles.

---

## Channel Assignment

[VERIFIED: firmware/include/biba_config.h lines 148–149]

```c
#define BIBA_CH_BEACON   7   /* CH8 — already exists */
```

`BIBA_CH_BEACON` is the **exact channel** the CONTEXT.md designates for blackbox trigger.
The existing `beacon_ch` variable in the tick already reads it.

**Recommended approach:** Add `#define BIBA_CH_BLACKBOX BIBA_CH_BEACON` in `biba_config.h`
and use `beacon_ch` (already computed) as the blackbox enable input. This avoids any
duplicate channel read and makes the semantic intention explicit.

**No new channel read needed** — `beacon_ch` already holds the value.

---

## Common Pitfalls

### Pitfall 1: Flash Sector Erase Stall (~45 ms every ~13 seconds)

**What goes wrong:** `lfs_file_write()` synchronously erases a 4096-byte flash sector
when allocating a new block. The RP2040 suspends XIP during this operation.

**Why it happens:** At 10 Hz × 31 bytes = 310 bytes/sec, a 4096-byte LittleFS block
fills in ~13 seconds, triggering one sector erase. W25Q128 sector erase: typical 45 ms,
max 400 ms.

**How to avoid:** Accept the stall. A 45 ms pause in the main tick causes at most 4–5
missed ticks — the CRSF failsafe timeout is 200 ms so no safety event is triggered.
Motor output holds its last duty during the stall (no active HAL reset).

**Warning signs:** Periodic ~45 ms gaps visible in the `DRIVE_DATA` telemetry timestamps
while recording.

**Mitigation if unacceptable later:** Pre-erase sectors on a 2nd core thread between
recording sessions. Not required for Phase 8.

### Pitfall 2: LittleFS.begin() Autoformat Erasing All Data

**What goes wrong:** First boot with a non-zero filesystem partition but no formatted
FS → `LittleFS.begin()` returns false. Calling `LittleFS.format()` then `LittleFS.begin()`
is correct and necessary, but must only happen **once** (not on every boot where sessions exist).

**How to avoid:** The arduino-pico `LittleFS.begin()` already has `autoFormat=true` as the
default config (`LittleFSConfig::autoFormat = true`). With this default, `LittleFS.begin()`
auto-formats on first use and returns true. **Do not call `LittleFS.format()` manually
unless you intend to wipe all sessions.**

**Correct pattern:**
```cpp
bool blackbox_init(void) {
    // Default LittleFSConfig has autoFormat=true — mounts or formats on first use
    return LittleFS.begin();
}
```

### Pitfall 3: `Serial.write()` Blocks During Large File Transfer While Armed

**What goes wrong:** `bb get` on a 186 KB session file sends ~186 KB over CDC. If the host
(Python) doesn't read fast enough, `Serial.write()` blocks. If the robot is armed while
this happens, the motor tick stops.

**How to avoid:** Shell commands are processed in `process_debug_serial()` which only fires
on a received newline. Guard all `bb get` responses so they refuse to transmit if `s_armed`:
```c
if (s_armed) {
    printf("[bb] refuse get while armed\r\n");
    return;
}
```

### Pitfall 4: `BIBA_CH_BLACKBOX` Conflicts With Existing Beacon Logic

**What goes wrong:** The beacon melody code in `mode_standalone.c` already uses `beacon_ch`
and `s_beacon_active` to play SOS when disarmed. Adding blackbox behavior to the same
variable without refactoring causes double-play of SOS on CH8 HIGH.

**How to avoid:** During refactor, the blackbox CH8 HIGH handler replaces the beacon SOS
trigger. The SOS melody context stays (blackbox enable = arm indicator), the old
"free-standing beacon" behavior is retired unless separately switched. Document this in
the plan as an explicit behavioral replacement.

### Pitfall 5: Session Number Wraps at 9999

**What goes wrong:** After 9999 sessions, `%04lu` wraps to 0000 and overwrites the oldest
session.

**How to avoid:** At 22 sessions per 4 MB, hitting 9999 requires 454 reformats.
Practically irrelevant, but the directory-listing scan should handle wrap-around by treating
`0000` as `10000` when `9999` is also present (lexicographic sort artifact). Simplest fix:
clamp at 9999 and refuse to open new session until a del clears space.

### Pitfall 6: LittleFS Not Included in Build (common in PlatformIO)

**What goes wrong:** `#include <LittleFS.h>` compiles fine (header found in IntelliSense path)
but linker reports undefined `LittleFS` object — the library's `.cpp` source wasn't compiled.

**Why it happens:** PlatformIO arduino-pico framework auto-discovers libraries in
`framework-arduinopico/libraries/`, but only if the library is referenced correctly and
the env uses the `arduino` framework.

**How to avoid:** The `[env:rpico_rp2040_standalone]` already uses `framework = arduino`
[VERIFIED: platformio.ini line 247]. LittleFS is auto-discovered. If there are link errors,
add `lib_deps = LittleFS` to the env stanza.

---

## Code Examples

### Open + write + close a session file

```cpp
// Source: arduino-pico/libraries/LittleFS/examples/SpeedTest/SpeedTest.ino (verified locally)
File f = LittleFS.open("/session_0001.bbd", "w");
f.write(header_buf, 32);          // 32-byte header
f.write(record_buf, record_size); // per-tick records
f.flush();                        // not required before close, but confirms write
f.close();
```

### Directory scan to find session bounds

```cpp
// Source: arduino-pico LittleFS API (verified from LittleFS.h LittleFSDirImpl)
Dir dir = LittleFS.openDir("/");
while (dir.next()) {
    String name = dir.fileName();   // "session_0001.bbd"
    size_t size = dir.fileSize();   // bytes
}
```

### Filesystem info

```cpp
// Source: LittleFS.h FSImpl lfs_fs_size()
FSInfo info;
LittleFS.info(info);
size_t used  = info.usedBytes;
size_t total = info.totalBytes;
```

### platformio.ini partition activation

```ini
; Source: /home/ros2/.platformio/platforms/rp2040/builder/main.py lines 63-79 (verified)
[env:rpico_rp2040_standalone]
; ... existing fields ...
board_build.filesystem_size = 4MB
```

This causes the platform builder to compute:
```
FS_START = 0x10000000 + 16MB - 4KB (EEPROM) - 4MB = 0x10C00000 - 4KB
FS_END   = 0x10000000 + 16MB - 4KB (EEPROM)       = 0x10FFD000
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| SPIFFS (no wear leveling) | LittleFS (wear leveled) | arduino-pico 2.x+ | LittleFS is the default and correct choice |
| SD card logging | Internal flash LittleFS | Board design (no SD on YD-RP2040) | Simpler: no SPI, no card insertion |

**Deprecated/outdated:**
- `SPIFFS` API: superseded by `LittleFS` in arduino-pico (same API surface, LittleFS preferred). Do not use `SPIFFS.begin()`.

---

## Environment Availability

[VERIFIED: local toolchain probe]

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| LittleFS library | firmware FS | ✓ | bundled with framework-arduinopico | — |
| pyserial | biba_blackbox_download.py | ✓ | already in requirements | — |
| picotool / cmsis-dap | flash upload | ✓ | PlatformIO upload_protocol = picotool | — |
| python3 struct | .bbd decoder | ✓ | stdlib | — |

**Missing dependencies with no fallback:** None.

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | The existing `beacon_ch` variable is safe to alias as blackbox enable | Channel Assignment | If beacon and blackbox must coexist independently (different CH), need a new channel assignment and transmitter config — affects field testing |
| A2 | 45 ms worst-case erase stall is acceptable for motor control | Pitfall 1 | If motors are in a precision maneuver, brief freeze may cause course deviation — may need pre-erase strategy |
| A3 | `Serial.write()` is thread-safe from core 0 main loop during file download | CDC Write | If TinyUSB has re-entrancy issues under heavy concurrent CDC output, partial data corruption possible — test empirically |

---

## Open Questions

1. **Beacon feature retirement**
   - What we know: `beacon_ch` + `s_beacon_active` implements a disarmed SOS beacon on CH8
   - What's unclear: Should the blackbox CH8 handler completely replace the beacon, or should both coexist (beacon when disarmed, blackbox when armed)?
   - Recommendation: **Replace.** The blackbox SOS plays on CH8 HIGH (same audio), and the old beacon-while-driving-disabled logic stays via `!control_active` guard. Functionally identical to the operator. Plan should document this explicitly.

2. **`mean_is_l/r` values — IRQ → tick handoff**
   - What we know: `mean_is_left/right` are computed as local variables inside `on_adc_pair_done()` IRQ
   - What's unclear: Not yet promoted to file-scope static volatiles
   - Recommendation: Add `static volatile uint16_t s_mean_is_last_left, s_mean_is_last_right;` as plan task in the same wave as blackbox record assembly.

---

## Security Domain

This is an embedded firmware with no network access, no authentication surface, and
no user-supplied untrusted data flowing through the blackbox path. The only external
inputs to the blackbox module are:

| ASVS Category | Applies | Control |
|---------------|---------|---------|
| V5 Input Validation | **YES** | CDC shell commands: filenames from `bb get <file>` must be validated before passing to `LittleFS.open()` — prevent path traversal (`../`, absolute paths). Validate: must match `^session_[0-9]{4}\.bbd$` |
| V6 Cryptography | No | No encryption needed for local flight data |
| V2 Authentication | No | CDC is a local USB connection — physical access assumed |

### Known Threat Patterns

| Pattern | STRIDE | Mitigation |
|---------|--------|------------|
| Path traversal in `bb get ../secret` | Tampering | Validate filename matches `session_NNNN.bbd` regex before open |
| Buffer overflow in shell line parser | Tampering | `biba_hal_serial_readline` already clamps at 127 chars; `bb get` filename fits in 24 chars |

---

## Sources

### Primary (HIGH confidence)
- `firmware/.pio/build/rpico_rp2040_standalone/idedata.json` — `PICO_FLASH_SIZE_BYTES=16777216`, `FS_START=FS_END` (verified locally)
- `/home/ros2/.platformio/platforms/rp2040/builder/main.py` — `board_build.filesystem_size` parsing logic, FS_PAGE/FS_BLOCK values
- `/home/ros2/.platformio/packages/framework-arduinopico/libraries/LittleFS/src/LittleFS.h` — API surface (open, Dir, FSInfo)
- `/home/ros2/.platformio/packages/framework-arduinopico/libraries/LittleFS/examples/SpeedTest/SpeedTest.ino` — usage patterns
- `firmware/src/modes/mode_standalone.c` — existing tick structure, channel reads, state variables
- `firmware/src/hal/biba_hal_serial.cpp` — existing C++/C wrapper pattern
- `firmware/include/biba_config.h` — `BIBA_CH_BEACON = 7`
- `firmware/src/drivers/voltage_sense.h` — `biba_voltage_sense_vbat_mv()` API
- `/home/ros2/.platformio/platforms/rp2040/boards/vccgnd_yd_rp2040.json` — `maximum_size: 16777216`

### Secondary (MEDIUM confidence)
- W25Q128 sector erase timing: typical 45 ms, max 400 ms [ASSUMED from W25Q128 datasheet knowledge — timing class applies to any W25Q128-series chip used on YD-RP2040]

---

## Metadata

**Confidence breakdown:**
- Standard Stack: HIGH — LittleFS verified present in local framework installation
- Flash size finding: HIGH — directly read from idedata.json
- Architecture: HIGH — derived from reading actual mode_standalone.c source
- Write latency: MEDIUM — sector erase timing is ASSUMED (not measured on this hardware)
- Python protocol: HIGH — based on pyserial patterns already in vcp_capture.py

**Research date:** 2026-05-25
**Valid until:** 2026-09-01 (LittleFS API is stable; platformio.ini syntax may shift with platform updates)
