# Testing Quick Reference Card

## 🚀 Quick Start

```bash
# Install dependencies
poetry install --with test

# Run all tests (except E2E)
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=src/proxy --cov-report=html -v
```

## 📁 Test Files

| File | Purpose | Tests | Time |
|------|---------|-------|------|
| `test_sdk_components.py` | Unit tests | 50+ | <5s |
| `test_sdk_integration.py` | Integration tests | 42+ | <30s |
| `test_binary_vs_sdk.py` | Comparison tests | 13 | <60s |
| `test_sdk_e2e.py` | E2E tests | 14+ | Variable |
| `validate_sdk_migration.py` | Validation script | - | <10s |

## 🎯 Common Commands

### Run Specific Test Suites

```bash
# Unit tests only
pytest tests/test_sdk_components.py -v

# Integration tests only
pytest tests/test_sdk_integration.py -v

# Comparison tests only
pytest tests/test_binary_vs_sdk.py -v

# E2E tests (requires API keys)
pytest tests/test_sdk_e2e.py -v -m e2e
```

### Run Specific Test Classes

```bash
# Test session manager
pytest tests/test_sdk_components.py::TestLiteLLMSessionManager -v

# Test error handlers
pytest tests/test_sdk_components.py::TestErrorHandlers -v

# Test chat completions
pytest tests/test_sdk_integration.py::TestChatCompletionsNonStreaming -v

# Test memory routing parity
pytest tests/test_binary_vs_sdk.py::TestMemoryRoutingParity -v
```

### Run by Test Name Pattern

```bash
# All memory routing tests
pytest tests/ -k "memory" -v

# All error handling tests
pytest tests/ -k "error" -v

# All streaming tests
pytest tests/ -k "streaming" -v

# All authentication tests
pytest tests/ -k "auth" -v
```

### Run by Marker

```bash
# E2E tests only
pytest tests/ -m e2e -v

# Slow tests only
pytest tests/ -m slow -v

# Real API tests
pytest tests/ -m real_api -v

# Exclude slow tests
pytest tests/ -m "not slow" -v
```

### Coverage Commands

```bash
# Generate HTML coverage report
pytest tests/ --cov=src/proxy --cov-report=html -v

# Generate terminal coverage report
pytest tests/ --cov=src/proxy --cov-report=term -v

# Coverage for specific module
pytest tests/ --cov=src/proxy/session_manager --cov-report=term -v

# View HTML report
open htmlcov/index.html
```

### Debug Commands

```bash
# Verbose output
pytest tests/test_sdk_components.py -vv

# Show local variables on failure
pytest tests/test_sdk_components.py -l -v

# Drop into debugger on failure
pytest tests/test_sdk_components.py --pdb

# Re-run last failed tests
pytest --lf -v

# Show print statements
pytest tests/test_sdk_components.py -s

# Full traceback
pytest tests/test_sdk_components.py --tb=long
```

## 🔍 Validation Script

### Quick Validation

```bash
# Pre-migration check
./validate_sdk_migration.py --phase pre

# Post-migration check
./validate_sdk_migration.py --phase post

# Full validation
./validate_sdk_migration.py --phase all

# Rollback verification
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

## 🧪 E2E Test Setup

### Set API Keys

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
export OPENAI_API_KEY="sk-..."
export SUPERMEMORY_API_KEY="sm_..."
```

### Run E2E Tests

```bash
# All E2E tests
pytest tests/test_sdk_e2e.py -v -m e2e

# Real API calls only
pytest tests/test_sdk_e2e.py::TestRealAPICalls -v

# Cookie persistence tests
pytest tests/test_sdk_e2e.py::TestCookiePersistence -v

# Load/performance tests
pytest tests/test_sdk_e2e.py::TestLoadAndPerformance -v
```

## 📊 Test Statistics

### Overall Coverage

- **Total Tests**: 106+
- **Unit Tests**: 50+
- **Integration Tests**: 42+
- **Comparison Tests**: 13
- **E2E Tests**: 14+

### Component Coverage

- Session Manager: 18 tests
- Config Parser: 19 tests
- Error Handlers: 19 tests
- Streaming Utils: 12 tests
- Memory Router: 13 tests
- FastAPI App: 25 tests

### Execution Time

- Unit: <5s
- Integration: <30s
- Comparison: <60s
- E2E: Variable
- **Total (no E2E)**: <2 minutes

## 🎨 Test Patterns

### AAA Pattern

```python
def test_example():
    # Arrange
    config = create_test_config()

    # Act
    result = function_under_test(config)

    # Assert
    assert result.is_valid()
```

### Parametrized Tests

```python
@pytest.mark.parametrize("input,expected", [
    ("value1", "result1"),
    ("value2", "result2"),
])
def test_multiple(input, expected):
    assert function(input) == expected
```

### Async Tests

```python
@pytest.mark.asyncio
async def test_async():
    result = await async_function()
    assert result
```

### Using Fixtures

```python
@pytest.fixture
def mock_client():
    return Mock(spec=httpx.AsyncClient)

def test_with_fixture(mock_client):
    # Use fixture
    pass
```

## 📦 Test Fixtures

### Import Fixtures

```python
from tests.fixtures import (
    mock_completion_response,
    mock_streaming_chunks_sequence,
    mock_error_response,
    get_chat_completion_request,
    get_request_headers,
    TEST_SCENARIOS,
    ERROR_TEST_CASES,
)
```

### Use Mock Responses

```python
# Mock completion
response = mock_completion_response(
    model="claude-sonnet-4.5",
    content="Test response",
)

# Mock streaming
chunks = mock_streaming_chunks_sequence()

# Mock error
error = mock_rate_limit_error()
```

### Use Test Scenarios

```python
# Get scenario
scenario = TEST_SCENARIOS["pycharm_client"]
request_body = scenario["request"]
headers = scenario["headers"]
expected_user_id = scenario["expected_user_id"]
```

## 🐛 Troubleshooting

### Import Errors

```bash
# Ensure in project root
cd /Users/cezary/litellm

# Reinstall
poetry install
```

### Async Test Failures

```bash
# Install pytest-asyncio
pip install pytest-asyncio

# Use decorator
@pytest.mark.asyncio
async def test_async():
    pass
```

### Mock Not Working

```python
# Patch where used, not where defined
with patch("litellm.acompletion") as mock:
    pass

# Or patch full path
with patch("src.proxy.litellm_proxy_sdk.litellm.acompletion") as mock:
    pass
```

### Fixture Scope Issues

```python
@pytest.fixture(scope="function")  # New per test
@pytest.fixture(scope="class")     # Shared in class
@pytest.fixture(scope="module")    # Shared in module
@pytest.fixture(scope="session")   # Shared in session
```

## 📝 Test Files Location

```
tests/
├── fixtures/
│   ├── __init__.py
│   ├── mock_responses.py      # Mock data
│   ├── test_data.py           # Test configs
│   └── test_config.yaml       # YAML config
├── test_sdk_components.py     # Unit tests
├── test_sdk_integration.py    # Integration
├── test_binary_vs_sdk.py      # Comparison
└── test_sdk_e2e.py            # E2E tests

validate_sdk_migration.py      # Validation script
SDK_TESTING_GUIDE.md           # Full guide
SDK_TESTING_SUMMARY.md         # Summary
TESTING_QUICK_REFERENCE.md     # This file
```

## ✅ Success Criteria

Migration ready when:

- ✅ All unit tests pass (50+)
- ✅ All integration tests pass (42+)
- ✅ Comparison tests show parity (13)
- ✅ E2E tests pass (14+, with keys)
- ✅ Validation script: 0 critical failures
- ✅ Code coverage >= 80%
- ✅ Performance acceptable
- ✅ Binary proxy still functional

## 📚 Documentation

- `SDK_TESTING_GUIDE.md` - Comprehensive guide
- `SDK_TESTING_SUMMARY.md` - Executive summary
- `TESTING_QUICK_REFERENCE.md` - This file

## 🆘 Need Help?

1. Check `SDK_TESTING_GUIDE.md` for detailed information
2. Run tests with `-vv` for verbose output
3. Use `--pdb` to drop into debugger
4. Check individual test files for documentation

---

**Quick Tip**: Run `pytest tests/ -v` first to ensure all tests pass before running E2E tests or validation script.
