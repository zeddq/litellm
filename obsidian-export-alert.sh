#!/usr/bin/env zsh
set -euo pipefail

# ============================================================================
# Obsidian Export Alert System (fswatch-based)
# ============================================================================
# Purpose: Monitor export logs and send macOS notifications on errors
# Usage: ./obsidian-export-alert.sh [--daemon]
# Monitors: /tmp/obsidian-exports/*.log
# Alerts: macOS notifications for errors, warnings, and failures
# ============================================================================

readonly LOG_DIR="/tmp/obsidian-exports"
readonly ALERT_LOG="${LOG_DIR}/alerts.log"
readonly PID_FILE="${LOG_DIR}/alert-daemon.pid"
readonly DAEMON_MODE="${1:-}"

# Ensure log directory exists
mkdir -p "${LOG_DIR}"

# ============================================================================
# Logging Functions
# ============================================================================

log_alert() {
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[${timestamp}] [ALERT] $*" | tee -a "${ALERT_LOG}"
}

# ============================================================================
# Check Dependencies
# ============================================================================

if ! command -v fswatch &>/dev/null; then
    echo "Error: fswatch not found. Install with: brew install fswatch" >&2
    exit 1
fi

# ============================================================================
# Notification Function
# ============================================================================

send_notification() {
    local title="$1"
    local message="$2"
    local sound="${3:-Basso}"

    log_alert "Notification: ${title} - ${message}"

    # Use osascript for native macOS notifications
    osascript -e "display notification \"${message}\" with title \"${title}\" sound name \"${sound}\""
}

# ============================================================================
# Log Analysis Functions
# ============================================================================

check_for_errors() {
    local log_file="$1"
    local log_name=$(basename "${log_file}")

    # Check for ERROR patterns
    if tail -n 50 "${log_file}" | grep -qi '\[ERROR\]'; then
        local error_msg=$(tail -n 50 "${log_file}" | grep -i '\[ERROR\]' | tail -n 1)
        send_notification "Export Error (${log_name})" "${error_msg}" "Basso"
        return 0
    fi

    # Check for WARN patterns
    if tail -n 50 "${log_file}" | grep -qi '\[WARN\]'; then
        local warn_msg=$(tail -n 50 "${log_file}" | grep -i '\[WARN\]' | tail -n 1)
        send_notification "Export Warning (${log_name})" "${warn_msg}" "Funk"
        return 0
    fi

    return 1
}

check_for_success() {
    local log_file="$1"
    local log_name=$(basename "${log_file}")

    # Check for successful export completion
    if [[ "${log_name}" == "wrapper.log" ]]; then
        if tail -n 10 "${log_file}" | grep -q 'Export succeeded'; then
            send_notification "Export Successful" "PDF generated successfully" "Glass"
            return 0
        fi
    fi

    return 1
}

# ============================================================================
# File Change Handler
# ============================================================================

on_file_change() {
    local changed_file="$1"
    local file_name=$(basename "${changed_file}")

    log_alert "File changed: ${file_name}"

    # Check for errors first
    if check_for_errors "${changed_file}"; then
        return
    fi

    # Then check for success
    if check_for_success "${changed_file}"; then
        return
    fi
}

# ============================================================================
# Daemon Mode Functions
# ============================================================================

start_daemon() {
    # Check if daemon is already running
    if [[ -f "${PID_FILE}" ]]; then
        local old_pid=$(cat "${PID_FILE}")
        if kill -0 "${old_pid}" 2>/dev/null; then
            echo "Alert daemon already running (PID: ${old_pid})"
            exit 1
        else
            rm -f "${PID_FILE}"
        fi
    fi

    # Start daemon in background
    echo "Starting alert daemon..."
    nohup "$0" &>"${LOG_DIR}/alert-daemon.out" &
    local daemon_pid=$!
    echo "${daemon_pid}" > "${PID_FILE}"

    echo "Alert daemon started (PID: ${daemon_pid})"
    echo "Stop with: ./obsidian-export-alert.sh --stop"

    exit 0
}

stop_daemon() {
    if [[ ! -f "${PID_FILE}" ]]; then
        echo "No daemon running"
        return 1
    fi

    local daemon_pid=$(cat "${PID_FILE}")
    if kill -0 "${daemon_pid}" 2>/dev/null; then
        echo "Stopping daemon (PID: ${daemon_pid})..."
        kill "${daemon_pid}"
        rm -f "${PID_FILE}"
        echo "Daemon stopped"
    else
        echo "Daemon not running"
        rm -f "${PID_FILE}"
    fi
}

# ============================================================================
# Signal Handlers
# ============================================================================

cleanup() {
    log_alert "Alert system shutting down..."
    exit 0
}

trap cleanup SIGINT SIGTERM

# ============================================================================
# Main Logic
# ============================================================================

# Handle daemon mode
if [[ "${DAEMON_MODE}" == "--daemon" ]]; then
    start_daemon
elif [[ "${DAEMON_MODE}" == "--stop" ]]; then
    stop_daemon
    exit 0
fi

# Start monitoring
log_alert "=== Alert system started ==="
log_alert "Monitoring directory: ${LOG_DIR}"

# Send startup notification
send_notification "Export Monitor Active" "Watching for changes" "Tink"

# Monitor log directory with fswatch
echo "Watching for changes in ${LOG_DIR}..."
echo "Press Ctrl+C to stop"
echo ""

# Use fswatch to monitor all .log files
fswatch -0 -r -e ".*" -i "\\.log$" "${LOG_DIR}" | while IFS= read -r -d '' changed_file; do
    on_file_change "${changed_file}"
done
