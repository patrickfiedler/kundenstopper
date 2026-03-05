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
echo -e "${BLUE}Kundenstopper Deployment Script${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Check if Python 3 is installed
echo -e "${YELLOW}[1/8] Checking Python 3...${NC}"
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}Error: Python 3 is not installed${NC}"
    echo "Please install Python 3 first: sudo apt install python3 python3-pip"
    exit 1
fi
PYTHON_VERSION=$(python3 --version)
echo -e "${GREEN}✓ Found: $PYTHON_VERSION${NC}"
echo ""

# Check if pip is installed
echo -e "${YELLOW}[2/8] Checking pip...${NC}"
if ! python3 -m pip --version &> /dev/null; then
    echo -e "${RED}Error: pip is not installed${NC}"
    echo "Please install pip: sudo apt install python3-pip"
    exit 1
fi
echo -e "${GREEN}✓ pip is installed${NC}"
echo ""

# Ask about virtual environment
echo -e "${YELLOW}[3/8] Virtual Environment Setup${NC}"
echo "Do you want to use a virtual environment? (recommended)"
read -p "Use venv? [Y/n]: " use_venv
use_venv=${use_venv:-Y}

if [[ $use_venv =~ ^[Yy]$ ]]; then
    VENV_DIR="$SCRIPT_DIR/venv"
    if [ -d "$VENV_DIR" ]; then
        echo -e "${YELLOW}Virtual environment already exists${NC}"
    else
        echo "Creating virtual environment..."
        python3 -m venv "$VENV_DIR"
        echo -e "${GREEN}✓ Virtual environment created${NC}"
    fi

    # Activate virtual environment
    source "$VENV_DIR/bin/activate"
    echo -e "${GREEN}✓ Virtual environment activated${NC}"

    # Store venv info for later
    USING_VENV=true
else
    echo -e "${YELLOW}Skipping virtual environment${NC}"
    USING_VENV=false
fi
echo ""

# Install dependencies
echo -e "${YELLOW}[4/8] Installing Python dependencies...${NC}"
python3 -m pip install -r "$SCRIPT_DIR/requirements.txt" --upgrade
echo -e "${GREEN}✓ Dependencies installed${NC}"
echo ""

# Create uploads directory
echo -e "${YELLOW}[5/8] Creating uploads directory...${NC}"
UPLOADS_DIR="$SCRIPT_DIR/uploads"
if [ ! -d "$UPLOADS_DIR" ]; then
    mkdir -p "$UPLOADS_DIR"
    echo -e "${GREEN}✓ Uploads directory created${NC}"
else
    echo -e "${GREEN}✓ Uploads directory already exists${NC}"
fi
echo ""

# Create config.json if it doesn't exist
echo -e "${YELLOW}[6/8] Configuration Setup${NC}"
CONFIG_FILE="$SCRIPT_DIR/config.json"

if [ -f "$CONFIG_FILE" ]; then
    echo -e "${YELLOW}config.json already exists${NC}"
    read -p "Do you want to reconfigure? [y/N]: " reconfigure
    reconfigure=${reconfigure:-N}

    if [[ ! $reconfigure =~ ^[Yy]$ ]]; then
        echo -e "${GREEN}✓ Using existing configuration${NC}"
        echo ""
        SKIP_CONFIG=true
    else
        SKIP_CONFIG=false
    fi
else
    SKIP_CONFIG=false
fi

if [ "$SKIP_CONFIG" != "true" ]; then
    # Copy example config
    cp "$SCRIPT_DIR/config.json.example" "$CONFIG_FILE"

    # Get admin username
    read -p "Admin username [admin]: " admin_username
    admin_username=${admin_username:-admin}

    # Read password securely (never interpolated into shell strings)
    echo ""
    while true; do
        read -s -p "Admin password: " admin_password; echo ""
        read -s -p "Confirm password: " admin_password_confirm; echo ""
        if [ "$admin_password" = "$admin_password_confirm" ]; then
            break
        fi
        echo -e "${RED}Passwords do not match, try again.${NC}"
    done

    # Generate password hash — pass via argument, not shell expansion
    echo "Generating password hash..."
    PASSWORD_HASH=$(python3 -c "
import bcrypt, sys
pw = sys.argv[1].encode('utf-8')
print(bcrypt.hashpw(pw, bcrypt.gensalt()).decode())
" "$admin_password")

    # Generate secret key
    SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")

    # Get port
    read -p "Server port [8080]: " port
    port=${port:-8080}

    # Update config.json — quoted heredoc + sys.argv avoids all shell-expansion issues
    python3 - "$admin_username" "$PASSWORD_HASH" "$SECRET_KEY" "$port" "$CONFIG_FILE" << 'PYEOF'
import json, sys
username, pw_hash, secret, port, cfg_file = sys.argv[1:6]
with open(cfg_file, 'r') as f:
    config = json.load(f)
config['admin_username'] = username
config['admin_password_hash'] = pw_hash
config['secret_key'] = secret
config['port'] = int(port)
with open(cfg_file, 'w') as f:
    json.dump(config, f, indent=2)
    f.write('\n')
PYEOF

    echo -e "${GREEN}✓ Configuration file created${NC}"
fi
echo ""

# Deployment target for update.sh
echo -e "${YELLOW}[7/8] Deployment Target${NC}"
echo "What should update.sh pull when you run it later?"
echo "  1) Always use the latest commit (main branch)"
echo "  2) Pin to a specific tag"
read -p "Choice [1]: " target_choice
target_choice=${target_choice:-1}

if [[ $target_choice == "2" ]]; then
    echo ""
    echo "Available tags:"
    git tag -l | sort -V | tail -10
    echo ""
    read -p "Tag name (e.g. v1.0): " deploy_target_tag
    cat > "$SCRIPT_DIR/deployment.conf" << DEPLOYEOF
TARGET_TYPE=tag
TARGET_VALUE=$deploy_target_tag
DEPLOYEOF
    echo -e "${GREEN}✓ update.sh will use tag: $deploy_target_tag${NC}"
else
    cat > "$SCRIPT_DIR/deployment.conf" << DEPLOYEOF
TARGET_TYPE=latest
TARGET_VALUE=main
DEPLOYEOF
    echo -e "${GREEN}✓ update.sh will always use latest commit on main${NC}"
fi
echo -e "   Change later with: ${BLUE}bash update.sh --tag v1.x${NC}  or  ${BLUE}bash update.sh --latest${NC}"
echo ""

# Setup systemd service (optional)
echo -e "${YELLOW}[8/8] Systemd Service Setup${NC}"
echo "Do you want to set up the systemd service?"
echo "(This will allow the app to start automatically on boot)"
read -p "Setup systemd service? [y/N]: " setup_service
setup_service=${setup_service:-N}

if [[ $setup_service =~ ^[Yy]$ ]]; then
    SERVICE_FILE="$SCRIPT_DIR/kundenstopper.service"
    TEMP_SERVICE="/tmp/kundenstopper.service"

    # Detect current user and group
    CURRENT_USER=$(whoami)
    CURRENT_GROUP=$(id -gn)

    # Determine Python executable path
    if [ "$USING_VENV" = true ]; then
        PYTHON_PATH="$VENV_DIR/bin/python3"
        EXEC_START="$PYTHON_PATH $SCRIPT_DIR/app.py"
    else
        PYTHON_PATH=$(which python3)
        EXEC_START="$PYTHON_PATH $SCRIPT_DIR/app.py"
    fi

    # Generate service file
    cat > "$TEMP_SERVICE" << SERVICEEOF
[Unit]
Description=Kundenstopper PDF Display Service
After=network.target

[Service]
Type=simple
User=$CURRENT_USER
Group=$CURRENT_GROUP
WorkingDirectory=$SCRIPT_DIR
Environment="PATH=/usr/bin:/usr/local/bin"
ExecStart=$EXEC_START

# Restart configuration
Restart=always
RestartSec=10

# Security settings
NoNewPrivileges=true
PrivateTmp=true

# Logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=kundenstopper

[Install]
WantedBy=multi-user.target
SERVICEEOF

    echo ""
    echo -e "${BLUE}Generated service file:${NC}"
    cat "$TEMP_SERVICE"
    echo ""

    read -p "Install this service file? [Y/n]: " install_service
    install_service=${install_service:-Y}

    if [[ $install_service =~ ^[Yy]$ ]]; then
        sudo cp "$TEMP_SERVICE" /etc/systemd/system/kundenstopper.service
        sudo systemctl daemon-reload

        read -p "Enable service to start on boot? [Y/n]: " enable_service
        enable_service=${enable_service:-Y}

        if [[ $enable_service =~ ^[Yy]$ ]]; then
            sudo systemctl enable kundenstopper
            echo -e "${GREEN}✓ Service enabled${NC}"
        fi

        read -p "Start service now? [Y/n]: " start_service
        start_service=${start_service:-Y}

        if [[ $start_service =~ ^[Yy]$ ]]; then
            sudo systemctl start kundenstopper
            echo -e "${GREEN}✓ Service started${NC}"
            echo ""
            echo "Checking service status..."
            sleep 2
            sudo systemctl status kundenstopper --no-pager -l
        fi
    fi

    rm -f "$TEMP_SERVICE"
else
    echo -e "${YELLOW}Skipping systemd service setup${NC}"
    echo "You can run the app manually with: python3 app.py"
fi
echo ""

# Final summary
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Deployment Complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "${BLUE}Application URLs:${NC}"

# Read port from config.json
PORT=$(python3 -c "import json; print(json.load(open('$CONFIG_FILE'))['port'])")

echo "  Display: http://localhost:$PORT/display"
echo "  Admin:   http://localhost:$PORT/admin"
echo ""

if [[ $setup_service =~ ^[Yy]$ ]] && [[ $start_service =~ ^[Yy]$ ]]; then
    echo -e "${BLUE}Service Management:${NC}"
    echo "  Status:  sudo systemctl status kundenstopper"
    echo "  Stop:    sudo systemctl stop kundenstopper"
    echo "  Restart: sudo systemctl restart kundenstopper"
    echo "  Logs:    sudo journalctl -u kundenstopper -f"
else
    echo -e "${BLUE}To start manually:${NC}"
    if [ "$USING_VENV" = true ]; then
        echo "  cd $SCRIPT_DIR"
        echo "  source venv/bin/activate"
        echo "  python3 app.py"
    else
        echo "  cd $SCRIPT_DIR"
        echo "  python3 app.py"
    fi
fi
echo ""

if [ "$USING_VENV" = true ]; then
    echo -e "${YELLOW}Note: Virtual environment is at $VENV_DIR${NC}"
fi

echo ""
echo -e "${GREEN}Happy displaying! 📄✨${NC}"
