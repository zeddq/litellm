# Quick Start Guide

Get your memory-aware LiteLLM proxy running in 5 minutes.

## Prerequisites

```bash
# Install dependencies
pip install fastapi uvicorn httpx pyyaml

# Set environment variables
export SUPERMEMORY_API_KEY="sm_1234"
export ANTHROPIC_API_KEY="sk-ant-your_key_here"
```

## Step 1: Verify Configuration

```bash
cd ~/litellm
cat config.yaml
```

Should contain the `user_id_mappings` section:
```yaml
user_id_mappings:
  custom_header: "x-memory-user-id"
  header_patterns:
    - header: "user-agent"
      pattern: "OpenAIClientImpl/Java"
      user_id: "pycharm-ai-chat"
  default_user_id: "default-dev"
```

## Step 2: Test Routing Logic

```bash
python test_memory_routing.py
```

Expected output:
```
✓ All tests passed!
✓ ALL TESTS PASSED
```

## Step 3: Start Proxies

### Terminal 1: LiteLLM Base Proxy
```bash
litellm --config config.yaml --port 4000
```

### Terminal 2: Memory Routing Proxy
```bash
cd ~/litellm
python litellm_proxy_with_memory.py --port 8765 --litellm-url http://localhost:4000
```

You should see:
```
INFO: Starting proxy on 127.0.0.1:8765
INFO: Forwarding to LiteLLM at http://localhost:4000
INFO: Memory Router initialized
```

## Step 4: Test It Works

### Test 1: Check Routing Info
```bash
curl http://localhost:8765/memory-routing/info \
  -H "User-Agent: OpenAIClientImpl/Java unknown"
```

Expected:
```json
{
  "user_id": "pycharm-ai-chat",
  "matched_pattern": {...},
  "custom_header_present": false,
  "is_default": false
}
```

### Test 2: Send Chat Request
```bash
curl http://localhost:8765/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer sk-1234" \
  -H "User-Agent: OpenAIClientImpl/Java unknown" \
  -d '{
    "model": "claude-sonnet-4.5",
    "messages": [{"role": "user", "content": "Hello! Remember: Project X uses Python"}],
    "max_tokens": 100
  }'
```

Check the logs - should see:
```
INFO | MEMORY ROUTING: model=claude-sonnet-4.5, user_id=pycharm-ai-chat
INFO | MATCHED PATTERN: user-agent='OpenAIClientImpl/Java unknown' -> pycharm-ai-chat
INFO | INJECTED: x-sm-user-id=pycharm-ai-chat
```

### Test 3: Verify Memory Works
```bash
# Second request should remember first conversation
curl http://localhost:8765/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer sk-1234" \
  -H "User-Agent: OpenAIClientImpl/Java unknown" \
  -d '{
    "model": "claude-sonnet-4.5",
    "messages": [{"role": "user", "content": "What language does Project X use?"}],
    "max_tokens": 50
  }'
```

## Step 5: Configure PyCharm

1. Open PyCharm Settings
2. Go to: **AI Assistant → OpenAI Service**
3. Set:
   - **URL**: `http://localhost:8765/v1`
   - **API Key**: `sk-1234`
   - **Model**: `claude-sonnet-4.5`
4. Click **Test Connection**
5. Start chatting!

PyCharm's conversations will now have memory across sessions, isolated from other clients.

## What's Next?

### Add More Clients

Edit `config.yaml`:
```yaml
user_id_mappings:
  header_patterns:
    - header: "user-agent"
      pattern: "MyApp/.*"
      user_id: "my-custom-app"
```

Restart memory proxy and test:
```bash
curl http://localhost:8765/memory-routing/info \
  -H "User-Agent: MyApp/1.0"
```

### Use Custom Headers

Any client can send explicit user ID:
```bash
curl http://localhost:8765/v1/chat/completions \
  -H "x-memory-user-id: project-alpha" \
  -H "Authorization: Bearer sk-1234" \
  -d '...'
```

### Monitor Logs

Watch routing decisions in real-time:
```bash
# In the memory proxy terminal
tail -f logs/memory-proxy.log  # if logging to file
# or just watch the console output
```

## Troubleshooting

### "Module not found" errors
```bash
pip install fastapi uvicorn httpx pyyaml
```

### "Connection refused" on port 4000
Make sure LiteLLM base proxy is running:
```bash
litellm --config config.yaml --port 4000
```

### "Unauthorized" from Supermemory
Check environment variable:
```bash
echo $SUPERMEMORY_API_KEY
```

### Wrong user ID assigned
Check the `/memory-routing/info` endpoint to debug.

## Architecture

```
PyCharm (port 8765)
    ↓
Memory Router (detects: OpenAIClientImpl/Java)
    ↓ (injects: x-sm-user-id=pycharm-ai-chat)
LiteLLM Proxy (port 4000)
    ↓ (routes to Supermemory with memory headers)
Supermemory
    ↓ (stores conversation under pycharm-ai-chat)
Anthropic API
```

## Production Deployment

For production, consider:

1. **SSL/TLS**: Use nginx/caddy as reverse proxy
2. **Authentication**: Add API key validation
3. **Rate Limiting**: Implement per-user-id limits
4. **Monitoring**: Add metrics and alerting
5. **Logging**: Write to files with rotation

See `MEMORY_ROUTING_README.md` for advanced topics.

## Support

- Check logs with `--log-level DEBUG`
- Test routing: `curl http://localhost:8765/memory-routing/info`
- Read full docs: `MEMORY_ROUTING_README.md`
