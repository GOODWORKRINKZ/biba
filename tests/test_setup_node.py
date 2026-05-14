from __future__ import annotations

from pathlib import Path


def test_setup_node_service_does_not_pull_images_on_boot() -> None:
    script = Path("scripts/setup/setup_node.sh").read_text(encoding="utf-8")

    assert "ExecStartPre=/usr/bin/docker compose pull --ignore-pull-failures" not in script
    assert "ExecStart=/usr/bin/docker compose up -d" in script
    assert "ExecStop=/usr/bin/docker compose down" in script


def test_setup_node_service_uses_docker_legacy_pi_compose_path() -> None:
    script = Path("scripts/setup/setup_node.sh").read_text(encoding="utf-8")

    assert "WorkingDirectory=$REPO_DIR/docker/legacy-pi" in script