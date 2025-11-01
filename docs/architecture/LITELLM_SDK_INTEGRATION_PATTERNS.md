# LiteLLM SDK Integration Patterns and Best Practices

**Document Type**: Research Report
**Created**: 2025-11-02
**Last Updated**: 2025-11-02
**Status**: Complete
**Purpose**: Practical implementation patterns for LiteLLM SDK integration with FastAPI

---

## Document Overview

This document provides researched best practices and working patterns for integrating LiteLLM SDK within a FastAPI application. It complements the existing SDK migration documentation with specific implementation details, code examples, and authoritative references from official documentation and real-world implementations.

**Target Audience**: Developers implementing `litellm_proxy_sdk.py`

**Research Sources**:
- LiteLLM official documentation (docs.litellm.ai)
- FastAPI official documentation (fastapi.tiangolo.com)
- httpx documentation and GitHub discussions
- Cloudflare developer documentation
- Real-world GitHub implementations

---

## Table of Contents

1. [LiteLLM SDK Session Management](#1-litellm-sdk-session-management)
2. [FastAPI + LiteLLM Integration](#2-fastapi--litellm-integration)
3. [Configuration Patterns](#3-configuration-patterns)
4. [Error Handling](#4-error-handling)
5. [Streaming Patterns](#5-streaming-patterns)
6. [Security Considerations](#6-security-considerations)
7. [Performance Optimization](#7-performance-optimization)
8. [Testing Strategies](#8-testing-strategies)

---

## 1. LiteLLM SDK Session Management

### 1.1 Persistent httpx.AsyncClient Configuration

**Key Finding**: LiteLLM supports injecting custom httpx.AsyncClient via `litellm.aclient_session`

**Official Documentation**: [Custom HTTP Handler](https://docs.litellm.ai/docs/completion/http_handler_config)

#### Basic Pattern

```python
import httpx
import litellm

# Create persistent client
litellm.aclient_session = httpx.AsyncClient(
    timeout=httpx.Timeout(600.0),
    follow_redirects=True,
    limits=httpx.Limits(
        max_connections=100,
        max_keepalive_connections=20
    )
)

# Use with acompletion
response = await litellm.acompletion(
    model="gpt-3.5-turbo",
    messages=[{"role": "user", "content": "Hello"}]
)
```

**⚠️ Important**: httpx.AsyncClient cookies persist automatically. This is CRITICAL for Cloudflare challenges.

**Reference**: [httpx GitHub Discussion #2144](https://github.com/encode/httpx/discussions/2144)

---

### 1.2 Production-Ready Session Manager

#### Recommended Implementation

```python
from typing import Optional
import asyncio
import httpx
import logging

logger = logging.getLogger(__name__)

class LiteLLMSessionManager:
    """
    Manages persistent httpx.AsyncClient for LiteLLM SDK.

    Features:
    - Singleton pattern (one client per process)
    - Thread-safe creation
    - Proper lifecycle management
    - Cookie persistence (Cloudflare-compatible)
    """

    _client: Optional[httpx.AsyncClient] = None
    _lock = asyncio.Lock()

    @classmethod
    async def get_client(cls) -> httpx.AsyncClient:
        """Get or create persistent httpx client."""
        async with cls._lock:
            if cls._client is None:
                cls._client = httpx.AsyncClient(
                    # Extended timeout for LLM requests
                    timeout=httpx.Timeout(
                        connect=30.0,  # Connection timeout
                        read=600.0,    # Read timeout (10 min for long completions)
                        write=30.0,    # Write timeout
                        pool=10.0      # Pool acquisition timeout
                    ),
                    # Follow redirects (Cloudflare may redirect)
                    follow_redirects=True,
                    # Connection pooling configuration
                    limits=httpx.Limits(
                        max_connections=100,        # Total connections
                        max_keepalive_connections=20,  # Keep-alive pool
                        keepalive_expiry=60.0      # Keep-alive duration
                    ),
                    # HTTP/2 support (optional, may improve performance)
                    http2=False,  # Set to True if providers support it
                )
                logger.info(
                    "Created persistent httpx.AsyncClient "
                    f"(id={id(cls._client)})"
                )
            return cls._client

    @classmethod
    async def close(cls):
        """Close persistent client (call during shutdown)."""
        async with cls._lock:
            if cls._client:
                await cls._client.aclose()
                logger.info(f"Closed httpx.AsyncClient (id={id(cls._client)})")
                cls._client = None

    @classmethod
    def is_initialized(cls) -> bool:
        """Check if client is initialized."""
        return cls._client is not None
```

**Key Design Decisions**:
1. **Singleton Pattern**: One client per process ensures cookie sharing
2. **Async Lock**: Thread-safe initialization
3. **Long Timeouts**: LLM requests can take minutes
4. **Connection Pooling**: Reuse TCP connections for performance
5. **Keep-Alive**: Persist connections to reduce handshake overhead

---

### 1.3 Alternative: aiohttp Handler (Advanced)

**When to Use**: For advanced connection pooling or corporate proxy requirements

```python
import aiohttp
import ssl
from litellm.llms.custom_httpx.aiohttp_handler import BaseLLMAIOHTTPHandler

# Production configuration
ssl_context = ssl.create_default_context()
session = aiohttp.ClientSession(
    timeout=aiohttp.ClientTimeout(total=300),
    connector=aiohttp.TCPConnector(
        limit=1000,              # Total connection limit
        limit_per_host=200,      # Per-host limit
        ttl_dns_cache=600,       # DNS cache (10 min)
        keepalive_timeout=60,    # Keep-alive timeout
        ssl=ssl_context
    ),
    trust_env=True  # Use system proxy settings
)

litellm.base_llm_aiohttp_handler = BaseLLMAIOHTTPHandler(
    client_session=session
)
```

**Trade-offs**:
- ✅ Better connection pooling control
- ✅ Corporate proxy/SSL support
- ❌ More complex configuration
- ❌ aiohttp dependency

**Recommendation**: Start with httpx.AsyncClient (simpler), migrate to aiohttp if needed.

---

### 1.4 Cloudflare Cookie Persistence

**Critical Requirement**: Cloudflare sets `cf_clearance` and `__cfruid` cookies after challenges.

**How httpx Handles Cookies**:
```python
# Cookies persist automatically in AsyncClient
client = httpx.AsyncClient()

# First request: May receive Cloudflare challenge
response1 = await client.get("https://api.supermemory.ai/...")
# Cloudflare sets cookies: cf_clearance, __cfruid

# Second request: Cookies automatically sent
response2 = await client.get("https://api.supermemory.ai/...")
# No challenge needed - cookies reused
```

**Verification Pattern**:
```python
async def verify_cookie_persistence():
    """Verify cookies persist across requests."""
    client = await LiteLLMSessionManager.get_client()

    # Make first request
    response1 = await client.get("https://api.supermemory.ai/health")
    cookies_after_first = dict(client.cookies)

    # Make second request
    response2 = await client.get("https://api.supermemory.ai/health")
    cookies_after_second = dict(client.cookies)

    # Verify cookies persisted
    assert cookies_after_first == cookies_after_second
    assert "cf_clearance" in cookies_after_second or "cf_clearance" in cookies_after_first

    logger.info(f"Cookies persisted: {list(cookies_after_second.keys())}")
```

**References**:
- [Cloudflare Cookies Documentation](https://developers.cloudflare.com/fundamentals/get-started/reference/cloudflare-cookies/)
- [Cloudflare Rate Limiting](https://developers.cloudflare.com/waf/rate-limiting-rules/parameters/)

---

## 2. FastAPI + LiteLLM Integration

### 2.1 Lifespan Context Manager Pattern

**Official Pattern**: FastAPI recommends `@asynccontextmanager` for startup/shutdown logic.

**Reference**: [FastAPI Lifespan Events](https://fastapi.tiangolo.com/advanced/events/)

#### Complete Implementation

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
import litellm
import logging

logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI lifespan context manager.

    Code before yield: Runs during startup
    Code after yield: Runs during shutdown
    """
    # ========== STARTUP ==========
    logger.info("🚀 Starting LiteLLM SDK Proxy")

    # 1. Initialize persistent HTTP client
    client = await LiteLLMSessionManager.get_client()
    litellm.aclient_session = client
    logger.info(f"✅ Initialized httpx.AsyncClient (id={id(client)})")

    # 2. Load configuration
    config = LiteLLMConfig("config/config.yaml")
    app.state.config = config
    logger.info(f"✅ Loaded configuration from config.yaml")

    # 3. Initialize memory router
    memory_router = MemoryRouter(config.config)
    app.state.memory_router = memory_router
    logger.info(f"✅ Initialized memory router")

    # 4. Set LiteLLM global settings
    litellm.drop_params = True  # Drop unsupported params
    litellm.set_verbose = True  # Verbose logging
    logger.info("✅ Configured LiteLLM settings")

    logger.info("✅ Startup complete")

    # ========== APPLICATION RUNS ==========
    yield

    # ========== SHUTDOWN ==========
    logger.info("🛑 Shutting down LiteLLM SDK Proxy")

    # 1. Close HTTP client
    await LiteLLMSessionManager.close()
    logger.info("✅ Closed httpx.AsyncClient")

    # 2. Clear LiteLLM session
    litellm.aclient_session = None
    logger.info("✅ Cleared LiteLLM session")

    logger.info("✅ Shutdown complete")


# Create FastAPI app with lifespan
app = FastAPI(
    title="LiteLLM Memory Proxy (SDK)",
    version="2.0.0",
    lifespan=lifespan
)
```

**Key Benefits**:
1. **Clean startup/shutdown**: Resources initialized once
2. **app.state**: Store application-level objects (config, router)
3. **Guaranteed cleanup**: Shutdown logic always runs
4. **Testable**: Can override in tests

---

### 2.2 Dependency Injection Pattern

**Pattern**: Use FastAPI dependencies to inject configuration and session manager.

#### Factory Function Pattern

```python
from fastapi import Depends, Request
from typing import Annotated

def get_config(request: Request) -> LiteLLMConfig:
    """Dependency: Get config from app.state."""
    return request.app.state.config

def get_memory_router(request: Request) -> MemoryRouter:
    """Dependency: Get memory router from app.state."""
    return request.app.state.memory_router

async def get_litellm_client() -> httpx.AsyncClient:
    """Dependency: Get persistent httpx client."""
    return await LiteLLMSessionManager.get_client()

# Type aliases for cleaner signatures
ConfigDep = Annotated[LiteLLMConfig, Depends(get_config)]
RouterDep = Annotated[MemoryRouter, Depends(get_memory_router)]
ClientDep = Annotated[httpx.AsyncClient, Depends(get_litellm_client)]
```

#### Usage in Endpoints

```python
@app.post("/v1/chat/completions")
async def chat_completions(
    request: Request,
    config: ConfigDep,
    memory_router: RouterDep,
    client: ClientDep
):
    """
    Handle chat completions with dependency injection.

    Benefits:
    - Explicit dependencies (no globals)
    - Easy to test (mock dependencies)
    - Type-safe
    """
    # Parse request
    body = await request.json()

    # Use injected dependencies
    user_id = memory_router.detect_user_id(request.headers)
    model_config = config.get_litellm_params(body["model"])

    # Client already set by get_litellm_client()
    # litellm.aclient_session = client  # Not needed, set in lifespan

    # Make completion
    response = await litellm.acompletion(
        model=model_config["model"],
        messages=body["messages"],
        api_base=model_config.get("api_base"),
        api_key=model_config.get("api_key"),
        extra_headers={"x-sm-user-id": user_id},
        stream=body.get("stream", False)
    )

    return response
```

**Benefits**:
- ✅ No global variables
- ✅ Testable (inject mocks)
- ✅ Type-safe
- ✅ Explicit dependencies

---

### 2.3 Error Handling Middleware

**Pattern**: Centralized exception handling for consistent responses.

```python
from fastapi import Request, Response
from fastapi.responses import JSONResponse
import litellm

@app.exception_handler(litellm.exceptions.RateLimitError)
async def handle_rate_limit_error(request: Request, exc: litellm.exceptions.RateLimitError):
    """Handle LiteLLM rate limit errors."""
    logger.warning(f"Rate limit error: {exc.message}")
    return JSONResponse(
        status_code=429,
        content={
            "error": {
                "message": exc.message,
                "type": "rate_limit_error",
                "code": "rate_limit_exceeded"
            }
        },
        headers={"Retry-After": "60"}
    )

@app.exception_handler(litellm.exceptions.ServiceUnavailableError)
async def handle_service_unavailable(request: Request, exc: litellm.exceptions.ServiceUnavailableError):
    """Handle LiteLLM service unavailable errors."""
    logger.error(f"Service unavailable: {exc.message}")
    return JSONResponse(
        status_code=503,
        content={
            "error": {
                "message": exc.message,
                "type": "service_unavailable",
                "code": "service_unavailable"
            }
        },
        headers={"Retry-After": "30"}
    )

@app.exception_handler(litellm.exceptions.AuthenticationError)
async def handle_auth_error(request: Request, exc: litellm.exceptions.AuthenticationError):
    """Handle LiteLLM authentication errors."""
    logger.error(f"Authentication error: {exc.message}")
    return JSONResponse(
        status_code=401,
        content={
            "error": {
                "message": "Invalid API key",
                "type": "authentication_error",
                "code": "invalid_api_key"
            }
        }
    )

@app.exception_handler(Exception)
async def handle_generic_error(request: Request, exc: Exception):
    """Handle all other errors."""
    logger.exception(f"Unexpected error: {type(exc).__name__}: {exc}")
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "message": "Internal server error",
                "type": "internal_error",
                "code": "internal_error"
            }
        }
    )
```

**Benefits**:
- ✅ Consistent error format (OpenAI-compatible)
- ✅ Centralized logging
- ✅ Proper HTTP status codes
- ✅ Retry hints (Retry-After headers)

---

## 3. Configuration Patterns

### 3.1 Config.yaml Parsing

**Requirement**: Parse LiteLLM's config.yaml format with environment variable resolution.

**Format**: `os.environ/VARIABLE_NAME` → resolved at runtime

#### Complete Config Parser

```python
import yaml
import os
import re
from typing import Dict, Optional, Any, List
import logging

logger = logging.getLogger(__name__)

class LiteLLMConfig:
    """
    Parses config.yaml and resolves environment variables.

    Supports:
    - Environment variable resolution (os.environ/VAR_NAME)
    - Model configuration lookup
    - Master key validation
    - litellm_settings extraction
    """

    def __init__(self, config_path: str):
        """Load and parse config.yaml."""
        self.config_path = config_path
        with open(config_path, 'r') as f:
            self.config = yaml.safe_load(f)

        logger.info(f"Loaded config from {config_path}")

        # Validate config structure
        self._validate_config()

    def _validate_config(self):
        """Validate required config sections."""
        required_sections = ["model_list"]
        for section in required_sections:
            if section not in self.config:
                raise ValueError(f"Missing required config section: {section}")

        if not self.config["model_list"]:
            raise ValueError("model_list cannot be empty")

        logger.info(f"Config validation passed ({len(self.config['model_list'])} models)")

    def get_model_config(self, model_name: str) -> Optional[Dict[str, Any]]:
        """Get full configuration for a specific model."""
        for model in self.config.get("model_list", []):
            if model.get("model_name") == model_name:
                return model

        logger.warning(f"Model not found in config: {model_name}")
        return None

    def get_litellm_params(self, model_name: str) -> Dict[str, Any]:
        """
        Extract litellm_params for a model with env var resolution.

        Returns:
            Dict with resolved parameters for litellm.acompletion()
        """
        model_config = self.get_model_config(model_name)
        if not model_config:
            raise ValueError(f"Model not found: {model_name}")

        params = model_config.get("litellm_params", {})

        # Resolve environment variables
        resolved = self._resolve_env_vars(params)

        logger.debug(f"Resolved params for {model_name}: {list(resolved.keys())}")
        return resolved

    def _resolve_env_vars(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Recursively resolve os.environ/VAR_NAME references.

        Supports:
        - Top-level params: api_key: os.environ/OPENAI_API_KEY
        - Nested dicts: extra_headers: {key: os.environ/VAR}
        - Lists: [os.environ/VAR1, os.environ/VAR2]
        """
        resolved = {}

        for key, value in params.items():
            if isinstance(value, str) and value.startswith("os.environ/"):
                # Resolve environment variable
                env_var = value.replace("os.environ/", "")
                resolved_value = os.getenv(env_var)

                if resolved_value is None:
                    logger.warning(
                        f"Environment variable not set: {env_var} "
                        f"(referenced in config as {key})"
                    )
                    # Option 1: Fail fast
                    # raise ValueError(f"Environment variable not set: {env_var}")

                    # Option 2: Use placeholder (for testing)
                    resolved_value = f"<UNSET:{env_var}>"

                resolved[key] = resolved_value

            elif isinstance(value, dict):
                # Recursively resolve nested dicts
                resolved[key] = self._resolve_env_vars(value)

            elif isinstance(value, list):
                # Resolve list items
                resolved[key] = [
                    self._resolve_env_var_value(item)
                    for item in value
                ]

            else:
                # Keep as-is
                resolved[key] = value

        return resolved

    def _resolve_env_var_value(self, value: Any) -> Any:
        """Resolve a single value (for list items)."""
        if isinstance(value, str) and value.startswith("os.environ/"):
            env_var = value.replace("os.environ/", "")
            return os.getenv(env_var, f"<UNSET:{env_var}>")
        elif isinstance(value, dict):
            return self._resolve_env_vars(value)
        else:
            return value

    def get_master_key(self) -> Optional[str]:
        """Get master API key for proxy authentication."""
        general_settings = self.config.get("general_settings", {})
        master_key = general_settings.get("master_key")

        # Resolve env var if needed
        if isinstance(master_key, str) and master_key.startswith("os.environ/"):
            env_var = master_key.replace("os.environ/", "")
            master_key = os.getenv(env_var)

        return master_key

    def get_litellm_settings(self) -> Dict[str, Any]:
        """Get litellm_settings section."""
        return self.config.get("litellm_settings", {})

    def get_all_models(self) -> List[str]:
        """Get list of all configured model names."""
        return [
            model.get("model_name")
            for model in self.config.get("model_list", [])
            if model.get("model_name")
        ]
```

**Usage Example**:

```python
# Load config
config = LiteLLMConfig("config/config.yaml")

# Get model params
params = config.get_litellm_params("claude-sonnet-4.5")
# Returns:
# {
#     "model": "anthropic/claude-sonnet-4-5-20250929",
#     "api_base": "https://api.supermemory.ai/v3/api.anthropic.com",
#     "api_key": "sk-ant-...",  # Resolved from env
#     "extra_headers": {
#         "x-supermemory-api-key": "sm_..."  # Resolved from env
#     }
# }

# Get master key
master_key = config.get_master_key()

# Get all models
models = config.get_all_models()
```

---

### 3.2 Environment Variable Best Practices

**Security Pattern**: Never hardcode secrets

```yaml
# ✅ GOOD: Environment variable reference
model_list:
  - model_name: claude-sonnet-4.5
    litellm_params:
      api_key: os.environ/ANTHROPIC_API_KEY
      extra_headers:
        x-supermemory-api-key: os.environ/SUPERMEMORY_API_KEY

# ❌ BAD: Hardcoded secret
model_list:
  - model_name: claude-sonnet-4.5
    litellm_params:
      api_key: sk-ant-actual-secret-key  # Never do this!
```

**Environment Variable Validation**:

```python
def validate_environment_variables():
    """Validate all required environment variables are set."""
    required_vars = [
        "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY",
        "SUPERMEMORY_API_KEY"
    ]

    missing = [var for var in required_vars if not os.getenv(var)]

    if missing:
        raise ValueError(
            f"Missing required environment variables: {', '.join(missing)}\n"
            f"Set them with: export VAR_NAME=value"
        )

    logger.info("✅ All required environment variables are set")
```

---

## 4. Error Handling

### 4.1 Complete Exception Hierarchy

**Reference**: [LiteLLM Exception Mapping](https://docs.litellm.ai/docs/exception_mapping)

**Key Principle**: All LiteLLM exceptions inherit from OpenAI's exception types.

#### Exception Types with Status Codes

| Status | Exception | Parent | Use Case |
|--------|-----------|--------|----------|
| 400 | `BadRequestError` | `openai.BadRequestError` | Invalid request format |
| 400 | `ContextWindowExceededError` | `litellm.BadRequestError` | Token limit exceeded |
| 400 | `ContentPolicyViolationError` | `litellm.BadRequestError` | Content policy violation |
| 400 | `UnsupportedParamsError` | `litellm.BadRequestError` | Unsupported parameters |
| 401 | `AuthenticationError` | `openai.AuthenticationError` | Invalid API key |
| 403 | `PermissionDeniedError` | `openai.PermissionDeniedError` | Insufficient permissions |
| 404 | `NotFoundError` | `openai.NotFoundError` | Model/resource not found |
| 408 | `Timeout` | `openai.APITimeoutError` | Request timeout |
| 429 | `RateLimitError` | `openai.RateLimitError` | Rate limit exceeded |
| 500 | `APIError` | `openai.APIError` | Generic API error |
| 503 | `ServiceUnavailableError` | `openai.APIStatusError` | Service unavailable |

#### Complete Error Handler

```python
import litellm
from fastapi import Request
from fastapi.responses import JSONResponse
import logging

logger = logging.getLogger(__name__)

class LiteLLMErrorHandler:
    """Centralized error handling for LiteLLM exceptions."""

    @staticmethod
    def create_error_response(
        status_code: int,
        error_type: str,
        message: str,
        code: str,
        retry_after: Optional[int] = None
    ) -> JSONResponse:
        """Create standardized error response."""
        content = {
            "error": {
                "message": message,
                "type": error_type,
                "code": code
            }
        }

        headers = {}
        if retry_after:
            headers["Retry-After"] = str(retry_after)

        return JSONResponse(
            status_code=status_code,
            content=content,
            headers=headers
        )

    @staticmethod
    async def handle_completion_error(exc: Exception) -> JSONResponse:
        """
        Handle LiteLLM completion errors.

        Returns appropriate HTTP response based on exception type.
        """
        # 400 - Bad Request
        if isinstance(exc, litellm.exceptions.ContextWindowExceededError):
            logger.warning(f"Context window exceeded: {exc.message}")
            return LiteLLMErrorHandler.create_error_response(
                status_code=400,
                error_type="invalid_request_error",
                message=exc.message,
                code="context_length_exceeded"
            )

        elif isinstance(exc, litellm.exceptions.ContentPolicyViolationError):
            logger.warning(f"Content policy violation: {exc.message}")
            return LiteLLMErrorHandler.create_error_response(
                status_code=400,
                error_type="invalid_request_error",
                message=exc.message,
                code="content_policy_violation"
            )

        elif isinstance(exc, litellm.exceptions.UnsupportedParamsError):
            logger.warning(f"Unsupported params: {exc.message}")
            return LiteLLMErrorHandler.create_error_response(
                status_code=400,
                error_type="invalid_request_error",
                message=exc.message,
                code="unsupported_params"
            )

        elif isinstance(exc, litellm.exceptions.BadRequestError):
            logger.warning(f"Bad request: {exc.message}")
            return LiteLLMErrorHandler.create_error_response(
                status_code=400,
                error_type="invalid_request_error",
                message=exc.message,
                code="bad_request"
            )

        # 401 - Authentication Error
        elif isinstance(exc, litellm.exceptions.AuthenticationError):
            logger.error(f"Authentication error: {exc.message}")
            return LiteLLMErrorHandler.create_error_response(
                status_code=401,
                error_type="authentication_error",
                message="Invalid API key",
                code="invalid_api_key"
            )

        # 403 - Permission Denied
        elif isinstance(exc, litellm.exceptions.PermissionDeniedError):
            logger.error(f"Permission denied: {exc.message}")
            return LiteLLMErrorHandler.create_error_response(
                status_code=403,
                error_type="permission_error",
                message=exc.message,
                code="permission_denied"
            )

        # 404 - Not Found
        elif isinstance(exc, litellm.exceptions.NotFoundError):
            logger.error(f"Not found: {exc.message}")
            return LiteLLMErrorHandler.create_error_response(
                status_code=404,
                error_type="not_found_error",
                message=exc.message,
                code="model_not_found"
            )

        # 408 - Timeout
        elif isinstance(exc, litellm.Timeout):
            logger.error(f"Timeout: {exc.message}")
            return LiteLLMErrorHandler.create_error_response(
                status_code=408,
                error_type="timeout_error",
                message=exc.message,
                code="request_timeout",
                retry_after=60
            )

        # 429 - Rate Limit
        elif isinstance(exc, litellm.exceptions.RateLimitError):
            logger.warning(f"Rate limit: {exc.message}")
            return LiteLLMErrorHandler.create_error_response(
                status_code=429,
                error_type="rate_limit_error",
                message=exc.message,
                code="rate_limit_exceeded",
                retry_after=60
            )

        # 503 - Service Unavailable
        elif isinstance(exc, litellm.exceptions.ServiceUnavailableError):
            logger.error(f"Service unavailable: {exc.message}")
            return LiteLLMErrorHandler.create_error_response(
                status_code=503,
                error_type="service_unavailable",
                message=exc.message,
                code="service_unavailable",
                retry_after=30
            )

        # 500 - API Error (catch-all for litellm.exceptions.APIError)
        elif isinstance(exc, litellm.exceptions.APIError):
            logger.error(f"API error: {exc.message}")
            return LiteLLMErrorHandler.create_error_response(
                status_code=500,
                error_type="api_error",
                message=exc.message,
                code="api_error"
            )

        # Generic exception handler
        else:
            logger.exception(f"Unexpected error: {type(exc).__name__}: {exc}")
            return LiteLLMErrorHandler.create_error_response(
                status_code=500,
                error_type="internal_error",
                message="Internal server error",
                code="internal_error"
            )
```

#### Usage in Endpoint

```python
@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    try:
        # ... completion logic ...
        response = await litellm.acompletion(...)
        return response

    except Exception as exc:
        return await LiteLLMErrorHandler.handle_completion_error(exc)
```

---

### 4.2 Retry Strategy

**Pattern**: Use `litellm._should_retry()` to determine if error is retryable.

```python
import litellm
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception

def is_retryable_error(exc: Exception) -> bool:
    """Check if error is retryable."""
    if hasattr(exc, 'status_code'):
        return litellm._should_retry(exc.status_code)
    return False

@retry(
    retry=retry_if_exception(is_retryable_error),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10)
)
async def completion_with_retry(model: str, messages: List[Dict], **kwargs):
    """
    Call litellm.acompletion with automatic retries.

    Retries on:
    - 429 Rate Limit
    - 503 Service Unavailable
    - 500 Server Error
    - Timeouts
    """
    return await litellm.acompletion(
        model=model,
        messages=messages,
        **kwargs
    )
```

---

## 5. Streaming Patterns

### 5.1 LiteLLM Streaming Basics

**Reference**: [LiteLLM Streaming Documentation](https://docs.litellm.ai/docs/completion/stream)

**Key Points**:
- Set `stream=True` in acompletion()
- Returns async iterator
- Yields `ModelResponse` chunks
- Use `chunk.choices[0].delta.content` to access text

#### Basic Streaming Pattern

```python
response = await litellm.acompletion(
    model="gpt-3.5-turbo",
    messages=[{"role": "user", "content": "Tell me a story"}],
    stream=True
)

async for chunk in response:
    content = chunk.choices[0].delta.content or ""
    print(content, end="", flush=True)
```

---

### 5.2 FastAPI SSE Streaming

**Pattern**: Use `StreamingResponse` with SSE format for OpenAI compatibility.

**Reference**: Multiple tutorials on FastAPI SSE (see research sources)

#### Complete Streaming Implementation

```python
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
import litellm
import json
import logging

logger = logging.getLogger(__name__)

async def stream_litellm_completion(
    model: str,
    messages: List[Dict],
    extra_headers: Optional[Dict] = None,
    **kwargs
) -> AsyncGenerator[str, None]:
    """
    Stream LiteLLM completion as SSE events.

    Yields:
        SSE-formatted strings: "data: {json}\n\n"
    """
    try:
        # Call LiteLLM with streaming
        response = await litellm.acompletion(
            model=model,
            messages=messages,
            extra_headers=extra_headers or {},
            stream=True,
            **kwargs
        )

        # Stream chunks
        async for chunk in response:
            # Extract content from chunk
            content = chunk.choices[0].delta.content or ""

            # Convert to dict for JSON serialization
            chunk_dict = chunk.model_dump()

            # Format as SSE
            sse_data = f"data: {json.dumps(chunk_dict)}\n\n"

            yield sse_data

            # Check for finish reason
            finish_reason = chunk.choices[0].finish_reason
            if finish_reason:
                logger.debug(f"Stream finished: {finish_reason}")
                break

        # Send [DONE] message (OpenAI format)
        yield "data: [DONE]\n\n"

    except litellm.exceptions.LiteLLMException as e:
        # Handle LiteLLM-specific errors
        logger.error(f"Streaming error: {type(e).__name__}: {e}")

        # Send error as SSE event
        error_data = {
            "error": {
                "message": str(e),
                "type": type(e).__name__,
                "code": "streaming_error"
            }
        }
        yield f"data: {json.dumps(error_data)}\n\n"

    except Exception as e:
        # Handle unexpected errors
        logger.exception(f"Unexpected streaming error: {e}")

        error_data = {
            "error": {
                "message": "Internal streaming error",
                "type": "internal_error",
                "code": "streaming_error"
            }
        }
        yield f"data: {json.dumps(error_data)}\n\n"


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    """Handle both streaming and non-streaming completions."""
    body = await request.json()

    model = body.get("model")
    messages = body.get("messages", [])
    stream = body.get("stream", False)

    # ... user ID detection, config loading ...

    if stream:
        # Return streaming response
        return StreamingResponse(
            stream_litellm_completion(
                model=model,
                messages=messages,
                extra_headers={"x-sm-user-id": user_id},
                **{k: v for k, v in body.items()
                   if k not in ["model", "messages", "stream"]}
            ),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"  # Disable nginx buffering
            }
        )
    else:
        # Non-streaming response
        response = await litellm.acompletion(
            model=model,
            messages=messages,
            extra_headers={"x-sm-user-id": user_id},
            stream=False
        )
        return response.model_dump()
```

**Key Details**:
- `media_type="text/event-stream"`: Required for SSE
- `Cache-Control: no-cache`: Prevent caching
- `X-Accel-Buffering: no`: Disable nginx buffering (if behind nginx)
- `data: [DONE]\n\n`: Signals end of stream (OpenAI convention)

---

### 5.3 Error Handling in Streams

**Challenge**: Errors during streaming must be sent as SSE events.

```python
async def stream_with_error_handling(model: str, messages: List[Dict], **kwargs):
    """Stream with robust error handling."""
    try:
        response = await litellm.acompletion(
            model=model,
            messages=messages,
            stream=True,
            **kwargs
        )

        chunk_count = 0
        last_content = ""

        async for chunk in response:
            chunk_count += 1
            content = chunk.choices[0].delta.content or ""

            # Detect infinite loops (LiteLLM has built-in protection)
            if content and content == last_content:
                logger.warning(f"Repeated chunk detected: {content[:50]}")
            last_content = content

            # Yield chunk
            chunk_dict = chunk.model_dump()
            yield f"data: {json.dumps(chunk_dict)}\n\n"

            # Check finish reason
            if chunk.choices[0].finish_reason:
                break

        logger.info(f"Stream completed successfully ({chunk_count} chunks)")
        yield "data: [DONE]\n\n"

    except litellm.RateLimitError as e:
        logger.error(f"Rate limit during streaming: {e}")
        error_data = {
            "error": {
                "message": "Rate limit exceeded during streaming",
                "type": "rate_limit_error",
                "code": "rate_limit_exceeded"
            }
        }
        yield f"data: {json.dumps(error_data)}\n\n"

    except litellm.Timeout as e:
        logger.error(f"Timeout during streaming: {e}")
        error_data = {
            "error": {
                "message": "Request timeout during streaming",
                "type": "timeout_error",
                "code": "stream_timeout"
            }
        }
        yield f"data: {json.dumps(error_data)}\n\n"

    except Exception as e:
        logger.exception(f"Unexpected error during streaming: {e}")
        error_data = {
            "error": {
                "message": "Internal error during streaming",
                "type": "internal_error",
                "code": "streaming_error"
            }
        }
        yield f"data: {json.dumps(error_data)}\n\n"
```

---

### 5.4 Infinite Loop Protection

**LiteLLM Feature**: Built-in protection against repeated chunks.

```python
# LiteLLM default configuration
litellm.REPEATED_STREAMING_CHUNK_LIMIT = 100

# Override in config.yaml
litellm_settings:
  REPEATED_STREAMING_CHUNK_LIMIT: 100
```

**Reference**: [LiteLLM Streaming Documentation](https://docs.litellm.ai/docs/completion/stream)

---

## 6. Security Considerations

### 6.1 API Key Validation

```python
from fastapi import Header, HTTPException
from typing import Optional

async def verify_api_key(
    authorization: Optional[str] = Header(None),
    config: ConfigDep = None
) -> str:
    """
    Verify API key from Authorization header.

    Raises:
        HTTPException: If API key is invalid

    Returns:
        Validated API key
    """
    if not authorization:
        raise HTTPException(
            status_code=401,
            detail="Missing Authorization header"
        )

    # Extract bearer token
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Invalid Authorization header format"
        )

    api_key = authorization.replace("Bearer ", "")

    # Validate against master key
    master_key = config.get_master_key()
    if api_key != master_key:
        raise HTTPException(
            status_code=401,
            detail="Invalid API key"
        )

    return api_key

# Usage in endpoint
@app.post("/v1/chat/completions")
async def chat_completions(
    request: Request,
    api_key: str = Depends(verify_api_key)
):
    # API key validated, proceed with request
    ...
```

---

### 6.2 Rate Limiting

```python
from fastapi import Request, HTTPException
from collections import defaultdict
import time
from typing import Dict, Tuple

class RateLimiter:
    """Simple in-memory rate limiter."""

    def __init__(self, max_requests: int = 60, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests: Dict[str, List[float]] = defaultdict(list)

    async def check_rate_limit(self, identifier: str):
        """
        Check if request is within rate limit.

        Args:
            identifier: User ID or IP address

        Raises:
            HTTPException: If rate limit exceeded
        """
        now = time.time()
        window_start = now - self.window_seconds

        # Clean old requests
        self.requests[identifier] = [
            req_time for req_time in self.requests[identifier]
            if req_time > window_start
        ]

        # Check limit
        if len(self.requests[identifier]) >= self.max_requests:
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded: {self.max_requests} requests per {self.window_seconds}s",
                headers={"Retry-After": str(self.window_seconds)}
            )

        # Record request
        self.requests[identifier].append(now)

# Global rate limiter
rate_limiter = RateLimiter(max_requests=60, window_seconds=60)

# Usage in endpoint
@app.post("/v1/chat/completions")
async def chat_completions(
    request: Request,
    memory_router: RouterDep
):
    # Get user ID
    user_id = memory_router.detect_user_id(request.headers)

    # Check rate limit
    await rate_limiter.check_rate_limit(user_id)

    # Proceed with request
    ...
```

---

### 6.3 Input Validation

```python
from pydantic import BaseModel, Field, validator
from typing import List, Optional

class Message(BaseModel):
    """Chat message model."""
    role: str = Field(..., regex="^(system|user|assistant)$")
    content: str = Field(..., min_length=1, max_length=100000)

class ChatCompletionRequest(BaseModel):
    """Chat completion request model."""
    model: str = Field(..., min_length=1)
    messages: List[Message] = Field(..., min_items=1, max_items=100)
    temperature: Optional[float] = Field(None, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(None, ge=1, le=100000)
    stream: Optional[bool] = False

    @validator("messages")
    def validate_messages(cls, v):
        """Validate message list structure."""
        if not v:
            raise ValueError("messages cannot be empty")

        # Check for alternating roles (optional)
        roles = [msg.role for msg in v]
        if roles[0] == "assistant":
            raise ValueError("First message cannot be from assistant")

        return v

# Usage in endpoint
@app.post("/v1/chat/completions")
async def chat_completions(
    request: ChatCompletionRequest,  # Pydantic validation
    memory_router: RouterDep
):
    # Request already validated by Pydantic
    ...
```

---

## 7. Performance Optimization

### 7.1 Connection Pooling Configuration

**httpx.AsyncClient Limits**:

```python
# Development settings
client = httpx.AsyncClient(
    limits=httpx.Limits(
        max_connections=50,
        max_keepalive_connections=10
    )
)

# Production settings
client = httpx.AsyncClient(
    limits=httpx.Limits(
        max_connections=200,       # Higher for concurrent requests
        max_keepalive_connections=50,  # More keep-alive connections
        keepalive_expiry=60.0     # Keep-alive for 60 seconds
    )
)
```

**Reference**: [httpx Connection Pooling](https://www.python-httpx.org/advanced/#pool-limit-configuration)

---

### 7.2 Timeout Configuration

**Recommended Timeouts**:

```python
client = httpx.AsyncClient(
    timeout=httpx.Timeout(
        connect=30.0,   # 30s to establish connection
        read=600.0,     # 10 minutes for LLM responses
        write=30.0,     # 30s to send request
        pool=10.0       # 10s to acquire connection from pool
    )
)
```

**Rationale**:
- **connect**: DNS + TCP handshake (30s is generous)
- **read**: LLM responses can be slow (especially for long completions)
- **write**: Sending request body (usually fast)
- **pool**: Acquiring connection from pool (should be instant)

---

### 7.3 Caching Strategy

**LiteLLM Built-in Caching**:

```python
# Enable client-side caching
litellm.use_client_cache = True

# Or in config.yaml
litellm_settings:
  use_client_cache: true
```

**Custom Caching**:

```python
from functools import lru_cache
import hashlib
import json

@lru_cache(maxsize=100)
def get_cached_config(model_name: str):
    """Cache model configurations."""
    config = LiteLLMConfig("config/config.yaml")
    return config.get_litellm_params(model_name)

def cache_key_from_request(model: str, messages: List[Dict]) -> str:
    """Generate cache key for completion request."""
    # Hash messages for deterministic key
    messages_str = json.dumps(messages, sort_keys=True)
    messages_hash = hashlib.sha256(messages_str.encode()).hexdigest()[:16]
    return f"{model}:{messages_hash}"
```

---

## 8. Testing Strategies

### 8.1 Unit Tests

#### Test Config Parser

```python
import pytest
from unittest.mock import patch
import os

def test_config_parser_resolves_env_vars():
    """Test environment variable resolution."""
    with patch.dict(os.environ, {
        "TEST_API_KEY": "sk-test-123",
        "TEST_API_BASE": "https://test.example.com"
    }):
        config = LiteLLMConfig("config/config.yaml")
        params = config.get_litellm_params("test-model")

        assert params["api_key"] == "sk-test-123"
        assert params["api_base"] == "https://test.example.com"
        assert "os.environ/" not in params["api_key"]

def test_config_parser_missing_env_var():
    """Test handling of missing environment variables."""
    with patch.dict(os.environ, {}, clear=True):
        config = LiteLLMConfig("config/config.yaml")
        params = config.get_litellm_params("test-model")

        # Should handle gracefully (with warning or placeholder)
        assert "<UNSET:" in params["api_key"] or params["api_key"] is None

def test_config_parser_validates_structure():
    """Test config validation."""
    with pytest.raises(ValueError, match="Missing required config section"):
        # Load invalid config
        config = LiteLLMConfig("tests/fixtures/invalid_config.yaml")
```

#### Test Session Manager

```python
import pytest
import httpx

@pytest.mark.asyncio
async def test_session_manager_singleton():
    """Test that session manager returns same client."""
    client1 = await LiteLLMSessionManager.get_client()
    client2 = await LiteLLMSessionManager.get_client()

    assert id(client1) == id(client2)
    assert isinstance(client1, httpx.AsyncClient)

@pytest.mark.asyncio
async def test_session_manager_lifecycle():
    """Test session manager lifecycle."""
    # Get client
    client = await LiteLLMSessionManager.get_client()
    assert LiteLLMSessionManager.is_initialized()

    # Close client
    await LiteLLMSessionManager.close()
    assert not LiteLLMSessionManager.is_initialized()

    # Can re-initialize
    client2 = await LiteLLMSessionManager.get_client()
    assert LiteLLMSessionManager.is_initialized()
    assert id(client) != id(client2)  # New client instance

@pytest.mark.asyncio
async def test_cookie_persistence():
    """Test that cookies persist across requests."""
    client = await LiteLLMSessionManager.get_client()

    # Make first request
    response1 = await client.get("https://httpbin.org/cookies/set/test/value")

    # Make second request
    response2 = await client.get("https://httpbin.org/cookies")

    # Verify cookie persisted
    cookies = response2.json()["cookies"]
    assert "test" in cookies
    assert cookies["test"] == "value"
```

---

### 8.2 Integration Tests

```python
import pytest
from httpx import AsyncClient
from fastapi.testclient import TestClient

@pytest.fixture
async def test_app():
    """Create test FastAPI app."""
    from src.proxy.litellm_proxy_sdk import app
    return app

@pytest.fixture
async def client(test_app):
    """Create test client."""
    async with AsyncClient(app=test_app, base_url="http://test") as client:
        yield client

@pytest.mark.asyncio
async def test_chat_completions_endpoint(client):
    """Test /v1/chat/completions endpoint."""
    response = await client.post(
        "/v1/chat/completions",
        json={
            "model": "gpt-3.5-turbo",
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
async def test_streaming_endpoint(client):
    """Test streaming completions."""
    async with client.stream(
        "POST",
        "/v1/chat/completions",
        json={
            "model": "gpt-3.5-turbo",
            "messages": [{"role": "user", "content": "Count to 5"}],
            "stream": True
        },
        headers={"Authorization": "Bearer sk-1234"}
    ) as response:
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/event-stream"

        chunks = []
        async for line in response.aiter_lines():
            if line.startswith("data: "):
                chunk_data = line[6:]  # Remove "data: " prefix
                if chunk_data != "[DONE]":
                    chunks.append(chunk_data)

        assert len(chunks) > 0

@pytest.mark.asyncio
async def test_error_handling(client):
    """Test error handling."""
    # Test invalid model
    response = await client.post(
        "/v1/chat/completions",
        json={
            "model": "nonexistent-model",
            "messages": [{"role": "user", "content": "Test"}]
        },
        headers={"Authorization": "Bearer sk-1234"}
    )

    assert response.status_code in [400, 404]
    data = response.json()
    assert "error" in data
```

---

### 8.3 End-to-End Tests

```python
@pytest.mark.e2e
@pytest.mark.asyncio
async def test_full_completion_flow():
    """Test complete flow: request → LiteLLM → provider → response."""
    # Start proxy
    # (assume proxy is running on localhost:8764)

    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://localhost:8764/v1/chat/completions",
            json={
                "model": "claude-sonnet-4.5",
                "messages": [
                    {"role": "user", "content": "What is 2+2?"}
                ],
                "max_tokens": 100
            },
            headers={
                "Authorization": "Bearer sk-1234",
                "User-Agent": "pytest-e2e"
            }
        )

        assert response.status_code == 200
        data = response.json()

        # Verify response structure
        assert "id" in data
        assert "choices" in data
        assert len(data["choices"]) > 0
        assert "message" in data["choices"][0]
        assert "content" in data["choices"][0]["message"]

        # Verify content makes sense
        content = data["choices"][0]["message"]["content"]
        assert "4" in content  # Should mention "4" for 2+2

@pytest.mark.e2e
@pytest.mark.asyncio
async def test_cookie_persistence_e2e():
    """Test Cloudflare cookie persistence end-to-end."""
    async with httpx.AsyncClient() as client:
        # Make multiple requests
        responses = []
        for i in range(5):
            response = await client.post(
                "http://localhost:8764/v1/chat/completions",
                json={
                    "model": "claude-sonnet-4.5",
                    "messages": [{"role": "user", "content": f"Test {i}"}],
                    "max_tokens": 10
                },
                headers={"Authorization": "Bearer sk-1234"}
            )
            responses.append(response)

        # All requests should succeed (no 503 errors)
        for response in responses:
            assert response.status_code == 200, \
                f"Request failed with {response.status_code}: {response.text}"
```

---

## Summary of Key Recommendations

### 1. Session Management
- ✅ Use `httpx.AsyncClient` for persistent sessions
- ✅ Implement singleton pattern for client reuse
- ✅ Set generous timeouts (600s read timeout)
- ✅ Configure connection pooling (100-200 max connections)
- ✅ Close client during shutdown

### 2. FastAPI Integration
- ✅ Use `@asynccontextmanager` for lifespan
- ✅ Store config/router in `app.state`
- ✅ Use dependency injection for clean architecture
- ✅ Implement centralized error handling
- ✅ Use middleware for common logic

### 3. Configuration
- ✅ Parse config.yaml with env var resolution
- ✅ Validate configuration at startup
- ✅ Never hardcode secrets
- ✅ Use `os.environ/VAR_NAME` pattern
- ✅ Cache parsed configurations

### 4. Error Handling
- ✅ Handle all LiteLLM exception types
- ✅ Map to appropriate HTTP status codes
- ✅ Return OpenAI-compatible error format
- ✅ Include Retry-After headers
- ✅ Log errors comprehensively

### 5. Streaming
- ✅ Use `StreamingResponse` with SSE format
- ✅ Set `media_type="text/event-stream"`
- ✅ Send errors as SSE events
- ✅ Include `data: [DONE]` at end
- ✅ Handle streaming errors gracefully

### 6. Security
- ✅ Validate API keys
- ✅ Implement rate limiting
- ✅ Use Pydantic for input validation
- ✅ Sanitize error messages
- ✅ Use HTTPS in production

### 7. Performance
- ✅ Enable connection pooling
- ✅ Use keep-alive connections
- ✅ Cache configuration objects
- ✅ Use LiteLLM's built-in caching
- ✅ Monitor performance metrics

### 8. Testing
- ✅ Unit test each component
- ✅ Integration test endpoints
- ✅ E2E test with real providers
- ✅ Test cookie persistence
- ✅ Test error scenarios

---

## References

### Official Documentation
1. [LiteLLM Documentation](https://docs.litellm.ai/)
2. [LiteLLM Custom HTTP Handler](https://docs.litellm.ai/docs/completion/http_handler_config)
3. [LiteLLM Exception Mapping](https://docs.litellm.ai/docs/exception_mapping)
4. [LiteLLM Streaming](https://docs.litellm.ai/docs/completion/stream)
5. [FastAPI Lifespan Events](https://fastapi.tiangolo.com/advanced/events/)
6. [httpx Documentation](https://www.python-httpx.org/)
7. [Cloudflare Cookies](https://developers.cloudflare.com/fundamentals/get-started/reference/cloudflare-cookies/)

### GitHub Issues & Discussions
1. [LiteLLM Issue #6538 - Custom httpx client](https://github.com/BerriAI/litellm/issues/6538)
2. [LiteLLM Issue #7667 - HTTP client re-use](https://github.com/BerriAI/litellm/issues/7667)
3. [httpx Discussion #2144 - Cookie persistence](https://github.com/encode/httpx/discussions/2144)

### Tutorials & Articles
1. [Server-Sent Events with FastAPI](https://medium.com/@nandagopal05/server-sent-events-with-python-fastapi-f1960e0c8e4b)
2. [Building OpenAI-Compatible Streaming with FastAPI](https://medium.com/@moustafa.abdelbaky/building-an-openai-compatible-streaming-interface-using-server-sent-events-with-fastapi-and-8f014420bca7)
3. [Comprehensive LiteLLM Configuration Guide](https://dev.to/yigit-konur/comprehensive-litellm-configuration-guide-configyaml-with-all-options-included-3e65)

---

## Appendix A: Complete Example

See `poc_litellm_sdk_proxy.py` for a working proof of concept demonstrating all patterns.

---

## Appendix B: Migration Checklist

When implementing `litellm_proxy_sdk.py`:

- [ ] Create `LiteLLMSessionManager` class
- [ ] Create `LiteLLMConfig` parser
- [ ] Implement lifespan context manager
- [ ] Set up dependency injection
- [ ] Implement `/v1/chat/completions` endpoint
- [ ] Add streaming support
- [ ] Implement error handlers for all exception types
- [ ] Add API key validation
- [ ] Add rate limiting
- [ ] Add input validation with Pydantic
- [ ] Configure logging
- [ ] Write unit tests
- [ ] Write integration tests
- [ ] Test with real providers
- [ ] Verify cookie persistence
- [ ] Load test with concurrent requests
- [ ] Document configuration options
- [ ] Update deployment scripts

---

**Document Status**: ✅ Complete
**Last Updated**: 2025-11-02
**Next Review**: After SDK implementation complete

---

*This document is part of the SDK Migration documentation suite. See `docs/architecture/SDK_MIGRATION_INDEX.md` for related documents.*
