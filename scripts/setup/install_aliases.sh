#!/bin/bash

set -euo pipefail

ALIASES_FILE="$HOME/biba/scripts/biba_aliases.sh"
SHELL_CONFIG="${HOME}/.bashrc"

if [ ! -f "$ALIASES_FILE" ]; then
    echo "Aliases file not found: $ALIASES_FILE"
    exit 1
fi

if grep -q "biba_aliases.sh" "$SHELL_CONFIG" 2>/dev/null; then
    echo "BiBa aliases already installed in $SHELL_CONFIG"
    exit 0
fi

cat >> "$SHELL_CONFIG" <<'EOF'

# BiBa aliases
if [ -f ~/biba/scripts/biba_aliases.sh ]; then
    source ~/biba/scripts/biba_aliases.sh
fi
EOF

echo "BiBa aliases installed into $SHELL_CONFIG"
echo "Run: source $SHELL_CONFIG"
