#!/usr/bin/env zsh
set -euo pipefail

# ============================================================================
# Obsidian Export Wrapper with Debug Logging
# ============================================================================
# Purpose: Wrap Pandoc exports with comprehensive 5-layer debug logging
# Usage: Called by Obsidian Pandoc plugin during exports
# Logs: /tmp/obsidian-exports/{wrapper,pandoc,mermaid,filter,system}.log
# ============================================================================

# Configuration
readonly LOG_DIR="/tmp/obsidian-exports"
readonly WRAPPER_LOG="${LOG_DIR}/wrapper.log"
readonly PANDOC_LOG="${LOG_DIR}/pandoc.log"
readonly MERMAID_LOG="${LOG_DIR}/mermaid.log"
readonly SYSTEM_LOG="${LOG_DIR}/system.log"
readonly TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

# Ensure log directory exists
mkdir -p "${LOG_DIR}"

# ============================================================================
# Logging Functions
# ============================================================================

log_wrapper() {
    echo "[${TIMESTAMP}] [WRAPPER] $*" | tee -a "${WRAPPER_LOG}"
}

log_system() {
    echo "[${TIMESTAMP}] [SYSTEM] $*" | tee -a "${SYSTEM_LOG}"
}

log_error() {
    echo "[${TIMESTAMP}] [ERROR] $*" | tee -a "${WRAPPER_LOG}" >&2
}

# ============================================================================
# Layer 1: Wrapper Layer - Pre-Export Validation
# ============================================================================

log_wrapper "=== Export wrapper started ==="
log_wrapper "Command: $0 $*"
log_wrapper "PWD: $(pwd)"
log_wrapper "User: $(whoami)"

# Validate required tools
log_wrapper "Validating required tools..."

if ! command -v pandoc &>/dev/null; then
    log_error "pandoc not found in PATH"
    log_error "PATH: ${PATH}"
    exit 1
fi

if ! command -v mermaid-filter &>/dev/null; then
    log_error "mermaid-filter not found in PATH"
    log_error "PATH: ${PATH}"
    exit 1
fi

PANDOC_VERSION=$(pandoc --version | head -n1)
log_wrapper "pandoc: ${PANDOC_VERSION}"

# ============================================================================
# Layer 2: System Layer - Environment Capture
# ============================================================================

log_system "=== System environment ==="
log_system "PATH: ${PATH}"
log_system "HOME: ${HOME}"
log_system "SHELL: ${SHELL}"

# Capture environment variables
env | grep -i 'mermaid\|pandoc\|node' | while read -r line; do
    log_system "ENV: ${line}"
done

# ============================================================================
# Layer 3: Pandoc Layer - Configure Verbose Logging
# ============================================================================

log_wrapper "Configuring Pandoc logging..."

# Build Pandoc command with verbose flags
PANDOC_ARGS=(
    "--verbose"
    "--log=${PANDOC_LOG}"
    "--filter=/opt/homebrew/bin/mermaid-filter"
)

# Add user-provided arguments
PANDOC_ARGS+=("$@")

log_wrapper "Pandoc arguments:"
for arg in "${PANDOC_ARGS[@]}"; do
    log_wrapper "  ${arg}"
done

# ============================================================================
# Layer 4: Filter Layer - Mermaid Filter Configuration
# ============================================================================

log_wrapper "Configuring mermaid-filter..."

# Set environment variables for mermaid-filter
export MERMAID_FILTER_FORMAT="png"
export MERMAID_FILTER_THEME="default"
export MERMAID_FILTER_WIDTH="1200"
export MERMAID_FILTER_BACKGROUND="transparent"
export MERMAID_FILTER_LOG="${MERMAID_LOG}"
export MERMAID_FILTER_VERBOSE="1"
export MERMAID_CONFIG="/Volumes/code/repos/litellm/.mermaid-config.json"

# Verify mermaid config exists
if [[ ! -f "${MERMAID_CONFIG}" ]]; then
    log_error "Mermaid config not found: ${MERMAID_CONFIG}"
    exit 1
fi

log_wrapper "Mermaid config: ${MERMAID_CONFIG}"

# ============================================================================
# Layer 5: Execution Layer - Run Pandoc with Error Capture
# ============================================================================

log_wrapper "=== Starting Pandoc export ==="

# Create a temporary file for stderr capture
STDERR_TMP=$(mktemp)
EXIT_CODE=0

# Execute Pandoc with full error capture
if pandoc "${PANDOC_ARGS[@]}" 2>"${STDERR_TMP}"; then
    EXIT_CODE=0
    log_wrapper "Export succeeded"
else
    EXIT_CODE=$?
    log_error "Export failed with exit code: ${EXIT_CODE}"
fi

# Capture stderr output
if [[ -s "${STDERR_TMP}" ]]; then
    log_wrapper "=== Pandoc stderr output ==="
    while IFS= read -r line; do
        log_wrapper "STDERR: ${line}"
    done < "${STDERR_TMP}"
fi

rm -f "${STDERR_TMP}"

# ============================================================================
# Post-Export Analysis
# ============================================================================

log_wrapper "=== Post-export analysis ==="

# Check for generated files
if [[ -d "${LOG_DIR}" ]]; then
    log_wrapper "Generated files in ${LOG_DIR}:"
    find "${LOG_DIR}" -type f -mmin -5 | while read -r file; do
        size=$(stat -f%z "${file}" 2>/dev/null || echo "unknown")
        log_wrapper "  ${file} (${size} bytes)"
    done
fi

# ============================================================================
# Cleanup and Exit
# ============================================================================

log_wrapper "=== Export wrapper finished ==="
log_wrapper "Exit code: ${EXIT_CODE}"
log_wrapper "Total logs written to: ${LOG_DIR}"

exit ${EXIT_CODE}
