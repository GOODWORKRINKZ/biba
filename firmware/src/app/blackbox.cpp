/* Blackbox flight recorder — LittleFS wrapper implementation.
 *
 * Follows the same pattern as biba_hal_serial.cpp: C++-only translation
 * unit that exports extern "C" symbols so C callers (mode_standalone.c)
 * can link against it without including any C++ headers.
 *
 * All LittleFS calls are main-context only — LittleFS is NOT ISR-safe.
 * blackbox_send_session() MUST only be called while disarmed. */

#include "blackbox.h"
#include <LittleFS.h>
#include <Arduino.h>
#include <stdio.h>
#include <string.h>

#include "hal/biba_hal.h"   /* biba_hal_serial_write_bytes / write_str */

/* --- File-scope state -------------------------------------------------- */

static File s_session_file;
static bool s_mounted = false;

/* --- Filename validation helper (T-08-01 — path traversal guard) ------- */

/* Returns true iff filename is exactly "session_NNNN.bbd" where NNNN is a
 * 4-digit decimal number (0000-9999).  Rejects any other string, preventing
 * directory traversal attacks from CDC shell input. */
static bool filename_is_valid(const char *filename)
{
    unsigned n = 0;
    if (!filename) return false;
    int matched = sscanf(filename, "session_%04u.bbd", &n);
    if (matched != 1) return false;
    /* Verify the resulting string is exactly the filename (no trailing junk). */
    char expected[24];
    snprintf(expected, sizeof(expected), "session_%04u.bbd", n);
    return strcmp(filename, expected) == 0;
}

/* --- Public API --------------------------------------------------------- */

extern "C" bool blackbox_init(void)
{
    if (!LittleFS.begin()) {
        LittleFS.format();
        LittleFS.begin();
    }
    s_mounted = LittleFS.begin();
    return s_mounted;
}

extern "C" bool blackbox_open_session(uint32_t session_num, uint32_t tick_ms,
                                       uint16_t field_mask, uint8_t rate_hz)
{
    if (!s_mounted) return false;

    char path[32];
    snprintf(path, sizeof(path), "/session_%04lu.bbd", (unsigned long)session_num);

    s_session_file = LittleFS.open(path, "w");
    if (!s_session_file) return false;

    biba_blackbox_header_t hdr;
    memcpy(hdr.magic, BLACKBOX_MAGIC, 4);
    hdr.created_tick_ms = tick_ms;
    hdr.field_mask       = field_mask;
    hdr.rate_hz          = rate_hz;
    memset(hdr.reserved, 0, sizeof(hdr.reserved));

    s_session_file.write(reinterpret_cast<const uint8_t *>(&hdr), sizeof(hdr));
    return true;
}

extern "C" void blackbox_write_record(const uint8_t *buf, size_t len)
{
    if (s_session_file) {
        s_session_file.write(buf, len);
    }
}

extern "C" void blackbox_close_session(void)
{
    if (s_session_file) {
        s_session_file.flush();
        s_session_file.close();
    }
}

extern "C" bool blackbox_is_full(uint32_t min_free_kb)
{
    if (!s_mounted) return true;
    FSInfo fs_info;
    LittleFS.info(fs_info);
    return (fs_info.totalBytes - fs_info.usedBytes) < (min_free_kb * 1024UL);
}

extern "C" uint32_t blackbox_next_session_num(uint32_t *oldest_out)
{
    if (!s_mounted) {
        if (oldest_out) *oldest_out = 0;
        return 1;
    }

    Dir dir = LittleFS.openDir("/");
    uint32_t min_n = UINT32_MAX;
    uint32_t max_n = 0;
    bool found_any = false;

    while (dir.next()) {
        unsigned n = 0;
        if (sscanf(dir.fileName().c_str(), "session_%04u.bbd", &n) == 1) {
            if ((uint32_t)n < min_n) min_n = (uint32_t)n;
            if ((uint32_t)n > max_n) max_n = (uint32_t)n;
            found_any = true;
        }
    }

    if (oldest_out) *oldest_out = found_any ? min_n : 0;
    return found_any ? (max_n + 1) : 1;
}

extern "C" void blackbox_delete_oldest(void)
{
    if (!s_mounted) return;
    uint32_t oldest = 0;
    blackbox_next_session_num(&oldest);
    if (oldest == 0) return;
    char path[32];
    snprintf(path, sizeof(path), "/session_%04lu.bbd", (unsigned long)oldest);
    LittleFS.remove(path);
}

extern "C" void blackbox_list_sessions(void)
{
    if (!s_mounted) return;
    Dir dir = LittleFS.openDir("/");
    while (dir.next()) {
        unsigned n = 0;
        if (sscanf(dir.fileName().c_str(), "session_%04u.bbd", &n) == 1) {
            char line[64];
            snprintf(line, sizeof(line), "%s %lu bytes\r\n",
                     dir.fileName().c_str(), (unsigned long)dir.fileSize());
            biba_hal_serial_write_str(line);
        }
    }
}

extern "C" bool blackbox_send_session(const char *filename)
{
    /* T-08-01: reject any filename that is not exactly "session_NNNN.bbd" */
    if (!filename_is_valid(filename)) {
        biba_hal_serial_write_str("ERR:INVALID\r\n");
        return false;
    }
    if (!s_mounted) {
        biba_hal_serial_write_str("ERR:NOT_FOUND\r\n");
        return false;
    }

    char path[32];
    snprintf(path, sizeof(path), "/%s", filename);

    File f = LittleFS.open(path, "r");
    if (!f) {
        biba_hal_serial_write_str("ERR:NOT_FOUND\r\n");
        return false;
    }

    uint32_t file_size = (uint32_t)f.size();
    char size_line[32];
    snprintf(size_line, sizeof(size_line), "SIZE:%lu\r\n", (unsigned long)file_size);
    biba_hal_serial_write_str(size_line);

    /* Stream file in 256-byte chunks. */
    uint8_t chunk[256];
    while (f.available()) {
        int n = f.read(chunk, sizeof(chunk));
        if (n > 0) {
            biba_hal_serial_write_bytes(chunk, (size_t)n);
        }
    }
    f.close();
    return true;
}

extern "C" bool blackbox_delete_session(const char *filename)
{
    /* T-08-01: reject any filename that is not exactly "session_NNNN.bbd" */
    if (!filename_is_valid(filename)) {
        biba_hal_serial_write_str("ERR:INVALID\r\n");
        return false;
    }
    if (!s_mounted) {
        biba_hal_serial_write_str("ERR:NOT_FOUND\r\n");
        return false;
    }

    char path[32];
    snprintf(path, sizeof(path), "/%s", filename);

    if (LittleFS.remove(path)) {
        biba_hal_serial_write_str("OK\r\n");
        return true;
    } else {
        biba_hal_serial_write_str("ERR:NOT_FOUND\r\n");
        return false;
    }
}

extern "C" void blackbox_info(void)
{
    if (!s_mounted) {
        biba_hal_serial_write_str("ERR:FS_NOT_MOUNTED\r\n");
        return;
    }

    FSInfo fs_info;
    LittleFS.info(fs_info);

    char line[80];
    snprintf(line, sizeof(line),
             "FS total=%lu used=%lu free=%lu bytes\r\n",
             (unsigned long)fs_info.totalBytes,
             (unsigned long)fs_info.usedBytes,
             (unsigned long)(fs_info.totalBytes - fs_info.usedBytes));
    biba_hal_serial_write_str(line);

    /* Count sessions. */
    Dir dir = LittleFS.openDir("/");
    unsigned count = 0;
    while (dir.next()) {
        unsigned n = 0;
        if (sscanf(dir.fileName().c_str(), "session_%04u.bbd", &n) == 1) {
            count++;
        }
    }
    snprintf(line, sizeof(line), "Sessions: %u\r\n", count);
    biba_hal_serial_write_str(line);
}
