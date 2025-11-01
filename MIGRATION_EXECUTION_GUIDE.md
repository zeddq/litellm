# SDK Migration Execution Guide

**Status**: ✅ Implementation Complete - Ready for Testing
**Date**: 2025-11-02
**Timeline**: 3-4 days from testing to production

---

## Executive Summary

The SDK migration from binary LiteLLM to SDK approach is **complete and ready for testing**. All implementation files, tests, and infrastructure are in place. The binary proxy remains **completely untouched** and fully functional.

### What's Been Delivered

✅ **5 SDK implementation files** (2,578 lines)
✅ **12 test files** (2,463 lines)
✅ **1 unified launcher** (supports both approaches)
✅ **3 comprehensive documentation files** (2,540 lines)
✅ **106+ test cases** at 4 levels (unit, integration, comparison, E2E)
✅ **0 modifications to existing code** (binary proxy untouched)

---

## Phase 1: Verification (15 minutes)

### Step 1: Verify File Structure

Check that all new files exist and binary files are untouched:

```bash
# New SDK files (should exist)
ls -la src/proxy/litellm_proxy_sdk.py
ls -la src/proxy/session_manager.py
ls -la src/proxy/config_parser.py
ls -la src/proxy/error_handlers.py
ls -la src/proxy/streaming_utils.py

# Binary files (should be unchanged)
git status src/proxy/litellm_proxy_with_memory.py  # Should show no changes
git status src/proxy/memory_router.py             # Should show no changes
git status src/proxy/schema.py                    # Should show no changes

# Test files (should exist)
ls -la tests/test_sdk_components.py
ls -la tests/test_sdk_integration.py
ls -la tests/test_binary_vs_sdk.py
ls -la tests/test_sdk_e2e.py

# Launcher (should exist)
ls -la deploy/run_unified_proxy.py

# Validation script (should exist)
ls -la validate_sdk_migration.py
```

### Step 2: Verify Dependencies

Ensure all required packages are installed:

```bash
# Install dependencies
poetry install

# Check specific packages
poetry show litellm
poetry show fastapi
poetry show httpx
poetry show uvicorn
poetry show pytest
```

### Step 3: Verify Binary Proxy Still Works

**CRITICAL**: Confirm binary proxy is unaffected:

```bash
# Start binary proxy (existing method)
poetry run start-proxies

# Test health (in another terminal)
curl http://localhost:8764/health

# Test completion
curl http://localhost:8764/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer sk-1234" \
  -d '{
    "model": "claude-sonnet-4.5",
    "messages": [{"role": "user", "content": "Test binary proxy"}],
    "max_tokens": 10
  }'

# Stop
# Press Ctrl+C
```

**Expected**: Binary proxy works exactly as before ✅

---

## Phase 2: Unit Testing (30 minutes)

### Step 1: Run Unit Tests

Test individual SDK components in isolation:

```bash
# Run all unit tests
pytest tests/test_sdk_components.py -v

# Expected: 50+ tests, all passing
# Execution time: <5 seconds
```

**What's being tested**:
- Session manager (singleton, cookie persistence, cleanup)
- Config parser (YAML parsing, env vars, model lookup)
- Error handlers (all exception types, response formatting)
- Streaming utilities (SSE format, chunk monitoring)

### Step 2: Investigate Failures (if any)

If tests fail:

```bash
# Run with verbose output
pytest tests/test_sdk_components.py -vv -s

# Run specific test
pytest tests/test_sdk_components.py::test_session_manager_singleton -vv

# Debug with pdb
pytest tests/test_sdk_components.py --pdb

# Check logs
tail -f logs/test_sdk_components.log
```

### Step 3: Verify Coverage

```bash
# Generate coverage report
pytest tests/test_sdk_components.py --cov=src/proxy --cov-report=html

# Open report
open htmlcov/index.html

# Expected: >80% coverage for all SDK files
```

---

## Phase 3: Integration Testing (1 hour)

### Step 1: Run Integration Tests

Test SDK proxy endpoints with mocked backends:

```bash
# Run all integration tests
pytest tests/test_sdk_integration.py -v

# Expected: 42+ tests, all passing
# Execution time: <30 seconds
```

**What's being tested**:
- FastAPI app startup/shutdown
- `/health` endpoint
- `/v1/models` endpoint
- `/v1/chat/completions` (streaming + non-streaming)
- `/memory-routing/info` endpoint
- Authentication and authorization
- Error scenarios (401, 400, 404, 429, 503)

### Step 2: Test SDK Proxy Manually

Start SDK proxy and test manually:

```bash
# Terminal 1: Start SDK proxy
python deploy/run_unified_proxy.py --mode sdk

# Terminal 2: Test endpoints
# Health check
curl http://localhost:8765/health

# Models list
curl http://localhost:8765/v1/models \
  -H "Authorization: Bearer sk-1234"

# Chat completion (non-streaming)
curl http://localhost:8765/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer sk-1234" \
  -d '{
    "model": "claude-sonnet-4.5",
    "messages": [{"role": "user", "content": "Hello from SDK proxy!"}],
    "max_tokens": 50
  }'

# Memory routing info
curl http://localhost:8765/memory-routing/info \
  -H "User-Agent: OpenAIClientImpl/Java"

# Stop: Press Ctrl+C in Terminal 1
```

**Expected**: All endpoints respond correctly ✅

### Step 3: Test Streaming

```bash
# Terminal 1: SDK proxy should still be running
# (If not, restart: python deploy/run_unified_proxy.py --mode sdk)

# Terminal 2: Test streaming
curl http://localhost:8765/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer sk-1234" \
  -d '{
    "model": "claude-sonnet-4.5",
    "messages": [{"role": "user", "content": "Count to 5"}],
    "stream": true
  }'

# Expected: SSE format chunks, ending with "data: [DONE]\n\n"
```

---

## Phase 4: Feature Parity Testing (1 hour)

### Step 1: Run Comparison Tests

Validate SDK proxy matches binary proxy behavior:

```bash
# Start both proxies
python deploy/run_unified_proxy.py --mode both

# In another terminal, run comparison tests
pytest tests/test_binary_vs_sdk.py -v

# Expected: 13+ tests, all passing
# Confirms feature parity
```

**What's being tested**:
- Same response format (OpenAI-compatible)
- Same error handling
- Same memory routing behavior
- Same header forwarding
- Performance comparison

### Step 2: Manual Side-by-Side Comparison

```bash
# Binary proxy on 8764
curl http://localhost:8764/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer sk-1234" \
  -d '{
    "model": "claude-sonnet-4.5",
    "messages": [{"role": "user", "content": "Test message"}],
    "max_tokens": 10
  }' > binary_response.json

# SDK proxy on 8765
curl http://localhost:8765/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer sk-1234" \
  -d '{
    "model": "claude-sonnet-4.5",
    "messages": [{"role": "user", "content": "Test message"}],
    "max_tokens": 10
  }' > sdk_response.json

# Compare (should be nearly identical, except minor differences like timing)
diff binary_response.json sdk_response.json
```

---

## Phase 5: End-to-End Testing (2 hours)

### Step 1: Set Up API Keys

```bash
# Export real API keys
export ANTHROPIC_API_KEY="sk-ant-..."
export OPENAI_API_KEY="sk-..."
export SUPERMEMORY_API_KEY="sm_..."
```

### Step 2: Run E2E Tests

Test with real providers:

```bash
# Run E2E tests (requires API keys)
pytest tests/test_sdk_e2e.py -v -m e2e

# Expected: 14+ tests, all passing (if API keys are valid)
# Execution time: Variable (depends on API response times)
```

**What's being tested**:
- Real Anthropic API calls
- Real OpenAI API calls
- Cookie persistence (Cloudflare verification)
- Actual streaming responses
- Load testing (50+ concurrent requests)
- Memory stability under load

### Step 3: Cookie Persistence Verification

**CRITICAL TEST**: Verify Cloudflare cookies persist:

```bash
# Start SDK proxy with debug logging
LOG_LEVEL=DEBUG python deploy/run_unified_proxy.py --mode sdk

# Make multiple requests to Supermemory (look for cookie persistence in logs)
for i in {1..5}; do
  echo "=== Request $i ==="
  curl -s http://localhost:8765/v1/chat/completions \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer sk-1234" \
    -d '{
      "model": "claude-sonnet-4.5",
      "messages": [{"role": "user", "content": "Test '$i'"}],
      "max_tokens": 10
    }' | jq '.choices[0].message.content'

  echo ""
  sleep 2
done

# Check logs for:
# ✅ "Cookie count: X" (should be >0 after first request)
# ✅ "cf_clearance", "__cf_bm" cookies present
# ❌ No 503 errors (Cloudflare Error 1200)
```

**Expected**:
- First request: Cloudflare challenge, cookies set
- Subsequent requests: Cookies reused, no challenges
- **Zero 503 errors** ✅

### Step 4: Load Testing

Test concurrent requests:

```bash
# Run load tests
pytest tests/test_sdk_e2e.py::test_concurrent_requests_load -v

# Or manual load test:
python -c "
import asyncio
import httpx

async def make_request(i):
    async with httpx.AsyncClient() as client:
        try:
            r = await client.post(
                'http://localhost:8765/v1/chat/completions',
                json={
                    'model': 'claude-sonnet-4.5',
                    'messages': [{'role': 'user', 'content': f'Request {i}'}],
                    'max_tokens': 10
                },
                headers={'Authorization': 'Bearer sk-1234'},
                timeout=30.0
            )
            return r.status_code
        except Exception as e:
            return str(e)

async def main():
    tasks = [make_request(i) for i in range(50)]
    results = await asyncio.gather(*tasks)
    successes = sum(1 for r in results if r == 200)
    print(f'Successes: {successes}/50')
    print(f'Failure rate: {(50-successes)/50*100:.1f}%')

asyncio.run(main())
"
```

**Expected**:
- Success rate: >95%
- No memory leaks
- Stable response times

---

## Phase 6: Client Testing (2 hours)

### Step 1: Test with PyCharm AI Assistant

```bash
# Start SDK proxy
python deploy/run_unified_proxy.py --mode sdk

# Configure PyCharm:
# Settings → AI Assistant → OpenAI Service
# - URL: http://localhost:8765/v1
# - API Key: sk-1234
# - Model: claude-sonnet-4.5

# Test in PyCharm:
# 1. Ask AI Assistant a question
# 2. Check streaming works
# 3. Check memory routing (should auto-detect as "pycharm-ai")

# Verify routing:
curl http://localhost:8765/memory-routing/info \
  -H "User-Agent: OpenAIClientImpl/Java"
# Expected: {"user_id": "pycharm-ai", ...}
```

### Step 2: Test with Claude Code

```bash
# Set environment variable
export ANTHROPIC_BASE_URL="http://localhost:8765"

# Test Claude Code
# (In the IDE where Claude Code is running)

# Verify routing:
curl http://localhost:8765/memory-routing/info \
  -H "User-Agent: Claude Code/1.0"
# Expected: {"user_id": "claude-cli", ...}
```

### Step 3: Test with Direct API Calls

```python
# test_direct_client.py
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8765/v1",
    api_key="sk-1234"
)

# Non-streaming
response = client.chat.completions.create(
    model="claude-sonnet-4.5",
    messages=[{"role": "user", "content": "Hello!"}],
    max_tokens=50
)
print(response.choices[0].message.content)

# Streaming
stream = client.chat.completions.create(
    model="claude-sonnet-4.5",
    messages=[{"role": "user", "content": "Count to 5"}],
    stream=True
)
for chunk in stream:
    if chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="")
print()
```

Run it:
```bash
python test_direct_client.py
```

---

## Phase 7: Validation Script (30 minutes)

### Step 1: Run Pre-Migration Validation

```bash
# Validate binary proxy is healthy
./validate_sdk_migration.py --phase pre

# Expected output:
# ✅ Binary proxy health check
# ✅ LiteLLM binary accessible
# ✅ Configuration valid
# ✅ Memory routing works
# ✅ All dependencies present
```

### Step 2: Run Post-Migration Validation

```bash
# Validate SDK proxy is healthy
./validate_sdk_migration.py --phase post

# Expected output:
# ✅ SDK proxy health check
# ✅ All endpoints accessible
# ✅ Feature parity confirmed
# ✅ Cookie persistence verified
# ✅ Performance acceptable
```

### Step 3: Run Full Validation

```bash
# Complete validation suite
./validate_sdk_migration.py --phase all

# Expected: All checks pass
# Exit code: 0 (success)
```

---

## Phase 8: Performance Comparison (1 hour)

### Step 1: Benchmark Binary Proxy

```bash
# Start binary proxy
python deploy/run_unified_proxy.py --mode binary

# Benchmark (using apache bench or similar)
ab -n 100 -c 10 \
  -H "Authorization: Bearer sk-1234" \
  -H "Content-Type: application/json" \
  -p test_request.json \
  http://localhost:8764/v1/chat/completions

# Record:
# - Average latency
# - p95 latency
# - Requests per second
# - Memory usage
```

### Step 2: Benchmark SDK Proxy

```bash
# Start SDK proxy
python deploy/run_unified_proxy.py --mode sdk

# Same benchmark
ab -n 100 -c 10 \
  -H "Authorization: Bearer sk-1234" \
  -H "Content-Type: application/json" \
  -p test_request.json \
  http://localhost:8765/v1/chat/completions

# Compare to binary proxy
```

### Step 3: Evaluate Results

**Success Criteria**:
- ✅ SDK latency ≤ Binary latency (should be faster due to no extra hop)
- ✅ SDK memory usage ≤ 1.5x Binary
- ✅ SDK throughput ≥ Binary throughput
- ✅ Zero 503 errors (cookie persistence working)

---

## Phase 9: Cutover Decision (1 hour)

### Decision Checklist

Before switching to SDK as primary:

- [ ] All unit tests pass (50+)
- [ ] All integration tests pass (42+)
- [ ] All comparison tests pass (13)
- [ ] E2E tests pass with real APIs
- [ ] Cookie persistence verified (no 503s)
- [ ] PyCharm AI Assistant works
- [ ] Claude Code works
- [ ] Direct API clients work
- [ ] Load testing passes (50+ concurrent)
- [ ] Performance acceptable (SDK ≤ 2x Binary)
- [ ] Memory stable under load
- [ ] Validation script passes all checks
- [ ] Rollback procedure tested
- [ ] Team approval obtained

### If All Criteria Met: Proceed with Cutover

### If Any Criteria Failed: Investigate and Fix

---

## Phase 10: Cutover (30 minutes)

### Step 1: Update Default Launcher

```bash
# Edit deploy/run_unified_proxy.py
# Change default mode from BINARY to SDK

# Or create alias
alias start-proxy='python deploy/run_unified_proxy.py --mode sdk'
```

### Step 2: Update Documentation

```bash
# Update CLAUDE.md to reference SDK proxy
# Update README.md
# Update docs/getting-started/QUICKSTART.md

# Mark binary proxy as "legacy" but keep available
```

### Step 3: Announce Migration

Create migration announcement:

```markdown
# LiteLLM Proxy Migration to SDK Approach

**Date**: 2025-11-02
**Status**: Complete

The LiteLLM proxy has been migrated from binary to SDK approach.

**Key Changes**:
- Default port changed from 8764 to 8765
- Cookie persistence now works (no more 503 errors)
- Better performance (lower latency)
- Single process deployment

**Migration Guide**:
- Update your client configuration to point to port 8765
- Or set `ANTHROPIC_BASE_URL="http://localhost:8765"` for Claude Code

**Rollback**:
If you experience issues, roll back with:
```bash
python deploy/run_unified_proxy.py --mode binary
```

**Support**: Contact team if you have questions.
```

### Step 4: Archive Binary Implementation

```bash
# Create archive directory
mkdir -p src/proxy/archive

# Move binary files (keep for rollback)
# DO NOT DELETE - keep for emergency rollback
# Just mark as archived in documentation
```

---

## Phase 11: Monitoring (Ongoing)

### What to Monitor

**First 24 Hours**:
- Error rate (should decrease due to cookie persistence)
- Response times (should improve)
- Memory usage (should be stable)
- Cookie persistence (check logs for cf_clearance)
- User feedback (PyCharm, Claude Code users)

**First Week**:
- Long-term memory stability
- Connection pool behavior
- Performance under various loads
- Client compatibility issues

### Key Metrics

| Metric | Pre-Migration (Binary) | Post-Migration (SDK) | Target |
|--------|----------------------|---------------------|---------|
| Error Rate | ~5% | ? | <2% |
| P95 Latency | ~520ms | ? | <520ms |
| Memory Usage | ~300MB | ? | <350MB |
| 503 Errors | Frequent | ? | 0 |
| Cloudflare Challenges | Every request | ? | Once per session |

### Monitoring Commands

```bash
# Check error rate
tail -f logs/sdk_proxy.log | grep ERROR

# Check latency
tail -f logs/sdk_proxy.log | grep "Request completed" | awk '{print $NF}'

# Check memory
ps aux | grep "litellm_proxy_sdk"

# Check cookie persistence
tail -f logs/sdk_proxy.log | grep "Cookie count"

# Check active connections
lsof -i :8765
```

---

## Rollback Procedure

If major issues occur, roll back immediately:

### Quick Rollback (<5 minutes)

```bash
# Option 1: Environment variable
USE_SDK_PROXY=false python deploy/run_unified_proxy.py

# Option 2: Command line
python deploy/run_unified_proxy.py --mode binary

# Option 3: Existing launcher
poetry run start-proxies  # Should still work
```

### Verify Rollback

```bash
# Test binary proxy
curl http://localhost:8764/health

# Test completion
curl http://localhost:8764/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer sk-1234" \
  -d '{"model": "claude-sonnet-4.5", "messages": [{"role": "user", "content": "Test"}]}'

# Update client configurations back to port 8764
```

### Post-Rollback Analysis

```bash
# Review logs
tail -100 logs/sdk_proxy.log > rollback_investigation.log

# Run validation to identify issues
./validate_sdk_migration.py --phase all > validation_report.txt

# Debug specific failures
pytest tests/test_sdk_e2e.py -vv -s
```

---

## Success Criteria Summary

The migration is successful when:

1. ✅ **All tests pass** (106+ tests)
2. ✅ **Cookie persistence works** (no 503 errors)
3. ✅ **Feature parity confirmed** (SDK = Binary behavior)
4. ✅ **Performance acceptable** (SDK ≤ Binary latency)
5. ✅ **Clients work** (PyCharm, Claude Code, direct APIs)
6. ✅ **Validation passes** (pre, post, all phases)
7. ✅ **Load testing passes** (50+ concurrent requests)
8. ✅ **Memory stable** (no leaks under load)
9. ✅ **Rollback tested** (can revert in <5 minutes)
10. ✅ **Documentation updated** (all references to SDK)

---

## Timeline Summary

| Phase | Duration | Tasks |
|-------|----------|-------|
| Verification | 15 min | Check files, deps, binary still works |
| Unit Testing | 30 min | Run 50+ unit tests |
| Integration Testing | 1 hour | Test SDK endpoints, manual testing |
| Feature Parity | 1 hour | Binary vs SDK comparison |
| E2E Testing | 2 hours | Real APIs, cookie persistence, load testing |
| Client Testing | 2 hours | PyCharm, Claude Code, direct APIs |
| Validation | 30 min | Pre, post, full validation |
| Performance | 1 hour | Benchmark both proxies |
| Cutover Decision | 1 hour | Review checklist, get approval |
| Cutover | 30 min | Update defaults, docs, announce |
| Monitoring | Ongoing | Track metrics, user feedback |

**Total Active Time**: ~10 hours (can be spread over 3-4 days)

---

## Contact & Support

**Questions**: Check documentation in `docs/architecture/`
**Issues**: Review logs in `logs/`
**Rollback**: Follow "Rollback Procedure" section above
**Emergency**: Contact migration team

---

## Next Steps

1. ✅ Read this guide thoroughly
2. ✅ Start with Phase 1 (Verification)
3. ✅ Progress through phases sequentially
4. ✅ Document any issues encountered
5. ✅ Make cutover decision based on checklist
6. ✅ Monitor post-migration
7. ✅ Celebrate success! 🎉

---

**Good luck with the migration! The SDK approach will provide better performance, reliability, and developer experience.**
