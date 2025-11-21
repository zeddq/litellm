# Common Issues & Troubleshooting

Solutions to common problems encountered when running LiteLLM Memory Proxy.

---

## Table of Contents

1. [503 Service Unavailable Errors](#1-503-service-unavailable-errors)
2. [Rate Limiting & Cloudflare Issues](#2-rate-limiting--cloudflare-issues)
3. [Redis Connection Issues](#3-redis-connection-issues)
4. [Cookie Persistence Problems](#4-cookie-persistence-problems)
5. [LiteLLM SDK Issues](#5-litellm-sdk-issues)
6. [Configuration Issues](#6-configuration-issues)
7. [Memory Routing Issues](#7-memory-routing-issues)
8. [Performance Issues](#8-performance-issues)
9. [Interceptor Issues](#9-interceptor-issues)
10. [Context Retrieval Issues](#10-context-retrieval-issues)

---

## 1. 503 Service Unavailable Errors

### Symptoms

- HTTP 503 responses from API requests
- HTML error pages instead of JSON responses
- "Service Unavailable" errors
- Cloudflare error pages

### Root Causes & Solutions

#### Cause A: Cloudflare Error 1200 Rate Limiting

**Symptoms**:
- 503 status with Cloudflare HTML response
- Error page contains "error code 1200"
- `Server: cloudflare` header in response
- Happens consistently with Supermemory API

**Root Cause**:
Cloudflare requires persistent HTTP sessions with cookie management. Without cookie persistence, each request appears as a new bot and triggers rate limiting.

**Solution**: ✅ Implemented - ProxySessionManager

The proxy uses `ProxySessionManager` to maintain persistent `httpx.AsyncClient` sessions that preserve Cloudflare cookies across requests.

**Verification**:
```bash
# Check proxy logs for cookie persistence
grep "Session cookies" proxy.log

# Should see: [Session cookies: 1] or higher
```

**If still seeing issues**:
1. Verify ProxySessionManager is being used
2. Check that sessions aren't being recreated per request
3. Confirm Cloudflare cookies (`cf_clearance`) are being stored

#### Cause B: LiteLLM SDK Initialization Failed

**Symptoms**:
- Connection refused errors
- 503 from Memory Proxy
- Error: "LiteLLM not ready"

**Root Cause**:
The internal LiteLLM SDK failed to initialize properly, likely due to configuration errors or missing dependencies.

**Solution**:
```bash
# Check logs for initialization errors
poetry run python deploy/run_unified_proxy.py --mode sdk --debug
```

**Verification**:
```bash
# Check Proxy is running
curl http://localhost:8764/health

# Should return: {"status": "healthy"}
```

#### Cause C: Upstream Provider Down

**Symptoms**:
- 503 errors from specific providers
- Works with some models, fails with others

**Root Cause**:
The upstream API provider (OpenAI, Anthropic, etc.) is experiencing outages.

**Solution**:
1. Check provider status pages:
   - OpenAI: https://status.openai.com
   - Anthropic: https://status.anthropic.com
2. Try alternative models/providers
3. Implement retry logic with exponential backoff

---

## 2. Rate Limiting & Cloudflare Issues

### Understanding Cloudflare Error 1200

**What is it?**
Cloudflare Error 1200 is a bot detection mechanism that blocks requests that don't properly handle Cloudflare challenges.

**How it works**:
1. Cloudflare sends a challenge on first request
2. Sets cookies (especially `cf_clearance`) after challenge passes
3. Subsequent requests must include these cookies
4. Without cookies, each request appears as a new bot → rate limiting

### The Solution: Persistent HTTP Sessions

**Implementation**: `ProxySessionManager`

```python
class ProxySessionManager:
    """
    Manages persistent HTTP sessions for proxy requests.
    
    Key features:
    - One persistent httpx.AsyncClient per upstream endpoint
    - Automatic cookie storage and reuse
    - Thread-safe with asyncio.Lock
    """
```

**Why it works**:
- Single client per endpoint preserves cookies
- Cloudflare `cf_clearance` cookie automatically included in all requests
- No repeated bot challenges

### Troubleshooting Rate Limiting

**Check if cookies are being persisted**:
```bash
# Enable debug logging
export LOG_LEVEL=DEBUG

# Start proxy and check logs
grep -i cookie proxy.log
```

---

## 3. Redis Connection Issues

### Symptoms

- "Redis connection failed" errors
- "NOAUTH Authentication required" errors
- "Could not connect to Redis at localhost:6379"

### Diagnosis

#### Check Redis Status

```bash
# Is Redis running?
docker ps | grep redis

# Or if Redis installed locally
redis-cli ping
# Should return: PONG
```

### Common Issues & Solutions

#### Issue: NOAUTH Authentication Required

**Cause**: Redis requires authentication but password not provided.

**Solution**:
```bash
# Set Redis password in environment
export REDIS_PASSWORD=your-password
```

#### Issue: Connection Refused

**Cause**: Redis is not running or listening on wrong port.

**Solution**:
```bash
# Start Redis with Docker
docker-compose up -d redis

# Check Redis is listening
lsof -i :6379
```

---

## 4. Cookie Persistence Problems

### Symptoms

- Repeated Cloudflare challenges
- 503 errors despite implementing ProxySessionManager
- `[Session cookies: 0]` in logs

### Diagnosis

**Check session cookie count**:
```bash
# Should see increasing cookie counts
grep "Session cookies" proxy.log
```

### Common Issues

#### Issue: New Client Created Per Request

**Cause**: ProxySessionManager not being used correctly.

**Solution**:
Ensure you are using the SDK mode which enforces `ProxySessionManager` usage.

#### Issue: Cookies for Wrong Domain

**Cause**: Using wrong base_url for session manager.

**Solution**:
Use actual Cloudflare-protected domain (e.g. `https://api.supermemory.ai`) instead of localhost.

---

## 5. LiteLLM SDK Issues

### Symptoms

- "LiteLLM not found" errors
- "Command not found: litellm"
- Initialization failures

### Solutions

#### Issue: Package Not Installed

**Diagnosis**:
```bash
pip show litellm
```

**Solution**:
```bash
# Install with poetry
poetry install

# Or pip
pip install 'litellm[proxy]'
```

#### Issue: Port Already in Use

**Symptoms**:
- "Address already in use" error
- Proxy fails to start

**Diagnosis**:
```bash
# Check what's using port 8764
lsof -i :8764
```

**Solution**:
```bash
# Kill process using port
lsof -i :8764 | grep LISTEN | awk '{print $2}' | xargs kill

# Or use different port
poetry run python deploy/run_unified_proxy.py --mode sdk --sdk-port 8766
```

#### Issue: Silent Crashes

**Diagnosis**:
```bash
# Run in debug mode
poetry run python deploy/run_unified_proxy.py --mode sdk --debug
```

**Common causes**:
1. Invalid config.yaml syntax
2. Missing API keys
3. Invalid model configuration

**Solution**:
```bash
# Validate config
poetry run python src/proxy/schema.py config/config.yaml
```

---

## 6. Configuration Issues

### Symptoms

- "Config file not found" errors
- "Invalid configuration" errors
- Models not loading
- Environment variables not resolving

### Common Issues

#### Issue: Config File Not Found

**Solution**:
```bash
# Check file exists
ls -l config.yaml

# Use absolute path
export LITELLM_CONFIG=/absolute/path/to/config.yaml
```

#### Issue: Environment Variables Not Resolving

**Symptoms**:
- Literal string `os.environ/OPENAI_API_KEY` in logs
- Authentication failures

**Diagnosis**:
```bash
# Check env var is set
echo $OPENAI_API_KEY
```

**Solution**:
```bash
# Set environment variable
export OPENAI_API_KEY=sk-...

# Or use .env file
echo "OPENAI_API_KEY=sk-..." >> .env
source .env
```

#### Issue: Invalid YAML Syntax

**Symptoms**:
- "YAML parsing error"
- "Invalid configuration structure"

**Diagnosis**:
```bash
# Validate YAML syntax
python -c "import yaml; yaml.safe_load(open('config.yaml'))"
```

**Common YAML mistakes**:
```yaml
# ❌ Wrong - inconsistent indentation
model_list:
- model_name: gpt-4
   litellm_params:
     model: openai/gpt-4

# ✅ Correct - consistent 2-space indentation
model_list:
  - model_name: gpt-4
    litellm_params:
      model: openai/gpt-4
```

---

## 7. Memory Routing Issues

### Symptoms

- Wrong user ID assigned
- Memory not isolated between clients
- Pattern not matching

### Diagnosis

**Test routing**:
```bash
# Check what user ID is assigned
curl http://localhost:8764/memory-routing/info \
  -H "User-Agent: OpenAIClientImpl/Java"
```

**Expected response**:
```json
{
  "user_id": "pycharm-ai",
  "matched_pattern": {
    "header": "user-agent",
    "pattern": "OpenAIClientImpl/Java",
    "user_id": "pycharm-ai"
  },
  "custom_header_present": false,
  "is_default": false
}
```

### Common Issues

#### Issue: Pattern Not Matching

**Cause**: Incorrect regex pattern.

**Solution**:
```python
# Test pattern in Python
import re
pattern = re.compile("OpenAIClientImpl/Java", re.IGNORECASE)
test_string = "OpenAIClientImpl/Java unknown"
print(pattern.search(test_string))  # Should match
```

#### Issue: Default User ID Always Used

**Cause**: No patterns matching.

**Diagnosis**:
```bash
curl http://localhost:8764/memory-routing/info \
  -H "User-Agent: YourApp"
# Check if result is default
```

**Solution**:
- Check User-Agent string is correct
- Verify pattern is in config.yaml
- Test pattern with regex tester

---

## 8. Performance Issues

### Symptoms

- Slow response times
- High memory usage
- CPU spikes

### Diagnosis

**Check resource usage**:
```bash
# Memory
ps aux | grep litellm

# Network
netstat -an | grep :8764
```

### Common Issues

#### Issue: Too Many Open Connections

**Symptoms**:
- "Too many open files" errors
- Connection refused errors

**Solution**:
```bash
# Increase file descriptor limit
ulimit -n 4096
```

#### Issue: Memory Leaks

**Symptoms**:
- Memory usage grows over time

**Solution**:
- Ensure HTTP clients are properly closed (handled by SessionManager)
- Implement cleanup in FastAPI lifespan

---

## 9. Interceptor Issues

### Symptoms

- Interceptor crashes when making requests
- Connection reset by peer
- "Address already in use" errors
- Wrong port assigned to project

### Common Interceptor Issues

#### Issue: Port Already in Use

**Symptoms**:
- "Address already in use" error when starting interceptor
- Interceptor fails to bind to port

**Diagnosis**:
```bash
# Check what's using the port
lsof -i :8888

# Check port registry
python -m src.interceptor.cli list
```

**Solution**:
```bash
# Option 1: Kill the process using the port
lsof -i :8888 | grep LISTEN | awk '{print $2}' | xargs kill

# Option 2: Get a new port assignment
python -m src.interceptor.cli remove
python -m src.interceptor.cli show  # Will assign new port
```

---

## 10. Context Retrieval Issues

### Symptoms

- No context being retrieved from Supermemory
- Context retrieval errors in logs
- Empty context being injected

### Common Issues

#### Issue: Context Retrieval Disabled

**Symptoms**:
- No context in requests
- No Supermemory API calls in logs

**Diagnosis**:
```bash
# Check configuration
grep -A 10 "context_retrieval:" config/config.yaml
```

**Solution**:
```yaml
context_retrieval:
  enabled: true  # Must be true
  api_key: os.environ/SUPERMEMORY_API_KEY
```

#### Issue: API Key Missing or Invalid

**Symptoms**:
- "api_key is required when context_retrieval.enabled=true" error
- 401 Unauthorized from Supermemory API

**Solution**:
```bash
# Set API key
export SUPERMEMORY_API_KEY="sm_..."
```

---

## Getting Help

If you're still experiencing issues after trying these solutions:

1. **Enable Debug Logging**:
   ```bash
   poetry run python deploy/run_unified_proxy.py --mode sdk --debug
   ```

2. **Collect Diagnostic Info**:
   ```bash
   # System info
   python --version
   poetry --version
   
   # Configuration
   cat config.yaml
   
   # Logs
   # Check terminal output or configured log file
   ```

3. **Check Related Documentation**:
   - [Architecture Overview](../architecture/OVERVIEW.md)
   - [Configuration Guide](../guides/CONFIGURATION.md)

---

**Last Updated**: 2025-11-21
**Status**: Updated for SDK Architecture