#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_CONF="$SCRIPT_DIR/deployment.conf"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Kundenstopper Update Script${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Sanity checks
if [ ! -d "$SCRIPT_DIR/.git" ]; then
    echo -e "${RED}Error: Not a git repository. Run deploy.sh first.${NC}"; exit 1
fi
if [ ! -f "$SCRIPT_DIR/config.json" ]; then
    echo -e "${RED}Error: config.json not found. Run deploy.sh first.${NC}"; exit 1
fi

# ---------- Parse arguments ----------
SKIP_SELF_UPDATE=false
TARGET_TYPE_OVERRIDE=""
TARGET_VALUE_OVERRIDE=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --skip-self-update) SKIP_SELF_UPDATE=true; shift ;;
        --latest) TARGET_TYPE_OVERRIDE=latest; TARGET_VALUE_OVERRIDE=main; shift ;;
        --tag)
            if [[ -z $2 || $2 == --* ]]; then
                echo -e "${RED}--tag requires a tag name, e.g.: bash update.sh --tag v1.2${NC}"; exit 1
            fi
            TARGET_TYPE_OVERRIDE=tag; TARGET_VALUE_OVERRIDE="$2"; shift 2 ;;
        *) echo -e "${RED}Unknown argument: $1${NC}"
           echo "Usage: $0 [--latest | --tag <tagname>]"; exit 1 ;;
    esac
done

# ---------- Load and apply deployment config ----------
TARGET_TYPE=latest
TARGET_VALUE=main

if [ -f "$DEPLOY_CONF" ]; then
    # shellcheck source=/dev/null
    source "$DEPLOY_CONF"
else
    echo -e "${YELLOW}No deployment.conf found. Defaulting to latest (main).${NC}"
    echo -e "Run deploy.sh first, or pass ${BLUE}--latest${NC} / ${BLUE}--tag <name>${NC}."
    echo ""
fi

if [ -n "$TARGET_TYPE_OVERRIDE" ]; then
    TARGET_TYPE=$TARGET_TYPE_OVERRIDE
    TARGET_VALUE=$TARGET_VALUE_OVERRIDE
    printf 'TARGET_TYPE=%s\nTARGET_VALUE=%s\n' "$TARGET_TYPE" "$TARGET_VALUE" > "$DEPLOY_CONF"
    echo -e "${GREEN}Deployment target updated: $TARGET_TYPE ($TARGET_VALUE)${NC}"
    echo ""
fi

echo -e "${BLUE}Target: $TARGET_TYPE ($TARGET_VALUE)${NC}"

# Detect venv and service
USING_SYSTEMD=false
systemctl is-active --quiet kundenstopper 2>/dev/null && USING_SYSTEMD=true

if [ -d "$SCRIPT_DIR/venv" ]; then
    PYTHON="$SCRIPT_DIR/venv/bin/python3"
    PIP="$SCRIPT_DIR/venv/bin/pip3"
    echo -e "${BLUE}Using virtual environment${NC}"
else
    PYTHON=python3
    PIP="python3 -m pip"
fi

[ "$USING_SYSTEMD" = true ] && echo -e "${BLUE}Detected running systemd service${NC}"
echo ""

# Resolve the git ref to compare against / check out
if [ "$TARGET_TYPE" = tag ]; then
    COMPARE_REF="$TARGET_VALUE"
else
    COMPARE_REF="origin/$TARGET_VALUE"
fi

# ---------- [1/5] Fetch + self-update check ----------
echo -e "${YELLOW}[1/5] Fetching from remote...${NC}"
git -C "$SCRIPT_DIR" fetch origin
[ "$TARGET_TYPE" = tag ] && git -C "$SCRIPT_DIR" fetch --tags 2>/dev/null || true
echo -e "${GREEN}✓ Fetch complete${NC}"

if [ "$SKIP_SELF_UPDATE" = false ]; then
    if ! git -C "$SCRIPT_DIR" diff --quiet HEAD "$COMPARE_REF" -- update.sh 2>/dev/null; then
        echo -e "${YELLOW}update.sh has been updated — restarting with new version...${NC}"
        git -C "$SCRIPT_DIR" show "$COMPARE_REF:update.sh" > "$SCRIPT_DIR/update.sh"
        chmod +x "$SCRIPT_DIR/update.sh"
        exec bash "$SCRIPT_DIR/update.sh" "$@" --skip-self-update
    fi
    echo -e "${GREEN}✓ update.sh is current${NC}"
fi
echo ""

# ---------- Show what has changed ----------
CURRENT_COMMIT=$(git -C "$SCRIPT_DIR" rev-parse HEAD)

if [ "$TARGET_TYPE" = tag ]; then
    BEHIND_COUNT=$(git -C "$SCRIPT_DIR" rev-list "HEAD..$TARGET_VALUE" --count 2>/dev/null || echo 0)
else
    BEHIND_COUNT=$(git -C "$SCRIPT_DIR" rev-list "HEAD..origin/$TARGET_VALUE" --count 2>/dev/null || echo 0)
fi

if [ "$BEHIND_COUNT" -eq 0 ]; then
    echo -e "${GREEN}Already up to date. Nothing to do.${NC}"
    exit 0
fi

echo -e "${BLUE}$BEHIND_COUNT new commit(s):${NC}"
git -C "$SCRIPT_DIR" log HEAD.."$COMPARE_REF" --oneline --max-count=10
echo ""

read -p "Continue with update? [Y/n]: " do_update
do_update=${do_update:-Y}
if [[ ! $do_update =~ ^[Yy]$ ]]; then
    echo "Update cancelled."
    exit 0
fi
echo ""

# ---------- [2/5] Backup tag ----------
echo -e "${YELLOW}[2/5] Creating backup tag...${NC}"
BACKUP_TAG="backup-$(date +%Y%m%d-%H%M%S)"
git -C "$SCRIPT_DIR" tag "$BACKUP_TAG"
echo -e "${GREEN}✓ Backup tag: $BACKUP_TAG${NC}"
echo "  Rollback: git reset --hard $BACKUP_TAG && sudo systemctl restart kundenstopper"
echo ""

# ---------- [3/5] Stop service, pull code ----------
echo -e "${YELLOW}[3/5] Updating code...${NC}"
if [ "$USING_SYSTEMD" = true ]; then
    sudo systemctl stop kundenstopper
    echo "Service stopped."
fi

if [ "$TARGET_TYPE" = tag ]; then
    git -C "$SCRIPT_DIR" checkout "$TARGET_VALUE"
else
    CURRENT_BRANCH=$(git -C "$SCRIPT_DIR" symbolic-ref --short HEAD 2>/dev/null || echo DETACHED)
    if [ "$CURRENT_BRANCH" != "$TARGET_VALUE" ]; then
        git -C "$SCRIPT_DIR" checkout "$TARGET_VALUE"
    fi
    git -C "$SCRIPT_DIR" reset --hard "origin/$TARGET_VALUE"
fi

NEW_COMMIT=$(git -C "$SCRIPT_DIR" rev-parse HEAD)
echo -e "${GREEN}✓ Code updated: ${CURRENT_COMMIT:0:7} → ${NEW_COMMIT:0:7}${NC}"
echo ""

# ---------- [4/5] Dependencies + migrations ----------
echo -e "${YELLOW}[4/5] Dependencies and database migrations...${NC}"
mkdir -p "$SCRIPT_DIR/uploads" "$SCRIPT_DIR/renders"

if git -C "$SCRIPT_DIR" diff "$CURRENT_COMMIT" "$NEW_COMMIT" --name-only 2>/dev/null | grep -q "requirements.txt"; then
    echo "requirements.txt changed — updating dependencies..."
    $PIP install -q -r "$SCRIPT_DIR/requirements.txt" --upgrade
    echo -e "${GREEN}✓ Dependencies updated${NC}"
else
    echo -e "${GREEN}✓ No dependency changes${NC}"
fi

if git -C "$SCRIPT_DIR" diff "$CURRENT_COMMIT" "$NEW_COMMIT" --name-only 2>/dev/null | grep -q "config.json.example"; then
    echo -e "${YELLOW}⚠ config.json.example has changed — new options may be available.${NC}"
    read -p "  View diff? [y/N]: " view_conf
    [[ $view_conf =~ ^[Yy]$ ]] && git -C "$SCRIPT_DIR" diff "$CURRENT_COMMIT" "$NEW_COMMIT" -- config.json.example
    echo ""
fi

echo "Running database migrations..."
cd "$SCRIPT_DIR" && $PYTHON migrate.py
echo ""

# ---------- [5/5] Restart service ----------
echo -e "${YELLOW}[5/5] Starting service...${NC}"
if [ "$USING_SYSTEMD" = true ]; then
    sudo systemctl start kundenstopper
    sleep 2
    if systemctl is-active --quiet kundenstopper; then
        echo -e "${GREEN}✓ Service started${NC}"
    else
        echo -e "${RED}Service failed to start!${NC}"
        echo "Logs: sudo journalctl -u kundenstopper -n 50"
        echo ""
        echo -e "${YELLOW}To rollback:${NC}"
        echo "  git -C $SCRIPT_DIR reset --hard $BACKUP_TAG"
        echo "  sudo systemctl restart kundenstopper"
        exit 1
    fi
else
    echo -e "${YELLOW}Service not running. Start manually: python3 app.py${NC}"
fi
echo ""

# ---------- Summary ----------
PORT=$($PYTHON -c "import json; print(json.load(open('$SCRIPT_DIR/config.json'))['port'])" 2>/dev/null || echo 8080)

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Update complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "${BLUE}Updated:${NC} ${CURRENT_COMMIT:0:7} → ${NEW_COMMIT:0:7}"
echo -e "${BLUE}Backup:${NC}  git reset --hard $BACKUP_TAG"
echo ""
echo -e "${BLUE}URLs:${NC}"
echo "  Admin:   http://localhost:$PORT/admin"
for slug in $(cd "$SCRIPT_DIR" && $PYTHON -c "
from models import get_all_displays
for d in get_all_displays(): print(d['slug'])
" 2>/dev/null); do
    echo "  Display: http://localhost:$PORT/display/$slug"
done
echo ""
