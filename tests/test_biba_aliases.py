from __future__ import annotations

from pathlib import Path


def test_biba_compose_loads_robot_env_file_when_present() -> None:
    aliases = Path("scripts/biba_aliases.sh").read_text(encoding="utf-8")

    assert 'BIBA_ENV_FILE="${BIBA_ENV_FILE:-/etc/default/biba-controller}"' in aliases
    assert '--env-file "$BIBA_ENV_FILE"' in aliases
    assert "docker compose" in aliases


def test_bbupdate_force_recreates_container() -> None:
    aliases = Path("scripts/biba_aliases.sh").read_text(encoding="utf-8")

    assert "alias bbupdate=" in aliases
    assert "_biba_compose up -d --force-recreate" in aliases