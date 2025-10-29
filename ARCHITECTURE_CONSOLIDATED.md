# LiteLLM Memory Proxy - Consolidated Architecture Documentation

## Project Overview

LiteLLM Memory Proxy is a FastAPI-based proxy layer that adds intelligent memory routing and client detection to LiteLLM. It enables multi-tenant memory isolation using Supermemory API with automatic client detection via User-Agent patterns and custom headers.

### Key Features
- **Automatic Client Detection**: Identifies clients by User-Agent and custom headers
- **Memory Isolation**: Each client gets isolated Supermemory user ID
- **Zero Code Changes**: Works with existing clients (PyCharm AI, Claude Code, etc.)
- **Pattern-Based Routing**: Flexible regex-based header detection
- **External Binary Architecture**: Uses LiteLLM as external process for better isolation

## High-Level Architecture

```
Client (PyCharm/Claude Code/Custom App)
    ↓ User-Agent or x-memory-user-id header
Memory Proxy (Port 8764) - FastAPI
    ↓ Detects client → Injects x-sm-user-id
LiteLLM Binary (Port 8765) - External Process
    ↓ Routes with memory headers
Supermemory API + Provider APIs (OpenAI/Anthropic/Gemini)
```

### Architecture Evolution: SDK to Binary

**Before (SDK-based)**:
- LiteLLM imported as Python SDK
- In-process coupling
- Dependency conflicts
- Harder to scale independently

**After (Binary-based)**:
- LiteLLM runs as external binary process
- Process isolation
- Independent scaling
- No SDK dependencies
- Easier version management

## Detailed Component Architecture

### 1. Memory Proxy Layer (litellm_proxy_with_memory.py)

**Port**: 8764 (configurable)
**Technology**: FastAPI with async/await

**Request Processing Pipeline**:
1. Intercept incoming request
2. Detect client from User-Agent/headers
3. Extract/generate session ID
4. Check rate limits (optional)
5. Retrieve conversation memory from Supermemory
6. Inject memory context and x-sm-user-id header
7. Forward modified request to LiteLLM binary
8. Handle response (streaming/non-streaming)
9. Store response in memory for future context
10. Return to client

**Key Functions**:
- `create_app()` - Factory function with dependency injection
- `proxy_handler()` - Main request forwarding with memory injection
- `get_memory_router()` - DI for router instance
- `get_litellm_base_url()` - DI for LiteLLM URL

### 2. Memory Router (memory_router.py)

**Responsibilities**:
- Configuration loading from YAML
- Header pattern compilation and matching
- User ID detection from multiple sources
- Memory header injection
- Supermemory model detection
- Routing information retrieval

**Key Methods**:
- `detect_user_id(headers)` - Multi-strategy user identification
- `inject_memory_headers(headers, api_key)` - Add x-sm-user-id
- `should_use_supermemory(model_name)` - Check model compatibility
- `get_routing_info(headers)` - Comprehensive routing metadata

**User ID Detection Priority**:
1. Custom header `x-memory-user-id` (highest priority)
2. Pattern matching on headers (User-Agent, etc.)
3. Default user ID from config (fallback)

### 3. LiteLLM Binary

**Port**: 8765 (configurable)
**Launch**: Via subprocess in start_proxies.py

**Responsibilities**:
- Model routing to provider APIs
- API authentication
- Request/response handling
- Streaming support

### 4. Process Manager (start_proxies.py)

**Responsibilities**:
- Launch LiteLLM binary subprocess
- Start Memory Proxy FastAPI app
- Coordinate both processes
- Handle graceful shutdown

## Data Flow Sequence

### Complete Request Flow

1. **Client → Memory Proxy**
   - HTTP request with headers (User-Agent, Authorization, etc.)
   - Request body with model and messages

2. **Memory Proxy: Client Detection**
   - Parse headers
   - Match against configured patterns
   - Determine user_id (e.g., 'pycharm-ai-chat')

3. **Memory Proxy: Memory Retrieval** (if Supermemory model)
   - Check if model uses Supermemory API
   - Retrieve conversation history for user_id
   - Build context messages from history

4. **Memory Proxy: Request Transformation**
   - Inject `x-sm-user-id` header
   - Add Supermemory API key if configured
   - Preserve all original headers
   - Modify request body if needed

5. **Memory Proxy → LiteLLM Binary**
   - Forward via HTTP POST
   - Include all transformed headers
   - Send modified body

6. **LiteLLM Binary → Provider API**
   - Route based on model name in config
   - Handle provider authentication
   - Forward to OpenAI/Anthropic/Gemini/etc.

7. **Provider API → LiteLLM Binary**
   - Return response (streaming or complete)
   - Handle errors

8. **LiteLLM Binary → Memory Proxy**
   - Forward response
   - Maintain streaming if enabled

9. **Memory Proxy: Response Storage**
   - Extract assistant message
   - Store in Supermemory for context
   - Update session state

10. **Memory Proxy → Client**
    - Return response
    - Preserve streaming format
    - Return proper status codes

## Configuration Architecture

### Configuration Files

**config.yaml** - Main configuration:
```yaml
model_list:
  - model_name: claude-sonnet-4.5
    litellm_params:
      api_base: https://api.supermemory.ai/v3/api.anthropic.com
      model: anthropic/claude-sonnet-4-5-20250929
      api_key: os.environ/ANTHROPIC_API_KEY

user_id_mappings:
  custom_header: "x-memory-user-id"
  header_patterns:
    - header: "user-agent"
      pattern: "OpenAIClientImpl/Java"
      user_id: "pycharm-ai"
    - header: "user-agent"
      pattern: "Claude Code"
      user_id: "claude-cli"
  default_user_id: "default-dev"
```

**Environment Variables** (.env):
- `OPENAI_API_KEY` - OpenAI authentication
- `ANTHROPIC_API_KEY` - Anthropic authentication
- `SUPERMEMORY_API_KEY` - Supermemory authentication
- `LITELLM_BASE_URL` - LiteLLM binary URL (default: http://localhost:8765)
- `ENABLE_RATE_LIMITING` - Enable per-client rate limits

### Configuration Priority
Command-Line Args > Environment Variables > config.yaml > Defaults

## Project Structure

```
litellm/
├── config.yaml                      # Model and routing configuration
├── .env                             # API keys and environment vars
├── src/proxy/
│   ├── litellm_proxy_with_memory.py # Memory routing proxy (FastAPI)
│   ├── memory_router.py             # Client detection logic
│   └── litellm_proxy.py             # Alternative proxy implementation
├── deploy/
│   └── start_proxies.py             # Process manager
├── tests/
│   ├── test_memory_proxy.py         # Memory proxy tests
│   ├── test_memory_routing.py       # Routing logic tests
│   └── test_litellm_proxy_refactored.py
├── docs/
│   ├── INDEX.md
│   ├── architecture/OVERVIEW.md
│   ├── getting-started/
│   │   ├── QUICKSTART.md
│   │   └── TUTORIAL.md
│   ├── guides/
│   │   ├── migration/MIGRATION_GUIDE.md
│   │   ├── refactoring/REFACTORING_GUIDE.md
│   │   └── testing/TESTING_GUIDE.md
│   └── reference/CONFIGURATION.md
├── README.md
├── MEMORY_ROUTING_README.md
└── pyproject.toml
```

## Key Benefits

1. **Process Isolation**: Memory proxy and LiteLLM run independently
2. **Multi-Tenant Memory**: Each client has isolated conversation history
3. **Zero Client Changes**: Automatic detection via existing headers
4. **Flexible Patterns**: Regex-based client identification
5. **Easy Deployment**: External binary approach simplifies updates
6. **Better Debugging**: Clear separation of concerns
7. **Independent Scaling**: Scale proxies separately

## Deployment Patterns

### Local Development
```
├── LiteLLM Binary (port 8765)
├── Memory Proxy (port 8764)
└── Local environment variables
```

### Production with Load Balancer
```
Load Balancer
    ↓
Multiple Memory Proxy Instances (8764)
    ↓
Shared LiteLLM Binary (8765)
    ↓
Shared Redis for session state
```

## Usage Examples

### Starting the Proxies

```bash
# Option 1: Use start script
python deploy/start_proxies.py

# Option 2: Manual start
# Terminal 1: LiteLLM binary
litellm --config config.yaml --port 8765

# Terminal 2: Memory proxy
python src/proxy/litellm_proxy_with_memory.py --port 8764 --litellm-url http://localhost:8765
```

### Client Configuration

**PyCharm AI Assistant**:
1. Settings → AI Assistant → OpenAI Service
2. URL: `http://localhost:8764/v1`
3. API Key: Your LiteLLM master key

**Python with OpenAI SDK**:
```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8764/v1",
    api_key="sk-1234",
    default_headers={"x-memory-user-id": "my-app"}
)

response = client.chat.completions.create(
    model="claude-sonnet-4.5",
    messages=[{"role": "user", "content": "Hello"}]
)
```

### Testing Routing

```bash
# Check what user ID would be assigned
curl http://localhost:8764/memory-routing/info \
  -H "User-Agent: OpenAIClientImpl/Java unknown"

# Response: {"user_id": "pycharm-ai", ...}

# Test with custom header
curl http://localhost:8764/memory-routing/info \
  -H "x-memory-user-id: my-project"

# Response: {"user_id": "my-project", ...}
```

## Performance Characteristics

- **Latency Overhead**: ~1-2ms per request for routing logic
- **Async I/O**: Non-blocking operations throughout
- **Connection Pooling**: HTTP connection reuse to LiteLLM
- **Memory Efficiency**: Compiled regex patterns cached
- **Scalability**: Horizontal scaling via load balancer + shared Redis

## Security

- **API Key Validation**: Master key authentication required
- **Header Sanitization**: Input validation on all headers
- **Injection Protection**: Safe header manipulation
- **Environment-Based Secrets**: API keys from environment variables
- **Rate Limiting**: Optional per-client rate limits

## Monitoring and Debugging

### Logging
- Structured JSON logging available
- Request tracing with unique IDs
- User ID detection logged for each request
- Memory injection logged

### Health Endpoints
- `/health` - Basic health check
- `/memory-routing/info` - Debug routing information

### Debug Mode
```bash
export LOG_LEVEL=DEBUG
python src/proxy/litellm_proxy_with_memory.py
```

## Extension Points

### Adding New Client Patterns
Edit config.yaml:
```yaml
user_id_mappings:
  header_patterns:
    - header: "user-agent"
      pattern: "MyApp/.*"
      user_id: "myapp-client"
```

### Custom User ID Detection
Extend MemoryRouter class:
```python
class CustomRouter(MemoryRouter):
    def detect_user_id(self, headers):
        # Custom logic here
        api_key = headers.get('authorization', '').replace('Bearer ', '')
        user_id = database.lookup_user(api_key)
        return user_id or super().detect_user_id(headers)
```

### Adding Rate Limiting
```python
from collections import defaultdict
import time

class RateLimitedRouter(MemoryRouter):
    def check_rate_limit(self, user_id, max_per_minute=60):
        # Implementation
        pass
```

## Recent Changes (Last 2 Days)

Files modified in last 2 days include:
- Documentation updates (README.md, MEMORY_ROUTING_README.md)
- Setup scripts (PYCHARM_ENV_LAUNCHER_README.md, SETUP_SUMMARY.md)
- All documentation files in docs/ directory
- Test files (test_memory_proxy.py, test_memory_routing.py)
- Core proxy files (litellm_proxy_with_memory.py, memory_router.py)
- Poetry configuration templates

## Related Documentation

- Quick Start: docs/getting-started/QUICKSTART.md
- Tutorial: docs/getting-started/TUTORIAL.md  
- Migration Guide: docs/guides/migration/MIGRATION_GUIDE.md
- Refactoring Guide: docs/guides/refactoring/REFACTORING_GUIDE.md
- Testing Guide: docs/guides/testing/TESTING_GUIDE.md
- Configuration Reference: docs/reference/CONFIGURATION.md

---

**Created**: 2025-10-31
**Project**: LiteLLM Memory Proxy
**Repository**: https://github.com/zeddq/litellm
**Last Updated**: Files modified within last 2 days
