"""
LiteLLM SDK-Based Proxy with Memory Routing

Main FastAPI application that uses LiteLLM SDK with persistent sessions.
Integrates all modular components: session manager, config parser, error handlers, streaming.

Architecture:
    - Persistent httpx.AsyncClient injected into LiteLLM SDK
    - Cookie persistence for Cloudflare (cf_clearance)
    - Memory routing with user ID detection
    - OpenAI-compatible API endpoints
    - Comprehensive error handling
    - SSE streaming support

Key Components:
    - session_manager: Manages persistent httpx.AsyncClient
    - config_parser: Loads and parses config.yaml
    - error_handlers: Maps LiteLLM exceptions to HTTP responses
    - streaming_utils: Handles SSE streaming format
    - memory_router: Detects user IDs from headers (existing)

Example:
    ```bash
    # Start server
    uvicorn src.proxy.litellm_proxy_sdk:app --host 0.0.0.0 --port 8764
    
    # Test request
    curl http://localhost:8764/v1/chat/completions \\
      -H "Content-Type: application/json" \\
      -H "Authorization: Bearer sk-1234" \\
      -d '{"model": "claude-sonnet-4.5", "messages": [{"role": "user", "content": "Hello"}]}'
    ```

References:
    - LITELLM_SDK_INTEGRATION_PATTERNS.md: Complete patterns
    - SDK_MIGRATION_ROLLOUT_ARCHITECTURE.md: Architecture design
    - poc_litellm_sdk_proxy.py: Working proof of concept
"""

import logging
import os
import time
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Dict

import litellm
from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.responses import StreamingResponse, JSONResponse
from litellm.litellm_core_utils.streaming_handler import CustomStreamWrapper
from litellm.proxy.proxy_server import master_key

from proxy.config_parser import LiteLLMConfig
from proxy.error_handlers import LiteLLMErrorHandler, register_exception_handlers
from proxy.memory_router import MemoryRouter
from proxy.session_manager import LiteLLMSessionManager
from proxy.streaming_utils import stream_litellm_completion

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


# ============================================================================
# Application Lifecycle Management
# ============================================================================


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """
    FastAPI lifespan context manager for startup and shutdown.

    Startup:
        1. Initialize session manager (persistent httpx.AsyncClient)
        2. Inject client into LiteLLM SDK
        3. Load configuration from config.yaml
        4. Initialize memory router
        5. Configure LiteLLM settings

    Shutdown:
        1. Close persistent session
        2. Log final statistics

    Args:
        app: FastAPI application instance

    Yields:
        None during application runtime
    """
    logger.info("=" * 70)
    logger.info("STARTUP: Initializing LiteLLM SDK Proxy")
    logger.info("=" * 70)

    # Startup Phase
    try:
        # 1. Initialize session manager
        logger.info("Step 1/5: Initializing session manager...")
        client = await LiteLLMSessionManager.get_client()
        logger.info(f"  Client ID: {id(client)}")
        logger.info(f"  Session info: {LiteLLMSessionManager.get_session_info()}")

        # 2. Inject into LiteLLM SDK
        logger.info("Step 2/5: Injecting client into LiteLLM SDK...")
        litellm.aclient_session = client
        logger.info(
            f"  Verified: litellm.aclient_session ID = {id(litellm.aclient_session)}"
        )

        # 3. Load configuration
        logger.info("Step 3/5: Loading configuration...")
        config_path = os.getenv("LITELLM_CONFIG_PATH", "config/config.yaml")
        config = LiteLLMConfig(config_path=config_path)
        app.state.config = config
        logger.info(f"  Loaded {len(config.get_all_models())} model configurations")
        logger.info(f"  Master key configured: {bool(config.get_master_key())}")

        # 4. Initialize memory router
        logger.info("Step 4/5: Initializing memory router...")
        memory_router = MemoryRouter(config=config.config)
        app.state.memory_router = memory_router
        logger.info(
            f"  Memory router initialized with {len(memory_router.header_patterns)} patterns"
        )

        # 5. Configure LiteLLM settings
        logger.info("Step 5/5: Configuring LiteLLM settings...")
        litellm.set_verbose = config.get_litellm_settings().get("set_verbose", True)
        litellm.drop_params = config.get_litellm_settings().get("drop_params", True)
        logger.info(f"  Verbose logging: {litellm.set_verbose}")
        logger.info(f"  Drop unknown params: {litellm.drop_params}")

        # Initialize error handler
        app.state.error_handler = LiteLLMErrorHandler(
            include_debug_info=config.get_litellm_settings().get("set_verbose", False)
        )

        logger.info("=" * 70)
        logger.info("STARTUP COMPLETE - Server ready to accept requests")
        logger.info("=" * 70)

        yield  # Application runs here

    except Exception as e:
        logger.error(f"STARTUP FAILED: {e}", exc_info=True)
        raise

    # Shutdown Phase
    logger.info("=" * 70)
    logger.info("SHUTDOWN: Cleaning up resources")
    logger.info("=" * 70)

    try:
        # Get final statistics
        session_info = LiteLLMSessionManager.get_session_info()
        logger.info(f"Final session stats: {session_info}")

        # Close session manager
        await LiteLLMSessionManager.close()
        logger.info("Session manager closed successfully")

    except Exception as e:
        logger.error(f"Error during shutdown: {e}", exc_info=True)

    logger.info("=" * 70)
    logger.info("SHUTDOWN COMPLETE")
    logger.info("=" * 70)


# ============================================================================
# FastAPI Application
# ============================================================================

app = FastAPI(
    title="LiteLLM SDK Proxy with Memory Routing",
    description="OpenAI-compatible proxy using LiteLLM SDK with persistent sessions and memory isolation",
    version="1.0.0",
    lifespan=lifespan,
)

# Register error handlers
register_exception_handlers(app, include_debug_info=bool(os.getenv("DEBUG", False)))


# ============================================================================
# Dependency Injection
# ============================================================================


def get_config() -> LiteLLMConfig:
    """Dependency: Get LiteLLM configuration."""
    return app.state.config


def get_memory_router() -> MemoryRouter:
    """Dependency: Get memory router."""
    return app.state.memory_router


def get_error_handler() -> LiteLLMErrorHandler:
    """Dependency: Get error handler."""
    return app.state.error_handler


# ============================================================================
# Authentication Middleware
# ============================================================================


async def verify_api_key(request: Request) -> None:
    """
    Verify API key from Authorization header.

    Args:
        request: FastAPI request object

    Raises:
        HTTPException: 401 if invalid or missing API key
    """
    config = get_config()

    mh = request.headers.mutablecopy()
    mh["authorization"] = f"Bearer {config.get_master_key()}"
    auth_header = mh.get("authorization", "")

    if not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header",
        )

    provided_key = auth_header[7:]  # Remove "Bearer " prefix

    if provided_key != config.get_master_key():
        logger.warning(f"Invalid API key attempt from {request.client.host}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )


# ============================================================================
# API Endpoints
# ============================================================================


@app.get("/health")
async def health_check() -> Dict[str, Any]:
    """
    Health check endpoint.

    Returns:
        Dict with status and session information
    """
    session_info = LiteLLMSessionManager.get_session_info()
    config = get_config()

    return {
        "status": "healthy",
        "version": "1.0.0",
        "session": session_info,
        "models_configured": len(config.get_all_models()),
        "litellm_sdk_injected": litellm.aclient_session is not None,
    }


@app.get("/memory-routing/info")
async def memory_routing_info(request: Request) -> Dict[str, Any]:
    """
    Get memory routing information for debugging.

    Returns detailed information about how the current request would be routed,
    including user ID detection and pattern matching.

    Args:
        request: FastAPI request object

    Returns:
        Dict with routing information
    """
    memory_router = get_memory_router()
    routing_info = memory_router.get_routing_info(request.headers)

    return {
        "routing": routing_info,
        "request_headers": dict(request.headers),
        "session_info": LiteLLMSessionManager.get_session_info(),
    }


@app.get("/v1/models")
async def list_models(request: Request) -> Dict[str, Any]:
    """
    List available models (OpenAI-compatible endpoint).

    Args:
        request: FastAPI request object

    Returns:
        Dict with list of available models
    """
    await verify_api_key(request)

    config = get_config()

    models = [
        {
            "id": model_config.model_name,
            "object": "model",
            "created": int(time.time()),
            "owned_by": "litellm",
            "permission": [],
            "root": model_config.model_name,
            "parent": None,
        }
        for model_name in config.get_all_models()
        if (model_config := config.get_model_config(model_name))
    ]

    return {
        "object": "list",
        "data": models,
    }


@app.post("/v1/chat/completions")
async def chat_completions(request: Request) -> Response:
    """
    OpenAI-compatible chat completions endpoint.

    Supports both streaming and non-streaming responses.
    Automatically injects memory routing headers based on client detection.

    Args:
        request: FastAPI request object

    Returns:
        JSONResponse for non-streaming, StreamingResponse for streaming

    Raises:
        HTTPException: For various error conditions
    """
    # Verify API key
    await verify_api_key(request)

    # Parse request body
    try:
        body = await request.json()
    except Exception as e:
        logger.error(f"Failed to parse request body: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid JSON in request body: {e}",
        )

    # Extract parameters
    model_name = body.get("model")
    messages = body.get("messages")
    stream = body.get("stream", False)

    if not model_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing required parameter: model",
        )

    if not messages:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing required parameter: messages",
        )

    # Get configuration and routing
    config = get_config()
    memory_router = get_memory_router()
    error_handler = get_error_handler()

    # Get LiteLLM parameters for this model
    try:
        litellm_params = config.get_litellm_params(model_name)
    except ValueError as e:
        logger.error(f"Model not found: {model_name}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )

    # Inject memory routing headers
    user_id = memory_router.detect_user_id(request.headers)
    logger.info(f"Request for model '{model_name}' routed to user_id: {user_id}")

    # Merge extra headers (memory routing + any from config)
    extra_headers = litellm_params.get("extra_headers", {}).copy()
    extra_headers["x-sm-user-id"] = user_id

    # Check if we need to inject Supermemory API key
    supermemory_key = os.getenv("SUPERMEMORY_API_KEY")
    if supermemory_key and memory_router.should_use_supermemory(model_name):
        extra_headers["x-supermemory-api-key"] = supermemory_key
        logger.debug(f"Injected Supermemory API key for model: {model_name}")

    litellm_params["extra_headers"] = extra_headers

    # Merge additional parameters from request body
    for key, value in body.items():
        if key not in ["model", "messages"]:
            litellm_params[key] = value

    # Generate request ID for tracking
    request_id = f"req_{int(time.time() * 1000)}"

    # Log request details
    logger.info(
        f"[{request_id}] Starting {'streaming' if stream else 'non-streaming'} request"
    )
    logger.info(f"[{request_id}] Model: {model_name}, User ID: {user_id}")

    # Handle streaming vs non-streaming
    if stream:
        return await handle_streaming_completion(
            messages=messages,
            litellm_params=litellm_params,
            request_id=request_id,
            error_handler=error_handler,
        )
    else:
        return await handle_non_streaming_completion(
            messages=messages,
            litellm_params=litellm_params,
            request_id=request_id,
            error_handler=error_handler,
        )


# ============================================================================
# Completion Handlers
# ============================================================================


async def handle_non_streaming_completion(
    messages: list,
    litellm_params: Dict[str, Any],
    request_id: str,
    error_handler: LiteLLMErrorHandler,
) -> JSONResponse:
    """
    Handle non-streaming completion request.

    Args:
        messages: Chat messages
        litellm_params: Parameters for litellm.acompletion()
        request_id: Request tracking ID
        error_handler: Error handler instance

    Returns:
        JSONResponse with completion result
    """
    try:
        start_time = time.time()

        # Call LiteLLM SDK
        response = await litellm.acompletion(
            messages=messages,
            **litellm_params,
        )

        elapsed = time.time() - start_time
        logger.info(f"[{request_id}] Completed in {elapsed:.2f}s")

        # Return OpenAI-compatible response
        # Convert response to dict (litellm.ModelResponse has dict() method)
        response_dict = response.dict() if hasattr(response, 'dict') else dict(response)
        return JSONResponse(content=response_dict)

    except Exception as e:
        logger.error(f"[{request_id}] Error: {type(e).__name__}: {e}")

        # Use error handler to convert to HTTP response
        return await error_handler.handle_completion_error(e, request_id=request_id)


async def handle_streaming_completion(
    messages: list,
    litellm_params: Dict[str, Any],
    request_id: str,
    error_handler: LiteLLMErrorHandler,
) -> StreamingResponse:
    """
    Handle streaming completion request.

    Args:
        messages: Chat messages
        litellm_params: Parameters for litellm.acompletion()
        request_id: Request tracking ID
        error_handler: Error handler instance

    Returns:
        StreamingResponse with SSE events
    """

    async def generate_stream() -> AsyncIterator[str]:
        """Generate SSE stream."""
        try:
            start_time = time.time()

            # Call LiteLLM SDK with streaming
            litellm_params["stream"] = True
            response_iterator = await litellm.acompletion(
                messages=messages,
                **litellm_params,
            )

            logger.info(f"[{request_id}] Starting stream...")
            if not isinstance(response_iterator, CustomStreamWrapper):
                raise ValueError(f"{response_iterator} should be and iterator but is: {type(response_iterator)}")
            # Use streaming utility to format SSE events
            async for sse_event in stream_litellm_completion(
                response_iterator=response_iterator,
                request_id=request_id,
                detect_infinite_loops=True,
            ):
                yield sse_event

            elapsed = time.time() - start_time
            logger.info(f"[{request_id}] Stream completed in {elapsed:.2f}s")

        except Exception as e:
            logger.error(f"[{request_id}] Stream error: {type(e).__name__}: {e}")

            # Send error as SSE event
            from proxy.streaming_utils import format_error_sse

            error_sse = format_error_sse(
                error_type=type(e).__name__,
                message=str(e),
                code=getattr(e, "status_code", None),
            )
            yield error_sse

    return StreamingResponse(
        generate_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )


# ============================================================================
# Development/Testing Entry Point
# ============================================================================


if __name__ == "__main__":
    import uvicorn

    print("=" * 70)
    print("LiteLLM SDK Proxy - Development Server")
    print("=" * 70)
    print()
    print("Starting server on http://localhost:8764")
    print()
    print("Endpoints:")
    print("  - GET  /health                    - Health check")
    print("  - GET  /memory-routing/info       - Routing debug info")
    print("  - GET  /v1/models                 - List models")
    print("  - POST /v1/chat/completions       - Chat completions")
    print()
    print("Example request:")
    print("  curl http://localhost:8764/v1/chat/completions \\")
    print("    -H 'Content-Type: application/json' \\")
    print("    -H 'Authorization: Bearer sk-1234' \\")
    print(
        '    -d \'{"model": "claude-sonnet-4.5", "messages": [{"role": "user", "content": "Hello"}]}\''
    )
    print()
    print("=" * 70)

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8764,
        log_level="info",
    )
