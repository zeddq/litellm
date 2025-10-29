LiteLLM Memory Proxy Architecture

PROJECT: Multi-tenant memory routing proxy for LiteLLM with automatic client detection

KEY COMPONENTS:
1. Memory Proxy (port 8764) - FastAPI app that intercepts requests, detects clients via User-Agent patterns, injects x-sm-user-id headers for Supermemory isolation
2. LiteLLM Binary (port 8765) - External process for provider routing (OpenAI, Anthropic, Gemini)
3. Memory Router - Pattern matching engine for client detection and header injection
4. Process Manager - Coordinates both proxy processes

ARCHITECTURE EVOLUTION:
Moved from SDK-based (in-process LiteLLM) to Binary-based (external LiteLLM process) for better isolation, independent scaling, and simplified dependencies.

REQUEST FLOW:
Client -> Memory Proxy (detect user_id from headers) -> Inject x-sm-user-id -> LiteLLM Binary -> Provider API -> Response

KEY FILES:
- src/proxy/litellm_proxy_with_memory.py - Main FastAPI proxy
- src/proxy/memory_router.py - Client detection logic
- deploy/start_proxies.py - Process orchestration
- config.yaml - Model definitions and user ID mappings
- ARCHITECTURE_CONSOLIDATED.md - Complete architecture documentation

CONFIGURATION:
User ID detection priority: 1) x-memory-user-id header, 2) Pattern matching (regex on User-Agent etc), 3) Default user ID

RECENT CHANGES (last 2 days): Documentation updates, test files, core proxy implementations, setup scripts

DOCUMENTATION:
Consolidated architecture in ARCHITECTURE_CONSOLIDATED.md includes: component details, data flows, configuration, deployment patterns, usage examples, performance characteristics, security, and extension points.