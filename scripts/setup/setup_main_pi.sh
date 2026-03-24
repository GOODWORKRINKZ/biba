#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SETUP_SCRIPT="$SCRIPT_DIR/setup_node.sh"

if [ -f "$SETUP_SCRIPT" ]; then
    bash "$SETUP_SCRIPT"
else
    curl -fsSL https://raw.githubusercontent.com/GOODWORKRINKZ/biba/main/scripts/setup/setup_node.sh | bash
fi
