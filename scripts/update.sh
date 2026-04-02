#!/bin/bash

set -euo pipefail

BIBA_DIR="${BIBA_DIR:-$HOME/biba}"
BIBA_ENV_FILE="${BIBA_ENV_FILE:-/etc/default/biba-controller}"

_biba_compose() {
	local env_args=()

	if [ -f "$BIBA_ENV_FILE" ]; then
		env_args+=(--env-file "$BIBA_ENV_FILE")
	elif [ -f "$BIBA_DIR/.env" ]; then
		env_args+=(--env-file "$BIBA_DIR/.env")
	fi

	docker compose "${env_args[@]}" -f "$BIBA_DIR/docker-compose.yml" "$@"
}

echo "=== Updating BiBa ==="

echo "Pulling latest code..."
git -C "$BIBA_DIR" pull --ff-only

echo "Pulling latest image..."
_biba_compose pull

echo "Restarting stack..."
_biba_compose up -d --force-recreate

echo
echo "=== Current image ==="
_biba_compose images

echo
echo "=== Container status ==="
_biba_compose ps
