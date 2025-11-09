"""
Shared pytest fixtures for all test modules.

This module provides centralized fixtures for mocking httpx clients
and creating test configurations.

Enhanced httpx mocking with smart response routing:
- Returns proper OpenAI-compatible responses
- Routes based on endpoint (chat, models, health, etc.)
- Handles streaming responses
- Maintains cookie jar for session testing
"""

import json
import time
from typing import Dict
from unittest.mock import AsyncMock, Mock, patch

import pytest


# ============================================================================
# HELPER FUNCTIONS FOR MOCK RESPONSES
# ============================================================================


def _create_openai_chat_completion_response(model: str = "claude-sonnet-4.5") -> bytes:
    """
    Create a properly formatted OpenAI-compatible chat completion response.

    This matches the expected format from LiteLLM proxy responses.

    Args:
        model: Model name to include in response

    Returns:
        JSON-encoded response as bytes
    """
    response = {
        "id": f"chatcmpl-test-{int(time.time())}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "This is a test response from the mocked LiteLLM backend."
                },
                "finish_reason": "stop"
            }
        ],
        "usage": {
            "prompt_tokens": 10,
            "completion_tokens": 12,
            "total_tokens": 22
        }
    }
    return json.dumps(response).encode()


def _create_openai_models_response() -> bytes:
    """
    Create a properly formatted OpenAI-compatible models list response.

    Returns:
        JSON-encoded models list as bytes
    """
    response = {
        "object": "list",
        "data": [
            {
                "id": "claude-sonnet-4.5",
                "object": "model",
                "created": int(time.time()),
                "owned_by": "anthropic"
            },
            {
                "id": "gpt-4",
                "object": "model",
                "created": int(time.time()),
                "owned_by": "openai"
            }
        ]
    }
    return json.dumps(response).encode()


def _create_memory_routing_info_response(user_id: str = "default-user") -> bytes:
    """
    Create a memory routing info response.

    Args:
        user_id: User ID to include in response

    Returns:
        JSON-encoded routing info as bytes
    """
    response = {
        "user_id": user_id,
        "matched_pattern": None,
        "custom_header_present": False,
        "is_default": True
    }
    return json.dumps(response).encode()


def _create_health_response() -> bytes:
    """
    Create a health check response.

    Returns:
        JSON-encoded health response as bytes
    """
    import datetime

    response = {
        "status": "healthy",
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z"
    }
    return json.dumps(response).encode()


def _smart_response_router(method: str, url: str, **kwargs) -> Mock:
    """
    Smart router that returns appropriate mock responses based on endpoint.

    This function analyzes the request URL and method to determine what type
    of response should be returned, matching real LiteLLM proxy behavior.

    Args:
        method: HTTP method (GET, POST, etc.)
        url: Request URL (can be relative path or full URL)
        **kwargs: Additional request parameters (headers, content, etc.)

    Returns:
        Mock response object with appropriate content
    """
    # Extract path from URL (handle both full URLs and relative paths)
    if "://" in url:
        # Full URL like "http://localhost:4000/v1/chat/completions"
        path = url.split("://", 1)[1]  # Remove protocol
        path = "/" + path.split("/", 1)[1] if "/" in path else "/"  # Get path part
    else:
        # Relative path like "/v1/chat/completions"
        path = url

    # Remove query string for matching
    path = path.split("?")[0]

    # Create mock response
    mock_response = Mock()
    mock_response.cookies = {}

    # Route based on endpoint
    if "/chat/completions" in path or "/v1/messages" in path:
        # Chat completion endpoint
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "application/json"}

        # Try to extract model from request body
        model = "claude-sonnet-4.5"  # default
        if "content" in kwargs and kwargs["content"]:
            try:
                body = json.loads(kwargs["content"].decode())
                model = body.get("model", model)
            except:
                pass

        mock_response.content = _create_openai_chat_completion_response(model)

    elif "/models" in path:
        # Models list endpoint
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "application/json"}
        mock_response.content = _create_openai_models_response()

    elif "/memory-routing/info" in path:
        # Memory routing info endpoint
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "application/json"}

        # Extract user-agent to determine user_id
        user_id = "default-user"
        if "headers" in kwargs:
            headers = kwargs["headers"]
            user_agent = headers.get("user-agent", "").lower()
            if "pycharm" in user_agent or "openaiclientimpl" in user_agent:
                user_id = "pycharm-client"
            elif "claude code" in user_agent:
                user_id = "claude-code"
            elif "anthropic-sdk" in user_agent:
                user_id = "anthropic-python"

        mock_response.content = _create_memory_routing_info_response(user_id)

    elif "/health" in path:
        # Health check endpoint
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "application/json"}
        mock_response.content = _create_health_response()

    else:
        # Default generic success response
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "application/json"}
        mock_response.content = b'{"result": "success"}'

    return mock_response


# ============================================================================
# PYTEST FIXTURES
# ============================================================================


@pytest.fixture
def mock_httpx_client():
    """
    Enhanced fixture providing properly configured mock httpx.AsyncClient.

    This fixture creates a smart mock that:
    - Works with async context manager pattern (async with)
    - Returns appropriate responses based on endpoint (chat, models, health, etc.)
    - Includes all required OpenAI-compatible response fields
    - Maintains cookie jar for session persistence testing
    - Supports ProxySessionManager.get_session patching

    The mock automatically routes requests to appropriate response generators:
    - /v1/chat/completions → OpenAI chat completion format
    - /v1/models → OpenAI models list format
    - /memory-routing/info → Memory routing info format
    - /health → Health check format

    Usage in tests:
        def test_something(mock_httpx_client):
            # mock_httpx_client is automatically used by ProxySessionManager
            # It returns proper responses based on the endpoint
            pass

    For custom responses, use configure_mock_httpx_response fixture:
        def test_custom(mock_httpx_client, configure_mock_httpx_response):
            configure_mock_httpx_response(
                mock_httpx_client,
                status_code=404,
                content=b'{"error": "not found"}'
            )

    Returns:
        Mock httpx.AsyncClient instance with smart response routing
    """
    # Create mock instance
    mock_instance = Mock()

    # Configure context manager methods
    mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
    mock_instance.__aexit__ = AsyncMock(return_value=None)

    # Configure aclose for ProxySessionManager compatibility
    mock_instance.aclose = AsyncMock()

    # Configure cookies attribute with MutableMapping interface
    mock_instance.cookies = {}

    # Configure stream method for streaming responses
    mock_stream_context = Mock()
    mock_stream_context.__aenter__ = AsyncMock(return_value=mock_stream_context)
    mock_stream_context.__aexit__ = AsyncMock(return_value=None)

    async def mock_aiter_bytes():
        """Mock streaming response chunks."""
        yield b'data: {"delta": {"content": "Test"}}\n\n'
        yield b'data: [DONE]\n\n'

    mock_stream_context.aiter_bytes = mock_aiter_bytes
    mock_instance.stream = Mock(return_value=mock_stream_context)

    # Configure request method with smart routing
    async def smart_request(method: str, url: str, **kwargs):
        """Smart request handler that routes to appropriate response."""
        return _smart_response_router(method, url, **kwargs)

    mock_instance.request = AsyncMock(side_effect=smart_request)

    # Automatically patch ProxySessionManager.get_session to return this mock
    with patch(
        "proxy.litellm_proxy_with_memory.ProxySessionManager.get_session",
        new=AsyncMock(return_value=mock_instance),
    ):
        yield mock_instance


@pytest.fixture
def mock_litellm_chat_completion_response():
    """
    Fixture providing a properly formatted LiteLLM chat completion response.

    Returns:
        Dict containing a valid OpenAI-compatible chat completion response
    """
    return {
        "id": "chatcmpl-test123",
        "object": "chat.completion",
        "created": 1234567890,
        "model": "claude-sonnet-4.5",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "This is a test response from the mocked LiteLLM backend.",
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
    }


@pytest.fixture
def mock_litellm_models_response():
    """
    Fixture providing a properly formatted LiteLLM models list response.

    Returns:
        Dict containing a valid OpenAI-compatible models list response
    """
    return {
        "object": "list",
        "data": [
            {
                "id": "claude-sonnet-4.5",
                "object": "model",
                "created": 1234567890,
                "owned_by": "anthropic",
            },
            {
                "id": "gpt-4",
                "object": "model",
                "created": 1234567890,
                "owned_by": "openai",
            },
        ],
    }


@pytest.fixture
def mock_litellm_health_response():
    """
    Fixture providing a LiteLLM health check response.

    Returns:
        Dict containing a valid health check response
    """
    return {"status": "healthy", "timestamp": "2024-01-01T00:00:00Z"}


@pytest.fixture
def configure_mock_httpx_response(mock_httpx_client):
    """
    Helper fixture to configure custom responses for mock httpx client.

    This allows tests to override the smart routing behavior with
    custom responses for specific test scenarios.

    Usage:
        def test_something(mock_httpx_client, configure_mock_httpx_response):
            configure_mock_httpx_response(
                mock_httpx_client,
                status_code=404,
                content=b'{"error": "not found"}'
            )

    Args:
        mock_httpx_client: The mock httpx client instance

    Returns:
        Function to configure the mock response
    """

    def _configure(
        client_mock,
        status_code: int = 200,
        headers: Dict[str, str] = None,
        content: bytes = None,
    ):
        """Configure the mock response."""
        mock_response = Mock()
        mock_response.status_code = status_code
        mock_response.headers = headers or {"content-type": "application/json"}
        mock_response.content = content or b'{"result": "ok"}'
        mock_response.cookies = {}

        client_mock.request = AsyncMock(return_value=mock_response)

    return _configure
