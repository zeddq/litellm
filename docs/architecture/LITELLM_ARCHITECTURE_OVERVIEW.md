# Memory Proxy Architecture Snapshot

This document summarizes the current LiteLLM memory proxy setup and how traffic flows through the system.

## Key Components
- **Memory Proxy (port 8764):** FastAPI application that detects clients (via headers and User-Agent patterns), injects `x-sm-user-id`, and forwards traffic.
- **LiteLLM Binary (port 8765):** External process handling provider routing (OpenAI, Anthropic, Gemini) outside the application runtime for isolation.
- **Memory Router:** Pattern-matching engine that determines user identity and routing rules.
- **Process Manager:** Coordinates the memory proxy and LiteLLM binary lifecycles.

## Request Flow
1. Client sends a request to the Memory Proxy.
2. Router derives the user ID from `x-memory-user-id`, matching patterns, or the default fallback.
3. Proxy injects `x-sm-user-id` and forwards the request to the LiteLLM binary.
4. Provider response returns through the proxy to the client.

## Configuration
- Primary config is stored in `config.yaml` (model definitions, routing, and user ID mappings).
- Detection priority: `x-memory-user-id` header, then regex-based pattern matching, then the default user ID.

## Key Files
- `src/proxy/litellm_proxy_with_memory.py` — FastAPI proxy entry point.
- `src/proxy/memory_router.py` — Client detection and routing rules.
- `deploy/start_proxies.py` — Process orchestration for the proxy and LiteLLM binary.
- `docs/architecture/OVERVIEW.md` — Expanded architecture details and diagrams.
