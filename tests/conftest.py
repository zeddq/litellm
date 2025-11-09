"""
Shared pytest fixtures for all test modules.

This module provides centralized fixtures for mocking httpx clients
and creating test configurations.
"""

from typing import Dict
from unittest.mock import AsyncMock, Mock, patch

import pytest


@pytest.fixture
def mock_httpx_client():
    """
    Fixture providing properly configured mock httpx.AsyncClient.

    This fixture creates a mock that works with the async context manager
    pattern used by httpx.AsyncClient and ProxySessionManager.

    The fixture automatically patches ProxySessionManager.get_session to return
    this mock client, so tests work with both direct httpx.AsyncClient usage
    and ProxySessionManager usage.

    Usage in tests:
        def test_something(mock_httpx_client):
            # mock_httpx_client is automatically used by ProxySessionManager
            # Your test code here
            pass

    Returns:
        Mock httpx.AsyncClient instance configured for async context manager usage
    """
    # Create mock instance
    mock_instance = Mock()

    # Configure context manager methods
    mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
    mock_instance.__aexit__ = AsyncMock(return_value=None)

    # Configure aclose for ProxySessionManager compatibility
    mock_instance.aclose = AsyncMock()

    # Configure cookies attribute (empty by default)
    mock_instance.cookies = {}

    # Configure default successful response
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.headers = {"content-type": "application/json"}
    mock_response.content = b'{"choices": [{"message": {"content": "Test response"}}]}'
    mock_response.cookies = {}

    # Configure request method
    mock_instance.request = AsyncMock(return_value=mock_response)

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
