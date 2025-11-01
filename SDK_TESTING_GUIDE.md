# SDK Migration Testing Guide

Complete guide for testing the SDK-based LiteLLM proxy migration.

## Overview

This testing suite validates the SDK-based proxy implementation at multiple levels:

1. **Unit Tests** - Individual component testing
2. **Integration Tests** - Full application testing
3. **Comparison Tests** - Binary vs SDK parity
4. **E2E Tests** - Real API testing
5. **Validation Script** - Migration verification

## Test Structure

```
tests/
├── fixtures/
│   ├── __init__.py              # Fixture exports
│   ├── mock_responses.py        # Mock LiteLLM responses
│   ├── test_data.py            # Test configuration data
│   └── test_config.yaml        # Test configuration file
├── test_sdk_components.py      # Unit tests (fast)
├── test_sdk_integration.py     # Integration tests
├── test_binary_vs_sdk.py       # Comparison tests
└── test_sdk_e2e.py             # End-to-end tests (slow)

validate_sdk_migration.py       # Migration validation script
```

## Quick Start

### Install Dependencies

```bash
# Install test dependencies
poetry install --with test

# Or if using pip
pip install pytest pytest-asyncio pytest-cov httpx
```

### Run All Tests

```bash
# Run all tests (excluding E2E)
pytest tests/ -v

# Run with coverage
pytest tests/ -v --cov=src/proxy --cov-report=html

# Run specific test file
pytest tests/test_sdk_components.py -v
```

### Run by Test Type

```bash
# Unit tests only (fast)
pytest tests/test_sdk_components.py -v

# Integration tests
pytest tests/test_sdk_integration.py -v

# Comparison tests
pytest tests/test_binary_vs_sdk.py -v

# E2E tests (requires API keys)
pytest tests/test_sdk_e2e.py -v -m e2e
```

## Test Suites

### 1. Unit Tests (`test_sdk_components.py`)

**Purpose**: Test individual components in isolation

**Coverage**:
- `LiteLLMSessionManager` (session_manager.py)
- `LiteLLMConfig` (config_parser.py)
- `LiteLLMErrorHandler` (error_handlers.py)
- Streaming utilities (streaming_utils.py)

**Characteristics**:
- Fast execution (<5 seconds)
- All dependencies mocked
- No external API calls
- 80%+ code coverage target

**Example**:
```bash
# Run all unit tests
pytest tests/test_sdk_components.py -v

# Run specific test class
pytest tests/test_sdk_components.py::TestLiteLLMSessionManager -v

# Run specific test
pytest tests/test_sdk_components.py::TestLiteLLMSessionManager::test_get_client_creates_singleton -v
```

### 2. Integration Tests (`test_sdk_integration.py`)

**Purpose**: Test the complete FastAPI application

**Coverage**:
- Application startup/shutdown
- All API endpoints (health, models, completions, routing info)
- Memory routing integration
- Streaming and non-streaming
- Error scenarios (401, 400, 404, 429, 503)

**Characteristics**:
- Uses FastAPI TestClient
- Mocks LiteLLM SDK responses
- No real API calls
- Tests all HTTP status codes

**Example**:
```bash
# Run all integration tests
pytest tests/test_sdk_integration.py -v

# Run endpoint-specific tests
pytest tests/test_sdk_integration.py::TestChatCompletionsNonStreaming -v

# Test error handling
pytest tests/test_sdk_integration.py::TestErrorHandling -v
```

### 3. Comparison Tests (`test_binary_vs_sdk.py`)

**Purpose**: Validate feature parity between binary and SDK proxies

**Coverage**:
- Same inputs produce same outputs
- Same error handling behavior
- Same memory routing behavior
- Performance comparison

**Characteristics**:
- Parametrized tests for both proxies
- Side-by-side validation
- Focus on behavior, not implementation

**Example**:
```bash
# Run all comparison tests
pytest tests/test_binary_vs_sdk.py -v

# Run memory routing parity tests
pytest tests/test_binary_vs_sdk.py::TestMemoryRoutingParity -v

# Run performance comparison
pytest tests/test_binary_vs_sdk.py::TestPerformanceComparison -v --tb=short
```

### 4. End-to-End Tests (`test_sdk_e2e.py`)

**Purpose**: Test with real API calls

**Coverage**:
- Real OpenAI/Anthropic API calls
- Cookie persistence verification
- Actual streaming
- Load testing (concurrent requests)
- Performance benchmarks

**Characteristics**:
- Requires API keys (conditional execution)
- Slow execution (>30 seconds)
- Uses real providers
- Performance metrics

**Setup**:
```bash
# Set API keys
export ANTHROPIC_API_KEY="sk-ant-..."
export OPENAI_API_KEY="sk-..."
export SUPERMEMORY_API_KEY="sm_..."

# Run E2E tests
pytest tests/test_sdk_e2e.py -v -m e2e
```

**Example**:
```bash
# Run all E2E tests (requires API keys)
pytest tests/test_sdk_e2e.py -v -m e2e

# Run only Anthropic tests
pytest tests/test_sdk_e2e.py::TestRealAPICalls::test_anthropic_real_call -v

# Run cookie persistence tests
pytest tests/test_sdk_e2e.py::TestCookiePersistence -v

# Run load tests
pytest tests/test_sdk_e2e.py::TestLoadAndPerformance -v
```

**Markers**:
- `@pytest.mark.e2e` - End-to-end test
- `@pytest.mark.slow` - Slow test (>5s)
- `@pytest.mark.real_api` - Requires real API keys

## Migration Validation Script

### Purpose

Validate the migration at different phases:
- **Pre-migration**: Verify binary proxy works
- **Post-migration**: Verify SDK proxy works
- **All**: Compare both proxies
- **Rollback**: Verify rollback capability

### Usage

```bash
# Pre-migration check
./validate_sdk_migration.py --phase pre

# Post-migration check
./validate_sdk_migration.py --phase post

# Full validation
./validate_sdk_migration.py --phase all

# Verify rollback
./validate_sdk_migration.py --phase rollback
```

### Custom Configuration

```bash
./validate_sdk_migration.py \
  --phase all \
  --binary-url http://localhost:8765 \
  --sdk-url http://localhost:8764 \
  --config config/config.yaml \
  --master-key sk-1234
```

### Exit Codes

- `0` - All checks passed
- `1` - Some checks failed (non-critical)
- `2` - Critical failure (cannot proceed)

### Validation Checks

The script performs these checks:

1. **File Checks**
   - Configuration file exists
   - SDK components present
   - Binary proxy intact

2. **Health Checks**
   - Proxy responds to /health
   - Session initialized
   - Models configured

3. **Functionality Checks**
   - Models list accessible
   - Memory routing works
   - Authentication enforced

4. **Parity Checks**
   - Both proxies work identically
   - Performance comparison

## Test Fixtures

### Mock Responses (`tests/fixtures/mock_responses.py`)

Provides realistic mock responses:

```python
from tests.fixtures import (
    mock_completion_response,
    mock_streaming_chunks_sequence,
    mock_error_response,
    MockLiteLLMResponse,
)

# Use in tests
mock_response = mock_completion_response(
    model="claude-sonnet-4.5",
    content="Hello! How can I help?",
)
```

### Test Data (`tests/fixtures/test_data.py`)

Provides test configurations and scenarios:

```python
from tests.fixtures import (
    TEST_SCENARIOS,
    ERROR_TEST_CASES,
    get_chat_completion_request,
    get_request_headers,
)

# Use scenarios
scenario = TEST_SCENARIOS["pycharm_client"]
request_body = scenario["request"]
headers = scenario["headers"]
expected_user_id = scenario["expected_user_id"]
```

### Test Configuration (`tests/fixtures/test_config.yaml`)

Standard test configuration with:
- 3 models (claude-sonnet-4.5, gpt-4, gpt-5-pro)
- Memory routing patterns
- Test authentication

## Running Specific Test Scenarios

### Test Memory Routing

```bash
# Unit tests
pytest tests/test_sdk_components.py -k "memory" -v

# Integration tests
pytest tests/test_sdk_integration.py -k "routing" -v

# Comparison tests
pytest tests/test_binary_vs_sdk.py::TestMemoryRoutingParity -v
```

### Test Error Handling

```bash
# Unit tests
pytest tests/test_sdk_components.py::TestErrorHandlers -v

# Integration tests
pytest tests/test_sdk_integration.py::TestErrorHandling -v
```

### Test Streaming

```bash
# Unit tests
pytest tests/test_sdk_components.py::TestStreamingUtilities -v

# Integration tests
pytest tests/test_sdk_integration.py::TestChatCompletionsStreaming -v

# E2E tests
pytest tests/test_sdk_e2e.py -k "streaming" -v
```

### Test Performance

```bash
# Comparison tests
pytest tests/test_binary_vs_sdk.py::TestPerformanceComparison -v

# E2E benchmarks
pytest tests/test_sdk_e2e.py::TestPerformanceBenchmarks -v
```

## Coverage Reports

### Generate Coverage Report

```bash
# Run tests with coverage
pytest tests/ -v \
  --cov=src/proxy \
  --cov-report=html \
  --cov-report=term

# Open HTML report
open htmlcov/index.html
```

### Coverage Targets

- **Overall**: 80%+ coverage
- **Session Manager**: 90%+ coverage
- **Config Parser**: 85%+ coverage
- **Error Handlers**: 85%+ coverage
- **Streaming Utils**: 80%+ coverage

## CI/CD Integration

### GitHub Actions Example

```yaml
name: SDK Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.13'

      - name: Install dependencies
        run: |
          pip install poetry
          poetry install

      - name: Run unit tests
        run: poetry run pytest tests/test_sdk_components.py -v

      - name: Run integration tests
        run: poetry run pytest tests/test_sdk_integration.py -v

      - name: Run comparison tests
        run: poetry run pytest tests/test_binary_vs_sdk.py -v

      - name: Generate coverage
        run: |
          poetry run pytest tests/ \
            --cov=src/proxy \
            --cov-report=xml

      - name: Upload coverage
        uses: codecov/codecov-action@v3
```

## Debugging Failed Tests

### Verbose Output

```bash
# Maximum verbosity
pytest tests/test_sdk_components.py -vv

# Show local variables on failure
pytest tests/test_sdk_components.py -l

# Full traceback
pytest tests/test_sdk_components.py --tb=long
```

### Run Specific Failed Test

```bash
# Re-run last failed tests
pytest --lf -v

# Run specific test with debugging
pytest tests/test_sdk_components.py::test_name -vv --pdb
```

### Print Debugging

```bash
# Enable print statements in tests
pytest tests/test_sdk_components.py -s

# Show captured output even for passing tests
pytest tests/test_sdk_components.py -s --capture=no
```

## Test Development Best Practices

### Writing New Tests

1. **Follow AAA Pattern**:
   ```python
   def test_feature():
       # Arrange
       config = create_test_config()

       # Act
       result = function_under_test(config)

       # Assert
       assert result.is_valid()
   ```

2. **Use Fixtures**:
   ```python
   @pytest.fixture
   def mock_client():
       return Mock(spec=httpx.AsyncClient)

   def test_with_fixture(mock_client):
       # Test uses fixture
       pass
   ```

3. **Parametrize Tests**:
   ```python
   @pytest.mark.parametrize("input,expected", [
       ("value1", "result1"),
       ("value2", "result2"),
   ])
   def test_multiple_cases(input, expected):
       assert function(input) == expected
   ```

### Naming Conventions

- Test files: `test_*.py`
- Test classes: `Test*`
- Test functions: `test_*`
- Use descriptive names: `test_session_manager_creates_singleton`

### Test Organization

```python
class TestComponent:
    """Test suite for specific component."""

    @pytest.fixture
    def component(self):
        """Fixture for component instance."""
        return Component()

    def test_happy_path(self, component):
        """Test normal operation."""
        pass

    def test_error_path(self, component):
        """Test error handling."""
        pass

    def test_edge_case(self, component):
        """Test edge cases."""
        pass
```

## Troubleshooting

### Common Issues

**Import Errors**:
```bash
# Ensure you're in project root
cd /Users/cezary/litellm

# Install in development mode
poetry install
```

**Async Test Failures**:
```bash
# Ensure pytest-asyncio is installed
pip install pytest-asyncio

# Use @pytest.mark.asyncio decorator
@pytest.mark.asyncio
async def test_async_function():
    result = await async_function()
    assert result
```

**Mock Issues**:
```python
# Correct import path for mocking
with patch("src.proxy.litellm_proxy_sdk.litellm.acompletion") as mock:
    pass

# Or patch where it's used
with patch("litellm.acompletion") as mock:
    pass
```

**Fixture Scope Issues**:
```python
# Use appropriate scope
@pytest.fixture(scope="function")  # New instance per test
@pytest.fixture(scope="class")     # Shared within class
@pytest.fixture(scope="module")    # Shared within module
@pytest.fixture(scope="session")   # Shared across session
```

## Performance Testing

### Benchmark Tests

```bash
# Run with timing
pytest tests/test_sdk_e2e.py -v --durations=10

# Profile tests
pytest tests/test_sdk_integration.py --profile
```

### Load Testing

```python
# Example load test
@pytest.mark.slow
def test_concurrent_load(client):
    num_requests = 100

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [
            executor.submit(make_request, client)
            for _ in range(num_requests)
        ]
        results = [f.result() for f in futures]

    success_rate = sum(1 for r in results if r.ok) / len(results)
    assert success_rate >= 0.95  # 95% success rate
```

## Summary

This testing suite provides comprehensive validation of the SDK migration:

✅ **Unit Tests** - Fast, isolated component testing
✅ **Integration Tests** - Full application testing
✅ **Comparison Tests** - Feature parity validation
✅ **E2E Tests** - Real-world scenarios
✅ **Validation Script** - Migration safety checks

**Total Test Coverage**: 80%+ across all components

**Test Execution Time**:
- Unit tests: <5 seconds
- Integration tests: <30 seconds
- Comparison tests: <60 seconds
- E2E tests: Variable (depends on API)

For questions or issues, refer to individual test files for detailed documentation.
