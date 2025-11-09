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
root_dir=$(dirname $0)
timestamp=$(date +"%Y_%m_%d_%H:%M:%S.%3N")

# Function to run tests
run_tests() {
    local cmd="$1"
    local desc="$2"
    
    echo -e "${YELLOW}Running: ${desc}${NC}"
    echo -e "${GREEN}Command: ${cmd}${NC}"
    echo ""
    eval "$cmd | tee $root_dir/logs/errors/run_$timestamp.log"
    echo ""
}

# Check if test dependencies are installed
if ! python -c "import pytest" 2>/dev/null; then
    echo -e "${YELLOW}⚠️  Test dependencies not found. Installing...${NC}"
    poetry install --with test || pip install pytest pytest-asyncio pytest-cov pytest-mock
fi

case "${1:-all}" in
    all)
        run_tests "poetry run pytest tests/src/ -v --ignore=tests/test_interceptor.py --ignore=tests/test_pipeline_e2e.py --ignore=tests/test_interceptor_integration.py" "All Tests (Excluding Pipeline Tests)"
        ;;

    full-suite)
        run_tests "poetry run pytest tests/src/ -v" "Complete Test Suite (Including Pipeline Tests)"
        ;;

    coverage)
        run_tests "poetry run pytest tests/src/ --cov=. --cov-report=html --cov-report=term-missing" "Tests with Coverage"
        echo -e "${GREEN}✅ Coverage report generated in htmlcov/index.html${NC}"
        ;;

    unit)
        run_tests "poetry run pytest tests/src/test_memory_proxy.py -v -k 'TestMemoryRouter'" "Memory Proxy Unit Tests"
        ;;

    integration)
        run_tests "poetry run pytest tests/src/test_memory_proxy.py -v -k 'TestFastAPI or TestHealth'" "Memory Proxy Integration Tests"
        ;;

    e2e)
        run_tests "poetry run pytest tests/src/test_memory_proxy.py -v -k 'TestEndToEnd'" "Memory Proxy E2E Tests"
        ;;

    interceptor)
        run_tests "poetry run pytest tests/src/test_interceptor.py -v" "Interceptor Component Tests"
        ;;

    pipeline)
        run_tests "poetry run pytest tests/src/test_pipeline_e2e.py -v --run-e2e" "Full Pipeline E2E Tests"
        ;;

    interceptor-integration)
        run_tests "poetry run pytest tests/src/test_interceptor_integration.py -v" "Interceptor Integration Tests"
        ;;

    known-issues)
        run_tests "poetry run pytest tests/src/test_interceptor_known_issues.py -v" "Known Issues Tests (Expected Failures)"
        ;;

    fast)
        run_tests "poetry run pytest tests/src/ -v -m 'not slow' --ignore=tests/test_pipeline_e2e.py" "Fast Tests (Skip Slow)"
        ;;

    debug)
        run_tests "poetry run pytest tests/src/ -v -x --pdb" "Debug Mode (Stop on First Failure)"
        ;;

    parallel)
        echo -e "${YELLOW}Installing pytest-xdist for parallel execution...${NC}"
        poetry add --group test pytest-xdist
        run_tests "poetry run pytest tests/src/ -v -n auto" "Parallel Test Execution"
        ;;

    help|--help|-h)
        echo "Usage: ./RUN_TESTS.sh [option]"
        echo ""
        echo "Test Categories:"
        echo "  all                    - Run all standard tests (default, excludes pipeline)"
        echo "  full-suite             - Run ALL tests including pipeline tests"
        echo "  coverage               - Run tests with coverage report"
        echo ""
        echo "Component Tests:"
        echo "  unit                   - Memory proxy unit tests only"
        echo "  integration            - Memory proxy integration tests only"
        echo "  e2e                    - Memory proxy e2e tests only"
        echo "  interceptor            - Interceptor component tests"
        echo "  pipeline               - Full pipeline e2e tests (requires services running)"
        echo "  interceptor-integration - Interceptor integration tests"
        echo "  known-issues           - Known issues tests (expected failures)"
        echo ""
        echo "Execution Modes:"
        echo "  fast                   - Run fast tests (skip slow tests)"
        echo "  debug                  - Run in debug mode (stop on first failure)"
        echo "  parallel               - Run tests in parallel"
        echo "  help                   - Show this help message"
        echo ""
        echo "Examples:"
        echo "  ./RUN_TESTS.sh                      # Run all standard tests"
        echo "  ./RUN_TESTS.sh full-suite           # Run complete test suite"
        echo "  ./RUN_TESTS.sh interceptor          # Test interceptor component"
        echo "  ./RUN_TESTS.sh pipeline             # Test full pipeline (slow)"
        echo "  ./RUN_TESTS.sh known-issues         # Run known issue tests"
        echo "  ./RUN_TESTS.sh coverage             # Run with coverage report"
        echo ""
        echo "Note: Pipeline tests require all services to be running and may be slow."
        echo "      Use './RUN_TESTS.sh interceptor' for faster component-level tests."
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
