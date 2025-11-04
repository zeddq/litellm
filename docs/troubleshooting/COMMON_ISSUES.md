# Common Issues & Troubleshooting

Solutions to common problems encountered when running LiteLLM Memory Proxy.

---

## Table of Contents

1. [503 Service Unavailable Errors](#1-503-service-unavailable-errors)
2. [Rate Limiting & Cloudflare Issues](#2-rate-limiting--cloudflare-issues)
3. [Redis Connection Issues](#3-redis-connection-issues)
4. [Cookie Persistence Problems](#4-cookie-persistence-problems)
5. [LiteLLM Binary Issues](#5-litellm-binary-issues)
6. [Configuration Issues](#6-configuration-issues)
7. [Memory Routing Issues](#7-memory-routing-issues)
8. [Performance Issues](#8-performance-issues)

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
tail -f proxy.log | grep "Session cookies"

# Should see: [Session cookies: 1] or higher
```

**If still seeing issues**:
1. Verify ProxySessionManager is being used
2. Check that sessions aren't being recreated per request
3. Confirm Cloudflare cookies (`cf_clearance`) are being stored

#### Cause B: LiteLLM Binary Not Running

**Symptoms**:
- Connection refused errors
- 503 from Memory Proxy
- Error: "Connection error: http://localhost:4000"

**Root Cause**:
The LiteLLM binary process is not running (only applicable in binary mode).

**Solution**:
```bash
# Start both proxies
poetry run start-proxies

# Or manually
litellm --config config.yaml --port 4000
```

**Verification**:
```bash
# Check LiteLLM binary is running
curl http://localhost:4000/health

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

### Why Simple Retry Doesn't Work

```
Attempt 1: New httpx client → 429 + cf_clearance cookie → Client closed ❌
Attempt 2: New httpx client → 429 + NEW cf_clearance → Client closed ❌
Attempt 3: New httpx client → 429 + NEW cf_clearance → FAIL ❌
```

Each retry creates a fresh client with no cookies, so Cloudflare treats every attempt as a new bot!

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
    
    _clients: Dict[str, httpx.AsyncClient] = {}
    
    @classmethod
    async def get_client(cls, base_url: str) -> httpx.AsyncClient:
        """Get or create persistent client for endpoint."""
        if base_url not in cls._clients:
            cls._clients[base_url] = httpx.AsyncClient(
                base_url=base_url,
                timeout=httpx.Timeout(600.0),
                follow_redirects=True
            )
        return cls._clients[base_url]
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
tail -f proxy.log | grep -i cookie
```

**Test Cloudflare directly**:
```bash
# This will likely fail with 503
curl -v https://api.supermemory.ai/v3/api.anthropic.com/v1/messages

# Check for Cloudflare headers
# Look for: Server: cloudflare
# Look for: Set-Cookie: cf_clearance=...
```

**Verify ProxySessionManager is active**:
```python
# In code, check session manager state
from proxy.session_manager import ProxySessionManager

clients = ProxySessionManager._clients
print(f"Active sessions: {len(clients)}")
for url, client in clients.items():
    print(f"  {url}: {len(client.cookies)} cookies")
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

#### Check Redis Connectivity

```bash
# Test connection
redis-cli -h localhost -p 6379 ping

# With password
redis-cli -h localhost -p 6379 -a your-password ping

# Check Redis info
redis-cli -h localhost -p 6379 INFO server
```

### Common Issues & Solutions

#### Issue: NOAUTH Authentication Required

**Cause**: Redis requires authentication but password not provided.

**Solution**:
```bash
# Set Redis password in environment
export REDIS_PASSWORD=your-password

# Or in config.yaml
litellm_settings:
  cache_params:
    type: redis
    password: os.environ/REDIS_PASSWORD
```

**Test**:
```bash
redis-cli -h localhost -p 6379 -a your-password ping
```

#### Issue: Connection Refused

**Cause**: Redis is not running or listening on wrong port.

**Solution**:
```bash
# Start Redis with Docker
docker-compose up -d redis

# Or start Redis locally
redis-server

# Check Redis is listening
lsof -i :6379
```

#### Issue: Authentication Failed

**Cause**: Wrong password or conflicting configuration.

**Solution**:
```bash
# Check Redis password requirement
redis-cli -h localhost -p 6379 CONFIG GET requirepass

# Check environment variables
env | grep REDIS

# Verify password in config.yaml matches Redis
```

#### Issue: Environment Variables Overriding Config

**Cause**: Environment variables take precedence over config.yaml.

**Solution**:
```bash
# Check for conflicting env vars
env | grep -E "(REDIS|CACHE)"

# Unset conflicting vars
unset REDIS_HOST
unset REDIS_PORT
unset REDIS_PASSWORD

# Or set them correctly
export REDIS_HOST=localhost
export REDIS_PORT=6379
export REDIS_PASSWORD=your-password
```

### Redis Health Check

```bash
# Complete health check script
echo "=== Redis Health Check ==="

# 1. Container status
echo "1. Container status:"
docker ps | grep redis

# 2. Connection test
echo "2. Connection test:"
redis-cli -h localhost -p 6379 -a ${REDIS_PASSWORD} ping

# 3. Info
echo "3. Redis info:"
redis-cli -h localhost -p 6379 -a ${REDIS_PASSWORD} INFO stats

# 4. Memory usage
echo "4. Memory usage:"
redis-cli -h localhost -p 6379 -a ${REDIS_PASSWORD} INFO memory | grep used_memory_human
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
tail -f proxy.log | grep "Session cookies"

# Good: [Session cookies: 1] or higher
# Bad: [Session cookies: 0] consistently
```

### Common Issues

#### Issue: New Client Created Per Request

**Cause**: ProxySessionManager not being used correctly.

**Solution**:
```python
# ❌ Wrong - creates new client
async def make_request(url):
    client = httpx.AsyncClient()  # New client, no cookies!
    response = await client.post(url, ...)
    await client.aclose()

# ✅ Correct - reuses persistent client
async def make_request(url):
    client = await ProxySessionManager.get_client(url)
    response = await client.post(url, ...)
    # Don't close! Keep client alive for next request
```

#### Issue: Cookies for Wrong Domain

**Cause**: Using wrong base_url for session manager.

**Solution**:
```python
# ❌ Wrong - localhost doesn't set Cloudflare cookies
client = await ProxySessionManager.get_client("http://localhost:4000")

# ✅ Correct - use actual Cloudflare-protected domain
client = await ProxySessionManager.get_client("https://api.supermemory.ai")
```

#### Issue: Binary Mode Can't Control Cookies

**Cause**: When using LiteLLM binary, the Memory Proxy can't control the binary's HTTP client.

**Explanation**:
```
Memory Proxy ← → LiteLLM Binary ← → Supermemory (Cloudflare)
                        ↑
                   Cookies needed HERE
                   But we can't control binary's HTTP client!
```

**Solution**: Migrate to SDK mode (see `docs/architecture/DESIGN_DECISIONS.md`)

---

## 5. LiteLLM Binary Issues

### Symptoms

- "LiteLLM binary not found" errors
- "Command not found: litellm"
- Binary exits unexpectedly

### Solutions

#### Issue: Binary Not Installed

**Diagnosis**:
```bash
which litellm
# If empty, binary not in PATH
```

**Solution**:
```bash
# Install with uvx (recommended)
uvx install 'litellm[proxy]'

# Or with pipx
pipx install 'litellm[proxy]'

# Verify
litellm --version
```

#### Issue: Binary Port Already in Use

**Symptoms**:
- "Address already in use" error
- Binary fails to start
- Port 4000 (or configured port) occupied

**Diagnosis**:
```bash
# Check what's using port 4000
lsof -i :4000
```

**Solution**:
```bash
# Kill process using port
lsof -i :4000 | grep LISTEN | awk '{print $2}' | xargs kill

# Or use different port
litellm --config config.yaml --port 4001
```

#### Issue: Binary Crashes Silently

**Diagnosis**:
```bash
# Run binary in foreground to see errors
litellm --config config.yaml --port 4000
```

**Common causes**:
1. Invalid config.yaml syntax
2. Missing API keys
3. Invalid model configuration

**Solution**:
```bash
# Validate config
poetry run python src/proxy/schema.py config/config.yaml

# Check API keys
env | grep API_KEY

# Check logs
tail -f litellm.log
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

# Or specify in command
python litellm_proxy_with_memory.py --config /path/to/config.yaml
```

#### Issue: Environment Variables Not Resolving

**Symptoms**:
- Literal string `os.environ/OPENAI_API_KEY` in logs
- Authentication failures

**Diagnosis**:
```bash
# Check env var is set
echo $OPENAI_API_KEY

# Should not be empty
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

# Or use online validator
# Copy config to: http://www.yamllint.com/
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

#### Issue: Model Format Invalid

**Symptoms**:
- "Model must be in format 'provider/model-name'"

**Solution**:
```yaml
# ❌ Wrong
model: gpt-4

# ✅ Correct
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

**Common regex mistakes**:
```yaml
# ❌ Wrong - need to escape dots
pattern: "MyApp/1.0"

# ✅ Correct - escaped dot for literal match
pattern: "MyApp/1\\.0"

# ✅ Or - use .* for any version
pattern: "MyApp/.*"
```

#### Issue: First Match Wins

**Cause**: Patterns are evaluated in order, first match wins.

**Solution**: Put more specific patterns first:
```yaml
header_patterns:
  # ✅ More specific first
  - header: "user-agent"
    pattern: "MyApp/2\\.0"
    user_id: "myapp-v2"
  
  # More general last
  - header: "user-agent"
    pattern: "MyApp/.*"
    user_id: "myapp-general"
```

#### Issue: Default User ID Always Used

**Cause**: No patterns matching.

**Diagnosis**:
```bash
curl http://localhost:8764/memory-routing/info \
  -H "User-Agent: YourApp" | jq '.is_default'
# If true, no pattern matched
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

# CPU
top -p $(pgrep -f litellm)

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

# Check current limit
ulimit -n
```

**In code**:
```python
# Limit connection pool size
httpx.AsyncClient(
    limits=httpx.Limits(
        max_connections=100,
        max_keepalive_connections=20
    )
)
```

#### Issue: Memory Leaks

**Symptoms**:
- Memory usage grows over time
- Eventually crashes or slows down

**Diagnosis**:
```bash
# Monitor memory over time
watch -n 5 'ps aux | grep litellm'
```

**Solution**:
- Ensure HTTP clients are properly closed
- Use ProxySessionManager correctly
- Implement cleanup in FastAPI lifespan

#### Issue: Slow Database Queries

**Symptoms**:
- High latency on requests
- Database connection pool exhausted

**Solution**:
```yaml
# Increase connection pool limit
general_settings:
  database_connection_pool_limit: 100

# Add database indexes
# (See database documentation)
```

---

## Getting Help

If you're still experiencing issues after trying these solutions:

1. **Enable Debug Logging**:
   ```bash
   export LOG_LEVEL=DEBUG
   python litellm_proxy_with_memory.py
   ```

2. **Collect Diagnostic Info**:
   ```bash
   # System info
   python --version
   poetry --version
   
   # Configuration
   cat config.yaml
   
   # Environment
   env | grep -E "(API_KEY|REDIS|DATABASE)"
   
   # Logs
   tail -100 proxy.log
   ```

3. **Check Related Documentation**:
   - [Architecture Overview](../architecture/OVERVIEW.md)
   - [Design Decisions](../architecture/DESIGN_DECISIONS.md)
   - [Configuration Guide](../guides/CONFIGURATION.md)
   - [Testing Guide](../guides/TESTING.md)

4. **Search Existing Issues**:
   - Check if similar issues have been reported
   - Look for solutions in closed issues

---

**Last Updated**: 2025-11-04  
**Status**: Consolidated from diagnostic reports and investigation documents
