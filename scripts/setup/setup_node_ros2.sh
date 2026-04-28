#!/bin/bash
#
# BiBa ROS2 stack bringup (composition C).
#
# Provisions a Pi to run docker/ros2/docker-compose.yml as a systemd
# unit. Does NOT install Docker itself or clone the repository — those
# are handled by the legacy setup_node.sh (or done manually). This
# script is idempotent: re-running it overwrites the systemd unit and
# the env file with current settings.
#
# Flags:
#   --dry-run   Print every action without touching the system.
#   --no-spi    Skip enabling the SPI overlay (e.g. on dev boxes that
#               are not real Pis).
#

set -euo pipefail

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
RED='\033[0;31m'
NC='\033[0m'

REPO_DIR="${BIBA_REPO_DIR:-$HOME/biba}"
COMPOSE_DIR="$REPO_DIR/docker/ros2"
SERVICE_NAME="biba-ros2"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
ENV_FILE="/etc/default/${SERVICE_NAME}"
BOOT_CONFIG="${BIBA_BOOT_CONFIG:-/boot/firmware/config.txt}"

DRY_RUN=0
SKIP_SPI=0

log_info()    { echo -e "${CYAN}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[OK]${NC}   $1"; }
log_warn()    { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error()   { echo -e "${RED}[ERR]${NC}  $1" >&2; }

step() {
    echo
    echo -e "${BLUE}============================================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}============================================================${NC}"
}

run() {
    if [[ "$DRY_RUN" -eq 1 ]]; then
        echo -e "${YELLOW}[dry-run]${NC} $*"
    else
        eval "$@"
    fi
}

parse_args() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --dry-run) DRY_RUN=1 ;;
            --no-spi)  SKIP_SPI=1 ;;
            -h|--help)
                sed -n '3,17p' "$0"
                exit 0
                ;;
            *)
                log_error "unknown flag: $1"
                exit 2
                ;;
        esac
        shift
    done
}

check_prereqs() {
    step "Checking prerequisites"

    if [[ ! -d "$REPO_DIR/.git" ]]; then
        log_error "Repository not found at $REPO_DIR. Run setup_node.sh first or set BIBA_REPO_DIR."
        exit 1
    fi
    log_success "Repository present at $REPO_DIR"

    if [[ ! -f "$COMPOSE_DIR/docker-compose.yml" ]]; then
        log_error "Compose file missing: $COMPOSE_DIR/docker-compose.yml"
        exit 1
    fi
    log_success "Compose file: $COMPOSE_DIR/docker-compose.yml"

    if ! command -v docker >/dev/null 2>&1; then
        log_error "docker is not installed. Run scripts/setup/setup_node.sh first."
        exit 1
    fi
    if ! docker compose version >/dev/null 2>&1; then
        log_error "docker compose plugin missing."
        exit 1
    fi
    log_success "Docker available: $(docker --version)"
}

enable_spi() {
    step "Enabling SPI overlay"

    if [[ "$SKIP_SPI" -eq 1 ]]; then
        log_warn "Skipping SPI overlay (--no-spi)"
        return
    fi

    if [[ ! -f "$BOOT_CONFIG" ]]; then
        log_warn "$BOOT_CONFIG not found — not a Raspberry Pi? Skipping SPI enable."
        return
    fi

    if grep -qE '^\s*dtparam=spi=on\b' "$BOOT_CONFIG"; then
        log_success "SPI already enabled in $BOOT_CONFIG"
        return
    fi

    log_info "Appending 'dtparam=spi=on' to $BOOT_CONFIG (reboot required)"
    run "echo 'dtparam=spi=on' | sudo tee -a $BOOT_CONFIG >/dev/null"
    log_warn "Reboot the Pi for SPI changes to take effect"
}

write_env_file() {
    step "Writing runtime environment file"

    if [[ "$DRY_RUN" -eq 1 ]]; then
        echo -e "${YELLOW}[dry-run]${NC} would write $ENV_FILE"
        return
    fi

    sudo tee "$ENV_FILE" >/dev/null <<'EOF'
# Managed by scripts/setup/setup_node_ros2.sh — re-run the script to refresh.
BIBA_ROS2_IMAGE_TAG=latest
BIBA_BASE_IMAGE=ghcr.io/goodworkrinkz/biba/biba-ros2-control
BIBA_BASE_TAG=latest
ROS_DOMAIN_ID=42
ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST
BIBA_WHEEL_SEPARATION=0.30
BIBA_MAX_WHEEL_SPEED=1.0
BIBA_SETPOINT_RATE_HZ=50.0
BIBA_TELEMETRY_RATE_HZ=20.0
BIBA_CMD_VEL_TIMEOUT_SEC=0.5
EOF
    log_success "Environment file at $ENV_FILE"
}

setup_service() {
    step "Configuring systemd unit"

    local unit_body
    unit_body=$(cat <<EOF
[Unit]
Description=BiBa ROS2 stack (composition C)
After=docker.service network-online.target
Requires=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=$COMPOSE_DIR
EnvironmentFile=-$ENV_FILE
ExecStart=/usr/bin/docker compose up -d
ExecStop=/usr/bin/docker compose down
TimeoutStartSec=0

[Install]
WantedBy=multi-user.target
EOF
)

    if [[ "$DRY_RUN" -eq 1 ]]; then
        echo -e "${YELLOW}[dry-run]${NC} would write $SERVICE_FILE:"
        echo "$unit_body" | sed 's/^/    /'
        return
    fi

    echo "$unit_body" | sudo tee "$SERVICE_FILE" >/dev/null
    sudo systemctl daemon-reload
    sudo systemctl enable "${SERVICE_NAME}.service"
    log_success "systemd unit ${SERVICE_NAME}.service enabled"
}

print_summary() {
    step "ROS2 stack bringup complete"
    cat <<EOF
Repository:    $REPO_DIR
Compose file:  $COMPOSE_DIR/docker-compose.yml
Service:       ${SERVICE_NAME}.service
Env file:      $ENV_FILE

Next steps:
  1. (If SPI was just enabled) sudo reboot
  2. Login to GHCR if pulling private images:
       echo TOKEN | docker login ghcr.io -u USERNAME --password-stdin
  3. Pull images:
       sudo systemctl start ${SERVICE_NAME}.service
       (or manually: cd $COMPOSE_DIR && docker compose pull && docker compose up -d)
  4. Tail logs:
       cd $COMPOSE_DIR && docker compose logs -f biba-stm32-bridge
EOF
}

main() {
    parse_args "$@"
    check_prereqs
    enable_spi
    write_env_file
    setup_service
    print_summary
}

main "$@"
