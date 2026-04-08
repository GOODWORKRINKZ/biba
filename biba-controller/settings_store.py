from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from threading import Lock


def clamp_motor_trim(trim: float, *, max_effect: float) -> float:
    return max(-max_effect, min(max_effect, float(trim)))


def load_motor_trim(settings_path: str | Path, *, max_effect: float) -> float:
    path = Path(settings_path)
    if not path.exists():
        return 0.0

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        trim = float(payload.get("trim", 0.0))
    except Exception:
        return 0.0

    return clamp_motor_trim(trim, max_effect=max_effect)


def save_motor_trim(settings_path: str | Path, trim: float, *, max_effect: float, updated_at: float | None = None) -> float:
    clamped_trim = clamp_motor_trim(trim, max_effect=max_effect)
    path = Path(settings_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f"{path.name}.tmp")
    payload = {
        "trim": clamped_trim,
        "updated_at": time.time() if updated_at is None else updated_at,
    }
    temp_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(temp_path, path)
    return clamped_trim


@dataclass(frozen=True)
class MotorTrimStatus:
    current: float
    pending: float | None
    applied_revision: int
    pending_revision: int | None
    armed: bool
    trim_mode_active: bool
    live_value: float | None
    last_error: str | None


class MotorTrimStore:
    def __init__(
        self,
        *,
        settings_path: str | Path,
        max_effect: float,
        current: float | None = None,
    ) -> None:
        self._settings_path = Path(settings_path)
        self._max_effect = float(max_effect)
        self._current = clamp_motor_trim(0.0 if current is None else current, max_effect=self._max_effect)
        self._pending: float | None = None
        self._applied_revision = 0
        self._pending_revision: int | None = None
        self._armed = False
        self._trim_mode_active = False
        self._live_value: float | None = None
        self._last_error: str | None = None
        self._lock = Lock()

    def set_armed(self, armed: bool) -> None:
        with self._lock:
            self._armed = armed

    def set_live_state(self, *, trim_mode_active: bool, live_value: float | None) -> None:
        with self._lock:
            self._trim_mode_active = trim_mode_active
            self._live_value = None if live_value is None else clamp_motor_trim(live_value, max_effect=self._max_effect)

    def snapshot_status(self) -> MotorTrimStatus:
        with self._lock:
            return MotorTrimStatus(
                current=self._current,
                pending=self._pending,
                applied_revision=self._applied_revision,
                pending_revision=self._pending_revision,
                armed=self._armed,
                trim_mode_active=self._trim_mode_active,
                live_value=self._live_value,
                last_error=self._last_error,
            )

    def request_update(self, trim: float) -> int:
        with self._lock:
            if self._armed:
                self._last_error = "Изменять трим моторов можно только когда платформа разоружена"
                raise RuntimeError(self._last_error)
            clamped_trim = save_motor_trim(self._settings_path, trim, max_effect=self._max_effect)
            next_revision = max(self._applied_revision, self._pending_revision or 0) + 1
            self._pending = clamped_trim
            self._pending_revision = next_revision
            self._last_error = None
            return next_revision

    def consume_pending_update(self) -> tuple[int, float] | None:
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

    def sync_current(self, trim: float, *, persist: bool = False) -> int:
        with self._lock:
            clamped_trim = (
                save_motor_trim(self._settings_path, trim, max_effect=self._max_effect)
                if persist
                else clamp_motor_trim(trim, max_effect=self._max_effect)
            )
            next_revision = max(self._applied_revision, self._pending_revision or 0) + 1
            self._current = clamped_trim
            self._pending = None
            self._pending_revision = None
            self._applied_revision = next_revision
            self._last_error = None
            return next_revision

    def record_apply_error(self, message: str) -> None:
        with self._lock:
            self._last_error = message