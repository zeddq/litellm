#!/bin/bash
#
# Quick Test Runner Script for LiteLLM Memory Proxy
# Usage: ./RUN_TESTS.sh [option]
#

set -e

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${BLUE}╔══════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║      LiteLLM Memory Proxy - Test Suite Runner           ║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════════════════════════╝${NC}"
echo ""

# Function to run tests
run_tests() {
    local cmd="$1"
    local desc="$2"
    
    echo -e "${YELLOW}Running: ${desc}${NC}"
    echo -e "${GREEN}Command: ${cmd}${NC}"
    echo ""
    eval "$cmd"
    echo ""
}

# Check if test dependencies are installed
if ! python -c "import pytest" 2>/dev/null; then
    echo -e "${YELLOW}⚠️  Test dependencies not found. Installing...${NC}"
    poetry install --with test || pip install pytest pytest-asyncio pytest-cov pytest-mock
fi

case "${1:-all}" in
    all)
        run_tests "pytest tests/test_memory_proxy.py -v" "All Tests"
        ;;
    
    coverage)
        run_tests "pytest tests/test_memory_proxy.py --cov=. --cov-report=html --cov-report=term-missing" "Tests with Coverage"
        echo -e "${GREEN}✅ Coverage report generated in htmlcov/index.html${NC}"
        ;;
    
    unit)
        run_tests "pytest tests/test_memory_proxy.py -v -k 'TestMemoryRouter'" "Unit Tests Only"
        ;;
    
    integration)
        run_tests "pytest tests/test_memory_proxy.py -v -k 'TestFastAPI or TestHealth'" "Integration Tests Only"
        ;;
    
    e2e)
        run_tests "pytest tests/test_memory_proxy.py -v -k 'TestEndToEnd'" "End-to-End Tests"
        ;;
    
    fast)
        run_tests "pytest tests/test_memory_proxy.py -v -m 'not slow'" "Fast Tests (Skip Slow)"
        ;;
    
    debug)
        run_tests "pytest tests/test_memory_proxy.py -v -x --pdb" "Debug Mode (Stop on First Failure)"
        ;;
    
    parallel)
        echo -e "${YELLOW}Installing pytest-xdist for parallel execution...${NC}"
        pip install pytest-xdist
        run_tests "pytest tests/test_memory_proxy.py -v -n auto" "Parallel Test Execution"
        ;;
    
    help|--help|-h)
        echo "Usage: ./RUN_TESTS.sh [option]"
        echo ""
        echo "Options:"
        echo "  all          - Run all tests (default)"
        echo "  coverage     - Run tests with coverage report"
        echo "  unit         - Run unit tests only"
        echo "  integration  - Run integration tests only"
        echo "  e2e          - Run end-to-end tests only"
        echo "  fast         - Run fast tests (skip slow tests)"
        echo "  debug        - Run in debug mode (stop on first failure)"
        echo "  parallel     - Run tests in parallel"
        echo "  help         - Show this help message"
        echo ""
        echo "Examples:"
        echo "  ./RUN_TESTS.sh                 # Run all tests"
        echo "  ./RUN_TESTS.sh coverage        # Run with coverage"
        echo "  ./RUN_TESTS.sh unit            # Run unit tests only"
        ;;
    
    *)
        echo -e "${YELLOW}Unknown option: $1${NC}"
        echo "Run './RUN_TESTS.sh help' for usage information"
        exit 1
        ;;
esac

echo -e "${GREEN}════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}✅ Test execution completed!${NC}"
echo -e "${GREEN}════════════════════════════════════════════════════════${NC}"
