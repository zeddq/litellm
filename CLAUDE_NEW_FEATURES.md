# New Features Documentation (to be integrated into CLAUDE.md)

## 🔥 NEW FEATURES

### 1. PyCharm/IDE Interceptor Proxy

**Location**: `src/interceptor/`

The interceptor is a FastAPI-based proxy that sits between PyCharm AI Assistant (or other JetBrains IDEs) and the Memory Proxy. It provides:

#### Features
- **Automatic Port Management**: Per-project port registry prevents conflicts when running multiple projects
- **Header Injection**: Automatically adds `x-memory-user-id` and `x-pycharm-instance` headers
- **Instance Identification**: Each project gets a unique identifier (e.g., `pycharm-litellm`)
- **Streaming Support**: Handles both streaming and non-streaming responses
- **CLI Management**: Full command-line interface for port management

#### Quick Start

```bash
# Run interceptor (auto-assigns port from registry)
cd /your/project
python -m src.interceptor.cli run

# View port assignments
python -m src.interceptor.cli list

# Check which port your project uses
python -m src.interceptor.cli show

# Manage ports
python -m src.interceptor.cli allocate /path/to/project
python -m src.interceptor.cli remove /path/to/project
```

#### PyCharm Configuration

1. Settings → Tools → AI Assistant → OpenAI Service
2. URL: `http://localhost:8888` (or your assigned port)
3. API Key: `sk-1234` (from config.yaml)
4. Model: `claude-sonnet-4.5`

#### Port Registry

The interceptor uses a persistent port registry at `~/.config/litellm/port_registry.json`:
- **Port Range**: 8888-9999 (configurable)
- **Automatic Assignment**: Each project gets a consistent port
- **Conflict Prevention**: File locking prevents race conditions
- **Persistence**: Port assignments survive across sessions

#### ⚠️ CRITICAL KNOWN ISSUE

**Interceptors are NOT hardened and will CRASH when used with supermemory-proxied endpoints.**

**Do NOT use**:
```yaml
model_list:
  - model_name: claude-sonnet-4.5
    litellm_params:
      api_base: https://api.supermemory.ai/v3/api.anthropic.com  # ❌ WILL CRASH WITH INTERCEPTOR
```

**Workaround**: Until this issue is resolved:
1. Use interceptors only with direct provider endpoints (no supermemory proxy)
2. OR use Memory Proxy directly without interceptor
3. OR use LiteLLM binary directly

**Status**: Under active investigation. Issue tracked in `src/interceptor/README.md`.

#### Architecture with Interceptor

```
┌──────────────────────┐
│ PyCharm AI Assistant │
└──────────┬───────────┘
           │ http://localhost:8888
           ▼
┌────────────────────────────────┐
│ Interceptor (Port 8888)        │
│ • Adds x-memory-user-id header │
│ • Adds x-pycharm-instance      │
└──────────┬─────────────────────┘
           │ http://localhost:8764
           ▼
┌────────────────────────────────┐
│ Memory Proxy (Port 8764)       │
│ • Client detection             │
│ • Memory routing               │
└──────────┬─────────────────────┘
           │ http://localhost:8765
           ▼
┌────────────────────────────────┐
│ LiteLLM Binary (Port 8765)     │
└────────────────────────────────┘
```

**Full Documentation**: `src/interceptor/README.md`

---

### 2. Context Retrieval from Supermemory

**Location**: `src/proxy/context_retriever.py`

Automatic retrieval and injection of relevant context from Supermemory into LLM prompts.

#### Features
- **Intelligent Query Extraction**: Multiple strategies (last_user, first_user, all_user, last_assistant)
- **Flexible Injection**: System message, user prefix, or user suffix
- **Model Filtering**: Whitelist or blacklist specific models
- **Configurable**: Max context length, results, timeout, container tags
- **Per-Model Control**: Enable/disable for specific models

#### Configuration

Add to `config/config.yaml`:

```yaml
context_retrieval:
  enabled: true
  api_key: os.environ/SUPERMEMORY_API_KEY
  base_url: https://api.supermemory.ai  # Optional

  # Query extraction strategy
  query_strategy: last_user  # last_user, first_user, all_user, last_assistant

  # Context injection strategy
  injection_strategy: system  # system, user_prefix, user_suffix

  # Container and limits
  container_tag: supermemory
  max_context_length: 4000
  max_results: 5
  timeout: 10.0

  # Model filtering (pick ONE)
  enabled_for_models:  # Whitelist
    - claude-sonnet-4.5
    - claude-haiku-4.5

  # OR

  disabled_for_models:  # Blacklist
    - gpt-3.5-turbo
```

#### How It Works

1. **Query Extraction**: Extracts search query from user messages based on `query_strategy`
2. **Context Retrieval**: Queries Supermemory `/v4/profile` endpoint
3. **Context Injection**: Injects retrieved context based on `injection_strategy`
4. **Request Processing**: Forwards enhanced request to LiteLLM

#### Query Strategies

- **`last_user`** (default): Use only the last user message
  - Best for: Follow-up questions, specific queries
  - Example: User asks "What was the bug in auth module?" → Query: "What was the bug in auth module?"

- **`first_user`**: Use only the first user message
  - Best for: Maintaining original context throughout conversation
  - Example: First message sets topic, subsequent messages build on it

- **`all_user`**: Concatenate all user messages
  - Best for: Complex multi-turn conversations
  - Example: "How do I deploy?" + "What about scaling?" → Query: "How do I deploy? | What about scaling?"

- **`last_assistant`**: Use last assistant message
  - Best for: Context-aware follow-ups
  - Example: AI says "I've explained deployment" → Query uses that for context

#### Injection Strategies

- **`system`** (default, recommended): Add as system message at start
  ```
  [System]: Retrieved context: ...
  [User]: My question
  ```
  - ✅ Best for models with system message support (Claude, GPT-4)
  - ✅ Clear separation of context from user content

- **`user_prefix`**: Prepend to first user message
  ```
  [User]: [Context: ...] My question
  ```
  - ✅ Works with models without system messages
  - ⚠️ Context mixed with user content

- **`user_suffix`**: Append to last user message
  ```
  [User]: My question [Context: ...]
  ```
  - ✅ Emphasizes recent context
  - ⚠️ May be less effective for some models

#### Example: Enable for Specific Models Only

```yaml
context_retrieval:
  enabled: true
  api_key: os.environ/SUPERMEMORY_API_KEY

  # Only Claude models get context
  enabled_for_models:
    - claude-sonnet-4.5
    - claude-haiku-4.5
    - claude-opus-4

  # GPT models don't use context retrieval
  # (implicitly disabled)
```

#### Testing

```bash
# Run context retrieval tests
poetry run pytest tests/test_context_retrieval.py -v

# Test with real API
export SUPERMEMORY_API_KEY="sm_..."
curl http://localhost:8764/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer sk-1234" \
  -d '{
    "model": "claude-sonnet-4.5",
    "messages": [{"role": "user", "content": "Tell me about the litellm project"}]
  }'
```

**Full Documentation**: `docs/guides/CONFIGURATION.md` (Context Retrieval section)

---

### 3. Enhanced Project Structure

The project has been reorganized for better maintainability:

#### Before
```
litellm/
├── config.yaml
├── litellm_proxy_with_memory.py
├── memory_router.py
└── test files...
```

#### After
```
litellm/
├── config/              # Configuration files
├── src/
│   ├── interceptor/     # 🔥 NEW: Interceptor proxy
│   ├── proxy/           # Core proxy components
│   └── integrations/    # External integrations
├── tests/               # Organized test suite
├── deploy/              # Deployment configs
└── docs/                # Comprehensive documentation
```

#### Benefits
- **Logical Grouping**: Related files are together
- **Scalability**: Easy to add new modules
- **Clear Separation**: Core vs. deployment vs. tests
- **Import Clarity**: `from proxy.memory_router import ...`

---

## Updated Architecture Diagram

```
┌─────────────────────────────────────────────┐
│ AI Clients                                  │
│ (PyCharm, Claude Code, VS Code, curl)      │
└─────────────────┬───────────────────────────┘
                  │
     ┌────────────┴────────────┐
     │                         │
     ▼ (PyCharm)               ▼ (Others)
┌──────────────┐    ┌──────────────────────┐
│ Interceptor  │    │ Direct Connection    │
│ (Port 8888+) │    │                      │
└──────┬───────┘    └──────┬───────────────┘
       │                   │
       │  + x-memory-user-id
       │  + x-pycharm-instance
       │                   │
       └────────┬──────────┘
                ▼
┌─────────────────────────────────────────────┐
│ Memory Proxy (Port 8764) - FastAPI         │
│ • Client detection (User-Agent)            │
│ • Context retrieval (Supermemory)          │ 🔥 NEW
│ • Header injection (x-sm-user-id)          │
│ • Request forwarding                        │
└─────────────────┬───────────────────────────┘
                  │ HTTP forward
                  ▼
┌─────────────────────────────────────────────┐
│ LiteLLM Binary (Port 8765)                 │
│ External process: litellm --config ...     │
└─────────────────┬───────────────────────────┘
                  │
         ┌────────┴────────┬──────────┐
         ▼                 ▼          ▼
   ┌─────────┐      ┌──────────┐  ┌────────┐
   │ OpenAI  │      │Supermemory│  │ Gemini │
   │   API   │      │  + Claude │  │  API   │
   └─────────┘      └──────────┘  └────────┘
```

---

## New Test Files

### `tests/test_context_retrieval.py`
Comprehensive tests for context retrieval feature:
- Query strategy tests
- Injection strategy tests
- Model filtering tests
- Error handling tests
- Integration tests with mock Supermemory API

### `tests/test_error_handlers.py`
Error handling and recovery tests:
- HTTP error responses
- Timeout handling
- API error propagation
- User-friendly error messages

---

## Development Workflow Updates

### Using the Interceptor

When developing features that need PyCharm testing:

```bash
# Terminal 1: Start main proxies
poetry run start-proxies

# Terminal 2: Start interceptor for this project
python -m src.interceptor.cli run

# Configure PyCharm to use http://localhost:8888
```

### Testing Context Retrieval

```bash
# Add configuration
vim config/config.yaml  # Add context_retrieval section

# Set API key
export SUPERMEMORY_API_KEY="sm_..."

# Run tests
poetry run pytest tests/test_context_retrieval.py -v

# Test manually
curl http://localhost:8764/v1/chat/completions \
  -H "Authorization: Bearer sk-1234" \
  -d '{"model": "claude-sonnet-4.5", "messages": [...]}'
```

### Common Development Tasks

#### Add New Model with Context Retrieval

```yaml
model_list:
  - model_name: my-model
    litellm_params:
      model: provider/my-model
      api_key: os.environ/MY_API_KEY

context_retrieval:
  enabled: true
  enabled_for_models:
    - my-model  # Add to whitelist
```

#### Debug Interceptor Port Issues

```bash
# Check current assignments
python -m src.interceptor.cli list

# Remove stale mapping
python -m src.interceptor.cli remove

# Manually allocate
python -m src.interceptor.cli allocate /path/to/project
```

---

## Configuration Updates

### Complete config.yaml Example with New Features

```yaml
general_settings:
  master_key: sk-1234

model_list:
  - model_name: claude-sonnet-4.5
    litellm_params:
      model: anthropic/claude-sonnet-4-5-20250929
      api_key: os.environ/ANTHROPIC_API_KEY

user_id_mappings:
  custom_header: "x-memory-user-id"
  header_patterns:
    - header: "user-agent"
      pattern: "OpenAIClientImpl/Java"
      user_id: "pycharm-ai"
  default_user_id: "default-dev"

# 🔥 NEW: Context Retrieval Configuration
context_retrieval:
  enabled: true
  api_key: os.environ/SUPERMEMORY_API_KEY
  query_strategy: last_user
  injection_strategy: system
  container_tag: supermemory
  max_context_length: 4000
  max_results: 5
  enabled_for_models:
    - claude-sonnet-4.5

litellm_settings:
  set_verbose: true
  json_logs: true
```

---

## Troubleshooting New Features

### Interceptor Issues

**Problem**: Interceptor crashes with supermemory endpoint
```
Error: Connection reset by peer
```

**Solution**: This is a known issue. Use direct proxy or non-supermemory endpoints.

**Problem**: Port already in use
```bash
# Check what's using the port
lsof -i :8888

# Get a new port
python -m src.interceptor.cli remove
python -m src.interceptor.cli show  # Will assign new port
```

### Context Retrieval Issues

**Problem**: No context being retrieved
```
Check:
1. context_retrieval.enabled = true
2. SUPERMEMORY_API_KEY is set
3. Model is in enabled_for_models (or not in disabled_for_models)
4. Supermemory API is accessible
```

**Problem**: Context too large
```yaml
context_retrieval:
  max_context_length: 2000  # Reduce from 4000
  max_results: 3  # Reduce from 5
```

---

## File Location Reference

| Component | Old Location | New Location |
|-----------|--------------|--------------|
| Main config | `config.yaml` | `config/config.yaml` |
| Memory router | `memory_router.py` | `src/proxy/memory_router.py` |
| Main proxy | `litellm_proxy_with_memory.py` | `src/proxy/litellm_proxy_sdk.py` |
| Tests | Root directory | `tests/` directory |
| Examples | Root directory | `src/example_complete_workflow.py` |

---

## Next Steps

1. **Read Full Docs**:
   - `src/interceptor/README.md` - Comprehensive interceptor documentation
   - `docs/guides/CONFIGURATION.md` - Complete configuration reference
   - `docs/troubleshooting/COMMON_ISSUES.md` - Troubleshooting guide

2. **Try New Features**:
   ```bash
   # Enable context retrieval
   vim config/config.yaml

   # Test it
   poetry run start-proxies
   curl http://localhost:8764/v1/chat/completions ...
   ```

3. **Set Up Interceptor** (for PyCharm users):
   ```bash
   python -m src.interceptor.cli run
   # Configure PyCharm: http://localhost:8888
   ```

4. **Run Tests**:
   ```bash
   ./RUN_TESTS.sh all
   ```