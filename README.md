# LiteLLM Proxy with PostgreSQL

LiteLLM proxy server with PostgreSQL database backend and authentication passthrough proxy.

## Setup

```bash
poetry install
```

## Usage

Run both proxies:
```bash
poetry run run-proxies
```

This starts:
- LiteLLM Proxy on `http://localhost:4000`
- Auth Passthrough Proxy on `http://localhost:8764`

## Environment Variables

- `DATABASE_URL` - PostgreSQL connection string
- `LITELLM_VIRTUAL_KEY` - Virtual key for authentication
- `OPENAI_API_KEY` - OpenAI API key
- `ANTHROPIC_API_KEY` - Anthropic API key
