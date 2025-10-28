# LiteLLM Memory Proxy - Architecture Overview

Comprehensive architectural documentation for LiteLLM Memory Proxy including design evolution and implementation details.

---

## High-Level Architecture

This project uses an **external LiteLLM binary** approach instead of SDK imports for better separation of concerns and easier deployment:

```
┌─────────────────────────────────────────────────────┐
│ CLIENT (OpenAI SDK, Anthropic SDK, curl, etc.)     │
└─────────────────┬───────────────────────────────────┘
                  │ HTTP/HTTPS
                  ▼
┌─────────────────────────────────────────────────────┐
│ Memory Proxy (Port 8764) - FastAPI Application     │
│ • Client Detection via User-Agent patterns         │
│ • Dynamic x-sm-user-id injection                   │
│ • HTTP request forwarding                          │
└─────────────────┬───────────────────────────────────┘
                  │ HTTP
                  ▼
┌─────────────────────────────────────────────────────┐
│ LiteLLM Binary Process (Port 8765)                 │
│ External process: litellm --config config.yaml     │
└─────────────────┬───────────────────────────────────┘
                  │
         ┌────────┴────────┬──────────────┐
         ▼                 ▼              ▼
   ┌─────────┐      ┌──────────┐   ┌──────────┐
   │ OpenAI  │      │ Anthropic│   │  Gemini  │
   │   API   │      │   API    │   │   API    │
   └─────────┘      └──────────┘   └──────────┘
```

---

## Detailed Component Architecture

### Memory-Enabled Proxy Layer

```
┌─────────────────────────────────────────────────────────┐
│              Memory-Enabled Proxy Layer                  │
│  ┌────────────────────────────────────────────────────┐ │
│  │  Request Processing Pipeline:                      │ │
│  │  1. Intercept request                              │ │
│  │  2. Detect client (User-Agent, headers)            │ │
│  │  3. Extract/generate session ID                    │ │
│  │  4. Check rate limits                              │ │
│  │  5. Retrieve conversation memory                   │ │
│  │  6. Inject context into request                    │ │
│  │  7. Forward to LiteLLM                             │ │
│  │  8. Handle response (streaming/non-streaming)      │ │
│  │  9. Store response in memory                       │ │
│  │ 10. Return to client                               │ │
│  └────────────────────────────────────────────────────┘ │
└────────────────────┬────────────────────────────────────┘
                     │
        ┌────────────┴────────────┐
        │                         │
        ▼                         ▼
┌──────────────┐         ┌──────────────┐
│  LiteLLM     │         │ Memory Store │
│  Router      │         │              │
│              │         │ Options:     │
│ Providers:   │         │ • InMemory   │
│ • OpenAI     │         │ • Redis      │
│ • Anthropic  │         │ • PostgreSQL │
│ • Gemini     │         │              │
│ • etc.       │         │ Features:    │
└──────────────┘         │ • Sessions   │
                         │ • TTL        │
                         │ • Cleanup    │
                         └──────────────┘
```

---

## Architecture Evolution: SDK to Binary

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

## FastAPI Application Architecture

### Before Refactoring (Global State)

```
┌────────────────────────────────────────┐
│ Module Level (Global Scope)           │
│                                        │
│  ┌──────────────┐  ┌─────────────┐   │
│  │ app          │  │ memory_      │   │
│  │ (FastAPI)    │  │ router       │   │
│  └──────┬───────┘  └──────┬──────┘   │
│         │                  │           │
│         │  @app.on_event   │           │
│         │    ("startup")   │           │
│         └──────────────────┘           │
│                  │                     │
│                  ▼                     │
│         ┌────────────────┐            │
│         │ startup_event()│            │
│         │ global router  │            │
│         └────────────────┘            │
│                                        │
│  Routes directly access global vars   │
└────────────────────────────────────────┘
```

### After Refactoring (Dependency Injection)

```
┌───────────────────────────────────────────────────┐
│ Module Level                                      │
│                                                   │
│  ┌─────────────────────────────────────────────┐│
│  │ create_app(router, base_url) -> FastAPI    ││
│  │                                             ││
│  │  Creates app with:                          ││
│  │  - lifespan context manager                 ││
│  │  - app.state.memory_router = router         ││
│  │  - app.state.litellm_base_url = base_url    ││
│  │  - route handlers with DI                   ││
│  └──────────────────┬──────────────────────────┘│
│                     │                            │
│                     ▼                            │
│  ┌──────────────────────────────────┐           │
│  │ Dependency Injection Functions   │           │
│  │                                  │           │
│  │ get_memory_router(request)      │           │
│  │ get_litellm_base_url(request)   │           │
│  │                                  │           │
│  │ Returns from app.state          │           │
│  └──────────────────┬───────────────┘           │
│                     │                            │
│                     ▼                            │
│  ┌──────────────────────────────────┐           │
│  │ Route Handlers                   │           │
│  │                                  │           │
│  │ Use Depends() to get:           │           │
│  │ - memory_router                  │           │
│  │ - litellm_base_url               │           │
│  │                                  │           │
│  │ No global access!                │           │
│  └──────────────────────────────────┘           │
│                                                   │
│  No global state - everything explicit          │
└───────────────────────────────────────────────────┘
```

---

## Project Structure

```
litellm/
├── config.yaml                      # LiteLLM and routing configuration
├── litellm_proxy_with_memory.py     # Memory routing proxy (FastAPI)
├── memory_router.py                 # Client detection and routing logic
├── start_proxies.py                 # Launch script for both proxies
├── tutorial_proxy_with_memory.py    # Comprehensive tutorial code
├── example_complete_workflow.py     # Usage examples
├── test_tutorial.py                 # Test suite
└── docs/                            # Consolidated documentation
    ├── getting-started/
    │   ├── QUICKSTART.md
    │   └── TUTORIAL.md
    ├── architecture/
    │   └── OVERVIEW.md
    ├── guides/
    │   ├── testing/
    │   │   └── TESTING_GUIDE.md
    │   ├── migration/
    │   │   └── MIGRATION_GUIDE.md
    │   └── refactoring/
    │       └── REFACTORING_GUIDE.md
    ├── reference/
    │   └── CONFIGURATION.md
    └── INDEX.md
```

---

## Key Components

### 1. Memory Router (`memory_router.py`)

**Responsibilities:**
- Configuration loading and management
- Header pattern matching and compilation
- User ID detection from various sources
- Memory header injection
- Supermemory model detection
- Routing information retrieval

**Key Methods:**
- `detect_user_id(headers)` - Identify user from request headers
- `inject_memory_headers(headers, api_key)` - Add memory-related headers
- `should_use_supermemory(model_name)` - Check if model uses Supermemory
- `get_routing_info(headers)` - Get comprehensive routing information

### 2. Memory Proxy (`litellm_proxy_with_memory.py`)

**Responsibilities:**
- FastAPI application creation and configuration
- Request interception and forwarding
- Memory context injection
- Response handling (streaming and non-streaming)
- Health and debug endpoints

**Key Functions:**
- `create_app()` - Factory function for FastAPI app
- `proxy_handler()` - Main request forwarding logic
- `get_memory_router()` - Dependency injection for router
- `get_litellm_base_url()` - Dependency injection for base URL

### 3. Process Manager (`start_proxies.py`)

**Responsibilities:**
- Launch LiteLLM binary process
- Start Memory Proxy
- Coordinate both proxies
- Handle process lifecycle

**Key Functions:**
- `start_litellm_proxy()` - Launch LiteLLM binary
- `start_memory_proxy()` - Start Memory Proxy
- `main()` - Orchestrate startup

---

## Data Flow

### Request Flow with Memory Routing

```
1. Client → Memory Proxy
   • HTTP request with headers
   • Contains User-Agent, session ID, etc.

2. Memory Proxy: Client Detection
   • Extract headers
   • Match User-Agent patterns
   • Determine user ID

3. Memory Proxy: Memory Retrieval
   • Check if model uses Supermemory
   • Retrieve conversation history
   • Build context messages

4. Memory Proxy: Request Transformation
   • Inject memory headers (x-sm-user-id)
   • Add Supermemory API key if configured
   • Preserve original headers

5. Memory Proxy → LiteLLM Binary
   • Forward modified request
   • Include all headers and body

6. LiteLLM Binary → Provider API
   • Route based on model name
   • Handle authentication
   • Forward to appropriate provider

7. Provider API → LiteLLM Binary
   • Return response
   • Handle streaming if enabled

8. LiteLLM Binary → Memory Proxy
   • Forward response
   • Maintain streaming state

9. Memory Proxy: Response Storage
   • Extract response content
   • Store in memory for context
   • Update session

10. Memory Proxy → Client
    • Return response
    • Preserve streaming format
```

---

## Key Benefits of Binary Approach

1. **Separation of Concerns**: Memory routing separate from LiteLLM
2. **Independent Scaling**: Scale proxies independently
3. **Version Management**: Upgrade LiteLLM without code changes
4. **Simplified Dependencies**: No SDK conflicts
5. **Production Ready**: Process isolation and better error handling
6. **Better Isolation**: Each component runs in separate process
7. **Easier Debugging**: Clear separation of concerns

---

## Configuration Architecture

### Configuration Layers

1. **Environment Variables** (`.env`)
   - API keys (OPENAI_API_KEY, ANTHROPIC_API_KEY)
   - Infrastructure (REDIS_URL, LITELLM_BASE_URL)
   - Feature flags (ENABLE_RATE_LIMITING)

2. **Configuration File** (`config.yaml`)
   - Model definitions and providers
   - User ID mapping patterns
   - LiteLLM-specific settings

3. **Command-Line Arguments**
   - Port configuration
   - Config file path
   - Runtime overrides

### Configuration Priority

```
Command-Line Args > Environment Variables > config.yaml > Defaults
```

---

## Security Architecture

### Multi-Layer Security

1. **API Key Validation**
   - Master key authentication
   - Per-model API keys
   - Secure storage in environment variables

2. **Rate Limiting**
   - Token bucket algorithm
   - Per-client limits
   - Configurable thresholds

3. **Header Validation**
   - Input sanitization
   - Pattern validation
   - Header injection protection

4. **Network Security**
   - HTTPS support
   - Reverse proxy compatibility
   - CORS configuration

---

## Performance Architecture

### Optimization Strategies

1. **Async I/O**
   - FastAPI async routes
   - httpx async client
   - Non-blocking operations

2. **Connection Pooling**
   - HTTP connection reuse
   - Redis connection pooling
   - Efficient resource management

3. **Memory Management**
   - Configurable context window
   - TTL-based cleanup
   - In-memory vs persistent storage options

4. **Caching**
   - Pattern compilation caching
   - LiteLLM client cache
   - Configuration caching

---

## Scalability Architecture

### Horizontal Scaling

```
┌─────────┐     ┌─────────┐     ┌─────────┐
│ Memory  │     │ Memory  │     │ Memory  │
│ Proxy 1 │     │ Proxy 2 │     │ Proxy N │
└────┬────┘     └────┬────┘     └────┬────┘
     │               │               │
     └───────────────┴───────────────┘
                     │
          ┌──────────┴──────────┐
          │                     │
          ▼                     ▼
    ┌──────────┐         ┌──────────┐
    │ LiteLLM  │         │  Redis   │
    │ (Shared) │         │ (Shared) │
    └──────────┘         └──────────┘
```

**Requirements for Horizontal Scaling:**
- Use Redis for shared session state
- Load balancer (nginx, HAProxy)
- Sticky sessions or session affinity

### Vertical Scaling

- Increase CPU cores for parallel request handling
- Increase memory for larger in-memory cache
- Tune async worker configuration
- Optimize connection pool sizes

---

## Monitoring Architecture

### Observability Components

1. **Structured Logging**
   - JSON format for aggregation
   - Request tracing with IDs
   - Performance metrics
   - Error tracking

2. **Health Endpoints**
   - `/health` - Basic health check
   - `/memory-routing/info` - Debug routing information

3. **Metrics Collection**
   - Request rate and latency
   - Error rates by endpoint
   - Memory usage and session counts
   - Rate limit violations

4. **Integration Points**
   - ELK Stack (Elasticsearch, Logstash, Kibana)
   - Datadog
   - CloudWatch
   - Prometheus + Grafana

---

## Deployment Architecture

### Local Development

```
Developer Machine
├── LiteLLM Binary (port 8765)
├── Memory Proxy (port 8764)
└── Local Redis (optional)
```

### Production Deployment

```
┌─────────────────────────────────┐
│        Load Balancer            │
└──────────┬──────────────────────┘
           │
    ┌──────┴──────┬──────────┐
    ▼             ▼          ▼
┌────────┐   ┌────────┐  ┌────────┐
│ Proxy1 │   │ Proxy2 │  │ ProxyN │
└───┬────┘   └───┬────┘  └───┬────┘
    │            │           │
    └────────────┴───────────┘
                 │
         ┌───────┴────────┐
         ▼                ▼
    ┌─────────┐      ┌────────┐
    │ LiteLLM │      │ Redis  │
    │ Binary  │      │Cluster │
    └─────────┘      └────────┘
```

---

## Extension Points

### Adding New Providers

1. Add model configuration to `config.yaml`
2. LiteLLM handles provider routing automatically
3. No code changes required

### Adding New Storage Backends

1. Implement `MemoryStore` interface
2. Add to `MemoryManager` initialization
3. Configure via environment variables

### Adding New Client Detection Patterns

1. Add pattern to `config.yaml` under `user_id_mappings`
2. Patterns are regex-based for flexibility
3. No code changes required

---

## Related Documentation

- [Quick Start Guide](../getting-started/QUICKSTART.md)
- [Tutorial Guide](../getting-started/TUTORIAL.md)
- [Migration Guide](../guides/migration/MIGRATION_GUIDE.md)
- [Refactoring Guide](../guides/refactoring/REFACTORING_GUIDE.md)
- [Testing Guide](../guides/testing/TESTING_GUIDE.md)

---

**Sources**: README.md, BEFORE_AFTER_COMPARISON.md, MIGRATION_GUIDE.md
**Created**: 2025-10-24
**Updated**: 2025-10-24
