"""
Shared pytest fixtures for all test modules.

This module provides centralized testing infrastructure for the LiteLLM Memory Proxy,
including mock HTTP clients, response generators, and configuration fixtures.

Overview:
    The conftest module solves a critical testing challenge: creating realistic mock
    responses that match actual LiteLLM proxy behavior without requiring running
    external services. It provides:
    
    - Smart HTTP mocking with endpoint-aware response routing
    - OpenAI-compatible response generators for various endpoints
    - Flexible fixture system for both simple and complex test scenarios
    - Automatic session management and cookie handling

Key Features:
    1. Smart Response Routing: Automatically returns appropriate responses based on
       the requested endpoint (chat completions, models, health, etc.)
    
    2. OpenAI API Compatibility: All responses match the exact format expected by
       OpenAI and LiteLLM clients, including proper field names and data types
    
    3. Flexible Mocking: Supports both automatic smart routing and custom response
       configuration for specific test scenarios
    
    4. Streaming Support: Handles both regular and streaming API responses
    
    5. Session Management: Maintains cookie jars and session state for testing
       multi-request scenarios

Architecture:
    Helper Functions (_create_* and _smart_response_router)
        ↓
    Core Fixture (mock_httpx_client)
        ↓
    Response Fixtures (mock_litellm_*_response)
        ↓
    Configuration Fixture (configure_mock_httpx_response)

Usage Patterns:
    # Basic test with automatic routing
    def test_chat(mock_httpx_client):
        # Automatically returns proper chat completion responses
        pass
    
    # Test with custom response
    def test_error(mock_httpx_client, configure_mock_httpx_response):
        configure_mock_httpx_response(
            mock_httpx_client,
            status_code=500,
            content=b'{"error": "server error"}'
        )
    
    # Test with pre-built response fixture
    def test_models(mock_httpx_client, mock_litellm_models_response):
        # Use the fixture data for assertions
        assert "data" in mock_litellm_models_response

Important Notes:
    - All fixtures use session scope where appropriate to improve test performance
    - The mock_httpx_client fixture automatically patches ProxySessionManager
    - Response generators use realistic timestamps and IDs for better test fidelity
    - Fixtures are designed to be composable and reusable across test modules
"""

import json
import time
from typing import Dict
from unittest.mock import AsyncMock, Mock, patch

import pytest

# Import interceptor fixtures to make them available to all tests
from ..fixtures import (
    temp_port_registry,
    cleanup_port_registry,
    interceptor_server,
)

__all__ = ['temp_port_registry', 'cleanup_port_registry', 'interceptor_server']


# ============================================================================
# HELPER FUNCTIONS FOR MOCK RESPONSES
# ============================================================================
#
# These helper functions generate realistic mock responses that match the exact
# format returned by LiteLLM proxy and OpenAI API. They are used internally by
# the smart response router and can also be imported for use in specific tests.
#
# Design Principles:
#   - Responses include all required fields per OpenAI API specification
#   - Use realistic timestamps and IDs for better test fidelity
#   - Return bytes (not strings) to match actual HTTP response behavior
#   - Support customization through function parameters
# ============================================================================


def _create_openai_chat_completion_response(model: str = "claude-sonnet-4.5") -> bytes:
    """
    Create a properly formatted OpenAI-compatible chat completion response.

    This function generates a complete chat completion response that matches both
    OpenAI's API specification and LiteLLM's proxy format. The response includes
    all required fields: id, object type, creation timestamp, model, choices array,
    and token usage statistics.

    The generated response is suitable for testing:
    - Chat completion endpoint handlers
    - Response parsing and validation logic
    - Token usage tracking
    - Model-specific behavior

    Args:
        model: The model identifier to include in the response. Defaults to
               "claude-sonnet-4.5" but can be any valid model name. This affects
               how clients interpret and process the response.

    Returns:
        A JSON-encoded byte string containing the complete chat completion response.
        The response structure matches OpenAI's chat.completion format with:
        - Unique chat completion ID (chatcmpl-test-{timestamp})
        - Current Unix timestamp
        - Single choice with assistant message
        - Token usage breakdown (prompt, completion, total)

    Example Response Structure:
        {
            "id": "chatcmpl-test-1234567890",
            "object": "chat.completion",
            "created": 1234567890,
            "model": "claude-sonnet-4.5",
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "This is a test response..."
                },
                "finish_reason": "stop"
            }],
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 12,
                "total_tokens": 22
            }
        }

    Note:
        The function uses the current timestamp to generate unique IDs, ensuring
        each call produces a distinct response ID for better test isolation.
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

    This function generates a models list response matching the format returned by
    the OpenAI API /v1/models endpoint. The response includes multiple model entries
    with complete metadata for testing model discovery and selection logic.

    The generated response is suitable for testing:
    - Model listing endpoints
    - Model availability checks
    - Client model discovery logic
    - Multi-provider model aggregation

    Returns:
        A JSON-encoded byte string containing the models list response with:
        - "list" object type identifier
        - Array of model objects with id, object, created, and owned_by fields
        - Multiple models representing different providers (Anthropic, OpenAI)

    Example Response Structure:
        {
            "object": "list",
            "data": [
                {
                    "id": "claude-sonnet-4.5",
                    "object": "model",
                    "created": 1234567890,
                    "owned_by": "anthropic"
                },
                {
                    "id": "gpt-4",
                    "object": "model",
                    "created": 1234567890,
                    "owned_by": "openai"
                }
            ]
        }

    Note:
        The models included in the response (Claude Sonnet 4.5 and GPT-4) represent
        the most commonly used models in the LiteLLM Memory Proxy test suite.
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
    Create a memory routing info response for the /memory-routing/info endpoint.

    This function generates responses for the Memory Proxy's diagnostic endpoint
    that shows how requests are being routed based on client detection patterns.
    The response includes information about user ID assignment, pattern matching,
    and routing configuration.

    The generated response is suitable for testing:
    - Client detection and identification logic
    - User ID assignment from headers
    - Pattern matching behavior
    - Default routing fallback behavior

    Args:
        user_id: The user identifier to include in the response. This represents
                 the detected or assigned user ID for the request. Common values:
                 - "default-user": Default fallback when no pattern matches
                 - "pycharm-client": PyCharm AI Assistant requests
                 - "claude-code": Claude Code CLI requests
                 - "anthropic-python": Anthropic Python SDK requests

    Returns:
        A JSON-encoded byte string containing the routing info response with:
        - user_id: The assigned user identifier
        - matched_pattern: Pattern that matched (null for default routing)
        - custom_header_present: Whether x-memory-user-id header was provided
        - is_default: Whether default routing was used

    Example Response Structure:
        {
            "user_id": "default-user",
            "matched_pattern": null,
            "custom_header_present": false,
            "is_default": true
        }

    Note:
        This endpoint is primarily used for debugging and verifying that client
        detection is working correctly. It should not affect actual proxy behavior.
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
    Create a health check response for the /health endpoint.

    This function generates a simple health status response used by monitoring
    systems and load balancers to verify that the proxy service is operational.
    The response includes a status indicator and timestamp for tracking.

    The generated response is suitable for testing:
    - Health check endpoint handlers
    - Service availability monitoring
    - Load balancer health probes
    - Uptime verification

    Returns:
        A JSON-encoded byte string containing the health response with:
        - status: Health status indicator (always "healthy" for mock)
        - timestamp: ISO 8601 formatted UTC timestamp with Z suffix

    Example Response Structure:
        {
            "status": "healthy",
            "timestamp": "2024-01-01T00:00:00.000000Z"
        }

    Note:
        The timestamp uses UTC and includes microseconds for precision. In
        production, this timestamp represents when the health check was performed.
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

    This is the core intelligence of the mock HTTP client system. It analyzes
    incoming requests and automatically routes them to the appropriate response
    generator, mimicking how a real LiteLLM proxy would behave. This eliminates
    the need for test-specific mocking configuration in most cases.

    The router uses pattern matching on URL paths to determine response type:
    - /chat/completions or /v1/messages → Chat completion responses
    - /models → Model list responses
    - /memory-routing/info → Memory routing diagnostic responses
    - /health → Health check responses
    - Other paths → Generic success responses

    For chat completion requests, the router intelligently extracts the model
    name from the request body and includes it in the response for more realistic
    testing behavior.

    Request Processing Flow:
        1. Extract path from URL (handles both full and relative URLs)
        2. Remove query string for clean pattern matching
        3. Match path against known endpoint patterns
        4. Generate appropriate response using helper functions
        5. Return Mock object with proper status, headers, and content

    Args:
        method: HTTP method verb (GET, POST, PUT, DELETE, etc.). Currently not
                used for routing decisions but included for future extensibility
                and compatibility with httpx.request signature.

        url: Request URL that can be either:
             - Full URL: "http://localhost:4000/v1/chat/completions"
             - Relative path: "/v1/chat/completions"
             Both formats are supported and normalized for matching.

        **kwargs: Additional request parameters passed through from httpx.request:
                  - headers (Dict[str, str]): Request headers for user-agent detection
                  - content (bytes): Request body for model extraction
                  - params (Dict): URL query parameters
                  - cookies (Dict): Request cookies
                  Additional kwargs are preserved but not currently used.

    Returns:
        A Mock object configured as an HTTP response with:
        - status_code (int): HTTP status code (200 for success)
        - headers (Dict[str, str]): Response headers including content-type
        - content (bytes): Response body as JSON-encoded bytes
        - cookies (Dict): Empty cookie dictionary for compatibility

    Example Usage:
        # Automatically routed to chat completion
        response = _smart_response_router(
            "POST",
            "/v1/chat/completions",
            headers={"content-type": "application/json"},
            content=b'{"model": "gpt-4", "messages": [...]}'
        )
        assert response.status_code == 200

        # Automatically routed to models list
        response = _smart_response_router("GET", "/v1/models")
        assert "data" in json.loads(response.content)

    Implementation Notes:
        - URL parsing is robust and handles both full URLs and relative paths
        - Pattern matching uses substring matching (in operator) for flexibility
        - Query strings are stripped before matching to avoid false negatives
        - Default response ensures tests never fail due to unmapped endpoints
        - Cookie dictionary is always included for session testing compatibility

    Related Functions:
        - _create_openai_chat_completion_response(): Chat response generator
        - _create_openai_models_response(): Models list generator
        - _create_memory_routing_info_response(): Routing info generator
        - _create_health_response(): Health check generator
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
        # Chat completion endpoint - validate request first
        mock_response.headers = {"content-type": "application/json"}

        # Try to extract and validate request body
        if "content" in kwargs and kwargs["content"]:
            try:
                body = json.loads(kwargs["content"].decode())
                
                # Validate required fields
                if "model" not in body:
                    mock_response.status_code = 400
                    mock_response.content = json.dumps({
                        "error": {
                            "type": "invalid_request_error",
                            "message": "Missing required parameter: model"
                        }
                    }).encode()
                    return mock_response
                    
                if "messages" not in body:
                    mock_response.status_code = 400
                    mock_response.content = json.dumps({
                        "error": {
                            "type": "invalid_request_error",
                            "message": "Missing required parameter: messages"
                        }
                    }).encode()
                    return mock_response
                
                # Validate model exists (mock valid models list)
                model = body.get("model", "claude-sonnet-4.5")
                valid_models = ["claude-sonnet-4.5", "gpt-4", "gpt-5-pro"]
                if model not in valid_models:
                    mock_response.status_code = 404
                    mock_response.content = json.dumps({
                        "error": {
                            "type": "not_found_error",
                            "message": f"Model '{model}' not found"
                        }
                    }).encode()
                    return mock_response
                
                # Valid request
                mock_response.status_code = 200
                mock_response.content = _create_openai_chat_completion_response(model)
            except json.JSONDecodeError:
                mock_response.status_code = 400
                mock_response.content = json.dumps({
                    "error": {
                        "type": "invalid_request_error",
                        "message": "Invalid JSON in request body"
                    }
                }).encode()
                return mock_response
        else:
            # No body provided
            mock_response.status_code = 400
            mock_response.content = json.dumps({
                "error": {
                    "type": "invalid_request_error",
                    "message": "Request body is required"
                }
            }).encode()

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
#
# This section defines pytest fixtures that provide pre-configured test
# infrastructure. Fixtures are automatically discovered by pytest and can be
# used by simply adding them as function parameters to test functions.
#
# Fixture Categories:
#   1. Core Mock Client (mock_httpx_client)
#      - Primary fixture for HTTP client mocking
#      - Automatically patches ProxySessionManager
#      - Provides smart response routing
#
#   2. Response Data Fixtures (mock_litellm_*_response)
#      - Pre-built response dictionaries
#      - Useful for assertion validation
#      - Can be used as reference data
#
#   3. Configuration Fixtures (configure_mock_httpx_response)
#      - Helper for custom response configuration
#      - Overrides smart routing when needed
#      - Useful for error testing scenarios
#
# Usage Patterns:
#   # Automatic smart routing
#   def test_chat(mock_httpx_client):
#       # Client automatically returns proper responses
#       pass
#
#   # Custom response for error testing
#   def test_error(mock_httpx_client, configure_mock_httpx_response):
#       configure_mock_httpx_response(mock_httpx_client, status_code=500)
#
#   # Using response fixtures for validation
#   def test_format(mock_litellm_chat_completion_response):
#       assert "choices" in mock_litellm_chat_completion_response
#
# Fixture Scopes:
#   - Function scope: Default, created fresh for each test
#   - Session scope: Shared across all tests (not currently used)
#
# Important: mock_httpx_client automatically patches ProxySessionManager.get_session
# so you don't need to manually patch it in your tests.
# ============================================================================


@pytest.fixture
def mock_httpx_client():
    """
    Enhanced fixture providing a fully-configured mock httpx.AsyncClient.

    This is the primary fixture for testing the Memory Proxy without requiring
    actual HTTP connections. It provides a sophisticated mock that behaves like
    a real httpx.AsyncClient but returns pre-configured responses based on the
    requested endpoint.

    Key Features:
        1. Async Context Manager Support: Works with 'async with' pattern
        2. Smart Response Routing: Automatically returns appropriate responses
        3. Cookie Management: Maintains session cookies for multi-request tests
        4. Streaming Support: Handles streaming responses for SSE endpoints
        5. Automatic Patching: Patches ProxySessionManager.get_session
        6. OpenAI Compatibility: All responses match OpenAI API format

    Routing Behavior:
        The mock uses intelligent path-based routing via _smart_response_router:
        
        Endpoint Pattern              → Response Type
        ─────────────────────────────────────────────────────────
        /chat/completions             → Chat completion (OpenAI format)
        /v1/messages                  → Chat completion (Anthropic format)
        /v1/models                    → Model list
        /memory-routing/info          → Routing diagnostic info
        /health                       → Health check
        Other paths                   → Generic success response

    Mock Client Capabilities:
        - request(): Async method with smart routing
        - stream(): Returns async context manager for streaming
        - aclose(): Async cleanup method
        - cookies: MutableMapping interface for session state
        - __aenter__/__aexit__: Context manager protocol

    Automatic Patching:
        This fixture automatically patches:
            proxy.litellm_proxy_with_memory.ProxySessionManager.get_session
        
        This means tests using this fixture don't need to manually patch the
        session manager. The mock is automatically injected wherever the proxy
        code calls ProxySessionManager.get_session().

    Basic Usage:
        def test_chat_completion(mock_httpx_client):
            # The mock is already active, just test your code
            result = await some_function_that_uses_httpx()
            assert result["status"] == "success"

    Custom Response Override:
        def test_error_handling(mock_httpx_client, configure_mock_httpx_response):
            # Override default routing for specific test scenarios
            configure_mock_httpx_response(
                mock_httpx_client,
                status_code=500,
                content=b'{"error": "Internal server error"}'
            )
            # Now all requests return this error response
            result = await some_function_that_uses_httpx()
            assert "error" in result

    Streaming Response Testing:
        async def test_streaming(mock_httpx_client):
            # The mock supports streaming via the stream() method
            async with mock_httpx_client.stream("POST", "/stream") as response:
                async for chunk in response.aiter_bytes():
                    # Process streaming chunks
                    assert b"data:" in chunk

    Session/Cookie Testing:
        def test_cookies(mock_httpx_client):
            # The mock maintains a cookie jar
            response1 = await mock_httpx_client.request("GET", "/set-cookie")
            # Cookies persist across requests
            response2 = await mock_httpx_client.request("GET", "/use-cookie")
            assert mock_httpx_client.cookies  # Cookie jar is accessible

    Common Pitfalls:
        ❌ Don't manually patch ProxySessionManager when using this fixture
        ✅ The fixture already patches it for you
        
        ❌ Don't assume specific response content without checking routing
        ✅ Use configure_mock_httpx_response for custom responses
        
        ❌ Don't forget to await async operations
        ✅ All httpx operations are async and must be awaited

    Related Fixtures:
        - configure_mock_httpx_response: For custom response configuration
        - mock_litellm_chat_completion_response: For response format reference
        - mock_litellm_models_response: For models list format reference

    Implementation Details:
        The fixture uses a context manager to patch ProxySessionManager during
        the test execution. When the test completes (or fails), the patch is
        automatically cleaned up, ensuring test isolation.

    Returns:
        Mock: A configured unittest.mock.Mock instance that implements the
              httpx.AsyncClient interface with smart response routing.

    Yields:
        The fixture yields the mock client within an active patch context,
        ensuring proper setup and teardown.

    Note:
        This fixture uses function scope, meaning a fresh mock is created for
        each test. This ensures complete test isolation and prevents state
        leakage between tests.
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

    This fixture returns a pre-built dictionary representing a complete chat
    completion response. It's primarily used for:
    - Validating response format in tests
    - Providing reference data for assertions
    - Testing response parsing logic
    - Verifying field presence and structure

    Unlike mock_httpx_client which mocks the HTTP layer, this fixture provides
    the actual response data structure that would be returned by the API.

    Usage:
        def test_response_format(mock_litellm_chat_completion_response):
            response = mock_litellm_chat_completion_response
            
            # Validate required fields
            assert "id" in response
            assert "choices" in response
            assert response["object"] == "chat.completion"
            
            # Validate message structure
            assert response["choices"][0]["message"]["role"] == "assistant"
            
            # Validate usage tracking
            assert "usage" in response
            assert response["usage"]["total_tokens"] == 30

    Response Structure:
        - id: Unique chat completion identifier (chatcmpl-test123)
        - object: Response type ("chat.completion")
        - created: Unix timestamp
        - model: Model identifier (claude-sonnet-4.5)
        - choices: Array with single choice containing:
            - index: Choice index (0)
            - message: Message object with role and content
            - finish_reason: Completion reason ("stop")
        - usage: Token usage statistics with prompt/completion/total counts

    Returns:
        Dict: A complete chat completion response matching OpenAI API format.
              The dictionary is mutable and can be modified in tests if needed.

    Note:
        This fixture returns a fresh dictionary for each test, ensuring test
        isolation. Modifications to the dictionary don't affect other tests.

    Related Fixtures:
        - mock_httpx_client: For testing HTTP layer with automatic responses
        - configure_mock_httpx_response: For custom HTTP response configuration
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

    This fixture returns a pre-built dictionary representing a complete models
    list response. It's useful for testing:
    - Model discovery and listing logic
    - Model availability checks
    - Multi-provider aggregation
    - Client-side model filtering

    The fixture includes models from multiple providers (Anthropic and OpenAI)
    to reflect realistic multi-provider proxy configurations.

    Usage:
        def test_model_listing(mock_litellm_models_response):
            models = mock_litellm_models_response
            
            # Validate structure
            assert models["object"] == "list"
            assert "data" in models
            
            # Check model availability
            model_ids = [m["id"] for m in models["data"]]
            assert "claude-sonnet-4.5" in model_ids
            assert "gpt-4" in model_ids
            
            # Validate model metadata
            for model in models["data"]:
                assert "id" in model
                assert "owned_by" in model
                assert "created" in model

    Response Structure:
        - object: Response type ("list")
        - data: Array of model objects, each containing:
            - id: Model identifier (e.g., "claude-sonnet-4.5")
            - object: Object type ("model")
            - created: Unix timestamp
            - owned_by: Provider name (e.g., "anthropic", "openai")

    Models Included:
        1. claude-sonnet-4.5 (Anthropic): Latest Claude model
        2. gpt-4 (OpenAI): OpenAI's flagship model

    Returns:
        Dict: A complete models list response matching OpenAI API format.
              The dictionary is mutable and can be extended with additional
              models if needed for specific tests.

    Note:
        The models included represent the most commonly used models in the
        LiteLLM Memory Proxy configuration. Tests can add or modify entries
        as needed for specific scenarios.

    Related Fixtures:
        - mock_httpx_client: Automatically returns this format for /v1/models
        - configure_mock_httpx_response: For custom models list responses
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

    This fixture returns a pre-built dictionary representing a health check
    response. It's useful for testing:
    - Health endpoint handlers
    - Service availability monitoring logic
    - Load balancer integration
    - Uptime tracking

    Usage:
        def test_health_check(mock_litellm_health_response):
            health = mock_litellm_health_response
            
            # Validate service is healthy
            assert health["status"] == "healthy"
            
            # Check timestamp format
            assert "timestamp" in health
            assert health["timestamp"].endswith("Z")  # UTC format

    Response Structure:
        - status: Health status string ("healthy" for operational service)
        - timestamp: ISO 8601 formatted timestamp with Z suffix (UTC)

    Returns:
        Dict: A simple health check response. The dictionary is mutable and
              can be modified in tests to simulate unhealthy states if needed.

    Note:
        The fixture always returns "healthy" status. To test error scenarios,
        modify the dictionary or use configure_mock_httpx_response to return
        custom health responses.

    Related Fixtures:
        - mock_httpx_client: Automatically returns this format for /health
        - configure_mock_httpx_response: For custom health check responses
    """
    return {"status": "healthy", "timestamp": "2024-01-01T00:00:00Z"}


@pytest.fixture
def configure_mock_httpx_response(mock_httpx_client):
    """
    Helper fixture to configure custom responses for mock httpx client.

    This fixture provides a convenient way to override the default smart routing
    behavior when you need specific response characteristics for testing error
    conditions, edge cases, or specific API scenarios.

    When to Use This Fixture:
        ✅ Testing error handling (4xx, 5xx status codes)
        ✅ Testing malformed response handling
        ✅ Testing specific header configurations
        ✅ Testing timeout/connection error scenarios
        ✅ Testing custom content types

    When NOT to Use:
        ❌ For standard happy-path testing (use mock_httpx_client alone)
        ❌ For testing multiple different endpoints (smart routing handles this)

    Basic Usage:
        def test_not_found(mock_httpx_client, configure_mock_httpx_response):
            # Configure a 404 error response
            configure_mock_httpx_response(
                mock_httpx_client,
                status_code=404,
                content=b'{"error": "not found"}'
            )
            
            # Now all requests return this error
            result = await some_api_call()
            assert result["error"] == "not found"

    Custom Headers:
        def test_custom_headers(mock_httpx_client, configure_mock_httpx_response):
            # Configure custom headers
            configure_mock_httpx_response(
                mock_httpx_client,
                headers={"x-custom": "value", "content-type": "text/plain"},
                content=b"Plain text response"
            )

    Error Scenarios:
        # Server error
        configure_mock_httpx_response(
            mock_httpx_client,
            status_code=500,
            content=b'{"error": "internal server error"}'
        )
        
        # Unauthorized
        configure_mock_httpx_response(
            mock_httpx_client,
            status_code=401,
            content=b'{"error": "unauthorized"}'
        )
        
        # Rate limited
        configure_mock_httpx_response(
            mock_httpx_client,
            status_code=429,
            content=b'{"error": "rate limit exceeded"}'
        )

    Parameters:
        mock_httpx_client: The mock httpx client instance (automatically injected
                           by pytest fixture dependency)

    Returns:
        Callable: A configuration function with the following signature:
                  _configure(
                      client_mock: Mock,
                      status_code: int = 200,
                      headers: Dict[str, str] = None,
                      content: bytes = None
                  ) -> None

    Configuration Function Parameters:
        client_mock: The mock client to configure (pass mock_httpx_client)
        status_code: HTTP status code to return (default: 200)
        headers: Response headers dict (default: {"content-type": "application/json"})
        content: Response body as bytes (default: b'{"result": "ok"}')

    Important Notes:
        - Configuration replaces ALL request routing (not endpoint-specific)
        - Once configured, ALL subsequent requests return the same response
        - Call this fixture early in your test before making API calls
        - Cookie jar is always empty in custom responses (add if needed)
        - The mock response is synchronous (no streaming support in override mode)

    Implementation Details:
        The function creates a new Mock response object and replaces the
        request method's return value. This completely overrides the smart
        routing behavior provided by _smart_response_router.

    Troubleshooting:
        If your custom response isn't being used:
        1. Ensure you call configure_mock_httpx_response BEFORE making requests
        2. Check that you're passing mock_httpx_client as the first parameter
        3. Verify the response is configured before async operations execute

    Related Fixtures:
        - mock_httpx_client: The mock client that this fixture configures
        - Helper functions (_create_*_response): For building realistic content

    Example Test:
        async def test_api_error_handling(
            mock_httpx_client,
            configure_mock_httpx_response
        ):
            # Setup error response
            configure_mock_httpx_response(
                mock_httpx_client,
                status_code=503,
                content=b'{"error": "service unavailable", "retry_after": 60}'
            )
            
            # Test that error is handled correctly
            with pytest.raises(ServiceUnavailableError) as exc_info:
                await api_client.make_request()
            
            assert exc_info.value.retry_after == 60
    """

    def _configure(
        client_mock,
        status_code: int = 200,
        headers: Dict[str, str] = None,
        content: bytes = None,
    ):
        """
        Configure the mock response with custom status, headers, and content.
        
        This inner function is returned by the fixture and performs the actual
        configuration. It creates a new Mock response and replaces the client's
        request method with an AsyncMock that returns this response.
        
        Args:
            client_mock: The mock client instance to configure
            status_code: HTTP status code (default: 200)
            headers: Response headers (default: {"content-type": "application/json"})
            content: Response body bytes (default: b'{"result": "ok"}')
        """
        mock_response = Mock()
        mock_response.status_code = status_code
        mock_response.headers = headers or {"content-type": "application/json"}
        mock_response.content = content or b'{"result": "ok"}'
        mock_response.cookies = {}

        client_mock.request = AsyncMock(return_value=mock_response)

    return _configure
