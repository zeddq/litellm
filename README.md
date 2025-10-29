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

```bash
```


## Environment Variables

