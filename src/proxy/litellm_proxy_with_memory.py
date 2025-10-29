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
import json
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Annotated, Dict, Optional
import pydevd_pycharm

# if os.getenv('ENABLE_DEBUG'):
#       import debugpy
#       debugpy.listen(("localhost", 5678))
#       print("⏳ Waiting for debugger to attach...")
#       debugpy.wait_for_client()
#       print("✅ Debugger attached!")

import httpx
import uvicorn
from fastapi import Depends, FastAPI, Request, Response
from fastapi.responses import StreamingResponse
from litellm.types.llms.anthropic import AnthropicThinkingParam

# Handle both package and direct execution imports
from proxy.memory_router import MemoryRouter

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(filename)s:%(lineno)d:%(funcName)s() | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


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


async def proxy_request(
    method: str,
    path: str,
    headers: Dict[str, str],
    body: Optional[bytes],
    litellm_base_url: str,
) -> tuple[int, Dict[str, str], bytes]:
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

            return response.status_code, dict(response.headers), response.content
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
    return getattr(
        request.app.state, "litellm_base_url", "http://localhost:4000"
    )


def is_valid_date(date_string: str) -> bool:
    try:
        datetime.strptime(date_string, '%Y%m%d')
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

class MyFastMemoryLane:
    def __init__(self, app: FastAPI, memory_router: MemoryRouter, litellm_auth_token: str, litellm_base_url: str) -> None:
        self.app = app
        self.memory_router = memory_router
        self.litellm_auth_token = litellm_auth_token
        self.litellm_base_url = litellm_base_url

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

    @asynccontextmanager
    async def lifespan(app: FastAPI):
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
            logger.info(
                f"Memory Router initialized with {len(memory_router.header_patterns)} patterns"
            )
        else:
            logger.warning("Memory Router not provided - memory routing disabled")

        logger.info(f"Forwarding requests to LiteLLM at {litellm_base_url}")

        yield  # Application runs here

        # Shutdown: Cleanup if needed
        logger.info("Application shutting down...")

    # Create FastAPI app with lifespan
    app = FastAPI(
        title="LiteLLM Proxy with Memory Routing",
        lifespan=lifespan,
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
        """
        if memory_router:
            info = memory_router.get_routing_info(request.headers)
            return info
        return {"error": "Memory router not initialized"}

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
            uodate_auth: Dependency to update LiteLLM auth token
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
        headers["Authorization"] = request.app.state.litellm_auth_token
        
        body = await request.body()

        logger.info(f"{request_id} REQUEST: {method} {full_path}")
        logger.info(f"{request_id} HEADERS: {headers}")

        # Check if this is a Supermemory-enabled model request
        # For chat completions, check the model in body
        if "/chat/completions" in full_path or "/v1/messages" in full_path:
            try:
                if body:
                    request_data = json.loads(body)
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
                    
                    #? TODO: what's this for?
                    if len(model_name) >= 8:
                        if is_valid_date(model_name[-8:]):
                            model_name = model_name[:-8].rstrip("-")

                    # Check if model uses Supermemory (only if router is available)
                    if (
                        memory_router
                        and memory_router.should_use_supermemory(model_name)
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
                        logger.info(
                            f"{request_id} INJECTED: x-sm-user-id={user_id}"
                        )
    
            except json.JSONDecodeError:
                logger.warning(f"{request_id} Failed to parse request body")
            except Exception as e:
                logger.error(f"{request_id} Error in memory routing: {e}")

            # Forward request to LiteLLM
            try:
                status_code, response_headers, response_body = await proxy_request(
                    method=method,
                    path=full_path,
                    headers=headers,
                    body=body if body else None,
                    litellm_base_url=litellm_base_url,
                )
    
                # Check if streaming response
                content_type = response_headers.get("content-type", "")
                if (
                    "text/event-stream" in content_type
                    or "application/x-ndjson" in content_type
                ):
                    logger.info(f"{request_id} Handling as streaming response")
    
                    async def stream_response():
                        async with httpx.AsyncClient(timeout=600.0) as client:
                            async with client.stream(
                                method=method,
                                url=f"{litellm_base_url}{full_path}",
                                headers=headers,
                                content=body,
                            ) as response:
                                async for chunk in response.aiter_bytes():
                                    yield chunk
                        logger.info(f"{request_id} Stream completed successfully")
    
                    return StreamingResponse(
                        stream_response(),
                        status_code=status_code,
                        headers=dict(response_headers),
                        media_type=content_type,
                    )
                logger.info(f"{request_id} Handling as non-streaming response")
                return Response(
                    content=response_body,
                    status_code=status_code,
                    headers=dict(response_headers),
                )

            except Exception as e:
                logger.error(f"{request_id} Proxy error: {e}")
                return Response(
                    content=str(e).encode(),
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
    parser = argparse.ArgumentParser(
        description="LiteLLM Proxy with Memory Routing"
    )
    parser.add_argument(
        "--config", default="config.yaml", help="Path to config.yaml"
    )
    parser.add_argument(
        "--port", type=int, default=8764, help="Port to listen on"
    )
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind to")
    parser.add_argument(
        "--litellm-url",
        default="http://localhost:4000",
        help="LiteLLM proxy URL",
    )

    args = parser.parse_args()

    # Initialize MemoryRouter with config file
    try:
        memory_router = MemoryRouter(args.config)
        logger.info(f"MemoryRouter initialized from config: {args.config}")
    except Exception as e:
        logger.error(f"Failed to initialize MemoryRouter: {e}")
        logger.warning("Continuing without memory routing")
        memory_router = None

    # Create FastAPI app using factory function
    # This eliminates global state and makes the app testable
    app = create_app(
        memory_router=memory_router, litellm_base_url=args.litellm_url, litellm_auth_token=f"Bearer {os.environ.get('LITELLM_VIRTUAL_KEY', 'sk-E-aQ2xeQ0aVGgsV12Zs7lg')}",
    )

    logger.info(f"Starting proxy on {args.host}:{args.port}")
    logger.info(f"Forwarding to LiteLLM at {args.litellm_url}")
    logger.info(f"Config: {args.config}")

    # Run server with the created app instance
    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        log_config=None,  # Use our custom logging
    )


if __name__ == "__main__":
    main()
