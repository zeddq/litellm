#!/bin/bash
# Setup PyCharm Environment Launcher
# Installs launcher scripts and configures shell aliases

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log() {
    echo -e "${BLUE}[INFO]${NC} $*"
}

success() {
    echo -e "${GREEN}[SUCCESS]${NC} $*"
}

warning() {
    echo -e "${YELLOW}[WARNING]${NC} $*"
}

# Determine installation directory
INSTALL_DIR="${HOME}/bin"
mkdir -p "$INSTALL_DIR"

log "Installing PyCharm environment launcher to: $INSTALL_DIR"

# Copy scripts
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

cp "$SCRIPT_DIR/pycharm-env-launcher.sh" "$INSTALL_DIR/"
cp "$SCRIPT_DIR/pycharm-project-switcher.sh" "$INSTALL_DIR/"

# Make executable
chmod +x "$INSTALL_DIR/pycharm-env-launcher.sh"
chmod +x "$INSTALL_DIR/pycharm-project-switcher.sh"

success "Scripts installed to $INSTALL_DIR"

# Detect shell
SHELL_NAME=$(basename "$SHELL")
SHELL_RC=""

case "$SHELL_NAME" in
    bash)
        SHELL_RC="${HOME}/.bashrc"
        [ -f "${HOME}/.bash_profile" ] && SHELL_RC="${HOME}/.bash_profile"
        ;;
    zsh)
        SHELL_RC="${HOME}/.zshrc"
        ;;
    fish)
        SHELL_RC="${HOME}/.config/fish/config.fish"
        warning "Fish shell detected. You'll need to manually add functions."
        ;;
    *)
        warning "Unknown shell: $SHELL_NAME"
        ;;
esac

if [ -n "$SHELL_RC" ] && [ "$SHELL_NAME" != "fish" ]; then
    log "Adding aliases to: $SHELL_RC"

    # Create backup
    cp "$SHELL_RC" "${SHELL_RC}.backup.$(date +%Y%m%d_%H%M%S)"

    # Add aliases if not already present
    if ! grep -q "pycharm-env-launcher" "$SHELL_RC"; then
        cat >> "$SHELL_RC" <<'EOF'

# PyCharm Environment Launcher
# Added by setup-pycharm-env.sh
export PATH="$HOME/bin:$PATH"

# Launch PyCharm with environment variables from current directory
alias pycharm-env='~/bin/pycharm-env-launcher.sh'

# Switch to a different project with its own environment
alias pycharm-switch='~/bin/pycharm-project-switcher.sh'

# Quick launch for current directory
pycharm-here() {
    ~/bin/pycharm-env-launcher.sh .
}

# Open project with environment (from anywhere)
pycharm-open() {
    if [ -z "$1" ]; then
        echo "Usage: pycharm-open <project-directory>"
        return 1
    fi
    ~/bin/pycharm-env-launcher.sh "$1"
}
EOF
        success "Aliases added to $SHELL_RC"
    else
        warning "Aliases already exist in $SHELL_RC, skipping..."
    fi
fi

# Create desktop launcher (macOS)
if [[ "$OSTYPE" == "darwin"* ]]; then
    log "Creating macOS Application launcher..."

    AUTOMATOR_APP="${HOME}/Applications/PyCharm with Env.app"

    # Create a simple shell script wrapper for Automator
    WRAPPER_SCRIPT="${HOME}/bin/pycharm-env-wrapper-for-automator.sh"

    cat > "$WRAPPER_SCRIPT" <<'EOF'
#!/bin/bash
# Get the frontmost Finder window path or use Desktop
PROJECT_DIR=$(osascript <<'APPLESCRIPT'
    tell application "Finder"
        try
            set frontWin to folder of front window as string
            set frontWinPath to POSIX path of frontWin
            return frontWinPath
        on error
            return (POSIX path of (path to desktop))
        end try
    end tell
APPLESCRIPT
)

# Launch PyCharm with environment
~/bin/pycharm-env-launcher.sh "$PROJECT_DIR"
EOF

    chmod +x "$WRAPPER_SCRIPT"

    warning "To create a clickable app launcher:"
    echo "1. Open Automator"
    echo "2. Create new Application"
    echo "3. Add 'Run Shell Script' action"
    echo "4. Paste: ~/bin/pycharm-env-wrapper-for-automator.sh"
    echo "5. Save as: $AUTOMATOR_APP"
fi

# Instructions
echo ""
success "Installation complete!"
echo ""
log "========================================"
log "Usage Instructions:"
log "========================================"
echo ""
log "1. Reload your shell configuration:"
echo "   source $SHELL_RC"
echo ""
log "2. Launch PyCharm with environment:"
echo "   pycharm-env                    # Launch from current directory"
echo "   pycharm-env ~/path/to/project  # Launch specific project"
echo "   pycharm-here                   # Quick launch current dir"
echo "   pycharm-open ~/my/project      # Open project from anywhere"
echo ""
log "3. Switch between projects (closes and reopens):"
echo "   pycharm-switch ~/path/to/other/project"
echo ""
log "4. Create .env or .envrc in your project:"
echo "   echo 'OPENAI_API_KEY=sk-...' > .env"
echo "   direnv allow  # If using direnv"
echo ""
warning "Note: The launcher will load .envrc (via direnv) or .env files"
warning "      Environment changes require relaunching PyCharm"
echo ""
success "Enjoy your PyCharm with environment variables! 🚀"
