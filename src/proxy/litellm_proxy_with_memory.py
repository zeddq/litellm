"""
LiteLLM Proxy with Dynamic Supermemory Routing

This is a complete proxy implementation that integrates the MemoryRouter
for client-specific memory isolation.

Refactored to eliminate global variables and use FastAPI best practices:
- Factory function pattern for app creation
- Dependency injection for MemoryRouter access
- app.state for storing application-level objects
- Lifespan context manager for startup/shutdown

Usage:
    python litellm_proxy_with_memory.py --config config.yaml --port 8765
"""

import argparse
import asyncio
import json
import logging
import os
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Annotated, Any, Dict, Optional, TypedDict

import httpx
import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.responses import StreamingResponse
from starlette.datastructures import Headers

from proxy import schema
# Handle both package and direct execution imports
from proxy.memory_router import MemoryRouter
import litellm

# Type definition for Anthropic thinking parameters
# This replaces the non-existent litellm.types.llms.anthropic.AnthropicThinkingParam
class AnthropicThinkingParam(TypedDict, total=False):
    """TypedDict for Anthropic extended thinking parameters."""
    type: str
    budget_tokens: int

# if os.getenv('ENABLE_DEBUG'):
#       import debugpy
#       debugpy.listen(("localhost", 5678))
#       print("⏳ Waiting for debugger to attach...")
#       debugpy.wait_for_client()
#       print("✅ Debugger attached!")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(filename)s:%(lineno)d:%(funcName)s() | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class ProxySessionManager:
    """
    Manages persistent HTTP sessions for upstream endpoints.

    This class solves the Cloudflare cookie persistence problem by maintaining
    a single httpx.AsyncClient instance per upstream endpoint. Cloudflare sets
    cookies (like cf_clearance) after passing bot challenges, and these cookies
    must be reused across requests to avoid repeated rate limiting.

    Without session persistence:
        Request 1 → 429 + cookie → client closed (cookie lost)
        Request 2 → 429 + cookie → client closed (cookie lost) [FAIL]

    With session persistence:
        Request 1 → 429 + cookie → stored in session
        Request 2 → 200 OK (cookie reused) [SUCCESS]

    Thread Safety:
        Uses asyncio.Lock to ensure thread-safe access to the session dictionary.
    """

    _sessions: dict[str, httpx.AsyncClient] = {}
    _lock = asyncio.Lock()

    @classmethod
    async def get_session(cls, base_url: str) -> httpx.AsyncClient:
        """
        Get or create a persistent session for an endpoint.

        Args:
            base_url: Base URL of the upstream endpoint (e.g., "http://localhost:4000")

        Returns:
            Persistent httpx.AsyncClient instance with cookie jar
        """
        async with cls._lock:
            if base_url not in cls._sessions:
                cls._sessions[base_url] = httpx.AsyncClient(
                    base_url=base_url,
                    follow_redirects=True,
                    timeout=httpx.Timeout(600.0),
                    # Cookies are automatically handled by httpx.AsyncClient
                    # The client maintains a cookie jar that persists across requests
                )
                logger.info(f"🍪 Created new persistent session for {base_url}")
                logger.info(f"📊 Total active sessions: {len(cls._sessions)}")
            return cls._sessions[base_url]

    @classmethod
    async def close_all(cls):
        """
        Close all sessions gracefully.

        Should be called during application shutdown to release resources.
        """
        logger.info(f"🔒 Closing {len(cls._sessions)} persistent sessions...")
        for base_url, session in cls._sessions.items():
            try:
                await session.aclose()
                logger.info(f"✅ Closed session for {base_url}")
            except Exception as e:
                logger.error(f"❌ Error closing session for {base_url}: {e}")
        cls._sessions.clear()
        logger.info("🏁 All sessions closed")


def get_request_id() -> str:
    """Generate a short request ID for logging."""
    import secrets

    return secrets.token_hex(2)


def round_thinking(th: int):
    match th:
        case n if n < 100:
            return 0
        case n if n < 1500:
            return 1024
        case n if n < 2400:
            return 2048
        case _:
            return 4096


def is_rate_limit_error(status_code: int, response_body: bytes) -> bool:
    """
    Detect if response indicates rate limiting.
    
    Checks for:
    - HTTP 429 (Too Many Requests)
    - HTTP 503 (Service Unavailable) 
    - Cloudflare 1200 error in response body
    - Other rate limit indicators
    
    Args:
        status_code: HTTP status code
        response_body: Response body bytes
        
    Returns:
        True if rate limiting detected
    """
    if status_code in (429, 503):
        return True
    
    # Check for Cloudflare 1200 error in response body
    if response_body:
        body_str = response_body.decode('utf-8', errors='ignore').lower()
        if 'error 1200' in body_str or 'rate limited' in body_str:
            return True
    
    return False


async def proxy_request_with_retry(
    method: str,
    path: str,
    headers: Headers,
    body: Optional[bytes],
    litellm_base_url: str,
    request_id: str,
    max_retries: int = 3,
    initial_delay: float = 1.0,
) -> tuple[int, httpx.Headers, bytes]:
    """
    Forward request to LiteLLM proxy with exponential backoff retry logic.

    Uses persistent HTTP session to maintain cookies across requests. This is
    CRITICAL for Cloudflare compatibility - cookies like cf_clearance are set
    after passing bot challenges and must be reused to avoid repeated rate limits.

    Retries on rate limit errors (429, 503, Cloudflare 1200) with exponential backoff.

    Args:
        method: HTTP method
        path: Request path
        headers: Request headers
        body: Request body
        litellm_base_url: Base URL for LiteLLM proxy
        request_id: Request ID for logging
        max_retries: Maximum number of retry attempts
        initial_delay: Initial delay in seconds before first retry

    Returns:
        Tuple of (status_code, headers, body)

    Raises:
        Exception: If all retries are exhausted
    """
    # Get persistent session for this endpoint - cookies will be automatically stored
    session = await ProxySessionManager.get_session(litellm_base_url)

    for attempt in range(max_retries + 1):
        try:
            # Use persistent session instead of creating new client
            # Cookies from previous requests (including cf_clearance) are automatically included
            response = await session.request(
                method=method,
                url=path,  # path is relative to base_url set in session
                headers=headers,
                content=body
            )

            # Log cookie information for debugging
            if response.cookies:
                cookie_names = list(response.cookies.keys())
                logger.info(
                    f"{request_id} 🍪 Received cookies: {cookie_names} "
                    f"(session now has {len(session.cookies)} total cookies)"
                )

            # Check if we got a rate limit error
            if is_rate_limit_error(response.status_code, response.content):
                if attempt < max_retries:
                    # Calculate exponential backoff delay
                    delay = initial_delay * (2 ** attempt)
                    logger.warning(
                        f"{request_id} ⚠️ Rate limit detected (status={response.status_code}), "
                        f"retrying in {delay:.1f}s (attempt {attempt + 1}/{max_retries}) "
                        f"[Session cookies: {len(session.cookies)}]"
                    )
                    await asyncio.sleep(delay)
                    continue
                else:
                    logger.error(
                        f"{request_id} ❌ Rate limit error after {max_retries} retries, giving up"
                    )

            # Success - log if we recovered from rate limiting
            if attempt > 0:
                logger.info(
                    f"{request_id} ✅ Request succeeded after {attempt} retries "
                    f"(cookies helped!)"
                )

            return response.status_code, response.headers, response.content

        except httpx.TimeoutException as e:
            if attempt < max_retries:
                delay = initial_delay * (2 ** attempt)
                logger.warning(
                    f"{request_id} ⏱️ Request timeout, retrying in {delay:.1f}s "
                    f"(attempt {attempt + 1}/{max_retries})"
                )
                await asyncio.sleep(delay)
                continue
            else:
                logger.error(f"{request_id} ❌ Request timeout after {max_retries} retries")
                raise

        except Exception as e:
            logger.error(f"{request_id} ❌ Proxy request failed: {e}")
            raise

    raise Exception(f"All {max_retries} retry attempts exhausted")


async def proxy_request(
    method: str,
    path: str,
    headers: Headers,
    body: Optional[bytes],
    litellm_base_url: str,
) -> tuple[int, httpx.Headers, bytes]:
    """
    Forward request to LiteLLM proxy.

    Args:
        method: HTTP method
        path: Request path
        headers: Request headers
        body: Request body
        litellm_base_url: Base URL for LiteLLM proxy

    Returns:
        Tuple of (status_code, headers, body)
    """
    url = f"{litellm_base_url}{path}"

    async with httpx.AsyncClient(timeout=600.0) as client:
        try:
            response = await client.request(
                method=method, url=url, headers=headers, content=body
            )

            return response.status_code, response.headers, response.content
        except Exception as e:
            logger.error(f"Proxy request failed: {e}")
            raise


def get_memory_router(request: Request) -> Optional[MemoryRouter]:
    """
    Dependency injection function to retrieve MemoryRouter from app state.

    This function is used as a FastAPI dependency to inject the MemoryRouter
    instance into route handlers without using global variables.

    Args:
        request: FastAPI request object containing app state

    Returns:
        MemoryRouter instance or None if not initialized
    """
    return getattr(request.app.state, "memory_router", None)


def get_litellm_base_url(request: Request) -> str:
    """
    Dependency injection function to retrieve LiteLLM base URL from app state.

    Args:
        request: FastAPI request object containing app state

    Returns:
        LiteLLM base URL string
    """
    return getattr(request.app.state, "litellm_base_url", "http://localhost:4000")


def get_litellm_auth_token(request: Request) -> str:
    """
    Dependency injection function to retrieve LiteLLM base URL from app state.

    Args:
        request: FastAPI request object containing app state

    Returns:
        LiteLLM base URL string
    """
    return request.app.state.litellm_auth_token





def is_valid_date(date_string: str) -> bool:
    try:
        datetime.strptime(date_string, "%Y%m%d")
        return True
    except ValueError:
        return False


def _adapt_llm_req_params(rid: str, body: bytes) -> Optional[dict]:
    try:
        body_data = json.loads(body.decode("utf-8"))
        is_stream_request = body_data.get("stream", False)
        logger.info(f"{rid} Stream request: {is_stream_request}")

        # round thinking to the values that littlellm is able to translate to openai format
        if "thinking" in body_data:
            anthropic_thinking = AnthropicThinkingParam(body_data["thinking"])
            anthropic_thinking["budget_tokens"] = round_thinking(
                anthropic_thinking.get("budget_tokens", 0)
            )
            body_data["thinking"] = anthropic_thinking
        # pop temperature (not supported)
        if "temperature" in body_data:
            del body_data["temperature"]

        return body_data
    except json.JSONDecodeError:
        return None


class MyFastMemoryLane(FastAPI):
    def __init__(
        self,
        memory_router: MemoryRouter | None,
        litellm_auth_token: str,
        litellm_base_url: str,
        *args,
        **kwargs,
    ) -> None:
        self.memory_router = memory_router
        self.litellm_auth_token = litellm_auth_token
        self.litellm_base_url = litellm_base_url

        @asynccontextmanager
        async def lifespan(app: FastAPI) -> AsyncIterator[None]:
            """
            Lifespan context manager for application startup and shutdown.

            This replaces the deprecated @app.on_event("startup") decorator
            and provides a cleaner way to manage application lifecycle.
            """
            # Startup: Initialize app state
            logger.info("Application starting up...")
            app.state.memory_router = memory_router
            app.state.litellm_base_url = litellm_base_url
            app.state.litellm_auth_token = litellm_auth_token

            if memory_router:
                # Resilient len() check for Mock objects in tests
                pattern_count = (
                    len(memory_router.header_patterns)
                    if hasattr(memory_router.header_patterns, "__len__")
                    else "unknown"
                )
                logger.info(f"Memory Router initialized with {pattern_count} patterns")
                
                # Initialize MCP Client if configured
                if memory_router.config and memory_router.config.mcp_servers:
                    logger.info("Initializing MCP Client...")
                    mcp_servers_dict = {}
                    for name, config in memory_router.config.mcp_servers.items():
                        if config.transport == "stdio":
                            mcp_servers_dict[name] = {"args": [config.command] + (config.args or [])}
                        elif config.transport == "sse":
                            mcp_servers_dict[name] = {"url": config.url}
                    
                    if mcp_servers_dict:
                        try:
                            # Load tools from configured MCP servers
                            mcp_tools = await litellm.experimental_mcp_client.load_mcp_tools(
                                mcp_servers=mcp_servers_dict
                            )
                            app.state.mcp_tools = mcp_tools
                            logger.info(f"✅ Loaded {len(mcp_tools)} MCP tools from {list(mcp_servers_dict.keys())}")
                        except Exception as e:
                            logger.error(f"❌ Failed to load MCP tools: {e}")
            else:
                logger.warning("Memory Router not provided - memory routing disabled")

            logger.info(f"Forwarding requests to LiteLLM at {litellm_base_url}")

            yield  # Application runs here

            logger.info("Application shutting down...")
            await ProxySessionManager.close_all()

        super().__init__(*args, lifespan=lifespan, **kwargs)


# noinspection D
def create_app(
    litellm_auth_token: str,
    memory_router: Optional[MemoryRouter] = None,
    litellm_base_url: str = "http://localhost:4000",
) -> FastAPI:
    """
    Factory function to create and configure a FastAPI application.

    This factory pattern allows for:
    - Dependency injection of MemoryRouter
    - Better testability (can create multiple app instances with different configs)
    - Elimination of global state
    - Cleaner separation of concerns

    Args:
        memory_router: Optional MemoryRouter instance for memory routing logic
        litellm_base_url: Base URL for the upstream LiteLLM proxy

    Returns:
        Configured FastAPI application instance
        :param litellm_base_url:
        :type litellm_base_url:
        :param memory_router:
        :type memory_router:
        :param litellm_auth_token:
        :type litellm_auth_token:
    """

    # Don't create a default router if None is passed
    # if not memory_router:
    #     memory_router = MemoryRouter()

    # Create FastAPI app with lifespan
    app = MyFastMemoryLane(
        memory_router=memory_router,
        litellm_auth_token=litellm_auth_token,
        litellm_base_url=litellm_base_url,
        title="LiteLLM Proxy with Memory Routing",
    )

    # Define route handlers
    # IMPORTANT: Specific routes must be defined BEFORE the catch-all route
    # Order matters in FastAPI - first matching route wins

    @app.get("/health")
    async def health_check(
        memory_router: Annotated[
            Optional[MemoryRouter], Depends(get_memory_router)
        ] = None,
        litellm_base_url: Annotated[str, Depends(get_litellm_base_url)] = "",
    ):
        """
        Health check endpoint.

        Uses dependency injection to access app state without global variables.

        Args:
            memory_router: Injected MemoryRouter instance
            litellm_base_url: Injected LiteLLM base URL
        """
        return {
            "status": "healthy",
            "memory_router": memory_router is not None,
            "litellm_base_url": litellm_base_url,
        }

    @app.get("/memory-routing/info")
    async def routing_info(
        request: Request,
        memory_router: Annotated[
            Optional[MemoryRouter], Depends(get_memory_router)
        ] = None,
    ):
        """
        Debug endpoint to check memory routing for current headers.

        Usage:
            curl http://localhost:8765/memory-routing/info \
                -H "User-Agent: OpenAIClientImpl/Java unknown"

        Args:
            request: FastAPI request object
            memory_router: Injected MemoryRouter instance
        
        Returns:
            Dict with routing information in standardized format matching SDK proxy
        """
        if memory_router:
            routing_info = memory_router.get_routing_info(request.headers)
            return {
                "routing": routing_info,
                "request_headers": dict(request.headers),
            }
        return {"error": "Memory router not initialized"}

    async def verify_api_key(request: Request) -> None:
        """
        Verify API key from Authorization header.

        Args:
            request: FastAPI request object

        Raises:
            HTTPException: 401 if invalid or missing API key
        """
        auth_header = request.headers.get("authorization", "")

        if not auth_header.startswith("Bearer "):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing or invalid Authorization header",
            )

        provided_key = auth_header[7:]  # Remove "Bearer " prefix
        expected_key = litellm_auth_token

        if provided_key != expected_key:
            logger.warning(f"Invalid API key attempt from {request.client.host if request.client else 'unknown'}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid API key",
            )

    @app.get("/v1/models")
    async def list_models(
        request: Request,
        memory_router: Annotated[
            Optional[MemoryRouter], Depends(get_memory_router)
        ] = None,
    ) -> Dict[str, Any]:
        """
        List available models (OpenAI-compatible endpoint).

        Args:
            request: FastAPI request object
            memory_router: Injected MemoryRouter instance

        Returns:
            Dict with list of available models
        """
        # Verify API key before serving models list
        await verify_api_key(request)

        if not memory_router or not memory_router.config:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Configuration not available",
            )

        config = memory_router.config

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
            for model_config in config.model_list
        ]

        return {
            "object": "list",
            "data": models,
        }





    # Catch-all proxy handler - MUST be defined LAST
    # noinspection D
    @app.api_route(
        "/{path:path}",
        methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    )
    async def proxy_handler(
        request: Request,
        path: str,
        memory_router: Annotated[
            Optional[MemoryRouter], Depends(get_memory_router)
        ] = None,
        litellm_base_url: Annotated[str, Depends(get_litellm_base_url)] = "",
        litellm_auth_token: Annotated[str, Depends(get_litellm_auth_token)] = ""
    ):
        """
        Main proxy handler with memory routing.

        Intercepts requests, detects client type, and injects appropriate
        Supermemory user ID before forwarding to LiteLLM.

        Uses dependency injection to access MemoryRouter and configuration
        instead of relying on global variables.

        Args:
            request: FastAPI request object
            path: Request path
            memory_router: Injected MemoryRouter instance
            litellm_base_url: Injected LiteLLM base URL
            litellm_auth_token: Injected LiteLLM auth token
        """
        request_id = get_request_id()


        # Read request details
        method = request.method
        full_path = request.url.path
        if request.url.query:
            full_path += f"?{request.url.query}"

        headers = request.headers.mutablecopy()
        # Remove headers that shouldn't be forwarded
        del headers["host"]
        # Replace Authorization with your API key
        headers["Authorization"] = litellm_auth_token
        
        # Add custom User-Agent to identify the proxy and avoid rate limiting
        if "user-agent" not in headers:
            headers["user-agent"] = "LiteLLM-Memory-Proxy/1.0"
        
        # Preserve important headers that Cloudflare/Supermemory might need
        # These help with rate limiting and proper routing
        if "x-forwarded-for" not in headers and "x-real-ip" in request.headers:
            headers["x-forwarded-for"] = request.headers["x-real-ip"]

        body = await request.body()

        logger.info(f"{request_id} REQUEST: {method} {full_path}")
        logger.info(f"{request_id} HEADERS: {headers}")

        # Check if this is a Supermemory-enabled model request
        # For chat completions, check the model in body
        if "/chat/completions" in full_path or "/v1/messages" in full_path:
            # Try to parse JSON, but continue even if it fails
            request_data = None
            try:
                if body:
                    request_data = json.loads(body)
            except json.JSONDecodeError:
                logger.warning(f"{request_id} Failed to parse request body as JSON, forwarding as-is")

            if request_data:
                try:
                    model_name: str = request_data.get("model", "")

                    # Extract experimental features from model string if present
                    # Format: "model-name,feature1,feature2,feature3"
                    if "," in model_name:
                        parts = model_name.split(",")
                        model_name = parts[0]  # First part is the actual model
                        experimental_features = parts[1:]  # Rest are features

                        # Add anthropic-beta header with experimental features
                        if experimental_features:
                            beta_header_value = ",".join(experimental_features)
                            headers["anthropic-beta"] = beta_header_value
                            logger.info(
                                f"{request_id} EXPERIMENTAL FEATURES: {beta_header_value}"
                            )
                            # Update model in request body to use cleaned model name
                            request_data["model"] = model_name
                            body = json.dumps(request_data).encode()

                    if len(model_name) >= 8:
                        if is_valid_date(model_name[-8:]):
                            model_name = model_name[:-8].rstrip("-")

                    # Check if model uses Supermemory (only if router is available)
                    if memory_router and memory_router.should_use_supermemory(
                        model_name
                    ):
                        # Get routing info for logging
                        routing_info = memory_router.get_routing_info(headers)
                        user_id = routing_info["user_id"]

                        logger.info(
                            f"{request_id} MEMORY ROUTING: model={model_name}, user_id={user_id}"
                        )
                        if routing_info["matched_pattern"]:
                            pattern = routing_info["matched_pattern"]
                            logger.info(
                                f"{request_id} MATCHED PATTERN: {pattern['header']}='{pattern['value']}' "
                                f"-> {pattern['user_id']}"
                            )

                        # Inject Supermemory headers
                        supermemory_key = os.environ.get("SUPERMEMORY_API_KEY")
                        headers = memory_router.inject_memory_headers(
                            headers, supermemory_key
                        )
                        logger.info(f"{request_id} INJECTED: x-sm-user-id={user_id}")

                    # Inject MCP tools if available
                    mcp_tools = getattr(request.app.state, "mcp_tools", [])
                    if mcp_tools:
                        current_tools = request_data.get("tools", [])
                        # Avoid duplicates if possible, or just append
                        request_data["tools"] = current_tools + mcp_tools
                        request_data["tool_choice"] = request_data.get("tool_choice", "auto")
                        logger.info(f"{request_id} INJECTED: {len(mcp_tools)} MCP tools")
                        body = json.dumps(request_data).encode()

                except Exception as e:
                    logger.error(f"{request_id} Error in memory/MCP routing: {e}")
                    # Don't fail the request, just log and continue
        # Forward request to LiteLLM with retry logic (outside the chat completions block)
        try:
            status_code, response_headers, response_body = await proxy_request_with_retry(
                method=method,
                path=full_path,
                headers=headers,
                body=body if body else None,
                litellm_base_url=litellm_base_url,
                request_id=request_id,
                max_retries=3,
                initial_delay=1.0,
            )

            # Check if streaming response
            content_type = response_headers.get("content-type", "")
            if (
                "text/event-stream" in content_type
                or "application/x-ndjson" in content_type
            ):
                logger.info(f"{request_id} Handling as streaming response")

                async def stream_response():
                    # Use persistent session for streaming too!
                    # This ensures cookies are maintained for streaming requests
                    session = await ProxySessionManager.get_session(litellm_base_url)
                    async with session.stream(
                        method=method,
                        url=full_path,  # relative to base_url
                        headers=headers,
                        content=body,
                    ) as response:
                        async for chunk in response.aiter_bytes():
                            yield chunk
                    logger.info(f"{request_id} 🌊 Stream completed successfully")

                return StreamingResponse(
                    stream_response(),
                    status_code=status_code,
                    headers=dict(response_headers),
                    media_type=content_type,
                )
            logger.info(f"{request_id} Handling as non-streaming response")
            
            # MCP Tool Execution Logic (Agentic Loop)
            # If the response contains MCP tool calls, execute them and loop back to LLM
            try:
                resp_json = json.loads(response_body)
                choices = resp_json.get("choices", [])
                if choices and choices[0].get("message", {}).get("tool_calls"):
                    tool_calls = choices[0]["message"]["tool_calls"]
                    mcp_tools_list = getattr(request.app.state, "mcp_tools", [])
                    mcp_tool_names = {t["function"]["name"] for t in mcp_tools_list}
                    
                    executed_mcp_tools = []
                    for tc in tool_calls:
                        if tc["function"]["name"] in mcp_tool_names:
                            logger.info(f"{request_id} 🛠️ Executing MCP tool: {tc['function']['name']}")
                            tool_result = await litellm.experimental_mcp_client.call_openai_tool(tc)
                            executed_mcp_tools.append({
                                "tool_call_id": tc["id"],
                                "role": "tool", 
                                "name": tc["function"]["name"],
                                "content": json.dumps(tool_result)
                            })
                    
                    if executed_mcp_tools and request_data:
                        logger.info(f"{request_id} 🔄 MCP tools executed, sending results back to LLM...")
                        # Construct new conversation history
                        new_messages = request_data.get("messages", []) + [choices[0]["message"]] + executed_mcp_tools
                        request_data["messages"] = new_messages
                        new_body = json.dumps(request_data).encode()
                        
                        # Recursive call (single depth for now)
                        status_code, response_headers, response_body = await proxy_request_with_retry(
                            method=method,
                            path=full_path,
                            headers=headers,
                            body=new_body,
                            litellm_base_url=litellm_base_url,
                            request_id=f"{request_id}-retry",
                            max_retries=3
                        )
                        logger.info(f"{request_id} ✅ Received final response after MCP execution")

            except Exception as e:
                logger.error(f"{request_id} ⚠️ Error in MCP tool execution loop: {e}")
                # Fallback to returning original response

            return Response(
                content=response_body,
                status_code=status_code,
                headers=dict(response_headers),
            )

        except httpx.ConnectError as e:
            logger.error(f"{request_id} Backend unavailable: {e}")
            error_response = {
                "error": {
                    "message": f"Backend service unavailable: {str(e)}",
                    "type": "connection_error",
                    "code": "backend_unavailable"
                }
            }
            return Response(
                content=json.dumps(error_response).encode(),
                status_code=500,
                headers={"content-type": "application/json"},
            )
        except httpx.TimeoutException as e:
            logger.error(f"{request_id} Request timeout: {e}")
            error_response = {
                "error": {
                    "message": f"Request timeout: {str(e)}",
                    "type": "timeout_error",
                    "code": "request_timeout"
                }
            }
            return Response(
                content=json.dumps(error_response).encode(),
                status_code=504,
                headers={"content-type": "application/json"},
            )
        except json.JSONDecodeError as e:
            logger.error(f"{request_id} Malformed response from backend: {e}")
            error_response = {
                "error": {
                    "message": "Malformed response from backend",
                    "type": "invalid_response_error",
                    "code": "malformed_response"
                }
            }
            return Response(
                content=json.dumps(error_response).encode(),
                status_code=502,
                headers={"content-type": "application/json"},
            )
        except Exception as e:
            logger.error(f"{request_id} Proxy error: {e}")
            error_response = {
                "error": {
                    "message": f"Internal proxy error: {str(e)}",
                    "type": "internal_error",
                    "code": "proxy_error"
                }
            }
            return Response(
                content=json.dumps(error_response).encode(),
                status_code=500,
                headers={"content-type": "text/plain"},
            )

    return app


def main():
    """
    Run the proxy server.

    This function:
    1. Parses command-line arguments
    2. Initializes the MemoryRouter with config
    3. Creates the FastAPI app using the factory function
    4. Starts the uvicorn server

    All configuration is passed explicitly to the factory function,
    eliminating the need for global variables.
    """
    # pydevd_pycharm.settrace('localhost', port=4747, stdout_to_server=True, stderr_to_server=True, suspend=True)
    parser = argparse.ArgumentParser(description="LiteLLM Proxy with Memory Routing")
    parser.add_argument("--config", default="config/config.yaml", help="Path to config.yaml")
    parser.add_argument("--port", type=int, default=8764, help="Port to listen on")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument(
        "--litellm-url",
        default="http://localhost:4000",
        help="LiteLLM proxy URL",
    )

    args = parser.parse_args()

    # Initialize MemoryRouter with config file
    try:
        config_parsed = schema.load_config_with_env_resolution(args.config)
        memory_router = MemoryRouter(config_parsed)
        logger.info(f"MemoryRouter initialized from config: {args.config}")
    except Exception as e:
        logger.error(f"Failed to initialize MemoryRouter: {e}")
        logger.warning("Continuing without memory routing")
        memory_router = None

    # Create FastAPI app using factory function
    # This eliminates global state and makes the app testable
    app = create_app(
        memory_router=memory_router,
        litellm_base_url=args.litellm_url,
        litellm_auth_token=f"Bearer {os.environ.get('LITELLM_VIRTUAL_KEY', 'sk-1234')}",
    )

    logger.info(f"Starting proxy on {args.host}:{args.port}")
    logger.info(f"Forwarding to LiteLLM at {args.litellm_url}")
    logger.info(f"Config: {args.config}")
    # 
    # import pydevd_pycharm
    # 
    # pydevd_pycharm.settrace(
    #     "localhost", port=4747, stdout_to_server=True, stderr_to_server=True
    # )

    # Run server with the created app instance
    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        log_config=None,  # Use our custom logging
    )


if __name__ == "__main__":
    main()
