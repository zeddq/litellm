# Migration Guide: SDK to Binary Architecture

This document explains the changes made to transition from using LiteLLM SDK to using the external LiteLLM binary.

## Summary of Changes

The project has been redesigned to use the **LiteLLM binary** (`litellm --port ...`) instead of importing and using the LiteLLM SDK as a Python package.

## What Changed

### 1. **Dependencies (pyproject.toml)**

#### Before:
```toml
dependencies = [
    "fastapi>=0.119.1",
    "httpx>=0.28.1",
    "litellm[proxy]~=1.9",  # ❌ SDK dependency
    "pyyaml>=6.0.3",
    "uvicorn>=0.38.0"
]
```

#### After:
```toml
dependencies = [
    "fastapi>=0.119.1",
    "httpx>=0.28.1",
    "pyyaml>=6.0.3",
    "uvicorn>=0.38.0"
]

# Note: LiteLLM is required as a CLI tool, not as a Python package dependency.
# Install separately: pip install litellm
```

**Action Required:**
```bash
poetry install  # Updates dependencies
pip install litellm  # Install CLI tool separately
```

---

### 2. **Process Management (start_proxies.py)**

#### Before:
```python
def start_litellm_proxy(port: int, config_path: str):
    # Import LiteLLM SDK
    from litellm.proxy.proxy_server import app

    # Configure via environment variables
    os.environ["WORKER_CONFIG"] = json.dumps(worker_config)

    # Run via uvicorn with imported app
    uvicorn.run("litellm.proxy.proxy_server:app", ...)
```

#### After:
```python
def start_litellm_proxy(port: int, config_path: str):
    # Run litellm as external binary
    cmd = [
        "litellm",
        "--config", str(config_path),
        "--port", str(port),
        "--host", "0.0.0.0",
    ]

    process = subprocess.run(cmd, ...)
```

**Benefits:**
- ✅ No SDK imports needed
- ✅ Better process isolation
- ✅ Easier version management
- ✅ Simpler error handling

---

### 3. **Memory Proxy Configuration (litellm_proxy_with_memory.py)**

#### Before:
```python
litellm_base_url = "http://localhost:4000"  # Hardcoded
```

#### After:
```python
litellm_base_url = os.environ.get("LITELLM_BASE_URL", "http://localhost:4000")
```

**Benefits:**
- ✅ Dynamic configuration via environment variables
- ✅ Easier to change at runtime
- ✅ Better for containerized deployments

---

## Architecture Comparison

### Before (SDK-based):

```
┌──────────────────────────────────────┐
│ start_proxies.py                     │
│  ├─ Import litellm.proxy.app (SDK)  │
│  └─ Import memory proxy              │
│                                      │
│  Python Process 1:                   │
│    └─ LiteLLM SDK (in-process)      │
│                                      │
│  Python Process 2:                   │
│    └─ Memory Proxy                   │
└──────────────────────────────────────┘
```

### After (Binary-based):

```
┌──────────────────────────────────────┐
│ start_proxies.py                     │
│  ├─ subprocess: litellm binary       │
│  └─ Import memory proxy              │
│                                      │
│  External Process:                   │
│    └─ litellm --port 8765 ✨         │
│                                      │
│  Python Process:                     │
│    └─ Memory Proxy (HTTP client)    │
└──────────────────────────────────────┘
```

---

## Migration Steps

### Step 1: Update Dependencies

```bash
# Remove old dependencies (if needed)
poetry remove litellm

# Install fresh dependencies
poetry install

# Install LiteLLM as CLI tool
pip install litellm
```

### Step 2: Verify LiteLLM Binary

```bash
# Check if litellm binary is available
which litellm

# Test litellm binary
litellm --help

# Expected output: LiteLLM CLI help text
```

### Step 3: Update Configuration

No changes needed to `config.yaml` - it uses the same format.

### Step 4: Test the Setup

```bash
# Start both proxies
poetry run start-proxies

# Expected output:
# - LiteLLM starts on port 8765
# - Memory Proxy starts on port 8764
# - Both proxies show healthy status
```

### Step 5: Verify Health

```bash
# Check LiteLLM
curl http://localhost:8765/health

# Check Memory Proxy
curl http://localhost:8764/health

# Expected: {"status":"healthy", ...}
```

---

## Breaking Changes

### None for End Users

- **Client Code**: No changes required
- **API Endpoints**: Unchanged
- **Configuration**: Same format
- **Environment Variables**: Same (with additions)

### For Developers

If you were importing LiteLLM SDK directly:

#### Before:
```python
from litellm import completion

response = completion(
    model="gpt-4",
    messages=[{"role": "user", "content": "Hello"}]
)
```

#### After:
Use HTTP client instead:

```python
import httpx

response = httpx.post(
    "http://localhost:8765/v1/chat/completions",
    json={
        "model": "gpt-4",
        "messages": [{"role": "user", "content": "Hello"}]
    }
)
```

Or use OpenAI SDK pointing to the proxy:

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8764/v1",
    api_key="sk-1234"
)

response = client.chat.completions.create(
    model="gpt-4",
    messages=[{"role": "user", "content": "Hello"}]
)
```

---

## Rollback Plan

If you need to rollback to SDK-based approach:

```bash
# Restore old dependencies
git checkout HEAD~1 pyproject.toml
poetry install

# Restore old start script
git checkout HEAD~1 start_proxies.py

# Restart services
poetry run start-proxies
```

---

## Benefits of New Architecture

1. **🔒 Better Isolation**: Each component runs in separate process
2. **📦 Simpler Dependencies**: No SDK version conflicts
3. **🔄 Easy Updates**: Upgrade LiteLLM independently
4. **🚀 Production Ready**: Standard process management
5. **🐳 Container Friendly**: Easier to containerize
6. **📊 Better Monitoring**: Separate process metrics
7. **🛠️ Easier Debugging**: Clear separation of concerns

---

## Troubleshooting

### Issue: "litellm: command not found"

**Solution:**
```bash
pip install litellm
# Or
poetry run pip install litellm
```

### Issue: "Connection refused to localhost:8765"

**Solution:**
```bash
# Check if LiteLLM is running
ps aux | grep litellm

# Check logs
poetry run start-proxies  # Watch for startup errors
```

### Issue: "Import error: cannot import memory_router"

**Solution:**
```bash
# Ensure you're in the project directory
cd /path/to/litellm

# Run from correct location
poetry run start-proxies
```

---

## Support

For issues or questions:
1. Check logs: `poetry run start-proxies` (verbose mode)
2. Test health endpoints: `curl http://localhost:{port}/health`
3. Review configuration: `cat config.yaml`
4. Verify environment: `env | grep -E '(OPENAI|ANTHROPIC|LITELLM)'`

---

## Next Steps

1. ✅ Test the new architecture
2. ✅ Update any custom scripts using SDK imports
3. ✅ Update deployment configurations
4. ✅ Test in staging environment
5. ✅ Deploy to production

---

**Last Updated:** 2025-01-24