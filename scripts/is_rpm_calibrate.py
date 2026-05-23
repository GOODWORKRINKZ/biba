#!/usr/bin/env python3
"""IS-RPM offline calibration script (Phase 07 Plan 03).

Drives the rpico_rp2040_is_poc firmware over USB CDC, issuing the CALRUN
command at each duty point, prompts the operator for an external
tachometer reading per point, fits a linear K-coefficient model, and
writes a JSON artifact to scripts/artifacts/calibration/.

Usage:
    # Real run against firmware:
    ./is_rpm_calibrate.py --port /dev/ttyACM0 --wheel left
    # Synthetic dry-run (no serial, no prompts):
    ./is_rpm_calibrate.py --dry-run --wheel left

Output JSON schema:
    {
      "wheel": "left",
      "date": "YYYY-MM-DD",
      "K_hz_per_pct": <float>,
      "dead_hz": <float>,
      "r_squared": <float>,
      "points": [ {"duty_pct": int, "is_hz": float, "tach_hz": float|null} ]
    }
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import random
import sys
import time
from pathlib import Path

import numpy as np

try:  # pyserial only required when not in --dry-run mode
    import serial  # type: ignore
except ImportError:  # pragma: no cover - exercised only on PoC hardware
    serial = None  # type: ignore


DEFAULT_DUTIES = "30,50,70,90"
DEFAULT_SETTLE_MS = 3000
DEFAULT_BAUD = 115200
IS_HZ_TIMEOUT_S = 15.0
MIN_VALID_POINTS = 3
R_SQUARED_WARN = 0.95
# Synthetic-mode coefficients (mirror RPMRUN_FF_SLOPE_DEFAULT / FF_DEAD_DEFAULT
# in firmware/src/poc/is_rpm_poc_main.cpp so the script's dry-run matches the
# real firmware's expected linear region).
SYNTHETIC_K = 10.13
SYNTHETIC_DEAD = 74.6
SYNTHETIC_NOISE_PCT = 0.02


def _eprint(*args, **kwargs) -> None:
    print(*args, file=sys.stderr, **kwargs)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", default=None,
                    help="Serial port (e.g. /dev/ttyACM0); required unless --dry-run.")
    ap.add_argument("--wheel", choices=["left", "right"], default="left",
                    help="Which wheel is being calibrated (default: left).")
    ap.add_argument("--duties", default=DEFAULT_DUTIES,
                    help=f"Comma-separated duty points (default: {DEFAULT_DUTIES}).")
    ap.add_argument("--settle-ms", type=int, default=DEFAULT_SETTLE_MS,
                    help=f"Motor settle time per point in ms (default: {DEFAULT_SETTLE_MS}).")
    ap.add_argument("--dry-run", action="store_true",
                    help="Skip serial + prompts; generate synthetic points.")
    ap.add_argument("--out-dir", default="scripts/artifacts/calibration",
                    help="Artifact directory (default: scripts/artifacts/calibration).")
    return ap.parse_args(argv)


def _parse_duties(spec: str) -> list[int]:
    out: list[int] = []
    for tok in spec.split(","):
        tok = tok.strip()
        if not tok:
            continue
        v = int(tok)
        if not (0 <= v <= 100):
            raise ValueError(f"duty {v} out of range 0..100")
        out.append(v)
    if not out:
        raise ValueError("no duty points provided")
    return out


def _wait_ready(ser, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        line = ser.readline().decode("ascii", errors="replace").strip()
        if line == "IS_POC_READY":
            return
    raise TimeoutError("IS_POC_READY not received within timeout")


def _read_is_hz(ser, duty: int) -> float:
    """Send CALRUN and read until IS_HZ line; return Hz (already scaled / 100)."""
    deadline = time.monotonic() + IS_HZ_TIMEOUT_S
    while time.monotonic() < deadline:
        line = ser.readline().decode("ascii", errors="replace").strip()
        if not line:
            continue
        if line.startswith("ERROR"):
            raise RuntimeError(f"firmware error: {line}")
        if line.startswith("IS_HZ "):
            parts = line.split()
            if len(parts) >= 3 and int(parts[1]) == duty:
                return int(parts[2]) / 100.0
    raise TimeoutError(f"IS_HZ not received within {IS_HZ_TIMEOUT_S}s for duty={duty}")


def _prompt_tach(duty: int) -> float | None:
    val = input(f"  Enter tachometer Hz at {duty}%% (or ENTER to skip): ").strip()
    if not val:
        return None
    try:
        return float(val)
    except ValueError:
        _eprint(f"  WARNING: '{val}' is not a number — skipping this point")
        return None


def _collect_points_real(port: str, duties: list[int],
                         settle_ms: int) -> list[dict]:
    if serial is None:
        raise RuntimeError("pyserial not installed; install it or use --dry-run")
    points: list[dict] = []
    with serial.Serial(port, DEFAULT_BAUD, timeout=2.0) as ser:
        time.sleep(2.0)
        try:
            _wait_ready(ser)
        except TimeoutError:
            # PoC firmware may have already booted; continue anyway.
            _eprint("WARNING: IS_POC_READY not seen; assuming firmware is up.")
        for duty in duties:
            _eprint(f"\u2192 duty {duty}%%: settle {settle_ms}ms, capturing...")
            ser.write(f"CALRUN {duty} {settle_ms}\n".encode("ascii"))
            is_hz = _read_is_hz(ser, duty)
            _eprint(f"  IS_HZ = {is_hz:.2f} Hz")
            tach = _prompt_tach(duty)
            points.append({"duty_pct": duty, "is_hz": is_hz, "tach_hz": tach})
        ser.write(b"STOP\n")
    return points


def _collect_points_synthetic(duties: list[int]) -> list[dict]:
    """Generate clean linear synthetic data for --dry-run."""
    rng = random.Random(42)  # deterministic for tests
    points: list[dict] = []
    for duty in duties:
        clean = SYNTHETIC_K * duty - SYNTHETIC_DEAD
        if clean < 0.0:
            clean = 0.0
        noise = 1.0 + rng.uniform(-SYNTHETIC_NOISE_PCT, SYNTHETIC_NOISE_PCT)
        is_hz = round(clean * noise, 2)
        tach_hz = round(clean * (1.0 + rng.uniform(-0.005, 0.005)), 2)
        points.append({"duty_pct": duty, "is_hz": is_hz, "tach_hz": tach_hz})
    return points


def _fit_linear(points: list[dict]) -> tuple[float, float, float]:
    """Return (K_hz_per_pct, dead_hz, r_squared) from points with tach_hz set."""
    valid = [(p["duty_pct"], p["tach_hz"]) for p in points if p["tach_hz"] is not None]
    if len(valid) < MIN_VALID_POINTS:
        raise RuntimeError(
            f"need >= {MIN_VALID_POINTS} valid tachometer points, got {len(valid)}"
        )
    duties = np.array([d for d, _ in valid], dtype=float)
    tach   = np.array([h for _, h in valid], dtype=float)
    coeffs = np.polyfit(duties, tach, 1)            # [slope, intercept]
    K_hz_per_pct = float(coeffs[0])
    intercept = float(coeffs[1])
    # Firmware FF model: hz = K * duty - dead_hz  =>  dead_hz = -intercept (in Hz).
    # This matches RPMRUN_FF_DEAD_DEFAULT in firmware/src/poc/is_rpm_poc_main.cpp.
    dead_hz = -intercept
    predicted = np.polyval(coeffs, duties)
    ss_res = float(np.sum((tach - predicted) ** 2))
    ss_tot = float(np.sum((tach - tach.mean()) ** 2))
    r_squared = 1.0 - ss_res / ss_tot if ss_tot > 0.0 else 1.0
    return K_hz_per_pct, dead_hz, r_squared


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        duties = _parse_duties(args.duties)
    except ValueError as e:
        _eprint(f"ERROR: --duties: {e}")
        return 2

    if not args.dry_run and not args.port:
        _eprint("ERROR: --port is required unless --dry-run is given")
        return 2

    if args.dry_run:
        _eprint(f"[dry-run] generating synthetic points for duties={duties}")
        points = _collect_points_synthetic(duties)
    else:
        points = _collect_points_real(args.port, duties, args.settle_ms)

    K_hz_per_pct, dead_hz, r_squared = _fit_linear(points)
    if r_squared < R_SQUARED_WARN:
        _eprint(
            f"WARNING: R\u00b2={r_squared:.3f} < {R_SQUARED_WARN} "
            "\u2014 check hardware/filter"
        )

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    today = _dt.date.today().isoformat()
    out_path = out_dir / f"{today}_{args.wheel}.json"
    artifact = {
        "wheel": args.wheel,
        "date": today,
        "K_hz_per_pct": round(K_hz_per_pct, 4),
        "dead_hz": round(dead_hz, 2),
        "r_squared": round(r_squared, 4),
        "points": points,
    }
    out_path.write_text(json.dumps(artifact, indent=2) + "\n")
    print(str(out_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
