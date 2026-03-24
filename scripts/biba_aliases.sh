#!/bin/bash

BIBA_DIR="${BIBA_DIR:-$HOME/biba}"

_biba_compose() {
    docker compose -f "$BIBA_DIR/docker-compose.yml" "$@"
}

alias bbcd='cd "$BIBA_DIR"'
alias bbstatus='_biba_compose ps'
alias bblogs='_biba_compose logs -f'
alias bbpull='_biba_compose pull'
alias bbstart='_biba_compose up -d'
alias bbstop='_biba_compose down'
alias bbrestart='_biba_compose down && _biba_compose up -d'
alias bbupdate='cd "$BIBA_DIR" && git pull --ff-only && _biba_compose pull && _biba_compose up -d'
alias bbhealth='docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Image}}"'
