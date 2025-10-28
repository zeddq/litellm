# Configuration Reference

Complete configuration reference for LiteLLM Memory Proxy.

---

## Environment Variables

### Required Variables

```bash
# OpenAI API Key
OPENAI_API_KEY=sk-...
```

### Optional Variables

#### API Keys
```bash
# Anthropic API Key (for Claude models)
ANTHROPIC_API_KEY=sk-ant-...

# Supermemory API Key (for memory features)
SUPERMEMORY_API_KEY=sm-...
```

#### Infrastructure
```bash
# Redis URL for persistent storage
REDIS_URL=redis://localhost:6379/0

# LiteLLM base URL
LITELLM_BASE_URL=http://localhost:8765

# Configuration file path
LITELLM_CONFIG=./config.yaml
```

#### Proxy Configuration
```bash
# Proxy host
PROXY_HOST=0.0.0.0

# Proxy port
PROXY_PORT=8765
```

#### Memory Settings
```bash
# Session TTL in seconds
MEMORY_TTL_SECONDS=3600

# Maximum context messages to retain
MAX_CONTEXT_MESSAGES=20
```

#### Security Settings
```bash
# Enable/disable rate limiting
ENABLE_RATE_LIMITING=true

# Maximum requests per minute
MAX_REQUESTS_PER_MINUTE=60

# Master API key for proxy
LITELLM_MASTER_KEY=sk-your-secure-master-key
```

#### Logging Settings
```bash
# Log level (DEBUG, INFO, WARNING, ERROR)
LOG_LEVEL=INFO

# Enable JSON logging
JSON_LOGS=false
```

---

## config.yaml Structure

### Complete Example

```yaml
# General Settings
general_settings:
  master_key: sk-1234
  set_verbose: true

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

    - header: "user-agent"
      pattern: "Anthropic"
      user_id: "anthropic-client"

  # Default user ID if no patterns match
  default_user_id: "default-user"

# Model List
model_list:
  # OpenAI Models
  - model_name: gpt-4
    litellm_params:
      model: openai/gpt-4
      api_key: os.environ/OPENAI_API_KEY

  - model_name: gpt-4-turbo
    litellm_params:
      model: openai/gpt-4-turbo-preview
      api_key: os.environ/OPENAI_API_KEY

  - model_name: gpt-3.5-turbo
    litellm_params:
      model: openai/gpt-3.5-turbo
      api_key: os.environ/OPENAI_API_KEY

  # Anthropic Models with Supermemory
  - model_name: claude-sonnet-4.5
    litellm_params:
      api_base: https://api.supermemory.ai/v3/api.anthropic.com
      model: anthropic/claude-sonnet-4-5-20250929
      api_key: os.environ/ANTHROPIC_API_KEY

  - model_name: claude-3-5-sonnet
    litellm_params:
      api_base: https://api.supermemory.ai/v3/api.anthropic.com
      model: anthropic/claude-3-5-sonnet-20241022
      api_key: os.environ/ANTHROPIC_API_KEY

  # Gemini Models
  - model_name: gemini-pro
    litellm_params:
      model: gemini/gemini-pro
      api_key: os.environ/GEMINI_API_KEY

# LiteLLM Settings
litellm_settings:
  set_verbose: true
  json_logs: true
  use_client_cache: true
  drop_params: true
```

---

## Configuration Sections

### general_settings

Controls general proxy behavior.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `master_key` | string | No | Master API key for accessing the proxy |
| `set_verbose` | boolean | No | Enable verbose logging |

**Example:**
```yaml
general_settings:
  master_key: sk-1234
  set_verbose: true
```

---

### user_id_mappings

Controls client detection and user ID assignment.

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

**Example:**
```yaml
header_patterns:
  - header: "user-agent"
    pattern: "OpenAIClientImpl/Java"
    user_id: "pycharm-ai"
```

---

### model_list

Defines available LLM models and their configurations.

Each model entry contains:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `model_name` | string | Yes | Friendly name used in API requests |
| `litellm_params` | object | Yes | LiteLLM configuration parameters |

#### litellm_params

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `model` | string | Yes | Provider/model identifier (e.g., `openai/gpt-4`) |
| `api_key` | string | Yes | API key or reference to environment variable |
| `api_base` | string | No | Custom API base URL (for Supermemory integration) |

**Example:**
```yaml
model_list:
  - model_name: gpt-4
    litellm_params:
      model: openai/gpt-4
      api_key: os.environ/OPENAI_API_KEY
```

**With Supermemory:**
```yaml
model_list:
  - model_name: claude-sonnet-4.5
    litellm_params:
      api_base: https://api.supermemory.ai/v3/api.anthropic.com
      model: anthropic/claude-sonnet-4-5-20250929
      api_key: os.environ/ANTHROPIC_API_KEY
```

---

### litellm_settings

LiteLLM-specific configuration options.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `set_verbose` | boolean | No | Enable verbose logging |
| `json_logs` | boolean | No | Output logs in JSON format |
| `use_client_cache` | boolean | No | Enable client caching |
| `drop_params` | boolean | No | Drop unsupported parameters |

**Example:**
```yaml
litellm_settings:
  set_verbose: true
  json_logs: true
  use_client_cache: true
  drop_params: true
```

---

## Configuration Priority

Configuration values are resolved in the following order (highest to lowest):

1. **Command-Line Arguments**
   - `--config` (config file path)
   - `--port` (proxy port)
   - `--litellm-url` (LiteLLM base URL)

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

### With Memory Routing

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
```

---

## Environment-Specific Configurations

### Development

```bash
# .env.development
LOG_LEVEL=DEBUG
JSON_LOGS=false
ENABLE_RATE_LIMITING=false
REDIS_URL=redis://localhost:6379/0
```

### Production

```bash
# .env.production
LOG_LEVEL=INFO
JSON_LOGS=true
ENABLE_RATE_LIMITING=true
MEMORY_TTL_SECONDS=3600
MAX_REQUESTS_PER_MINUTE=100
REDIS_URL=redis://redis.prod:6379/0
```

---

## Validation

### Configuration Validation

The proxy validates configuration on startup:

1. **Required Environment Variables**
   - At least one API key must be configured
   - Config file must exist and be readable

2. **YAML Syntax**
   - Must be valid YAML
   - Required fields must be present

3. **Regex Patterns**
   - Pattern compilation is validated
   - Invalid patterns are logged and skipped

### Testing Configuration

```bash
# Dry-run to test configuration
python litellm_proxy_with_memory.py --config config.yaml --dry-run

# Check specific pattern matching
curl http://localhost:8764/memory-routing/info \
  -H "User-Agent: Claude Code"
```

---

## Troubleshooting

### Common Issues

**Issue: "Config file not found"**
- Check `LITELLM_CONFIG` environment variable
- Ensure file exists at specified path
- Use absolute path if relative path fails

**Issue: "API key not configured"**
- Check environment variable is set: `echo $OPENAI_API_KEY`
- Verify `os.environ/` prefix in config.yaml
- Check for typos in variable names

**Issue: "Pattern not matching"**
- Test pattern with debug endpoint: `/memory-routing/info`
- Check regex syntax
- Verify header name (case-insensitive)
- Check for leading/trailing whitespace

---

## Related Documentation

- [Quick Start Guide](../getting-started/QUICKSTART.md)
- [Architecture Overview](../architecture/OVERVIEW.md)
- [Migration Guide](../guides/migration/MIGRATION_GUIDE.md)

---

**Sources**: README.md, TUTORIAL_README.md, config.yaml examples
**Created**: 2025-10-24
**Updated**: 2025-10-24
