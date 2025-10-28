#!/bin/bash
# PyCharm Environment Launcher
# Launches PyCharm with environment variables from .envrc or .env files
# Usage: ./pycharm-env-launcher.sh [project-directory]

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
PROJECT_DIR="${1:-.}"
LOG_FILE="${HOME}/.pycharm-env-launcher.log"

log() {
    echo -e "${BLUE}[$(date '+%Y-%m-%d %H:%M:%S')]${NC} $*" | tee -a "$LOG_FILE"
}

error() {
    echo -e "${RED}[ERROR]${NC} $*" | tee -a "$LOG_FILE"
}

success() {
    echo -e "${GREEN}[SUCCESS]${NC} $*" | tee -a "$LOG_FILE"
}

warning() {
    echo -e "${YELLOW}[WARNING]${NC} $*" | tee -a "$LOG_FILE"
}

# Change to project directory
if [ ! -d "$PROJECT_DIR" ]; then
    error "Directory not found: $PROJECT_DIR"
    exit 1
fi

cd "$PROJECT_DIR" || exit 1
PROJECT_DIR="$(pwd)"  # Get absolute path
log "Project directory: $PROJECT_DIR"

# Function to find PyCharm executable
find_pycharm() {
    local pycharm_path=""

    # Try common locations in order of preference
    if command -v charm &> /dev/null; then
        pycharm_path="charm"
        log "Found PyCharm command: charm (JetBrains Toolbox)"
    elif command -v pycharm &> /dev/null; then
        pycharm_path="pycharm"
        log "Found PyCharm command: pycharm"
    elif [ -d "/Applications/PyCharm.app" ]; then
        pycharm_path="/Applications/PyCharm.app/Contents/MacOS/pycharm"
        log "Found PyCharm.app in Applications"
    elif [ -d "/Applications/PyCharm CE.app" ]; then
        pycharm_path="/Applications/PyCharm CE.app/Contents/MacOS/pycharm"
        log "Found PyCharm CE.app in Applications"
    elif [ -d "${HOME}/Applications/PyCharm.app" ]; then
        pycharm_path="${HOME}/Applications/PyCharm.app/Contents/MacOS/pycharm"
        log "Found PyCharm.app in ~/Applications"
    else
        error "PyCharm not found! Please install PyCharm or add it to PATH"
        exit 1
    fi

    echo "$pycharm_path"
}

# Function to load .env file manually
load_env_file() {
    local env_file="$1"
    if [ -f "$env_file" ]; then
        log "Loading environment from: $env_file"

        # Export variables, skipping comments and empty lines
        while IFS= read -r line || [ -n "$line" ]; do
            # Skip comments and empty lines
            [[ "$line" =~ ^[[:space:]]*# ]] && continue
            [[ -z "$line" ]] && continue

            # Export the variable (handle quotes properly)
            if [[ "$line" =~ ^[[:space:]]*([A-Za-z_][A-Za-z0-9_]*)[[:space:]]*=[[:space:]]*(.*)$ ]]; then
                key="${BASH_REMATCH[1]}"
                value="${BASH_REMATCH[2]}"

                # Remove surrounding quotes if present
                value="${value%\"}"
                value="${value#\"}"
                value="${value%\'}"
                value="${value#\'}"

                export "$key=$value"
                log "  ✓ Exported: $key"
            fi
        done < "$env_file"

        return 0
    fi
    return 1
}

# Function to load environment variables
load_environment() {
    local loaded=false

    # Try direnv first (if available)
    if command -v direnv &> /dev/null && [ -f .envrc ]; then
        log "direnv found, loading .envrc..."

        # Check if .envrc is allowed
        if direnv status 2>/dev/null | grep -q "Found RC allowed true"; then
            eval "$(direnv export bash 2>/dev/null)"
            success "Environment loaded via direnv"
            loaded=true
        else
            warning ".envrc found but not allowed. Run: direnv allow"
            warning "Falling back to manual .env loading..."
        fi
    fi

    # If direnv didn't work, try loading .env files manually
    if [ "$loaded" = false ]; then
        # Try loading .env files in order of precedence
        if load_env_file ".env.local"; then
            loaded=true
        elif load_env_file ".env"; then
            loaded=true
        fi
    fi

    if [ "$loaded" = false ]; then
        warning "No .envrc or .env file found in project directory"
        warning "PyCharm will launch with system environment only"
    fi
}

# Function to display loaded environment variables
show_environment() {
    log "Environment variables loaded:"

    # List of common variable patterns to show
    local patterns=("API_KEY" "TOKEN" "SECRET" "DATABASE" "CUSTOM_" "OPENAI" "ANTHROPIC")
    local found=false

    for pattern in "${patterns[@]}"; do
        for var in $(env | grep -i "$pattern" | cut -d= -f1); do
            local value="${!var}"
            # Mask sensitive values
            if [[ "$var" =~ (KEY|TOKEN|SECRET|PASSWORD) ]]; then
                local masked="${value:0:10}...${value: -4}"
                log "  $var=$masked"
            else
                log "  $var=$value"
            fi
            found=true
        done
    done

    if [ "$found" = false ]; then
        log "  (No matching variables found - showing first 5 env vars)"
        env | head -5 | while read -r line; do
            log "  $line"
        done
    fi
}

# Main execution
main() {
    log "========================================"
    log "PyCharm Environment Launcher"
    log "========================================"

    # Load environment variables
    load_environment

    # Show what was loaded
    show_environment

    # Find PyCharm
    PYCHARM_PATH=$(find_pycharm)

    log "========================================"
    log "Launching PyCharm..."
    log "Command: $PYCHARM_PATH $PROJECT_DIR"
    log "========================================"

    # Launch PyCharm with the current environment
    # Using 'open' on macOS ensures the app launches as a GUI app
    if [[ "$OSTYPE" == "darwin"* ]] && [[ "$PYCHARM_PATH" == *.app* ]]; then
        # Extract app bundle path
        APP_BUNDLE=$(echo "$PYCHARM_PATH" | sed 's|/Contents/MacOS/pycharm||')
        success "Launching PyCharm (macOS): $APP_BUNDLE"
        open -a "$APP_BUNDLE" "$PROJECT_DIR"
    else
        # For Linux or when using JetBrains Toolbox command
        success "Launching PyCharm: $PYCHARM_PATH"
        "$PYCHARM_PATH" "$PROJECT_DIR" &
    fi

    success "PyCharm launched! Check $LOG_FILE for details"
}

# Run main function
main
