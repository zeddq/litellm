# Recommended CLAUDE.md Testing Section
**Replace lines 312-340 in CLAUDE.md with this content**

---

## Testing

### Quick Start

```bash
# Run all standard tests (fastest, recommended for development)
./scripts/testing/RUN_TESTS.sh

# Run specific test categories
./scripts/testing/RUN_TESTS.sh unit           # Unit tests (~30s)
./scripts/testing/RUN_TESTS.sh integration    # Integration tests (~1m)
./scripts/testing/RUN_TESTS.sh e2e            # End-to-end tests (~2m)

# Run with coverage report
./scripts/testing/RUN_TESTS.sh coverage       # Generates htmlcov/index.html
```

---

### Complete Test Runner Modes

The `RUN_TESTS.sh` script provides **13 distinct modes** for different testing scenarios:

#### Test Categories (5 modes)
```bash
./scripts/testing/RUN_TESTS.sh all            # Standard tests (default, excludes pipeline)
./scripts/testing/RUN_TESTS.sh full-suite     # ALL tests including pipeline
./scripts/testing/RUN_TESTS.sh coverage       # Run with coverage report
./scripts/testing/RUN_TESTS.sh unit           # Memory proxy unit tests only
./scripts/testing/RUN_TESTS.sh integration    # Memory proxy integration tests
```

#### Component Tests (5 modes)
```bash
./scripts/testing/RUN_TESTS.sh e2e                       # End-to-end scenarios
./scripts/testing/RUN_TESTS.sh interceptor               # Interceptor component tests
./scripts/testing/RUN_TESTS.sh interceptor-integration   # Interceptor integration tests
./scripts/testing/RUN_TESTS.sh pipeline                  # Full pipeline e2e (requires services)
./scripts/testing/RUN_TESTS.sh known-issues              # Expected failure tests
```

#### Execution Modes (3 modes)
```bash
./scripts/testing/RUN_TESTS.sh fast       # Skip slow tests (uses -m 'not slow')
./scripts/testing/RUN_TESTS.sh debug      # Stop on first failure + pdb debugger
./scripts/testing/RUN_TESTS.sh parallel   # Run tests in parallel (faster)
```

**Get Help**:
```bash
./scripts/testing/RUN_TESTS.sh help       # Show complete usage information
```

---

### Pytest Markers

Use markers to filter tests by category or characteristic:

```bash
# Skip slow tests
poetry run pytest -m "not slow"

# Run only unit tests
poetry run pytest -m "unit"

# Run integration tests
poetry run pytest -m "integration"

# Run e2e tests
poetry run pytest -m "e2e"

# Combine markers (unit tests that are NOT slow)
poetry run pytest -m "unit and not slow"
```

**Available Markers**:
- `slow` - Slow tests (>5s execution time)
- `unit` - Unit tests (test individual functions/classes)
- `integration` - Integration tests (test component interactions)
- `e2e` - End-to-end tests (test complete workflows)
- `real_api` - Tests requiring real API keys and network calls

---

### Alternative Test Commands (Direct pytest)

**Not Recommended for Daily Use** (use `RUN_TESTS.sh` instead), but useful for specific scenarios:

```bash
# Run specific test file
poetry run pytest tests/src/test_memory_proxy.py -v

# Run specific test class
poetry run pytest tests/src/test_memory_proxy.py::TestMemoryRouterInit -v

# Run specific test function
poetry run pytest tests/src/test_memory_proxy.py::TestMemoryRouterInit::test_init_with_valid_config -v

# Run tests matching pattern
poetry run pytest -k "test_detect_user_id" -v

# Run with verbose output and stop on first failure
poetry run pytest -v -x
```

---

### Test Organization

```
tests/
├── fixtures/                  # Centralized test fixtures
│   ├── __init__.py            # Fixture exports
│   ├── mock_responses.py      # Mock response generators
│   ├── test_data.py           # Test data constants
│   └── interceptor_fixtures.py # Interceptor-specific fixtures
├── helpers/                   # Test utility functions
│   ├── __init__.py
│   └── pipeline_helpers.py    # Pipeline test helpers
├── src/                       # Main test directory
│   ├── conftest.py            # ⭐ Core fixture configuration (smart HTTP mocking)
│   ├── test_memory_proxy.py  # Main test suite (86 tests)
│   ├── test_interceptor.py   # Interceptor component tests
│   ├── test_pipeline_e2e.py  # Full pipeline e2e tests
│   ├── test_sdk_*.py          # SDK integration tests
│   ├── test_error_handlers.py # Error handling tests
│   └── ...                    # Additional test modules
└── test_*.py                  # Root-level test files
```

---

### Test Fixtures and Mocking

The project uses a **sophisticated pytest fixture system** defined in `tests/src/conftest.py`:

#### Key Fixtures

**`mock_httpx_client`** (Primary Fixture):
- Smart HTTP mocking with automatic response routing
- Automatically patches `ProxySessionManager.get_session`
- Returns appropriate responses based on endpoint patterns:
  - `/chat/completions` → Chat completion responses
  - `/v1/models` → Models list
  - `/memory-routing/info` → Routing diagnostic info
  - `/health` → Health check responses
- Supports streaming responses
- Maintains cookie jar for session testing
- Validates request payloads (checks for required fields)

**Response Data Fixtures**:
- `mock_litellm_chat_completion_response` - Pre-built chat response dict
- `mock_litellm_models_response` - Models list dict
- `mock_litellm_health_response` - Health check dict

**Configuration Fixtures**:
- `configure_mock_httpx_response` - Override smart routing for error testing
- `temp_port_registry` - Temporary port registry for interceptor tests
- `interceptor_server` - Start/stop interceptor server for integration tests

**Usage Example**:
```python
def test_chat_completion(mock_httpx_client):
    # The fixture automatically mocks HTTP requests
    # No manual patching required!
    response = await some_function_that_uses_httpx()
    assert response.status_code == 200
```

See `tests/src/conftest.py` for comprehensive fixture documentation (1000+ lines with extensive docstrings).

---

### Coverage Targets

| Module | Target | Current |
|--------|--------|---------|
| `memory_router.py` | 90% | 90-95% |
| `litellm_proxy_*.py` | 85% | 85-90% |
| `session_manager.py` | 80% | 80-85% |

**View Coverage Report**:
```bash
./scripts/testing/RUN_TESTS.sh coverage   # Run tests with coverage
open htmlcov/index.html                    # Open HTML report
```

**Coverage Configuration**:
- Branch coverage enabled (more thorough than line coverage)
- Excludes test files, cache, and venv
- Shows missing lines for easy gap identification
- 2-decimal precision for accurate metrics

---

### Test Logs

Test execution logs are automatically saved:

**Location**: `logs/errors/`
**Format**: `run_YYYY_MM_DD_HH:MM:SS.log`
**Content**: Full test output (stdout + stderr)

---

### Testing Philosophy

1. **Fast by default**: `./RUN_TESTS.sh` runs fast tests (<2 min)
2. **No external dependencies**: All tests use mocks (no API keys required for standard tests)
3. **Test isolation**: Each test is independent (no shared state between tests)
4. **AAA Pattern**: Arrange-Act-Assert pattern in every test
5. **Comprehensive mocking**: Smart HTTP mocking with realistic OpenAI-compatible responses
6. **Coverage-driven**: Track and maintain >80% coverage on core modules
7. **Async-first**: Proper asyncio testing with `pytest-asyncio`

---

### Comprehensive Testing Guide

For detailed information on:
- Writing new tests (templates and patterns)
- Test coverage analysis and improvement
- Fixture system deep dive
- Mocking strategies and best practices
- Troubleshooting test failures
- Performance testing
- SDK vs Binary testing
- Pipeline testing

See: **[docs/guides/TESTING.md](docs/guides/TESTING.md)**

---

### Test Structure Summary

**Key Test Files** (28 total test files):

| File | Purpose | Test Count | Time |
|------|---------|------------|------|
| `test_memory_proxy.py` | Core proxy tests (routing, FastAPI, integration) | 86 | ~60s |
| `test_interceptor.py` | Interceptor component tests | 30+ | ~20s |
| `test_pipeline_e2e.py` | Full pipeline e2e tests | 20+ | Variable |
| `test_sdk_components.py` | SDK unit tests | 50+ | ~5s |
| `test_sdk_integration.py` | SDK integration tests | 40+ | ~30s |
| `test_error_handlers.py` | Error handling tests | 15+ | ~10s |
| `test_binary_vs_sdk.py` | Binary/SDK comparison tests | 13 | ~60s |

**Total**: 250+ tests across 28 test files

**Key Support Files**:
- `tests/src/conftest.py` - Outstanding fixture system with smart HTTP mocking (1000+ lines)
- `tests/fixtures/` - Reusable fixtures and mock responses
- `tests/helpers/` - Test utility functions

---

### Quick Reference

**Most Common Commands**:
```bash
# Daily development workflow
./scripts/testing/RUN_TESTS.sh                # Run all standard tests

# Before committing
./scripts/testing/RUN_TESTS.sh coverage       # Check coverage

# Debugging a specific test
poetry run pytest tests/src/test_memory_proxy.py::TestMemoryRouterInit::test_init_with_valid_config -v -s

# Fast iteration during development
./scripts/testing/RUN_TESTS.sh fast           # Skip slow tests

# When test fails
./scripts/testing/RUN_TESTS.sh debug          # Stop on failure + debugger
```

**Test Markers**:
```bash
poetry run pytest -m "not slow"               # Skip slow tests
poetry run pytest -m "unit"                   # Unit tests only
poetry run pytest -m "integration"            # Integration tests only
poetry run pytest -m "unit and not slow"      # Fast unit tests
```

---

## Next Steps

After reading this testing overview:
1. Run `./scripts/testing/RUN_TESTS.sh` to verify your setup
2. Read `docs/guides/TESTING.md` for comprehensive testing guide
3. Review `tests/src/conftest.py` to understand the fixture system
4. Try running individual tests with different markers
5. Check coverage report: `open htmlcov/index.html`

---
