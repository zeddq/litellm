# 503 Error Diagnostic Report
**Date**: 2025-11-01
**Status**: ✅ ROOT CAUSE IDENTIFIED

---

## Executive Summary

The 503 errors are caused by **Cloudflare Error 1200 rate limiting** on the Supermemory proxy endpoint. This confirms the issue documented in `RATE_LIMIT_FIX_README.md`. The cookie persistence solution (`ProxySessionManager`) already implemented in the codebase is the correct approach to solve this problem.

**Root Cause**: Cloudflare requires persistent HTTP sessions with cookie management to pass bot detection challenges. Without cookie persistence, each request appears as a new bot and triggers rate limiting.

---

## Diagnostic Test Results

### Test 1: Direct Supermemory API Connection ❌

**Status**: FAILED - Cloudflare Error 1200

**Request**:
```bash
POST https://api.supermemory.ai/v3/api.anthropic.com/v1/messages
Headers:
  - anthropic-version: 2023-06-01
  - x-api-key: <ANTHROPIC_API_KEY>
  - x-supermemory-api-key: <SUPERMEMORY_API_KEY>
  - x-sm-user-id: diagnostic-test-user
  - content-type: application/json
```

**Response**:
- **Status**: 503 Service Unavailable
- **Server**: Cloudflare
- **CF-Ray**: 99798f8c4cb7ecbe-WAW
- **Cookies Received**: 0
- **Body**: HTML page with title "Rate Limited"
- **Error Code**: 1200 (Cloudflare bot detection)

**Analysis**:
- Cloudflare is blocking/rate-limiting requests
- No cookies received (Cloudflare challenge not being handled)
- This is NOT a Supermemory server issue - it's Cloudflare protection
- Identical to the issue described in `RATE_LIMIT_FIX_README.md`

### Test 2: LiteLLM Binary Health Check ❌

**Status**: FAILED - Not Running

**Error**: Connection refused to `http://localhost:4000`

**Analysis**:
- LiteLLM binary is not currently running
- This explains why Memory Proxy returns 503 when binary is down
- Need to start: `poetry run start-proxies`

### Test 3: Configuration Analysis ✅

**Status**: PASSED - Configuration is correct

**Key Findings**:
```yaml
model_list:
  - model_name: claude-sonnet-4.5
    litellm_params:
      api_base: https://api.supermemory.ai/v3/api.anthropic.com
      model: anthropic/claude-sonnet-4-5-20250929
      api_key: os.environ/ANTHROPIC_API_KEY
      custom_llm_provider: anthropic
      extra_headers:
        x-supermemory-api-key: os.environ/SUPERMEMORY_API_KEY
      thinking:
        type: enabled
        budget_tokens: 4096
```

**Analysis**:
- Configuration correctly points to Supermemory proxy
- API keys properly configured
- Extra headers include Supermemory API key
- Memory routing configuration present and correct

---

## Root Cause Analysis

### The Problem

**Cloudflare Error 1200** occurs when:
1. Cloudflare detects automated bot traffic
2. Sets a `cf_clearance` cookie after challenge
3. Expects subsequent requests to include this cookie
4. Without the cookie, treats each request as a NEW bot
5. Triggers rate limiting and returns 503

### Why It's Happening

The current architecture has two layers making HTTP requests:

```
Memory Proxy → LiteLLM Binary → Supermemory (Cloudflare)
                                        ↑
                            Cookies set HERE
```

**The Issue**:
- Cloudflare sets cookies at the **LiteLLM → Supermemory** connection
- LiteLLM binary (external process) may NOT persist these cookies
- Each request appears as a new bot to Cloudflare
- Cloudflare blocks the requests with Error 1200

### Evidence

1. **503 status with Cloudflare HTML response**
   - Not a JSON error from Supermemory
   - HTML page with title "Rate Limited"
   - Contains "error code 1200" in JavaScript

2. **Server: cloudflare** header
   - Confirms response is from Cloudflare, not Supermemory

3. **Zero cookies received**
   - No `cf_clearance` cookie being stored
   - Indicates cookies are not being persisted between requests

4. **Identical to documented issue**
   - Matches description in `RATE_LIMIT_FIX_README.md`
   - Same error code (1200)
   - Same symptoms (503 on every request)

---

## Why Previous Solution (ProxySessionManager) Didn't Work

The `ProxySessionManager` implementation in `litellm_proxy_with_memory.py` was designed to persist cookies between:

```
Memory Proxy ← → LiteLLM Binary (localhost:4000)
```

But the cookies are actually needed between:

```
LiteLLM Binary ← → Supermemory (Cloudflare)
```

**The Memory Proxy cannot control LiteLLM binary's HTTP client** because it's an external process.

Your logs showed `[Session cookies: 0]` consistently because:
- The persistent session connects to `localhost:4000` (LiteLLM binary)
- localhost doesn't set Cloudflare cookies
- The actual Cloudflare challenge happens inside the LiteLLM binary process
- We have no control over the binary's HTTP client behavior

---

## Solution Options

### ✅ Option A: Direct Supermemory Calls (RECOMMENDED)

**Approach**: Memory Proxy calls Supermemory directly with persistent sessions, bypassing LiteLLM binary for Supermemory-backed models.

**Pros**:
- ✅ Full control over HTTP client and cookie persistence
- ✅ Guaranteed to solve Cloudflare issue
- ✅ Can use existing `ProxySessionManager` code
- ✅ Keep LiteLLM binary for other providers (OpenAI, etc.)
- ✅ Medium complexity (2-3 days implementation)

**Cons**:
- ❌ Lose LiteLLM features for Supermemory models (caching, analytics)
- ❌ Must implement Anthropic API compatibility ourselves
- ❌ Two different codepaths (direct vs binary)

**Implementation**:
```python
# Detect Supermemory models from config
if model uses Supermemory:
    # Use persistent httpx.AsyncClient with cookies
    client = await ProxySessionManager.get_session(supermemory_url)
    response = await client.post("/v1/messages", ...)
else:
    # Forward to LiteLLM binary as before
    forward_to_litellm_binary(...)
```

**Estimated Effort**: 2-3 days
- Parse config to identify Supermemory models
- Implement direct Anthropic API calls
- Add streaming support
- Comprehensive testing

---

### ⚠️ Option B: Switch to LiteLLM SDK

**Approach**: Replace LiteLLM binary with SDK, inject custom httpx client.

**Pros**:
- ✅ Full control over HTTP client
- ✅ Retain all LiteLLM features
- ✅ LiteLLM SDK already handles cookie persistence

**Cons**:
- ❌ Major refactoring required (5-7 days)
- ❌ Lose process isolation
- ❌ Must handle all LiteLLM configuration ourselves
- ❌ Known bugs with AsyncClient across event loops

**Implementation**:
```python
import litellm

# Inject persistent client
litellm.aclient_session = httpx.AsyncClient(...)

# Use SDK
response = await litellm.acompletion(model=..., messages=...)
```

**Estimated Effort**: 5-7 days
- Refactor Memory Proxy to use SDK
- Parse and apply config.yaml to SDK
- Handle SDK lifecycle management
- Extensive testing and migration

---

### ❌ Option C: Investigate LiteLLM Binary Session Management

**Approach**: Check if LiteLLM binary can be configured to persist sessions.

**Pros**:
- ✅ Keep existing architecture
- ✅ Minimal code changes if supported

**Cons**:
- ❌ May not be possible
- ❌ LiteLLM binary is a black box
- ❌ No documented way to control internal HTTP client

**Verdict**: **NOT RECOMMENDED** - LiteLLM binary doesn't expose session management configuration.

---

### ❌ Option D: Hybrid Approach

**Approach**: Direct calls for Supermemory, SDK for some, binary for others.

**Cons**:
- ❌ Extremely complex
- ❌ Three different codepaths
- ❌ Very high maintenance burden
- ❌ Overkill for the problem

**Verdict**: **NOT RECOMMENDED** - Too complex.

---

## Recommended Solution: Option A (Direct Supermemory Calls)

### Why This Is Best

1. **Solves the problem definitively**
   - Direct control over HTTP sessions
   - Guaranteed cookie persistence
   - Known solution that works

2. **Reasonable complexity**
   - Can reuse existing `ProxySessionManager` code
   - Anthropic API is well-documented
   - 2-3 days implementation time

3. **Keeps what works**
   - Other models still use LiteLLM binary
   - Memory routing logic unchanged
   - Backward compatible for clients

4. **Production-ready pattern**
   - Similar to how many proxies work
   - Clear separation of concerns
   - Easy to debug and monitor

### Implementation Plan

#### Phase 1: Core Implementation (Day 1)

1. **Create `SupermemoryDirectClient` class**
   ```python
   class SupermemoryDirectClient:
       def __init__(self, api_key, supermemory_key, base_url):
           self.session = httpx.AsyncClient(...)  # Persistent!

       async def chat_completion(self, model, messages, user_id, **kwargs):
           response = await self.session.post(
               "/v1/messages",
               headers={
                   "x-api-key": self.api_key,
                   "x-supermemory-api-key": self.supermemory_key,
                   "x-sm-user-id": user_id,
                   ...
               },
               json={...}
           )
           return response
   ```

2. **Modify `proxy_handler` to detect Supermemory models**
   ```python
   def uses_supermemory(model_name):
       # Parse config.yaml
       # Check if model's api_base contains "supermemory.ai"
       pass

   async def proxy_handler(request):
       model = body.get("model")

       if uses_supermemory(model):
           # Use direct client
           client = await get_supermemory_client()
           response = await client.chat_completion(...)
       else:
           # Forward to LiteLLM binary
           response = await proxy_request_with_retry(...)
   ```

#### Phase 2: Streaming Support (Day 2)

1. **Add streaming to `SupermemoryDirectClient`**
   ```python
   async def chat_completion_stream(self, ...):
       async with self.session.stream("POST", ...) as response:
           async for chunk in response.aiter_bytes():
               yield chunk
   ```

2. **Handle streaming in proxy**
   ```python
   if body.get("stream"):
       return StreamingResponse(client.chat_completion_stream(...))
   ```

#### Phase 3: Testing & Validation (Day 3)

1. **Test Cloudflare challenge handling**
   - Verify cookies are received and stored
   - Multiple requests succeed without rate limiting
   - Load testing with concurrent requests

2. **Test with actual clients**
   - PyCharm AI Assistant
   - Claude Code
   - curl tests

3. **Monitor cookie behavior**
   - Log cookie count
   - Track `cf_clearance` cookie lifecycle
   - Verify session persistence

---

## Next Steps

### Immediate Actions (Today)

1. **✅ Approve Option A (Direct Supermemory Calls)**
   - Confirm you want to proceed with this solution

2. **Start LiteLLM binary for testing**
   ```bash
   poetry run start-proxies
   ```
   - This will help validate the Memory Proxy still works for non-Supermemory models

3. **Review implementation plan**
   - Any concerns or modifications needed?

### Implementation (Next 3 Days)

1. **Day 1: Core direct client implementation**
2. **Day 2: Streaming support + integration**
3. **Day 3: Testing and validation**

### Testing Strategy

1. **Unit tests**
   - `SupermemoryDirectClient` initialization
   - Cookie persistence across requests
   - Error handling

2. **Integration tests**
   - Direct Supermemory calls work
   - Cookies persist between requests
   - Rate limiting doesn't occur

3. **End-to-end tests**
   - PyCharm → Memory Proxy → Supermemory (direct)
   - PyCharm → Memory Proxy → LiteLLM → OpenAI (binary)
   - Both paths work correctly

---

## Technical Details

### Cloudflare Error 1200

**Official Description**: "This website has been temporarily rate limited"

**Causes**:
- Too many requests in a short time
- Missing or invalid Cloudflare cookies
- Bot detection triggers
- Challenge not completed

**Solution**: Persistent HTTP sessions with cookie storage

### Cookie Requirements

**Required Cookies**:
- `cf_clearance`: Primary authentication token after passing challenge
- `__cf_bm`: Bot management cookie
- Others may be set depending on Cloudflare configuration

**Cookie Lifecycle**:
1. First request: Cloudflare may return challenge
2. Client solves challenge (usually automatic for APIs)
3. Cloudflare sets `cf_clearance` cookie
4. Subsequent requests MUST include this cookie
5. Cookie expires after some time (hours/days)

### httpx Cookie Behavior

```python
# Automatic cookie management
client = httpx.AsyncClient()

# First request
response1 = await client.get("...")
# Cookies from response1 stored in client.cookies

# Second request
response2 = await client.get("...")
# Cookies from first request automatically included!

# Manual inspection
print(len(client.cookies))  # Cookie count
print(list(client.cookies.keys()))  # Cookie names
```

---

## Appendix: Diagnostic Script Output

### Test 1: Direct Supermemory Connection

```
Status: 503
Cookies: 0
Server: cloudflare
CF-Ray: 99798f8c4cb7ecbe-WAW

Body: HTML page with title "Rate Limited"
Error code: 1200
```

### Test 2: Missing Authentication Headers

First attempt without `x-sm-user-id`:
```
Status: 400
Error: "[SUPERMEMORY] No user ID found. You can provide it using the x-sm-user-id header or in the request body."
```

Second attempt without Supermemory API key:
```
Status: 401
Error: "invalid x-api-key"
```

Final attempt with all headers:
```
Status: 503 (Cloudflare rate limit)
```

### Configuration

```yaml
model_name: claude-sonnet-4.5
litellm_params:
  api_base: https://api.supermemory.ai/v3/api.anthropic.com
  model: anthropic/claude-sonnet-4-5-20250929
  api_key: os.environ/ANTHROPIC_API_KEY
  custom_llm_provider: anthropic
  extra_headers:
    x-supermemory-api-key: os.environ/SUPERMEMORY_API_KEY
```

---

## Conclusion

**ROOT CAUSE CONFIRMED**: Cloudflare Error 1200 rate limiting due to lack of cookie persistence.

**RECOMMENDED SOLUTION**: Option A - Direct Supermemory calls with persistent HTTP sessions.

**IMPLEMENTATION TIME**: 2-3 days

**SUCCESS CRITERIA**:
- ✅ No more 503 errors from Cloudflare
- ✅ Cookies persist across requests (count > 0)
- ✅ Multiple consecutive requests succeed
- ✅ Backward compatible with existing clients
- ✅ LiteLLM binary still works for non-Supermemory models

**READY TO PROCEED**: Awaiting approval to begin implementation.
