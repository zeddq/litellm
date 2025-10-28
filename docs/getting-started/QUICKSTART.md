# Quick Start Guide - LiteLLM Memory Proxy

Get up and running with LiteLLM Memory Proxy in 5 minutes!

---

## Overview

LiteLLM Memory Proxy is a lightweight memory routing proxy for LiteLLM with dynamic user-based memory isolation using Supermemory. This guide provides quick setup instructions to get you started immediately.

---

## Prerequisites

```bash
# Python 3.13+
python --version

# Install dependencies
pip install litellm[proxy] fastapi uvicorn httpx pyyaml pydantic openai anthropic
```

Or using Poetry:
```bash
poetry install
```

---

## 1. Environment Setup

Create a `.env` file:

```bash
# Required
export OPENAI_API_KEY="sk-your-openai-key-here"

# Optional
export ANTHROPIC_API_KEY="sk-ant-your-anthropic-key-here"
export SUPERMEMORY_API_KEY="sm-your-supermemory-key-here"
export REDIS_URL="redis://localhost:6379/0"  # For persistence

# Proxy Configuration
export LITELLM_BASE_URL="http://localhost:8765"
export LITELLM_CONFIG="./config.yaml"
```

Load environment:

```bash
source .env
```

---

## 2. Configuration

Edit `config.yaml` to configure:
- **Models**: OpenAI, Anthropic, Gemini models
- **User ID Mappings**: Header patterns for client detection
- **Memory Routing**: Supermemory integration settings

Example configuration:
```yaml
general_settings:
  master_key: sk-1234

model_list:
  - model_name: gpt-4
    litellm_params:
      model: openai/gpt-4
      api_key: os.environ/OPENAI_API_KEY

  - model_name: claude-sonnet-4.5
    litellm_params:
      api_base: https://api.supermemory.ai/v3/api.anthropic.com
      model: anthropic/claude-sonnet-4-5-20250929
      api_key: os.environ/ANTHROPIC_API_KEY

user_id_mappings:
  header_patterns:
    - header: "user-agent"
      pattern: "OpenAIClientImpl/Java"
      user_id: "pycharm-ai"
    - header: "user-agent"
      pattern: "Claude Code"
      user_id: "claude-cli"
```

---

## 3. Start the Proxies

### Option A: Start Both Proxies (Recommended)

```bash
poetry run start-proxies
# or with custom ports
poetry run start-proxies --litellm-port 8765 --memoryproxy-port 8764
# or with custom config
poetry run start-proxies --config ./config.yaml
```

This will:
1. Start LiteLLM as an external binary process on port 8765
2. Start Memory Proxy on port 8764 (forwarding to LiteLLM)
3. Provide automatic memory routing and user isolation

### Option B: Start Memory Proxy Only

If LiteLLM is already running:

```bash
poetry run python litellm_proxy_with_memory.py \
  --config config.yaml \
  --port 8764 \
  --litellm-url http://localhost:8765
```

### Option C: Start LiteLLM Binary Manually

```bash
litellm --config config.yaml --port 8765 --host 0.0.0.0
```

---

## 4. Test with cURL

### First Message

```bash
curl -X POST http://localhost:8764/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer sk-1234" \
  -H "x-session-id: my-session" \
  -d '{
    "model": "gpt-4",
    "messages": [
      {"role": "user", "content": "My name is Alice"}
    ]
  }'
```

### Second Message - Memory Maintained!

```bash
curl -X POST http://localhost:8764/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer sk-1234" \
  -H "x-session-id: my-session" \
  -d '{
    "model": "gpt-4",
    "messages": [
      {"role": "user", "content": "What is my name?"}
    ]
  }'

# Response will include: "Your name is Alice" (from memory!)
```

---

## 5. Test with Python SDK

### Using OpenAI SDK

```python
from openai import OpenAI

# Point to your proxy
client = OpenAI(
    base_url="http://localhost:8764/v1",
    api_key="sk-1234"  # Your configured master key
)

# First message
response1 = client.chat.completions.create(
    model="gpt-4",
    messages=[
        {"role": "user", "content": "My favorite color is blue"}
    ],
    extra_headers={"x-session-id": "demo-session"}
)
print(response1.choices[0].message.content)

# Second message - memory works!
response2 = client.chat.completions.create(
    model="gpt-4",
    messages=[
        {"role": "user", "content": "What's my favorite color?"}
    ],
    extra_headers={"x-session-id": "demo-session"}
)
print(response2.choices[0].message.content)
# Output: "Your favorite color is blue"
```

---

## 6. View Session History

```bash
# List all sessions
curl http://localhost:8764/v1/sessions

# Get session details
curl http://localhost:8764/v1/sessions/demo-session

# Delete session
curl -X DELETE http://localhost:8764/v1/sessions/demo-session
```

---

## Common Commands

```bash
# Run tutorial examples
python tutorial_proxy_with_memory.py --examples

# View tutorial documentation
python tutorial_proxy_with_memory.py

# Start server on custom port
python tutorial_proxy_with_memory.py --serve --port 8080

# Run tests
python test_tutorial.py

# Check health
curl http://localhost:8764/health
```

---

## Key Features

- **Memory Persistence** - Conversations maintained across requests
- **Multi-Provider** - OpenAI, Anthropic, Gemini support
- **Client Detection** - Automatic user isolation via headers
- **Rate Limiting** - Built-in request throttling
- **Redis Support** - Optional persistent storage
- **Streaming** - Supports streaming responses
- **Production-Ready** - Logging, monitoring, error handling

---

## Architecture

```
Client (OpenAI SDK, Anthropic SDK, curl, etc.)
    ↓
Memory Proxy (Port 8764) - FastAPI Application
    • Client Detection via User-Agent patterns
    • Dynamic x-sm-user-id injection
    • HTTP request forwarding
    ↓
LiteLLM Binary Process (Port 8765)
    • External process: litellm --config config.yaml
    ↓
OpenAI / Anthropic / Gemini APIs
```

---

## Troubleshooting

### LiteLLM binary not found
```bash
pip install litellm
# Verify installation
which litellm
```

### Memory Proxy can't connect to LiteLLM
- Ensure LiteLLM is running: `curl http://localhost:8765/health`
- Check port configuration
- Review logs for connection errors

### Client detection not working
- Check User-Agent patterns in config.yaml
- Test with: `curl http://localhost:8764/memory-routing/info -H "User-Agent: YourClient"`
- Review logs for pattern matching

---

## Next Steps

1. Read the comprehensive [Tutorial Guide](../TUTORIAL.md)
2. Review the [Architecture Overview](../../architecture/OVERVIEW.md)
3. Explore [Testing Documentation](../../guides/testing/TESTING_GUIDE.md)
4. Learn about [Production Deployment](../../guides/migration/MIGRATION_GUIDE.md)
5. Run examples: `python example_complete_workflow.py`

---

**Happy Building!**

---

**Sources**: TUTORIAL_QUICKSTART.md, TUTORIAL_README.md (intro), README.md (quick start)
**Created**: 2025-10-24
**Updated**: 2025-10-24
