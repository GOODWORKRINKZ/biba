# 08-03 SUMMARY — CDC bb Shell + Python Download Script

## Status: COMPLETE

## What Was Built

### `firmware/src/modes/mode_standalone.c` — bb shell commands in `process_debug_serial()`

Four new CDC commands added (always available, no `s_dbg_active` required):

| Command | Handler | Guard |
|---|---|---|
| `bb list\n` | `blackbox_list_sessions()` | none (read-only) |
| `bb get session_NNNN.bbd\n` | `blackbox_send_session(line+7)` | `ERR:RECORDING_ACTIVE` if `s_bb_recording` |
| `bb del session_NNNN.bbd\n` | `blackbox_delete_session(line+7)` | `ERR:RECORDING_ACTIVE` if `s_bb_recording` |
| `bb info\n` | `blackbox_info()` | none (read-only) |

Security: `ERR:RECORDING_ACTIVE` guard prevents concurrent LittleFS access from CDC handler and tick's write path (T-08-08 mitigation). Filename path-traversal validation remains in `blackbox_send_session` / `blackbox_delete_session` (T-08-07, Plan 01).

### `scripts/biba_blackbox_download.py` — standalone download + decode tool

Functions implemented:
- `auto_detect_port()` — glob `/dev/ttyACM*`, returns first; raises `RuntimeError` if none
- `list_sessions(port)` — sends `bb list\n`, returns `list[str]` of filenames
- `download_session(port, filename, out_dir)` — validates filename regex, sends `bb get`, reads `SIZE:N` header, reads N bytes, writes `.bbd`
- `decode_bbd(data)` — unpacks 32-byte header, builds active field list from `field_mask` bitmask, parses 31-byte records
- `save_csv(filename, records, out_dir)` — writes `artifacts/blackbox/session_NNNN.csv`
- `main()` — argparse CLI: `--all`, `--session NNNN`, `--no-decode`, `--port`, `--baud`

Security: `download_session` validates filename with `r"^session_\d{4}\.bbd$"` before constructing output path (T-08-09). Port comes from glob pattern (T-08-10: `timeout=5` on `Serial` open).

## Verification Results

- `pio run -e rpico_rp2040_standalone`: **SUCCESS**
- `python3 -m py_compile scripts/biba_blackbox_download.py`: **exit 0**
- `python3 scripts/biba_blackbox_download.py --help`: prints all flags
- Decode smoke test: synthetic 32-byte header + 31-byte record → correct 16-column dict, record size confirmed 31 bytes

## Integration Test (hardware required)

1. Flash firmware; CH8 HIGH → arm → ride → disarm
2. `python3 scripts/biba_blackbox_download.py --all`
3. Verify `artifacts/blackbox/session_0001.bbd` ≥ 342 bytes (32 header + 31×10 records)
4. Verify `artifacts/blackbox/session_0001.csv` has 16-column header + ≥10 data rows
5. Verify `timestamp_ms` column increases monotonically
