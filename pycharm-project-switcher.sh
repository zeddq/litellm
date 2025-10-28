#!/bin/bash
# PyCharm Project Switcher
# Closes current PyCharm instance and reopens with new project's environment
# Usage: ./pycharm-project-switcher.sh <project-directory>

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log() {
    echo -e "${BLUE}[INFO]${NC} $*"
}

error() {
    echo -e "${RED}[ERROR]${NC} $*"
}

success() {
    echo -e "${GREEN}[SUCCESS]${NC} $*"
}

warning() {
    echo -e "${YELLOW}[WARNING]${NC} $*"
}

# Check if project directory is provided
if [ -z "$1" ]; then
    error "Usage: $0 <project-directory>"
    exit 1
fi

PROJECT_DIR="$1"

# Verify project directory exists
if [ ! -d "$PROJECT_DIR" ]; then
    error "Directory not found: $PROJECT_DIR"
    exit 1
fi

# Get absolute path
cd "$PROJECT_DIR" || exit 1
PROJECT_DIR="$(pwd)"

log "Switching to project: $PROJECT_DIR"

# Function to close PyCharm
close_pycharm() {
    if [[ "$OSTYPE" == "darwin"* ]]; then
        log "Closing PyCharm on macOS..."

        # Try to close PyCharm gracefully
        osascript -e 'tell application "PyCharm" to quit' 2>/dev/null || true
        osascript -e 'tell application "PyCharm CE" to quit' 2>/dev/null || true

        # Wait a bit for graceful shutdown
        sleep 2

        # Force kill if still running
        pkill -f "PyCharm" 2>/dev/null || true

        success "PyCharm closed"
    else
        log "Closing PyCharm on Linux..."

        # Kill PyCharm processes
        pkill -f "pycharm" 2>/dev/null || true
        pkill -f "jetbrains" 2>/dev/null || true

        success "PyCharm processes terminated"
    fi

    # Wait for processes to fully close
    sleep 1
}

# Find the launcher script
LAUNCHER_SCRIPT=""

# Check if launcher is in the same directory as this script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "$SCRIPT_DIR/pycharm-env-launcher.sh" ]; then
    LAUNCHER_SCRIPT="$SCRIPT_DIR/pycharm-env-launcher.sh"
elif [ -f "${HOME}/bin/pycharm-env-launcher.sh" ]; then
    LAUNCHER_SCRIPT="${HOME}/bin/pycharm-env-launcher.sh"
elif [ -f "${HOME}/.local/bin/pycharm-env-launcher.sh" ]; then
    LAUNCHER_SCRIPT="${HOME}/.local/bin/pycharm-env-launcher.sh"
else
    error "pycharm-env-launcher.sh not found!"
    error "Please ensure it's in the same directory or in ~/bin/"
    exit 1
fi

log "Using launcher: $LAUNCHER_SCRIPT"

# Confirm with user
echo ""
warning "This will close your current PyCharm session!"
read -p "Continue? (y/N): " -n 1 -r
echo

if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    log "Cancelled."
    exit 0
fi

# Close PyCharm
close_pycharm

# Launch with new environment
log "Launching PyCharm with environment from: $PROJECT_DIR"
"$LAUNCHER_SCRIPT" "$PROJECT_DIR"

success "Project switched successfully!"
