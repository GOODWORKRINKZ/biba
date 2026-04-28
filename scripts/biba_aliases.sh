#!/bin/bash

BIBA_DIR="${BIBA_DIR:-$HOME/biba}"

# BIBA_STACK selects which compose stack the bb* aliases target:
#   legacy  (default) — docker/legacy-pi/  (composition A)
#   ros2              — docker/ros2/       (composition C)
#
# Override compose path / env file directly via BIBA_COMPOSE_FILE and
# BIBA_ENV_FILE if you need a non-standard layout.
BIBA_STACK="${BIBA_STACK:-legacy}"

case "$BIBA_STACK" in
    ros2)
        BIBA_ENV_FILE="${BIBA_ENV_FILE:-/etc/default/biba-ros2}"
        BIBA_COMPOSE_FILE="${BIBA_COMPOSE_FILE:-$BIBA_DIR/docker/ros2/docker-compose.yml}"
        ;;
    legacy|*)
        BIBA_ENV_FILE="${BIBA_ENV_FILE:-/etc/default/biba-controller}"
        BIBA_COMPOSE_FILE="${BIBA_COMPOSE_FILE:-$BIBA_DIR/docker/legacy-pi/docker-compose.yml}"
        ;;
esac

_biba_compose() {
    local env_args=()

    if [ -f "$BIBA_ENV_FILE" ]; then
        env_args+=(--env-file "$BIBA_ENV_FILE")
    elif [ -f "$BIBA_DIR/.env" ]; then
        env_args+=(--env-file "$BIBA_DIR/.env")
    fi

    docker compose "${env_args[@]}" -f "$BIBA_COMPOSE_FILE" "$@"
}

alias bbcd='cd "$BIBA_DIR"'
alias bbstatus='_biba_compose ps'
alias bblogs='_biba_compose logs -f'
alias bbpull='_biba_compose pull'
alias bbstart='_biba_compose up -d'
alias bbstop='_biba_compose down'
alias bbrestart='_biba_compose down && _biba_compose up -d'
alias bbupdate='cd "$BIBA_DIR" && git pull --ff-only && _biba_compose pull && _biba_compose up -d --force-recreate'
alias bbhealth='docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Image}}"'
alias bbstack='echo "BIBA_STACK=$BIBA_STACK  BIBA_COMPOSE_FILE=$BIBA_COMPOSE_FILE  BIBA_ENV_FILE=$BIBA_ENV_FILE"'
