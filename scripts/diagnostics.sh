#!/bin/bash

set -euo pipefail

BIBA_DIR="${BIBA_DIR:-$HOME/biba}"

GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
NC='\033[0m'

section() {
    echo
    echo -e "${CYAN}=== $1 ===${NC}"
}

section "Docker"
docker --version 2>/dev/null || echo "Docker not installed"
docker compose version 2>/dev/null || echo "Compose not available"

section "Container Status"
docker compose -f "$BIBA_DIR/docker-compose.yml" ps 2>/dev/null || echo "Compose stack not running"

section "Container Images"
docker compose -f "$BIBA_DIR/docker-compose.yml" images 2>/dev/null || true

section "Recent Logs (last 30 lines)"
docker compose -f "$BIBA_DIR/docker-compose.yml" logs --tail 30 2>/dev/null || echo "No logs available"

section "Host Info"
echo -e "${GREEN}Hostname:${NC} $(hostname)"
echo -e "${GREEN}Uptime:${NC} $(uptime -p 2>/dev/null || uptime)"
echo -e "${GREEN}Kernel:${NC} $(uname -r)"

section "CPU Temperature"
if [ -f /sys/class/thermal/thermal_zone0/temp ]; then
    TEMP=$(cat /sys/class/thermal/thermal_zone0/temp)
    echo "${TEMP%???}.${TEMP: -3:1}°C"
else
    echo "Not available"
fi

section "Memory"
free -h 2>/dev/null || echo "free not available"

section "Disk"
df -h / 2>/dev/null | tail -1

section "USB Devices"
lsusb 2>/dev/null || echo "lsusb not available"

section "Serial Ports"
ls -la /dev/ttyAMA0 /dev/ttyUSB* 2>/dev/null || echo "No serial devices found"

section "Git Status"
if [ -d "$BIBA_DIR/.git" ]; then
    echo -e "${GREEN}Branch:${NC} $(git -C "$BIBA_DIR" branch --show-current)"
    echo -e "${GREEN}Commit:${NC} $(git -C "$BIBA_DIR" log --oneline -1)"
    BEHIND=$(git -C "$BIBA_DIR" rev-list --count HEAD..origin/main 2>/dev/null || echo "?")
    echo -e "${GREEN}Behind origin:${NC} ${BEHIND} commits"
else
    echo "Not a git repository"
fi
