#!/usr/bin/env python3
"""BiBa live telemetry monitor.

Connects to the robot via SSH, tails docker logs, and plots real-time
graphs of throttle, steering, and motor duty.

Usage:
    python scripts/biba_monitor.py [--host 192.168.2.185] [--tail 120]
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass, field

import matplotlib.pyplot as plt
import matplotlib.animation as animation
from matplotlib.figure import Figure

# ── Log line regex ──────────────────────────────────────────────────
# Matches:  ... raw_thr=0.02 thr=0.02 str=0.01 lm=0.000 rm=0.000 arm_ch=0.98 armed=True
_LOG_RE = re.compile(
    r"raw_thr=(?P<raw_thr>-?[\d.]+)\s+"
    r"thr=(?P<thr>-?[\d.]+)\s+"
    r"str=(?P<steer>-?[\d.]+)\s+"
    r"lm=(?P<lm>-?[\d.]+)\s+"
    r"rm=(?P<rm>-?[\d.]+)\s+"
    r"arm_ch=(?P<arm_ch>-?[\d.]+)\s+"
    r"armed=(?P<armed>\w+)"
)

# Also match old format without lm/rm for backward compat
_LOG_RE_OLD = re.compile(
    r"raw_thr=(?P<raw_thr>-?[\d.]+)\s+"
    r"thr=(?P<thr>-?[\d.]+)\s+"
    r"str=(?P<steer>-?[\d.]+)\s+"
    r"arm_ch=(?P<arm_ch>-?[\d.]+)\s+"
    r"armed=(?P<armed>\w+)"
)

MAX_POINTS = 300  # 5 minutes at 1Hz


@dataclass
class TelemetryBuffer:
    timestamps: deque[float] = field(default_factory=lambda: deque(maxlen=MAX_POINTS))
    raw_thr: deque[float] = field(default_factory=lambda: deque(maxlen=MAX_POINTS))
    thr: deque[float] = field(default_factory=lambda: deque(maxlen=MAX_POINTS))
    steer: deque[float] = field(default_factory=lambda: deque(maxlen=MAX_POINTS))
    left_motor: deque[float] = field(default_factory=lambda: deque(maxlen=MAX_POINTS))
    right_motor: deque[float] = field(default_factory=lambda: deque(maxlen=MAX_POINTS))
    armed: deque[bool] = field(default_factory=lambda: deque(maxlen=MAX_POINTS))
    lock: threading.Lock = field(default_factory=threading.Lock)
    _t0: float | None = field(default=None, repr=False)

    def append(
        self,
        raw_thr: float,
        thr: float,
        steer: float,
        lm: float,
        rm: float,
        armed: bool,
    ) -> None:
        now = time.monotonic()
        with self.lock:
            if self._t0 is None:
                self._t0 = now
            self.timestamps.append(now - self._t0)
            self.raw_thr.append(raw_thr)
            self.thr.append(thr)
            self.steer.append(steer)
            self.left_motor.append(lm)
            self.right_motor.append(rm)
            self.armed.append(armed)


def _parse_line(line: str, buf: TelemetryBuffer) -> None:
    m = _LOG_RE.search(line)
    if m:
        buf.append(
            raw_thr=float(m.group("raw_thr")),
            thr=float(m.group("thr")),
            steer=float(m.group("steer")),
            lm=float(m.group("lm")),
            rm=float(m.group("rm")),
            armed=m.group("armed") == "True",
        )
        return
    m = _LOG_RE_OLD.search(line)
    if m:
        buf.append(
            raw_thr=float(m.group("raw_thr")),
            thr=float(m.group("thr")),
            steer=float(m.group("steer")),
            lm=0.0,
            rm=0.0,
            armed=m.group("armed") == "True",
        )


def _tail_logs(host: str, password: str, tail: int, buf: TelemetryBuffer) -> None:
    """SSH into robot and tail docker logs, feeding parsed data into buffer."""
    cmd = [
        "sshpass", "-p", password,
        "ssh", "-o", "StrictHostKeyChecking=no", "-o", "ServerAliveInterval=5",
        f"biba@{host}",
        f"docker logs --follow --tail {tail} biba-biba-controller-1 2>&1",
    ]
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    try:
        for line in iter(proc.stdout.readline, ""):
            _parse_line(line, buf)
    except Exception:
        pass
    finally:
        proc.kill()


def _build_figure() -> tuple[Figure, dict]:
    fig, axes = plt.subplots(3, 1, figsize=(14, 9), sharex=True)
    fig.suptitle("BiBa Telemetry", fontsize=14, fontweight="bold")
    fig.patch.set_facecolor("#1e1e1e")

    colors = {
        "raw_thr": "#ff6b6b",
        "thr": "#ffd93d",
        "steer": "#6bcbff",
        "lm": "#51cf66",
        "rm": "#cc5de8",
    }

    lines = {}
    for ax in axes:
        ax.set_facecolor("#2d2d2d")
        ax.tick_params(colors="white")
        ax.spines["bottom"].set_color("#555")
        ax.spines["left"].set_color("#555")
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.set_ylim(-1.15, 1.15)
        ax.axhline(0, color="#555", linewidth=0.5)
        ax.grid(True, alpha=0.2, color="white")

    # Ax 0: Throttle input
    ax0 = axes[0]
    ax0.set_ylabel("Throttle", color="white")
    (lines["raw_thr"],) = ax0.plot([], [], color=colors["raw_thr"], linewidth=1.5, label="raw_thr (stick)")
    (lines["thr"],) = ax0.plot([], [], color=colors["thr"], linewidth=1.5, label="thr (filtered)")
    ax0.legend(loc="upper right", fontsize=8, facecolor="#2d2d2d", edgecolor="#555", labelcolor="white")

    # Ax 1: Steering
    ax1 = axes[1]
    ax1.set_ylabel("Steering", color="white")
    (lines["steer"],) = ax1.plot([], [], color=colors["steer"], linewidth=1.5, label="steering")
    ax1.legend(loc="upper right", fontsize=8, facecolor="#2d2d2d", edgecolor="#555", labelcolor="white")

    # Ax 2: Motor duty (post-ramp PWM)
    ax2 = axes[2]
    ax2.set_ylabel("Motor Duty", color="white")
    ax2.set_xlabel("Time (s)", color="white")
    (lines["lm"],) = ax2.plot([], [], color=colors["lm"], linewidth=1.5, label="left motor")
    (lines["rm"],) = ax2.plot([], [], color=colors["rm"], linewidth=1.5, linestyle="--", label="right motor")
    ax2.legend(loc="upper right", fontsize=8, facecolor="#2d2d2d", edgecolor="#555", labelcolor="white")

    fig.tight_layout()
    return fig, {"axes": axes, "lines": lines}


def _animate(frame: int, buf: TelemetryBuffer, parts: dict) -> list:
    with buf.lock:
        ts = list(buf.timestamps)
        raw_thr = list(buf.raw_thr)
        thr = list(buf.thr)
        steer = list(buf.steer)
        lm = list(buf.left_motor)
        rm = list(buf.right_motor)

    if not ts:
        return []

    lines = parts["lines"]
    axes = parts["axes"]

    lines["raw_thr"].set_data(ts, raw_thr)
    lines["thr"].set_data(ts, thr)
    lines["steer"].set_data(ts, steer)
    lines["lm"].set_data(ts, lm)
    lines["rm"].set_data(ts, rm)

    # Auto-scroll X axis: show last 60 seconds
    xmax = ts[-1]
    xmin = max(0, xmax - 60)
    for ax in axes:
        ax.set_xlim(xmin, xmax + 1)

    return list(lines.values())


def main() -> None:
    parser = argparse.ArgumentParser(description="BiBa live telemetry monitor")
    parser.add_argument("--host", default="192.168.2.185", help="Robot IP")
    parser.add_argument("--password", default="open", help="SSH password")
    parser.add_argument("--tail", type=int, default=120, help="Initial log lines to load")
    args = parser.parse_args()

    buf = TelemetryBuffer()

    # Start log reader in background thread
    reader = threading.Thread(
        target=_tail_logs,
        args=(args.host, args.password, args.tail, buf),
        daemon=True,
    )
    reader.start()

    # Build plot
    fig, parts = _build_figure()
    _ = animation.FuncAnimation(
        fig,
        _animate,
        fargs=(buf, parts),
        interval=200,  # refresh every 200ms
        blit=False,
        cache_frame_data=False,
    )

    print(f"Monitoring BiBa at {args.host} — close the window to stop")
    try:
        plt.show()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
