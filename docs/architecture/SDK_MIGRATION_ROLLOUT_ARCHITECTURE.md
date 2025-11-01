# LiteLLM SDK Migration: Incremental Rollout Architecture

**Document Version**: 1.0
**Date**: 2025-11-02
**Status**: Ready for Implementation
**Author**: Architecture Team

---

## Executive Summary

This document provides a comprehensive, **practical implementation plan** for migrating from binary LiteLLM to SDK-based approach while maintaining 100% backward compatibility and zero downtime. The strategy emphasizes **parallel coexistence** with the existing binary proxy remaining completely untouched.

### Key Principles

1. **Non-Destructive Migration**: Binary proxy remains untouched and fully operational
2. **Parallel Deployment**: Both proxies run simultaneously during migration
3. **Easy Rollback**: Single environment variable to switch between approaches
4. **Zero Config Changes**: Same config.yaml for both implementations
5. **Progressive Validation**: Incremental testing with real clients before cutover

### Timeline: 3-4 Days

- **Day 1-2**: SDK implementation in parallel directory structure
- **Day 3**: Testing and validation with both proxies running
- **Day 4**: Cutover with feature flag and monitoring

---

## Table of Contents

1. [Directory Structure Strategy](#1-directory-structure-strategy)
2. [Parallel Coexistence Strategy](#2-parallel-coexistence-strategy)
3. [Integration Points](#3-integration-points)
4. [Rollout Phases](#4-rollout-phases)
5. [Risk Mitigation](#5-risk-mitigation)
6. [Component Architecture](#6-component-architecture)
7. [Testing Strategy](#7-testing-strategy)
8. [Monitoring and Observability](#8-monitoring-and-observability)

---

## 1. Directory Structure Strategy

### 1.1 Current State (Before Migration)

```
litellm/
├── src/proxy/
│   ├── __init__.py
│   ├── litellm_proxy_with_memory.py    # BINARY: Keep untouched
│   ├── memory_router.py                # SHARED: Reuse as-is
│   ├── schema.py                       # SHARED: Reuse as-is
│   └── litellm_proxy_sdk.py            # SDK: Incomplete, to be completed
│
├── config/
│   └── config.yaml                     # SHARED: No changes
│
├── deploy/
│   ├── run_proxies.py                  # ORCHESTRATOR: Enhance with feature toggle
│   └── start_proxies.py                # OLD: Keep for backward compat
│
├── poc_litellm_sdk_proxy.py            # REFERENCE: Keep for validation
└── SDK_MIGRATION_PLAN.md               # DOCUMENTATION
```

### 1.2 Target State (During Migration - Both Coexist)

```
litellm/
├── src/proxy/
│   ├── __init__.py
│   │
│   ├── litellm_proxy_with_memory.py    # BINARY: Untouched, operational
│   │   └── Runs on port 8764
│   │
│   ├── litellm_proxy_sdk.py            # SDK: Complete implementation
│   │   └── Runs on port 8765
│   │
│   ├── memory_router.py                # SHARED: Used by both
│   ├── schema.py                       # SHARED: Used by both
│   │
│   ├── config_parser.py                # NEW: SDK-specific config parsing
│   ├── session_manager.py              # NEW: Persistent httpx client
│   ├── error_handlers.py               # NEW: Rich error handling
│   └── streaming_utils.py              # NEW: SSE streaming helpers
│
├── config/
│   └── config.yaml                     # SHARED: Identical for both
│
├── deploy/
│   ├── run_proxies.py                  # ENHANCED: Intelligent proxy selector
│   ├── start_binary_proxy.py           # NEW: Binary-only launcher
│   └── start_sdk_proxy.py              # NEW: SDK-only launcher
│
├── tests/
│   ├── test_binary_proxy.py            # EXISTING: Binary tests
│   ├── test_sdk_proxy.py               # NEW: SDK tests
│   ├── test_memory_router.py           # SHARED: Tests for both
│   ├── test_config_parser.py           # NEW: Config parsing tests
│   └── test_integration_both.py        # NEW: Side-by-side comparison
│
└── docs/architecture/
    ├── BINARY_VS_SDK_ARCHITECTURE.md   # REFERENCE: Architectural comparison
    ├── SDK_MIGRATION_PLAN.md           # PLAN: Implementation details
    └── SDK_MIGRATION_ROLLOUT_ARCHITECTURE.md  # THIS DOCUMENT
```

### 1.3 Final State (After Cutover - SDK Primary)

```
litellm/
├── src/proxy/
│   ├── __init__.py
│   │
│   ├── litellm_proxy_sdk.py            # PRIMARY: Main implementation (port 8764)
│   ├── config_parser.py
│   ├── session_manager.py
│   ├── error_handlers.py
│   ├── streaming_utils.py
│   │
│   ├── memory_router.py                # SHARED: Unchanged
│   ├── schema.py                       # SHARED: Unchanged
│   │
│   └── archive/                        # ARCHIVED: For rollback
│       ├── litellm_proxy_with_memory.py    # BINARY: Preserved
│       ├── start_binary_proxy.py
│       └── ROLLBACK_INSTRUCTIONS.md
│
├── config/
│   └── config.yaml                     # UNCHANGED
│
├── deploy/
│   ├── run_proxies.py                  # SIMPLIFIED: SDK by default
│   └── start_sdk_proxy.py              # PRIMARY launcher
│
└── poc_litellm_sdk_proxy.py            # DELETE after validation
```

### 1.4 Naming Conventions

**File Naming Strategy**:
- `*_sdk.py` - SDK-specific implementations
- `*_binary.py` - Binary-specific implementations
- No suffix - Shared components (e.g., `memory_router.py`)

**Function/Class Naming**:
- Binary approach: Existing names unchanged
- SDK approach: New names with clear purpose (e.g., `LiteLLMSessionManager`, `LiteLLMConfig`)
- Shared: Generic names (e.g., `MemoryRouter`, `detect_user_id`)

**Port Allocation**:
- `8764` - Production port (Binary during migration, SDK after cutover)
- `8765` - Testing port (SDK during migration)
- `4000` - LiteLLM binary (only during binary proxy operation)

---

## 2. Parallel Coexistence Strategy

### 2.1 Dual-Proxy Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     Client Applications                          │
│  (PyCharm AI, Claude Code, VS Code, curl, httpx)                │
└───────────────┬─────────────────────────────────────────────────┘
                │
                │ User configures which proxy to use
                │
        ┌───────┴────────┐
        │                │
        ▼                ▼
┌────────────────┐  ┌────────────────┐
│ Binary Proxy   │  │  SDK Proxy     │
│ Port 8764      │  │  Port 8765     │
│ (Current)      │  │  (New)         │
└───────┬────────┘  └───────┬────────┘
        │                   │
        │                   │ Both use same config
        ▼                   ▼
    ┌────────────────────────────┐
    │    config/config.yaml      │
    │    (Single source)         │
    └────────────────────────────┘
        │
        │ Both use same memory routing
        ▼
    ┌────────────────────────────┐
    │    memory_router.py        │
    │    (Shared component)      │
    └────────────────────────────┘
```

### 2.2 Intelligent Launcher (run_proxies.py)

```python
#!/usr/bin/env python3
"""
Intelligent proxy launcher with feature toggle.

Environment Variables:
    USE_SDK_PROXY - Set to "true" to use SDK proxy (default: "false")
    PROXY_PORT - Port for the selected proxy (default: 8764)
    CONFIG_PATH - Path to config.yaml (default: "config/config.yaml")

Usage:
    # Binary proxy (default)
    python deploy/run_proxies.py

    # SDK proxy
    USE_SDK_PROXY=true python deploy/run_proxies.py

    # Both proxies simultaneously (testing)
    python deploy/run_proxies.py --run-both
"""

import os
import sys
import argparse
import subprocess
import asyncio
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

class ProxyLauncher:
    """Manages proxy selection and startup."""

    def __init__(
        self,
        use_sdk: bool = False,
        config_path: str = "config/config.yaml",
        port: int = 8764,
    ):
        self.use_sdk = use_sdk
        self.config_path = config_path
        self.port = port

    def launch_binary_proxy(self, port: int = 8764):
        """Launch binary-based proxy (existing implementation)."""
        logger.info(f"🚀 Launching BINARY proxy on port {port}")

        # Start LiteLLM binary first
        litellm_process = subprocess.Popen([
            "litellm",
            "--config", self.config_path,
            "--port", "4000",
            "--detailed_debug"
        ])

        # Wait for binary to be ready
        asyncio.run(self._wait_for_port(4000))

        # Start memory proxy
        from src.proxy.litellm_proxy_with_memory import create_app

        app = create_app(
            config_path=self.config_path,
            litellm_base_url="http://localhost:4000"
        )

        import uvicorn
        uvicorn.run(app, host="0.0.0.0", port=port)

    def launch_sdk_proxy(self, port: int = 8765):
        """Launch SDK-based proxy (new implementation)."""
        logger.info(f"🚀 Launching SDK proxy on port {port}")

        from src.proxy.litellm_proxy_sdk import create_app

        app = create_app(config_path=self.config_path)

        import uvicorn
        uvicorn.run(app, host="0.0.0.0", port=port)

    def launch_both(self):
        """Launch both proxies for side-by-side testing."""
        logger.info("🚀 Launching BOTH proxies (binary on 8764, SDK on 8765)")

        import multiprocessing

        # Binary proxy on 8764
        binary_process = multiprocessing.Process(
            target=self.launch_binary_proxy,
            args=(8764,)
        )

        # SDK proxy on 8765
        sdk_process = multiprocessing.Process(
            target=self.launch_sdk_proxy,
            args=(8765,)
        )

        binary_process.start()
        sdk_process.start()

        try:
            binary_process.join()
            sdk_process.join()
        except KeyboardInterrupt:
            logger.info("🛑 Shutting down both proxies")
            binary_process.terminate()
            sdk_process.terminate()

    async def _wait_for_port(self, port: int, timeout: int = 30):
        """Wait for port to be ready."""
        import httpx
        start_time = asyncio.get_event_loop().time()

        while True:
            try:
                async with httpx.AsyncClient() as client:
                    await client.get(f"http://localhost:{port}/health")
                logger.info(f"✅ Port {port} is ready")
                return
            except:
                if asyncio.get_event_loop().time() - start_time > timeout:
                    raise TimeoutError(f"Port {port} not ready after {timeout}s")
                await asyncio.sleep(1)

def main():
    parser = argparse.ArgumentParser(description="LiteLLM Proxy Launcher")
    parser.add_argument(
        "--use-sdk",
        action="store_true",
        default=os.getenv("USE_SDK_PROXY", "false").lower() == "true",
        help="Use SDK-based proxy (default: binary)"
    )
    parser.add_argument(
        "--run-both",
        action="store_true",
        help="Run both proxies for testing"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("PROXY_PORT", "8764")),
        help="Port for proxy (default: 8764)"
    )
    parser.add_argument(
        "--config",
        default=os.getenv("CONFIG_PATH", "config/config.yaml"),
        help="Path to config.yaml"
    )

    args = parser.parse_args()

    launcher = ProxyLauncher(
        use_sdk=args.use_sdk,
        config_path=args.config,
        port=args.port
    )

    if args.run_both:
        launcher.launch_both()
    elif args.use_sdk:
        launcher.launch_sdk_proxy(args.port)
    else:
        launcher.launch_binary_proxy(args.port)

if __name__ == "__main__":
    main()
```

### 2.3 Configuration Sharing

**Critical Design Decision**: Both proxies use **identical** `config/config.yaml`

**Why This Works**:
1. Binary proxy: Passes config to LiteLLM binary + uses memory routing
2. SDK proxy: Parses config + calls LiteLLM SDK + uses same memory routing
3. No conflicts: Both read-only access to same configuration

**Validation Script**:

```bash
#!/bin/bash
# validate_configs.sh

echo "Validating configuration compatibility..."

# Start binary proxy on 8764
USE_SDK_PROXY=false python deploy/run_proxies.py --port 8764 &
BINARY_PID=$!

# Wait for startup
sleep 5

# Test binary proxy
echo "Testing binary proxy..."
curl -s http://localhost:8764/memory-routing/info \
  -H "User-Agent: Test" | jq

# Start SDK proxy on 8765
USE_SDK_PROXY=true python deploy/run_proxies.py --port 8765 &
SDK_PID=$!

# Wait for startup
sleep 5

# Test SDK proxy
echo "Testing SDK proxy..."
curl -s http://localhost:8765/memory-routing/info \
  -H "User-Agent: Test" | jq

# Compare responses
echo "If both responses are identical, configuration is compatible ✅"

# Cleanup
kill $BINARY_PID $SDK_PID
```

---

## 3. Integration Points

### 3.1 Shared Components (100% Reuse)

#### 3.1.1 Memory Router (`memory_router.py`)

```python
# SHARED COMPONENT - NO MODIFICATIONS NEEDED
# Used by both binary and SDK proxies identically

from proxy.memory_router import MemoryRouter

# Binary proxy usage
memory_router = MemoryRouter(config)
user_id = memory_router.detect_user_id(request.headers)
# Inject into forwarded request

# SDK proxy usage (identical)
memory_router = MemoryRouter(config)
user_id = memory_router.detect_user_id(request.headers)
# Inject into litellm.acompletion() extra_headers
```

**Why No Changes**: Memory routing logic is independent of LiteLLM invocation mechanism.

#### 3.1.2 Schema (`schema.py`)

```python
# SHARED COMPONENT - NO MODIFICATIONS NEEDED
# Configuration schemas used by both

from proxy.schema import (
    LiteLLMProxyConfig,
    UserIDMappings,
    load_config_with_env_resolution
)

# Both proxies use same schema validation
config = load_config_with_env_resolution("config/config.yaml")
```

### 3.2 New SDK-Specific Components

#### 3.2.1 Config Parser (`src/proxy/config_parser.py`)

```python
"""
Configuration parser for SDK proxy.

Responsibilities:
- Parse config.yaml (reuses schema.py)
- Extract model-specific litellm_params
- Resolve environment variables
- Validate configuration
- Provide lookup methods for SDK calls
"""

from typing import Dict, Optional, Any
import os
import yaml
from dataclasses import dataclass

from proxy.schema import load_config_with_env_resolution, LiteLLMProxyConfig

@dataclass
class ModelConfig:
    """Model configuration for LiteLLM SDK."""
    model_name: str
    litellm_model: str  # e.g., "anthropic/claude-sonnet-4-5-20250929"
    api_base: Optional[str]
    api_key: Optional[str]
    extra_headers: Dict[str, str]
    custom_llm_provider: Optional[str]

class LiteLLMConfigParser:
    """
    Parses config.yaml for SDK proxy use.

    Pattern: Repository + Builder
    """

    def __init__(self, config_path: str):
        """Load and parse configuration."""
        self.config: LiteLLMProxyConfig = load_config_with_env_resolution(config_path)
        self._models: Dict[str, ModelConfig] = self._build_model_configs()

    def _build_model_configs(self) -> Dict[str, ModelConfig]:
        """Build ModelConfig objects from schema."""
        models = {}

        for model_entry in self.config.model_list:
            model_name = model_entry.model_name
            params = model_entry.litellm_params

            models[model_name] = ModelConfig(
                model_name=model_name,
                litellm_model=params.model,
                api_base=params.api_base,
                api_key=self._resolve_env_var(params.api_key),
                extra_headers=params.extra_headers or {},
                custom_llm_provider=params.custom_llm_provider
            )

        return models

    def get_model_config(self, model_name: str) -> Optional[ModelConfig]:
        """Get configuration for specific model."""
        return self._models.get(model_name)

    def get_litellm_params(self, model_name: str) -> Dict[str, Any]:
        """
        Get parameters ready for litellm.acompletion().

        Returns dict suitable for **kwargs unpacking.
        """
        model_config = self.get_model_config(model_name)
        if not model_config:
            raise ValueError(f"Model {model_name} not found in config")

        params = {
            "model": model_config.litellm_model,
        }

        if model_config.api_base:
            params["api_base"] = model_config.api_base

        if model_config.api_key:
            params["api_key"] = model_config.api_key

        if model_config.extra_headers:
            params["extra_headers"] = model_config.extra_headers.copy()

        return params

    def _resolve_env_var(self, value: Optional[str]) -> Optional[str]:
        """Resolve os.environ/VAR_NAME references."""
        if not value:
            return None

        if value.startswith("os.environ/"):
            env_var = value.replace("os.environ/", "")
            resolved = os.getenv(env_var)
            if not resolved:
                raise ValueError(f"Environment variable {env_var} not set")
            return resolved

        return value
```

#### 3.2.2 Session Manager (`src/proxy/session_manager.py`)

```python
"""
Persistent HTTP session manager for LiteLLM SDK.

Critical for Cloudflare cookie persistence.
"""

import asyncio
import logging
from typing import Optional
import httpx
import litellm

logger = logging.getLogger(__name__)

class LiteLLMSessionManager:
    """
    Manages global persistent httpx.AsyncClient for LiteLLM SDK.

    Pattern: Singleton with lazy initialization
    Thread-safe: Uses asyncio.Lock

    CRITICAL: This client is injected into litellm.aclient_session
    to ensure Cloudflare cookies persist across requests.
    """

    _client: Optional[httpx.AsyncClient] = None
    _lock = asyncio.Lock()

    @classmethod
    async def get_client(cls) -> httpx.AsyncClient:
        """
        Get or create persistent httpx client.

        Thread-safe lazy initialization.
        """
        async with cls._lock:
            if cls._client is None:
                cls._client = httpx.AsyncClient(
                    timeout=httpx.Timeout(600.0),
                    follow_redirects=True,
                    limits=httpx.Limits(
                        max_connections=100,
                        max_keepalive_connections=20
                    )
                )

                # CRITICAL: Inject into LiteLLM SDK
                litellm.aclient_session = cls._client

                logger.info("🍪 Created persistent httpx.AsyncClient for LiteLLM SDK")
                logger.info(f"   Max connections: 100")
                logger.info(f"   Keepalive connections: 20")
                logger.info(f"   Timeout: 600s")

            return cls._client

    @classmethod
    async def close(cls):
        """
        Close persistent client.

        Called during application shutdown.
        Idempotent: Safe to call multiple times.
        """
        if cls._client:
            await cls._client.aclose()
            cls._client = None
            litellm.aclient_session = None
            logger.info("🔒 Closed persistent httpx client")

    @classmethod
    def get_cookie_count(cls) -> int:
        """Get number of cookies in session (for debugging)."""
        if cls._client:
            return len(cls._client.cookies)
        return 0

    @classmethod
    def get_cookie_names(cls) -> list[str]:
        """Get cookie names (for debugging)."""
        if cls._client:
            return list(cls._client.cookies.keys())
        return []
```

#### 3.2.3 Error Handlers (`src/proxy/error_handlers.py`)

```python
"""
Error handling utilities for SDK proxy.

Provides structured error responses and exception mapping.
"""

import logging
from typing import Dict, Any, Optional
from fastapi.responses import JSONResponse
import litellm

logger = logging.getLogger(__name__)

class ErrorResponse:
    """Structured error response builder."""

    @staticmethod
    def build(
        status_code: int,
        error_type: str,
        message: str,
        details: Optional[str] = None,
        retry_after: Optional[int] = None
    ) -> JSONResponse:
        """Build standardized error response."""
        content = {
            "error": {
                "type": error_type,
                "message": message,
            }
        }

        if details:
            content["error"]["details"] = details

        if retry_after:
            content["error"]["retry_after"] = retry_after

        return JSONResponse(
            content=content,
            status_code=status_code
        )

def handle_litellm_error(
    e: Exception,
    request_id: Optional[str] = None,
    include_debug_info: bool = False
) -> JSONResponse:
    """
    Map LiteLLM exceptions to appropriate HTTP responses.

    Comprehensive exception handling for all LiteLLM error types.
    """

    # Add request_id to all logs if available
    log_extra = {"request_id": request_id} if request_id else {}

    if isinstance(e, litellm.exceptions.ServiceUnavailableError):
        logger.error(f"503 Service Unavailable: {e}", extra=log_extra)
        return ErrorResponse.build(
            status_code=503,
            error_type="service_unavailable",
            message="Upstream service temporarily unavailable",
            details=str(e) if include_debug_info else None
        )

    elif isinstance(e, litellm.exceptions.RateLimitError):
        logger.error(f"429 Rate Limited: {e}", extra=log_extra)
        retry_after = getattr(e, "retry_after", None)
        return ErrorResponse.build(
            status_code=429,
            error_type="rate_limit_error",
            message="Rate limit exceeded",
            retry_after=retry_after
        )

    elif isinstance(e, litellm.exceptions.AuthenticationError):
        logger.error(f"401 Authentication Error: {e}", extra=log_extra)
        return ErrorResponse.build(
            status_code=401,
            error_type="authentication_error",
            message="Invalid API key or authentication failed"
        )

    elif isinstance(e, litellm.exceptions.InvalidRequestError):
        logger.error(f"400 Invalid Request: {e}", extra=log_extra)
        return ErrorResponse.build(
            status_code=400,
            error_type="invalid_request_error",
            message=str(e)
        )

    else:
        logger.exception(f"Unexpected error: {type(e).__name__}", extra=log_extra)
        return ErrorResponse.build(
            status_code=500,
            error_type="internal_error",
            message="Internal server error",
            details=str(e) if include_debug_info else None
        )
```

#### 3.2.4 Streaming Utils (`src/proxy/streaming_utils.py`)

```python
"""
SSE streaming utilities for SDK proxy.
"""

import json
import logging
from typing import AsyncIterator

logger = logging.getLogger(__name__)

async def stream_generator(
    response_iterator: AsyncIterator,
    request_id: str
) -> AsyncIterator[str]:
    """
    Convert LiteLLM streaming response to SSE format.

    Args:
        response_iterator: LiteLLM streaming response
        request_id: Request ID for logging

    Yields:
        SSE-formatted chunks: "data: {json}\n\n"
    """
    try:
        async for chunk in response_iterator:
            if hasattr(chunk, "model_dump"):
                data = chunk.model_dump()
            elif hasattr(chunk, "dict"):
                data = chunk.dict()
            else:
                data = chunk

            # SSE format: "data: {json}\n\n"
            yield f"data: {json.dumps(data)}\n\n"

        # Send [DONE] marker
        yield "data: [DONE]\n\n"

    except Exception as e:
        logger.exception(f"Error in streaming: {e}", extra={"request_id": request_id})
        error_data = {
            "error": {
                "type": "streaming_error",
                "message": str(e)
            }
        }
        yield f"data: {json.dumps(error_data)}\n\n"
```

### 3.3 Component Dependency Graph

```
┌─────────────────────────────────────────────────────────┐
│                Binary Proxy (Untouched)                 │
│         litellm_proxy_with_memory.py                    │
└───────────────┬─────────────────────────────────────────┘
                │
                ├──> memory_router.py (SHARED)
                ├──> schema.py (SHARED)
                └──> config.yaml (SHARED)


┌─────────────────────────────────────────────────────────┐
│                SDK Proxy (New)                          │
│            litellm_proxy_sdk.py                         │
└───────────────┬─────────────────────────────────────────┘
                │
                ├──> config_parser.py (NEW)
                │       └──> schema.py (SHARED)
                │
                ├──> session_manager.py (NEW)
                │       └──> litellm SDK
                │
                ├──> error_handlers.py (NEW)
                │
                ├──> streaming_utils.py (NEW)
                │
                ├──> memory_router.py (SHARED)
                │
                └──> config.yaml (SHARED)
```

**Key Insight**: SDK proxy has **MORE dependencies** but NO impact on binary proxy.

---

## 4. Rollout Phases

### Phase 1: SDK Implementation (Day 1-2)

**Goal**: Complete SDK proxy implementation in parallel directory structure

#### Day 1 Morning (4 hours)

**Tasks**:
1. ✅ Create `src/proxy/config_parser.py`
   - Implement `LiteLLMConfigParser` class
   - Implement `ModelConfig` dataclass
   - Add environment variable resolution
   - Add validation logic

2. ✅ Create `src/proxy/session_manager.py`
   - Implement `LiteLLMSessionManager` singleton
   - Add httpx.AsyncClient configuration
   - Add litellm.aclient_session injection
   - Add cookie debugging helpers

3. ✅ Create `src/proxy/error_handlers.py`
   - Implement `ErrorResponse` builder
   - Implement `handle_litellm_error()` function
   - Add comprehensive exception mapping

4. ✅ Create `src/proxy/streaming_utils.py`
   - Implement `stream_generator()` async generator
   - Add SSE formatting
   - Add error handling in streams

**Validation**: All new modules have unit tests

#### Day 1 Afternoon (4 hours)

**Tasks**:
1. ✅ Complete `src/proxy/litellm_proxy_sdk.py`
   - Implement `lifespan()` context manager
   - Implement `/v1/chat/completions` endpoint
   - Implement `/v1/models` endpoint
   - Implement `/health` and `/memory-routing/info` endpoints

2. ✅ Integrate new components
   - Wire config_parser into app.state
   - Wire session_manager into startup
   - Wire memory_router (reuse existing)
   - Add error handling to all endpoints

3. ✅ Test basic functionality
   - Non-streaming completions
   - Health checks
   - Memory routing

**Validation**: SDK proxy starts and responds to curl requests

#### Day 2 Morning (4 hours)

**Tasks**:
1. ✅ Implement streaming support
   - Wire streaming_utils into completions endpoint
   - Test with stream=true requests
   - Validate SSE format

2. ✅ Implement graceful shutdown
   - Ensure session_manager.close() called
   - Test signal handling (SIGTERM, SIGINT)
   - Verify no resource leaks

3. ✅ Add comprehensive logging
   - Request/response logging
   - Cookie state logging (for debugging)
   - Error context logging

**Validation**: Streaming works, shutdown is clean

#### Day 2 Afternoon (4 hours)

**Tasks**:
1. ✅ Create launcher enhancements
   - Update `deploy/run_proxies.py` with feature toggle
   - Create `deploy/start_sdk_proxy.py`
   - Create `deploy/start_binary_proxy.py`
   - Add `--run-both` option

2. ✅ Create test scripts
   - `tests/test_sdk_proxy.py` - SDK unit tests
   - `tests/test_config_parser.py` - Config parser tests
   - `tests/test_session_manager.py` - Session tests
   - `tests/test_integration_both.py` - Side-by-side comparison

3. ✅ Documentation
   - Update CLAUDE.md with SDK proxy instructions
   - Create SDK_PROXY_USAGE.md

**Validation**: Both proxies can run simultaneously

---

### Phase 2: Feature Parity Validation (Day 3 Morning)

**Goal**: Ensure SDK proxy has 100% feature parity with binary proxy

#### Feature Checklist

| Feature | Binary Proxy | SDK Proxy | Test |
|---------|-------------|-----------|------|
| Non-streaming chat | ✅ Works | ⏳ Test | Side-by-side |
| Streaming chat | ✅ Works | ⏳ Test | Side-by-side |
| Model listing | ✅ Works | ⏳ Test | `/v1/models` |
| Memory routing | ✅ Works | ⏳ Test | User-Agent detection |
| Health checks | ✅ Works | ⏳ Test | `/health` |
| Error handling | ✅ Works | ⏳ Test | Invalid requests |
| Anthropic thinking | ✅ Works | ⏳ Test | With thinking param |
| Custom headers | ✅ Works | ⏳ Test | `anthropic-beta` |
| Temperature | ✅ Works | ⏳ Test | Parameter passing |
| Max tokens | ✅ Works | ⏳ Test | Parameter passing |

#### Validation Script

```bash
#!/bin/bash
# tests/validate_feature_parity.sh

echo "🔍 Validating feature parity between binary and SDK proxies"

# Start both proxies
echo "Starting proxies..."
python deploy/run_proxies.py --run-both &
LAUNCHER_PID=$!

sleep 10  # Wait for startup

# Test 1: Non-streaming chat
echo "Test 1: Non-streaming chat"
BINARY_RESPONSE=$(curl -s http://localhost:8764/v1/chat/completions \
  -H "Authorization: Bearer sk-1234" \
  -d '{"model":"claude-sonnet-4.5","messages":[{"role":"user","content":"Hi"}],"max_tokens":10}')

SDK_RESPONSE=$(curl -s http://localhost:8765/v1/chat/completions \
  -H "Authorization: Bearer sk-1234" \
  -d '{"model":"claude-sonnet-4.5","messages":[{"role":"user","content":"Hi"}],"max_tokens":10}')

echo "Binary response: $BINARY_RESPONSE"
echo "SDK response: $SDK_RESPONSE"

# Test 2: Streaming chat
echo "Test 2: Streaming chat"
curl -s http://localhost:8764/v1/chat/completions \
  -H "Authorization: Bearer sk-1234" \
  -d '{"model":"claude-sonnet-4.5","messages":[{"role":"user","content":"Count to 5"}],"stream":true,"max_tokens":50}' \
  > /tmp/binary_stream.txt

curl -s http://localhost:8765/v1/chat/completions \
  -H "Authorization: Bearer sk-1234" \
  -d '{"model":"claude-sonnet-4.5","messages":[{"role":"user","content":"Count to 5"}],"stream":true,"max_tokens":50}' \
  > /tmp/sdk_stream.txt

echo "Binary stream chunks: $(grep -c 'data:' /tmp/binary_stream.txt)"
echo "SDK stream chunks: $(grep -c 'data:' /tmp/sdk_stream.txt)"

# Test 3: Memory routing
echo "Test 3: Memory routing"
BINARY_ROUTING=$(curl -s http://localhost:8764/memory-routing/info \
  -H "User-Agent: OpenAIClientImpl/Java")

SDK_ROUTING=$(curl -s http://localhost:8765/memory-routing/info \
  -H "User-Agent: OpenAIClientImpl/Java")

echo "Binary routing: $BINARY_ROUTING"
echo "SDK routing: $SDK_ROUTING"

# Cleanup
kill $LAUNCHER_PID
echo "✅ Feature parity validation complete"
```

---

### Phase 3: Client Testing (Day 3 Afternoon)

**Goal**: Test SDK proxy with real AI clients

#### Client Test Matrix

| Client | Port | Expected Behavior | Validation |
|--------|------|-------------------|------------|
| PyCharm AI | 8765 | Completions work | Generate code |
| Claude Code | 8765 | Long conversations work | Multi-turn |
| curl | 8765 | Direct API calls work | Basic smoke test |
| httpx script | 8765 | Concurrent requests work | Load test |

#### PyCharm AI Configuration

```
Settings → AI Assistant → OpenAI Service
- URL: http://localhost:8765/v1
- API Key: sk-1234 (from config.yaml)
- Model: claude-sonnet-4.5

Test:
1. Open any Python file
2. Ask AI Assistant: "Explain this function"
3. Verify response is coherent
4. Check logs for cookie persistence (no 503 errors)
```

#### Claude Code Configuration

```bash
# In your shell config (.zshrc or .bashrc)
export ANTHROPIC_BASE_URL="http://localhost:8765"

# Test
claude code
> What is the purpose of memory_router.py?

# Verify response
# Check logs for user_id detection
```

#### Load Test Script

```python
#!/usr/bin/env python3
"""
Load test SDK proxy with concurrent requests.

Usage:
    python tests/load_test_sdk.py --num-requests 100 --port 8765
"""

import asyncio
import argparse
import time
from typing import List
import httpx

async def make_completion_request(
    client: httpx.AsyncClient,
    port: int,
    request_id: int
) -> dict:
    """Make a single completion request."""
    try:
        response = await client.post(
            f"http://localhost:{port}/v1/chat/completions",
            json={
                "model": "claude-sonnet-4.5",
                "messages": [
                    {"role": "user", "content": f"Test request {request_id}"}
                ],
                "max_tokens": 10
            },
            headers={"Authorization": "Bearer sk-1234"},
            timeout=60.0
        )
        return {
            "request_id": request_id,
            "status": response.status_code,
            "success": response.status_code == 200
        }
    except Exception as e:
        return {
            "request_id": request_id,
            "status": 0,
            "success": False,
            "error": str(e)
        }

async def load_test(port: int, num_requests: int):
    """Run load test with concurrent requests."""
    print(f"🚀 Starting load test with {num_requests} concurrent requests")
    print(f"   Target: http://localhost:{port}")

    async with httpx.AsyncClient() as client:
        tasks = [
            make_completion_request(client, port, i)
            for i in range(num_requests)
        ]

        start_time = time.time()
        results = await asyncio.gather(*tasks)
        duration = time.time() - start_time

        successes = sum(1 for r in results if r["success"])
        failures = num_requests - successes

        print(f"\n📊 Results:")
        print(f"   Duration: {duration:.2f}s")
        print(f"   Throughput: {num_requests/duration:.2f} req/s")
        print(f"   Success rate: {successes/num_requests*100:.1f}%")
        print(f"   Successes: {successes}")
        print(f"   Failures: {failures}")

        if failures > 0:
            print(f"\n❌ Failed requests:")
            for r in results:
                if not r["success"]:
                    print(f"   Request {r['request_id']}: {r.get('error', 'Unknown error')}")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--num-requests", type=int, default=50)
    args = parser.parse_args()

    asyncio.run(load_test(args.port, args.num_requests))

if __name__ == "__main__":
    main()
```

---

### Phase 4: Cutover and Monitoring (Day 4)

**Goal**: Make SDK proxy the default, monitor for issues

#### Cutover Steps

1. **Update default in run_proxies.py**:

```python
# Change default from binary to SDK
USE_SDK_PROXY = os.getenv("USE_SDK_PROXY", "true")  # Changed from "false"
```

2. **Update documentation**:
   - CLAUDE.md: Update proxy instructions
   - README.md: Update quick start
   - Add migration notes

3. **Create rollback script**:

```bash
#!/bin/bash
# rollback_to_binary.sh

echo "🔄 Rolling back to binary proxy..."

# Stop SDK proxy
pkill -f "litellm_proxy_sdk"

# Start binary proxy
USE_SDK_PROXY=false python deploy/run_proxies.py --port 8764

echo "✅ Rollback complete - binary proxy running on 8764"
```

4. **Archive binary proxy**:

```bash
mkdir -p src/proxy/archive
mv src/proxy/litellm_proxy_with_memory.py src/proxy/archive/
echo "Preserved for rollback - DO NOT DELETE" > src/proxy/archive/README.md
```

#### Monitoring Plan

**Metrics to Track**:
- Error rate (should decrease due to cookie persistence)
- Response latency (should decrease due to no extra hop)
- Memory usage (should be similar or lower)
- Cookie persistence (no 503 errors from Cloudflare)
- Client satisfaction (PyCharm, Claude Code users)

**Monitoring Script**:

```bash
#!/bin/bash
# monitor_sdk_proxy.sh

echo "📊 Monitoring SDK proxy..."

while true; do
    # Check health
    HEALTH=$(curl -s http://localhost:8764/health)
    echo "Health: $HEALTH"

    # Check logs for errors
    ERROR_COUNT=$(tail -100 /var/log/litellm_proxy.log | grep -c ERROR)
    echo "Recent errors: $ERROR_COUNT"

    # Check for 503 errors (Cloudflare issues)
    CLOUDFLARE_ERRORS=$(tail -100 /var/log/litellm_proxy.log | grep -c "503")
    echo "Cloudflare 503s: $CLOUDFLARE_ERRORS"

    sleep 60
done
```

---

## 5. Risk Mitigation

### 5.1 Risk Assessment Matrix

| Risk | Likelihood | Impact | Mitigation Strategy |
|------|-----------|--------|---------------------|
| **SDK bugs** | Medium | High | POC validated; extensive testing; easy rollback |
| **Performance degradation** | Low | Medium | Load testing; compare benchmarks; optimize if needed |
| **Client compatibility issues** | Low | High | Test with all clients before cutover; gradual rollout |
| **Configuration incompatibility** | Very Low | Medium | Same config.yaml; validation script |
| **Cookie persistence doesn't work** | Very Low | High | POC proved it works; monitor in production |
| **Binary proxy broken by changes** | Very Low | Critical | **ZERO changes to binary proxy** |

### 5.2 Rollback Strategy

#### Immediate Rollback (< 5 minutes)

```bash
# If SDK proxy has critical issues

# Option 1: Via environment variable
USE_SDK_PROXY=false python deploy/run_proxies.py

# Option 2: Via rollback script
./rollback_to_binary.sh

# Option 3: Manual
pkill -f litellm_proxy_sdk
python src/proxy/archive/litellm_proxy_with_memory.py
```

#### Gradual Rollback (Partial)

```bash
# Route only specific clients to binary proxy temporarily

# Client 1: PyCharm → SDK proxy (8765)
# Client 2: Claude Code → Binary proxy (8764)

# Both proxies running simultaneously
python deploy/run_proxies.py --run-both
```

### 5.3 Feature Flags

```python
# In config.yaml (optional)
general_settings:
  experimental:
    use_sdk_proxy: true  # Feature flag
    sdk_proxy_port: 8765
    binary_proxy_port: 8764
```

### 5.4 Circuit Breaker Pattern

```python
# Add to SDK proxy for automatic failover

class CircuitBreaker:
    """Automatically failover to binary proxy if SDK fails repeatedly."""

    def __init__(self, failure_threshold: int = 5):
        self.failure_count = 0
        self.failure_threshold = failure_threshold
        self.is_open = False

    async def call(self, func, *args, **kwargs):
        if self.is_open:
            raise Exception("Circuit breaker open - failover to binary proxy")

        try:
            result = await func(*args, **kwargs)
            self.failure_count = 0  # Reset on success
            return result
        except Exception as e:
            self.failure_count += 1
            if self.failure_count >= self.failure_threshold:
                self.is_open = True
                logger.critical("Circuit breaker opened - too many failures")
            raise
```

---

## 6. Component Architecture

### 6.1 SDK Proxy Architecture Diagram

```
┌────────────────────────────────────────────────────────────────┐
│                    FastAPI Application                         │
│                  (litellm_proxy_sdk.py)                        │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │                  Lifespan Context Manager                 │ │
│  │                                                            │ │
│  │  Startup:                                                  │ │
│  │  1. Load configuration (config_parser)                    │ │
│  │  2. Initialize session manager                            │ │
│  │  3. Inject httpx client into litellm.aclient_session     │ │
│  │  4. Initialize memory router                              │ │
│  │                                                            │ │
│  │  Shutdown:                                                 │ │
│  │  1. Close session manager                                 │ │
│  │  2. Cleanup resources                                      │ │
│  └──────────────────────────────────────────────────────────┘ │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │              Request Handling Pipeline                    │ │
│  │                                                            │ │
│  │  1. Parse request body                                    │ │
│  │  2. Detect user ID (memory_router)                       │ │
│  │  3. Get model config (config_parser)                     │ │
│  │  4. Prepare headers (inject x-sm-user-id)               │ │
│  │  5. Call litellm.acompletion()                           │ │
│  │  6. Handle response (streaming or non-streaming)         │ │
│  │  7. Error handling (error_handlers)                      │ │
│  └──────────────────────────────────────────────────────────┘ │
│                                                                 │
│  Endpoints:                                                     │
│  • POST /v1/chat/completions - Main completion endpoint       │
│  • GET /v1/models - List available models                     │
│  • GET /health - Health check                                 │
│  • GET /memory-routing/info - Debug routing                   │
└────────────────────────────────────────────────────────────────┘
         │                  │                  │
         │                  │                  │
         ▼                  ▼                  ▼
┌─────────────────┐  ┌─────────────┐  ┌──────────────┐
│ config_parser   │  │session_mgr  │  │memory_router │
│ (NEW)           │  │(NEW)        │  │(SHARED)      │
└─────────────────┘  └─────────────┘  └──────────────┘
         │                  │                  │
         ▼                  ▼                  ▼
┌─────────────────┐  ┌─────────────┐  ┌──────────────┐
│  schema.py      │  │litellm SDK  │  │  config.yaml │
│  (SHARED)       │  │+ httpx      │  │  (SHARED)    │
└─────────────────┘  └─────────────┘  └──────────────┘
```

### 6.2 Binary Proxy Architecture (Unchanged)

```
┌────────────────────────────────────────────────────────────────┐
│                    FastAPI Application                         │
│              (litellm_proxy_with_memory.py)                    │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │              Request Handling Pipeline                    │ │
│  │                                                            │ │
│  │  1. Parse request                                         │ │
│  │  2. Detect user ID (memory_router)                       │ │
│  │  3. Inject x-sm-user-id header                           │ │
│  │  4. Forward to LiteLLM binary (localhost:4000)           │ │
│  │  5. Return response                                       │ │
│  └──────────────────────────────────────────────────────────┘ │
│                                                                 │
│  Endpoints:                                                     │
│  • /{path:path} - Catch-all proxy endpoint                    │
│  • GET /health - Health check                                 │
│  • GET /memory-routing/info - Debug routing                   │
└────────────────────────────────────────────────────────────────┘
         │                  │
         ▼                  ▼
┌──────────────┐  ┌──────────────┐
│memory_router │  │  config.yaml │
│(SHARED)      │  │  (SHARED)    │
└──────────────┘  └──────────────┘
         │
         ▼
┌─────────────────────────────────────┐
│   LiteLLM Binary (Port 4000)        │
│   (External process)                │
└─────────────────────────────────────┘
```

### 6.3 Shared Components

```
┌─────────────────────────────────────────────────┐
│           Shared Components (Read-Only)         │
│                                                  │
│  ┌────────────────────────────────────────────┐ │
│  │         memory_router.py                   │ │
│  │  - Client detection via User-Agent         │ │
│  │  - Pattern matching (regex)                │ │
│  │  - User ID assignment                      │ │
│  │  - Custom header detection                 │ │
│  └────────────────────────────────────────────┘ │
│                                                  │
│  ┌────────────────────────────────────────────┐ │
│  │         schema.py                          │ │
│  │  - Configuration data models               │ │
│  │  - Pydantic schemas                        │ │
│  │  - Environment variable resolution         │ │
│  │  - Config validation                       │ │
│  └────────────────────────────────────────────┘ │
│                                                  │
│  ┌────────────────────────────────────────────┐ │
│  │         config/config.yaml                 │ │
│  │  - Model definitions                       │ │
│  │  - API keys (via env vars)                 │ │
│  │  - Memory routing patterns                 │ │
│  │  - LiteLLM settings                        │ │
│  └────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────┘
          │                    │
          │                    │
          ▼                    ▼
┌──────────────────┐  ┌──────────────────┐
│  Binary Proxy    │  │    SDK Proxy     │
│  (Unchanged)     │  │    (New)         │
└──────────────────┘  └──────────────────┘
```

---

## 7. Testing Strategy

### 7.1 Test Pyramid

```
              ┌─────────────┐
              │   E2E Tests │  (10% - Slow, comprehensive)
              │   Both      │
              │   Proxies   │
              └─────────────┘
                    ▲
            ┌───────────────┐
            │  Integration  │  (30% - Medium speed)
            │  Tests        │
            │  Per Proxy    │
            └───────────────┘
                    ▲
        ┌─────────────────────┐
        │    Unit Tests       │  (60% - Fast, focused)
        │    Per Component    │
        └─────────────────────┘
```

### 7.2 Test Coverage Matrix

| Component | Unit Tests | Integration Tests | E2E Tests |
|-----------|-----------|------------------|-----------|
| **config_parser** | ✅ Parse config<br>✅ Resolve env vars<br>✅ Validation | ✅ Load from file | N/A |
| **session_manager** | ✅ Singleton behavior<br>✅ Client creation<br>✅ Cleanup | ✅ LiteLLM injection | ✅ Cookie persistence |
| **error_handlers** | ✅ Exception mapping<br>✅ Response format | N/A | N/A |
| **streaming_utils** | ✅ SSE formatting<br>✅ Chunk handling | ✅ Stream generation | ✅ Streaming completions |
| **memory_router** | ✅ Pattern matching<br>✅ User ID detection | ✅ Header parsing | ✅ Client isolation |
| **SDK proxy** | N/A | ✅ All endpoints<br>✅ Error cases | ✅ Full workflow |
| **Binary proxy** | N/A | ✅ Existing tests | ✅ Full workflow |
| **Both proxies** | N/A | N/A | ✅ Side-by-side<br>✅ Feature parity |

### 7.3 Test Scripts

#### Unit Tests (`tests/test_config_parser.py`)

```python
import pytest
from src.proxy.config_parser import LiteLLMConfigParser, ModelConfig

def test_parse_config():
    """Test config parsing."""
    parser = LiteLLMConfigParser("config/config.yaml")

    # Test model lookup
    model = parser.get_model_config("claude-sonnet-4.5")
    assert model is not None
    assert model.model_name == "claude-sonnet-4.5"
    assert "anthropic" in model.litellm_model

def test_get_litellm_params():
    """Test parameter extraction for SDK."""
    parser = LiteLLMConfigParser("config/config.yaml")

    params = parser.get_litellm_params("claude-sonnet-4.5")

    assert "model" in params
    assert "api_base" in params
    assert "api_key" in params
    assert "anthropic" in params["model"]

def test_env_var_resolution():
    """Test environment variable resolution."""
    import os
    os.environ["TEST_API_KEY"] = "sk-test-123"

    # Mock config with os.environ reference
    # ... test resolution logic

    del os.environ["TEST_API_KEY"]
```

#### Integration Tests (`tests/test_sdk_proxy_integration.py`)

```python
import pytest
import httpx
from src.proxy.litellm_proxy_sdk import create_app

@pytest.fixture
def client():
    """Create test client."""
    app = create_app(config_path="config/config.yaml")
    return httpx.AsyncClient(app=app, base_url="http://test")

@pytest.mark.asyncio
async def test_chat_completions_non_streaming(client):
    """Test non-streaming completions."""
    response = await client.post(
        "/v1/chat/completions",
        json={
            "model": "claude-sonnet-4.5",
            "messages": [{"role": "user", "content": "Test"}],
            "max_tokens": 10
        },
        headers={"Authorization": "Bearer sk-1234"}
    )

    assert response.status_code == 200
    data = response.json()
    assert "choices" in data
    assert len(data["choices"]) > 0

@pytest.mark.asyncio
async def test_chat_completions_streaming(client):
    """Test streaming completions."""
    async with client.stream(
        "POST",
        "/v1/chat/completions",
        json={
            "model": "claude-sonnet-4.5",
            "messages": [{"role": "user", "content": "Count to 3"}],
            "stream": True,
            "max_tokens": 50
        },
        headers={"Authorization": "Bearer sk-1234"}
    ) as response:
        assert response.status_code == 200

        chunks = []
        async for line in response.aiter_lines():
            if line.startswith("data: "):
                chunks.append(line)

        assert len(chunks) > 0
        assert any("[DONE]" in chunk for chunk in chunks)

@pytest.mark.asyncio
async def test_memory_routing(client):
    """Test memory routing detection."""
    response = await client.get(
        "/memory-routing/info",
        headers={"User-Agent": "OpenAIClientImpl/Java"}
    )

    assert response.status_code == 200
    data = response.json()
    assert data["user_id"] == "pycharm-ai"
```

#### E2E Tests (`tests/test_both_proxies_e2e.py`)

```python
import pytest
import httpx
import subprocess
import time

@pytest.fixture(scope="module")
def both_proxies():
    """Start both proxies for comparison."""
    # Start both proxies
    process = subprocess.Popen([
        "python", "deploy/run_proxies.py", "--run-both"
    ])

    time.sleep(10)  # Wait for startup

    yield {
        "binary_url": "http://localhost:8764",
        "sdk_url": "http://localhost:8765"
    }

    process.terminate()
    process.wait()

@pytest.mark.asyncio
async def test_feature_parity(both_proxies):
    """Test that both proxies produce equivalent results."""
    test_request = {
        "model": "claude-sonnet-4.5",
        "messages": [{"role": "user", "content": "Say 'test'"}],
        "max_tokens": 10
    }

    async with httpx.AsyncClient() as client:
        # Binary proxy
        binary_response = await client.post(
            f"{both_proxies['binary_url']}/v1/chat/completions",
            json=test_request,
            headers={"Authorization": "Bearer sk-1234"}
        )

        # SDK proxy
        sdk_response = await client.post(
            f"{both_proxies['sdk_url']}/v1/chat/completions",
            json=test_request,
            headers={"Authorization": "Bearer sk-1234"}
        )

        # Both should succeed
        assert binary_response.status_code == 200
        assert sdk_response.status_code == 200

        # Both should have similar structure
        binary_data = binary_response.json()
        sdk_data = sdk_response.json()

        assert "choices" in binary_data
        assert "choices" in sdk_data
```

---

## 8. Monitoring and Observability

### 8.1 Logging Strategy

**Log Levels**:
- `DEBUG`: Cookie state, session details, config parsing
- `INFO`: Request start/complete, routing decisions, startup/shutdown
- `WARNING`: Retries, fallbacks, deprecated usage
- `ERROR`: Request failures, SDK errors, configuration issues
- `CRITICAL`: Circuit breaker open, service unavailable

**Structured Logging Format**:

```python
{
    "timestamp": "2025-11-02T10:30:45.123Z",
    "level": "INFO",
    "component": "sdk_proxy",
    "event": "request_completed",
    "request_id": "req_abc123",
    "user_id": "pycharm-ai",
    "model": "claude-sonnet-4.5",
    "duration_ms": 234,
    "tokens": 150,
    "status": "success"
}
```

### 8.2 Metrics to Track

**Performance Metrics**:
- Request latency (p50, p95, p99)
- Throughput (requests/second)
- Error rate (%)
- Success rate (%)

**Resource Metrics**:
- Memory usage (MB)
- CPU usage (%)
- Connection pool utilization (%)
- Cookie count (for debugging)

**Business Metrics**:
- Requests by client (PyCharm, Claude Code, etc.)
- Requests by model
- Token usage
- Cost estimation

### 8.3 Health Checks

```python
@app.get("/health")
async def health_check():
    """Comprehensive health check."""
    checks = {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "checks": {}
    }

    # Check 1: Session manager
    try:
        client = await LiteLLMSessionManager.get_client()
        checks["checks"]["session_manager"] = {
            "status": "healthy",
            "cookie_count": len(client.cookies)
        }
    except Exception as e:
        checks["checks"]["session_manager"] = {
            "status": "unhealthy",
            "error": str(e)
        }
        checks["status"] = "degraded"

    # Check 2: Configuration
    try:
        config = app.state.litellm_config
        model_count = len(config._models)
        checks["checks"]["configuration"] = {
            "status": "healthy",
            "model_count": model_count
        }
    except Exception as e:
        checks["checks"]["configuration"] = {
            "status": "unhealthy",
            "error": str(e)
        }
        checks["status"] = "unhealthy"

    # Check 3: Memory router
    try:
        router = app.state.memory_router
        checks["checks"]["memory_router"] = {
            "status": "healthy",
            "pattern_count": len(router.header_patterns)
        }
    except Exception as e:
        checks["checks"]["memory_router"] = {
            "status": "unhealthy",
            "error": str(e)
        }
        checks["status"] = "unhealthy"

    status_code = 200 if checks["status"] == "healthy" else 503
    return JSONResponse(content=checks, status_code=status_code)
```

---

## Conclusion

This incremental rollout architecture provides a **comprehensive, low-risk migration path** from binary to SDK-based LiteLLM proxy. Key principles:

1. **Non-Destructive**: Binary proxy remains completely untouched
2. **Parallel**: Both proxies coexist during migration for testing
3. **Reversible**: Easy rollback via environment variable or script
4. **Validated**: POC already proved the approach works
5. **Monitored**: Comprehensive logging and health checks

**Next Steps**:
1. Review and approve this architecture
2. Begin Phase 1 implementation (Day 1-2)
3. Progressive testing and validation (Day 3)
4. Cutover with monitoring (Day 4)

**Success Criteria**:
- ✅ Both proxies operational simultaneously
- ✅ SDK proxy achieves feature parity
- ✅ All clients (PyCharm, Claude Code) work with SDK proxy
- ✅ Cookie persistence eliminates Cloudflare 503 errors
- ✅ Performance meets or exceeds binary proxy
- ✅ Easy rollback mechanism validated

---

**Document Status**: Complete and ready for implementation
**Last Updated**: 2025-11-02
**Reviewers**: TBD
**Approvers**: TBD