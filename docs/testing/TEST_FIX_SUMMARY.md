# LiteLLM Test Failure Fix - Quick Reference

**Status**: Analysis Complete | **Timeline**: 2-3 days | **Risk**: Low

---

## Priority Matrix

| Priority | Group | Issue | Tests | Complexity | Time | Blocks |
|----------|-------|-------|-------|------------|------|--------|
| 🔴 P0 | **1** | Binary routing format KeyError | 10 | Low | 2-3h | Group 2 |
| 🔴 P0 | **4** | SDK session manager mocks | 6 | Medium | 3-4h | Group 5 |
| 🔴 P1 | **5** | SDK backend 500 errors | 12 | High | 4-6h | None |
| 🟡 P2 | **2** | Context retrieval integration | 4 | Medium | 2-3h | None |
| 🟡 P2 | **6** | Error response format | 6 | Low | 2h | None |
| 🟢 P3 | **3** | Port Registry API rename | 3 | Low | 1h | None |
| 🟢 P3 | **7** | Streaming async types | 2 | Medium | 1-2h | None |

**Total**: 43 failures, 15-21 hours estimated

---

## 3-Day Fix Plan

### Day 1: Critical Infrastructure (8 hours)

**Morning** (4h):
```
[2-3h] Group 1: Fix routing format KeyError
       File: tests/test_binary_vs_sdk.py
       Change: data["routing"]["user_id"] → data["user_id"]
       Impact: 10 tests fixed

[1h]   Group 3: Update Port Registry calls
       Files: tests/test_interceptor*.py
       Change: allocate_port() → get_or_allocate_port()
       Impact: 3 tests fixed
```

**Afternoon** (4h):
```
[3-4h] Group 4: Fix SDK session manager mocks
       File: tests/conftest.py
       Add: mock_litellm_session fixture (AsyncMock)
       Update: test_sdk_components.py, test_sdk_integration.py
       Impact: 6 tests fixed, unblocks Group 5
```

**End of Day**: 19 tests fixed (44%)

---

### Day 2: End-to-End & Error Handling (8 hours)

**Morning** (5h):
```
[4-5h] Group 5: SDK backend 500 errors
       File: tests/conftest.py
       Add: mock_litellm_completion fixture
       Update: tests/test_sdk_e2e.py (all 12 tests)
       Impact: 12 tests fixed (LARGEST GROUP)
```

**Afternoon** (3h):
```
[2h]   Group 6: Error response format
       File: src/proxy/error_handlers.py
       Add: Missing exception handlers (ValueError, KeyError, etc.)
       Update: tests/test_error_handlers.py
       Impact: 6 tests fixed
```

**End of Day**: 37 tests fixed (86%)

---

### Day 3: Advanced Features (4-5 hours)

**Morning** (3h):
```
[2-3h] Group 2: Context retrieval integration
       Files: tests/conftest.py, tests/test_context_retrieval.py
       Add: mock_supermemory_api fixture
       Add: E2E integration tests
       Impact: 4 tests fixed
```

**Afternoon** (2h):
```
[1-2h] Group 7: Streaming async generators
       File: tests/conftest.py
       Add: mock_streaming_response fixture (CustomStreamWrapper)
       Update: tests/test_sdk_e2e.py streaming tests
       Impact: 2 tests fixed
```

**End of Day**: All 43 tests fixed (100%)

---

## Dependency Graph

```
┌─────────────┐
│  GROUP 1    │  Routing Format
│  (2-3h)     │  10 tests
└──────┬──────┘
       │
       ├────────> ┌─────────────┐
       │          │  GROUP 2    │  Context Retrieval
       │          │  (2-3h)     │  4 tests
       │          └─────────────┘
       │
┌──────┴──────┐
│  GROUP 4    │  Session Mocks
│  (3-4h)     │  6 tests
└──────┬──────┘
       │
       └────────> ┌─────────────┐
                  │  GROUP 5    │  SDK 500 Errors
                  │  (4-6h)     │  12 tests
                  └─────────────┘

┌─────────────┐
│  GROUP 3    │  Port Registry (Independent)
│  (1h)       │  3 tests
└─────────────┘

┌─────────────┐
│  GROUP 6    │  Error Format (Independent)
│  (2h)       │  6 tests
└─────────────┘

┌─────────────┐
│  GROUP 7    │  Streaming (Independent)
│  (1-2h)     │  2 tests
└─────────────┘
```

---

## Error Group Details

### Group 1: Binary Routing Format (🔴 Critical)

**Error**: `KeyError: 'routing'`

**Cause**: Tests expect nested structure, binary proxy returns flat:
```python
# Actual Response
{"user_id": "pycharm-ai", "matched_pattern": {...}}

# Test Expectation (WRONG)
{"routing": {"user_id": "...", ...}}
```

**Fix**: Update assertions in `test_binary_vs_sdk.py`
```python
# Before
assert binary_data["routing"]["user_id"] == expected_user_id

# After
assert binary_data["user_id"] == expected_user_id
```

**Impact**: 10 tests fixed

---

### Group 2: Context Retrieval Integration (🟡 Medium)

**Error**: Tests call functions directly, not through proxy

**Cause**: Unit tests exist, integration tests missing

**Fix**: Add E2E tests with mock Supermemory API
```python
@pytest.fixture
def mock_supermemory_api():
    with patch("httpx.AsyncClient") as mock:
        mock.request.return_value.json.return_value = {
            "results": [{"content": "...", "score": 0.95}]
        }
        yield mock
```

**Impact**: 4 tests added/fixed

---

### Group 3: Port Registry API (🟢 Low)

**Error**: `AttributeError: 'PortRegistry' object has no attribute 'allocate_port'`

**Cause**: API renamed to `get_or_allocate_port`

**Fix**: Global find/replace in test files
```bash
# In tests/test_interceptor*.py
allocate_port → get_or_allocate_port
```

**Impact**: 3 tests fixed (15 minutes work)

---

### Group 4: SDK Session Manager Mocks (🔴 Critical)

**Error**: `TypeError: 'Mock' object is not awaitable`

**Cause**: Tests use `Mock()` instead of `AsyncMock()`

**Fix**: Create proper async mock fixture
```python
@pytest.fixture
def mock_litellm_session():
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.request = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.aclose = AsyncMock()
    mock_client.cookies = httpx.Cookies()

    with patch("proxy.session_manager.LiteLLMSessionManager.get_session",
               new=AsyncMock(return_value=mock_client)):
        yield mock_client
```

**Impact**: 6 tests fixed, unblocks Group 5

---

### Group 5: SDK Backend 500 Errors (🔴 Critical)

**Error**: `HTTP 500 Internal Server Error` (all e2e tests)

**Cause**: Mock httpx client returns wrong format, LiteLLM SDK can't parse

**Fix**: Mock at LiteLLM level, not httpx level
```python
@pytest.fixture
def mock_litellm_completion():
    async def mock_completion(*args, **kwargs):
        return {
            "id": "chatcmpl-test",
            "object": "chat.completion",
            "choices": [{"message": {"role": "assistant", "content": "..."}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30}
        }

    with patch("litellm.acompletion", new=AsyncMock(side_effect=mock_completion)):
        yield mock_completion
```

**Impact**: 12 tests fixed (LARGEST GROUP)

---

### Group 6: Error Response Format (🟡 Medium)

**Error**: Tests expect `{"error": {...}}`, get `{"detail": "..."}`

**Cause**: Missing exception handlers fall through to FastAPI default

**Fix**: Register all exception handlers
```python
# In error_handlers.py
def register_exception_handlers(app: FastAPI, ...):
    app.add_exception_handler(ValueError, handler.handle_value_error)
    app.add_exception_handler(KeyError, handler.handle_key_error)
    app.add_exception_handler(TypeError, handler.handle_type_error)
    app.add_exception_handler(Exception, handler.handle_generic_error)
```

**Impact**: 6 tests fixed

---

### Group 7: Streaming Async Generator (🟢 Low)

**Error**: `TypeError: 'NoneType' object is not async iterable`

**Cause**: Streaming mock not properly async

**Fix**: Create proper async generator mock
```python
@pytest.fixture
def mock_streaming_response():
    async def generate_chunks():
        yield {"id": "...", "choices": [{"delta": {"content": "Hello"}}]}
        yield {"id": "...", "choices": [{"delta": {"content": " World"}}]}
        yield {"id": "...", "choices": [{"delta": {}, "finish_reason": "stop"}]}

    return CustomStreamWrapper(
        completion_stream=generate_chunks(),
        model="claude-sonnet-4.5"
    )
```

**Impact**: 2 tests fixed

---

## Files to Modify

### Test Files (Primary Changes)

```
tests/
├── conftest.py                    [Groups 2,4,5,7] Add fixtures
├── test_binary_vs_sdk.py          [Group 1] Fix assertions
├── test_context_retrieval.py      [Group 2] Add integration tests
├── test_interceptor.py            [Group 3] Rename method calls
├── test_interceptor_integration.py [Group 3] Rename method calls
├── test_sdk_components.py         [Group 4] Use new fixture
├── test_sdk_integration.py        [Group 4] Use new fixture
├── test_sdk_e2e.py                [Group 5,7] Add mock fixtures
└── test_error_handlers.py         [Group 6] Add handler tests
```

### Production Files (Minimal Changes)

```
src/proxy/
└── error_handlers.py              [Group 6] Add exception handlers
```

---

## Risk Assessment

### High Risk Changes

**Group 5: SDK Backend Mocking**
- Complex: Mocking LiteLLM SDK internal behavior
- Mitigation: Test with both mock and real API (feature flag)
- Rollback: Revert conftest.py changes

**Group 4: Session Manager**
- Risk: Breaking production session management
- Mitigation: Only modify test mocks, not production code
- Rollback: Revert test_sdk_*.py changes

### Low Risk Changes

**Groups 1, 3, 6, 7**
- Test-only changes
- No production impact
- Easy rollback

---

## Success Criteria

### Per-Group Validation

After each fix:
```bash
# Run group tests
pytest tests/test_<group>.py -v

# Run full suite
pytest tests/ -v

# Check for regressions
pytest tests/test_memory_routing.py -v
```

### Final Validation

```bash
# All tests pass
./RUN_TESTS.sh all

# Coverage maintained
pytest tests/ --cov=src --cov-report=html

# Manual smoke tests
poetry run start-proxies  # Test binary
uvicorn src.proxy.litellm_proxy_sdk:app  # Test SDK
```

---

## Quick Commands

### Run Specific Groups

```bash
# Group 1: Routing
pytest tests/test_binary_vs_sdk.py::TestMemoryRoutingParity -v

# Group 2: Context
pytest tests/test_context_retrieval.py -v

# Group 3: Port Registry
pytest tests/test_interceptor*.py -k "allocate" -v

# Group 4: Session Manager
pytest tests/test_sdk_components.py tests/test_sdk_integration.py -v

# Group 5: SDK E2E
pytest tests/test_sdk_e2e.py -v

# Group 6: Error Handlers
pytest tests/test_error_handlers.py -v

# Group 7: Streaming
pytest tests/ -k "streaming" -v
```

### Progress Tracking

```bash
# Count failures by group
pytest tests/ --tb=no | grep FAILED | wc -l

# Generate detailed report
pytest tests/ -v --tb=short > test_report.txt
```

---

## Rollback Plan

### If Fix Breaks More Tests

```bash
# Check what changed
git diff HEAD tests/
git diff HEAD src/

# Rollback specific file
git checkout HEAD -- tests/test_<problem>.py

# Rollback everything
git reset --hard HEAD
```

### If Production Broken

**Signs**: PyCharm can't connect, Claude Code fails, manual curl errors

**Actions**:
1. Revert production files: `git checkout HEAD -- src/`
2. Keep test changes for analysis
3. Review approach
4. Consider feature flags for risky changes

---

## Post-Fix Checklist

- [ ] All 43 tests pass
- [ ] No new failures introduced
- [ ] Coverage remains > 80%
- [ ] Manual testing (PyCharm, Claude Code, curl)
- [ ] Documentation updated (TESTING.md)
- [ ] docs/CHANGELOG.md updated
- [ ] Code reviewed
- [ ] Merged to main

---

## Key Takeaways

1. **Not Production Bugs**: Tests don't match reality, code works fine
2. **Mock Infrastructure**: Need better fixtures for async/httpx
3. **Dual Architecture**: Binary (preferred) + SDK (needed for cookies)
4. **Critical Path**: Groups 1,4 → Group 5
5. **Low Risk**: Mostly test-only changes

**Next Step**: Start with Group 1 (routing format) - easiest 2-3 hour fix that unlocks 10 tests.

---

**Document**: TEST_FIX_SUMMARY.md
**Version**: 1.0
**Created**: 2025-11-09
**See Also**: TEST_FAILURE_FIX_STRATEGY.md (detailed analysis)
