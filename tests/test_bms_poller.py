"""Tests for the threaded BMS poller."""

from __future__ import annotations

import time
from typing import Optional

from bms.daly import BatteryState
from bms.poller import BMSPoller


def _make_state(voltage: float = 24.0) -> BatteryState:
    return BatteryState(
        voltage=voltage,
        current=1.0,
        soc=80.0,
        cells=[4.0, 4.0, 4.0],
        temperatures=[25.0],
        min_cell=4.0,
        max_cell=4.0,
        delta=0.0,
    )


class FakeBMS:
    def __init__(self, state: Optional[BatteryState] = None) -> None:
        self.state = state
        self.call_count = 0
        self.delay = 0.0

    def read_state(self) -> Optional[BatteryState]:
        self.call_count += 1
        if self.delay:
            time.sleep(self.delay)
        return self.state


def test_poller_returns_none_before_first_poll() -> None:
    bms = FakeBMS()
    poller = BMSPoller(bms, interval_s=10.0)

    assert poller.latest_state is None


def test_poller_caches_latest_state() -> None:
    state = _make_state(25.5)
    bms = FakeBMS(state)
    poller = BMSPoller(bms, interval_s=0.01)
    poller.start()

    deadline = time.monotonic() + 2.0
    while poller.latest_state is None and time.monotonic() < deadline:
        time.sleep(0.01)
    poller.stop()

    assert poller.latest_state is not None
    assert poller.latest_state.voltage == 25.5
    assert poller.latest_state_timestamp_s is not None


def test_poller_updates_timestamp_after_successful_poll() -> None:
    state = _make_state(25.5)
    bms = FakeBMS(state)
    poller = BMSPoller(bms, interval_s=0.01)

    assert poller.latest_state_timestamp_s is None

    poller.start()
    deadline = time.monotonic() + 2.0
    while poller.latest_state_timestamp_s is None and time.monotonic() < deadline:
        time.sleep(0.01)
    poller.stop()

    assert poller.latest_state_timestamp_s is not None


def test_poller_clears_timestamp_after_read_exception() -> None:
    state = _make_state(25.5)

    class FlakyBMS:
        def __init__(self) -> None:
            self.call_count = 0

        def read_state(self) -> Optional[BatteryState]:
            self.call_count += 1
            if self.call_count == 1:
                return state
            raise OSError("BLE timeout")

    poller = BMSPoller(FlakyBMS(), interval_s=0.01)
    poller.start()

    deadline = time.monotonic() + 2.0
    observed_timestamp = False
    observed_clear = False
    while time.monotonic() < deadline:
        latest_timestamp = poller.latest_state_timestamp_s
        if latest_timestamp is not None:
            observed_timestamp = True
        if observed_timestamp and latest_timestamp is None:
            observed_clear = True
            break
        time.sleep(0.01)

    poller.stop()

    assert observed_timestamp is True
    assert observed_clear is True


def test_poller_does_not_block_caller() -> None:
    bms = FakeBMS(_make_state())
    bms.delay = 0.5  # simulate slow BMS
    poller = BMSPoller(bms, interval_s=0.01)
    poller.start()

    t0 = time.monotonic()
    _ = poller.latest_state  # must return instantly
    elapsed = time.monotonic() - t0
    poller.stop()

    assert elapsed < 0.05


def test_poller_handles_bms_exception() -> None:
    class BrokenBMS:
        def read_state(self):
            raise OSError("UART error")

    poller = BMSPoller(BrokenBMS(), interval_s=0.01)
    poller.start()
    time.sleep(0.1)
    poller.stop()

    # Should not crash, state stays None
    assert poller.latest_state is None


def test_poller_stop_is_idempotent() -> None:
    bms = FakeBMS()
    poller = BMSPoller(bms, interval_s=1.0)
    poller.start()
    poller.stop()
    poller.stop()  # must not raise


def test_poller_clears_latest_state_after_read_exception() -> None:
    state = _make_state(25.5)

    class FlakyBMS:
        def __init__(self) -> None:
            self.call_count = 0

        def read_state(self) -> Optional[BatteryState]:
            self.call_count += 1
            if self.call_count == 1:
                return state
            raise OSError("BLE timeout")

    poller = BMSPoller(FlakyBMS(), interval_s=0.01)
    poller.start()

    deadline = time.monotonic() + 2.0
    observed_state = False
    observed_clear = False
    while time.monotonic() < deadline:
        latest_state = poller.latest_state
        if latest_state is not None and latest_state.voltage == 25.5:
            observed_state = True
        if observed_state and latest_state is None:
            observed_clear = True
            break
        time.sleep(0.01)

    poller.stop()

    assert observed_state is True
    assert observed_clear is True
