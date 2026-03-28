#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import BinaryIO, TextIO

import serial


DEFAULT_DEVICE = "/dev/ttyACM0"
DEFAULT_BAUD = 115200


def default_output_path(now: datetime | None = None) -> Path:
    moment = now or datetime.now().astimezone()
    return Path("artifacts/telemetry-captures") / f"vcp-{moment.strftime('%Y%m%d-%H%M%S')}.log"


def format_log_line(payload: str, moment: datetime, epoch_s: float) -> str:
    return f"{moment.isoformat()} epoch={epoch_s:.6f} {payload.rstrip()}\n"


def capture_stream(
    reader: BinaryIO,
    output: TextIO,
    *,
    now_fn=datetime.now,
    epoch_fn=time.time,
    max_empty_reads: int | None = None,
) -> None:
    empty_reads = 0

    while True:
        raw = reader.readline()
        if not raw:
            empty_reads += 1
            if max_empty_reads is not None and empty_reads >= max_empty_reads:
                return
            continue

        empty_reads = 0
        moment = now_fn()
        if moment.tzinfo is None:
            moment = moment.astimezone()
        payload = raw.decode("utf-8", errors="replace").rstrip("\r\n")
        output.write(format_log_line(payload, moment, epoch_fn()))
        output.flush()


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture EdgeTX Lua VCP output with local timestamps")
    parser.add_argument("--device", default=DEFAULT_DEVICE, help="Serial device to read")
    parser.add_argument("--baud", type=int, default=DEFAULT_BAUD, help="Serial baud rate")
    parser.add_argument("--output", type=Path, default=None, help="Output log path")
    args = parser.parse_args()

    output_path = args.output or default_output_path()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        with serial.Serial(args.device, args.baud, timeout=1) as reader, output_path.open("w", encoding="utf-8") as output:
            print(output_path)
            capture_stream(reader, output)
    except KeyboardInterrupt:
        return 0
    except serial.SerialException as exc:
        print(f"serial error: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())