from __future__ import annotations

from pathlib import Path


def test_biba_compose_loads_robot_env_file_when_present() -> None:
    aliases = Path("scripts/biba_aliases.sh").read_text(encoding="utf-8")

    assert 'BIBA_ENV_FILE="${BIBA_ENV_FILE:-/etc/default/biba-controller}"' in aliases
    assert '--env-file "$BIBA_ENV_FILE"' in aliases
    assert "docker compose" in aliases


def test_biba_aliases_use_docker_legacy_pi_compose_path() -> None:
    aliases = Path("scripts/biba_aliases.sh").read_text(encoding="utf-8")

    assert 'BIBA_COMPOSE_FILE="${BIBA_COMPOSE_FILE:-$BIBA_DIR/docker/legacy-pi/docker-compose.yml}"' in aliases
    assert '"$BIBA_DIR/docker-compose.yml"' not in aliases
    assert '-f "$BIBA_COMPOSE_FILE"' in aliases


def test_bbupdate_force_recreates_container() -> None:
    aliases = Path("scripts/biba_aliases.sh").read_text(encoding="utf-8")

    assert "alias bbupdate=" in aliases
    assert "_biba_compose up -d --force-recreate" in aliases


def test_update_script_loads_robot_env_file_when_present() -> None:
    script = Path("scripts/update.sh").read_text(encoding="utf-8")

    assert 'BIBA_ENV_FILE="${BIBA_ENV_FILE:-/etc/default/biba-controller}"' in script
    assert '--env-file "$BIBA_ENV_FILE"' in script
    assert "_biba_compose pull" in script
    assert "_biba_compose up -d" in script


def test_diagnostics_script_loads_robot_env_file_when_present() -> None:
    script = Path("scripts/diagnostics.sh").read_text(encoding="utf-8")

    assert 'BIBA_ENV_FILE="${BIBA_ENV_FILE:-/etc/default/biba-controller}"' in script
    assert '--env-file "$BIBA_ENV_FILE"' in script
    assert "_biba_compose ps" in script
    assert "_biba_compose logs --tail 30" in script


def test_update_script_uses_docker_legacy_pi_compose_path() -> None:
    script = Path("scripts/update.sh").read_text(encoding="utf-8")

    assert 'BIBA_COMPOSE_FILE="${BIBA_COMPOSE_FILE:-$BIBA_DIR/docker/legacy-pi/docker-compose.yml}"' in script
    assert '"$BIBA_DIR/docker-compose.yml"' not in script
    assert '-f "$BIBA_COMPOSE_FILE"' in script


def test_diagnostics_script_uses_docker_legacy_pi_compose_path() -> None:
    script = Path("scripts/diagnostics.sh").read_text(encoding="utf-8")

    assert 'BIBA_COMPOSE_FILE="${BIBA_COMPOSE_FILE:-$BIBA_DIR/docker/legacy-pi/docker-compose.yml}"' in script
    assert '"$BIBA_DIR/docker-compose.yml"' not in script
    assert '-f "$BIBA_COMPOSE_FILE"' in script


def test_biba_stack_env_var_selects_compose_file() -> None:
    aliases = Path("scripts/biba_aliases.sh").read_text(encoding="utf-8")

    # BIBA_STACK with default 'legacy'.
    assert 'BIBA_STACK="${BIBA_STACK:-legacy}"' in aliases
    # ros2 case maps to docker/ros2/ + /etc/default/biba-ros2.
    assert 'BIBA_ENV_FILE:-/etc/default/biba-ros2' in aliases
    assert 'BIBA_COMPOSE_FILE:-$BIBA_DIR/docker/ros2/docker-compose.yml' in aliases
    # Both branches must still respect explicit overrides.
    assert 'BIBA_ENV_FILE="${BIBA_ENV_FILE:-/etc/default/biba-controller}"' in aliases
    assert 'BIBA_COMPOSE_FILE="${BIBA_COMPOSE_FILE:-$BIBA_DIR/docker/legacy-pi/docker-compose.yml}"' in aliases


def test_bbstack_alias_prints_active_stack() -> None:
    aliases = Path("scripts/biba_aliases.sh").read_text(encoding="utf-8")

    assert "alias bbstack=" in aliases
    assert "BIBA_STACK=" in aliases
    assert "BIBA_COMPOSE_FILE=" in aliases