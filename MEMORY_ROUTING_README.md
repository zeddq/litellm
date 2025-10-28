# LiteLLM Proxy with Dynamic Supermemory Routing

Multi-tenant memory routing for LiteLLM proxy that automatically detects clients and assigns isolated Supermemory user IDs.

## Features

- **Automatic Client Detection**: Identifies clients by User-Agent and custom headers
- **Memory Isolation**: Each client gets its own Supermemory user ID
- **Pattern Matching**: Flexible regex-based header detection
- **Custom Headers**: Explicit user ID specification via `x-memory-user-id`
- **Zero Code Changes**: Works with existing clients (PyCharm, Claude Code, etc.)

## Architecture

```
Client (PyCharm AI Chat)
    ↓ User-Agent: OpenAIClientImpl/Java
Memory Proxy (port 8765)
    ↓ Detects client → Injects x-sm-user-id: pycharm-ai-chat
LiteLLM Proxy (port 4000)
    ↓ Routes with memory headers
Supermemory API
    ↓ Stores memories per user ID
Anthropic API
```

## Files

- **`memory_router.py`**: Core routing logic and header detection
- **`litellm_proxy_with_memory.py`**: Complete proxy implementation
- **`config.yaml`**: Configuration with user ID mappings

## Configuration

### config.yaml

```yaml
user_id_mappings:
  # Custom header for explicit user ID (highest priority)
  custom_header: "x-memory-user-id"

  # Pattern-based detection
  header_patterns:
    - header: "user-agent"
      pattern: "OpenAIClientImpl/Java"
      user_id: "pycharm-ai-chat"

    - header: "user-agent"
      pattern: "anthropic-sdk-python"
      user_id: "claude-code"

    - header: "user-agent"
      pattern: "Claude Code"
      user_id: "claude-code-cli"

  # Default when no pattern matches
  default_user_id: "default-dev"
```

### Environment Variables

```bash
export SUPERMEMORY_API_KEY="sm_your_key_here"
export ANTHROPIC_API_KEY="sk-ant-your_key_here"
```

## Installation

```bash
cd ~/litellm

# Install dependencies
pip install fastapi uvicorn httpx pyyaml

# Or if using pipx for litellm
pipx inject litellm fastapi uvicorn httpx pyyaml
```

## Usage

### Option 1: Standalone Proxy (Recommended)

Run the memory-aware proxy on port 8765, which forwards to LiteLLM on port 4000:

```bash
# Terminal 1: Start LiteLLM proxy
litellm --config config.yaml --port 4000

# Terminal 2: Start memory routing proxy
python litellm_proxy_with_memory.py --port 8765 --litellm-url http://localhost:4000
```

Configure clients to use `http://localhost:8765` instead of `http://localhost:4000`.

### Option 2: Integrate into Existing Proxy

If you already have a custom `litellm_proxy.py`, add this code:

```python
from memory_router import MemoryRouter
import os

# Initialize router
router = MemoryRouter("config.yaml")

# In your request handler
def handle_request(headers, body):
    # Detect user ID
    routing_info = router.get_routing_info(headers)
    user_id = routing_info['user_id']

    # Inject Supermemory headers
    supermemory_key = os.environ.get('SUPERMEMORY_API_KEY')
    updated_headers = router.inject_memory_headers(headers, supermemory_key)

    # Forward request with updated headers
    # ... your forwarding logic ...
```

## Testing

### 1. Test Memory Router

```bash
cd ~/litellm
python memory_router.py
```

Expected output:
```
=== PyCharm AI Chat Request ===
User ID: pycharm-ai-chat
Matched Pattern: {...}

=== Custom Header Request ===
User ID: project-alpha
Custom Header Present: True

=== Default Request ===
User ID: default-dev
Is Default: True
```

### 2. Test Proxy Routing Info

Start the proxy and check routing for different headers:

```bash
# Start proxy
python litellm_proxy_with_memory.py --port 8765

# Test PyCharm AI Chat detection
curl http://localhost:8765/memory-routing/info \
  -H "User-Agent: OpenAIClientImpl/Java unknown"

# Expected: {"user_id": "pycharm-ai-chat", ...}

# Test custom header
curl http://localhost:8765/memory-routing/info \
  -H "x-memory-user-id: my-project"

# Expected: {"user_id": "my-project", ...}

# Test default
curl http://localhost:8765/memory-routing/info \
  -H "User-Agent: curl/7.68.0"

# Expected: {"user_id": "default-dev", ...}
```

### 3. Test Complete Flow

```bash
# Send chat completion request through memory proxy
curl http://localhost:8765/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer sk-1234" \
  -H "User-Agent: OpenAIClientImpl/Java unknown" \
  -d '{
    "model": "claude-sonnet-4.5",
    "messages": [{"role": "user", "content": "Hello, remember this: Project X uses Python"}]
  }'

# Make another request - should have memory of first conversation
curl http://localhost:8765/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer sk-1234" \
  -H "User-Agent: OpenAIClientImpl/Java unknown" \
  -d '{
    "model": "claude-sonnet-4.5",
    "messages": [{"role": "user", "content": "What language does Project X use?"}]
  }'
```

### 4. Test Multi-Client Isolation

```bash
# Client A (PyCharm)
curl http://localhost:8765/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer sk-1234" \
  -H "User-Agent: OpenAIClientImpl/Java unknown" \
  -d '{
    "model": "claude-sonnet-4.5",
    "messages": [{"role": "user", "content": "Remember: I prefer tabs over spaces"}]
  }'

# Client B (Custom app with explicit user ID)
curl http://localhost:8765/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer sk-1234" \
  -H "x-memory-user-id: mobile-app" \
  -d '{
    "model": "claude-sonnet-4.5",
    "messages": [{"role": "user", "content": "Do I prefer tabs or spaces?"}]
  }'

# Expected: Client B should not know about Client A's preference
```

## Client Configuration

### PyCharm AI Chat

PyCharm automatically sends `User-Agent: OpenAIClientImpl/Java unknown`. Just configure it to use the memory proxy:

1. Settings → AI Assistant → OpenAI Service
2. Set URL: `http://localhost:8765/v1`
3. Set API Key: `sk-1234` (your litellm master key)

### Custom Applications

Add the `x-memory-user-id` header to explicitly set user ID:

```python
# Python with OpenAI SDK
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8765/v1",
    api_key="sk-1234",
    default_headers={"x-memory-user-id": "my-app-v1"}
)

response = client.chat.completions.create(
    model="claude-sonnet-4.5",
    messages=[{"role": "user", "content": "Hello"}]
)
```

```javascript
// JavaScript/TypeScript
import OpenAI from 'openai';

const client = new OpenAI({
  baseURL: 'http://localhost:8765/v1',
  apiKey: 'sk-1234',
  defaultHeaders: {
    'x-memory-user-id': 'my-app-v1'
  }
});

const response = await client.chat.completions.create({
  model: 'claude-sonnet-4.5',
  messages: [{ role: 'user', content: 'Hello' }]
});
```

## Adding New Client Patterns

To add support for new clients, edit `config.yaml`:

```yaml
user_id_mappings:
  header_patterns:
    # Add new pattern
    - header: "user-agent"
      pattern: "MyApp/\\d+\\.\\d+"  # Regex pattern
      user_id: "myapp-client"

    # Match on different header
    - header: "x-client-id"
      pattern: "frontend-.*"
      user_id: "web-frontend"
```

Patterns use Python regex syntax. Special characters must be escaped (e.g., `\\.` for literal dot).

## Debugging

### Enable Verbose Logging

```bash
# Set log level to DEBUG
export LOG_LEVEL=DEBUG
python litellm_proxy_with_memory.py --port 8765
```

### Check Routing Info

```bash
# See what user ID would be assigned
curl http://localhost:8765/memory-routing/info \
  -H "User-Agent: YourApp/1.0"
```

### View Logs

The proxy logs all routing decisions:

```
2025-10-23 00:09:04 | INFO     | litellm_proxy_with_memory.py:123 | 5c06 MEMORY ROUTING: model=claude-sonnet-4.5, user_id=pycharm-ai-chat
2025-10-23 00:09:04 | INFO     | litellm_proxy_with_memory.py:127 | 5c06 MATCHED PATTERN: user-agent='OpenAIClientImpl/Java unknown' -> pycharm-ai-chat
2025-10-23 00:09:04 | INFO     | litellm_proxy_with_memory.py:135 | 5c06 INJECTED: x-sm-user-id=pycharm-ai-chat
```

## Troubleshooting

### Memory Not Working

1. Check Supermemory API key is set:
   ```bash
   echo $SUPERMEMORY_API_KEY
   ```

2. Verify user ID is being injected:
   ```bash
   curl http://localhost:8765/memory-routing/info -H "User-Agent: YourApp"
   ```

3. Check logs for routing decisions

### Wrong User ID Assigned

1. Check pattern order - first match wins
2. Verify regex pattern:
   ```python
   import re
   pattern = re.compile("YourPattern", re.IGNORECASE)
   print(pattern.search("Your User Agent"))
   ```

### Performance Issues

- Memory routing adds ~1-2ms latency per request
- Consider caching routing decisions if needed
- Use compiled regex patterns (already done)

## Advanced Usage

### Dynamic User ID from Database

```python
from memory_router import MemoryRouter

class DatabaseMemoryRouter(MemoryRouter):
    def detect_user_id(self, headers):
        # Get API key from Authorization header
        auth = headers.get('authorization', '')
        api_key = auth.replace('Bearer ', '')

        # Look up user ID from database
        user_id = your_database.get_user_id(api_key)

        return user_id or super().detect_user_id(headers)
```

### Rate Limiting per User

```python
from collections import defaultdict
import time

class RateLimitedRouter(MemoryRouter):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.request_counts = defaultdict(list)

    def check_rate_limit(self, user_id, max_per_minute=60):
        now = time.time()
        # Clean old entries
        self.request_counts[user_id] = [
            t for t in self.request_counts[user_id]
            if now - t < 60
        ]

        if len(self.request_counts[user_id]) >= max_per_minute:
            raise Exception(f"Rate limit exceeded for {user_id}")

        self.request_counts[user_id].append(now)
```

## License

MIT

## Support

For issues or questions:
1. Check logs with `--log-level DEBUG`
2. Test routing with `/memory-routing/info` endpoint
3. Verify Supermemory API key is valid
