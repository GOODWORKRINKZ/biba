from __future__ import annotations

import json

import pytest

from settings_store import MotorTrimStore, load_motor_trim


def test_load_motor_trim_defaults_to_zero_when_file_is_missing(tmp_path) -> None:
    trim = load_motor_trim(tmp_path / "motor-trim.json", max_effect=0.3)

    assert trim == pytest.approx(0.0)


def test_load_motor_trim_clamps_saved_value_to_max_effect(tmp_path) -> None:
    settings_path = tmp_path / "motor-trim.json"
    settings_path.write_text(json.dumps({"trim": 0.8}), encoding="utf-8")

    trim = load_motor_trim(settings_path, max_effect=0.3)

    assert trim == pytest.approx(0.3)


def test_motor_trim_store_rejects_updates_while_armed(tmp_path) -> None:
    store = MotorTrimStore(settings_path=tmp_path / "motor-trim.json", max_effect=0.3)
    store.set_armed(True)

    with pytest.raises(RuntimeError, match="disarmed"):
        store.request_update(0.15)

    status = store.snapshot_status()
    assert status.current == pytest.approx(0.0)
    assert status.pending is None
    assert status.pending_revision is None


def test_motor_trim_store_persists_pending_update_and_marks_it_applied(tmp_path) -> None:
    settings_path = tmp_path / "motor-trim.json"
    store = MotorTrimStore(settings_path=settings_path, max_effect=0.3)

    revision = store.request_update(0.12)

    pending_revision, pending_trim = store.consume_pending_update()
    assert pending_revision == revision
    assert pending_trim == pytest.approx(0.12)

    payload = json.loads(settings_path.read_text(encoding="utf-8"))
    assert payload["trim"] == pytest.approx(0.12)

    store.mark_applied(revision)
    status = store.snapshot_status()
    assert status.current == pytest.approx(0.12)
    assert status.pending is None
    assert status.applied_revision == 1
    assert status.pending_revision is None


def test_motor_trim_store_tracks_trim_mode_live_state(tmp_path) -> None:
    store = MotorTrimStore(settings_path=tmp_path / "motor-trim.json", max_effect=0.3)

    store.set_live_state(trim_mode_active=True, live_value=-0.08)

    status = store.snapshot_status()
    assert status.trim_mode_active is True
    assert status.live_value == pytest.approx(-0.08)


def test_motor_trim_store_sync_current_persists_external_trim_save(tmp_path) -> None:
    settings_path = tmp_path / "motor-trim.json"
    store = MotorTrimStore(settings_path=settings_path, max_effect=0.3)

    store.sync_current(-0.18, persist=True)

    status = store.snapshot_status()
    assert status.current == pytest.approx(-0.18)
    assert status.pending is None
    assert status.applied_revision == 1

    payload = json.loads(settings_path.read_text(encoding="utf-8"))
    assert payload["trim"] == pytest.approx(-0.18)


def test_motor_trim_store_records_apply_error_without_losing_pending_update(tmp_path) -> None:
    store = MotorTrimStore(settings_path=tmp_path / "motor-trim.json", max_effect=0.3)
    store.request_update(0.1)

    store.record_apply_error("boom")

    status = store.snapshot_status()
    assert status.pending == pytest.approx(0.1)
    assert status.pending_revision == 1
    assert status.last_error == "boom"