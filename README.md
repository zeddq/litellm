# LiteLLM Memory Proxy

A lightweight memory routing proxy for LiteLLM with dynamic user-based memory isolation using Supermemory.

## Architecture

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

## Prerequisites

1. **Python 3.13+**
2. **LiteLLM CLI** (installed separately):
   ```bash
   pip install litellm
   # or
   poetry add litellm
   ```
3. **API Keys** (set in environment):
   - `OPENAI_API_KEY`
   - `ANTHROPIC_API_KEY`
   - `SUPERMEMORY_API_KEY` (optional, for memory features)

## Installation

```bash
poetry install
```

## Configuration

Edit `config.yaml` to configure:
- **Models**: OpenAI, Anthropic, Gemini models
- **User ID Mappings**: Header patterns for client detection
- **Memory Routing**: Supermemory integration settings

Example configuration:
```yaml
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

## Usage

### Start Both Proxies (Recommended)

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

### Start Memory Proxy Only

If LiteLLM is already running:

```bash
poetry run python litellm_proxy_with_memory.py \
  --config config.yaml \
  --port 8764 \
  --litellm-url http://localhost:8765
```

### Start LiteLLM Binary Manually

```bash
litellm --config config.yaml --port 8765 --host 0.0.0.0
```

## Testing

Point your clients to the Memory Proxy (port 8764):

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8764/v1",
    api_key="sk-1234"  # Your configured master key
)

response = client.chat.completions.create(
    model="claude-sonnet-4.5",
    messages=[{"role": "user", "content": "Hello!"}]
)
```

## Features

### 1. **Dynamic Memory Routing**
- Automatically detects client type from headers
- Assigns user IDs for memory isolation
- Injects Supermemory headers for conversation persistence

### 2. **Client Detection**
Multiple detection methods:
- **Custom Header**: `x-memory-user-id`
- **Pattern Matching**: User-Agent, custom headers
- **Default Fallback**: Configurable default user ID

### 3. **Multi-Provider Support**
- OpenAI (GPT models)
- Anthropic (Claude models with Supermemory)
- Google Gemini
- Any LiteLLM-supported provider

### 4. **Zero SDK Dependencies**
- Uses external LiteLLM binary via subprocess
- Pure HTTP communication
- Easier deployment and version management

## Project Structure

```
litellm/
├── config.yaml                      # LiteLLM and routing configuration
├── litellm_proxy_with_memory.py     # Memory routing proxy (FastAPI)
├── memory_router.py                 # Client detection and routing logic
├── start_proxies.py                 # Launch script for both proxies
├── tutorial_proxy_with_memory.py    # Comprehensive tutorial code
├── example_complete_workflow.py     # Usage examples
└── test_tutorial.py                 # Test suite
```

## Key Benefits of Binary Approach

1. **Separation of Concerns**: Memory routing separate from LiteLLM
2. **Independent Scaling**: Scale proxies independently
3. **Version Management**: Upgrade LiteLLM without code changes
4. **Simplified Dependencies**: No SDK conflicts
5. **Production Ready**: Process isolation and better error handling

## Development

Run tests:
```bash
poetry run python test_tutorial.py
```

Run examples:
```bash
poetry run python example_complete_workflow.py
```

## Environment Variables

```bash
# Required
export OPENAI_API_KEY="sk-..."
export ANTHROPIC_API_KEY="sk-ant-..."

# Optional
export SUPERMEMORY_API_KEY="sm_..."
export LITELLM_BASE_URL="http://localhost:8765"
export LITELLM_CONFIG="./config.yaml"
```

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

## License

See project root for license information.
