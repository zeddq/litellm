# httpx.AsyncClient Mocking Strategy for LiteLLM Memory Proxy Tests

**Version:** 1.0
**Date:** 2025-11-09
**Status:** Design Document

## Executive Summary

This document defines a comprehensive mocking strategy for `httpx.AsyncClient` in the LiteLLM Memory Proxy test suite. The strategy addresses current test failures ("All connection attempts failed" HTTP 500) by providing properly configured mock fixtures that simulate LiteLLM binary responses without requiring actual HTTP connections.

---

## Current State Analysis

### Architecture Overview

The LiteLLM Memory Proxy uses an **external binary proxy pattern**:

```
Test Client → Memory Proxy (FastAPI) → httpx.AsyncClient → LiteLLM Binary
                                           [MOCK HERE]
```

### Current Mocking Approach

**Location:** `tests/conftest.py`

**Existing Fixture:** `mock_httpx_client`
- Creates a Mock instance with async context manager support
- Configures default 200 OK response
- **Patches:** `ProxySessionManager.get_session` to return the mock
- **Issue:** Only patches ProxySessionManager, doesn't handle direct `httpx.AsyncClient()` instantiation in `proxy_request()`

### Key Problem

The `proxy_request()` function (line 293 in `litellm_proxy_with_memory.py`) creates httpx.AsyncClient directly:

```python
async def proxy_request(...) -> tuple[int, httpx.Headers, bytes]:
    url = f"{litellm_base_url}{path}"

    async with httpx.AsyncClient(timeout=600.0) as client:  # ← Direct instantiation
        try:
            response = await client.request(
                method=method, url=url, headers=headers, content=body
            )
            return response.status_code, response.headers, response.content
        except Exception as e:
            logger.error(f"Proxy request failed: {e}")
            raise
```

**Current tests patch** `httpx.AsyncClient` but the mock configuration is incomplete, leading to:
- Connection errors (no response configured)
- HTTP 500 errors ("All connection attempts failed")
- Test failures despite correct mock setup

---

## Design Principles

1. **Realistic Responses:** Mock responses must match actual LiteLLM binary format (OpenAI-compatible)
2. **Endpoint-Specific:** Different endpoints require different response structures
3. **Reusability:** Fixtures should be composable and reusable across test suites
4. **Minimal Patching:** Use existing fixtures, extend with endpoint-specific configs
5. **Backward Compatible:** Don't break existing tests during migration
6. **Isolation:** Each test should get a fresh mock instance (function scope)

---

## Fixture Architecture

### Layer 1: Core Mock Infrastructure (Already Exists)

**File:** `tests/conftest.py`

```python
@pytest.fixture
def mock_httpx_client():
    """
    Base mock for httpx.AsyncClient with async context manager support.

    Provides:
    - Async context manager protocol (__aenter__/__aexit__)
    - Mock request() method (AsyncMock)
    - Default 200 OK response
    - Cookie jar support
    - aclose() for cleanup

    Auto-patches: ProxySessionManager.get_session
    """
    # [Existing implementation - keep as is]
```

**Status:** ✅ Working, keep as-is

---

### Layer 2: Response Templates

**File:** `tests/fixtures/mock_responses.py` (Already exists)

**Existing Functions:**
- `mock_completion_response()` - Chat completion response
- `mock_models_list()` - Models list endpoint
- `mock_routing_info()` - Memory routing info
- `mock_error_response()` - Error responses
- `MockHTTPResponse` - HTTP response object

**Status:** ✅ Comprehensive, no changes needed

---

### Layer 3: Endpoint-Specific Configuration Fixtures (NEW)

**File:** `tests/conftest.py` (additions)

These fixtures configure `mock_httpx_client` with appropriate responses for specific endpoints:

```python
@pytest.fixture
def mock_chat_completions_response(mock_httpx_client, mock_litellm_chat_completion_response):
    """
    Configure mock_httpx_client for /v1/chat/completions endpoint.

    Returns properly formatted OpenAI-compatible chat completion response.

    Usage:
        def test_chat(mock_chat_completions_response):
            # mock_chat_completions_response is pre-configured
            # Just use it in your test
            pass
    """
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.headers = httpx.Headers({"content-type": "application/json"})
    mock_response.content = json.dumps(mock_litellm_chat_completion_response).encode()
    mock_response.cookies = {}

    mock_httpx_client.request = AsyncMock(return_value=mock_response)

    return mock_httpx_client


@pytest.fixture
def mock_models_endpoint_response(mock_httpx_client, mock_litellm_models_response):
    """
    Configure mock_httpx_client for /v1/models endpoint.

    Returns list of available models.
    """
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.headers = httpx.Headers({"content-type": "application/json"})
    mock_response.content = json.dumps(mock_litellm_models_response).encode()
    mock_response.cookies = {}

    mock_httpx_client.request = AsyncMock(return_value=mock_response)

    return mock_httpx_client


@pytest.fixture
def mock_health_endpoint_response(mock_httpx_client, mock_litellm_health_response):
    """
    Configure mock_httpx_client for /health endpoint.
    """
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.headers = httpx.Headers({"content-type": "application/json"})
    mock_response.content = json.dumps(mock_litellm_health_response).encode()
    mock_response.cookies = {}

    mock_httpx_client.request = AsyncMock(return_value=mock_response)

    return mock_httpx_client


@pytest.fixture
def mock_error_response_fixture(mock_httpx_client):
    """
    Factory fixture for configuring error responses.

    Returns a function that accepts (status_code, error_message).

    Usage:
        def test_error(mock_error_response_fixture):
            client = mock_error_response_fixture(404, "Model not found")
            # Now client returns 404 error
    """
    def configure_error(status_code: int, error_message: str):
        from tests.fixtures import mock_error_response

        error_data = mock_error_response(
            status_code=status_code,
            error_type="invalid_request_error",
            message=error_message
        )

        mock_response = Mock()
        mock_response.status_code = status_code
        mock_response.headers = httpx.Headers({"content-type": "application/json"})
        mock_response.content = json.dumps(error_data).encode()
        mock_response.cookies = {}

        mock_httpx_client.request = AsyncMock(return_value=mock_response)

        return mock_httpx_client

    return configure_error


@pytest.fixture
def mock_streaming_response(mock_httpx_client):
    """
    Configure mock_httpx_client for streaming responses.

    Returns async iterator of Server-Sent Events (SSE) format.

    Usage:
        def test_streaming(mock_streaming_response):
            # mock_streaming_response returns streaming chunks
            pass
    """
    from tests.fixtures import mock_streaming_chunks_sequence

    chunks = mock_streaming_chunks_sequence()

    async def mock_stream():
        for chunk in chunks:
            yield f"data: {json.dumps(chunk)}\n\n".encode()
        yield b"data: [DONE]\n\n"

    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.headers = httpx.Headers({
        "content-type": "text/event-stream",
        "cache-control": "no-cache"
    })
    mock_response.aiter_bytes = mock_stream
    mock_response.cookies = {}

    mock_httpx_client.request = AsyncMock(return_value=mock_response)

    return mock_httpx_client
```

---

### Layer 4: Route-Aware Mock (ADVANCED - Optional)

For tests that need to handle multiple endpoints in one test:

```python
@pytest.fixture
def mock_httpx_smart_router(mock_httpx_client):
    """
    Smart router that returns different responses based on request path.

    Automatically detects endpoint from URL and returns appropriate response.

    Usage:
        def test_multiple_endpoints(mock_httpx_smart_router):
            # Automatically handles /v1/chat/completions, /v1/models, /health
            pass
    """
    from tests.fixtures import (
        mock_completion_response,
        mock_models_list,
        mock_litellm_health_response
    )

    async def smart_request(method, url, **kwargs):
        mock_response = Mock()
        mock_response.cookies = {}
        mock_response.headers = httpx.Headers({"content-type": "application/json"})

        # Route based on path
        if "/v1/chat/completions" in url:
            mock_response.status_code = 200
            mock_response.content = json.dumps(mock_completion_response()).encode()
        elif "/v1/models" in url:
            mock_response.status_code = 200
            mock_response.content = json.dumps(mock_models_list()).encode()
        elif "/health" in url:
            mock_response.status_code = 200
            mock_response.content = json.dumps({"status": "healthy"}).encode()
        else:
            # Default 404
            mock_response.status_code = 404
            mock_response.content = b'{"error": {"message": "Not found"}}'

        return mock_response

    mock_httpx_client.request = AsyncMock(side_effect=smart_request)

    return mock_httpx_client
```

---

## Response Format Specifications

### /v1/chat/completions (Non-streaming)

**Status Code:** 200
**Headers:**
```python
{
    "content-type": "application/json",
    "x-request-id": "chatcmpl-123"  # Optional
}
```

**Body:**
```json
{
    "id": "chatcmpl-test-123",
    "object": "chat.completion",
    "created": 1234567890,
    "model": "claude-sonnet-4.5",
    "choices": [
        {
            "index": 0,
            "message": {
                "role": "assistant",
                "content": "This is a test response from the mocked LiteLLM backend."
            },
            "finish_reason": "stop"
        }
    ],
    "usage": {
        "prompt_tokens": 10,
        "completion_tokens": 20,
        "total_tokens": 30
    }
}
```

**Source:** `mock_litellm_chat_completion_response` fixture (already exists)

---

### /v1/chat/completions (Streaming)

**Status Code:** 200
**Headers:**
```python
{
    "content-type": "text/event-stream",
    "cache-control": "no-cache",
    "connection": "keep-alive"
}
```

**Body:** Server-Sent Events (SSE) format
```
data: {"id":"chatcmpl-123","object":"chat.completion.chunk","created":1234567890,"model":"claude-sonnet-4.5","choices":[{"index":0,"delta":{"content":"Hello"},"finish_reason":null}]}

data: {"id":"chatcmpl-123","object":"chat.completion.chunk","created":1234567890,"model":"claude-sonnet-4.5","choices":[{"index":0,"delta":{"content":"!"},"finish_reason":null}]}

data: {"id":"chatcmpl-123","object":"chat.completion.chunk","created":1234567890,"model":"claude-sonnet-4.5","choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}

data: [DONE]
```

**Source:** `mock_streaming_chunks_sequence()` from `mock_responses.py`

---

### /v1/models

**Status Code:** 200
**Headers:**
```python
{"content-type": "application/json"}
```

**Body:**
```json
{
    "object": "list",
    "data": [
        {
            "id": "claude-sonnet-4.5",
            "object": "model",
            "created": 1234567890,
            "owned_by": "anthropic"
        },
        {
            "id": "gpt-4",
            "object": "model",
            "created": 1234567890,
            "owned_by": "openai"
        }
    ]
}
```

**Source:** `mock_litellm_models_response` fixture (already exists)

---

### /health

**Status Code:** 200
**Headers:**
```python
{"content-type": "application/json"}
```

**Body:**
```json
{
    "status": "healthy",
    "timestamp": "2024-01-01T00:00:00Z"
}
```

**Source:** `mock_litellm_health_response` fixture (already exists)

---

### Error Responses

**Status Codes:** 400, 401, 404, 429, 500, 503
**Headers:**
```python
{"content-type": "application/json"}
```

**Body:**
```json
{
    "error": {
        "message": "Descriptive error message",
        "type": "invalid_request_error",
        "code": "model_not_found"
    }
}
```

**Source:** `mock_error_response()` function (already exists)

---

## Integration with Existing Tests

### Pattern 1: Direct httpx.AsyncClient Patching (Current Pattern)

**Used in:** `test_memory_proxy.py`, `test_binary_vs_sdk.py`

```python
def test_chat_completion(mock_httpx_client):
    """Test using direct patching."""
    with patch("httpx.AsyncClient", return_value=mock_httpx_client):
        # Your test code
        response = client.post("/v1/chat/completions", ...)
        assert response.status_code == 200
```

**Status:** ✅ Keep this pattern, enhance mock_httpx_client configuration

---

### Pattern 2: ProxySessionManager Patching (Already Patched by mock_httpx_client)

**Used in:** Tests that rely on session persistence

```python
def test_with_session(mock_httpx_client):
    """mock_httpx_client auto-patches ProxySessionManager.get_session."""
    # No explicit patching needed!
    response = client.post("/v1/chat/completions", ...)
    assert response.status_code == 200
```

**Status:** ✅ Already working via conftest.py

---

### Pattern 3: Endpoint-Specific Fixtures (NEW - Recommended)

**Use for:** New tests, refactored tests

```python
def test_chat_with_preconfigured_mock(mock_chat_completions_response):
    """Test using endpoint-specific fixture."""
    # mock_chat_completions_response is already configured!

    with patch("httpx.AsyncClient", return_value=mock_chat_completions_response):
        response = client.post("/v1/chat/completions", ...)
        assert response.status_code == 200
        data = response.json()
        assert "choices" in data
```

---

### Pattern 4: Smart Router (Advanced)

**Use for:** Integration tests covering multiple endpoints

```python
def test_full_flow(mock_httpx_smart_router):
    """Test multiple endpoints in one test."""
    with patch("httpx.AsyncClient", return_value=mock_httpx_smart_router):
        # Check health
        health = client.get("/health")
        assert health.status_code == 200

        # List models
        models = client.get("/v1/models")
        assert models.status_code == 200

        # Chat completion
        chat = client.post("/v1/chat/completions", ...)
        assert chat.status_code == 200
```

---

## Migration Strategy

### Phase 1: Enhance Core Infrastructure (IMMEDIATE)

1. ✅ **Keep existing** `mock_httpx_client` fixture in `conftest.py`
2. ✅ **Keep existing** response templates in `mock_responses.py`
3. ✅ **Keep existing** test data in `test_data.py`
4. ✅ **Verify** existing fixtures are properly imported and used

**Files Changed:** None (verification only)

---

### Phase 2: Add Endpoint-Specific Fixtures (QUICK WIN)

1. Add 3-4 endpoint-specific fixtures to `conftest.py`:
   - `mock_chat_completions_response`
   - `mock_models_endpoint_response`
   - `mock_health_endpoint_response`
   - `mock_error_response_fixture`

2. Document usage in fixture docstrings

**Files Changed:**
- `tests/conftest.py` (additions only, ~100 lines)

**Estimated Effort:** 30 minutes

---

### Phase 3: Fix Failing Tests (PRIORITY)

Target tests in:
- `tests/test_binary_vs_sdk.py`
- `tests/test_litellm_proxy_refactored.py`

**Strategy:**
1. Identify which endpoints each test calls
2. Use appropriate endpoint-specific fixture
3. Ensure `patch("httpx.AsyncClient", return_value=fixture)` is used
4. Verify response format matches expected structure

**Example Fix:**
```python
# BEFORE (failing)
def test_chat_completion(mock_httpx_client):
    # mock_httpx_client has generic 200 OK response
    # Doesn't match OpenAI format → test fails
    pass

# AFTER (working)
def test_chat_completion(mock_chat_completions_response):
    with patch("httpx.AsyncClient", return_value=mock_chat_completions_response):
        # Now returns proper chat completion format → test passes
        pass
```

**Estimated Effort:** 1-2 hours

---

### Phase 4: Implement Smart Router (OPTIONAL)

For advanced integration tests that need multiple endpoints.

**Estimated Effort:** 1 hour

---

## Test Examples

### Example 1: Simple Chat Completion Test

```python
def test_simple_chat_completion(test_client, mock_chat_completions_response):
    """Test basic chat completion with mocked LiteLLM response."""
    request_body = {
        "model": "claude-sonnet-4.5",
        "messages": [{"role": "user", "content": "Hello!"}]
    }

    with patch("httpx.AsyncClient", return_value=mock_chat_completions_response):
        response = test_client.post(
            "/v1/chat/completions",
            json=request_body,
            headers={"Authorization": "Bearer sk-test-1234"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["object"] == "chat.completion"
        assert len(data["choices"]) > 0
        assert "content" in data["choices"][0]["message"]
```

---

### Example 2: Error Handling Test

```python
def test_model_not_found_error(test_client, mock_error_response_fixture):
    """Test handling of model not found error."""
    mock_client = mock_error_response_fixture(404, "Model 'unknown' not found")

    request_body = {
        "model": "unknown-model",
        "messages": [{"role": "user", "content": "Test"}]
    }

    with patch("httpx.AsyncClient", return_value=mock_client):
        response = test_client.post(
            "/v1/chat/completions",
            json=request_body,
            headers={"Authorization": "Bearer sk-test-1234"}
        )

        assert response.status_code == 404
        data = response.json()
        assert "error" in data
        assert "not found" in data["error"]["message"].lower()
```

---

### Example 3: Memory Routing Integration Test

```python
def test_memory_routing_injects_headers(
    test_client,
    mock_chat_completions_response
):
    """Test that memory routing correctly injects x-sm-user-id header."""
    request_body = {
        "model": "claude-sonnet-4.5",
        "messages": [{"role": "user", "content": "Remember this"}]
    }

    with patch("httpx.AsyncClient", return_value=mock_chat_completions_response):
        response = test_client.post(
            "/v1/chat/completions",
            json=request_body,
            headers={
                "Authorization": "Bearer sk-test-1234",
                "User-Agent": "OpenAIClientImpl/Java 1.0"  # PyCharm
            }
        )

        assert response.status_code == 200

        # Verify memory routing injected user ID
        call_kwargs = mock_chat_completions_response.request.call_args[1]
        assert "headers" in call_kwargs

        # Check for x-sm-user-id in forwarded headers
        forwarded_headers = call_kwargs["headers"]
        assert "x-sm-user-id" in forwarded_headers
        assert forwarded_headers["x-sm-user-id"] == "pycharm-ai"
```

---

### Example 4: Multi-Endpoint Integration Test

```python
def test_full_workflow(test_client, mock_httpx_smart_router):
    """Test complete workflow: health → models → chat."""
    with patch("httpx.AsyncClient", return_value=mock_httpx_smart_router):
        # 1. Check health
        health = test_client.get("/health")
        assert health.status_code == 200
        assert health.json()["status"] == "healthy"

        # 2. List available models
        models = test_client.get(
            "/v1/models",
            headers={"Authorization": "Bearer sk-test-1234"}
        )
        assert models.status_code == 200
        model_list = models.json()
        assert "data" in model_list
        assert len(model_list["data"]) > 0

        # 3. Use model for chat
        chat = test_client.post(
            "/v1/chat/completions",
            json={
                "model": "claude-sonnet-4.5",
                "messages": [{"role": "user", "content": "Hi"}]
            },
            headers={"Authorization": "Bearer sk-test-1234"}
        )
        assert chat.status_code == 200
        assert "choices" in chat.json()
```

---

## Troubleshooting Guide

### Issue 1: "All connection attempts failed" (HTTP 500)

**Symptom:** Tests fail with connection errors despite mocking

**Root Cause:** Mock not properly configured or patch target incorrect

**Solution:**
```python
# ✅ CORRECT: Patch where httpx.AsyncClient is instantiated
with patch("httpx.AsyncClient", return_value=mock_httpx_client):
    # Test code

# ❌ WRONG: Patching wrong module
with patch("proxy.session_manager.httpx.AsyncClient", ...):  # Won't work
```

---

### Issue 2: Mock returns empty response

**Symptom:** `response.json()` fails or returns empty dict

**Root Cause:** Mock response content not configured

**Solution:**
```python
# Configure mock response with proper content
mock_response = Mock()
mock_response.status_code = 200
mock_response.headers = httpx.Headers({"content-type": "application/json"})
mock_response.content = json.dumps(response_data).encode()  # ← Must be bytes!

mock_httpx_client.request = AsyncMock(return_value=mock_response)
```

---

### Issue 3: TypeError: object Mock can't be used in 'await' expression

**Symptom:** Async mock not properly configured

**Root Cause:** Using Mock instead of AsyncMock for async methods

**Solution:**
```python
# ✅ CORRECT: AsyncMock for async methods
mock_httpx_client.request = AsyncMock(return_value=mock_response)

# ❌ WRONG: Regular Mock for async method
mock_httpx_client.request = Mock(return_value=mock_response)
```

---

### Issue 4: Fixture not applying to test

**Symptom:** Test still tries to make real HTTP requests

**Root Cause:** Fixture not used in test function signature

**Solution:**
```python
# ✅ CORRECT: Include fixture in function signature
def test_something(mock_chat_completions_response):
    with patch("httpx.AsyncClient", return_value=mock_chat_completions_response):
        pass

# ❌ WRONG: Fixture not in signature
def test_something():  # Missing fixture parameter
    pass
```

---

### Issue 5: Headers not preserved in mock

**Symptom:** Injected headers (like x-sm-user-id) not found

**Root Cause:** Need to inspect call_args to verify headers

**Solution:**
```python
# Verify headers were passed to mock
call_kwargs = mock_httpx_client.request.call_args[1]
assert "headers" in call_kwargs
injected_headers = call_kwargs["headers"]
assert "x-sm-user-id" in injected_headers
```

---

## Best Practices

### 1. Use Endpoint-Specific Fixtures

```python
# ✅ GOOD: Clear intent, proper response format
def test_chat(mock_chat_completions_response):
    pass

# ❌ BAD: Generic fixture, manual configuration
def test_chat(mock_httpx_client):
    # Manually configure response...
    pass
```

---

### 2. Always Patch at Usage Point

```python
# ✅ GOOD: Patch where AsyncClient is created
with patch("httpx.AsyncClient", return_value=mock):
    await proxy_request(...)

# ❌ BAD: Patching import location
with patch("proxy.litellm_proxy_with_memory.httpx.AsyncClient", ...):
```

---

### 3. Verify Mock Calls in Tests

```python
# ✅ GOOD: Verify mock was called correctly
mock_client.request.assert_called_once()
call_kwargs = mock_client.request.call_args[1]
assert call_kwargs["method"] == "POST"
assert call_kwargs["url"] == "http://localhost:4000/v1/chat/completions"
```

---

### 4. Use Response Templates from fixtures/

```python
# ✅ GOOD: Use existing templates
from tests.fixtures import mock_completion_response
response_data = mock_completion_response()

# ❌ BAD: Hardcode response structure
response_data = {"id": "123", ...}  # Might drift from spec
```

---

### 5. Test Both Success and Error Cases

```python
# ✅ GOOD: Test both paths
def test_success(mock_chat_completions_response):
    pass

def test_error(mock_error_response_fixture):
    pass

# ❌ BAD: Only test happy path
def test_chat(mock_chat_completions_response):
    # What about errors?
    pass
```

---

## Summary

### Key Takeaways

1. **Mock at the right level:** Patch `httpx.AsyncClient` where it's instantiated (in `proxy_request`)
2. **Use proper response formats:** All fixtures in `mock_responses.py` are OpenAI-compatible
3. **Compose fixtures:** Layer endpoint-specific fixtures on top of base `mock_httpx_client`
4. **Verify behavior:** Check that headers and user IDs are correctly injected
5. **Keep it simple:** Start with endpoint-specific fixtures before reaching for smart router

### Quick Reference

| Need to test... | Use this fixture |
|----------------|------------------|
| Chat completions (non-streaming) | `mock_chat_completions_response` |
| Chat completions (streaming) | `mock_streaming_response` |
| Models list | `mock_models_endpoint_response` |
| Health check | `mock_health_endpoint_response` |
| Error responses | `mock_error_response_fixture` |
| Multiple endpoints | `mock_httpx_smart_router` |
| Custom configuration | `configure_mock_httpx_response` |

### Next Steps

1. **Implement Phase 2:** Add endpoint-specific fixtures to `conftest.py`
2. **Fix failing tests:** Apply new fixtures to `test_binary_vs_sdk.py` and `test_litellm_proxy_refactored.py`
3. **Document patterns:** Update test documentation with examples
4. **Review coverage:** Ensure all endpoints have proper mock coverage

---

**Document Status:** Ready for Implementation
**Review Status:** Awaiting team review
**Implementation Priority:** HIGH (blocks failing tests)
