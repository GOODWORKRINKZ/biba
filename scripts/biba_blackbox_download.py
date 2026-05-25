#!/usr/bin/env python3
"""biba_blackbox_download.py — Download and decode BiBa blackbox sessions.

Usage:
  python3 scripts/biba_blackbox_download.py --all
  python3 scripts/biba_blackbox_download.py --session 0001
  python3 scripts/biba_blackbox_download.py          # list only

Output:  artifacts/blackbox/session_NNNN.bbd  (raw binary)
         artifacts/blackbox/session_NNNN.csv  (decoded, unless --no-decode)
"""
from __future__ import annotations

import argparse
import csv
import glob
import re
import struct
import sys
import time
from pathlib import Path

import serial

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_BAUD = 115200
OUT_DIR = Path("artifacts/blackbox")

# 16 record fields in bit-index order (matches biba_blackbox_record_t).
# Each tuple: (column_name, struct_fmt_char)
FIELDS: list[tuple[str, str]] = [
    ("timestamp_ms",   "I"),
    ("throttle",       "h"),
    ("rudder",         "h"),
    ("duty_left",      "h"),
    ("duty_right",     "h"),
    ("rpm_left_hz10",  "H"),
    ("rpm_right_hz10", "H"),
    ("active_blocks_l","B"),
    ("active_blocks_r","B"),
    ("mean_is_l",      "H"),
    ("mean_is_r",      "H"),
    ("latch_resets",   "B"),
    ("vbat_mv",        "H"),
    ("pi_integral_l",  "h"),
    ("pi_integral_r",  "h"),
    ("pi_meas_ema_l",  "H"),
]

HEADER_SIZE = 32
MAGIC = b"BBD1"
FILENAME_RE = re.compile(r"^session_\d{4}\.bbd$")


# ---------------------------------------------------------------------------
# Port detection
# ---------------------------------------------------------------------------

def auto_detect_port() -> str:
    """Return the first /dev/ttyACM* device found, or raise RuntimeError."""
    candidates = sorted(glob.glob("/dev/ttyACM*"))
    if not candidates:
        raise RuntimeError(
            "No /dev/ttyACM* device found. Is the RP2040 connected?"
        )
    return candidates[0]


# ---------------------------------------------------------------------------
# Firmware CDC communication
# ---------------------------------------------------------------------------

def _read_line(port: serial.Serial) -> str:
    """Read one line from the serial port, strip CRLF."""
    raw = port.readline()
    return raw.decode("utf-8", errors="replace").rstrip("\r\n")


def list_sessions(port: serial.Serial) -> list[str]:
    """Send 'bb list' and return a list of session filenames."""
    port.write(b"bb list\n")
    sessions: list[str] = []
    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline:
        line = _read_line(port)
        if not line:
            break
        m = re.search(r"(session_\d{4}\.bbd)", line)
        if m:
            sessions.append(m.group(1))
    return sessions


def download_session(port: serial.Serial, filename: str, out_dir: Path) -> bytes:
    """Download a single session file from the firmware.

    Returns the raw .bbd bytes and saves them to out_dir/filename.
    Raises RuntimeError on firmware error or protocol violation.
    Raises ValueError if filename fails validation.
    """
    if not FILENAME_RE.match(filename):
        raise ValueError(
            f"Invalid session filename '{filename}'. "
            "Expected pattern: session_NNNN.bbd"
        )
    port.write(f"bb get {filename}\n".encode())

    # Read SIZE header
    header_line = _read_line(port)
    if header_line.startswith("ERR:"):
        raise RuntimeError(f"Firmware error: {header_line}")
    m = re.match(r"SIZE:(\d+)", header_line)
    if not m:
        raise RuntimeError(
            f"Unexpected response from firmware (expected SIZE:N): '{header_line}'"
        )
    size = int(m.group(1))
    if size == 0:
        raise RuntimeError("Firmware reported SIZE:0 — session is empty.")

    # Read exactly `size` bytes
    data = b""
    deadline = time.monotonic() + 30.0  # generous timeout for large sessions
    while len(data) < size and time.monotonic() < deadline:
        chunk = port.read(size - len(data))
        if chunk:
            data += chunk
    if len(data) != size:
        raise RuntimeError(
            f"Short read: expected {size} bytes, got {len(data)}."
        )

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / filename).write_bytes(data)
    print(f"  Saved {filename} ({size} bytes)")
    return data


# ---------------------------------------------------------------------------
# Binary decode
# ---------------------------------------------------------------------------

def decode_bbd(data: bytes) -> tuple[dict, list[dict]]:
    """Parse a .bbd binary blob into (header_dict, list_of_record_dicts).

    Raises ValueError on magic mismatch or structural errors.
    """
    if len(data) < HEADER_SIZE:
        raise ValueError(f"Too short to be a valid .bbd file ({len(data)} bytes).")

    magic, created_ms, field_mask, rate_hz = struct.unpack_from("<4sIHB", data, 0)
    if magic != MAGIC:
        raise ValueError(
            f"Bad magic: expected {MAGIC!r}, got {magic!r}."
        )

    header: dict = {
        "magic": magic.decode("ascii"),
        "created_ms": created_ms,
        "field_mask": f"0x{field_mask:04X}",
        "rate_hz": rate_hz,
    }

    # Build active field list from field_mask bitmask
    active = [
        (name, fmt)
        for bit, (name, fmt) in enumerate(FIELDS)
        if field_mask & (1 << bit)
    ]
    if not active:
        return header, []

    rec_fmt = "<" + "".join(fmt for _, fmt in active)
    rec_size = struct.calcsize(rec_fmt)
    col_names = [name for name, _ in active]

    records: list[dict] = []
    offset = HEADER_SIZE
    while offset + rec_size <= len(data):
        values = struct.unpack_from(rec_fmt, data, offset)
        records.append(dict(zip(col_names, values)))
        offset += rec_size

    return header, records


# ---------------------------------------------------------------------------
# CSV export
# ---------------------------------------------------------------------------

ALL_FIELD_NAMES = [name for name, _ in FIELDS]


def save_csv(filename: str, records: list[dict], out_dir: Path) -> Path:
    """Write records to a CSV file; returns the path."""
    csv_path = out_dir / filename.replace(".bbd", ".csv")
    fieldnames = list(records[0].keys()) if records else ALL_FIELD_NAMES
    with csv_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)
    print(f"  Decoded → {csv_path.name} ({len(records)} records)")
    return csv_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="biba_blackbox_download",
        description="Download BiBa RP2040 blackbox sessions over USB CDC.",
    )
    p.add_argument(
        "--port",
        default=None,
        help="Serial port (default: auto-detect /dev/ttyACM*)",
    )
    p.add_argument(
        "--baud",
        type=int,
        default=DEFAULT_BAUD,
        help=f"Baud rate (default: {DEFAULT_BAUD})",
    )
    p.add_argument(
        "--all",
        action="store_true",
        dest="download_all",
        help="Download all sessions",
    )
    p.add_argument(
        "--session",
        metavar="NNNN",
        default=None,
        help="Download a specific session by 4-digit number (e.g. 0001)",
    )
    p.add_argument(
        "--no-decode",
        action="store_true",
        help="Skip CSV decode; save .bbd binary only",
    )
    return p


def main() -> int:
    parser = build_argparser()
    args = parser.parse_args()

    # Resolve port
    try:
        port_path = args.port or auto_detect_port()
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Opening {port_path} at {args.baud} baud …")
    try:
        ser = serial.Serial(port_path, args.baud, timeout=5)
    except serial.SerialException as exc:
        print(f"ERROR: Cannot open serial port: {exc}", file=sys.stderr)
        return 1

    # Flush partial lines in firmware buffer
    ser.write(b"\n")
    time.sleep(0.1)
    ser.reset_input_buffer()

    downloaded: list[str] = []

    if args.download_all:
        print("Listing sessions …")
        sessions = list_sessions(ser)
        if not sessions:
            print("No sessions found on device.")
            ser.close()
            return 0
        print(f"Found {len(sessions)} session(s): {', '.join(sessions)}")
        for fname in sessions:
            print(f"Downloading {fname} …")
            try:
                data = download_session(ser, fname, OUT_DIR)
                downloaded.append(fname)
                if not args.no_decode:
                    _, records = decode_bbd(data)
                    save_csv(fname, records, OUT_DIR)
            except (RuntimeError, ValueError) as exc:
                print(f"  ERROR: {exc}", file=sys.stderr)

    elif args.session is not None:
        fname = f"session_{args.session:0>4}.bbd"
        print(f"Downloading {fname} …")
        try:
            data = download_session(ser, fname, OUT_DIR)
            downloaded.append(fname)
            if not args.no_decode:
                _, records = decode_bbd(data)
                save_csv(fname, records, OUT_DIR)
        except (RuntimeError, ValueError) as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            ser.close()
            return 1

    else:
        # List only
        print("Listing sessions (no --all or --session flag given) …")
        sessions = list_sessions(ser)
        if sessions:
            for s in sessions:
                print(f"  {s}")
        else:
            print("  (no sessions)")
        ser.close()
        return 0

    ser.close()
    if downloaded:
        print(f"\nDownloaded {len(downloaded)} session(s) to {OUT_DIR}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
