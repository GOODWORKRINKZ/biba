from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from threading import Lock
from typing import Any, Mapping


@dataclass(frozen=True)
class PidTuningSnapshot:
    yaw_rate_kp: float
    yaw_rate_ki: float
    yaw_rate_kd: float
    yaw_rate_deadband_dps: float
    yaw_rate_filter_hz: float
    stabilization_min_throttle: float
    neutral_stabilization_steering_limit: float
    neutral_stabilization_max_throttle: float

    def to_dict(self) -> dict[str, float]:
        return asdict(self)


@dataclass(frozen=True)
class PidTuningStatus:
    current: PidTuningSnapshot
    defaults: PidTuningSnapshot
    pending: PidTuningSnapshot | None
    applied_revision: int
    pending_revision: int | None
    armed: bool
    last_error: str | None


_FIELD_NAMES = tuple(PidTuningSnapshot.__dataclass_fields__.keys())


def _require_float(mapping: Mapping[str, Any], field_name: str, default: float) -> float:
    value = mapping.get(field_name, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field_name} must be a number")
    return float(value)


def _validate_range(field_name: str, value: float, minimum: float, maximum: float) -> None:
    if value < minimum or value > maximum:
        raise ValueError(f"{field_name} must be between {minimum} and {maximum}")


def validate_pid_tuning_snapshot(snapshot: PidTuningSnapshot) -> None:
    _validate_range("yaw_rate_kp", snapshot.yaw_rate_kp, 0.0, 1.0)
    _validate_range("yaw_rate_ki", snapshot.yaw_rate_ki, 0.0, 1.0)
    _validate_range("yaw_rate_kd", snapshot.yaw_rate_kd, 0.0, 1.0)
    _validate_range("yaw_rate_deadband_dps", snapshot.yaw_rate_deadband_dps, 0.0, 45.0)
    _validate_range("yaw_rate_filter_hz", snapshot.yaw_rate_filter_hz, 0.0, 30.0)
    _validate_range("stabilization_min_throttle", snapshot.stabilization_min_throttle, 0.0, 1.0)
    _validate_range(
        "neutral_stabilization_steering_limit",
        snapshot.neutral_stabilization_steering_limit,
        0.0,
        1.0,
    )
    _validate_range(
        "neutral_stabilization_max_throttle",
        snapshot.neutral_stabilization_max_throttle,
        0.0,
        1.0,
    )
    if snapshot.neutral_stabilization_max_throttle < snapshot.stabilization_min_throttle:
        raise ValueError(
            "neutral_stabilization_max_throttle must be greater than or equal to stabilization_min_throttle"
        )


def snapshot_from_mapping(
    mapping: Mapping[str, Any],
    *,
    defaults: PidTuningSnapshot,
) -> PidTuningSnapshot:
    snapshot = PidTuningSnapshot(
        **{
            field_name: _require_float(mapping, field_name, getattr(defaults, field_name))
            for field_name in _FIELD_NAMES
        }
    )
    validate_pid_tuning_snapshot(snapshot)
    return snapshot


def load_pid_tuning(settings_path: str | Path, *, defaults: PidTuningSnapshot) -> PidTuningSnapshot:
    path = Path(settings_path)
    if not path.exists():
        return defaults

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            return defaults
        values = payload.get("values", payload)
        if not isinstance(values, dict):
            return defaults
        return snapshot_from_mapping(values, defaults=defaults)
    except Exception:
        return defaults


def save_pid_tuning(
    settings_path: str | Path,
    snapshot: PidTuningSnapshot,
    *,
    updated_at: float | None = None,
) -> None:
    validate_pid_tuning_snapshot(snapshot)
    path = Path(settings_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f"{path.name}.tmp")
    payload = {
        "values": snapshot.to_dict(),
        "updated_at": time.time() if updated_at is None else updated_at,
    }
    temp_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(temp_path, path)


class PidTuningStore:
    def __init__(
        self,
        *,
        settings_path: str | Path,
        defaults: PidTuningSnapshot,
        current: PidTuningSnapshot | None = None,
    ) -> None:
        self._settings_path = Path(settings_path)
        self._defaults = defaults
        self._current = defaults if current is None else current
        self._pending: PidTuningSnapshot | None = None
        self._applied_revision = 0
        self._pending_revision: int | None = None
        self._armed = False
        self._last_error: str | None = None
        self._lock = Lock()
        validate_pid_tuning_snapshot(self._current)

    def set_armed(self, armed: bool) -> None:
        with self._lock:
            self._armed = armed

    def snapshot_status(self) -> PidTuningStatus:
        with self._lock:
            return PidTuningStatus(
                current=self._current,
                defaults=self._defaults,
                pending=self._pending,
                applied_revision=self._applied_revision,
                pending_revision=self._pending_revision,
                armed=self._armed,
                last_error=self._last_error,
            )

    def request_update(self, snapshot: PidTuningSnapshot) -> int:
        validate_pid_tuning_snapshot(snapshot)
        with self._lock:
            if self._armed:
                self._last_error = "pid tuning changes are allowed only while disarmed"
                raise RuntimeError(self._last_error)
            save_pid_tuning(self._settings_path, snapshot)
            next_revision = max(self._applied_revision, self._pending_revision or 0) + 1
            self._pending = snapshot
            self._pending_revision = next_revision
            self._last_error = None
            return next_revision

    def consume_pending_update(self) -> tuple[int, PidTuningSnapshot] | None:
        with self._lock:
            if self._pending is None or self._pending_revision is None:
                return None
            return self._pending_revision, self._pending

    def mark_applied(self, revision: int) -> None:
        with self._lock:
            if self._pending is None or self._pending_revision != revision:
                raise ValueError(f"revision {revision} is not pending")
            self._current = self._pending
            self._applied_revision = revision
            self._pending = None
            self._pending_revision = None
            self._last_error = None

    def record_apply_error(self, message: str) -> None:
        with self._lock:
            self._last_error = message
