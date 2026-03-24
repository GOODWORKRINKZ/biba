#!/bin/bash

set -euo pipefail

BIBA_DIR="${BIBA_DIR:-$HOME/biba}"

echo "=== Updating BiBa ==="

echo "Pulling latest code..."
git -C "$BIBA_DIR" pull --ff-only

echo "Pulling latest image..."
docker compose -f "$BIBA_DIR/docker-compose.yml" pull

echo "Restarting stack..."
docker compose -f "$BIBA_DIR/docker-compose.yml" up -d

echo
echo "=== Current image ==="
docker compose -f "$BIBA_DIR/docker-compose.yml" images

echo
echo "=== Container status ==="
docker compose -f "$BIBA_DIR/docker-compose.yml" ps
