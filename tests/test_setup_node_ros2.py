"""Structural tests for the ROS2 composition C bringup script."""

from __future__ import annotations

from pathlib import Path

import pytest


SCRIPT = Path("scripts/setup/setup_node_ros2.sh")


@pytest.fixture(scope="module")
def script_text() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def test_script_exists_and_is_executable() -> None:
    assert SCRIPT.is_file(), f"missing {SCRIPT}"
    mode = SCRIPT.stat().st_mode & 0o111
    assert mode != 0, f"{SCRIPT} must be executable"


def test_script_uses_strict_bash(script_text: str) -> None:
    assert script_text.splitlines()[0].startswith("#!/bin/bash")
    assert "set -euo pipefail" in script_text


def test_script_targets_ros2_compose_path(script_text: str) -> None:
    assert "docker/ros2" in script_text
    # Must not silently start the legacy stack.
    assert "docker/legacy-pi" not in script_text


def test_script_enables_spi_overlay(script_text: str) -> None:
    # Bridge node mounts /dev/spidev0.0 — we need to ensure the overlay
    # is on before docker compose up.
    assert "dtparam=spi=on" in script_text or "raspi-config" in script_text


def test_script_writes_systemd_unit(script_text: str) -> None:
    assert 'SERVICE_NAME="biba-ros2"' in script_text
    assert "/etc/systemd/system/${SERVICE_NAME}.service" in script_text
    assert "ExecStart=/usr/bin/docker compose up -d" in script_text
    assert "ExecStop=/usr/bin/docker compose down" in script_text


def test_script_does_not_pull_on_boot(script_text: str) -> None:
    # Same policy as legacy: pull is a manual step (or via aliases),
    # never on every boot — keeps the unit fast and offline-safe.
    assert "ExecStartPre=/usr/bin/docker compose pull" not in script_text


def test_script_supports_dry_run_flag(script_text: str) -> None:
    # --dry-run must be accepted so the script can be exercised in CI
    # without touching the system.
    assert "--dry-run" in script_text or "DRY_RUN" in script_text
