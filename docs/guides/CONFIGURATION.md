# Configuration Guide

Complete configuration reference for LiteLLM Memory Proxy.

---

## Table of Contents

1. [Environment Variables](#environment-variables)
2. [Configuration File Structure](#configuration-file-structure)
3. [Configuration Sections](#configuration-sections)
4. [Configuration Examples](#configuration-examples)
5. [Configuration Schema](#configuration-schema)
6. [Validation](#validation)
7. [Troubleshooting](#troubleshooting)

---

## Environment Variables

### Required Variables

```bash
# At least one provider API key is required
OPENAI_API_KEY=sk-...
# OR
ANTHROPIC_API_KEY=sk-ant-...
```

### Optional Variables

#### API Keys
```bash
# Anthropic API Key (for Claude models)
ANTHROPIC_API_KEY=sk-ant-...

# Supermemory API Key (for memory features)
SUPERMEMORY_API_KEY=sm_...

# Gemini API Key
GEMINI_API_KEY=...
```

#### Infrastructure
```bash
# Database URL (for SDK persistence)
DATABASE_URL=postgresql://user:pass@localhost:5432/litellm

# Redis URL for caching
REDIS_URL=redis://localhost:6379/0
REDIS_PASSWORD=your-redis-password

# LiteLLM base URL (for binary proxy mode)
LITELLM_BASE_URL=http://localhost:4000
```

#### Proxy Configuration
```bash
# Configuration file path
LITELLM_CONFIG=./config.yaml

# Proxy host and port
PROXY_HOST=0.0.0.0
PROXY_PORT=8764
```

#### Security Settings
```bash
# Master API key for proxy
LITELLM_MASTER_KEY=sk-your-secure-master-key

# Enable/disable rate limiting
ENABLE_RATE_LIMITING=true
MAX_REQUESTS_PER_MINUTE=60
```

#### Logging Settings
```bash
# Log level (DEBUG, INFO, WARNING, ERROR)
LOG_LEVEL=INFO

# Enable JSON logging
JSON_LOGS=false
```

---

## Configuration File Structure

### Complete Example

```yaml
# General Settings
general_settings:
  master_key: sk-1234  # or os.environ/LITELLM_MASTER_KEY
  set_verbose: true
  database_url: os.environ/DATABASE_URL
  store_model_in_db: true

# User ID Mappings for Client Detection
user_id_mappings:
  # Custom header to check first (highest priority)
  custom_header: "x-memory-user-id"

  # Header patterns for automatic detection
  header_patterns:
    - header: "user-agent"
      pattern: "OpenAIClientImpl/Java"
      user_id: "pycharm-ai"

    - header: "user-agent"
      pattern: "Claude Code"
      user_id: "claude-cli"

  # Default user ID if no patterns match
  default_user_id: "default-user"

# Model List
model_list:
  # OpenAI Models
  - model_name: gpt-4
    litellm_params:
      model: openai/gpt-4
      api_key: os.environ/OPENAI_API_KEY

  # Anthropic Models with Supermemory
  - model_name: claude-sonnet-4.5
    litellm_params:
      api_base: https://api.supermemory.ai/v3/api.anthropic.com
      model: anthropic/claude-sonnet-4-5-20250929
      api_key: os.environ/ANTHROPIC_API_KEY
      custom_llm_provider: anthropic

# LiteLLM Settings
litellm_settings:
  set_verbose: true
  json_logs: true
  use_client_cache: true
  drop_params: true
  
  # Database (for SDK mode)
  database_type: prisma
  database_url: os.environ/DATABASE_URL
  
  # Cache configuration
  cache: true
  cache_params:
    type: redis
    host: localhost
    port: 6379
    password: os.environ/REDIS_PASSWORD
    ttl: 3600
```

---

## Configuration Sections

### 1. general_settings

Controls general proxy behavior.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `master_key` | string | No | Master API key for accessing the proxy |
| `set_verbose` | boolean | No | Enable verbose logging |
| `database_url` | string | No | PostgreSQL connection string |
| `database_connection_pool_limit` | integer | No | Max database connections (1-1000) |
| `store_model_in_db` | boolean | No | Store model information in database |

**Example:**
```yaml
general_settings:
  master_key: os.environ/LITELLM_MASTER_KEY
  set_verbose: true
  database_url: os.environ/DATABASE_URL
  database_connection_pool_limit: 100
```

---

### 2. user_id_mappings

Controls client detection and user ID assignment for memory isolation.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `custom_header` | string | No | Header name to check for explicit user ID (highest priority) |
| `header_patterns` | array | No | List of pattern matching rules |
| `default_user_id` | string | No | Fallback user ID if no patterns match |

**Example:**
```yaml
user_id_mappings:
  custom_header: "x-memory-user-id"
  header_patterns:
    - header: "user-agent"
      pattern: "Claude Code"
      user_id: "claude-cli"
  default_user_id: "default-user"
```

#### header_patterns Entry

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `header` | string | Yes | Header name to match against (case-insensitive) |
| `pattern` | string | Yes | Regex pattern to match |
| `user_id` | string | Yes | User ID to assign on match |

**Regex Pattern Examples:**
```yaml
header_patterns:
  # Exact match
  - header: "user-agent"
    pattern: "^OpenAIClientImpl/Java$"
    user_id: "pycharm-ai"
  
  # Starts with
  - header: "user-agent"
    pattern: "^Claude Code"
    user_id: "claude-cli"
  
  # Contains
  - header: "user-agent"
    pattern: ".*MyApp.*"
    user_id: "my-app"
  
  # Version pattern
  - header: "user-agent"
    pattern: "MyApp/\\d+\\.\\d+"
    user_id: "my-app-versioned"
```

---

### 3. model_list

Defines available LLM models and their configurations.

Each model entry contains:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `model_name` | string | Yes | Friendly name used in API requests |
| `litellm_params` | object | Yes | LiteLLM configuration parameters |

#### litellm_params

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `model` | string | Yes | Provider/model identifier (format: `provider/model-name`) |
| `api_key` | string | Yes | API key or env var reference |
| `api_base` | string | No | Custom API base URL |
| `custom_llm_provider` | string | No | Explicit provider name |
| `timeout` | float | No | Request timeout in seconds |
| `max_retries` | integer | No | Max retry attempts |
| `extra_headers` | object | No | Additional headers to send |

**Basic Model:**
```yaml
model_list:
  - model_name: gpt-4
    litellm_params:
      model: openai/gpt-4
      api_key: os.environ/OPENAI_API_KEY
```

**With Supermemory Integration:**
```yaml
model_list:
  - model_name: claude-sonnet-4.5
    litellm_params:
      api_base: https://api.supermemory.ai/v3/api.anthropic.com
      model: anthropic/claude-sonnet-4-5-20250929
      api_key: os.environ/ANTHROPIC_API_KEY
      custom_llm_provider: anthropic
      extra_headers:
        x-supermemory-api-key: os.environ/SUPERMEMORY_API_KEY
```

**With Extended Thinking:**
```yaml
model_list:
  - model_name: claude-sonnet-4.5-thinking
    litellm_params:
      model: anthropic/claude-sonnet-4-5-20250929
      api_key: os.environ/ANTHROPIC_API_KEY
      thinking:
        type: enabled
        budget_tokens: 10000
```

---

### 4. litellm_settings

LiteLLM-specific configuration options.

#### Logging

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `set_verbose` | boolean | false | Enable verbose logging |
| `json_logs` | boolean | false | Output logs in JSON format |
| `drop_params` | boolean | false | Drop unsupported parameters |

#### Database (SDK Mode)

| Field | Type | Description |
|-------|------|-------------|
| `database_type` | string | Database backend: `prisma`, `postgresql`, `sqlite` |
| `database_url` | string | Database connection string |
| `store_model_in_db` | boolean | Store model metadata |
| `store_prompts_in_spend_logs` | boolean | Log full prompts |

#### Callbacks

| Field | Type | Description |
|-------|------|-------------|
| `success_callback` | array | Callbacks on successful requests |
| `failure_callback` | array | Callbacks on failed requests |

Available callbacks: `postgres`, `otel`, `langfuse`, `prisma_proxy`

#### Caching

| Field | Type | Description |
|-------|------|-------------|
| `cache` | boolean | Enable caching |
| `cache_params` | object | Cache configuration |

**Redis Cache:**
```yaml
litellm_settings:
  cache: true
  cache_params:
    type: redis
    host: localhost
    port: 6379
    password: os.environ/REDIS_PASSWORD
    db: 0
    ttl: 3600
    ssl: false
```

#### OpenTelemetry

| Field | Type | Description |
|-------|------|-------------|
| `otel` | boolean | Enable OTEL tracing |
| `otel_exporter` | string | Exporter type: `otlp_http`, `otlp_grpc`, `console` |
| `otel_endpoint` | string | OTEL collector endpoint |
| `otel_service_name` | string | Service name for traces |

**Example:**
```yaml
litellm_settings:
  otel: true
  otel_exporter: otlp_http
  otel_endpoint: "http://localhost:4318/v1/traces"
  otel_service_name: "litellm-proxy"
```

---

## Configuration Examples

### Basic OpenAI Setup

```yaml
general_settings:
  master_key: sk-1234

model_list:
  - model_name: gpt-4
    litellm_params:
      model: openai/gpt-4
      api_key: os.environ/OPENAI_API_KEY
```

### Multi-Provider Setup

```yaml
model_list:
  - model_name: gpt-4
    litellm_params:
      model: openai/gpt-4
      api_key: os.environ/OPENAI_API_KEY

  - model_name: claude-3-5-sonnet
    litellm_params:
      model: anthropic/claude-3-5-sonnet-20241022
      api_key: os.environ/ANTHROPIC_API_KEY

  - model_name: gemini-pro
    litellm_params:
      model: gemini/gemini-pro
      api_key: os.environ/GEMINI_API_KEY
```

### With Memory Routing & Supermemory

```yaml
user_id_mappings:
  custom_header: "x-memory-user-id"
  header_patterns:
    - header: "user-agent"
      pattern: "Claude Code"
      user_id: "claude-cli"
    - header: "user-agent"
      pattern: "OpenAIClientImpl/Java"
      user_id: "pycharm-ai"
  default_user_id: "default-user"

model_list:
  - model_name: claude-sonnet-4.5
    litellm_params:
      api_base: https://api.supermemory.ai/v3/api.anthropic.com
      model: anthropic/claude-sonnet-4-5-20250929
      api_key: os.environ/ANTHROPIC_API_KEY
      custom_llm_provider: anthropic
```

### Production Configuration with All Features

```yaml
general_settings:
  master_key: os.environ/LITELLM_MASTER_KEY
  set_verbose: false
  database_url: os.environ/DATABASE_URL
  database_connection_pool_limit: 100
  store_model_in_db: true

user_id_mappings:
  custom_header: "x-memory-user-id"
  header_patterns:
    - header: "user-agent"
      pattern: "OpenAIClientImpl/Java"
      user_id: "pycharm-ai"
    - header: "user-agent"
      pattern: "Claude Code"
      user_id: "claude-cli"
  default_user_id: "default-user"

model_list:
  - model_name: claude-sonnet-4.5
    litellm_params:
      api_base: https://api.supermemory.ai/v3/api.anthropic.com
      model: anthropic/claude-sonnet-4-5-20250929
      api_key: os.environ/ANTHROPIC_API_KEY
      custom_llm_provider: anthropic
      timeout: 600.0
      max_retries: 3

  - model_name: gpt-4
    litellm_params:
      model: openai/gpt-4
      api_key: os.environ/OPENAI_API_KEY
      timeout: 600.0
      max_retries: 3

litellm_settings:
  set_verbose: false
  json_logs: true
  drop_params: true
  use_client_cache: true
  
  # Database persistence (SDK mode)
  database_type: prisma
  database_url: os.environ/DATABASE_URL
  success_callback: ["prisma_proxy", "otel"]
  
  # Caching
  cache: true
  cache_params:
    type: redis
    host: localhost
    port: 6379
    password: os.environ/REDIS_PASSWORD
    db: 0
    ttl: 3600
    ssl: false
  
  # Observability
  otel: true
  otel_exporter: otlp_http
  otel_endpoint: "http://localhost:4318/v1/traces"
  otel_service_name: "litellm-memory-proxy"
```

---

## Configuration Schema

### Using Pydantic Schema for Validation

The configuration is validated using Pydantic models in `src/proxy/schema.py`.

#### Load and Validate Configuration

```python
from src.proxy.schema import load_config

# Load and validate
config = load_config("config.yaml")

# Access configuration
print(config.general_settings.master_key)
print(f"Models: {len(config.model_list)}")
```

#### Validate from CLI

```bash
poetry run python src/proxy/schema.py config/config.yaml
```

#### Environment Variable Resolution

```python
from src.proxy.schema import load_config_with_env_resolution
import os

# Set environment variables
os.environ["MASTER_KEY"] = "sk-1234"
os.environ["OPENAI_API_KEY"] = "sk-..."

# Load with env vars resolved
config = load_config_with_env_resolution("config.yaml")
print(config.general_settings.master_key)  # "sk-1234" (resolved)
```

### Schema Validation Rules

1. **Environment Variables**: Must use format `os.environ/VAR_NAME`
2. **Model Format**: Must be `provider/model-name`
3. **URLs**: Must start with `http://` or `https://`
4. **Regex Patterns**: Must compile successfully
5. **Unique Model Names**: No duplicates allowed
6. **Required Fields**: Model params require `model` and `api_key`

---

## Validation

### Pre-Flight Validation

The proxy validates configuration on startup:

1. **Environment Variables**
   - At least one API key configured
   - Valid env var references

2. **YAML Syntax**
   - Valid YAML format
   - Required fields present

3. **Regex Patterns**
   - All patterns compile successfully
   - Invalid patterns logged and skipped

4. **Model Configuration**
   - Unique model names
   - Valid provider/model format
   - API keys configured

### Testing Configuration

```bash
# Validate configuration file
poetry run python src/proxy/schema.py config/config.yaml

# Test pattern matching
curl http://localhost:8764/memory-routing/info \
  -H "User-Agent: Claude Code"
```

### Common Validation Errors

**Error: "Invalid environment variable name"**
```yaml
# ❌ Bad: Hyphens not allowed
api_key: os.environ/MY-API-KEY

# ✅ Good: Use underscores
api_key: os.environ/MY_API_KEY
```

**Error: "Model must be in format 'provider/model-name'"**
```yaml
# ❌ Bad
model: gpt-4

# ✅ Good
model: openai/gpt-4
```

**Error: "cache_params is required when cache=true"**
```yaml
# ❌ Bad
litellm_settings:
  cache: true

# ✅ Good
litellm_settings:
  cache: true
  cache_params:
    type: redis
    host: localhost
    port: 6379
```

---

## Troubleshooting

### Common Issues

#### "Config file not found"

**Solution:**
- Check `LITELLM_CONFIG` environment variable
- Ensure file exists at specified path
- Use absolute path if relative path fails

```bash
# Set absolute path
export LITELLM_CONFIG=/absolute/path/to/config.yaml
```

#### "API key not configured"

**Solution:**
- Check environment variable is set: `echo $OPENAI_API_KEY`
- Verify `os.environ/` prefix in config.yaml
- Check for typos in variable names

```bash
# List all API key env vars
env | grep API_KEY
```

#### "Pattern not matching"

**Solution:**
- Test pattern with debug endpoint
- Check regex syntax
- Verify header name (case-insensitive)

```bash
# Debug routing
curl http://localhost:8764/memory-routing/info \
  -H "User-Agent: MyApp/1.0"
```

#### "Database connection failed"

**Solution:**
- Verify DATABASE_URL format
- Check database is running
- Test connection manually

```bash
# Test PostgreSQL connection
psql $DATABASE_URL -c "SELECT 1"
```

#### "Redis connection failed"

**Solution:**
- Verify Redis is running
- Check REDIS_URL and REDIS_PASSWORD
- Test connection

```bash
# Test Redis connection
redis-cli -h localhost -p 6379 ping
```

---

## Configuration Priority

Configuration values are resolved in the following order (highest to lowest):

1. **Command-Line Arguments**
   - `--config` (config file path)
   - `--port` (proxy port)

2. **Environment Variables**
   - `LITELLM_CONFIG`
   - `OPENAI_API_KEY`
   - `ANTHROPIC_API_KEY`
   - etc.

3. **config.yaml**
   - Model definitions
   - User ID mappings
   - LiteLLM settings

4. **Defaults**
   - Hardcoded fallback values

---

## Related Documentation

- [Quick Start Guide](../getting-started/QUICKSTART.md) - Get started quickly
- [Architecture Overview](../architecture/OVERVIEW.md) - System design
- [Design Decisions](../architecture/DESIGN_DECISIONS.md) - Architectural choices
- [Testing Guide](TESTING.md) - Testing strategies
- [Troubleshooting](../troubleshooting/COMMON_ISSUES.md) - Common issues

---

**Last Updated**: 2025-11-04  
**Status**: Consolidated from reference documentation
