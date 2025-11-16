#!/usr/bin/env zsh
set -euo pipefail

# ============================================================================
# Obsidian Export Setup Validator
# ============================================================================
# Purpose: Validate all dependencies, configs, and permissions before export
# Usage: ./validate-obsidian-setup.sh [--fix]
# Returns: Exit 0 if all checks pass, non-zero otherwise
# ============================================================================

readonly VAULT_ROOT="/Volumes/code/repos/litellm"
readonly LOG_DIR="/tmp/obsidian-exports"
readonly FIX_MODE="${1:-}"

# Color codes
readonly RED='\033[0;31m'
readonly GREEN='\033[0;32m'
readonly YELLOW='\033[1;33m'
readonly BLUE='\033[0;34m'
readonly NC='\033[0m'

# Validation results
declare -a ERRORS=()
declare -a WARNINGS=()
declare -a SUCCESS=()

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

print_check() {
    echo -n "  [ ] $1... "
}

print_success() {
    echo "${GREEN}✓${NC}"
    SUCCESS+=("$1")
}

print_warning() {
    echo "${YELLOW}⚠${NC}"
    WARNINGS+=("$1: $2")
}

print_error() {
    echo "${RED}✗${NC}"
    ERRORS+=("$1: $2")
}

# ============================================================================
# Validation Functions
# ============================================================================

validate_system_tools() {
    print_header "Validating System Tools"

    # Check Node.js
    print_check "Node.js"
    if command -v node &>/dev/null; then
        local node_version=$(node --version)
        print_success "Node.js (${node_version})"
    else
        print_error "Node.js" "Not installed (install with: brew install node)"
    fi

    # Check npm
    print_check "npm"
    if command -v npm &>/dev/null; then
        local npm_version=$(npm --version)
        print_success "npm (v${npm_version})"
    else
        print_error "npm" "Not installed (comes with Node.js)"
    fi

    # Check Pandoc
    print_check "Pandoc"
    if command -v pandoc &>/dev/null; then
        local pandoc_version=$(pandoc --version | head -n1)
        print_success "Pandoc (${pandoc_version})"
    else
        print_error "Pandoc" "Not installed (install with: brew install pandoc)"
    fi

    # Check mermaid-filter
    print_check "mermaid-filter"
    if command -v mermaid-filter &>/dev/null; then
        print_success "mermaid-filter installed"
    else
        print_error "mermaid-filter" "Not installed (install with: npm install -g mermaid-filter)"
    fi

    # Check tmux (optional)
    print_check "tmux"
    if command -v tmux &>/dev/null; then
        local tmux_version=$(tmux -V)
        print_success "tmux (${tmux_version})"
    else
        print_warning "tmux" "Not installed (optional, for monitoring: brew install tmux)"
    fi

    # Check fswatch (optional)
    print_check "fswatch"
    if command -v fswatch &>/dev/null; then
        print_success "fswatch installed"
    else
        print_warning "fswatch" "Not installed (optional, for alerts: brew install fswatch)"
    fi
}

validate_configuration_files() {
    print_header "Validating Configuration Files"

    # Check mermaid-config.json
    print_check "Mermaid config"
    local mermaid_config="${VAULT_ROOT}/.mermaid-config.json"
    if [[ -f "${mermaid_config}" ]]; then
        if jq empty "${mermaid_config}" &>/dev/null; then
            print_success "Valid JSON"
        else
            print_error "Mermaid config" "Invalid JSON syntax"
        fi
    else
        print_error "Mermaid config" "Not found at ${mermaid_config}"
    fi

    # Check Pandoc plugin config
    print_check "Pandoc plugin config"
    local pandoc_config="${VAULT_ROOT}/.obsidian/plugins/obsidian-pandoc/data.json"
    if [[ -f "${pandoc_config}" ]]; then
        if jq empty "${pandoc_config}" &>/dev/null; then
            print_success "Valid JSON"
        else
            print_error "Pandoc config" "Invalid JSON syntax"
        fi
    else
        print_warning "Pandoc config" "Not found (plugin may not be installed)"
    fi
}

validate_scripts() {
    print_header "Validating Scripts"

    local scripts=(
        "obsidian-export-wrapper.sh"
        "obsidian-monitor.sh"
        "obsidian-export-alert.sh"
        "validate-obsidian-setup.sh"
        "install-obsidian-export.sh"
    )

    for script in "${scripts[@]}"; do
        local script_path="${VAULT_ROOT}/${script}"
        print_check "${script}"

        if [[ -f "${script_path}" ]]; then
            if [[ -x "${script_path}" ]]; then
                print_success "Executable"
            else
                if [[ "${FIX_MODE}" == "--fix" ]]; then
                    chmod +x "${script_path}"
                    print_success "Fixed (made executable)"
                else
                    print_warning "${script}" "Not executable (run with --fix)"
                fi
            fi
        else
            print_error "${script}" "Not found"
        fi
    done
}

validate_directories() {
    print_header "Validating Directories"

    # Check log directory
    print_check "Log directory"
    if [[ -d "${LOG_DIR}" ]]; then
        if [[ -w "${LOG_DIR}" ]]; then
            print_success "Writable"
        else
            print_error "Log directory" "Not writable"
        fi
    else
        if [[ "${FIX_MODE}" == "--fix" ]]; then
            mkdir -p "${LOG_DIR}"
            print_success "Created"
        else
            print_warning "Log directory" "Does not exist (will be created on first export)"
        fi
    fi

    # Check plugins directory
    print_check "Obsidian plugins"
    local plugins_dir="${VAULT_ROOT}/.obsidian/plugins"
    if [[ -d "${plugins_dir}" ]]; then
        print_success "Exists"
    else
        print_error "Plugins directory" "Not found"
    fi
}

# ============================================================================
# Summary
# ============================================================================

print_summary() {
    print_header "Validation Summary"

    echo "${GREEN}Successes: ${#SUCCESS[@]}${NC}"
    echo "${YELLOW}Warnings:  ${#WARNINGS[@]}${NC}"
    echo "${RED}Errors:    ${#ERRORS[@]}${NC}"
    echo ""

    if [[ ${#ERRORS[@]} -gt 0 ]]; then
        echo "${RED}❌ Errors (must fix):${NC}"
        for error in "${ERRORS[@]}"; do
            echo "  ${RED}•${NC} ${error}"
        done
        echo ""
    fi

    if [[ ${#WARNINGS[@]} -gt 0 ]]; then
        echo "${YELLOW}⚠️  Warnings (recommended):${NC}"
        for warning in "${WARNINGS[@]}"; do
            echo "  ${YELLOW}•${NC} ${warning}"
        done
        echo ""
    fi

    if [[ ${#ERRORS[@]} -eq 0 ]]; then
        echo "${GREEN}✓ All critical checks passed!${NC}"
        echo ""
        return 0
    else
        echo "${RED}✗ Critical errors found.${NC}"
        echo ""
        if [[ "${FIX_MODE}" != "--fix" ]]; then
            echo "Run with --fix to auto-fix some issues:"
            echo "  ./validate-obsidian-setup.sh --fix"
            echo ""
        fi
        return 1
    fi
}

# ============================================================================
# Main Execution
# ============================================================================

main() {
    clear
    echo "${BLUE}"
    echo "╔════════════════════════════════════════╗"
    echo "║  Obsidian Export Setup Validator      ║"
    echo "╚════════════════════════════════════════╝"
    echo "${NC}"

    if [[ "${FIX_MODE}" == "--fix" ]]; then
        echo "${YELLOW}Running in FIX mode${NC}"
        echo ""
    fi

    validate_system_tools
    validate_configuration_files
    validate_scripts
    validate_directories

    print_summary
}

main
