# LiteLLM Memory Proxy - Comprehensive Testing Guide

Complete guide for running, understanding, and maintaining the test suite for LiteLLM Memory Proxy.

---

## Quick Reference

### Installation

```bash
# Install test dependencies
poetry install --with test

# Or using pip
pip install pytest pytest-asyncio pytest-cov pytest-mock pytest-timeout
```

### Essential Commands

```bash
# Run all tests
pytest test_memory_proxy.py -v

# Run with coverage
pytest test_memory_proxy.py --cov=. --cov-report=term-missing

# Run with HTML coverage report
pytest test_memory_proxy.py --cov=. --cov-report=html
open htmlcov/index.html
```

---

## Overview

The test suite (`test_memory_proxy.py`) provides comprehensive coverage for:

### 1. Unit Tests for MemoryRouter (`memory_router.py`)
- Configuration loading and initialization
- Header pattern matching and compilation
- User ID detection from various sources
- Memory header injection
- Supermemory model detection
- Routing information retrieval

### 2. Integration Tests for FastAPI Application (`litellm_proxy_with_memory.py`)
- FastAPI app creation and configuration
- Health endpoint functionality
- Routing info endpoint
- Dependency injection system
- Request proxying and forwarding
- Streaming response handling
- Error handling and edge cases

### 3. End-to-End Tests
- Complete request flows for different clients
- Multi-client isolation
- Custom header override behavior

---

## Test Coverage Statistics

### Current Metrics

| Metric | Count |
|--------|-------|
| Test Functions | 71+ |
| Test Classes | 15+ |
| Fixtures | 8 |
| Parametrized Test Cases | 27 |
| Total Test Scenarios | 98+ |

### Test Distribution

- **Unit Tests (MemoryRouter)**: ~40% (30+ tests)
- **Integration Tests (FastAPI)**: ~45% (35+ tests)
- **End-to-End Tests**: ~10% (10+ tests)
- **Edge Cases**: ~5% (5+ tests)

### Expected Code Coverage

- **memory_router.py**: 90-95% coverage
- **litellm_proxy_with_memory.py**: 85-90% coverage
- **Overall Project**: 80-85% coverage

---

## Running Tests

### Basic Test Execution

Run all tests with verbose output:
```bash
pytest test_memory_proxy.py -v
```

Run all tests with detailed output:
```bash
pytest test_memory_proxy.py -vv
```

### Run Specific Test Categories

Run only unit tests:
```bash
pytest test_memory_proxy.py -v -k "TestMemoryRouter"
```

Run only integration tests:
```bash
pytest test_memory_proxy.py -v -k "TestFastAPI or TestHealth"
```

Run only end-to-end tests:
```bash
pytest test_memory_proxy.py -v -k "TestEndToEnd"
```

### Run Specific Test Classes or Methods

Run a specific test class:
```bash
pytest test_memory_proxy.py::TestMemoryRouterDetectUserId -v
```

Run a specific test method:
```bash
pytest test_memory_proxy.py::TestMemoryRouterDetectUserId::test_detect_from_pycharm_user_agent -v
```

Run tests matching a pattern:
```bash
pytest test_memory_proxy.py -v -k "detect_user_id"
```

### Exclude Slow Tests

Skip slow performance tests:
```bash
pytest test_memory_proxy.py -v -m "not slow"
```

---

## Code Coverage

### Generate Coverage Report

Run tests with coverage:
```bash
pytest test_memory_proxy.py --cov=. --cov-report=term-missing
```

### Generate HTML Coverage Report

```bash
pytest test_memory_proxy.py --cov=. --cov-report=html
```

View the report:
```bash
open htmlcov/index.html  # macOS
xdg-open htmlcov/index.html  # Linux
start htmlcov/index.html  # Windows
```

### Coverage for Specific Modules

Test coverage for MemoryRouter only:
```bash
pytest test_memory_proxy.py --cov=memory_router --cov-report=term-missing
```

Test coverage for proxy app only:
```bash
pytest test_memory_proxy.py --cov=litellm_proxy_with_memory --cov-report=term-missing
```

### Set Coverage Thresholds

Fail tests if coverage is below 80%:
```bash
pytest test_memory_proxy.py --cov=. --cov-fail-under=80
```

---

## Test Output Options

### Detailed Test Output

Show print statements and logs:
```bash
pytest test_memory_proxy.py -v -s
```

Show local variables on failures:
```bash
pytest test_memory_proxy.py -v -l
```

Stop on first failure:
```bash
pytest test_memory_proxy.py -v -x
```

Stop after N failures:
```bash
pytest test_memory_proxy.py -v --maxfail=3
```

---

## Parallel Test Execution

Install pytest-xdist for parallel execution:
```bash
pip install pytest-xdist
```

Run tests in parallel (4 workers):
```bash
pytest test_memory_proxy.py -v -n 4
```

Run tests using all CPU cores:
```bash
pytest test_memory_proxy.py -v -n auto
```

---

## Test Markers

The test suite uses markers to categorize tests:

### Available Markers
- `@pytest.mark.slow` - Slow-running tests (performance tests)
- `@pytest.mark.unit` - Unit tests (future use)
- `@pytest.mark.integration` - Integration tests (future use)
- `@pytest.mark.e2e` - End-to-end tests (future use)

### Using Markers

Run only marked tests:
```bash
pytest test_memory_proxy.py -v -m "slow"
```

Exclude marked tests:
```bash
pytest test_memory_proxy.py -v -m "not slow"
```

---

## Debugging Tests

### Run Tests with PDB on Failure

```bash
pytest test_memory_proxy.py -v --pdb
```

### Run Tests with PDB on First Failure

```bash
pytest test_memory_proxy.py -v -x --pdb
```

### Show Captured Output on Failure

```bash
pytest test_memory_proxy.py -v --tb=long
```

### Different Traceback Formats

```bash
pytest test_memory_proxy.py -v --tb=short  # Short traceback
pytest test_memory_proxy.py -v --tb=line   # One line per failure
pytest test_memory_proxy.py -v --tb=native # Python standard traceback
pytest test_memory_proxy.py -v --tb=no     # No traceback
```

---

## Continuous Integration

### GitHub Actions Example

Create `.github/workflows/test.yml`:

```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.11", "3.12", "3.13"]

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}

      - name: Install dependencies
        run: |
          pip install poetry
          poetry install --with test

      - name: Run tests
        run: |
          poetry run pytest test_memory_proxy.py -v --cov=. --cov-report=xml

      - name: Upload coverage
        uses: codecov/codecov-action@v4
        with:
          file: ./coverage.xml
```

### Pre-commit Hook

Create `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: local
    hooks:
      - id: pytest
        name: pytest
        entry: pytest test_memory_proxy.py -v
        language: system
        pass_filenames: false
        always_run: true
```

---

## Test Structure

### Test File Organization

```
test_memory_proxy.py
├── Fixtures (lines 50-150)
│   ├── sample_config_dict
│   ├── config_file
│   ├── memory_router
│   ├── app_with_router
│   ├── test_client
│   └── mock_httpx_response
│
├── Unit Tests (lines 160-550)
│   ├── TestMemoryRouterInit
│   ├── TestMemoryRouterDetectUserId
│   ├── TestMemoryRouterInjectHeaders
│   ├── TestMemoryRouterSupermemoryCheck
│   └── TestMemoryRouterRoutingInfo
│
├── Integration Tests (lines 560-950)
│   ├── TestFastAPIAppCreation
│   ├── TestHealthEndpoint
│   ├── TestRoutingInfoEndpoint
│   ├── TestProxyHandler
│   ├── TestStreamingResponse
│   ├── TestErrorHandling
│   └── TestDependencyInjection
│
├── End-to-End Tests (lines 960-1050)
│   └── TestEndToEndScenarios
│
├── Parametrized Tests (lines 1060-1140)
│
├── Edge Cases (lines 1150-1350)
│   └── TestEdgeCases
│
└── Performance Tests (lines 1360-1450)
    └── TestPerformance
```

---

## Common Issues and Solutions

### Issue: Import Errors

**Problem**: `ModuleNotFoundError: No module named 'memory_router'`

**Solution**: Ensure you're running tests from the project root directory:
```bash
cd /Users/cezary/litellm
pytest test_memory_proxy.py -v
```

### Issue: Async Test Warnings

**Problem**: `RuntimeWarning: coroutine was never awaited`

**Solution**: Ensure pytest-asyncio is installed and configured:
```bash
pip install pytest-asyncio
```

The test file already includes proper async configuration.

### Issue: Mock Errors

**Problem**: Mocks not working as expected

**Solution**: Check that you have pytest-mock installed:
```bash
pip install pytest-mock
```

### Issue: Fixture Not Found

**Problem**: `fixture 'memory_router' not found`

**Solution**: Ensure you're running the test file that contains the fixtures:
```bash
pytest test_memory_proxy.py -v
```

Not just:
```bash
pytest -v  # This might pick up other test files
```

---

## Writing New Tests

### Test Naming Conventions

- Test files: `test_*.py` or `*_test.py`
- Test classes: `Test*` (e.g., `TestMemoryRouter`)
- Test methods: `test_*` (e.g., `test_detect_user_id`)

### Example Test Template

```python
class TestNewFeature:
    """Tests for new feature."""

    def test_basic_functionality(self, memory_router: MemoryRouter):
        """Test basic functionality of new feature."""
        # Arrange
        input_data = {"key": "value"}

        # Act
        result = memory_router.new_method(input_data)

        # Assert
        assert result is not None
        assert result["key"] == "expected_value"

    @pytest.mark.parametrize("input,expected", [
        ("test1", "result1"),
        ("test2", "result2"),
    ])
    def test_with_parameters(self, memory_router: MemoryRouter, input: str, expected: str):
        """Test with multiple parameter sets."""
        result = memory_router.new_method(input)
        assert result == expected
```

### Async Test Template

```python
@pytest.mark.asyncio
async def test_async_functionality(self, test_client: TestClient):
    """Test async functionality."""
    # Arrange
    with patch("httpx.AsyncClient") as mock_client:
        # Setup mocks
        mock_instance = Mock()
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=None)
        mock_client.return_value = mock_instance

        # Act
        result = await some_async_function()

        # Assert
        assert result is not None
```

---

## Best Practices

### 1. Test Independence
- Each test should be independent
- Use fixtures for setup/teardown
- Don't rely on test execution order

### 2. Clear Test Names
- Use descriptive test names
- Follow convention: `test_should_do_something_when_condition`
- Example: `test_should_return_error_when_user_not_found`

### 3. Arrange-Act-Assert Pattern
```python
def test_example(self):
    # Arrange: Set up test data
    data = {"key": "value"}

    # Act: Execute the code being tested
    result = function_under_test(data)

    # Assert: Verify the results
    assert result == expected_value
```

### 4. Mock External Dependencies
- Mock HTTP requests with httpx
- Mock file system operations
- Mock environment variables
- Mock time-dependent functions

### 5. Test Edge Cases
- Empty inputs
- Null/None values
- Very large inputs
- Invalid data types
- Boundary conditions

---

## Performance Benchmarking

Run performance tests:
```bash
pytest test_memory_proxy.py -v -m "slow" --durations=10
```

Show test durations:
```bash
pytest test_memory_proxy.py -v --durations=0
```

---

## Test Coverage Goals

- **Overall Coverage**: Aim for >80%
- **Critical Modules**: Aim for >90%
  - `memory_router.py`: User ID detection logic
  - `litellm_proxy_with_memory.py`: Proxy routing logic

---

## Command Cheat Sheet

| Command | Description |
|---------|-------------|
| `pytest test_memory_proxy.py -v` | Run all tests |
| `pytest test_memory_proxy.py -v -k "pattern"` | Run matching tests |
| `pytest test_memory_proxy.py -v -x` | Stop on first failure |
| `pytest test_memory_proxy.py -v -s` | Show print output |
| `pytest test_memory_proxy.py --cov=.` | Run with coverage |
| `pytest test_memory_proxy.py -v -m "not slow"` | Skip slow tests |
| `pytest test_memory_proxy.py -v --pdb` | Debug on failure |
| `pytest test_memory_proxy.py -v -n auto` | Run in parallel |

---

## Additional Resources

### Pytest Documentation
- Official docs: https://docs.pytest.org/
- Pytest-asyncio: https://pytest-asyncio.readthedocs.io/
- Pytest-cov: https://pytest-cov.readthedocs.io/

### FastAPI Testing
- FastAPI testing guide: https://fastapi.tiangolo.com/tutorial/testing/
- TestClient documentation: https://www.starlette.io/testclient/

### Mocking
- unittest.mock: https://docs.python.org/3/library/unittest.mock.html
- Pytest-mock: https://pytest-mock.readthedocs.io/

---

## Support

For issues or questions:
1. Review this documentation
2. Check test output and error messages
3. Run tests with verbose output: `pytest -vv`
4. Use PDB debugger: `pytest --pdb`

---

**Sources**: TEST_README.md, TEST_QUICK_START.md, TEST_DELIVERABLES.md, TESTING_SUMMARY.md
**Created**: 2025-10-24
**Updated**: 2025-10-24
