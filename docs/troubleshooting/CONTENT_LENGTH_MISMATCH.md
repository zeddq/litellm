# Content-Length Mismatch Investigation

## Issue
Requests to the proxy were failing or behaving unexpectedly when the `Content-Length` header did not match the actual body size. This often occurs when:
1. A client manually constructs headers and miscalculates length.
2. An intermediary (like a streaming interceptor) modifies the body without updating the header.
3. Unicode characters are counted as characters instead of bytes.

## Standard Behavior
Standard HTTP servers (like Uvicorn/Starlette) and model endpoints (like OpenAI) have varying behaviors:

1.  **Strict Mode (Default for many servers):**
    *   If `Content-Length` > Actual Body: Server waits for more data until timeout.
    *   If `Content-Length` < Actual Body: Server truncates the body, leading to invalid JSON.

2.  **Permissive/Chunked:**
    *   If `Transfer-Encoding: chunked` is present, `Content-Length` is ignored.
    *   Some endpoints might read until EOF and ignore the header if it doesn't match, but this is non-standard.

## Solution Implemented
We have enforced strict validation to fail fast and provide clear error messages.

### 1. Interceptor (`intercepting_contexter.py`)
Middleware added to:
- Read `Content-Length` header.
- Read full body.
- Compare lengths.
- Return `400 Bad Request` if they differ.
- Log the mismatch with details.

### 2. Proxy (`litellm_proxy_sdk.py`)
- **Middleware:** Added identical `Content-Length` validation middleware.
- **Pydantic Validation:** Updated `chat_completions` to use `ChatCompletionRequest` Pydantic model.
    - Validates presence of `model` and `messages`.
    - Allows extra fields (pass-through).
    - Returns `422 Unprocessable Entity` for malformed JSON or missing fields.

## Recommendation for Clients
Clients must ensure:
- `Content-Length` is calculated based on **byte length** (UTF-8 encoded), not string length.
- If streaming or modifying body, update the header or use `Transfer-Encoding: chunked`.
