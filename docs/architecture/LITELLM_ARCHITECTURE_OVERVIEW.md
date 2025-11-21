# Memory Proxy Architecture Snapshot

This document summarizes the current LiteLLM memory proxy setup and how traffic flows through the system.

## Key Components
- **Memory Proxy (port 8764):** FastAPI application that embeds the LiteLLM SDK.
- **LiteLLM SDK (In-Process):** Integrated Python library handling provider routing (OpenAI, Anthropic, Gemini) directly within the proxy process.
- **Memory Router:** Pattern-matching engine that determines user identity and routing rules.
- **Session Manager:** Manages persistent `httpx` sessions and cookies for each user context.

## Request Flow
1. Client sends a request to the Memory Proxy (Port 8764).
2. Router derives the user ID from `x-memory-user-id`, matching patterns, or the default fallback.
3. Session Manager retrieves or creates a persistent session (with cookies) for that user.
4. Proxy calls the LiteLLM SDK using the user's persistent session.
5. LiteLLM SDK communicates with upstream providers (OpenAI, Supermemory, etc.).
6. Response returns through the SDK to the proxy and then to the client.

## Configuration
- Primary config is stored in `config.yaml` (model definitions, routing, and user ID mappings).
- Detection priority: `x-memory-user-id` header, then regex-based pattern matching, then the default user ID.

## Key Files
- `src/proxy/litellm_proxy_sdk.py` — FastAPI proxy entry point (SDK Mode).
- `src/proxy/memory_router.py` — Client detection and routing rules.
- `src/proxy/session_manager.py` — Persistent session management.
- `deploy/run_unified_proxy.py` — Unified launcher script.
- `docs/architecture/OVERVIEW.md` — Expanded architecture details and diagrams.