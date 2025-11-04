# Testing Guide

Comprehensive guide for running, understanding, and maintaining tests for LiteLLM Memory Proxy.

---

## Table of Contents

1. [Quick Reference](#quick-reference)
2. [Test Suite Overview](#test-suite-overview)
3. [Running Tests](#running-tests)
4. [Test Coverage](#test-coverage)
5. [SDK Testing](#sdk-testing)
6. [Writing Tests](#writing-tests)
7. [Troubleshooting Tests](#troubleshooting-tests)

---

## Quick Reference

### Installation

```bash
# Install test dependencies
poetry install --with test

# Or using pip
pip install pytest pytest-asyncio pytest-cov pytest-mock pytest-timeout httpx
```

### Essential Commands

```bash
# Run all tests (recommended)
./RUN_TESTS.sh

# Run all tests with pytest directly
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=src/proxy --cov-report=html

# View coverage report
open htmlcov/index.html
```

### Quick Test Commands

| Command | Purpose | Time |
|---------|---------|------|
| `./RUN_TESTS.sh` | Run all tests | <2 min |
| `./RUN_TESTS.sh unit` | Unit tests only | <30s |
| `./RUN_TESTS.sh integration` | Integration tests | <1 min |
| `./RUN_TESTS.sh fast` | Skip slow tests | <1 min |
| `./RUN_TESTS.sh coverage` | With coverage report | <3 min |
| `./RUN_TESTS.sh debug` | Verbose debug mode | Variable |

---

## Test Suite Overview

### Test Files

| File | Purpose | Test Count | Time |
|------|---------|------------|------|
| `test_memory_proxy.py` | Core memory proxy tests | 70+ | <60s |
| `test_sdk_components.py` | SDK unit tests | 50+ | <5s |
| `test_sdk_integration.py` | SDK integration tests | 40+ | <30s |
| `test_binary_vs_sdk.py` | Binary/SDK comparison | 13 | <60s |
| `test_sdk_e2e.py` | End-to-end tests | 14+ | Variable |

### Test Categories

**Unit Tests** (50%):
- MemoryRouter pattern matching
- Configuration parsing
- Session management
- Error handling

**Integration Tests** (35%):
- FastAPI endpoints
- Request proxying
- Memory routing
- Authentication

**End-to-End Tests** (10%):
- Complete request flows
- Multi-client isolation
- Real API integration

**Comparison Tests** (5%):
- Binary vs SDK parity
- Feature validation
- Performance benchmarks

### Current Coverage

| Module | Coverage | Target |
|--------|----------|--------|
| `memory_router.py` | 90-95% | 90% |
| `litellm_proxy_with_memory.py` | 85-90% | 85% |
| `session_manager.py` | 85-90% | 85% |
| `config_parser.py` | 80-85% | 80% |
| **Overall** | **80-85%** | **80%** |

---

## Running Tests

### Using RUN_TESTS.sh (Recommended)

The `RUN_TESTS.sh` script provides a convenient wrapper around pytest:

```bash
# Run all tests
./RUN_TESTS.sh

# Run specific test suites
./RUN_TESTS.sh unit           # Unit tests only
./RUN_TESTS.sh integration    # Integration tests
./RUN_TESTS.sh e2e            # End-to-end tests
./RUN_TESTS.sh fast           # Skip slow tests
./RUN_TESTS.sh parallel       # Parallel execution

# With coverage
./RUN_TESTS.sh coverage       # Generate HTML coverage report

# Debug mode
./RUN_TESTS.sh debug          # Verbose output with debugging
```

### Using pytest Directly

#### Run All Tests

```bash
# Verbose output
pytest tests/ -v

# Very verbose
pytest tests/ -vv

# Show print statements
pytest tests/ -s
```

#### Run Specific Test Files

```bash
# Memory proxy tests
pytest tests/test_memory_proxy.py -v

# SDK component tests
pytest tests/test_sdk_components.py -v

# Integration tests
pytest tests/test_sdk_integration.py -v

# E2E tests (requires API keys)
pytest tests/test_sdk_e2e.py -v
```

#### Run Specific Test Classes

```bash
# Test MemoryRouter
pytest tests/test_memory_proxy.py::TestMemoryRouter -v

# Test session manager
pytest tests/test_sdk_components.py::TestLiteLLMSessionManager -v

# Test error handlers
pytest tests/test_sdk_components.py::TestErrorHandlers -v

# Test chat completions
pytest tests/test_sdk_integration.py::TestChatCompletionsNonStreaming -v
```

#### Run Specific Test Methods

```bash
# Single test method
pytest tests/test_memory_proxy.py::TestMemoryRouter::test_detect_from_pycharm_user_agent -v

# Multiple methods matching pattern
pytest tests/ -k "detect_user_id" -v
```

#### Run by Test Markers

```bash
# E2E tests only
pytest tests/ -m e2e -v

# Slow tests only
pytest tests/ -m slow -v

# Skip slow tests
pytest tests/ -m "not slow" -v

# Real API tests
pytest tests/ -m real_api -v
```

---

## Test Coverage

### Generate Coverage Reports

#### HTML Report (Recommended)

```bash
# Generate and open
pytest tests/ --cov=src/proxy --cov-report=html -v
open htmlcov/index.html

# Or use RUN_TESTS.sh
./RUN_TESTS.sh coverage
```

#### Terminal Report

```bash
# Brief summary
pytest tests/ --cov=src/proxy --cov-report=term -v

# With missing lines
pytest tests/ --cov=src/proxy --cov-report=term-missing -v
```

#### Coverage for Specific Modules

```bash
# Memory router only
pytest tests/ --cov=src/proxy/memory_router --cov-report=term -v

# Session manager only
pytest tests/ --cov=src/proxy/session_manager --cov-report=term -v

# Multiple modules
pytest tests/ --cov=src/proxy/memory_router --cov=src/proxy/session_manager --cov-report=html
```

### Coverage Targets

| Module | Current | Target | Priority |
|--------|---------|--------|----------|
| `memory_router.py` | 90-95% | 90% | ✅ Met |
| `litellm_proxy_with_memory.py` | 85-90% | 85% | ✅ Met |
| `session_manager.py` | 85-90% | 85% | ✅ Met |
| `config_parser.py` | 80-85% | 80% | ✅ Met |
| `error_handlers.py` | 75-80% | 80% | ⚠️ Improve |
| `streaming_utils.py` | 70-75% | 80% | ⚠️ Improve |

---

## SDK Testing

### SDK Test Suites

#### 1. Component Tests (`test_sdk_components.py`)

**Purpose**: Unit tests for SDK-specific components

**Coverage**:
- Configuration parsing (`config_parser.py`)
- Session management (`session_manager.py`)
- Error handling (`error_handlers.py`)
- Streaming utilities (`streaming_utils.py`)

**Run**:
```bash
pytest tests/test_sdk_components.py -v
```

**Key Tests**:
- `TestConfigParser`: YAML parsing, env var resolution, model lookup
- `TestLiteLLMSessionManager`: Client lifecycle, singleton pattern
- `TestErrorHandlers`: Exception mapping, response formatting
- `TestStreamingUtils`: SSE formatting, chunk handling

#### 2. Integration Tests (`test_sdk_integration.py`)

**Purpose**: Test SDK proxy endpoints and features

**Coverage**:
- Chat completions (streaming and non-streaming)
- Memory routing integration
- Authentication and authorization
- Error responses
- Health checks

**Run**:
```bash
pytest tests/test_sdk_integration.py -v
```

**Key Tests**:
- `TestChatCompletionsNonStreaming`: Complete chat flow
- `TestChatCompletionsStreaming`: SSE streaming
- `TestMemoryRoutingIntegration`: User ID injection
- `TestAuthentication`: API key validation
- `TestErrorHandling`: Error scenarios

#### 3. Comparison Tests (`test_binary_vs_sdk.py`)

**Purpose**: Validate SDK vs Binary parity

**Coverage**:
- Feature parity validation
- Response format comparison
- Memory routing consistency
- Performance benchmarks

**Run**:
```bash
pytest tests/test_binary_vs_sdk.py -v
```

**Key Tests**:
- `TestMemoryRoutingParity`: User ID detection matches
- `TestResponseParity`: Response formats identical
- `TestErrorParity`: Error handling consistent
- `TestPerformance`: Latency comparisons

#### 4. End-to-End Tests (`test_sdk_e2e.py`)

**Purpose**: Real API integration testing

**Requirements**: Valid API keys in environment

**Run**:
```bash
# Set API keys
export OPENAI_API_KEY="sk-..."
export ANTHROPIC_API_KEY="sk-ant-..."

# Run E2E tests
pytest tests/test_sdk_e2e.py -v -m e2e
```

**Key Tests**:
- `TestE2EOpenAI`: Real OpenAI API calls
- `TestE2EAnthropic`: Real Anthropic API calls
- `TestE2ESupermemory`: Supermemory integration
- `TestE2ECookiePersistence`: Cloudflare cookie handling

### SDK Validation Script

Use the validation script for comprehensive checks:

```bash
# Pre-migration validation
python validate_sdk_migration.py --phase pre

# Post-migration validation
python validate_sdk_migration.py --phase post

# Full validation
python validate_sdk_migration.py --phase all

# Rollback verification
python validate_sdk_migration.py --phase rollback
```

---

## Writing Tests

### Test Structure

```python
import pytest
from unittest.mock import Mock, patch, AsyncMock

class TestMyFeature:
    """Test suite for MyFeature."""
    
    @pytest.fixture
    def mock_config(self):
        """Fixture providing test configuration."""
        return {"key": "value"}
    
    def test_basic_functionality(self, mock_config):
        """Test basic functionality works."""
        # Arrange
        feature = MyFeature(mock_config)
        
        # Act
        result = feature.do_something()
        
        # Assert
        assert result == expected_value
    
    @pytest.mark.asyncio
    async def test_async_functionality(self):
        """Test async functionality."""
        result = await async_function()
        assert result is not None
    
    @pytest.mark.parametrize("input,expected", [
        ("test1", "result1"),
        ("test2", "result2"),
    ])
    def test_multiple_cases(self, input, expected):
        """Test multiple input cases."""
        assert process(input) == expected
```

### Testing Best Practices

1. **Use Descriptive Names**
   ```python
   # Good
   def test_memory_router_detects_pycharm_from_user_agent()
   
   # Bad
   def test_router()
   ```

2. **Follow AAA Pattern** (Arrange, Act, Assert)
   ```python
   def test_feature():
       # Arrange
       config = create_test_config()
       router = MemoryRouter(config)
       
       # Act
       result = router.detect_user_id(headers)
       
       # Assert
       assert result == "expected-user-id"
   ```

3. **Use Fixtures for Setup**
   ```python
   @pytest.fixture
   def test_config():
       return {
           "user_id_mappings": {
               "default_user_id": "test-user"
           }
       }
   ```

4. **Mock External Dependencies**
   ```python
   @patch('httpx.AsyncClient')
   async def test_proxy_request(mock_client):
       mock_client.return_value.post = AsyncMock(
           return_value=Mock(status_code=200)
       )
       result = await make_proxy_request()
       assert result.status_code == 200
   ```

5. **Use Parametrize for Multiple Cases**
   ```python
   @pytest.mark.parametrize("user_agent,expected_id", [
       ("OpenAIClientImpl/Java", "pycharm-ai"),
       ("Claude Code", "claude-cli"),
       ("Unknown", "default-user"),
   ])
   def test_user_id_detection(user_agent, expected_id):
       result = detect_user_id({"user-agent": user_agent})
       assert result == expected_id
   ```

### Test Markers

Use markers to categorize tests:

```python
@pytest.mark.slow
def test_performance_benchmark():
    """Slow performance test."""
    pass

@pytest.mark.e2e
def test_real_api_call():
    """E2E test requiring real API."""
    pass

@pytest.mark.asyncio
async def test_async_feature():
    """Async test."""
    pass
```

---

## Troubleshooting Tests

### Common Issues

#### "Module not found"

**Solution**: Ensure you're in the correct directory and have installed dependencies

```bash
# Install dependencies
poetry install --with test

# Run from project root
cd /path/to/litellm
pytest tests/ -v
```

#### "Fixture not found"

**Solution**: Check fixture is defined and imported

```python
# Define fixture
@pytest.fixture
def my_fixture():
    return "value"

# Or import from conftest.py
# fixtures in conftest.py are automatically available
```

#### "Async test failed"

**Solution**: Ensure `pytest-asyncio` is installed and test is marked

```python
# Install
poetry add --group test pytest-asyncio

# Mark test
@pytest.mark.asyncio
async def test_async_function():
    result = await async_function()
    assert result is not None
```

#### "Test timeout"

**Solution**: Increase timeout or optimize test

```bash
# Increase timeout
pytest tests/ --timeout=300

# Or in test
@pytest.mark.timeout(60)
def test_slow_operation():
    pass
```

#### "Import errors in tests"

**Solution**: Ensure PYTHONPATH includes src directory

```bash
# Set PYTHONPATH
export PYTHONPATH="${PYTHONPATH}:$(pwd)/src"

# Or use pytest with src path
pytest tests/ --pythonpath=src
```

### Debug Commands

```bash
# Verbose output
pytest tests/ -vv

# Show local variables on failure
pytest tests/ -l

# Drop into debugger on failure
pytest tests/ --pdb

# Show print statements
pytest tests/ -s

# Re-run only failed tests
pytest --lf

# Full traceback
pytest tests/ --tb=long
```

### Performance Tips

```bash
# Run tests in parallel (requires pytest-xdist)
pytest tests/ -n auto

# Skip slow tests
pytest tests/ -m "not slow"

# Run only fast tests
pytest tests/ -m fast

# Fail fast (stop on first failure)
pytest tests/ -x
```

---

## CI/CD Integration

### GitHub Actions Example

```yaml
name: Tests

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
          poetry install --with test
      
      - name: Run tests
        run: poetry run pytest tests/ --cov=src/proxy --cov-report=xml
      
      - name: Upload coverage
        uses: codecov/codecov-action@v3
        with:
          files: ./coverage.xml
```

---

## Related Documentation

- [Quick Start Guide](../getting-started/QUICKSTART.md) - Get started quickly
- [Configuration Guide](CONFIGURATION.md) - Configuration reference
- [Troubleshooting](../troubleshooting/COMMON_ISSUES.md) - Common issues

---

**Last Updated**: 2025-11-04  
**Status**: Consolidated from multiple testing documents
