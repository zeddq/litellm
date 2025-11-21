# LiteLLM Memory Proxy - Test Failure Fix Strategy

**Created**: 2025-11-09
**Status**: Analysis Complete - Ready for Implementation
**Context**: Binary vs SDK Dual Architecture Transition

---

## Executive Summary

The test suite has 43 failures across 7 distinct error groups. These failures stem from an ongoing architectural transition from a **binary-based proxy** to an **SDK-based proxy**. The binary approach (preferred per CLAUDE.md) uses an external LiteLLM process, while the SDK approach uses in-process LiteLLM library calls.

**Key Insight**: Most failures are test infrastructure issues, not production code bugs. The production code supports both architectures, but the tests expect inconsistent response formats.

**Fix Timeline**: 2-3 days (Groups 1-4 are critical path)

---

## Architecture Context

### Current State: Dual Implementation

```
┌─────────────────────────────────────────────────────────────────┐
│                    BINARY APPROACH (Preferred)                   │
│  ┌──────────────┐   HTTP    ┌────────────┐   HTTP   ┌────────┐ │
│  │ Memory Proxy │ ────────> │  LiteLLM   │ ──────>  │ Providers│ │
│  │  (FastAPI)   │  :4000    │   Binary   │          │ API      │ │
│  └──────────────┘           └────────────┘          └────────┘ │
│       File: litellm_proxy_with_memory.py                        │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                     SDK APPROACH (Alternative)                   │
│  ┌──────────────────────────────────────────────────────────────│
│  │ Memory Proxy + LiteLLM SDK (in-process)                      │ │
│  │  - Direct litellm.acompletion() calls                        │ │
│  │  - Persistent HTTP sessions for cookie handling             │ │
│  └──────────────────────────────────────────────────────────────│
│       File: litellm_proxy_sdk.py                                │
└─────────────────────────────────────────────────────────────────┘
```

**Why Both Exist**:
- Binary: Simpler, production-preferred, better separation of concerns
- SDK: Needed for Cloudflare cookie persistence (cf_clearance)

**Test Challenge**: Tests must work with both, but each has different response formats.

---

## Error Group Analysis

### Priority Matrix

| Group | Error Type | Count | Criticality | Blocking | Complexity | Fix Time |
|-------|-----------|-------|-------------|----------|------------|----------|
| **1** | Binary routing format | 10 | 🔴 Critical | Yes (Group 2) | Low | 2-3 hrs |
| **2** | Context retrieval | 4 | 🟡 Medium | No | Medium | 2-3 hrs |
| **3** | Port Registry API | 3 | 🟢 Low | No | Low | 1 hr |
| **4** | SDK mock issues | 6 | 🔴 Critical | Yes (Group 5) | Medium | 3-4 hrs |
| **5** | SDK backend 500s | 12 | 🔴 Critical | No | High | 4-6 hrs |
| **6** | Error format | 6 | 🟡 Medium | No | Low | 2 hrs |
| **7** | Streaming types | 2 | 🟢 Low | No | Medium | 1-2 hrs |

**Total**: 43 failures, Est. 15-21 hours work

---

## Group 1: Binary vs SDK Routing Format (🔴 Critical, 10 tests)

### Problem

Binary proxy returns routing info at **top level**, SDK proxy returns it in `/memory-routing/info` endpoint:

```python
# Binary Response (actual)
{
  "user_id": "pycharm-ai",
  "matched_pattern": {...}
}

# Test Expectation (wrong)
{
  "routing": {          # ❌ Nested structure doesn't exist
    "user_id": "...",
    "matched_pattern": {...}
  }
}
```

### Root Cause

**File**: `tests/test_binary_vs_sdk.py:254`
```python
def test_user_id_detection_matches(self, ...):
    assert binary_data["routing"]["user_id"] == expected_user_id
    #                  ^^^^^^^^^^ KeyError: 'routing'
```

Tests expect nested `routing` key that doesn't exist in actual binary proxy response.

### Affected Tests

1. `test_binary_vs_sdk.py::TestMemoryRoutingParity::test_user_id_detection_matches[OpenAIClientImpl/Java-pycharm-ai]`
2. `test_binary_vs_sdk.py::TestMemoryRoutingParity::test_user_id_detection_matches[Claude Code CLI-claude-code]`
3. `test_binary_vs_sdk.py::TestMemoryRoutingParity::test_user_id_detection_matches[anthropic-sdk-python/1.0-anthropic-python]`
4. `test_binary_vs_sdk.py::TestMemoryRoutingParity::test_user_id_detection_matches[curl/7.68.0-default-dev]`
5. `test_binary_vs_sdk.py::TestMemoryRoutingParity::test_custom_user_id_header`
6-10. Related routing validation tests

### Solution

**Option A: Fix Tests (Recommended)** - 2 hours
```python
# Change from:
assert binary_data["routing"]["user_id"] == expected_user_id

# To:
assert binary_data["user_id"] == expected_user_id
```

**Option B: Change Binary Proxy Format** - 4 hours
- Add `routing` wrapper to `/memory-routing/info` endpoint
- Update documentation
- Risk: Breaking change for existing clients

**Recommendation**: Option A - Fix tests to match actual API format.

### Files to Modify

1. **tests/test_binary_vs_sdk.py** (lines 250-280)
   - Remove `["routing"]` nesting
   - Update all assertions: `data["routing"]["key"]` → `data["key"]`

2. **tests/fixtures.py** (if routing fixtures exist)
   - Update mock response generators

### Implementation Steps

1. Read current `/memory-routing/info` response from binary proxy
2. Update test assertions to match actual format
3. Verify SDK proxy returns same format
4. Run `pytest tests/test_binary_vs_sdk.py::TestMemoryRoutingParity -v`

### Dependencies

- **Blocks**: Group 2 (context retrieval tests may expect this format)
- **Blocked by**: None

---

## Group 2: Context Retrieval Not Integrated (🟡 Medium, 4 tests)

### Problem

Context retrieval feature (Supermemory integration) is **partially implemented but not integrated** with SDK proxy tests.

```python
# SDK Proxy Code (litellm_proxy_sdk.py)
if should_use_context_retrieval(model_name, config):
    messages = await apply_context_retrieval(
        messages, user_id, http_client
    )
# ✅ Code exists

# Test Code (test_context_retrieval.py)
def test_context_injection_system_message(...):
    # ❌ Tests call functions directly, not through proxy
    pass
```

### Root Cause

**Gap**: Tests validate `ContextRetriever` class methods in isolation, but don't test integration with proxy handlers.

**Missing**: End-to-end tests that:
1. Send request to SDK proxy
2. Verify Supermemory API called
3. Confirm context injected into messages
4. Validate response includes context

### Affected Tests

1. `test_context_retrieval.py::TestContextRetriever::test_retrieve_context_success`
2. `test_context_retrieval.py::TestContextRetriever::test_retrieve_context_api_error`
3. `test_context_retrieval.py::TestIntegration::test_sdk_proxy_context_integration`
4. `test_context_retrieval.py::TestIntegration::test_context_injection_full_flow`

### Solution

**Phase 1: Integration Tests** - 2 hours
```python
# Add to test_context_retrieval.py
@pytest.mark.asyncio
async def test_context_retrieval_e2e(sdk_client, mock_supermemory):
    """Test context retrieval through SDK proxy handler."""
    # Configure mock
    mock_supermemory.return_value = {
        "results": [{"content": "Paris is capital..."}]
    }

    # Send request
    response = sdk_client.post(
        "/v1/chat/completions",
        json={
            "model": "claude-sonnet-4.5",
            "messages": [{"role": "user", "content": "Tell me about Paris"}]
        },
        headers={"x-sm-user-id": "test-user"}
    )

    # Verify Supermemory called
    assert mock_supermemory.called
    assert response.status_code == 200
```

**Phase 2: Mock Supermemory** - 1 hour
```python
# Add to conftest.py
@pytest.fixture
def mock_supermemory_api():
    with patch("proxy.context_retriever.httpx.AsyncClient") as mock:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "results": [{"content": "...", "score": 0.95}]
        }
        mock.request.return_value = mock_response
        yield mock
```

### Files to Modify

1. **tests/test_context_retrieval.py** (add integration tests)
   - New section: `TestEndToEndIntegration`
   - Tests: context injection, error handling, config-based enable/disable

2. **tests/conftest.py** (add Supermemory mock)
   - Fixture: `mock_supermemory_api`
   - Response generator: `_create_supermemory_response`

3. **src/proxy/litellm_proxy_sdk.py** (verify integration points)
   - Ensure `apply_context_retrieval` is called
   - Verify error handling for Supermemory failures

### Implementation Steps

1. Add `mock_supermemory_api` fixture to `conftest.py`
2. Write integration test in `test_context_retrieval.py`
3. Mock httpx calls to Supermemory API
4. Verify messages modified with context
5. Test error graceful degradation
6. Run `pytest tests/test_context_retrieval.py -v`

### Dependencies

- **Blocks**: None (tests are isolated)
- **Blocked by**: Group 1 (routing format must be consistent)

---

## Group 3: Port Registry API Changed (🟢 Low, 3 tests)

### Problem

Tests call `registry.allocate_port()` but current API uses `registry.get_or_allocate_port()`.

```python
# Old API (tests use)
port = registry.allocate_port(project_path)

# Current API (implemented)
port = registry.get_or_allocate_port(project_path)
```

### Root Cause

**File**: `src/interceptor/port_registry.py:134`
```python
class PortRegistry:
    def get_or_allocate_port(self, project_path: str) -> int:
        """Get existing port or allocate a new one."""
        # ✅ This method exists

    # ❌ No allocate_port() method
```

Tests written against old API before refactoring to clearer name.

### Affected Tests

1. `test_interceptor.py::test_allocate_port`
2. `test_interceptor.py::test_allocate_multiple_projects`
3. `test_interceptor_integration.py::test_port_allocation_persistence`

### Solution

**Option A: Update Tests (Recommended)** - 30 minutes
```python
# Change from:
port = registry.allocate_port(project_path)

# To:
port = registry.get_or_allocate_port(project_path)
```

**Option B: Add Alias Method** - 15 minutes
```python
# In port_registry.py
def allocate_port(self, project_path: str) -> int:
    """Deprecated: Use get_or_allocate_port() instead."""
    return self.get_or_allocate_port(project_path)
```

**Recommendation**: Option A - Update tests to use current API.

### Files to Modify

1. **tests/test_interceptor.py** (lines 42, 52-53, 61-62, 71, 76, 85)
   - Find/replace: `allocate_port` → `get_or_allocate_port`

2. **tests/test_interceptor_integration.py** (line 176)
   - Update call site

### Implementation Steps

1. Search for `allocate_port` in test files
2. Replace with `get_or_allocate_port`
3. Update docstrings if needed
4. Run `pytest tests/test_interceptor*.py -v`

### Dependencies

- **Blocks**: None
- **Blocked by**: None

---

## Group 4: SDK Session Manager Mock Issues (🔴 Critical, 6 tests)

### Problem

Tests mock `LiteLLMSessionManager` incorrectly, causing `TypeError` when SDK proxy tries to use the mocked session.

```python
# Test Mock (wrong)
@patch("proxy.litellm_proxy_sdk.LiteLLMSessionManager.get_session")
def test_something(mock_get_session):
    mock_get_session.return_value = Mock()  # ❌ Missing async methods
    # SDK proxy calls: await session.request(...)
    # TypeError: 'Mock' object is not awaitable

# Correct Mock
mock_session = AsyncMock()
mock_session.request = AsyncMock(return_value=mock_response)
mock_get_session.return_value = mock_session  # ✅ Properly async
```

### Root Cause

**File**: `src/proxy/session_manager.py:67-85`
```python
class LiteLLMSessionManager:
    @classmethod
    async def get_session(cls) -> httpx.AsyncClient:
        # Returns real httpx.AsyncClient
        # Tests must mock with AsyncMock, not Mock
```

Tests create synchronous `Mock()` when they need `AsyncMock()` with proper async context manager methods.

### Affected Tests

1. `test_sdk_components.py::TestSessionManager::test_session_singleton`
2. `test_sdk_components.py::TestSessionManager::test_cookie_persistence`
3. `test_sdk_integration.py::test_litellm_sdk_call`
4. `test_sdk_integration.py::test_session_injection`
5. `test_sdk_integration.py::test_concurrent_requests_share_session`
6. `test_sdk_integration.py::test_cookies_persist_across_calls`

### Solution

**Fix Mock Configuration** - 3-4 hours

```python
# Add to conftest.py
@pytest.fixture
def mock_litellm_session():
    """
    Properly configured mock for LiteLLMSessionManager.

    Returns AsyncMock with httpx.AsyncClient interface:
    - request() method
    - Context manager methods (__aenter__, __aexit__)
    - cookies attribute
    - aclose() method
    """
    mock_client = AsyncMock(spec=httpx.AsyncClient)

    # Configure request method
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.headers = {"content-type": "application/json"}
    mock_response.content = json.dumps({
        "id": "chatcmpl-test",
        "choices": [{"message": {"role": "assistant", "content": "Test"}}]
    }).encode()

    mock_client.request = AsyncMock(return_value=mock_response)

    # Configure context manager
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    # Configure cleanup
    mock_client.aclose = AsyncMock()

    # Configure cookies
    mock_client.cookies = httpx.Cookies()

    # Patch get_session to return this mock
    with patch(
        "proxy.session_manager.LiteLLMSessionManager.get_session",
        new=AsyncMock(return_value=mock_client)
    ):
        yield mock_client
```

### Files to Modify

1. **tests/conftest.py** (add `mock_litellm_session` fixture)
   - Complete httpx.AsyncClient interface
   - Proper async context manager
   - Cookie jar

2. **tests/test_sdk_components.py** (use fixture)
   - Remove inline mocking
   - Use `mock_litellm_session` fixture

3. **tests/test_sdk_integration.py** (use fixture)
   - Replace manual patches
   - Use centralized fixture

### Implementation Steps

1. Create `mock_litellm_session` fixture in `conftest.py`
2. Update `test_sdk_components.py` to use fixture
3. Update `test_sdk_integration.py` to use fixture
4. Verify async methods properly mocked
5. Run `pytest tests/test_sdk_*.py -v`

### Dependencies

- **Blocks**: Group 5 (SDK backend errors depend on proper mocking)
- **Blocked by**: None

---

## Group 5: SDK Backend 500 Errors (🔴 Critical, 12 tests)

### Problem

All end-to-end tests against SDK proxy fail with HTTP 500 errors because the mock httpx client doesn't properly handle LiteLLM SDK's internal HTTP calls.

```python
# SDK Proxy Flow
1. Test sends request to SDK proxy
2. SDK proxy calls litellm.acompletion()
3. LiteLLM SDK makes HTTP request via httpx client
4. Mock returns generic response (wrong format)
5. LiteLLM fails to parse response
6. Test sees HTTP 500 Internal Server Error
```

### Root Cause

**File**: `tests/conftest.py:347` (mock_httpx_client)

Current mock doesn't understand LiteLLM SDK's internal API calls:

```python
# Current Mock (too simple)
mock_response.content = b'{"result": "success"}'  # ❌ Not OpenAI format

# LiteLLM SDK expects:
{
  "id": "chatcmpl-...",
  "object": "chat.completion",
  "choices": [{"message": {...}}],
  "usage": {...}
}
```

The `_smart_response_router` in conftest.py handles this for binary proxy tests, but SDK tests bypass it.

### Affected Tests

1-12. All tests in `test_sdk_e2e.py` (12 total):
   - `test_anthropic_real_call`
   - `test_openai_real_call`
   - `test_streaming_real_call`
   - `test_cookies_persist_across_requests`
   - `test_session_maintains_cookies`
   - `test_user_id_routing_pycharm`
   - `test_custom_user_id`
   - `test_sequential_requests`
   - `test_concurrent_requests_async`
   - `test_context_length_error`
   - `test_invalid_parameter`
   - `test_response_time_acceptable`

### Solution

**Enhanced Mock Integration** - 4-6 hours

The smart response router exists but isn't used by SDK tests. We need to:

1. **Ensure SDK Uses Mock Client** (2 hours)
```python
# In conftest.py, enhance mock_litellm_session
@pytest.fixture
def mock_litellm_session(mock_httpx_client):
    """Session that uses smart routing httpx mock."""
    # Use the same mock_httpx_client that has _smart_response_router
    with patch(
        "proxy.session_manager.LiteLLMSessionManager.get_session",
        new=AsyncMock(return_value=mock_httpx_client)
    ):
        with patch(
            "litellm.aclient_session",
            new=mock_httpx_client
        ):
            yield mock_httpx_client
```

2. **Fix LiteLLM SDK Mocking** (2 hours)
```python
# Current problem: LiteLLM SDK makes its own httpx client internally
# Solution: Mock litellm.acompletion directly

@pytest.fixture
def mock_litellm_completion():
    """Mock litellm.acompletion to return proper format."""
    async def mock_completion(*args, **kwargs):
        return {
            "id": f"chatcmpl-{int(time.time())}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": kwargs.get("model", "claude-sonnet-4.5"),
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "This is a test response"
                },
                "finish_reason": "stop"
            }],
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 20,
                "total_tokens": 30
            }
        }

    with patch("litellm.acompletion", new=AsyncMock(side_effect=mock_completion)):
        yield mock_completion
```

3. **Update E2E Tests** (1-2 hours)
```python
# In test_sdk_e2e.py
def test_anthropic_real_call(e2e_client, mock_litellm_completion):
    response = e2e_client.post(
        "/v1/chat/completions",
        json=get_chat_completion_request(model="claude-sonnet-4.5")
    )

    assert response.status_code == 200  # ✅ No longer 500
    data = response.json()
    assert "choices" in data
```

### Files to Modify

1. **tests/conftest.py**
   - Enhance `mock_litellm_session` to use `mock_httpx_client`
   - Add `mock_litellm_completion` fixture
   - Ensure smart routing available to SDK tests

2. **tests/test_sdk_e2e.py**
   - Add `mock_litellm_completion` fixture to all tests
   - Or use session-scoped mock for entire module

3. **src/proxy/litellm_proxy_sdk.py** (verify)
   - Ensure `litellm.aclient_session` properly used
   - Check error handling for malformed responses

### Implementation Steps

1. Create `mock_litellm_completion` fixture (primary fix)
2. Update `mock_litellm_session` to inject mock_httpx_client
3. Add fixture to all `test_sdk_e2e.py` tests
4. Verify response formats match expectations
5. Test error scenarios (4xx, 5xx)
6. Run `pytest tests/test_sdk_e2e.py -v`

### Dependencies

- **Blocks**: None (these are end-to-end tests)
- **Blocked by**: Group 4 (session manager must be properly mocked first)

---

## Group 6: Error Response Format Inconsistencies (🟡 Medium, 6 tests)

### Problem

Tests expect errors in `{"error": {...}}` format, but some handlers return different structures:

```python
# Expected Format (OpenAI compatible)
{
  "error": {
    "type": "invalid_request_error",
    "message": "Invalid parameter",
    "code": "invalid_parameter"
  }
}

# Actual Format (some handlers)
{
  "detail": "Invalid parameter"  # ❌ FastAPI default
}
```

### Root Cause

**File**: `src/proxy/error_handlers.py`

Some exceptions bypass custom error handlers and fall through to FastAPI's default exception handler:

```python
# Custom handler (correct format)
@app.exception_handler(litellm.BadRequestError)
async def handle_bad_request(request, exc):
    return ErrorResponse.build(...)  # ✅ Returns {"error": {...}}

# Missing handler
@app.exception_handler(ValueError)  # ❌ Not registered
async def handle_value_error(request, exc):
    # Falls through to FastAPI default
    # Returns {"detail": "..."} instead of {"error": {...}}
```

### Affected Tests

1. `test_error_handlers.py::test_bad_request_error_format`
2. `test_error_handlers.py::test_rate_limit_error_has_retry_after`
3. `test_error_handlers.py::test_authentication_error_format`
4. `test_sdk_e2e.py::test_context_length_error`
5. `test_sdk_e2e.py::test_invalid_parameter`
6. `test_binary_vs_sdk.py::test_error_format_consistent`

### Solution

**Register Missing Handlers** - 2 hours

```python
# In error_handlers.py
def register_exception_handlers(app: FastAPI, include_debug_info: bool = False):
    """Register all exception handlers."""
    handler = LiteLLMErrorHandler(include_debug_info=include_debug_info)

    # Existing handlers
    app.add_exception_handler(litellm.BadRequestError, handler.handle_bad_request)
    app.add_exception_handler(litellm.AuthenticationError, handler.handle_auth_error)

    # Missing handlers (add these)
    app.add_exception_handler(ValueError, handler.handle_value_error)
    app.add_exception_handler(KeyError, handler.handle_key_error)
    app.add_exception_handler(TypeError, handler.handle_type_error)

    # Catch-all for unexpected errors
    app.add_exception_handler(Exception, handler.handle_generic_error)
```

Add handler methods:
```python
# In LiteLLMErrorHandler class
async def handle_value_error(
    self, request: Request, exc: ValueError
) -> JSONResponse:
    """Handle ValueError with proper format."""
    return JSONResponse(
        status_code=400,
        content={
            "error": {
                "type": "invalid_request_error",
                "message": str(exc),
                "code": "invalid_value"
            }
        }
    )
```

### Files to Modify

1. **src/proxy/error_handlers.py**
   - Add `handle_value_error` method
   - Add `handle_key_error` method
   - Add `handle_type_error` method
   - Add `handle_generic_error` catch-all
   - Update `register_exception_handlers` to register all handlers

2. **tests/test_error_handlers.py**
   - Add tests for new handlers
   - Verify format consistency

### Implementation Steps

1. Identify all exception types that can be raised
2. Add handler methods for each type
3. Register handlers in `register_exception_handlers`
4. Test each handler returns proper format
5. Add catch-all handler for unexpected exceptions
6. Run `pytest tests/test_error_handlers.py -v`

### Dependencies

- **Blocks**: None
- **Blocked by**: None

---

## Group 7: Streaming Async Generator Type Error (🟢 Low, 2 tests)

### Problem

Streaming tests fail with type errors when SDK proxy returns non-iterable or wrong type:

```python
# Expected: AsyncGenerator[bytes, None]
async for chunk in response:
    # Process chunk

# Actual: Something else returned
# TypeError: 'NoneType' object is not async iterable
```

### Root Cause

**File**: `src/proxy/litellm_proxy_sdk.py:395`
```python
async def stream_completion(response_iterator):
    if not isinstance(response_iterator, CustomStreamWrapper):
        raise ValueError(f"Expected iterator but got: {type(response_iterator)}")
    # ✅ Validation exists but doesn't help tests
```

Tests mock LiteLLM's streaming response incorrectly:

```python
# Wrong Mock
mock_stream = Mock()
mock_stream.__aiter__ = lambda: iter([b"chunk1", b"chunk2"])  # ❌ Not async

# Correct Mock
async def async_chunks():
    yield b'data: {"delta": {"content": "chunk1"}}\n\n'
    yield b'data: [DONE]\n\n'

mock_stream.__aiter__ = lambda: async_chunks()  # ✅ Async generator
```

### Affected Tests

1. `test_sdk_e2e.py::test_streaming_real_call`
2. `test_sdk_integration.py::test_streaming_response_format`

### Solution

**Fix Streaming Mocks** - 1-2 hours

```python
# Add to conftest.py
@pytest.fixture
def mock_streaming_response():
    """
    Properly configured streaming response mock.

    Returns CustomStreamWrapper-like object with async iteration.
    """
    from litellm.litellm_core_utils.streaming_handler import CustomStreamWrapper

    async def generate_chunks():
        """Generate SSE-formatted chunks."""
        # Chunk 1: Content delta
        yield {
            "id": "chatcmpl-test",
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": "claude-sonnet-4.5",
            "choices": [{
                "index": 0,
                "delta": {"content": "Hello"},
                "finish_reason": None
            }]
        }

        # Chunk 2: More content
        yield {
            "id": "chatcmpl-test",
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": "claude-sonnet-4.5",
            "choices": [{
                "index": 0,
                "delta": {"content": " World"},
                "finish_reason": None
            }]
        }

        # Chunk 3: End
        yield {
            "id": "chatcmpl-test",
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": "claude-sonnet-4.5",
            "choices": [{
                "index": 0,
                "delta": {},
                "finish_reason": "stop"
            }]
        }

    # Create CustomStreamWrapper
    mock_wrapper = CustomStreamWrapper(
        completion_stream=generate_chunks(),
        model="claude-sonnet-4.5"
    )

    return mock_wrapper
```

Use in tests:
```python
@pytest.mark.asyncio
async def test_streaming(sdk_client, mock_streaming_response):
    with patch("litellm.acompletion", return_value=mock_streaming_response):
        response = sdk_client.post(
            "/v1/chat/completions",
            json={"model": "claude-sonnet-4.5", "messages": [...], "stream": True}
        )

        # Response should be StreamingResponse
        assert response.headers["content-type"] == "text/event-stream"

        # Collect chunks
        chunks = []
        async for chunk in response:
            chunks.append(chunk)

        assert len(chunks) > 0
```

### Files to Modify

1. **tests/conftest.py**
   - Add `mock_streaming_response` fixture
   - Ensure returns proper `CustomStreamWrapper`

2. **tests/test_sdk_e2e.py**
   - Update `test_streaming_real_call` to use fixture
   - Verify SSE format

3. **tests/test_sdk_integration.py**
   - Update `test_streaming_response_format` to use fixture

### Implementation Steps

1. Study `litellm.litellm_core_utils.streaming_handler.CustomStreamWrapper`
2. Create `mock_streaming_response` fixture
3. Update streaming tests to use fixture
4. Verify SSE format in responses
5. Test with `stream=True` parameter
6. Run `pytest -k "streaming" -v`

### Dependencies

- **Blocks**: None
- **Blocked by**: None

---

## Fix Order & Timeline

### Critical Path (Must Complete First)

**Day 1** (8 hours):
1. **Group 1**: Binary routing format (2-3 hrs) - BLOCKING
2. **Group 4**: SDK session manager mocks (3-4 hrs) - BLOCKING
3. **Group 3**: Port Registry API (1 hr) - Easy win

**Day 2** (8 hours):
4. **Group 5**: SDK backend 500 errors (4-6 hrs) - DEPENDS ON GROUP 4
5. **Group 6**: Error response format (2 hrs)

**Day 3** (4-5 hours):
6. **Group 2**: Context retrieval integration (2-3 hrs)
7. **Group 7**: Streaming async generator (1-2 hrs)

### Dependency Graph

```
Day 1:
  Group 1 (routing format)
     ↓
  Group 2 (context retrieval) [can wait]

  Group 4 (session mocks)
     ↓
  Group 5 (SDK 500 errors)

  Group 3 (port registry) [independent]

Day 2:
  Group 5 (continue if needed)
  Group 6 (error format) [independent]

Day 3:
  Group 2 (finish context retrieval)
  Group 7 (streaming) [independent]
```

### Parallel Work Opportunities

**Can Work Simultaneously**:
- Group 1 + Group 4 (different files, no overlap)
- Group 3 + anything (completely independent)
- Group 6 + anything (error handlers isolated)
- Group 7 + anything (streaming isolated)

**Must Be Sequential**:
- Group 1 → Group 2 (routing format must be fixed first)
- Group 4 → Group 5 (mocks must work before e2e tests)

---

## Risk Assessment

### High Risk (Requires Careful Testing)

**Group 5: SDK Backend 500 Errors**
- **Risk**: Mocking LiteLLM SDK is complex, may have side effects
- **Mitigation**:
  - Test with both mock and real API (with flag)
  - Add detailed logging to trace mock calls
  - Create separate test suite for real API calls

**Group 4: SDK Session Manager**
- **Risk**: Breaking session management affects production code
- **Mitigation**:
  - Only modify test mocks, not production code
  - Verify production session manager still works
  - Add integration test with real httpx client

### Medium Risk

**Group 2: Context Retrieval**
- **Risk**: Supermemory integration may have undiscovered issues
- **Mitigation**:
  - Test with mock Supermemory API first
  - Add feature flag to disable context retrieval
  - Graceful degradation if API fails

### Low Risk (Safe Changes)

**Groups 1, 3, 6, 7**
- Test-only changes
- No production code impact
- Easy to verify and rollback

---

## Success Criteria

### Definition of Done

**Per Group**:
- [ ] All tests in group pass
- [ ] No new test failures introduced
- [ ] Existing passing tests still pass
- [ ] Code reviewed for correctness

**Overall**:
- [ ] `pytest tests/ -v` shows 0 failures
- [ ] Coverage remains above 80%
- [ ] Documentation updated (if API changed)
- [ ] No regressions in binary proxy tests
- [ ] No regressions in SDK proxy tests

### Validation Steps

After each group fix:
```bash
# Run group-specific tests
pytest tests/test_<group>.py -v

# Run full test suite
pytest tests/ -v

# Check coverage
pytest tests/ --cov=src --cov-report=html

# Verify no regressions
pytest tests/test_memory_routing.py -v  # Core functionality
pytest tests/test_binary_vs_sdk.py -v   # Parity tests
```

---

## Rollback Plan

### If Fix Causes More Failures

1. **Identify Scope**
   ```bash
   git diff HEAD tests/  # Show test changes
   git diff HEAD src/    # Show production changes
   ```

2. **Rollback Tests Only**
   ```bash
   git checkout HEAD -- tests/test_<failed_group>.py
   ```

3. **Rollback Everything**
   ```bash
   git reset --hard HEAD
   ```

4. **Analyze Failure**
   - Review test output
   - Check if production code needs adjustment
   - Verify mock configuration

### If Production Code Broken

**Signs**:
- Manual testing fails
- PyCharm integration broken
- Claude Code cannot connect

**Actions**:
1. Immediately revert production changes
2. Keep test changes for documentation
3. Re-evaluate approach
4. Consider feature flag for risky changes

---

## Implementation Notes

### Testing Best Practices

**Always Test Both Proxies**:
```python
@pytest.mark.parametrize("proxy_type", ["binary", "sdk"])
def test_feature(proxy_type, binary_client, sdk_client):
    client = binary_client if proxy_type == "binary" else sdk_client
    # Test with both architectures
```

**Mock at Right Level**:
```python
# ❌ Too low level
@patch("httpx.AsyncClient.request")

# ✅ Right level
@patch("litellm.acompletion")

# ✅ Even better
use fixture: mock_litellm_completion
```

**Verify Mock Called**:
```python
mock_completion.assert_called_once()
mock_completion.assert_called_with(
    model="claude-sonnet-4.5",
    messages=[...],
    extra_headers={"x-sm-user-id": "test-user"}
)
```

### Code Quality

**Add Type Hints**:
```python
def configure_mock(
    client: AsyncMock,
    status_code: int = 200,
    response_data: Dict[str, Any] = None
) -> None:
    """Configure mock client with response."""
```

**Document Complex Mocks**:
```python
@pytest.fixture
def mock_litellm_session():
    """
    Properly configured mock for LiteLLMSessionManager.

    Provides:
    - httpx.AsyncClient interface
    - Async context manager support
    - Cookie persistence
    - Request/response cycle

    Usage:
        def test_something(mock_litellm_session):
            # Session automatically available
            response = await litellm.acompletion(...)
    """
```

**Test Edge Cases**:
```python
def test_streaming_with_error(mock_streaming_response):
    """Test streaming when provider returns error mid-stream."""
    # Setup mock to raise exception after 2 chunks

def test_empty_context_retrieval(mock_supermemory):
    """Test context retrieval when Supermemory returns no results."""
    mock_supermemory.return_value = {"results": []}
```

---

## Post-Fix Validation

### Manual Testing Checklist

After all fixes complete:

**Binary Proxy**:
- [ ] Start binary proxy: `poetry run start-proxies`
- [ ] Test PyCharm AI Assistant connection
- [ ] Send chat request via curl
- [ ] Verify `/memory-routing/info` endpoint
- [ ] Check logs for errors

**SDK Proxy**:
- [ ] Start SDK proxy: `uvicorn src.proxy.litellm_proxy_sdk:app`
- [ ] Send chat request via curl
- [ ] Test streaming request
- [ ] Verify cookies persist (check session cookies)
- [ ] Check Supermemory integration (if enabled)

**Integration**:
- [ ] Run full test suite: `./RUN_TESTS.sh all`
- [ ] Check coverage report
- [ ] Verify no deprecation warnings
- [ ] Review log output for anomalies

### Documentation Updates

**Update After Completion**:
- [ ] `docs/guides/TESTING.md` - Add new mock fixtures
- [ ] `tests/README.md` - Document test structure
- [ ] `docs/CHANGELOG.md` - Record fix completion
- [ ] `CLAUDE.md` - Update if API changed

---

## Architectural Implications

### Long-Term Considerations

**Binary vs SDK Decision**:
- Current: Both implementations maintained
- Future: Choose one based on production needs
- Decision factors:
  - Cookie persistence (favors SDK)
  - Operational simplicity (favors binary)
  - Performance (need benchmarks)
  - Maintainability (favors single approach)

**Recommendation**: After tests pass, conduct production trial:
1. Deploy SDK proxy to staging
2. Monitor error rates, latency, cookie handling
3. Compare with binary proxy metrics
4. Make data-driven decision
5. Deprecate unused implementation

**Test Strategy Going Forward**:
- Maintain dual testing until decision made
- Once decided, convert to single-proxy tests
- Keep compatibility tests for migration period

### Technical Debt

**Created by These Fixes**:
- Increased mock complexity in conftest.py
- Duplicated test patterns for binary vs SDK
- Context retrieval partially tested

**Should Address Later**:
- Consolidate mock fixtures (DRY principle)
- Create test utilities module
- Add comprehensive integration test suite
- Document testing patterns in TESTING.md

**Not Addressing Now** (Out of Scope):
- Binary vs SDK architectural decision
- Performance optimization
- Production deployment strategy
- Monitoring and observability

---

## Summary

### By The Numbers

- **Total Failures**: 43 tests
- **Error Groups**: 7 distinct types
- **Critical Fixes**: 3 groups (1, 4, 5)
- **Estimated Time**: 15-21 hours over 2-3 days
- **Files Modified**: ~10 files (mostly tests)
- **Production Impact**: Minimal (test infrastructure only)

### Key Insights

1. **Root Cause**: Architectural transition from binary to SDK created test infrastructure gaps
2. **Not Production Bugs**: Code works, tests don't reflect reality
3. **Fix Strategy**: Update tests to match actual APIs, improve mocks
4. **Critical Path**: Fix mocking infrastructure (Groups 1, 4) before e2e tests (Group 5)
5. **Low Risk**: Most changes are test-only, easily reversible

### Next Steps

1. Review this strategy with team
2. Begin with Group 1 (routing format) - quickest win
3. Continue with Group 4 (session mocks) - unblocks Group 5
4. Tackle Group 5 (SDK e2e) - largest impact
5. Clean up remaining groups (2, 3, 6, 7)
6. Full regression testing
7. Update documentation
8. Close issue

---

**Document Version**: 1.0
**Created**: 2025-11-09
**Next Review**: After Group 1-4 complete
**Owner**: Development Team
