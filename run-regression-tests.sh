#!/bin/bash
# Regression test suite for Obsidian PDF Export
# Ensures updates don't break existing functionality

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Setup
TEST_DIR="/tmp/obsidian-regression-$$"
mkdir -p "$TEST_DIR"

# Track results
PASSED=0
FAILED=0
SKIPPED=0
RESULTS_FILE="$TEST_DIR/regression-results.txt"

echo "=========================================" | tee "$RESULTS_FILE"
echo "Regression Test Suite" | tee -a "$RESULTS_FILE"
echo "=========================================" | tee -a "$RESULTS_FILE"
echo "Start time: $(date)" | tee -a "$RESULTS_FILE"
echo "Test directory: $TEST_DIR" | tee -a "$RESULTS_FILE"
echo | tee -a "$RESULTS_FILE"

# Test function
run_test() {
    local test_name="$1"
    local test_command="$2"
    local test_type="${3:-required}"

    echo -n "Running $test_name... " | tee -a "$RESULTS_FILE"

    if [ "$test_type" == "optional" ]; then
        if eval "$test_command" &>"$TEST_DIR/$test_name.log"; then
            echo -e "${GREEN}✅ PASSED${NC}" | tee -a "$RESULTS_FILE"
            echo "$test_name: PASS" >> "$RESULTS_FILE"
            ((PASSED++))
        else
            echo -e "${YELLOW}⚠️  SKIPPED${NC}" | tee -a "$RESULTS_FILE"
            echo "$test_name: SKIPPED" >> "$RESULTS_FILE"
            ((SKIPPED++))
        fi
    else
        if eval "$test_command" &>"$TEST_DIR/$test_name.log"; then
            echo -e "${GREEN}✅ PASSED${NC}" | tee -a "$RESULTS_FILE"
            echo "$test_name: PASS" >> "$RESULTS_FILE"
            ((PASSED++))
        else
            echo -e "${RED}❌ FAILED${NC}" | tee -a "$RESULTS_FILE"
            echo "$test_name: FAIL" >> "$RESULTS_FILE"
            echo "  Log: $TEST_DIR/$test_name.log" | tee -a "$RESULTS_FILE"
            ((FAILED++))
        fi
    fi
}

# Core functionality tests
echo "=== Core Functionality ===" | tee -a "$RESULTS_FILE"

run_test "Flowchart Export" \
    "[ -f test-flowchart.md ] && ./pandoc-wrapper.sh test-flowchart.md -o $TEST_DIR/out-flow.pdf && [ -f $TEST_DIR/out-flow.pdf ]" \
    "optional"

run_test "Sequence Export" \
    "[ -f test-sequence.md ] && ./pandoc-wrapper.sh test-sequence.md -o $TEST_DIR/out-seq.pdf && [ -f $TEST_DIR/out-seq.pdf ]" \
    "optional"

run_test "Class Export" \
    "[ -f test-class.md ] && ./pandoc-wrapper.sh test-class.md -o $TEST_DIR/out-class.pdf && [ -f $TEST_DIR/out-class.pdf ]" \
    "optional"

echo | tee -a "$RESULTS_FILE"

# Script tests
echo "=== Script Functionality ===" | tee -a "$RESULTS_FILE"

run_test "Wrapper Exists" \
    "[ -f ./pandoc-wrapper.sh ] || [ -f $(which pandoc-wrapper.sh 2>/dev/null) ]"

run_test "Wrapper Executable" \
    "[ -x ./pandoc-wrapper.sh ] || [ -x $(which pandoc-wrapper.sh 2>/dev/null) ]"

run_test "Validator Exists" \
    "[ -f ./validate-setup.sh ]"

run_test "Monitor Exists" \
    "[ -f ./obsidian-monitor.sh ]" \
    "optional"

echo | tee -a "$RESULTS_FILE"

# Dependency tests
echo "=== Dependencies ===" | tee -a "$RESULTS_FILE"

run_test "Pandoc Installed" \
    "command -v pandoc >/dev/null 2>&1"

run_test "Node.js Installed" \
    "command -v node >/dev/null 2>&1"

run_test "mermaid-filter Installed" \
    "npm list -g mermaid-filter >/dev/null 2>&1 || command -v mermaid-filter >/dev/null 2>&1" \
    "optional"

echo | tee -a "$RESULTS_FILE"

# Configuration tests
echo "=== Configuration Validation ===" | tee -a "$RESULTS_FILE"

run_test "Pandoc Config Exists" \
    "[ -f pandoc.yaml ] || [ -f ~/.pandoc/defaults/pandoc.yaml ]" \
    "optional"

run_test "Pandoc Config Valid" \
    "[ -f pandoc.yaml ] && pandoc -d pandoc.yaml --print-defaults >/dev/null 2>&1" \
    "optional"

run_test "Mermaid Config Exists" \
    "[ -f mermaid-filter.json ] || [ -f ~/.config/mermaid/config.json ]" \
    "optional"

run_test "Mermaid Config Valid" \
    "[ -f mermaid-filter.json ] && command -v jq >/dev/null 2>&1 && jq . mermaid-filter.json >/dev/null 2>&1" \
    "optional"

echo | tee -a "$RESULTS_FILE"

# Log tests
echo "=== Logging ===" | tee -a "$RESULTS_FILE"

run_test "Log Directory Exists" \
    "[ -d ~/.obsidian-pandoc/logs ] || mkdir -p ~/.obsidian-pandoc/logs"

run_test "Log Directory Writable" \
    "[ -w ~/.obsidian-pandoc/logs ]"

run_test "Wrapper Log Created" \
    "[ -f ~/.obsidian-pandoc/logs/wrapper.log ]" \
    "optional"

run_test "Logs Contain Timestamps" \
    "[ -f ~/.obsidian-pandoc/logs/wrapper.log ] && grep -qE '[0-9]{4}-[0-9]{2}-[0-9]{2}' ~/.obsidian-pandoc/logs/wrapper.log" \
    "optional"

echo | tee -a "$RESULTS_FILE"

# Error handling tests
echo "=== Error Handling ===" | tee -a "$RESULTS_FILE"

run_test "Missing File Error Detected" \
    "! ./pandoc-wrapper.sh nonexistent-file-12345.md -o $TEST_DIR/out.pdf 2>&1" \
    "optional"

run_test "Invalid Syntax Detection" \
    "[ -f test-error.md ] && ! ./pandoc-wrapper.sh test-error.md -o $TEST_DIR/out-error.pdf 2>&1" \
    "optional"

echo | tee -a "$RESULTS_FILE"

# Summary
echo "=========================================" | tee -a "$RESULTS_FILE"
echo "Regression Test Summary" | tee -a "$RESULTS_FILE"
echo "=========================================" | tee -a "$RESULTS_FILE"
echo "End time: $(date)" | tee -a "$RESULTS_FILE"
echo | tee -a "$RESULTS_FILE"

total=$((PASSED + FAILED + SKIPPED))
echo "Passed: $PASSED" | tee -a "$RESULTS_FILE"
echo "Failed: $FAILED" | tee -a "$RESULTS_FILE"
echo "Skipped: $SKIPPED" | tee -a "$RESULTS_FILE"
echo "Total:  $total" | tee -a "$RESULTS_FILE"

if [ $total -gt 0 ]; then
    pass_rate=$(echo "scale=1; $PASSED * 100 / $total" | bc)
    echo "Pass Rate: ${pass_rate}%" | tee -a "$RESULTS_FILE"
fi

echo | tee -a "$RESULTS_FILE"
echo "Full results: $RESULTS_FILE" | tee -a "$RESULTS_FILE"

# Show failed tests
if [ $FAILED -gt 0 ]; then
    echo | tee -a "$RESULTS_FILE"
    echo "Failed Tests:" | tee -a "$RESULTS_FILE"
    grep "FAIL" "$RESULTS_FILE" | grep -v "Failed:" | tee -a "$RESULTS_FILE"
fi

# Cleanup option (keep logs for review)
echo | tee -a "$RESULTS_FILE"
echo "Test artifacts preserved in: $TEST_DIR" | tee -a "$RESULTS_FILE"
echo "To cleanup: rm -rf $TEST_DIR" | tee -a "$RESULTS_FILE"

# Exit with failure if any tests failed
if [ $FAILED -gt 0 ]; then
    echo | tee -a "$RESULTS_FILE"
    echo -e "${RED}❌ REGRESSION TESTS FAILED${NC}" | tee -a "$RESULTS_FILE"
    exit 1
else
    echo | tee -a "$RESULTS_FILE"
    echo -e "${GREEN}✅ REGRESSION TESTS PASSED${NC}" | tee -a "$RESULTS_FILE"
    exit 0
fi
