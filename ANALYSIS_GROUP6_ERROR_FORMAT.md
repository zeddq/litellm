# Group 6: Error Response Format Analysis

## Problem Summary

Tests expect OpenAI-compatible error format but SDK proxy returns FastAPI default format.

**Failing Tests**: 6 tests in `tests/test_sdk_integration.py`
- `test_list_models_requires_auth` - expects 401, gets 200
- `test_list_models_invalid_key` - expects 401, gets 200
- `test_chat_completion_requires_auth` - expects 401, gets 500
- `test_chat_completion_invalid_key` - expects 401, gets 500
- `test_chat_completion_missing_model` - missing 'error' key
- `test_chat_completion_invalid_model` - missing 'error' key

## Root Causes

### Issue 1: Authentication Bug in `verify_api_key()`

**File**: `src/proxy/litellm_proxy_sdk.py` (lines 349-380)

**Bug**: Function overwrites the authorization header with master key BEFORE checking it:

```python
async def verify_api_key(request: Request) -> None:
    config = get_config()

    # BUG: This overwrites the Authorization header with master key
    mh = request.headers.mutablecopy()
    mh["authorization"] = f"Bearer {config.get_master_key()}"
    auth_header = mh.get("authorization", "")  # Always returns master key!

    # This check always passes because we just set it to master_key
    if provided_key != config.get_master_key():
        raise HTTPException(...)
```

**Impact**: All requests pass authentication, even those with no auth header or invalid keys.

**Fix**: Remove the header overwrite, read directly from request:

```python
async def verify_api_key(request: Request) -> None:
    config = get_config()
    auth_header = request.headers.get("authorization", "")

    if not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header",
        )

    provided_key = auth_header[7:]  # Remove "Bearer " prefix

    if provided_key != config.get_master_key():
        logger.warning(f"Invalid API key attempt from {request.client.host}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )
```

### Issue 2: Error Format Inconsistency

**Expected Format** (OpenAI-compatible):
```json
{
  "error": {
    "message": "Invalid API key",
    "type": "invalid_request_error",
    "code": "invalid_api_key"
  }
}
```

**Actual Format** (FastAPI default):
```json
{
  "detail": "Invalid API key"
}
```

**Problem**: FastAPI's `HTTPException` uses `{"detail": "..."}` format, not OpenAI format.

**Solution**: Two approaches:

#### Approach A: Custom HTTPException Handler (Recommended)

Add a global exception handler to convert FastAPI HTTPException to OpenAI format:

```python
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Convert HTTPException to OpenAI error format."""

    # Map status codes to error types
    error_type_map = {
        400: "invalid_request_error",
        401: "authentication_error",
        403: "permission_error",
        404: "not_found_error",
        429: "rate_limit_error",
        500: "api_error",
        503: "service_unavailable_error",
    }

    error_type = error_type_map.get(exc.status_code, "api_error")

    # Build OpenAI-compatible error response
    content = {
        "error": {
            "message": exc.detail,
            "type": error_type,
        }
    }

    # Add code for specific cases
    if exc.status_code == 401:
        content["error"]["code"] = "invalid_api_key"
    elif exc.status_code == 404:
        content["error"]["code"] = "model_not_found"
    elif exc.status_code == 400 and "model" in str(exc.detail).lower():
        content["error"]["code"] = "invalid_parameter"

    return JSONResponse(
        status_code=exc.status_code,
        content=content,
    )
```

#### Approach B: Replace All HTTPException Raises

Change every `raise HTTPException(...)` to use `ErrorResponse.build()` from error_handlers.py.

**Verdict**: **Approach A is preferred** because:
- Single point of change (DRY principle)
- Handles all HTTPException raises automatically
- Maintains compatibility with existing error handling
- Easier to maintain and test

## Implementation Plan

### Step 1: Fix Authentication Bug

**File**: `src/proxy/litellm_proxy_sdk.py`

Replace lines 349-380 with corrected `verify_api_key()` function.

### Step 2: Add HTTPException Handler

**File**: `src/proxy/litellm_proxy_sdk.py`

Add exception handler after app initialization:

```python
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    # Implementation above
```

### Step 3: Verify All 6 Tests Pass

Run tests to confirm fixes:

```bash
poetry run pytest tests/test_sdk_integration.py::TestModelsListEndpoint::test_list_models_requires_auth -xvs
poetry run pytest tests/test_sdk_integration.py::TestModelsListEndpoint::test_list_models_invalid_key -xvs
poetry run pytest tests/test_sdk_integration.py::TestChatCompletionsNonStreaming::test_chat_completion_requires_auth -xvs
poetry run pytest tests/test_sdk_integration.py::TestChatCompletionsNonStreaming::test_chat_completion_invalid_key -xvs
poetry run pytest tests/test_sdk_integration.py::TestChatCompletionsNonStreaming::test_chat_completion_missing_model -xvs
poetry run pytest tests/test_sdk_integration.py::TestChatCompletionsNonStreaming::test_chat_completion_invalid_model -xvs
```

## Testing Strategy

### Auth Tests (Should Return 401)

1. **No Authorization header** → 401 with "Missing or invalid Authorization header"
2. **Invalid API key** → 401 with "Invalid API key"
3. **Valid API key** → 200 OK

### Error Format Tests (Should Have OpenAI Format)

1. **Missing model** → 400 with `{"error": {"message": "...", "type": "invalid_request_error"}}`
2. **Invalid model** → 404 with `{"error": {"message": "...", "type": "not_found_error"}}`
3. **Missing messages** → 400 with OpenAI format

## Expected Outcome

- All 6 tests pass
- Auth checks work correctly (401 for invalid/missing keys)
- All error responses use OpenAI-compatible format
- No regressions in other tests

## Time Estimate

- Analysis: 30 minutes ✅ (completed)
- Implementation: 45 minutes (in progress)
- Testing: 30 minutes
- Documentation: 15 minutes

**Total**: ~2 hours
