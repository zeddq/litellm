#!/bin/bash
# Automated test for all Mermaid diagram types
# Part of Obsidian PDF Export Test Suite

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEST_OUTPUT_DIR="/tmp/diagram-tests-$$"
mkdir -p "$TEST_OUTPUT_DIR"

# Configuration
DIAGRAM_TYPES=("flowchart" "sequence" "class" "state" "er" "gantt" "pie" "git")
PASS=0
FAIL=0
WARN=0

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Log file
LOG_FILE="$TEST_OUTPUT_DIR/test-summary.log"

echo "=========================================" | tee "$LOG_FILE"
echo "Mermaid Diagram Type Test Suite" | tee -a "$LOG_FILE"
echo "=========================================" | tee -a "$LOG_FILE"
echo "Start time: $(date)" | tee -a "$LOG_FILE"
echo "Output directory: $TEST_OUTPUT_DIR" | tee -a "$LOG_FILE"
echo | tee -a "$LOG_FILE"

# Test each diagram type
for type in "${DIAGRAM_TYPES[@]}"; do
    echo "=========================================" | tee -a "$LOG_FILE"
    echo "Testing: $type diagram" | tee -a "$LOG_FILE"
    echo "=========================================" | tee -a "$LOG_FILE"

    input_file="test-$type.md"
    output_file="$TEST_OUTPUT_DIR/$type.pdf"
    log_file="$TEST_OUTPUT_DIR/$type.log"

    # Check if input file exists
    if [ ! -f "$input_file" ]; then
        echo -e "${RED}❌ FAIL: $type - Input file not found: $input_file${NC}" | tee -a "$LOG_FILE"
        ((FAIL++))
        continue
    fi

    # Execute export
    start_time=$(date +%s)
    if ./pandoc-wrapper.sh "$input_file" -o "$output_file" 2>&1 | tee "$log_file"; then
        end_time=$(date +%s)
        duration=$((end_time - start_time))

        # Verify PDF created
        if [ -f "$output_file" ]; then
            file_size=$(stat -f%z "$output_file" 2>/dev/null || stat -c%s "$output_file")
            file_size_kb=$((file_size / 1024))

            # Check if file size is reasonable (>10KB indicates content)
            if [ $file_size -lt 10240 ]; then
                echo -e "${YELLOW}⚠️  WARN: $type - PDF very small (${file_size_kb}KB), may be empty${NC}" | tee -a "$LOG_FILE"
                echo "  Duration: ${duration}s" | tee -a "$LOG_FILE"
                ((WARN++))
            else
                echo -e "${GREEN}✅ SUCCESS: $type${NC}" | tee -a "$LOG_FILE"
                echo "  Duration: ${duration}s" | tee -a "$LOG_FILE"
                echo "  File size: ${file_size_kb}KB" | tee -a "$LOG_FILE"
                ((PASS++))
            fi
        else
            echo -e "${RED}❌ FAIL: $type - PDF not created${NC}" | tee -a "$LOG_FILE"
            ((FAIL++))
        fi
    else
        echo -e "${RED}❌ FAIL: $type - Export error${NC}" | tee -a "$LOG_FILE"
        echo "  Check log: $log_file" | tee -a "$LOG_FILE"
        ((FAIL++))
    fi

    echo | tee -a "$LOG_FILE"
done

# Summary
echo "=========================================" | tee -a "$LOG_FILE"
echo "Test Summary" | tee -a "$LOG_FILE"
echo "=========================================" | tee -a "$LOG_FILE"
echo "End time: $(date)" | tee -a "$LOG_FILE"
echo | tee -a "$LOG_FILE"

total=$((PASS + FAIL + WARN))
echo "Total tests: $total" | tee -a "$LOG_FILE"
echo -e "${GREEN}Passed: $PASS / $total${NC}" | tee -a "$LOG_FILE"
echo -e "${RED}Failed: $FAIL / $total${NC}" | tee -a "$LOG_FILE"
echo -e "${YELLOW}Warnings: $WARN / $total${NC}" | tee -a "$LOG_FILE"

if [ $total -gt 0 ]; then
    pass_rate=$(echo "scale=1; $PASS * 100 / $total" | bc)
    echo "Pass rate: ${pass_rate}%" | tee -a "$LOG_FILE"
fi

echo | tee -a "$LOG_FILE"
echo "Output directory: $TEST_OUTPUT_DIR" | tee -a "$LOG_FILE"
echo "Test log: $LOG_FILE" | tee -a "$LOG_FILE"

# Exit with failure if any tests failed
if [ $FAIL -gt 0 ]; then
    echo | tee -a "$LOG_FILE"
    echo -e "${RED}❌ TEST SUITE FAILED${NC}" | tee -a "$LOG_FILE"
    exit 1
else
    echo | tee -a "$LOG_FILE"
    echo -e "${GREEN}✅ TEST SUITE PASSED${NC}" | tee -a "$LOG_FILE"
    exit 0
fi
