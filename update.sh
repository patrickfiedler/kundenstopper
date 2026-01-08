#!/bin/bash
set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Kundenstopper Update Script${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Check if this is a git repository
if [ ! -d "$SCRIPT_DIR/.git" ]; then
    echo -e "${RED}Error: Not a git repository${NC}"
    echo "This script only works with git-cloned installations"
    echo "Please use deploy.sh for initial setup"
    exit 1
fi

# Check if config.json exists
if [ ! -f "$SCRIPT_DIR/config.json" ]; then
    echo -e "${RED}Error: config.json not found${NC}"
    echo "Please run deploy.sh first for initial setup"
    exit 1
fi

# Detect if using systemd service
USING_SYSTEMD=false
if systemctl is-active --quiet kundenstopper 2>/dev/null; then
    USING_SYSTEMD=true
    echo -e "${BLUE}Detected running systemd service${NC}"
fi

# Detect if using virtual environment
USING_VENV=false
VENV_DIR="$SCRIPT_DIR/venv"
if [ -d "$VENV_DIR" ]; then
    USING_VENV=true
    echo -e "${BLUE}Detected virtual environment${NC}"
fi
echo ""

# Create backup tag before updating
echo -e "${YELLOW}[1/6] Creating backup tag...${NC}"
BACKUP_TAG="backup-$(date +%Y%m%d-%H%M%S)"
git tag "$BACKUP_TAG"
echo -e "${GREEN}✓ Backup tag created: $BACKUP_TAG${NC}"
echo "  (To rollback: git reset --hard $BACKUP_TAG)"
echo ""

# Store current commit for comparison
CURRENT_COMMIT=$(git rev-parse HEAD)

# Fetch updates
echo -e "${YELLOW}[2/6] Fetching updates from GitHub...${NC}"
git fetch origin
echo -e "${GREEN}✓ Fetch complete${NC}"
echo ""

# Check if there are updates
BEHIND_COUNT=$(git rev-list HEAD..origin/main --count 2>/dev/null || echo "0")

if [ "$BEHIND_COUNT" -eq 0 ]; then
    echo -e "${GREEN}Already up to date!${NC}"
    echo "No updates available."
    exit 0
fi

echo -e "${BLUE}Updates available: $BEHIND_COUNT commit(s)${NC}"
echo ""
echo -e "${BLUE}Recent changes:${NC}"
git log HEAD..origin/main --oneline --max-count=5
echo ""

read -p "Continue with update? [Y/n]: " continue_update
continue_update=${continue_update:-Y}

if [[ ! $continue_update =~ ^[Yy]$ ]]; then
    echo "Update cancelled"
    git tag -d "$BACKUP_TAG"  # Remove backup tag
    exit 0
fi
echo ""

# Stop service if running
if [ "$USING_SYSTEMD" = true ]; then
    echo -e "${YELLOW}[3/6] Stopping service...${NC}"
    sudo systemctl stop kundenstopper
    echo -e "${GREEN}✓ Service stopped${NC}"
    echo ""
else
    echo -e "${YELLOW}[3/6] No service to stop${NC}"
    echo -e "${YELLOW}⚠ Warning: Make sure the app is not running manually${NC}"
    read -p "Press Enter to continue..."
    echo ""
fi

# Pull updates
echo -e "${YELLOW}[4/6] Pulling updates...${NC}"
git pull origin main
NEW_COMMIT=$(git rev-parse HEAD)
echo -e "${GREEN}✓ Code updated${NC}"
echo ""

# Check if requirements.txt changed
echo -e "${YELLOW}[5/6] Checking dependencies...${NC}"
if git diff "$CURRENT_COMMIT" "$NEW_COMMIT" --name-only | grep -q "requirements.txt"; then
    echo -e "${YELLOW}requirements.txt has changed, updating dependencies...${NC}"

    if [ "$USING_VENV" = true ]; then
        source "$VENV_DIR/bin/activate"
        echo "Using virtual environment"
    fi

    python3 -m pip install -r "$SCRIPT_DIR/requirements.txt" --upgrade
    echo -e "${GREEN}✓ Dependencies updated${NC}"
else
    echo -e "${GREEN}✓ No dependency changes${NC}"
fi
echo ""

# Check if config.json.example changed
if git diff "$CURRENT_COMMIT" "$NEW_COMMIT" --name-only | grep -q "config.json.example"; then
    echo -e "${YELLOW}⚠ config.json.example has changed!${NC}"
    echo "New configuration options may be available."
    echo "Please review config.json.example and update your config.json if needed"
    echo ""

    read -p "View changes to config.json.example? [y/N]: " view_config
    if [[ $view_config =~ ^[Yy]$ ]]; then
        echo ""
        git diff "$CURRENT_COMMIT" "$NEW_COMMIT" -- config.json.example
        echo ""
    fi
fi

# Restart service if it was running
if [ "$USING_SYSTEMD" = true ]; then
    echo -e "${YELLOW}[6/6] Starting service...${NC}"
    sudo systemctl start kundenstopper

    # Wait a moment for service to start
    sleep 2

    # Check if service started successfully
    if systemctl is-active --quiet kundenstopper; then
        echo -e "${GREEN}✓ Service started successfully${NC}"
        echo ""
        echo "Checking service status..."
        sudo systemctl status kundenstopper --no-pager -l || true
    else
        echo -e "${RED}✗ Service failed to start!${NC}"
        echo ""
        echo "Checking logs..."
        sudo journalctl -u kundenstopper -n 20 --no-pager
        echo ""
        echo -e "${RED}Update may have introduced issues${NC}"
        echo -e "${YELLOW}To rollback:${NC}"
        echo "  cd $SCRIPT_DIR"
        echo "  git reset --hard $BACKUP_TAG"
        echo "  sudo systemctl restart kundenstopper"
        exit 1
    fi
else
    echo -e "${YELLOW}[6/6] No service to restart${NC}"
    echo -e "${BLUE}Please start the app manually if needed${NC}"
fi
echo ""

# Final summary
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Update Complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "${BLUE}Updated from:${NC} ${CURRENT_COMMIT:0:7}"
echo -e "${BLUE}Updated to:${NC}   ${NEW_COMMIT:0:7}"
echo ""

# Read port from config.json
PORT=$(python3 -c "import json; print(json.load(open('$SCRIPT_DIR/config.json'))['port'])")

echo -e "${BLUE}Application URLs:${NC}"
echo "  Display: http://localhost:$PORT/display"
echo "  Admin:   http://localhost:$PORT/admin"
echo ""

if [ "$USING_SYSTEMD" = true ]; then
    echo -e "${BLUE}Service Management:${NC}"
    echo "  Status:  sudo systemctl status kundenstopper"
    echo "  Logs:    sudo journalctl -u kundenstopper -f"
    echo ""
fi

echo -e "${BLUE}Backup tag created:${NC} $BACKUP_TAG"
echo "  To rollback: git reset --hard $BACKUP_TAG"
echo ""

echo -e "${GREEN}Update successful! 🚀${NC}"
