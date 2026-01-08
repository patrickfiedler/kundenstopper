# Kundenstopper Deployment Guide

This guide covers deploying and updating Kundenstopper on Linux machines using Git.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Initial Deployment](#initial-deployment)
- [Updating an Existing Installation](#updating-an-existing-installation)
- [Manual Deployment](#manual-deployment)
- [Rollback Procedure](#rollback-procedure)
- [Service Management](#service-management)
- [Troubleshooting](#troubleshooting)

---

## Prerequisites

Before deploying Kundenstopper, ensure the target machine has:

- **Linux Operating System** (tested on Ubuntu, Debian, CachyOS)
- **Python 3.7+** and pip
- **Git** (for cloning and updates)
- **systemd** (optional, for running as a service)
- **sudo access** (if using systemd)

### Installing Prerequisites

**Debian/Ubuntu:**
```bash
sudo apt update
sudo apt install python3 python3-pip git
```

**Arch/CachyOS:**
```bash
sudo pacman -S python python-pip git
```

**RHEL/Fedora:**
```bash
sudo dnf install python3 python3-pip git
```

---

## Initial Deployment

### Automated Deployment (Recommended)

The `deploy.sh` script automates the entire setup process.

**Steps:**

1. **Clone the repository:**
   ```bash
   git clone https://github.com/parsnipsmoothie/kundenstopper.git
   cd kundenstopper
   ```

2. **Run the deployment script:**
   ```bash
   ./deploy.sh
   ```

3. **Follow the interactive prompts:**
   - Choose whether to use a virtual environment (recommended: Yes)
   - Enter admin username (default: admin)
   - Enter and confirm admin password
   - Enter server port (default: 8080)
   - Choose whether to set up systemd service

**What the script does:**
- ✅ Checks Python 3 and pip installation
- ✅ Creates virtual environment (optional)
- ✅ Installs Python dependencies
- ✅ Creates `uploads/` directory
- ✅ Generates password hash securely
- ✅ Creates `config.json` from template
- ✅ Generates and installs systemd service (optional)
- ✅ Starts the service (optional)

**Example output:**
```
========================================
Kundenstopper Deployment Script
========================================

[1/7] Checking Python 3...
✓ Found: Python 3.11.5

[2/7] Checking pip...
✓ pip is installed

[3/7] Virtual Environment Setup
Use venv? [Y/n]: y
✓ Virtual environment created
✓ Virtual environment activated

[4/7] Installing Python dependencies...
✓ Dependencies installed

[5/7] Creating uploads directory...
✓ Uploads directory created

[6/7] Configuration Setup
Admin username [admin]: admin
Generating password hash...
Enter password: ********
Confirm password: ********
✓ Configuration file created

[7/7] Systemd Service Setup
Setup systemd service? [y/N]: y
✓ Service enabled
✓ Service started

========================================
Deployment Complete!
========================================
```

---

## Updating an Existing Installation

### Automated Updates (Recommended)

The `update.sh` script safely updates your installation from GitHub.

**Steps:**

1. **Navigate to your installation:**
   ```bash
   cd /path/to/kundenstopper
   ```

2. **Run the update script:**
   ```bash
   ./update.sh
   ```

3. **Review changes and confirm:**
   - The script shows recent commits
   - Automatically creates a backup tag
   - Stops the service (if running)
   - Pulls latest code
   - Updates dependencies (if changed)
   - Restarts the service

**What the script does:**
- ✅ Creates automatic backup tag before updating
- ✅ Shows preview of changes
- ✅ Stops systemd service gracefully
- ✅ Pulls latest code from GitHub
- ✅ Updates dependencies only if `requirements.txt` changed
- ✅ Alerts if `config.json.example` changed (new options available)
- ✅ Restarts service and verifies it started successfully
- ✅ Provides rollback instructions if update fails

**Example output:**
```
========================================
Kundenstopper Update Script
========================================

[1/6] Creating backup tag...
✓ Backup tag created: backup-20260108-143022
  (To rollback: git reset --hard backup-20260108-143022)

[2/6] Fetching updates from GitHub...
✓ Fetch complete

Updates available: 3 commit(s)

Recent changes:
a1b2c3d Fix PDF rotation issue
e4f5g6h Add configuration option for cache
h7i8j9k Update README with new features

Continue with update? [Y/n]: y

[3/6] Stopping service...
✓ Service stopped

[4/6] Pulling updates...
✓ Code updated

[5/6] Checking dependencies...
✓ No dependency changes

[6/6] Starting service...
✓ Service started successfully

========================================
Update Complete!
========================================
```

### Manual Update Process

If you prefer manual control:

1. **Stop the service:**
   ```bash
   sudo systemctl stop kundenstopper
   ```

2. **Create backup:**
   ```bash
   git tag backup-$(date +%Y%m%d-%H%M%S)
   ```

3. **Pull updates:**
   ```bash
   git pull origin main
   ```

4. **Update dependencies (if needed):**
   ```bash
   # If using venv:
   source venv/bin/activate
   pip install -r requirements.txt --upgrade
   ```

5. **Check for config changes:**
   ```bash
   git diff HEAD@{1} HEAD -- config.json.example
   ```

6. **Restart service:**
   ```bash
   sudo systemctl start kundenstopper
   sudo systemctl status kundenstopper
   ```

---

## Manual Deployment

If you prefer to deploy manually without the `deploy.sh` script:

### 1. Clone Repository

```bash
git clone https://github.com/parsnipsmoothie/kundenstopper.git
cd kundenstopper
```

### 2. Create Virtual Environment (Recommended)

```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Create Configuration

```bash
# Copy example config
cp config.json.example config.json

# Generate password hash
python3 generate_password_hash.py

# Edit config.json and paste the hash
nano config.json
```

Update `config.json`:
- Replace `admin_password_hash` with generated hash
- Change `secret_key` to a random string
- Adjust `port` if needed

### 5. Create Uploads Directory

```bash
mkdir uploads
```

### 6. Test Run

```bash
python3 app.py
```

Visit `http://localhost:8080` to verify it works.

### 7. Set Up Systemd Service (Optional)

```bash
# Edit service file with your paths
nano kundenstopper.service

# Copy to systemd
sudo cp kundenstopper.service /etc/systemd/system/

# Enable and start
sudo systemctl daemon-reload
sudo systemctl enable kundenstopper
sudo systemctl start kundenstopper

# Check status
sudo systemctl status kundenstopper
```

---

## Rollback Procedure

If an update causes issues, you can easily rollback:

### Using Backup Tags

The `update.sh` script automatically creates backup tags before each update.

**List available backups:**
```bash
git tag | grep backup
```

**Rollback to a specific backup:**
```bash
# Stop service
sudo systemctl stop kundenstopper

# Reset to backup
git reset --hard backup-20260108-143022

# Restart service
sudo systemctl start kundenstopper
```

### Manual Rollback

If you didn't use `update.sh`:

```bash
# View recent commits
git log --oneline -10

# Reset to specific commit
sudo systemctl stop kundenstopper
git reset --hard <commit-hash>
sudo systemctl start kundenstopper
```

---

## Service Management

### Systemd Commands

**Check service status:**
```bash
sudo systemctl status kundenstopper
```

**Start service:**
```bash
sudo systemctl start kundenstopper
```

**Stop service:**
```bash
sudo systemctl stop kundenstopper
```

**Restart service:**
```bash
sudo systemctl restart kundenstopper
```

**Enable auto-start on boot:**
```bash
sudo systemctl enable kundenstopper
```

**Disable auto-start:**
```bash
sudo systemctl disable kundenstopper
```

### Viewing Logs

**Real-time logs:**
```bash
sudo journalctl -u kundenstopper -f
```

**Last 50 lines:**
```bash
sudo journalctl -u kundenstopper -n 50
```

**All logs:**
```bash
sudo journalctl -u kundenstopper
```

**Logs since boot:**
```bash
sudo journalctl -u kundenstopper -b
```

---

## Troubleshooting

### Update Script Issues

**Issue: "Not a git repository"**
```
Solution: You must clone the repository using git, not download as ZIP
```

**Issue: "config.json not found"**
```
Solution: Run deploy.sh first for initial setup
```

**Issue: Service fails to start after update**
```
1. Check logs: sudo journalctl -u kundenstopper -n 50
2. Rollback: git reset --hard <backup-tag>
3. Restart: sudo systemctl restart kundenstopper
```

### Deployment Issues

**Issue: Python 3 not found**
```bash
# Debian/Ubuntu
sudo apt install python3 python3-pip

# Arch
sudo pacman -S python python-pip
```

**Issue: Permission denied when accessing /etc/systemd**
```
Solution: You need sudo access to install systemd services
Alternative: Run the app manually without systemd
```

**Issue: Port already in use**
```bash
# Check what's using the port
sudo lsof -i :8080

# Change port in config.json
nano config.json
# Change "port": 8080 to another port

# Restart service
sudo systemctl restart kundenstopper
```

**Issue: Can't connect to the app**
```bash
# Check if service is running
sudo systemctl status kundenstopper

# Check firewall (if accessing from another machine)
sudo ufw allow 8080/tcp

# Check the actual host:port from config
cat config.json | grep -E "(host|port)"
```

### Configuration Issues

**Issue: Forgot admin password**
```bash
# Generate new hash
python3 generate_password_hash.py

# Update config.json with new hash
nano config.json

# Restart service
sudo systemctl restart kundenstopper
```

**Issue: New config options after update**
```bash
# Compare your config with the example
diff config.json config.json.example

# Manually add any new options from example to your config
nano config.json
```

---

## File Preservation

The following files are **never overwritten** by updates (protected by `.gitignore`):

- `config.json` - Your configuration
- `kundenstopper.db` - Your database
- `uploads/` - Your uploaded PDFs
- `venv/` - Your virtual environment

These files persist across all updates and only you can modify them.

---

## Security Best Practices

1. **Use strong admin passwords** - The password is your only authentication
2. **Change the secret_key** - Never use the default from config.json.example
3. **Use HTTPS in production** - Consider using a reverse proxy (nginx, Caddy)
4. **Keep firewall enabled** - Only open necessary ports
5. **Regular updates** - Run `./update.sh` periodically to get security fixes
6. **Backup uploads/** - Consider backing up your PDF files separately

---

## Multi-Machine Deployment

To deploy on multiple machines:

1. **Clone on each machine:**
   ```bash
   git clone https://github.com/parsnipsmoothie/kundenstopper.git
   cd kundenstopper
   ./deploy.sh
   ```

2. **Each machine can have different configuration:**
   - Different admin passwords
   - Different ports
   - Different PDF files

3. **Update all machines:**
   ```bash
   # On each machine:
   cd /path/to/kundenstopper
   ./update.sh
   ```

---

## Getting Help

- **GitHub Issues:** https://github.com/parsnipsmoothie/kundenstopper/issues
- **Documentation:** See README.md for usage instructions
- **Logs:** Always check `sudo journalctl -u kundenstopper -n 50` when troubleshooting
