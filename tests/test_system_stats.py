from __future__ import annotations

from io import StringIO
from unittest.mock import patch

from system_stats import SystemStats


def test_cpu_percent_returns_percentage() -> None:
    stats = SystemStats()
    line1 = "cpu  100 0 0 900 0 0 0 0 0 0\n"
    line2 = "cpu  300 0 0 1700 0 0 0 0 0 0\n"

    with patch("builtins.open", return_value=StringIO(line1)):
        stats.cpu_percent()  # baseline

    with patch("builtins.open", return_value=StringIO(line2)):
        result = stats.cpu_percent()

    # d_total = 2000-1000 = 1000, d_idle = 1700-900 = 800
    # cpu = (1 - 800/1000) * 100 = 20.0%
    assert abs(result - 20.0) < 0.1


def test_cpu_percent_first_call_returns_zero() -> None:
    stats = SystemStats()
    line = "cpu  0 0 0 0 0 0 0 0 0 0\n"

    with patch("builtins.open", return_value=StringIO(line)):
        result = stats.cpu_percent()

    assert result == 0.0


def test_cpu_percent_handles_missing_proc() -> None:
    stats = SystemStats()

    with patch("builtins.open", side_effect=OSError("No such file")):
        assert stats.cpu_percent() == 0.0


def test_memory_percent_returns_percentage() -> None:
    meminfo = (
        "MemTotal:       1000000 kB\n"
        "MemFree:         200000 kB\n"
        "MemAvailable:    400000 kB\n"
    )

    with patch("builtins.open", return_value=StringIO(meminfo)):
        result = SystemStats.memory_percent()

    assert abs(result - 60.0) < 0.1


def test_memory_percent_falls_back_to_memfree() -> None:
    meminfo = "MemTotal:       1000000 kB\nMemFree:         300000 kB\n"

    with patch("builtins.open", return_value=StringIO(meminfo)):
        result = SystemStats.memory_percent()

    assert abs(result - 70.0) < 0.1


def test_memory_percent_handles_missing_proc() -> None:
    with patch("builtins.open", side_effect=OSError("No such file")):
        assert SystemStats.memory_percent() == 0.0
