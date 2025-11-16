#!/usr/bin/env zsh
set -euo pipefail

# ============================================================================
# Obsidian Export System Installer
# ============================================================================
# Purpose: Automated installation of Obsidian export dependencies and configs
# Usage: ./install-obsidian-export.sh
# Installs: Homebrew packages, npm packages, configures Obsidian plugins
# ============================================================================

readonly VAULT_ROOT="/Volumes/code/repos/litellm"
readonly LOG_DIR="/tmp/obsidian-exports"

# Color codes
readonly RED='\033[0;31m'
readonly GREEN='\033[0;32m'
readonly YELLOW='\033[1;33m'
readonly BLUE='\033[0;34m'
readonly NC='\033[0m'

# ============================================================================
# Output Functions
# ============================================================================

print_header() {
    echo ""
    echo "${BLUE}========================================${NC}"
    echo "${BLUE}  $1${NC}"
    echo "${BLUE}========================================${NC}"
    echo ""
}

print_step() {
    echo "${GREEN}▶${NC} $1"
}

print_error() {
    echo "${RED}✗${NC} $1" >&2
}

print_warning() {
    echo "${YELLOW}⚠${NC} $1"
}

print_success() {
    echo "${GREEN}✓${NC} $1"
}

# ============================================================================
# Installation Functions
# ============================================================================

install_homebrew() {
    print_header "Installing Homebrew"

    if command -v brew &>/dev/null; then
        print_success "Homebrew already installed"
        print_step "Updating Homebrew..."
        brew update
    else
        print_step "Installing Homebrew..."
        /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

        # Add Homebrew to PATH for this session
        eval "$(/opt/homebrew/bin/brew shellenv)"

        print_success "Homebrew installed"
    fi
}

install_system_packages() {
    print_header "Installing System Packages"

    local packages=(
        "pandoc"
        "node"
        "tmux"
        "fswatch"
        "jq"
    )

    for package in "${packages[@]}"; do
        print_step "Installing ${package}..."
        if brew list "${package}" &>/dev/null; then
            print_success "${package} already installed"
        else
            brew install "${package}"
            print_success "${package} installed"
        fi
    done
}

install_npm_packages() {
    print_header "Installing npm Packages"

    print_step "Installing mermaid-filter globally..."
    if npm list -g mermaid-filter &>/dev/null; then
        print_success "mermaid-filter already installed"
    else
        npm install -g mermaid-filter
        print_success "mermaid-filter installed"
    fi

    print_step "Installing mermaid-cli (mmdc) globally..."
    if npm list -g @mermaid-js/mermaid-cli &>/dev/null; then
        print_success "@mermaid-js/mermaid-cli already installed"
    else
        npm install -g @mermaid-js/mermaid-cli
        print_success "@mermaid-js/mermaid-cli installed"
    fi
}

create_directories() {
    print_header "Creating Directories"

    local directories=(
        "${LOG_DIR}"
        "${VAULT_ROOT}/.obsidian/plugins/obsidian-pandoc"
        "${VAULT_ROOT}/.obsidian/plugins/show-hidden-files"
        "${VAULT_ROOT}/.obsidian/plugins/console-debugger"
    )

    for dir in "${directories[@]}"; do
        if [[ ! -d "${dir}" ]]; then
            print_step "Creating ${dir}..."
            mkdir -p "${dir}"
            print_success "Directory created"
        else
            print_success "${dir} already exists"
        fi
    done
}

set_permissions() {
    print_header "Setting Script Permissions"

    local scripts=(
        "obsidian-export-wrapper.sh"
        "obsidian-monitor.sh"
        "obsidian-export-alert.sh"
        "validate-obsidian-setup.sh"
        "install-obsidian-export.sh"
    )

    for script in "${scripts[@]}"; do
        local script_path="${VAULT_ROOT}/${script}"
        if [[ -f "${script_path}" ]]; then
            print_step "Making ${script} executable..."
            chmod +x "${script_path}"
            print_success "${script} is now executable"
        else
            print_warning "${script} not found (may need to be created)"
        fi
    done
}

configure_shell() {
    print_header "Configuring Shell Environment"

    local shell_rc="${HOME}/.zshrc"

    # Check if Homebrew is in PATH
    if ! grep -q "/opt/homebrew/bin" "${shell_rc}" 2>/dev/null; then
        print_step "Adding Homebrew to PATH in ${shell_rc}..."
        echo "" >> "${shell_rc}"
        echo "# Added by Obsidian Export Installer" >> "${shell_rc}"
        echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> "${shell_rc}"
        print_success "Homebrew added to PATH"
    else
        print_success "Homebrew already in PATH"
    fi

    # Check if npm global bin is in PATH
    if command -v npm &>/dev/null; then
        local npm_prefix=$(npm prefix -g)
        if ! grep -q "${npm_prefix}/bin" "${shell_rc}" 2>/dev/null; then
            print_step "Adding npm globals to PATH..."
            echo "export PATH=\"${npm_prefix}/bin:\$PATH\"" >> "${shell_rc}"
            print_success "npm globals added to PATH"
        else
            print_success "npm globals already in PATH"
        fi
    fi

    print_warning "Shell configuration updated. Run: source ${shell_rc}"
}

verify_installation() {
    print_header "Verifying Installation"

    print_step "Running validation script..."
    if [[ -f "${VAULT_ROOT}/validate-obsidian-setup.sh" ]]; then
        "${VAULT_ROOT}/validate-obsidian-setup.sh" --fix
    else
        print_error "Validation script not found"
        return 1
    fi
}

# ============================================================================
# Main Installation Flow
# ============================================================================

main() {
    clear
    echo "${BLUE}"
    echo "╔════════════════════════════════════════╗"
    echo "║  Obsidian Export System Installer     ║"
    echo "╚════════════════════════════════════════╝"
    echo "${NC}"
    echo ""
    echo "This script will install:"
    echo "  • Homebrew (if not installed)"
    echo "  • Pandoc, Node.js, tmux, fswatch, jq"
    echo "  • mermaid-filter, mermaid-cli (npm global)"
    echo "  • Configure directories and permissions"
    echo ""

    read -q "REPLY?Continue with installation? (y/n) "
    echo ""

    if [[ ! "${REPLY}" =~ ^[Yy]$ ]]; then
        echo "Installation cancelled."
        exit 0
    fi

    # Run installation steps
    install_homebrew
    install_system_packages
    install_npm_packages
    create_directories
    set_permissions
    configure_shell

    # Final verification
    echo ""
    verify_installation

    # Success message
    print_header "Installation Complete"
    echo "${GREEN}✓ All dependencies installed successfully!${NC}"
    echo ""
    echo "Next steps:"
    echo "  1. Reload your shell: source ~/.zshrc"
    echo "  2. Start monitoring: ./obsidian-monitor.sh"
    echo "  3. Start alerts: ./obsidian-export-alert.sh --daemon"
    echo "  4. Export from Obsidian (Cmd+P → Export)"
    echo ""
    echo "For help, run: ./validate-obsidian-setup.sh"
    echo ""
}

main
