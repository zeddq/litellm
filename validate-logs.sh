#!/bin/bash
# Validate log file quality and completeness
# Part of Obsidian PDF Export Test Suite

LOG_DIR="${1:-$HOME/.obsidian-pandoc/logs}"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "Obsidian PDF Export - Log Validation"
echo "====================================="
echo "Validating logs in: $LOG_DIR"
echo

ISSUES=0
WARNINGS=0

# Check if log directory exists
if [ ! -d "$LOG_DIR" ]; then
    echo -e "${RED}❌ Log directory not found: $LOG_DIR${NC}"
    echo "   Create with: mkdir -p $LOG_DIR"
    exit 1
fi

echo "1. Checking log files exist..."
echo "-------------------------------"

# Check log files exist
for log in wrapper.log pandoc.log mermaid.log; do
    if [ ! -f "$LOG_DIR/$log" ]; then
        echo -e "${RED}❌ Missing log file: $log${NC}"
        ((ISSUES++))
    else
        echo -e "${GREEN}✅ Found: $log${NC}"
    fi
done

echo

# Validate log format
echo "2. Checking log format..."
echo "-------------------------"

for log in wrapper.log pandoc.log mermaid.log; do
    if [ -f "$LOG_DIR/$log" ]; then
        # Check if file has content
        if [ ! -s "$LOG_DIR/$log" ]; then
            echo -e "${YELLOW}⚠️  $log: Empty file${NC}"
            ((WARNINGS++))
            continue
        fi

        # Check for timestamps (ISO 8601 format)
        if grep -qE '[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}' "$LOG_DIR/$log"; then
            echo -e "${GREEN}✅ $log: Timestamps valid (ISO 8601)${NC}"
        elif grep -qE '[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}' "$LOG_DIR/$log"; then
            echo -e "${GREEN}✅ $log: Timestamps valid (alternative format)${NC}"
        else
            echo -e "${RED}❌ $log: Missing or invalid timestamps${NC}"
            echo "   Expected format: 2025-11-16T10:30:00 or 2025-11-16 10:30:00"
            ((ISSUES++))
        fi

        # Check for component tags
        component=$(basename "$log" .log | tr 'a-z' 'A-Z')
        if grep -q "\[$component\]" "$LOG_DIR/$log"; then
            echo -e "${GREEN}✅ $log: Component tags present [$component]${NC}"
        else
            echo -e "${YELLOW}⚠️  $log: Missing component tags [$component]${NC}"
            echo "   Expected format: [$component] Log message"
            ((WARNINGS++))
        fi

        # Check for error markers
        error_count=$(grep -ci "error" "$LOG_DIR/$log" || true)
        if [ $error_count -gt 0 ]; then
            echo -e "${YELLOW}⚠️  $log: Contains $error_count error entries${NC}"
            echo "   Review errors with: grep -i error $LOG_DIR/$log"
        fi
    fi
done

echo

# Check log size
echo "3. Checking log sizes..."
echo "------------------------"

for log in wrapper.log pandoc.log mermaid.log; do
    if [ -f "$LOG_DIR/$log" ]; then
        size=$(stat -f%z "$LOG_DIR/$log" 2>/dev/null || stat -c%s "$LOG_DIR/$log")
        size_mb=$((size / 1024 / 1024))
        size_kb=$((size / 1024))

        if [ $size_mb -gt 10 ]; then
            echo -e "${YELLOW}⚠️  $log: Large file (${size_mb}MB) - consider rotation${NC}"
            echo "   Rotate with: mv $LOG_DIR/$log $LOG_DIR/$log.old"
            ((WARNINGS++))
        elif [ $size_mb -gt 0 ]; then
            echo -e "${GREEN}✅ $log: Size OK (${size_mb}MB)${NC}"
        else
            echo -e "${GREEN}✅ $log: Size OK (${size_kb}KB)${NC}"
        fi
    fi
done

echo

# Check log age
echo "4. Checking log age..."
echo "----------------------"

for log in wrapper.log pandoc.log mermaid.log; do
    if [ -f "$LOG_DIR/$log" ]; then
        # Get last modification time
        if [[ "$OSTYPE" == "darwin"* ]]; then
            # macOS
            log_age=$(stat -f%m "$LOG_DIR/$log")
        else
            # Linux
            log_age=$(stat -c%Y "$LOG_DIR/$log")
        fi

        current_time=$(date +%s)
        age_seconds=$((current_time - log_age))
        age_hours=$((age_seconds / 3600))
        age_days=$((age_seconds / 86400))

        if [ $age_days -gt 7 ]; then
            echo -e "${YELLOW}⚠️  $log: Last updated ${age_days} days ago${NC}"
            echo "   Run an export to update logs"
        elif [ $age_hours -gt 24 ]; then
            echo -e "${GREEN}✅ $log: Last updated ${age_days} days ago${NC}"
        else
            echo -e "${GREEN}✅ $log: Last updated ${age_hours} hours ago${NC}"
        fi
    fi
done

echo

# Check for recent export activity
echo "5. Checking recent activity..."
echo "------------------------------"

recent_activity=false
for log in wrapper.log pandoc.log mermaid.log; do
    if [ -f "$LOG_DIR/$log" ]; then
        # Check for entries in last 24 hours
        yesterday=$(date -v-1d +%Y-%m-%d 2>/dev/null || date -d "yesterday" +%Y-%m-%d)
        today=$(date +%Y-%m-%d)

        if grep -qE "($yesterday|$today)" "$LOG_DIR/$log"; then
            recent_activity=true
            break
        fi
    fi
done

if $recent_activity; then
    echo -e "${GREEN}✅ Recent export activity detected (last 24 hours)${NC}"
else
    echo -e "${YELLOW}⚠️  No recent export activity (last 24 hours)${NC}"
    echo "   This is normal if no exports were run recently"
fi

echo

# Summary
echo "========================================="
echo "Validation Summary"
echo "========================================="

if [ $ISSUES -eq 0 ] && [ $WARNINGS -eq 0 ]; then
    echo -e "${GREEN}✅ All log validations passed${NC}"
    echo "   No issues or warnings found"
    exit 0
elif [ $ISSUES -eq 0 ]; then
    echo -e "${YELLOW}⚠️  Found $WARNINGS warnings${NC}"
    echo "   No critical issues, but check warnings above"
    exit 0
else
    echo -e "${RED}❌ Found $ISSUES issues and $WARNINGS warnings${NC}"
    echo "   Review issues above and fix before proceeding"
    exit 1
fi
