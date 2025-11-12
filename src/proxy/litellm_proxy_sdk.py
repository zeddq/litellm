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
import json
import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator, Dict, Optional

import litellm
from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.responses import StreamingResponse, JSONResponse
from litellm.litellm_core_utils.streaming_handler import CustomStreamWrapper
from litellm.proxy.proxy_server import master_key

from proxy.config_parser import LiteLLMConfig
from proxy.context_retriever import ContextRetriever, retrieve_and_inject_context
from proxy.error_handlers import LiteLLMErrorHandler, register_exception_handlers
from proxy.memory_router import MemoryRouter
from proxy.session_manager import LiteLLMSessionManager
from proxy.streaming_utils import stream_litellm_completion
from proxy.tool_executor import ToolExecutor, ToolExecutionConfig, should_execute_tools

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
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
        # Resilient len() check for Mock objects in tests
        model_count = (
            len(config.get_all_models())
            if hasattr(config, "get_all_models") and hasattr(config.get_all_models(), "__len__")
            else "unknown"
        )
        logger.info(f"  Loaded {model_count} model configurations:")
        logger.info(Path(config_path).read_text())
        logger.info(f"  Master key configured: {bool(config.get_master_key())}")

        # 4. Initialize memory router
        logger.info("Step 4/5: Initializing memory router...")
        memory_router = MemoryRouter(config=config.config)
        app.state.memory_router = memory_router
        # Resilient len() check for Mock objects in tests
        pattern_count = (
            len(memory_router.header_patterns)
            if hasattr(memory_router.header_patterns, "__len__")
            else "unknown"
        )
        logger.info(f"  Memory router initialized with {pattern_count} patterns")

        # 5. Configure LiteLLM settings
        logger.info("Step 5/6: Configuring LiteLLM settings...")
        litellm.set_verbose = config.get_litellm_settings().get("set_verbose", True)
        litellm.drop_params = config.get_litellm_settings().get("drop_params", True)
        logger.info(f"  Verbose logging: {litellm.set_verbose}")
        logger.info(f"  Drop unknown params: {litellm.drop_params}")

        # Initialize error handler
        app.state.error_handler = LiteLLMErrorHandler(
            include_debug_info=config.get_litellm_settings().get("set_verbose", False)
        )

        # 6. Initialize tool executor
        logger.info("Step 6/6: Initializing tool executor...")
        tool_exec_config_dict = config.config.tool_execution or {}
        tool_exec_config = ToolExecutionConfig.from_config_dict(tool_exec_config_dict)

        if should_execute_tools(tool_exec_config):
            try:
                tool_executor = ToolExecutor(
                    supermemory_api_key=tool_exec_config.supermemory_api_key,
                    supermemory_base_url=tool_exec_config.supermemory_base_url,
                    timeout=tool_exec_config.timeout_per_tool,
                    max_results=tool_exec_config_dict.get("max_results", 5) if isinstance(tool_exec_config_dict, dict) else 5,
                )
                app.state.tool_executor = tool_executor
                app.state.tool_exec_config = tool_exec_config
                logger.info(f"  ✅ Tool executor initialized (max_iterations={tool_exec_config.max_iterations})")
            except Exception as e:
                logger.warning(f"  ⚠️  Tool executor initialization failed: {e}")
                app.state.tool_executor = None
                app.state.tool_exec_config = None
        else:
            logger.info("  Tool execution disabled")
            app.state.tool_executor = None
            app.state.tool_exec_config = None

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
    debug=True,
)

# Register error handlers
register_exception_handlers(app, include_debug_info=bool(os.getenv("DEBUG", False)))


# ============================================================================
# HTTPException Handler (OpenAI Format Compatibility)
# ============================================================================


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """
    Convert FastAPI HTTPException to OpenAI-compatible error format.

    This handler ensures all HTTP errors return OpenAI's standard error format:
    {"error": {"message": "...", "type": "...", "code": "..."}}

    Args:
        request: FastAPI request object
        exc: HTTPException instance

    Returns:
        JSONResponse with OpenAI-compatible error format
    """
    # Map status codes to OpenAI error types
    error_type_map = {
        400: "invalid_request_error",
        401: "authentication_error",
        403: "permission_error",
        404: "not_found_error",
        408: "timeout_error",
        429: "rate_limit_error",
        500: "api_error",
        503: "service_unavailable_error",
    }

    error_type = error_type_map.get(exc.status_code, "api_error")

    # Build base error response
    error_content: Dict[str, Any] = {
        "message": exc.detail,
        "type": error_type,
    }

    # Add specific error codes based on status and message
    detail_lower = str(exc.detail).lower()

    if exc.status_code == 401:
        error_content["code"] = "invalid_api_key"
    elif exc.status_code == 404:
        error_content["code"] = "model_not_found"
    elif exc.status_code == 400:
        if "model" in detail_lower and "missing" in detail_lower:
            error_content["code"] = "missing_parameter"
            error_content["param"] = "model"
        elif "messages" in detail_lower and "missing" in detail_lower:
            error_content["code"] = "missing_parameter"
            error_content["param"] = "messages"
        elif "json" in detail_lower or "invalid" in detail_lower:
            error_content["code"] = "invalid_request"
        else:
            error_content["code"] = "invalid_parameter"

    # Log the error
    logger.warning(
        f"HTTP {exc.status_code}: {exc.detail}",
        extra={"status_code": exc.status_code, "path": request.url.path},
    )

    return JSONResponse(
        status_code=exc.status_code,
        content={"error": error_content},
    )


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


def get_tool_executor() -> Optional[ToolExecutor]:
    """Dependency: Get tool executor (may be None if disabled)."""
    return getattr(app.state, "tool_executor", None)


def get_tool_exec_config() -> Optional[ToolExecutionConfig]:
    """Dependency: Get tool execution config (may be None if disabled)."""
    return getattr(app.state, "tool_exec_config", None)


def should_use_context_retrieval(model_name: str, config: LiteLLMConfig) -> bool:
    """
    Check if context retrieval should be used for the given model.

    Args:
        model_name: The model name to check
        config: LiteLLM configuration

    Returns:
        True if context retrieval is enabled and model is allowed, False otherwise
    """
    try:
        # Get context retrieval config - handle both Pydantic models and dicts
        if hasattr(config.config, 'context_retrieval'):
            # Pydantic model (production)
            context_retrieval_obj = config.config.context_retrieval
            if context_retrieval_obj is None:
                return False
            context_config = context_retrieval_obj.model_dump() if hasattr(context_retrieval_obj, 'model_dump') else context_retrieval_obj
        elif isinstance(config.config, dict):
            # Dict (tests)
            context_config = config.config.get("context_retrieval")
            if context_config is None:
                return False
        else:
            logger.debug("Context retrieval config not found")
            return False
        
        if not context_config or not context_config.get("enabled", False):
            logger.debug("Context retrieval is disabled globally")
            return False

        # Check model-specific filters
        enabled_for_models = context_config.get("enabled_for_models")
        disabled_for_models = context_config.get("disabled_for_models")

        # If enabled_for_models is specified, only those models are allowed
        if enabled_for_models is not None:
            if model_name in enabled_for_models:
                logger.debug(f"Context retrieval enabled for model: {model_name}")
                return True
            else:
                logger.debug(f"Context retrieval not enabled for model: {model_name}")
                return False

        # If disabled_for_models is specified, those models are disallowed
        if disabled_for_models is not None:
            if model_name in disabled_for_models:
                logger.debug(f"Context retrieval disabled for model: {model_name}")
                return False
            else:
                logger.debug(f"Context retrieval enabled for model: {model_name}")
                return True

        # If neither filter is specified, enable for all models
        logger.debug(f"Context retrieval enabled for all models (no filters)")
        return True

    except Exception as e:
        logger.error(f"Error checking context retrieval config: {e}")
        return False


async def apply_context_retrieval(
    messages: list,
    model_name: str,
    user_id: str,
    config: LiteLLMConfig,
) -> list:
    """
    Apply context retrieval to messages if enabled.

    Args:
        messages: Original chat messages
        model_name: Model name for filtering
        user_id: User ID for memory isolation
        config: LiteLLM configuration

    Returns:
        Enhanced messages with context, or original messages if retrieval fails/disabled
    """
    if not should_use_context_retrieval(model_name, config):
        return messages

    try:
        # Get context retrieval configuration - handle both Pydantic models and dicts
        if hasattr(config.config, 'context_retrieval'):
            # Pydantic model (production)
            context_retrieval_obj = config.config.context_retrieval
            if context_retrieval_obj is None:
                return messages
            context_config = context_retrieval_obj.model_dump() if hasattr(context_retrieval_obj, 'model_dump') else context_retrieval_obj
        elif isinstance(config.config, dict):
            # Dict (tests)
            context_config = config.config.get("context_retrieval", {})
        else:
            logger.warning("Context retrieval config not found")
            return messages
        
        # Get API key (resolve environment variable if needed)
        api_key = context_config.get("api_key")
        if isinstance(api_key, str) and api_key.startswith("os.environ/"):
            env_var = api_key.split("/", 1)[1]
            api_key = os.getenv(env_var)
            
        if not api_key:
            logger.warning("Context retrieval enabled but SUPERMEMORY_API_KEY not set")
            return messages

        # Get persistent HTTP client from session manager
        http_client = await LiteLLMSessionManager.get_client()

        # Initialize ContextRetriever with config values
        retriever = ContextRetriever(
            api_key=api_key,
            base_url=context_config.get("base_url", "https://api.supermemory.ai"),
            http_client=http_client,
            default_container_tag=context_config.get("container_tag", "supermemory"),
            max_context_length=context_config.get("max_context_length", 4000),
            timeout=context_config.get("timeout", 10.0),
        )

        # Retrieve and inject context
        enhanced_messages, metadata = await retrieve_and_inject_context(
            retriever=retriever,
            messages=messages,
            user_id=user_id,
            query_strategy=context_config.get("query_strategy", "last_user"),
            injection_strategy=context_config.get("injection_strategy", "system"),
            container_tag=context_config.get("container_tag"),
        )

        if metadata:
            logger.info(
                f"Context retrieval successful: {metadata.get('results_count', 0)} results, "
                f"query='{metadata.get('query', 'N/A')}'"
            )
        else:
            logger.info("Context retrieval returned no results")

        return enhanced_messages

    except Exception as e:
        logger.error(f"Context retrieval failed, using original messages: {e}", exc_info=True)
        return messages


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
    auth_header = request.headers.get("authorization", "")

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

    # Resilient len() check for Mock objects in tests
    models = config.get_all_models()
    models_count = (
        len(models)
        if hasattr(models, "__len__")
        else "unknown"
    )

    return {
        "status": "healthy",
        "version": "1.0.0",
        "session": session_info,
        "models_configured": models_count,
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
    
    logger.info(f"Request headers: {request.headers.items()}")
    logger.info(f"Request body: {body}")

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

    # Apply context retrieval if enabled
    messages = await apply_context_retrieval(
        messages=messages,
        model_name=model_name,
        user_id=user_id,
        config=config,
    )

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
            user_id=user_id,
        )


# ============================================================================
# Completion Handlers
# ============================================================================


async def handle_non_streaming_completion(
    messages: list,
    litellm_params: Dict[str, Any],
    request_id: str,
    error_handler: LiteLLMErrorHandler,
    user_id: Optional[str] = None,
) -> JSONResponse:
    """
    Handle non-streaming completion request with automatic tool execution.

    If the LLM returns tool_calls, this function automatically:
    1. Executes the tools using ToolExecutor
    2. Appends tool results to messages
    3. Calls the LLM again with the tool results
    4. Repeats until a final text response is received

    Args:
        messages: Chat messages
        litellm_params: Parameters for litellm.acompletion()
        request_id: Request tracking ID
        error_handler: Error handler instance
        user_id: User ID for tool execution context (optional)

    Returns:
        JSONResponse with completion result (final text response)
    """
    try:
        start_time = time.time()

        # Get tool executor and config
        tool_executor = get_tool_executor()
        tool_exec_config = get_tool_exec_config()

        # Tool execution loop
        iteration = 0
        max_iterations = tool_exec_config.max_iterations if tool_exec_config else 10

        while iteration < max_iterations:
            iteration += 1
            logger.info(f"[{request_id}] Tool execution iteration {iteration}/{max_iterations}")

            # Call LiteLLM SDK
            response = await litellm.acompletion(
                messages=messages,
                **litellm_params,
            )

            # Check if response has tool_calls
            has_tool_calls = False
            tool_calls = None

            # Extract tool_calls from response (different formats possible)
            if hasattr(response, 'choices') and response.choices:
                choice = response.choices[0]
                if hasattr(choice, 'message') and hasattr(choice.message, 'tool_calls'):
                    tool_calls = choice.message.tool_calls
                    has_tool_calls = tool_calls is not None and len(tool_calls) > 0

            if not has_tool_calls:
                # No tool calls - return final response
                elapsed = time.time() - start_time
                logger.info(f"[{request_id}] Completed in {elapsed:.2f}s (no tool calls)")

                # Return OpenAI-compatible response
                response_dict = response.model_dump() if hasattr(response, 'model_dump') else dict(response)
                return JSONResponse(content=response_dict)

            # Check if tool executor is available
            if not tool_executor:
                logger.warning(f"[{request_id}] Tool calls detected but tool executor not initialized")
                # Return response as-is (client needs to handle tool calls)
                response_dict = response.model_dump() if hasattr(response, 'model_dump') else dict(response)
                return JSONResponse(content=response_dict)

            # Execute tools
            logger.info(f"[{request_id}] Executing {len(tool_calls)} tool call(s)")

            # Append assistant message with tool_calls to messages
            assistant_message = {
                "role": "assistant",
                "content": response.choices[0].message.content if response.choices[0].message.content else "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": tc.type,
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        }
                    }
                    for tc in tool_calls
                ]
            }
            messages.append(assistant_message)

            # Execute each tool and append results
            for tool_call in tool_calls:
                tool_name = tool_call.function.name
                tool_args_str = tool_call.function.arguments
                tool_call_id = tool_call.id

                logger.info(f"[{request_id}] Executing tool: {tool_name} (id={tool_call_id})")

                try:
                    # Parse tool arguments
                    tool_args = json.loads(tool_args_str) if isinstance(tool_args_str, str) else tool_args_str

                    # Execute tool
                    tool_result = await tool_executor.execute_tool_call(
                        tool_name=tool_name,
                        tool_args=tool_args,
                        user_id=user_id or "default",
                        tool_call_id=tool_call_id,
                    )

                    # Format tool result for LLM
                    tool_result_content = tool_executor.format_tool_result_for_llm(tool_result)

                    logger.info(f"[{request_id}] Tool {tool_name} executed successfully")

                except Exception as tool_error:
                    logger.error(f"[{request_id}] Tool execution failed: {tool_error}", exc_info=True)
                    tool_result_content = f"Tool execution error: {str(tool_error)}"

                # Append tool result message
                tool_message = {
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "content": tool_result_content,
                }
                messages.append(tool_message)

            logger.info(f"[{request_id}] All tools executed, sending results back to LLM")

        # Max iterations reached
        elapsed = time.time() - start_time
        logger.warning(f"[{request_id}] Max iterations ({max_iterations}) reached in {elapsed:.2f}s")

        # Return last response even if it has tool_calls
        response_dict = response.model_dump() if hasattr(response, 'model_dump') else dict(response)
        return JSONResponse(content=response_dict)

    except Exception as e:
        logger.error(f"[{request_id}] Error: {type(e).__name__}: {e}", exc_info=True)

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
        log_level="debug",
    )
