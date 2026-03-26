#!/bin/bash

set -euo pipefail

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
RED='\033[0;31m'
PURPLE='\033[0;35m'
NC='\033[0m'

REPO_URL="${BIBA_REPO_URL:-https://github.com/GOODWORKRINKZ/biba.git}"
REPO_DIR="${BIBA_REPO_DIR:-$HOME/biba}"
BRANCH="${BIBA_BRANCH:-main}"
SERVICE_NAME="biba-controller"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
ENV_FILE="/etc/default/${SERVICE_NAME}"

log_info() {
    echo -e "${CYAN}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[OK]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERR]${NC} $1"
}

step() {
    echo
    echo -e "${BLUE}============================================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}============================================================${NC}"
}

print_logo() {
    echo -e "${PURPLE}"
    cat << 'EOF'
    ╔═══════════════════════════════════════════════════════╗
    ║                                                       ║
    ║  ██████╗  ██╗ ██████╗   █████╗                        ║
    ║  ██╔══██╗ ██║ ██╔══██╗ ██╔══██╗                       ║
    ║  ██████╔╝ ██║ ██████╔╝ ███████║                       ║
    ║  ██╔══██╗ ██║ ██╔══██╗ ██╔══██║                       ║
    ║  ██████╔╝ ██║ ██████╔╝ ██║  ██║                       ║
    ║  ╚═════╝  ╚═╝ ╚═════╝  ╚═╝  ╚═╝                       ║
    ║                                                       ║
    ╚═══════════════════════════════════════════════════════╝
EOF
    echo -e "${NC}"
    echo -e "${CYAN}              🤖  BiBa Node Setup v1.0  🤖${NC}"
    echo ""
}

install_packages() {
    step "Installing system dependencies"
    sudo apt update
    sudo apt install -y git curl wget vim htop net-tools usbutils ca-certificates gnupg lsb-release
    log_success "System packages installed"
}

install_docker() {
    step "Checking Docker"
    if command -v docker >/dev/null 2>&1; then
        log_success "Docker already installed: $(docker --version)"
    else
        log_info "Installing Docker from get.docker.com"
        curl -fsSL https://get.docker.com -o /tmp/get-docker.sh
        sudo sh /tmp/get-docker.sh
        rm -f /tmp/get-docker.sh
        sudo usermod -aG docker "$USER"
        log_success "Docker installed"
        log_warn "Relogin may be required for docker group membership"
    fi

    if docker compose version >/dev/null 2>&1; then
        log_success "Docker Compose available: $(docker compose version)"
    else
        log_info "Installing docker-compose-plugin"
        sudo apt install -y docker-compose-plugin
        log_success "Docker Compose plugin installed"
    fi
}

clone_or_update_repo() {
    step "Cloning or updating BiBa repository"
    if [ -d "$REPO_DIR/.git" ]; then
        log_info "Repository already exists in $REPO_DIR"
        git -C "$REPO_DIR" fetch origin
        git -C "$REPO_DIR" checkout "$BRANCH"
        git -C "$REPO_DIR" pull --ff-only origin "$BRANCH"
        log_success "Repository updated"
    else
        git clone "$REPO_URL" "$REPO_DIR"
        git -C "$REPO_DIR" checkout "$BRANCH"
        log_success "Repository cloned to $REPO_DIR"
    fi
}

install_aliases() {
    step "Installing BiBa aliases"
    bash "$REPO_DIR/scripts/setup/install_aliases.sh"
    log_success "Aliases installed"
}

write_env_file() {
    step "Writing runtime environment file"
    sudo tee "$ENV_FILE" >/dev/null <<'EOF'
BIBA_IMAGE_TAG=latest
EOF
    log_success "Environment file created at $ENV_FILE"
}

setup_service() {
    step "Configuring systemd autostart"
    sudo tee "$SERVICE_FILE" >/dev/null <<EOF
[Unit]
Description=BiBa controller docker compose stack
After=docker.service network-online.target
Requires=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=$REPO_DIR
EnvironmentFile=-$ENV_FILE
ExecStart=/usr/bin/docker compose up -d
ExecStop=/usr/bin/docker compose down
TimeoutStartSec=0

[Install]
WantedBy=multi-user.target
EOF

    sudo systemctl daemon-reload
    sudo systemctl enable "$SERVICE_NAME.service"
    log_success "systemd service enabled"
}

print_summary() {
    step "Setup completed"
    echo "Repository: $REPO_DIR"
    echo "Branch: $BRANCH"
    echo "Systemd unit: $SERVICE_FILE"
    echo
    echo "Next steps:"
    echo "  1. Relogin if Docker group membership was just added"
    echo "  2. Login to GHCR: echo TOKEN | docker login ghcr.io -u USERNAME --password-stdin"
    echo "  3. Start stack: sudo systemctl start ${SERVICE_NAME}.service"
    echo "  4. Check status: bbstatus"
    echo "  5. Tail logs: bblogs"
}

setup_motd() {
    step "Configuring custom MOTD"

    MOTD_SCRIPT="/usr/local/bin/biba-motd"

    sudo tee "$MOTD_SCRIPT" > /dev/null << 'MOTDEOF'
#!/bin/bash
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
BOLD='\033[1m'
NC='\033[0m'

HOSTNAME=$(hostname)
UPTIME=$(uptime -p 2>/dev/null | sed 's/up //' || uptime)
MEMORY=$(free -h 2>/dev/null | awk '/^Mem:/ {print $3 "/" $2}' || echo "N/A")
DISK=$(df -h / 2>/dev/null | awk 'NR==2 {print $3 "/" $2 " (" $5 ")"}' || echo "N/A")

if [ -f /sys/class/thermal/thermal_zone0/temp ]; then
    RAW=$(cat /sys/class/thermal/thermal_zone0/temp)
    CPU_TEMP="${RAW%???}.${RAW: -3:1}°C"
else
    CPU_TEMP="N/A"
fi

WLAN_IP=$(ip -4 addr show wlan0 2>/dev/null | grep -oP '(?<=inet\s)\d+(\.\d+){3}' || echo "N/A")
ETH_IP=$(ip -4 addr show eth0 2>/dev/null | grep -oP '(?<=inet\s)\d+(\.\d+){3}' || echo "N/A")

if command -v docker &>/dev/null; then
    DOCKER_RUNNING=$(docker ps --format "{{.Names}}" 2>/dev/null | wc -l)
    DOCKER_TOTAL=$(docker ps -a --format "{{.Names}}" 2>/dev/null | wc -l)
    DOCKER_STATUS="${GREEN}${DOCKER_RUNNING}${NC}/${DOCKER_TOTAL} running"
else
    DOCKER_RUNNING=0
    DOCKER_STATUS="${RED}Not installed${NC}"
fi

echo -e "${PURPLE}"
cat << 'LOGO'
    ╔═══════════════════════════════════════════════════════╗
    ║                                                       ║
    ║  ██████╗  ██╗ ██████╗   █████╗                        ║
    ║  ██╔══██╗ ██║ ██╔══██╗ ██╔══██╗                       ║
    ║  ██████╔╝ ██║ ██████╔╝ ███████║                       ║
    ║  ██╔══██╗ ██║ ██╔══██╗ ██╔══██║                       ║
    ║  ██████╔╝ ██║ ██████╔╝ ██║  ██║                       ║
    ║  ╚═════╝  ╚═╝ ╚═════╝  ╚═╝  ╚═╝                       ║
    ║                                                       ║
    ╚═══════════════════════════════════════════════════════╝
LOGO
echo -e "${NC}"
echo -e "${CYAN}                🤖  BiBa Controller  🤖${NC}"
echo ""

echo -e "${BOLD}${CYAN}SYSTEM${NC}"
echo -e "  ${BLUE}Hostname:${NC}    $HOSTNAME"
echo -e "  ${BLUE}Uptime:${NC}      $UPTIME"
echo -e "  ${BLUE}Memory:${NC}      $MEMORY"
echo -e "  ${BLUE}Disk:${NC}        $DISK"
echo -e "  ${BLUE}CPU Temp:${NC}    $CPU_TEMP"
echo ""

echo -e "${BOLD}${GREEN}NETWORK${NC}"
echo -e "  ${BLUE}Ethernet:${NC}    $ETH_IP"
echo -e "  ${BLUE}WiFi:${NC}        $WLAN_IP"
echo ""

echo -e "${BOLD}${PURPLE}DOCKER${NC}"
echo -e "  ${BLUE}Containers:${NC}  $DOCKER_STATUS"
if [ "$DOCKER_RUNNING" -gt 0 ] 2>/dev/null; then
    docker ps --format "  ${GREEN}✓${NC} {{.Names}}  {{.Status}}" 2>/dev/null
fi
echo ""

echo -e "${CYAN}═══════════════════════════════════════════════════════${NC}"
echo -e "${CYAN}Quick Commands:${NC}"
echo -e "  ${BLUE}bbstatus${NC}    Container status"
echo -e "  ${BLUE}bblogs${NC}      Tail logs"
echo -e "  ${BLUE}bbupdate${NC}    Full update (git pull + pull + restart)"
echo -e "  ${BLUE}bbhealth${NC}    Docker overview"
echo -e "  ${BLUE}bbrestart${NC}   Restart stack"
echo -e "${CYAN}═══════════════════════════════════════════════════════${NC}"
echo ""
MOTDEOF

    sudo chmod +x "$MOTD_SCRIPT"

    if [ -d /etc/update-motd.d ]; then
        sudo chmod -x /etc/update-motd.d/* 2>/dev/null || true
    fi

    if ! grep -q "biba-motd" "$HOME/.bashrc"; then
        {
            echo ""
            echo "# BiBa Custom MOTD"
            echo "$MOTD_SCRIPT"
        } >> "$HOME/.bashrc"
    fi

    log_success "Custom MOTD configured"
}

main() {
    print_logo
    install_packages
    install_docker
    clone_or_update_repo
    install_aliases
    write_env_file
    setup_service
    setup_motd
    print_summary
}

main "$@"
