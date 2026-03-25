"""System resource monitoring for Raspberry Pi."""

from __future__ import annotations


class SystemStats:
    """Read CPU and memory usage from /proc."""

    def __init__(self) -> None:
        self._prev_idle = 0
        self._prev_total = 0

    def cpu_percent(self) -> float:
        """Return CPU usage as a percentage (0-100).

        Requires two consecutive calls to produce a meaningful delta.
        The first call establishes the baseline and returns 0.0.
        """
        try:
            with open("/proc/stat") as f:
                line = f.readline()
        except OSError:
            return 0.0

        parts = line.split()
        if parts[0] != "cpu" or len(parts) < 5:
            return 0.0

        values = [int(x) for x in parts[1:]]
        idle = values[3]
        total = sum(values)

        d_idle = idle - self._prev_idle
        d_total = total - self._prev_total
        self._prev_idle = idle
        self._prev_total = total

        if d_total == 0:
            return 0.0
        return round((1.0 - d_idle / d_total) * 100.0, 1)

    @staticmethod
    def memory_percent() -> float:
        """Return memory usage as a percentage (0-100)."""
        try:
            with open("/proc/meminfo") as f:
                lines = f.readlines()
        except OSError:
            return 0.0

        info: dict[str, int] = {}
        for line in lines:
            parts = line.split()
            if len(parts) >= 2:
                info[parts[0].rstrip(":")] = int(parts[1])

        total = info.get("MemTotal", 0)
        available = info.get("MemAvailable", info.get("MemFree", 0))
        if total == 0:
            return 0.0
        return round((1.0 - available / total) * 100.0, 1)
