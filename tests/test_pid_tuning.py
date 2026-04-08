from __future__ import annotations

import json
from dataclasses import replace

import pytest

from pid_tuning import PidTuningSnapshot, PidTuningStore, load_pid_tuning, snapshot_from_mapping


def _defaults() -> PidTuningSnapshot:
    return PidTuningSnapshot(
        yaw_rate_kp=0.01,
        yaw_rate_ki=0.0,
        yaw_rate_kd=0.001,
        yaw_rate_deadband_dps=4.0,
        yaw_rate_filter_hz=5.0,
        stabilization_min_throttle=0.1,
        neutral_stabilization_steering_limit=0.12,
        neutral_stabilization_max_throttle=0.25,
    )


def test_snapshot_from_mapping_merges_with_defaults() -> None:
    snapshot = snapshot_from_mapping(
        {
            "yaw_rate_kp": 0.02,
            "yaw_rate_filter_hz": 3.0,
        },
        defaults=_defaults(),
    )

    assert snapshot.yaw_rate_kp == pytest.approx(0.02)
    assert snapshot.yaw_rate_filter_hz == pytest.approx(3.0)
    assert snapshot.yaw_rate_kd == pytest.approx(0.001)
    assert snapshot.neutral_stabilization_steering_limit == pytest.approx(0.12)


def test_snapshot_from_mapping_rejects_invalid_ranges() -> None:
    with pytest.raises(ValueError, match="neutral_stabilization_max_throttle"):
        snapshot_from_mapping(
            {
                "stabilization_min_throttle": 0.2,
                "neutral_stabilization_max_throttle": 0.1,
            },
            defaults=_defaults(),
        )


def test_load_pid_tuning_returns_defaults_when_settings_file_is_missing(tmp_path) -> None:
    snapshot = load_pid_tuning(tmp_path / "pid-tuning.json", defaults=_defaults())

    assert snapshot == _defaults()


def test_load_pid_tuning_merges_saved_values_over_defaults(tmp_path) -> None:
    settings_path = tmp_path / "pid-tuning.json"
    settings_path.write_text(
        json.dumps(
            {
                "values": {
                    "yaw_rate_kp": 0.02,
                    "yaw_rate_filter_hz": 3.5,
                }
            }
        ),
        encoding="utf-8",
    )

    snapshot = load_pid_tuning(settings_path, defaults=_defaults())

    assert snapshot.yaw_rate_kp == pytest.approx(0.02)
    assert snapshot.yaw_rate_filter_hz == pytest.approx(3.5)
    assert snapshot.yaw_rate_kd == pytest.approx(0.001)


def test_load_pid_tuning_returns_defaults_for_invalid_saved_values(tmp_path) -> None:
    settings_path = tmp_path / "pid-tuning.json"
    settings_path.write_text(
        json.dumps(
            {
                "values": {
                    "yaw_rate_kp": -1.0,
                }
            }
        ),
        encoding="utf-8",
    )

    snapshot = load_pid_tuning(settings_path, defaults=_defaults())

    assert snapshot == _defaults()


def test_pid_tuning_store_rejects_updates_while_armed(tmp_path) -> None:
    settings_path = tmp_path / "pid-tuning.json"
    store = PidTuningStore(settings_path=settings_path, defaults=_defaults())
    store.set_armed(True)

    with pytest.raises(RuntimeError, match="disarmed"):
        store.request_update(replace(_defaults(), yaw_rate_kp=0.02))

    status = store.snapshot_status()
    assert status.pending_revision is None
    assert status.pending is None
    assert not settings_path.exists()


def test_pid_tuning_store_persists_and_applies_pending_updates(tmp_path) -> None:
    settings_path = tmp_path / "pid-tuning.json"
    store = PidTuningStore(settings_path=settings_path, defaults=_defaults())
    updated = replace(_defaults(), yaw_rate_kp=0.02, yaw_rate_filter_hz=3.0)

    revision = store.request_update(updated)

    pending_revision, pending_snapshot = store.consume_pending_update()
    assert pending_revision == revision
    assert pending_snapshot == updated

    payload = json.loads(settings_path.read_text(encoding="utf-8"))
    assert payload["values"]["yaw_rate_kp"] == pytest.approx(0.02)
    assert payload["values"]["yaw_rate_filter_hz"] == pytest.approx(3.0)

    store.mark_applied(revision)
    status = store.snapshot_status()
    assert status.current == updated
    assert status.pending is None
    assert status.applied_revision == revision
    assert status.pending_revision is None