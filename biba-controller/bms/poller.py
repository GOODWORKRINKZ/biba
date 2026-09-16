"""Background-threaded BMS poller to avoid blocking the control loop."""

from __future__ import annotations

import logging
import threading
import time
from typing import Protocol

from bms.daly import BatteryState

LOGGER = logging.getLogger(__name__)


class BMSReader(Protocol):
    def read_state(self) -> BatteryState | None: ...


class BMSPoller:
    """Poll a BMS in a background thread, exposing the latest state."""

    def __init__(self, bms: BMSReader, interval_s: float = 1.0) -> None:
        self._bms = bms
        self._interval = interval_s
        self._state: BatteryState | None = None
        self._state_timestamp_s: float | None = None
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def latest_state(self) -> BatteryState | None:
        with self._lock:
            return self._state

    @property
    def latest_state_timestamp_s(self) -> float | None:
        with self._lock:
            return self._state_timestamp_s

    def start(self) -> None:
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=5.0)
            self._thread = None

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                state = self._bms.read_state()
                polled_at_s = time.monotonic()
                with self._lock:
                    self._state = state
                    self._state_timestamp_s = polled_at_s
            except Exception as exc:  # noqa: BLE001 -- polling loop must survive any driver error
                with self._lock:
                    self._state = None
                    self._state_timestamp_s = None
                LOGGER.warning("BMS poll failed: %s", exc)
            self._stop_event.wait(self._interval)
