"""
Integration Tests for SDK-Based Proxy

Tests the complete FastAPI application with all components integrated:
- Application startup/shutdown
- All API endpoints
- Memory routing integration
- Streaming and non-streaming
- Error scenarios

Test Strategy:
- Use FastAPI TestClient for HTTP testing
- Mock LiteLLM SDK responses
- Test all HTTP status codes
- Validate request/response formats

Usage:
    pytest tests/test_sdk_integration.py -v
    pytest tests/test_sdk_integration.py -v -k "test_chat_completions"
"""

import asyncio
import json
import os
import tempfile
from typing import Dict, Any
from unittest.mock import AsyncMock, Mock, patch, MagicMock

import httpx
import litellm
import pytest
from fastapi.testclient import TestClient

# Import SDK proxy application
from src.proxy.litellm_proxy_sdk import app
from src.proxy.session_manager import LiteLLMSessionManager

# Import test fixtures
from tests.fixtures import (
    TEST_CONFIG_YAML,
    create_test_config_file,
    get_chat_completion_request,
    get_request_headers,
    mock_completion_response,
    mock_streaming_chunks_sequence,
    MockLiteLLMResponse,
    create_mock_streaming_iterator,
    TEST_SCENARIOS,
    ERROR_TEST_CASES,
    assert_response_format,
    assert_error_format,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(scope="function")
def test_config_file(tmp_path_factory):
    """Create test configuration file."""
    tmp_path = tmp_path_factory.mktemp("config")
    return create_test_config_file(tmp_path, TEST_CONFIG_YAML)


@pytest.fixture(scope="function")
def mock_env_vars(monkeypatch):
    """Mock environment variables for testing."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-key")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-test-key")
    monkeypatch.setenv("SUPERMEMORY_API_KEY", "sm_test_key")


@pytest.fixture(scope="function")
async def test_client(test_config_file, mock_env_vars):
    """
    Create TestClient for SDK proxy application.

    Note: We use function scope to ensure clean state for each test.
    """
    # Set config path
    os.environ["LITELLM_CONFIG_PATH"] = test_config_file

    # Create TestClient (triggers lifespan startup)
    with TestClient(app) as client:
        yield client

    # Cleanup after test
    await LiteLLMSessionManager.close()


@pytest.fixture
def mock_litellm_completion():
    """Mock litellm.acompletion for non-streaming."""
    with patch("litellm.acompletion") as mock:
        # Return mock response
        mock_response = mock_completion_response()
        mock.return_value = MockLiteLLMResponse(mock_response)
        yield mock


@pytest.fixture
def mock_litellm_streaming():
    """Mock litellm.acompletion for streaming."""
    with patch("litellm.acompletion") as mock:
        # Return async iterator
        chunks = mock_streaming_chunks_sequence()
        mock.return_value = create_mock_streaming_iterator(chunks)
        yield mock


# =============================================================================
# Test Health Endpoint
# =============================================================================


class TestHealthEndpoint:
    """Tests for /health endpoint."""

    def test_health_check(self, test_client):
        """Test health check returns 200 OK."""
        response = test_client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "session" in data
        assert "models_configured" in data
        assert "litellm_sdk_injected" in data

    def test_health_check_session_info(self, test_client):
        """Test health check includes session information."""
        response = test_client.get("/health")

        assert response.status_code == 200
        data = response.json()

        session_info = data["session"]
        assert "initialized" in session_info
        assert session_info["initialized"] is True


# =============================================================================
# Test Memory Routing Info Endpoint
# =============================================================================


class TestMemoryRoutingInfoEndpoint:
    """Tests for /memory-routing/info endpoint."""

    def test_routing_info_default_user(self, test_client):
        """Test routing info with default user ID."""
        response = test_client.get(
            "/memory-routing/info",
            headers={"User-Agent": "test-client/1.0"},
        )

        assert response.status_code == 200
        data = response.json()
        assert "routing" in data
        assert data["routing"]["user_id"] == "default-dev"
        assert data["routing"]["is_default"] is True

    def test_routing_info_pycharm_client(self, test_client):
        """Test routing info detects PyCharm client."""
        response = test_client.get(
            "/memory-routing/info",
            headers={"User-Agent": "OpenAIClientImpl/Java 1.0"},
        )

        assert response.status_code == 200
        data = response.json()
        routing = data["routing"]
        assert routing["user_id"] == "pycharm-ai"
        assert routing["is_default"] is False
        assert routing["matched_pattern"] is not None

    def test_routing_info_custom_header(self, test_client):
        """Test routing info with custom user ID header."""
        response = test_client.get(
            "/memory-routing/info",
            headers={
                "User-Agent": "test-client/1.0",
                "x-memory-user-id": "custom-project",
            },
        )

        assert response.status_code == 200
        data = response.json()
        routing = data["routing"]
        assert routing["user_id"] == "custom-project"
        assert routing["custom_header_present"] is True

    def test_routing_info_includes_session(self, test_client):
        """Test routing info includes session information."""
        response = test_client.get("/memory-routing/info")

        assert response.status_code == 200
        data = response.json()
        assert "session_info" in data
        assert data["session_info"]["initialized"] is True


# =============================================================================
# Test Models List Endpoint
# =============================================================================


class TestModelsListEndpoint:
    """Tests for /v1/models endpoint."""

    def test_list_models_success(self, test_client):
        """Test listing models returns configured models."""
        response = test_client.get(
            "/v1/models",
            headers=get_request_headers(),
        )

        assert response.status_code == 200
        data = response.json()
        assert data["object"] == "list"
        assert "data" in data

        models = data["data"]
        assert len(models) >= 3

        model_ids = [m["id"] for m in models]
        assert "claude-sonnet-4.5" in model_ids
        assert "gpt-4" in model_ids
        assert "gpt-5-pro" in model_ids

    def test_list_models_requires_auth(self, test_client):
        """Test listing models requires authentication."""
        response = test_client.get("/v1/models")

        assert response.status_code == 401
        data = response.json()
        assert_error_format(data)

    def test_list_models_invalid_key(self, test_client):
        """Test listing models with invalid API key."""
        response = test_client.get(
            "/v1/models",
            headers=get_request_headers(api_key="sk-invalid"),
        )

        assert response.status_code == 401
        data = response.json()
        assert_error_format(data)

    def test_list_models_format(self, test_client):
        """Test models list has correct OpenAI format."""
        response = test_client.get(
            "/v1/models",
            headers=get_request_headers(),
        )

        assert response.status_code == 200
        data = response.json()

        for model in data["data"]:
            assert "id" in model
            assert "object" in model
            assert model["object"] == "model"
            assert "created" in model
            assert "owned_by" in model


# =============================================================================
# Test Chat Completions Endpoint - Non-Streaming
# =============================================================================


class TestChatCompletionsNonStreaming:
    """Tests for /v1/chat/completions (non-streaming)."""

    def test_chat_completion_success(self, test_client, mock_litellm_completion):
        """Test successful chat completion."""
        request_body = get_chat_completion_request(
            model="claude-sonnet-4.5",
            messages=[{"role": "user", "content": "Hello!"}],
        )

        response = test_client.post(
            "/v1/chat/completions",
            json=request_body,
            headers=get_request_headers(),
        )

        assert response.status_code == 200
        data = response.json()
        assert_response_format(data, streaming=False)

        # Verify litellm was called
        mock_litellm_completion.assert_called_once()

    def test_chat_completion_requires_auth(self, test_client):
        """Test chat completion requires authentication."""
        request_body = get_chat_completion_request()

        response = test_client.post(
            "/v1/chat/completions",
            json=request_body,
        )

        assert response.status_code == 401

    def test_chat_completion_invalid_key(self, test_client):
        """Test chat completion with invalid API key."""
        request_body = get_chat_completion_request()

        response = test_client.post(
            "/v1/chat/completions",
            json=request_body,
            headers=get_request_headers(api_key="sk-invalid"),
        )

        assert response.status_code == 401

    def test_chat_completion_missing_model(self, test_client):
        """Test chat completion without model parameter."""
        request_body = {"messages": [{"role": "user", "content": "Hello"}]}

        response = test_client.post(
            "/v1/chat/completions",
            json=request_body,
            headers=get_request_headers(),
        )

        assert response.status_code == 400
        data = response.json()
        assert_error_format(data)
        assert "model" in data["error"]["message"].lower()

    def test_chat_completion_missing_messages(self, test_client):
        """Test chat completion without messages parameter."""
        request_body = {"model": "claude-sonnet-4.5"}

        response = test_client.post(
            "/v1/chat/completions",
            json=request_body,
            headers=get_request_headers(),
        )

        assert response.status_code == 400
        data = response.json()
        assert "messages" in data["error"]["message"].lower()

    def test_chat_completion_invalid_model(self, test_client):
        """Test chat completion with non-existent model."""
        request_body = get_chat_completion_request(model="nonexistent-model")

        response = test_client.post(
            "/v1/chat/completions",
            json=request_body,
            headers=get_request_headers(),
        )

        assert response.status_code == 404
        data = response.json()
        assert_error_format(data)

    def test_chat_completion_memory_routing(self, test_client, mock_litellm_completion):
        """Test that memory routing headers are injected."""
        request_body = get_chat_completion_request()

        response = test_client.post(
            "/v1/chat/completions",
            json=request_body,
            headers=get_request_headers(user_agent="OpenAIClientImpl/Java"),
        )

        assert response.status_code == 200

        # Verify litellm was called with extra_headers
        call_kwargs = mock_litellm_completion.call_args[1]
        assert "extra_headers" in call_kwargs
        assert "x-sm-user-id" in call_kwargs["extra_headers"]
        assert call_kwargs["extra_headers"]["x-sm-user-id"] == "pycharm-ai"

    def test_chat_completion_custom_user_id(self, test_client, mock_litellm_completion):
        """Test chat completion with custom user ID header."""
        request_body = get_chat_completion_request()

        response = test_client.post(
            "/v1/chat/completions",
            json=request_body,
            headers=get_request_headers(custom_user_id="my-project"),
        )

        assert response.status_code == 200

        # Verify custom user ID was used
        call_kwargs = mock_litellm_completion.call_args[1]
        assert call_kwargs["extra_headers"]["x-sm-user-id"] == "my-project"

    def test_chat_completion_additional_params(
        self, test_client, mock_litellm_completion
    ):
        """Test chat completion with additional parameters."""
        request_body = get_chat_completion_request(
            model="gpt-4",
            messages=[{"role": "user", "content": "Test"}],
            temperature=0.7,
            max_tokens=100,
            top_p=0.9,
        )

        response = test_client.post(
            "/v1/chat/completions",
            json=request_body,
            headers=get_request_headers(),
        )

        assert response.status_code == 200

        # Verify parameters were passed through
        call_kwargs = mock_litellm_completion.call_args[1]
        assert call_kwargs["temperature"] == 0.7
        assert call_kwargs["max_tokens"] == 100
        assert call_kwargs["top_p"] == 0.9

    def test_chat_completion_malformed_json(self, test_client):
        """Test chat completion with malformed JSON."""
        response = test_client.post(
            "/v1/chat/completions",
            data="{invalid json",
            headers=get_request_headers(),
        )

        assert response.status_code == 400


# =============================================================================
# Test Chat Completions Endpoint - Streaming
# =============================================================================


class TestChatCompletionsStreaming:
    """Tests for /v1/chat/completions (streaming)."""

    def test_chat_completion_streaming(self, test_client, mock_litellm_streaming):
        """Test streaming chat completion."""
        request_body = get_chat_completion_request(
            model="claude-sonnet-4.5",
            messages=[{"role": "user", "content": "Hello!"}],
            stream=True,
        )

        response = test_client.post(
            "/v1/chat/completions",
            json=request_body,
            headers=get_request_headers(),
        )

        assert response.status_code == 200
        assert response.headers["content-type"] == "text/event-stream; charset=utf-8"

        # Verify streaming content
        content = response.text
        assert "data: " in content
        assert "[DONE]" in content

    def test_streaming_sse_format(self, test_client, mock_litellm_streaming):
        """Test that streaming responses use SSE format."""
        request_body = get_chat_completion_request(
            model="gpt-4",
            messages=[{"role": "user", "content": "Stream test"}],
            stream=True,
        )

        response = test_client.post(
            "/v1/chat/completions",
            json=request_body,
            headers=get_request_headers(),
        )

        assert response.status_code == 200

        # Parse SSE events
        lines = response.text.split("\n")
        data_lines = [line for line in lines if line.startswith("data: ")]

        assert len(data_lines) > 0

        # Each data line should be valid JSON (except [DONE])
        for line in data_lines:
            data_content = line[6:]  # Remove "data: " prefix
            if data_content != "[DONE]":
                chunk_data = json.loads(data_content)
                assert "choices" in chunk_data

    def test_streaming_memory_routing(self, test_client, mock_litellm_streaming):
        """Test memory routing works with streaming."""
        request_body = get_chat_completion_request(
            model="claude-sonnet-4.5",
            messages=[{"role": "user", "content": "Test"}],
            stream=True,
        )

        response = test_client.post(
            "/v1/chat/completions",
            json=request_body,
            headers=get_request_headers(user_agent="Claude Code CLI"),
        )

        assert response.status_code == 200

        # Verify memory routing was applied
        call_kwargs = mock_litellm_streaming.call_args[1]
        assert "extra_headers" in call_kwargs
        assert call_kwargs["extra_headers"]["x-sm-user-id"] == "claude-code"


# =============================================================================
# Test Error Handling
# =============================================================================


class TestErrorHandling:
    """Tests for error handling and edge cases."""

    def test_rate_limit_error(self, test_client):
        """Test handling of rate limit errors."""
        with patch("litellm.acompletion") as mock_completion:
            mock_completion.side_effect = litellm.exceptions.RateLimitError(
                message="Rate limit exceeded",
                model="gpt-4",
                llm_provider="openai",
            )

            request_body = get_chat_completion_request()
            response = test_client.post(
                "/v1/chat/completions",
                json=request_body,
                headers=get_request_headers(),
            )

            assert response.status_code == 429
            assert "Retry-After" in response.headers
            data = response.json()
            assert_error_format(data)

    def test_authentication_error(self, test_client):
        """Test handling of authentication errors."""
        with patch("litellm.acompletion") as mock_completion:
            mock_completion.side_effect = litellm.exceptions.AuthenticationError(
                message="Invalid API key",
                model="gpt-4",
                llm_provider="openai",
            )

            request_body = get_chat_completion_request()
            response = test_client.post(
                "/v1/chat/completions",
                json=request_body,
                headers=get_request_headers(),
            )

            assert response.status_code == 401
            data = response.json()
            assert_error_format(data)

    def test_context_length_error(self, test_client):
        """Test handling of context length exceeded errors."""
        with patch("litellm.acompletion") as mock_completion:
            mock_completion.side_effect = litellm.exceptions.ContextWindowExceededError(
                message="Context too long",
                model="gpt-4",
                llm_provider="openai",
            )

            request_body = get_chat_completion_request()
            response = test_client.post(
                "/v1/chat/completions",
                json=request_body,
                headers=get_request_headers(),
            )

            assert response.status_code == 400
            data = response.json()
            assert "context" in data["error"]["message"].lower()

    def test_service_unavailable_error(self, test_client):
        """Test handling of service unavailable errors."""
        with patch("litellm.acompletion") as mock_completion:
            mock_completion.side_effect = litellm.exceptions.ServiceUnavailableError(
                message="Service down",
                model="gpt-4",
                llm_provider="openai",
            )

            request_body = get_chat_completion_request()
            response = test_client.post(
                "/v1/chat/completions",
                json=request_body,
                headers=get_request_headers(),
            )

            assert response.status_code == 503
            data = response.json()
            assert_error_format(data)


# =============================================================================
# Test Application Lifecycle
# =============================================================================


class TestApplicationLifecycle:
    """Tests for application startup and shutdown."""

    @pytest.mark.asyncio
    async def test_startup_initializes_session(self, test_config_file, mock_env_vars):
        """Test that startup initializes session manager."""
        os.environ["LITELLM_CONFIG_PATH"] = test_config_file

        # Manually invoke the lifespan context manager
        lifespan_context = app.router.lifespan_context(app)
        
        async with lifespan_context:
            # Session should be initialized after lifespan startup
            assert LiteLLMSessionManager.is_initialized()

            # Use httpx.AsyncClient to make requests
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                # Health check should confirm
                response = await client.get("/health")
                data = response.json()
                assert data["session"]["initialized"] is True

        # After lifespan context exit, session should be closed
        assert not LiteLLMSessionManager.is_initialized()


# =============================================================================
# Test Execution
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
