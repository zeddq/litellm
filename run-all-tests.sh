#!/bin/bash
# Master test runner for Obsidian PDF Export system
# Runs all test suites in sequence

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Configuration
OUTPUT_DIR="test-results-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$OUTPUT_DIR"

SUMMARY_FILE="$OUTPUT_DIR/test-summary.txt"

echo "=========================================" | tee "$SUMMARY_FILE"
echo "Obsidian PDF Export - Master Test Suite" | tee -a "$SUMMARY_FILE"
echo "=========================================" | tee -a "$SUMMARY_FILE"
echo "Start time: $(date)" | tee -a "$SUMMARY_FILE"
echo "Output directory: $OUTPUT_DIR" | tee -a "$SUMMARY_FILE"
echo | tee -a "$SUMMARY_FILE"

# Track overall results
TOTAL_SUITES=0
PASSED_SUITES=0
FAILED_SUITES=0
SKIPPED_SUITES=0

# Function to run test suite
run_suite() {
    local suite_name="$1"
    local suite_script="$2"
    local suite_type="${3:-required}"

    ((TOTAL_SUITES++))

    echo | tee -a "$SUMMARY_FILE"
    echo "=========================================" | tee -a "$SUMMARY_FILE"
    echo -e "${BLUE}Test Suite: $suite_name${NC}" | tee -a "$SUMMARY_FILE"
    echo "=========================================" | tee -a "$SUMMARY_FILE"

    # Check if script exists
    if [ ! -f "$suite_script" ]; then
        if [ "$suite_type" == "required" ]; then
            echo -e "${RED}❌ Script not found: $suite_script${NC}" | tee -a "$SUMMARY_FILE"
            ((FAILED_SUITES++))
            return 1
        else
            echo -e "${YELLOW}⚠️  Script not found (optional): $suite_script${NC}" | tee -a "$SUMMARY_FILE"
            ((SKIPPED_SUITES++))
            return 0
        fi
    fi

    # Make executable if not already
    chmod +x "$suite_script"

    # Run the suite
    suite_log="$OUTPUT_DIR/$suite_name.log"
    start_time=$(date +%s)

    if "$suite_script" > "$suite_log" 2>&1; then
        end_time=$(date +%s)
        duration=$((end_time - start_time))

        echo -e "${GREEN}✅ PASSED${NC} (${duration}s)" | tee -a "$SUMMARY_FILE"
        echo "  Log: $suite_log" | tee -a "$SUMMARY_FILE"
        ((PASSED_SUITES++))
        return 0
    else
        end_time=$(date +%s)
        duration=$((end_time - start_time))
        exit_code=$?

        if [ "$suite_type" == "optional" ] && [ $exit_code -eq 2 ]; then
            echo -e "${YELLOW}⚠️  PASSED WITH WARNINGS${NC} (${duration}s)" | tee -a "$SUMMARY_FILE"
            echo "  Log: $suite_log" | tee -a "$SUMMARY_FILE"
            ((PASSED_SUITES++))
            return 0
        else
            echo -e "${RED}❌ FAILED${NC} (${duration}s)" | tee -a "$SUMMARY_FILE"
            echo "  Log: $suite_log" | tee -a "$SUMMARY_FILE"
            echo "  Exit code: $exit_code" | tee -a "$SUMMARY_FILE"
            ((FAILED_SUITES++))
            return 1
        fi
    fi
}

# Run test suites in order
echo "Running test suites..." | tee -a "$SUMMARY_FILE"

# Suite 1: Setup Validation
run_suite "Setup Validation" "./validate-setup.sh" "required"

# Suite 2: Log Validation
run_suite "Log Validation" "./validate-logs.sh" "optional"

# Suite 3: Diagram Tests
run_suite "Diagram Type Tests" "./test-all-diagrams.sh" "optional"

# Suite 4: Performance Benchmarks
run_suite "Performance Benchmarks" "./benchmark-performance.sh" "optional"

# Suite 5: Regression Tests
run_suite "Regression Tests" "./run-regression-tests.sh" "required"

# Copy result files to output directory
echo | tee -a "$SUMMARY_FILE"
echo "Collecting test artifacts..." | tee -a "$SUMMARY_FILE"

if [ -f "performance-results.csv" ]; then
    cp performance-results.csv "$OUTPUT_DIR/"
    echo "  Copied: performance-results.csv" | tee -a "$SUMMARY_FILE"
fi

if [ -f "test-case-matrix.csv" ]; then
    cp test-case-matrix.csv "$OUTPUT_DIR/"
    echo "  Copied: test-case-matrix.csv" | tee -a "$SUMMARY_FILE"
fi

# Generate HTML report if generate-test-report.sh exists
if [ -f "generate-test-report.sh" ]; then
    echo | tee -a "$SUMMARY_FILE"
    echo "Generating HTML report..." | tee -a "$SUMMARY_FILE"
    if ./generate-test-report.sh > "$OUTPUT_DIR/test-report.html" 2>&1; then
        echo "  Created: test-report.html" | tee -a "$SUMMARY_FILE"
    fi
fi

# Final summary
echo | tee -a "$SUMMARY_FILE"
echo "=========================================" | tee -a "$SUMMARY_FILE"
echo "Master Test Suite Summary" | tee -a "$SUMMARY_FILE"
echo "=========================================" | tee -a "$SUMMARY_FILE"
echo "End time: $(date)" | tee -a "$SUMMARY_FILE"
echo | tee -a "$SUMMARY_FILE"

echo "Total test suites: $TOTAL_SUITES" | tee -a "$SUMMARY_FILE"
echo -e "${GREEN}Passed: $PASSED_SUITES${NC}" | tee -a "$SUMMARY_FILE"
echo -e "${RED}Failed: $FAILED_SUITES${NC}" | tee -a "$SUMMARY_FILE"
echo -e "${YELLOW}Skipped: $SKIPPED_SUITES${NC}" | tee -a "$SUMMARY_FILE"

if [ $TOTAL_SUITES -gt 0 ]; then
    pass_rate=$(echo "scale=1; $PASSED_SUITES * 100 / $TOTAL_SUITES" | bc)
    echo "Pass rate: ${pass_rate}%" | tee -a "$SUMMARY_FILE"
fi

echo | tee -a "$SUMMARY_FILE"
echo "All results saved to: $OUTPUT_DIR" | tee -a "$SUMMARY_FILE"

# Show detailed failure info if any
if [ $FAILED_SUITES -gt 0 ]; then
    echo | tee -a "$SUMMARY_FILE"
    echo "Failed test suites:" | tee -a "$SUMMARY_FILE"
    grep "❌ FAILED" "$SUMMARY_FILE" | grep -v "Failed test" | tee -a "$SUMMARY_FILE"

    echo | tee -a "$SUMMARY_FILE"
    echo "Review individual logs in: $OUTPUT_DIR" | tee -a "$SUMMARY_FILE"
fi

# Recommendations
echo | tee -a "$SUMMARY_FILE"
echo "Next steps:" | tee -a "$SUMMARY_FILE"
if [ $FAILED_SUITES -eq 0 ]; then
    echo "  ✅ All tests passed! System ready for use." | tee -a "$SUMMARY_FILE"
else
    echo "  1. Review failed test logs in $OUTPUT_DIR" | tee -a "$SUMMARY_FILE"
    echo "  2. Fix identified issues" | tee -a "$SUMMARY_FILE"
    echo "  3. Re-run: ./run-all-tests.sh" | tee -a "$SUMMARY_FILE"
fi

# Exit code
echo | tee -a "$SUMMARY_FILE"
if [ $FAILED_SUITES -gt 0 ]; then
    echo -e "${RED}❌ TEST SUITE FAILED${NC}" | tee -a "$SUMMARY_FILE"
    exit 1
else
    echo -e "${GREEN}✅ TEST SUITE PASSED${NC}" | tee -a "$SUMMARY_FILE"
    exit 0
fi
