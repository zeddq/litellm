#!/usr/bin/env zsh
set -euo pipefail

# ============================================================================
# Obsidian Export Monitor (tmux 4-pane viewer)
# ============================================================================
# Purpose: Real-time monitoring of Obsidian exports with 4-pane log display
# Usage: ./obsidian-monitor.sh [session_name]
# Layout: Top-left: wrapper | Top-right: pandoc
#         Bottom-left: mermaid | Bottom-right: system
# ============================================================================

readonly SESSION_NAME="${1:-obsidian-export-monitor}"
readonly LOG_DIR="/tmp/obsidian-exports"

# Log files
readonly WRAPPER_LOG="${LOG_DIR}/wrapper.log"
readonly PANDOC_LOG="${LOG_DIR}/pandoc.log"
readonly MERMAID_LOG="${LOG_DIR}/mermaid.log"
readonly SYSTEM_LOG="${LOG_DIR}/system.log"

# Ensure log directory and files exist
mkdir -p "${LOG_DIR}"
touch "${WRAPPER_LOG}" "${PANDOC_LOG}" "${MERMAID_LOG}" "${SYSTEM_LOG}"

# Colors for log titles
readonly COLOR_WRAPPER="\033[1;34m"  # Blue
readonly COLOR_PANDOC="\033[1;32m"   # Green
readonly COLOR_MERMAID="\033[1;35m"  # Magenta
readonly COLOR_SYSTEM="\033[1;33m"   # Yellow
readonly COLOR_RESET="\033[0m"

# ============================================================================
# Check Dependencies
# ============================================================================

if ! command -v tmux &>/dev/null; then
    echo "Error: tmux not found. Install with: brew install tmux" >&2
    exit 1
fi

# ============================================================================
# Tmux Session Management
# ============================================================================

# Kill existing session if present
if tmux has-session -t "${SESSION_NAME}" 2>/dev/null; then
    echo "Killing existing session: ${SESSION_NAME}"
    tmux kill-session -t "${SESSION_NAME}"
fi

# Create new tmux session (detached)
echo "Creating tmux session: ${SESSION_NAME}"
tmux new-session -d -s "${SESSION_NAME}" -n "logs"

# ============================================================================
# Pane Layout Configuration (2x2 grid)
# ============================================================================

# Split horizontally (create top and bottom)
tmux split-window -v -t "${SESSION_NAME}:0"

# Split top pane vertically (create top-left and top-right)
tmux select-pane -t "${SESSION_NAME}:0.0"
tmux split-window -h -t "${SESSION_NAME}:0.0"

# Split bottom pane vertically (create bottom-left and bottom-right)
tmux select-pane -t "${SESSION_NAME}:0.2"
tmux split-window -h -t "${SESSION_NAME}:0.2"

# ============================================================================
# Pane Titles and Content
# ============================================================================

# Top-left: Wrapper logs (pane 0)
tmux select-pane -t "${SESSION_NAME}:0.0" -T "Wrapper Log"
tmux send-keys -t "${SESSION_NAME}:0.0" "clear" C-m
tmux send-keys -t "${SESSION_NAME}:0.0" "echo '${COLOR_WRAPPER}=== WRAPPER LOG ===${COLOR_RESET}'" C-m
tmux send-keys -t "${SESSION_NAME}:0.0" "tail -f '${WRAPPER_LOG}'" C-m

# Top-right: Pandoc logs (pane 1)
tmux select-pane -t "${SESSION_NAME}:0.1" -T "Pandoc Log"
tmux send-keys -t "${SESSION_NAME}:0.1" "clear" C-m
tmux send-keys -t "${SESSION_NAME}:0.1" "echo '${COLOR_PANDOC}=== PANDOC LOG ===${COLOR_RESET}'" C-m
tmux send-keys -t "${SESSION_NAME}:0.1" "tail -f '${PANDOC_LOG}'" C-m

# Bottom-left: Mermaid logs (pane 2)
tmux select-pane -t "${SESSION_NAME}:0.2" -T "Mermaid Log"
tmux send-keys -t "${SESSION_NAME}:0.2" "clear" C-m
tmux send-keys -t "${SESSION_NAME}:0.2" "echo '${COLOR_MERMAID}=== MERMAID LOG ===${COLOR_RESET}'" C-m
tmux send-keys -t "${SESSION_NAME}:0.2" "tail -f '${MERMAID_LOG}'" C-m

# Bottom-right: System logs (pane 3)
tmux select-pane -t "${SESSION_NAME}:0.3" -T "System Log"
tmux send-keys -t "${SESSION_NAME}:0.3" "clear" C-m
tmux send-keys -t "${SESSION_NAME}:0.3" "echo '${COLOR_SYSTEM}=== SYSTEM LOG ===${COLOR_RESET}'" C-m
tmux send-keys -t "${SESSION_NAME}:0.3" "tail -f '${SYSTEM_LOG}'" C-m

# ============================================================================
# Status Line Configuration
# ============================================================================

tmux set-option -t "${SESSION_NAME}" status on
tmux set-option -t "${SESSION_NAME}" status-position bottom
tmux set-option -t "${SESSION_NAME}" status-style "bg=black,fg=white"
tmux set-option -t "${SESSION_NAME}" status-left "[Obsidian Export Monitor] "
tmux set-option -t "${SESSION_NAME}" status-left-length 40
tmux set-option -t "${SESSION_NAME}" status-right "%Y-%m-%d %H:%M:%S "
tmux set-option -t "${SESSION_NAME}" status-interval 1

# ============================================================================
# Pane Borders and Styling
# ============================================================================

tmux set-option -t "${SESSION_NAME}" pane-border-style "fg=colour240"
tmux set-option -t "${SESSION_NAME}" pane-active-border-style "fg=colour33"
tmux set-option -t "${SESSION_NAME}" pane-border-status top
tmux set-option -t "${SESSION_NAME}" pane-border-format "#{pane_title}"

# ============================================================================
# Mouse Support
# ============================================================================

tmux set-option -t "${SESSION_NAME}" mouse on

# ============================================================================
# Attach to Session
# ============================================================================

echo ""
echo "=========================================="
echo "  Obsidian Export Monitor Started"
echo "=========================================="
echo ""
echo "Layout:"
echo "  Top-left:     Wrapper logs"
echo "  Top-right:    Pandoc logs"
echo "  Bottom-left:  Mermaid logs"
echo "  Bottom-right: System logs"
echo ""
echo "Controls:"
echo "  - Mouse: Click and scroll"
echo "  - Ctrl+B + Arrow: Navigate panes"
echo "  - Ctrl+B + D: Detach"
echo "  - Ctrl+C: Exit"
echo ""
echo "Attaching..."
echo ""

# Attach to session
tmux attach-session -t "${SESSION_NAME}"
