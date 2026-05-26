/* Blackbox flight recorder — C-compatible header.
 *
 * Provides struct definitions for the .bbd binary file format and
 * extern-C declarations for the LittleFS wrapper API (blackbox.cpp).
 *
 * Rules:
 *  - All blackbox_* functions MUST be called from main context only —
 *    LittleFS is NOT interrupt-safe.
 *  - blackbox_send_session() MUST only be called while the robot is disarmed —
 *    blocking USB writes during a live session would corrupt timing.
 *
 * Security: blackbox_send_session() and blackbox_delete_session() validate
 * the filename argument against the strict pattern "session_%04u.bbd" before
 * constructing any filesystem path (T-08-01 — path traversal mitigation). */

#ifndef BIBA_BLACKBOX_H
#define BIBA_BLACKBOX_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>

/* Magic bytes at the start of every .bbd file header. */
#define BLACKBOX_MAGIC  "BBD1"

/* --- File header (32 bytes) -------------------------------------------- */

/* Written once at the start of every session file. */
typedef struct __attribute__((packed)) {
    uint8_t  magic[4];        /* "BBD1"                                      */
    uint32_t created_tick_ms; /* biba_hal_now_ms() at session open           */
    uint16_t field_mask;      /* bitfield: which record fields are present   */
    uint8_t  rate_hz;         /* BIBA_BLACKBOX_RATE_HZ used for this session */
    uint8_t  reserved[21];    /* pad to exactly 32 bytes                     */
} biba_blackbox_header_t;

/* --- Record (31 bytes, field_mask bit ordering) ------------------------- */

/* One record is written every 1000/BIBA_BLACKBOX_RATE_HZ ms while armed +
 * recording.  All 16 fields are present when field_mask == 0xFFFF. */
typedef struct __attribute__((packed)) {
    uint32_t timestamp_ms;    /* bit  0  — millis since boot                 */
    int16_t  throttle;        /* bit  1  — rc_to_unit ×1000 → [-1000..+1000] */
    int16_t  rudder;          /* bit  2  — rc_to_unit ×1000                  */
    int16_t  duty_left;       /* bit  3  — s_rpm_duty_left ×1000             */
    int16_t  duty_right;      /* bit  4  — s_rpm_duty_right ×1000            */
    int16_t  rpm_left_hz10;   /* bit  5  — pi_meas_hz_left  × 10 (signed)   */
    int16_t  rpm_right_hz10;  /* bit  6  — pi_meas_hz_right × 10 (signed)   */
    uint8_t  active_blocks_l; /* bit  7  — s_freqdet_blocks_left             */
    uint8_t  active_blocks_r; /* bit  8  — s_freqdet_blocks_right            */
    uint16_t mean_is_l;       /* bit  9  — s_mean_is_left (raw ADC counts)   */
    uint16_t mean_is_r;       /* bit 10  — s_mean_is_right                   */
    uint8_t  latch_resets;    /* bit 11  — s_latch_resets (accumulated)      */
    uint16_t vbat_mv;         /* bit 12  — biba_voltage_sense_vbat_mv()      */
    int16_t  pi_integral_l;   /* bit 13  — s_rpm_pi_left.integral ×10000     */
    int16_t  pi_integral_r;   /* bit 14  — s_rpm_pi_right.integral ×10000    */
    uint16_t pi_meas_ema_l;   /* bit 15  — s_telem_meas_ema_left × 10        */
} biba_blackbox_record_t;

/* Compile-time size assertions. */
#ifdef __cplusplus
static_assert(sizeof(biba_blackbox_header_t) == 32u,
              "biba_blackbox_header_t must be exactly 32 bytes");
static_assert(sizeof(biba_blackbox_record_t) == 31u,
              "biba_blackbox_record_t must be exactly 31 bytes");
#else
_Static_assert(sizeof(biba_blackbox_header_t) == 32u,
               "biba_blackbox_header_t must be exactly 32 bytes");
_Static_assert(sizeof(biba_blackbox_record_t) == 31u,
               "biba_blackbox_record_t must be exactly 31 bytes");
#endif

/* --- C API ------------------------------------------------------------- */

#ifdef __cplusplus
extern "C" {
#endif

/* Mount LittleFS.  Formats and remounts on first-use failure.
 * Must be called once during init before any other blackbox_* call. */
bool blackbox_init(void);

/* Create a new session file "/session_NNNN.bbd" and write the 32-byte header.
 * Returns false if the file cannot be created. */
bool blackbox_open_session(uint32_t session_num, uint32_t tick_ms,
                           uint16_t field_mask, uint8_t rate_hz);

/* Append `len` raw bytes to the open session file.  No-op if no session is
 * currently open. */
void blackbox_write_record(const uint8_t *buf, size_t len);

/* Flush and close the current session file. */
void blackbox_close_session(void);

/* Returns true when free space on the filesystem is below min_free_kb
 * kilobytes.  Call before opening a new session. */
bool blackbox_is_full(uint32_t min_free_kb);

/* Returns the next sequential session number to use (max existing + 1, or 1
 * if no sessions exist).  If oldest_out is non-NULL, writes the number of the
 * oldest (lowest-numbered) existing session to *oldest_out. */
uint32_t blackbox_next_session_num(uint32_t *oldest_out);

/* Removes the session file with the lowest session number. */
void blackbox_delete_oldest(void);

/* CDC shell helpers — called by process_debug_serial() in Plan 03. */

/* Print one "session_NNNN.bbd SIZE bytes\r\n" line per session to CDC. */
void blackbox_list_sessions(void);

/* Send the named session over CDC as "SIZE:N\r\n" followed by N raw bytes.
 * Validates filename strictly before opening (T-08-01).
 * Returns false if the file is not found. */
bool blackbox_send_session(const char *filename);

/* Remove the named session.  Validates filename strictly (T-08-01).
 * Prints "OK\r\n" on success, "ERR:NOT_FOUND\r\n" on failure. */
bool blackbox_delete_session(const char *filename);

/* Print filesystem stats and session count to CDC. */
void blackbox_info(void);

#ifdef __cplusplus
}
#endif

#endif /* BIBA_BLACKBOX_H */
