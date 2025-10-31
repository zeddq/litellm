# LiteLLM Proxy Configuration Schema

Comprehensive Pydantic schema for validating LiteLLM proxy configuration files (`config.yaml`).

## Overview

The schema provides:
- **Type validation** for all configuration sections
- **Custom validators** for regex patterns, URLs, and cross-field validation
- **Environment variable support** with `os.environ/VAR_NAME` pattern
- **Helpful error messages** for configuration issues
- **JSON Schema export** for IDE autocompletion

## Quick Start

### Basic Usage

```python
from proxy.schema import load_config

# Load and validate configuration
config = load_config("config.yaml")

# Access configuration
print(config.general_settings.master_key)
print(f"Models: {len(config.model_list)}")
```

### With Environment Variable Resolution

```python
from proxy.schema import load_config_with_env_resolution
import os

# Set environment variables
os.environ["MASTER_KEY"] = "sk-1234"
os.environ["OPENAI_API_KEY"] = "sk-..."

# Load with env vars resolved
config = load_config_with_env_resolution("config.yaml")
print(config.general_settings.master_key)  # "sk-1234" (resolved)
```

### Validate Config Dictionary

```python
from proxy.schema import validate_config_dict

config_dict = {
    "general_settings": {"master_key": "sk-1234"},
    "model_list": [
        {
            "model_name": "gpt-4",
            "litellm_params": {
                "model": "openai/gpt-4",
                "api_key": "sk-test"
            }
        }
    ]
}

config = validate_config_dict(config_dict)
```

### CLI Validation

```bash
# Validate config file from command line
poetry run python src/proxy/schema.py config/config.yaml
```

## Configuration Sections

### 1. General Settings

```yaml
general_settings:
  master_key: sk-1234                    # or os.environ/MASTER_KEY
  forward_openai_org_id: true
  forward_client_headers_to_llm_api: true
  database_url: os.environ/DATABASE_URL
  database_connection_pool_limit: 100
  store_model_in_db: true
  store_prompts_in_spend_logs: false
```

**Validators:**
- `master_key`: Required, supports env vars
- `database_connection_pool_limit`: 1-1000
- Env var names must be valid Python identifiers

### 2. User ID Mappings (Memory Routing)

```yaml
user_id_mappings:
  custom_header: "x-memory-user-id"
  header_patterns:
    - header: "user-agent"
      pattern: "^OpenAIClientImpl/Java"
      user_id: "pycharm-ai"
    - header: "user-agent"
      pattern: "^Claude Code"
      user_id: "claude-cli"
  default_user_id: "default-dev"
```

**Validators:**
- Regex patterns must compile successfully
- Header names normalized to lowercase
- User IDs cannot contain whitespace
- Duplicate patterns not allowed

### 3. Model List

```yaml
model_list:
  - model_name: claude-sonnet-4.5
    litellm_params:
      model: anthropic/claude-sonnet-4-5-20250929  # Required format: provider/model
      api_key: os.environ/ANTHROPIC_API_KEY
      api_base: https://api.supermemory.ai/v3/api.anthropic.com
      custom_llm_provider: anthropic
      extra_headers:
        x-supermemory-api-key: os.environ/SUPERMEMORY_API_KEY
      thinking:
        type: enabled
        budget_tokens: 4096
      timeout: 30.0
      max_retries: 3
```

**Validators:**
- `model`: Must be in format `provider/model-name`
- `api_base`: Must start with `http://` or `https://`
- `timeout`: >= 0.1 seconds
- `thinking.budget_tokens`: 1-100000
- Model names must be unique

### 4. MCP Servers

```yaml
mcp_servers:
  jetbrains_mcp:
    transport: sse                    # or stdio
    url: "http://localhost:64343/sse" # Required for sse
    auth_type: none                   # or bearer, basic

  local_server:
    transport: stdio
    command: "python"                 # Required for stdio
    args: ["-m", "mcp_server"]
    env:
      PATH: "/usr/bin"
```

**Validators:**
- SSE transport requires `url`
- STDIO transport requires `command`
- URLs must start with `http://` or `https://`

### 5. LiteLLM Settings

```yaml
litellm_settings:
  # Database
  database_type: prisma           # or postgresql, postgres, sqlite
  database_url: os.environ/DATABASE_URL
  store_model_in_db: true

  # Callbacks
  success_callback: ["postgres", "otel"]
  failure_callback: ["postgres", "otel"]

  # OpenTelemetry
  otel: true
  otel_exporter: otlp_http        # or otlp_grpc, console
  otel_endpoint: "http://localhost:4318/v1/traces"
  otel_service_name: "litellm-proxy"
  otel_headers: ""

  # Cache
  cache: true
  cache_params:
    type: redis                   # or s3
    host: localhost
    port: 6379
    password: os.environ/REDIS_PASSWORD
    db: 0
    ttl: 3600
    ssl: false

  # MCP
  mcp_aliases:
    jetbrains: jetbrains_mcp

  # Logging
  set_verbose: true
  json_logs: true
  drop_params: true
  forward_traceparent_to_llm_provider: true
```

**Validators:**
- `cache=true` requires `cache_params`
- `otel=true` requires `otel_exporter` and `otel_endpoint`
- OTEL endpoint must be valid URL
- Redis port: 1-65535
- MCP aliases must reference existing servers

## Validation Features

### Environment Variable Resolution

The schema supports two forms of environment variable references:

```yaml
# Format: os.environ/VAR_NAME
api_key: os.environ/OPENAI_API_KEY
database_url: os.environ/DATABASE_URL
```

Use `load_config()` to keep env vars as-is, or `load_config_with_env_resolution()` to resolve immediately.

### Custom Validators

1. **Regex Pattern Validation**
   ```python
   # Compiles patterns to ensure they're valid
   pattern: "^OpenAIClientImpl/Java"  # Valid
   pattern: "[invalid(regex"          # ValidationError
   ```

2. **URL Format Validation**
   ```python
   # Must start with http:// or https://
   url: "http://localhost:8000"       # Valid
   url: "localhost:8000"              # ValidationError
   ```

3. **Model Format Validation**
   ```python
   # Must be provider/model-name
   model: "openai/gpt-4"              # Valid
   model: "gpt-4"                     # ValidationError
   ```

4. **Cross-Field Validation**
   - Cache enabled → cache_params required
   - OTEL enabled → exporter and endpoint required
   - SSE transport → URL required
   - STDIO transport → command required

### Helpful Error Messages

```python
from pydantic import ValidationError

try:
    config = load_config("invalid_config.yaml")
except ValidationError as e:
    print(e)
```

Example output:
```
ValidationError: 3 validation errors for LiteLLMProxyConfig
model_list -> 0 -> litellm_params -> model
  Model must be in format 'provider/model-name', got: gpt-4
cache_params
  cache_params is required when cache=true
otel_endpoint
  otel_endpoint must start with http:// or https://, got: localhost:4318
```

## Export JSON Schema

Generate JSON Schema for IDE autocompletion:

```python
from proxy.schema import export_json_schema

export_json_schema("config_schema.json")
```

Use with VS Code YAML extension:
```json
{
  "yaml.schemas": {
    "./config_schema.json": "config/config.yaml"
  }
}
```

## Testing

Run the comprehensive test suite:

```bash
# All tests
poetry run pytest test_schema.py -v

# Specific test category
poetry run pytest test_schema.py -v -k TestModelConfig

# Exclude slow tests
poetry run pytest test_schema.py -v -k "not slow"
```

Test coverage:
- GeneralSettings validation
- UserIDMappings and pattern matching
- ModelConfig and LiteLLMParams
- MCPServerConfig for both transports
- Cache configuration (Redis & S3)
- LiteLLMSettings with OTEL
- Root config validation
- Environment variable resolution
- Helper functions
- Integration tests with real config files

## Type Hints

The schema is fully typed with Pydantic v2:

```python
from proxy.schema import LiteLLMProxyConfig, ModelConfig

# Type checking works
config: LiteLLMProxyConfig = load_config("config.yaml")
model: ModelConfig = config.model_list[0]
api_key: str = model.litellm_params.api_key
```

## Python 3.13+ Features

The schema uses modern Python features:
- `Union[X, Y]` and `Optional[X]` type hints
- Pydantic v2 with `ConfigDict`
- Path objects for file handling
- Enum for string literals
- Type aliases for clarity

## Common Issues

### Issue: "Invalid environment variable name"
**Solution:** Env var names must be valid Python identifiers (no hyphens, spaces, or special chars).

```yaml
# Bad
api_key: os.environ/MY-API-KEY

# Good
api_key: os.environ/MY_API_KEY
```

### Issue: "Model must be in format 'provider/model-name'"
**Solution:** Always use `provider/model` format.

```yaml
# Bad
model: gpt-4

# Good
model: openai/gpt-4
```

### Issue: "Duplicate model names found"
**Solution:** Each model name must be unique.

```yaml
# Bad
model_list:
  - model_name: gpt-4
    litellm_params: ...
  - model_name: gpt-4  # Duplicate!
    litellm_params: ...

# Good - use different names or aliases
model_list:
  - model_name: gpt-4
    litellm_params: ...
  - model_name: gpt-4-turbo
    litellm_params: ...
```

### Issue: "cache_params is required when cache=true"
**Solution:** Provide cache configuration when enabling cache.

```yaml
litellm_settings:
  cache: true
  cache_params:
    type: redis
    host: localhost
    port: 6379
    ttl: 3600
```

## API Reference

### Functions

- `load_config(path)` - Load and validate config (env vars as-is)
- `load_config_with_env_resolution(path)` - Load with env vars resolved
- `validate_config_dict(dict)` - Validate config dictionary
- `resolve_env_vars(value)` - Recursively resolve env var references
- `export_json_schema(path)` - Export JSON Schema to file

### Models

- `LiteLLMProxyConfig` - Root configuration model
- `GeneralSettings` - General proxy settings
- `UserIDMappings` - Memory routing configuration
- `ModelConfig` - Model entry
- `LiteLLMParams` - Model parameters
- `MCPServerConfig` - MCP server configuration
- `LiteLLMSettings` - LiteLLM settings
- `RedisCacheParams` - Redis cache config
- `S3CacheParams` - S3 cache config

### Enums

- `DatabaseType` - Database backend types
- `CacheType` - Cache backend types
- `OTELExporter` - OpenTelemetry exporters
- `MCPTransport` - MCP transport protocols
- `MCPAuthType` - MCP authentication types
- `ThinkingType` - Extended thinking modes

## Performance

The schema is optimized for fast validation:
- Validates 100 models in <1 second
- Minimal memory overhead
- Efficient regex compilation (cached)
- No network calls during validation

## Future Enhancements

Potential additions:
- [ ] Rate limiting configuration validation
- [ ] Custom provider parameter schemas
- [ ] Migration helpers for config upgrades
- [ ] Config diff/comparison utilities
- [ ] Visual config editor support

## Contributing

When modifying the schema:
1. Update models in `src/proxy/schema.py`
2. Add validators for new fields
3. Update test suite in `test_schema.py`
4. Update this README
5. Run full test suite: `poetry run pytest test_schema.py -v`

## License

Same as main project.