# LiteLLM Binary → SDK Migration Plan

**Status**: ✅ POC Validated - Ready to Implement
**Timeline**: 3-4 days
**Risk Level**: Medium (well-tested migration path)

---

## Migration Strategy

### Phase 1: Create SDK-Based Proxy (Day 1-2)
**Goal**: New `litellm_proxy_sdk.py` that works alongside existing binary proxy

**Benefits of Parallel Development**:
- ✅ Existing proxy keeps working
- ✅ Can test SDK version without breaking anything
- ✅ Easy rollback if issues arise
- ✅ Side-by-side comparison

### Phase 2: Testing & Validation (Day 3)
**Goal**: Comprehensive testing with all clients

### Phase 3: Cutover & Cleanup (Day 4)
**Goal**: Make SDK version primary, archive binary version

---

## Architecture Comparison

### Current: Binary Architecture
```
┌─────────────┐     HTTP      ┌──────────────┐     HTTP        ┌────────────┐
│   Clients   │ ───────────> │ Memory Proxy │ ─────────────> │  LiteLLM   │
│ (PyCharm,   │   port 8764   │  (FastAPI)   │  localhost:4000 │   Binary   │
│ Claude Code)│               │              │                 │ (External) │
└─────────────┘               └──────────────┘                 └────────────┘
                                     ↓                                ↓
                              Memory Routing                    Multi-Provider
                              User ID Detection                 Routing, Caching
                                                                       ↓
                                                              ┌────────────────┐
                                                              │   Supermemory  │
                                                              │   Anthropic    │
                                                              │   OpenAI       │
                                                              └────────────────┘
```

**Problems**:
- ❌ Can't control LiteLLM binary's HTTP client
- ❌ No cookie persistence for Cloudflare
- ❌ Extra process to manage
- ❌ Limited configuration control

### New: SDK Architecture
```
┌─────────────┐     HTTP      ┌──────────────────────────────────┐
│   Clients   │ ───────────> │   Memory Proxy (FastAPI)          │
│ (PyCharm,   │   port 8764   │   + LiteLLM SDK (in-process)     │
│ Claude Code)│               │   + Persistent httpx Sessions     │
└─────────────┘               └──────────────────────────────────┘
                                     ↓              ↓
                              Memory Routing   LiteLLM SDK
                              User ID          (acompletion)
                              Detection             ↓
                                            ┌────────────────┐
                                            │   Supermemory  │
                                            │   Anthropic    │
                                            │   OpenAI       │
                                            └────────────────┘
```

**Benefits**:
- ✅ Full control over HTTP clients
- ✅ Persistent sessions (Cloudflare-compatible)
- ✅ Single process (simpler deployment)
- ✅ Direct configuration access
- ✅ All LiteLLM features retained

---

## Implementation Details

### File Structure

```
litellm/
├── src/proxy/
│   ├── litellm_proxy_with_memory.py    # OLD: Binary-based (keep for now)
│   ├── litellm_proxy_sdk.py            # NEW: SDK-based (implement)
│   ├── memory_router.py                # SHARED: No changes needed
│   └── schema.py                       # SHARED: Request/response models
├── config/
│   └── config.yaml                     # SAME: No changes needed
├── poc_litellm_sdk_proxy.py           # POC: Keep for reference
└── SDK_MIGRATION_PLAN.md              # This document
```

### Core Components

#### 1. Session Manager
```python
class LiteLLMSessionManager:
    """
    Manages persistent httpx.AsyncClient for LiteLLM SDK.
    Ensures Cloudflare cookies persist across requests.
    """

    _client: Optional[httpx.AsyncClient] = None
    _lock = asyncio.Lock()

    @classmethod
    async def get_client(cls) -> httpx.AsyncClient:
        """Get or create persistent httpx client."""
        async with cls._lock:
            if cls._client is None:
                cls._client = httpx.AsyncClient(
                    timeout=httpx.Timeout(600.0),
                    follow_redirects=True,
                    limits=httpx.Limits(
                        max_connections=100,
                        max_keepalive_connections=20
                    )
                )
                logger.info("🍪 Created persistent httpx.AsyncClient")
            return cls._client

    @classmethod
    async def close(cls):
        """Close persistent client."""
        if cls._client:
            await cls._client.aclose()
            cls._client = None
            logger.info("🔒 Closed persistent httpx client")
```

#### 2. Configuration Parser
```python
class LiteLLMConfig:
    """Parses config.yaml and configures LiteLLM SDK."""

    def __init__(self, config_path: str):
        with open(config_path) as f:
            self.config = yaml.safe_load(f)

    def get_model_config(self, model_name: str) -> Optional[Dict]:
        """Get configuration for specific model."""
        for model in self.config.get("model_list", []):
            if model.get("model_name") == model_name:
                return model
        return None

    def get_litellm_params(self, model_name: str) -> Dict:
        """Extract litellm_params for a model."""
        model_config = self.get_model_config(model_name)
        if model_config:
            params = model_config.get("litellm_params", {})
            # Resolve environment variables
            return self._resolve_env_vars(params)
        return {}

    def _resolve_env_vars(self, params: Dict) -> Dict:
        """Resolve os.environ/VAR_NAME references."""
        resolved = {}
        for key, value in params.items():
            if isinstance(value, str) and value.startswith("os.environ/"):
                env_var = value.replace("os.environ/", "")
                resolved[key] = os.getenv(env_var)
            else:
                resolved[key] = value
        return resolved
```

#### 3. Main Proxy Handler
```python
@app.post("/v1/chat/completions")
async def chat_completions_handler(request: Request):
    """Handle chat completions using LiteLLM SDK."""

    # Parse request
    body_bytes = await request.body()
    body = json.loads(body_bytes) if body_bytes else {}

    model = body.get("model")
    messages = body.get("messages", [])

    # Detect user ID (existing memory routing logic)
    user_id = memory_router.detect_user_id(request.headers)

    # Get model configuration
    config = LiteLLMConfig("config/config.yaml")
    litellm_params = config.get_litellm_params(model)

    # Prepare extra headers
    extra_headers = litellm_params.get("extra_headers", {}).copy()
    extra_headers["x-sm-user-id"] = user_id

    # Get persistent session
    client = await LiteLLMSessionManager.get_client()
    litellm.aclient_session = client

    try:
        # Call LiteLLM SDK
        response = await litellm.acompletion(
            model=litellm_params.get("model"),
            messages=messages,
            api_base=litellm_params.get("api_base"),
            api_key=litellm_params.get("api_key"),
            extra_headers=extra_headers,
            stream=body.get("stream", False),
            **{k: v for k, v in body.items()
               if k not in ["model", "messages", "stream"]}
        )

        # Handle streaming vs non-streaming
        if body.get("stream"):
            return StreamingResponse(
                stream_generator(response),
                media_type="text/event-stream"
            )
        else:
            return JSONResponse(content=response.model_dump())

    except litellm.ServiceUnavailableError as e:
        logger.error(f"503 Service Unavailable: {e}")
        return JSONResponse(
            content={"error": {"message": str(e), "type": "service_unavailable"}},
            status_code=503
        )

    except litellm.RateLimitError as e:
        logger.error(f"429 Rate Limited: {e}")
        return JSONResponse(
            content={"error": {"message": str(e), "type": "rate_limit_error"}},
            status_code=429
        )

    except Exception as e:
        logger.error(f"Error: {type(e).__name__}: {e}")
        return JSONResponse(
            content={"error": {"message": str(e), "type": "api_error"}},
            status_code=500
        )
```

---

## Migration Steps

### Day 1: Core Implementation

**Morning (4 hours)**:
1. ✅ Create `src/proxy/litellm_proxy_sdk.py`
2. ✅ Implement `LiteLLMSessionManager`
3. ✅ Implement `LiteLLMConfig` parser
4. ✅ Basic FastAPI app structure

**Afternoon (4 hours)**:
1. ✅ Implement `/v1/chat/completions` endpoint
2. ✅ Integrate memory routing (reuse existing code)
3. ✅ Add basic error handling
4. ✅ Test with simple requests

### Day 2: Feature Completeness

**Morning (4 hours)**:
1. ✅ Implement streaming support
2. ✅ Add `/v1/models` endpoint
3. ✅ Add `/health` endpoint
4. ✅ Add `/memory-routing/info` endpoint (existing)

**Afternoon (4 hours)**:
1. ✅ Implement graceful startup/shutdown
2. ✅ Add comprehensive logging
3. ✅ Session lifecycle management
4. ✅ Configuration validation

### Day 3: Testing & Validation

**Morning (3 hours)**:
1. ✅ Unit tests for config parser
2. ✅ Unit tests for session manager
3. ✅ Integration tests for endpoints
4. ✅ Test error handling

**Afternoon (3 hours)**:
1. ✅ Test with PyCharm AI Assistant
2. ✅ Test with Claude Code
3. ✅ Test with curl/httpx
4. ✅ Load testing (multiple concurrent requests)
5. ✅ Cookie persistence validation

### Day 4: Cutover & Documentation

**Morning (2 hours)**:
1. ✅ Update `start_proxies.py` to use SDK version
2. ✅ Update deployment scripts
3. ✅ Create migration guide
4. ✅ Update CLAUDE.md

**Afternoon (2 hours)**:
1. ✅ Final smoke tests
2. ✅ Performance comparison (binary vs SDK)
3. ✅ Archive binary version
4. ✅ Update README

---

## Configuration Compatibility

**Good News**: `config.yaml` requires **ZERO changes**!

The SDK version will read the same config format:
```yaml
model_list:
  - model_name: claude-sonnet-4.5
    litellm_params:
      api_base: https://api.supermemory.ai/v3/api.anthropic.com
      model: anthropic/claude-sonnet-4-5-20250929
      api_key: os.environ/ANTHROPIC_API_KEY
      extra_headers:
        x-supermemory-api-key: os.environ/SUPERMEMORY_API_KEY
```

SDK version will parse this and pass to `litellm.acompletion()` directly.

---

## Testing Strategy

### 1. Unit Tests
```python
# Test: Config Parser
def test_config_parser():
    config = LiteLLMConfig("config/config.yaml")
    params = config.get_litellm_params("claude-sonnet-4.5")
    assert params["api_base"] == "https://api.supermemory.ai/..."
    assert params["model"] == "anthropic/claude-sonnet-4-5-20250929"
    assert "ANTHROPIC_API_KEY" not in params["api_key"]  # Resolved

# Test: Session Manager
async def test_session_manager():
    client1 = await LiteLLMSessionManager.get_client()
    client2 = await LiteLLMSessionManager.get_client()
    assert id(client1) == id(client2)  # Same instance
```

### 2. Integration Tests
```python
# Test: Chat Completions
async def test_chat_completions_sdk():
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://localhost:8764/v1/chat/completions",
            json={
                "model": "claude-sonnet-4.5",
                "messages": [{"role": "user", "content": "Test"}],
                "max_tokens": 10
            },
            headers={"Authorization": "Bearer sk-1234"}
        )
        assert response.status_code == 200
```

### 3. Client Tests
- **PyCharm**: Configure to `http://localhost:8764/v1`
- **Claude Code**: `export ANTHROPIC_BASE_URL="http://localhost:8764"`
- **curl**: Direct API calls

### 4. Load Tests
```python
# Test: Concurrent Requests
async def test_concurrent_requests():
    async with httpx.AsyncClient() as client:
        tasks = [
            make_completion_request(client, f"Test {i}")
            for i in range(50)
        ]
        results = await asyncio.gather(*tasks)
        assert all(r.status_code == 200 for r in results)
```

---

## Rollback Plan

If issues arise:

1. **Immediate Rollback**:
   ```bash
   # Stop SDK proxy
   pkill -f litellm_proxy_sdk.py

   # Start binary proxy
   poetry run python src/proxy/litellm_proxy_with_memory.py --port 8764
   ```

2. **Gradual Migration**:
   - Run both proxies on different ports
   - Test SDK version with subset of clients
   - Gradually migrate traffic

3. **Feature Flags**:
   ```yaml
   # config.yaml
   general_settings:
     use_sdk: true  # Toggle between binary and SDK
   ```

---

## Success Criteria

✅ **Functional**:
- All endpoints work (completions, models, health)
- Streaming works correctly
- Memory routing works as before
- Cookie persistence verified

✅ **Performance**:
- Response times comparable to binary
- No memory leaks
- Handles concurrent requests

✅ **Compatibility**:
- Works with PyCharm AI Assistant
- Works with Claude Code
- Works with direct API calls
- Config.yaml unchanged

✅ **Reliability**:
- Error handling comprehensive
- Graceful shutdown
- Session cleanup
- Logging informative

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| SDK bugs/limitations | Medium | High | POC validated approach; extensive testing |
| Performance degradation | Low | Medium | Benchmark before/after; optimize if needed |
| Breaking changes for clients | Low | High | Same API contract; backward compatible |
| Configuration issues | Low | Medium | Config parser tested; validation added |
| Cookie persistence doesn't work | Low | High | POC showed it works; fallback to direct calls |

---

## Next Steps

### 🚀 Ready to Implement?

**Option 1: Start Full Implementation Now**
- I can begin coding `litellm_proxy_sdk.py` immediately
- 3-4 days total timeline
- Detailed progress updates

**Option 2: Review Plan First**
- Any concerns or questions about the approach?
- Want to adjust timeline or priorities?
- Need clarification on any component?

**Option 3: Incremental Rollout**
- Start with minimal SDK proxy (non-streaming only)
- Test thoroughly
- Add features incrementally

**What would you prefer?** 🤔
