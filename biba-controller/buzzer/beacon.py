"""Beacon manager — automatic SOS after prolonged connection loss."""

from __future__ import annotations

import logging

LOGGER = logging.getLogger("biba-controller")


class BeaconManager:
    """Track failsafe duration and decide when to emit an SOS beacon.

    The beacon activates after *delay_s* seconds of continuous failsafe.
    It can also be force-enabled via an RC channel (manual toggle).
    """

    def __init__(self, delay_s: float, enabled: bool = True) -> None:
        self.delay_s = delay_s
        self.enabled = enabled
        self._failsafe_since: float | None = None
        self._manual_on = False
        self._last_sos_at = -9999.0  # allow first SOS immediately
        self._sos_interval = 8.0  # seconds between SOS repeats

    # ------------------------------------------------------------------
    # State updates (called from main loop)
    # ------------------------------------------------------------------

    def on_failsafe(self, now: float) -> None:
        """Call every loop iteration while failsafe is active."""
        if self._failsafe_since is None:
            self._failsafe_since = now

    def on_connected(self) -> None:
        """Call when valid CRSF frames are being received."""
        self._failsafe_since = None

    def set_manual(self, active: bool) -> None:
        """Set manual beacon toggle from RC channel."""
        self._manual_on = active

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def should_sos(self, now: float) -> bool:
        """Return True when the buzzer should play the SOS melody now."""
        if not self.enabled:
            return False

        auto_active = (
            self._failsafe_since is not None
            and (now - self._failsafe_since) >= self.delay_s
        )

        if not (auto_active or self._manual_on):
            return False

        if now - self._last_sos_at >= self._sos_interval:
            self._last_sos_at = now
            if auto_active:
                elapsed = now - self._failsafe_since
                LOGGER.info("SOS beacon (auto) — no link for %.0fs", elapsed)
            else:
                LOGGER.info("SOS beacon (manual toggle)")
            return True

        return False
