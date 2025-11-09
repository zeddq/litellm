"""
Comprehensive pytest test suite for LiteLLM Memory Proxy Application.

This test suite provides extensive coverage for:
- MemoryRouter class (memory_router.py)
- FastAPI proxy application (litellm_proxy_with_memory.py)
- Integration and end-to-end scenarios

Test Structure:
1. Unit Tests for MemoryRouter
2. Integration Tests for FastAPI application
3. End-to-End Tests

Usage:
    pytest test_memory_proxy.py -v
    pytest test_memory_proxy.py -v --cov=. --cov-report=html
    pytest test_memory_proxy.py -v -k "test_detect_user_id"
"""

import json
import os
import tempfile
from pathlib import Path
from typing import Dict, Any
from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest
import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient

# Import modules under test
from proxy.memory_router import MemoryRouter
from proxy.schema import load_config_with_env_resolution
from proxy.litellm_proxy_with_memory import (
    create_app,
    get_memory_router,
    get_litellm_base_url,
    proxy_request,
)


# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def sample_config_dict() -> Dict[str, Any]:
    """Fixture providing sample configuration dictionary."""
    return {
        "general_settings": {"master_key": "sk-test-1234"},
        "user_id_mappings": {
            "custom_header": "x-memory-user-id",
            "default_user_id": "default-user",
            "header_patterns": [
                {
                    "header": "user-agent",
                    "pattern": "^OpenAIClientImpl/Java",
                    "user_id": "pycharm-client",
                },
                {
                    "header": "user-agent",
                    "pattern": "^anthropic-sdk-python",
                    "user_id": "anthropic-python",
                },
                {
                    "header": "user-agent",
                    "pattern": "^Claude Code",
                    "user_id": "claude-code",
                },
                {
                    "header": "x-client-type",
                    "pattern": "mobile-app",
                    "user_id": "mobile-user",
                },
            ],
        },
        "model_list": [
            {
                "model_name": "gpt-4",
                "litellm_params": {
                    "model": "openai/gpt-4",
                    "api_key": "os.environ/OPENAI_API_KEY",
                },
            },
            {
                "model_name": "claude-sonnet",
                "litellm_params": {
                    "api_base": "https://api.supermemory.ai/v3/api.anthropic.com",
                    "model": "anthropic/claude-sonnet-4-5-20250929",
                    "api_key": "os.environ/ANTHROPIC_API_KEY",
                    "custom_llm_provider": "anthropic",
                },
            },
        ],
    }


@pytest.fixture
def config_file(sample_config_dict: Dict[str, Any]) -> str:
    """Fixture providing a temporary config file."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", delete=False
    ) as tmp_file:
        yaml.dump(sample_config_dict, tmp_file)
        tmp_file.flush()
        yield tmp_file.name
    # Cleanup
    Path(tmp_file.name).unlink(missing_ok=True)


@pytest.fixture
def with_litellm_auth():
    """Fixture providing LiteLLM auth token."""
    return "Bearer test-key"


@pytest.fixture
def memory_router(config_file: str) -> MemoryRouter:
    """Fixture providing initialized MemoryRouter instance."""
    config = load_config_with_env_resolution(config_file)
    return MemoryRouter(config)


@pytest.fixture
def app_with_router(with_litellm_auth, memory_router: MemoryRouter):
    """Fixture providing FastAPI app with MemoryRouter."""
    return create_app(
        litellm_auth_token=with_litellm_auth,
        memory_router=memory_router,
        litellm_base_url="http://localhost:4000"
    )


@pytest.fixture
def app_without_router(with_litellm_auth):
    """Fixture providing FastAPI app without MemoryRouter."""
    return create_app(
        litellm_auth_token=with_litellm_auth,
        memory_router=None,
        litellm_base_url="http://localhost:4000"
    )


@pytest.fixture
def test_client(app_with_router: FastAPI):
    """Fixture providing FastAPI test client with lifespan context."""
    with TestClient(app_with_router) as client:
        yield client


@pytest.fixture
def test_client_no_router(app_without_router):
    """Fixture providing FastAPI test client without router with lifespan context."""
    with TestClient(app_without_router) as client:
        yield client


@pytest.fixture
def mock_httpx_response():
    """Fixture providing mock httpx response."""

    def _create_response(
        status_code: int = 200,
        headers: Dict[str, str] = None,
        content: bytes = b'{"result": "success"}',
    ):
        mock_response = Mock()
        mock_response.status_code = status_code
        mock_response.headers = headers or {"content-type": "application/json"}
        mock_response.content = content
        return mock_response

    return _create_response


# ============================================================================
# UNIT TESTS: MemoryRouter
# ============================================================================


class TestMemoryRouterInit:
    """Tests for MemoryRouter initialization."""

    def test_init_with_valid_config(self, config_file: str):
        """Test MemoryRouter initialization with valid config file."""
        config = load_config_with_env_resolution(config_file)
        router = MemoryRouter(config)

        assert router is not None
        assert len(router.header_patterns) == 4
        assert router.custom_header == "x-memory-user-id"
        assert router.default_user_id == "default-user"

    def test_init_with_missing_config(self):
        """Test MemoryRouter initialization with missing config file."""
        # Should raise FileNotFoundError
        with pytest.raises(FileNotFoundError):
            config = load_config_with_env_resolution("nonexistent_config.yaml")

    def test_init_with_invalid_config(self):
        """Test MemoryRouter initialization with invalid YAML."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("invalid: yaml: syntax: [[[")
            f.flush()
            temp_path = f.name

        try:
            # Should raise YAMLError for invalid YAML
            with pytest.raises(yaml.YAMLError):
                config = load_config_with_env_resolution(temp_path)
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_header_patterns_compilation(self, memory_router: MemoryRouter):
        """Test that regex patterns are compiled correctly."""
        patterns = memory_router.header_patterns

        assert len(patterns) == 4

        # Check pattern structure (HeaderPattern named tuple)
        for pattern in patterns:
            assert hasattr(pattern, "header")
            assert hasattr(pattern, "pattern")
            assert hasattr(pattern, "user_id")
            assert hasattr(pattern, "pattern_compiled")
            # Verify pattern_compiled is compiled regex
            assert hasattr(pattern.pattern_compiled, "search")


class TestMemoryRouterDetectUserId:
    """Tests for MemoryRouter.detect_user_id method."""

    def test_detect_from_custom_header(self, memory_router: MemoryRouter):
        """Test user ID detection from custom header (highest priority)."""
        headers = {
            "x-memory-user-id": "custom-user-123",
            "user-agent": "OpenAIClientImpl/Java unknown",  # Would match pattern
        }

        user_id = memory_router.detect_user_id(headers)
        assert user_id == "custom-user-123"

    def test_detect_from_pycharm_user_agent(self, memory_router: MemoryRouter):
        """Test user ID detection from PyCharm user-agent pattern."""
        headers = {"user-agent": "OpenAIClientImpl/Java unknown"}

        user_id = memory_router.detect_user_id(headers)
        assert user_id == "pycharm-client"

    def test_detect_from_anthropic_sdk(self, memory_router: MemoryRouter):
        """Test user ID detection from Anthropic SDK user-agent."""
        headers = {"user-agent": "anthropic-sdk-python/0.71.0"}

        user_id = memory_router.detect_user_id(headers)
        assert user_id == "anthropic-python"

    def test_detect_from_claude_code(self, memory_router: MemoryRouter):
        """Test user ID detection from Claude Code user-agent."""
        headers = {"user-agent": "Claude Code/1.2.3"}

        user_id = memory_router.detect_user_id(headers)
        assert user_id == "claude-code"

    def test_detect_from_custom_header_pattern(self, memory_router: MemoryRouter):
        """Test user ID detection from custom header pattern (x-client-type)."""
        headers = {"x-client-type": "mobile-app"}

        user_id = memory_router.detect_user_id(headers)
        assert user_id == "mobile-user"

    def test_detect_default_user_id(self, memory_router: MemoryRouter):
        """Test default user ID when no patterns match."""
        headers = {"user-agent": "curl/7.68.0"}

        user_id = memory_router.detect_user_id(headers)
        assert user_id == "default-user"

    def test_detect_case_insensitive_headers(self, memory_router: MemoryRouter):
        """Test that header matching is case-insensitive."""
        headers = {"USER-AGENT": "Claude Code/1.0"}

        user_id = memory_router.detect_user_id(headers)
        assert user_id == "claude-code"

    def test_detect_empty_headers(self, memory_router: MemoryRouter):
        """Test user ID detection with empty headers."""
        headers = {}

        user_id = memory_router.detect_user_id(headers)
        assert user_id == "default-user"

    def test_detect_with_multiple_matching_patterns(self, memory_router: MemoryRouter):
        """Test that first matching pattern wins."""
        # Both patterns could match, but first one should win
        headers = {"user-agent": "OpenAIClientImpl/Java unknown"}

        user_id = memory_router.detect_user_id(headers)
        # Should match first pattern (pycharm-client)
        assert user_id == "pycharm-client"

    def test_detect_partial_pattern_match(self, memory_router: MemoryRouter):
        """Test that patterns support partial matching."""
        headers = {
            "user-agent": "OpenAIClientImpl/Java unknown with extra stuff"
        }

        user_id = memory_router.detect_user_id(headers)
        assert user_id == "pycharm-client"


class TestMemoryRouterInjectHeaders:
    """Tests for MemoryRouter.inject_memory_headers method."""

    def test_inject_headers_basic(self, memory_router: MemoryRouter):
        """Test basic header injection."""
        headers = {"user-agent": "Claude Code/1.0", "authorization": "Bearer sk-123"}

        updated = memory_router.inject_memory_headers(headers)

        assert "x-sm-user-id" in updated
        assert updated["x-sm-user-id"] == "claude-code"
        assert "authorization" in updated  # Original headers preserved

    def test_inject_headers_with_api_key(self, memory_router: MemoryRouter):
        """Test header injection with Supermemory API key."""
        headers = {"user-agent": "curl/7.68.0"}
        api_key = "sm_test_key_123"

        updated = memory_router.inject_memory_headers(headers, api_key)

        assert updated["x-sm-user-id"] == "default-user"
        assert updated["x-supermemory-api-key"] == api_key

    def test_inject_headers_without_api_key(self, memory_router: MemoryRouter):
        """Test header injection without API key."""
        headers = {"user-agent": "curl/7.68.0"}

        updated = memory_router.inject_memory_headers(headers)

        assert "x-sm-user-id" in updated
        assert "x-supermemory-api-key" not in updated

    def test_inject_headers_preserves_originals(self, memory_router: MemoryRouter):
        """Test that original headers are preserved."""
        headers = {
            "user-agent": "test-agent",
            "content-type": "application/json",
            "authorization": "Bearer token",
        }

        updated = memory_router.inject_memory_headers(headers)

        # Original headers should be preserved
        assert updated["user-agent"] == "test-agent"
        assert updated["content-type"] == "application/json"
        assert updated["authorization"] == "Bearer token"
        # New header added
        assert "x-sm-user-id" in updated


class TestMemoryRouterSupermemoryCheck:
    """Tests for MemoryRouter.should_use_supermemory method."""

    def test_should_use_supermemory_true(self, memory_router: MemoryRouter):
        """Test detection of Supermemory-enabled model."""
        result = memory_router.should_use_supermemory("claude-sonnet")
        assert result is True

    def test_should_use_supermemory_false(self, memory_router: MemoryRouter):
        """Test detection of non-Supermemory model."""
        result = memory_router.should_use_supermemory("gpt-4")
        assert result is False

    def test_should_use_supermemory_unknown_model(self, memory_router: MemoryRouter):
        """Test with unknown model name."""
        result = memory_router.should_use_supermemory("unknown-model")
        assert result is False

    def test_should_use_supermemory_empty_model(self, memory_router: MemoryRouter):
        """Test with empty model name."""
        result = memory_router.should_use_supermemory("")
        assert result is False


class TestMemoryRouterRoutingInfo:
    """Tests for MemoryRouter.get_routing_info method."""

    def test_routing_info_with_pattern_match(self, memory_router: MemoryRouter):
        """Test routing info when pattern matches."""
        headers = {"user-agent": "Claude Code/1.0"}

        info = memory_router.get_routing_info(headers)

        assert info["user_id"] == "claude-code"
        assert info["matched_pattern"] is not None
        assert info["matched_pattern"]["header"] == "user-agent"
        assert info["matched_pattern"]["user_id"] == "claude-code"
        assert info["custom_header_present"] is False
        assert info["is_default"] is False

    def test_routing_info_with_custom_header(self, memory_router: MemoryRouter):
        """Test routing info with custom header."""
        headers = {"x-memory-user-id": "my-custom-id"}

        info = memory_router.get_routing_info(headers)

        assert info["user_id"] == "my-custom-id"
        assert info["matched_pattern"] is None
        assert info["custom_header_present"] is True
        assert info["is_default"] is False

    def test_routing_info_default(self, memory_router: MemoryRouter):
        """Test routing info with default user ID."""
        headers = {"user-agent": "curl/7.68.0"}

        info = memory_router.get_routing_info(headers)

        assert info["user_id"] == "default-user"
        assert info["matched_pattern"] is None
        assert info["custom_header_present"] is False
        assert info["is_default"] is True

    def test_routing_info_structure(self, memory_router: MemoryRouter):
        """Test that routing info has expected structure."""
        headers = {"user-agent": "test"}

        info = memory_router.get_routing_info(headers)

        # Verify all expected keys are present
        assert "user_id" in info
        assert "matched_pattern" in info
        assert "custom_header_present" in info
        assert "is_default" in info


# ============================================================================
# INTEGRATION TESTS: FastAPI Application
# ============================================================================


class TestFastAPIAppCreation:
    """Tests for FastAPI app factory function."""

    def test_create_app_with_router(self, with_litellm_auth, memory_router: MemoryRouter):
        """Test app creation with MemoryRouter."""
        app = create_app(
            litellm_auth_token=with_litellm_auth,
            memory_router=memory_router,
            litellm_base_url="http://localhost:4000"
        )

        assert app is not None
        assert hasattr(app, "state")

    def test_create_app_without_router(self, with_litellm_auth):
        """Test app creation without MemoryRouter."""
        app = create_app(
            litellm_auth_token=with_litellm_auth,
            memory_router=None,
            litellm_base_url="http://localhost:4000"
        )

        assert app is not None
        assert hasattr(app, "state")

    def test_app_has_expected_routes(self, app_with_router):
        """Test that app has expected routes."""
        routes = [route.path for route in app_with_router.routes]

        assert "/health" in routes
        assert "/memory-routing/info" in routes

    def test_app_state_initialization(self, with_litellm_auth, memory_router: MemoryRouter):
        """Test that app state is initialized correctly during lifespan."""
        app = create_app(
            litellm_auth_token=with_litellm_auth,
            memory_router=memory_router,
            litellm_base_url="http://test:9999"
        )

        # Create test client to trigger lifespan
        with TestClient(app) as client:
            # Access app state through a request
            response = client.get("/health")
            assert response.status_code == 200


class TestHealthEndpoint:
    """Tests for /health endpoint."""

    def test_health_check_with_router(self, test_client: TestClient):
        """Test health endpoint with MemoryRouter enabled."""
        response = test_client.get("/health")

        assert response.status_code == 200
        data = response.json()

        assert data["status"] == "healthy"
        assert data["memory_router"] is True
        assert data["litellm_base_url"] == "http://localhost:4000"

    def test_health_check_without_router(self, test_client_no_router: TestClient):
        """Test health endpoint without MemoryRouter."""
        response = test_client_no_router.get("/health")

        assert response.status_code == 200
        data = response.json()

        assert data["status"] == "healthy"
        assert data["memory_router"] is False
        assert data["litellm_base_url"] == "http://localhost:4000"

    def test_health_endpoint_returns_json(self, test_client: TestClient):
        """Test that health endpoint returns proper JSON."""
        response = test_client.get("/health")

        assert response.headers["content-type"] == "application/json"
        # Should be valid JSON
        _ = response.json()


class TestRoutingInfoEndpoint:
    """Tests for /memory-routing/info endpoint."""

    def test_routing_info_with_pycharm_agent(self, test_client: TestClient):
        """Test routing info endpoint with PyCharm user agent."""
        response = test_client.get(
            "/memory-routing/info", headers={"user-agent": "OpenAIClientImpl/Java unknown"}
        )

        assert response.status_code == 200
        data = response.json()

        assert data["user_id"] == "pycharm-client"
        assert data["matched_pattern"] is not None
        assert data["is_default"] is False

    def test_routing_info_with_custom_header(self, test_client: TestClient):
        """Test routing info endpoint with custom header."""
        response = test_client.get(
            "/memory-routing/info", headers={"x-memory-user-id": "test-user-123"}
        )

        assert response.status_code == 200
        data = response.json()

        assert data["user_id"] == "test-user-123"
        assert data["custom_header_present"] is True

    def test_routing_info_default(self, test_client: TestClient):
        """Test routing info endpoint with default routing."""
        response = test_client.get(
            "/memory-routing/info", headers={"user-agent": "curl/7.68.0"}
        )

        assert response.status_code == 200
        data = response.json()

        assert data["user_id"] == "default-user"
        assert data["is_default"] is True

    def test_routing_info_without_router(self, test_client_no_router: TestClient):
        """Test routing info endpoint when router is not initialized."""
        response = test_client_no_router.get("/memory-routing/info")

        assert response.status_code == 200
        data = response.json()

        assert "error" in data
        assert "not initialized" in data["error"]


class TestProxyHandler:
    """Tests for main proxy handler."""

    @pytest.mark.asyncio
    async def test_proxy_request_success(self, mock_httpx_response):
        """Test successful proxy request."""
        mock_response = mock_httpx_response(
            status_code=200,
            headers={"content-type": "application/json"},
            content=b'{"message": "success"}',
        )

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = Mock()
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            mock_instance.request = AsyncMock(return_value=mock_response)
            mock_client.return_value = mock_instance

            status, headers, body = await proxy_request(
                method="GET",
                path="/test",
                headers={"user-agent": "test"},
                body=None,
                litellm_base_url="http://localhost:4000",
            )

            assert status == 200
            assert "content-type" in headers
            assert body == b'{"message": "success"}'

    @pytest.mark.asyncio
    async def test_proxy_request_with_body(self, mock_httpx_response):
        """Test proxy request with request body."""
        request_body = b'{"model": "gpt-4", "messages": []}'
        mock_response = mock_httpx_response(status_code=200)

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = Mock()
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            mock_instance.request = AsyncMock(return_value=mock_response)
            mock_client.return_value = mock_instance

            status, headers, body = await proxy_request(
                method="POST",
                path="/v1/chat/completions",
                headers={"content-type": "application/json"},
                body=request_body,
                litellm_base_url="http://localhost:4000",
            )

            # Verify request was made with correct body
            mock_instance.request.assert_called_once()
            call_kwargs = mock_instance.request.call_args[1]
            assert call_kwargs["content"] == request_body

    @pytest.mark.asyncio
    async def test_proxy_request_error_handling(self):
        """Test proxy request error handling."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = Mock()
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            mock_instance.request = AsyncMock(
                side_effect=httpx.ConnectError("Connection failed")
            )
            mock_client.return_value = mock_instance

            with pytest.raises(httpx.ConnectError):
                await proxy_request(
                    method="GET",
                    path="/test",
                    headers={},
                    body=None,
                    litellm_base_url="http://localhost:4000",
                )

    def test_chat_completion_without_supermemory(self, test_client: TestClient):
        """Test chat completion request for non-Supermemory model."""
        request_data = {"model": "gpt-4", "messages": [{"role": "user", "content": "Hello"}]}

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = Mock()
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)

            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.headers = {"content-type": "application/json"}
            mock_response.content = b'{"choices": []}'
            mock_instance.request = AsyncMock(return_value=mock_response)

            mock_client.return_value = mock_instance

            response = test_client.post(
                "/v1/chat/completions",
                json=request_data,
                headers={"user-agent": "test-client"},
            )

            assert response.status_code == 200

    def test_chat_completion_with_supermemory(self, test_client: TestClient):
        """Test chat completion request for Supermemory-enabled model."""
        request_data = {
            "model": "claude-sonnet",
            "messages": [{"role": "user", "content": "Hello"}],
        }

        with patch("httpx.AsyncClient") as mock_client, patch.dict(
            os.environ, {"SUPERMEMORY_API_KEY": "sm_test_key"}
        ):
            mock_instance = Mock()
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)

            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.headers = {"content-type": "application/json"}
            mock_response.content = b'{"content": []}'
            mock_instance.request = AsyncMock(return_value=mock_response)

            mock_client.return_value = mock_instance

            response = test_client.post(
                "/v1/chat/completions",
                json=request_data,
                headers={"user-agent": "Claude Code/1.0"},
            )

            assert response.status_code == 200

            # Verify that Supermemory headers were injected
            call_kwargs = mock_instance.request.call_args[1]
            injected_headers = call_kwargs["headers"]
            # Note: x-sm-user-id should be in headers
            assert "x-sm-user-id" in injected_headers or any(
                "x-sm-user-id" in str(v) for v in injected_headers.values()
            )

    def test_invalid_json_body_handling(self, test_client: TestClient):
        """Test handling of invalid JSON in request body."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = Mock()
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)

            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.headers = {"content-type": "application/json"}
            mock_response.content = b'{"result": "ok"}'
            mock_instance.request = AsyncMock(return_value=mock_response)

            mock_client.return_value = mock_instance

            # Send invalid JSON
            response = test_client.post(
                "/v1/chat/completions",
                content=b"invalid json {{{",
                headers={"content-type": "application/json"},
            )

            # Should still forward the request
            assert response.status_code == 200

    def test_get_request_forwarding(self, test_client: TestClient):
        """Test that GET requests are forwarded correctly."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = Mock()
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)

            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.headers = {"content-type": "application/json"}
            mock_response.content = b'{"models": []}'
            mock_instance.request = AsyncMock(return_value=mock_response)

            mock_client.return_value = mock_instance

            response = test_client.get("/v1/models")

            assert response.status_code == 200
            mock_instance.request.assert_called_once()

    def test_query_string_preservation(self, test_client: TestClient):
        """Test that query strings are preserved in forwarding."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = Mock()
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)

            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.headers = {"content-type": "application/json"}
            mock_response.content = b'{"result": "ok"}'
            mock_instance.request = AsyncMock(return_value=mock_response)

            mock_client.return_value = mock_instance

            response = test_client.get("/v1/models?limit=10&offset=5")

            assert response.status_code == 200

            # Verify query string was included
            call_kwargs = mock_instance.request.call_args[1]
            assert "limit=10" in call_kwargs["url"]
            assert "offset=5" in call_kwargs["url"]


class TestStreamingResponse:
    """Tests for streaming response handling."""

    def test_streaming_response_detection(self, test_client: TestClient):
        """Test detection and handling of streaming responses."""
        request_data = {
            "model": "gpt-4",
            "messages": [{"role": "user", "content": "Hello"}],
            "stream": True,
        }

        async def mock_stream():
            yield b'data: {"delta": {"content": "Hello"}}\n\n'
            yield b'data: {"delta": {"content": " world"}}\n\n'
            yield b"data: [DONE]\n\n"

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = Mock()
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)

            # Mock streaming response
            mock_stream_response = Mock()
            mock_stream_response.__aenter__ = AsyncMock(
                return_value=mock_stream_response
            )
            mock_stream_response.__aexit__ = AsyncMock(return_value=None)
            mock_stream_response.aiter_bytes = lambda: mock_stream()

            mock_instance.stream = Mock(return_value=mock_stream_response)

            # Mock non-streaming response for initial detection
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.headers = {"content-type": "text/event-stream"}
            mock_response.content = b""
            mock_instance.request = AsyncMock(return_value=mock_response)

            mock_client.return_value = mock_instance

            response = test_client.post(
                "/v1/chat/completions",
                json=request_data,
            )

            # StreamingResponse returns 200
            assert response.status_code == 200


class TestErrorHandling:
    """Tests for error handling scenarios."""

    def test_proxy_backend_unavailable(self, test_client: TestClient):
        """Test handling when LiteLLM backend is unavailable."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = Mock()
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            mock_instance.request = AsyncMock(
                side_effect=httpx.ConnectError("Connection refused")
            )
            mock_client.return_value = mock_instance

            response = test_client.get("/v1/models")

            assert response.status_code == 500
            assert b"Connection refused" in response.content

    def test_proxy_timeout(self, test_client: TestClient):
        """Test handling of request timeouts."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = Mock()
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            mock_instance.request = AsyncMock(
                side_effect=httpx.TimeoutException("Request timeout")
            )
            mock_client.return_value = mock_instance

            response = test_client.post(
                "/v1/chat/completions",
                json={"model": "gpt-4", "messages": []},
            )

            assert response.status_code == 500

    def test_malformed_response_from_backend(self, test_client: TestClient):
        """Test handling of malformed responses from backend."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = Mock()
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)

            # Return response with missing attributes
            mock_response = Mock()
            mock_response.status_code = 500
            mock_response.headers = {}
            mock_response.content = b"Internal Server Error"
            mock_instance.request = AsyncMock(return_value=mock_response)

            mock_client.return_value = mock_instance

            response = test_client.get("/v1/models")

            # Should handle gracefully
            assert response.status_code in [500, 502, 503, 504]


class TestDependencyInjection:
    """Tests for FastAPI dependency injection."""

    def test_get_memory_router_dependency(self, with_litellm_auth, memory_router: MemoryRouter):
        """Test get_memory_router dependency function."""
        app = create_app(litellm_auth_token=with_litellm_auth, memory_router=memory_router)

        with TestClient(app) as client:
            # The dependency should provide the router
            response = client.get("/memory-routing/info")
            assert response.status_code == 200
            # Should not error, meaning router was injected

    def test_get_litellm_base_url_dependency(self, with_litellm_auth):
        """Test get_litellm_base_url dependency function."""
        custom_url = "http://custom-litellm:9999"
        app = create_app(
            litellm_auth_token=with_litellm_auth,
            memory_router=None,
            litellm_base_url=custom_url
        )

        with TestClient(app) as client:
            response = client.get("/health")
            assert response.status_code == 200
            data = response.json()
            assert data["litellm_base_url"] == custom_url


# ============================================================================
# END-TO-END TESTS
# ============================================================================


class TestEndToEndScenarios:
    """End-to-end integration tests."""

    def test_complete_pycharm_request_flow(self, test_client: TestClient):
        """Test complete request flow from PyCharm client."""
        # Simulate PyCharm AI Assistant request
        request_data = {
            "model": "claude-sonnet",
            "messages": [
                {"role": "user", "content": "Write a Python function to sort a list"}
            ],
        }

        headers = {
            "user-agent": "OpenAIClientImpl/Java unknown",
            "x-stainless-lang": "java",
            "content-type": "application/json",
        }

        with patch("httpx.AsyncClient") as mock_client, patch.dict(
            os.environ, {"SUPERMEMORY_API_KEY": "sm_test_key"}
        ):
            mock_instance = Mock()
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)

            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.headers = {"content-type": "application/json"}
            mock_response.content = b'{"content": [{"text": "def sort_list..."}]}'
            mock_instance.request = AsyncMock(return_value=mock_response)

            mock_client.return_value = mock_instance

            # Make request
            response = test_client.post(
                "/v1/chat/completions", json=request_data, headers=headers
            )

            assert response.status_code == 200

            # Verify headers were injected
            call_kwargs = mock_instance.request.call_args[1]
            forwarded_headers = call_kwargs["headers"]

            # Should have user ID injected
            has_user_id = (
                "x-sm-user-id" in forwarded_headers
                or any("pycharm" in str(v).lower() for v in forwarded_headers.values())
            )
            assert has_user_id or "x-sm-user-id" in str(forwarded_headers)

    def test_complete_claude_code_request_flow(self, test_client: TestClient):
        """Test complete request flow from Claude Code CLI."""
        request_data = {
            "model": "claude-sonnet",
            "messages": [{"role": "user", "content": "Explain async/await in Python"}],
        }

        headers = {
            "user-agent": "Claude Code/1.2.3",
            "content-type": "application/json",
        }

        with patch("httpx.AsyncClient") as mock_client, patch.dict(
            os.environ, {"SUPERMEMORY_API_KEY": "sm_test_key"}
        ):
            mock_instance = Mock()
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)

            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.headers = {"content-type": "application/json"}
            mock_response.content = b'{"content": [{"text": "Async/await..."}]}'
            mock_instance.request = AsyncMock(return_value=mock_response)

            mock_client.return_value = mock_instance

            response = test_client.post(
                "/v1/chat/completions", json=request_data, headers=headers
            )

            assert response.status_code == 200

    def test_multi_client_isolation(self, test_client: TestClient):
        """Test that different clients get different user IDs."""
        clients = [
            ("OpenAIClientImpl/Java", "pycharm-client"),
            ("Claude Code/1.0", "claude-code"),
            ("anthropic-sdk-python/0.71", "anthropic-python"),
            ("curl/7.68.0", "default-user"),
        ]

        for user_agent, expected_user_id in clients:
            response = test_client.get(
                "/memory-routing/info", headers={"user-agent": user_agent}
            )

            assert response.status_code == 200
            data = response.json()
            assert (
                data["user_id"] == expected_user_id
            ), f"Failed for user-agent: {user_agent}"

    def test_custom_header_override(self, test_client: TestClient):
        """Test that custom header overrides pattern matching."""
        headers = {
            "user-agent": "OpenAIClientImpl/Java",  # Would match pycharm pattern
            "x-memory-user-id": "custom-override-id",  # Should take precedence
        }

        response = test_client.get("/memory-routing/info", headers=headers)

        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == "custom-override-id"


# ============================================================================
# PARAMETRIZED TESTS
# ============================================================================


@pytest.mark.parametrize(
    "user_agent,expected_user_id",
    [
        ("OpenAIClientImpl/Java unknown", "pycharm-client"),
        ("OpenAIClientImpl/Java 17.0.1", "pycharm-client"),
        ("anthropic-sdk-python/0.71.0", "anthropic-python"),
        ("anthropic-sdk-python/1.0.0", "anthropic-python"),
        ("Claude Code/1.0.0", "claude-code"),
        ("Claude Code/2.5.3", "claude-code"),
        ("curl/7.68.0", "default-user"),
        ("Mozilla/5.0", "default-user"),
        ("python-requests/2.28.0", "default-user"),
    ],
)
def test_user_agent_detection(
    memory_router: MemoryRouter, user_agent: str, expected_user_id: str
):
    """Parametrized test for various user agent patterns."""
    headers = {"user-agent": user_agent}
    user_id = memory_router.detect_user_id(headers)
    assert user_id == expected_user_id, f"Failed for user-agent: {user_agent}"


@pytest.mark.parametrize(
    "model_name,should_use_memory",
    [
        ("claude-sonnet", True),
        ("gpt-4", False),
        ("gpt-5-pro", False),
        ("unknown-model", False),
        ("", False),
    ],
)
def test_supermemory_model_detection(
    memory_router: MemoryRouter, model_name: str, should_use_memory: bool
):
    """Parametrized test for Supermemory model detection."""
    result = memory_router.should_use_supermemory(model_name)
    assert result == should_use_memory, f"Failed for model: {model_name}"


@pytest.mark.parametrize(
    "method",
    ["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
)
def test_http_methods_forwarding(test_client: TestClient, method: str):
    """Parametrized test for different HTTP methods."""
    with patch("httpx.AsyncClient") as mock_client:
        mock_instance = Mock()
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=None)

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "application/json"}
        mock_response.content = b'{"result": "ok"}'
        mock_instance.request = AsyncMock(return_value=mock_response)

        mock_client.return_value = mock_instance

        response = test_client.request(method, "/v1/test")

        assert response.status_code == 200
        mock_instance.request.assert_called_once()
        assert mock_instance.request.call_args[1]["method"] == method


# ============================================================================
# EDGE CASES AND BOUNDARY CONDITIONS
# ============================================================================


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_empty_config_file(self):
        """Test handling of empty config file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("")  # Empty file
            f.flush()
            temp_path = f.name

        try:
            # Should raise ValueError for empty config
            with pytest.raises(ValueError, match="Config file is empty"):
                config = load_config_with_env_resolution(temp_path)
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_very_long_header_value(self, memory_router: MemoryRouter):
        """Test handling of very long header values."""
        long_value = "A" * 10000
        headers = {"user-agent": long_value}

        # Should not crash
        user_id = memory_router.detect_user_id(headers)
        assert user_id == "default-user"

    def test_special_characters_in_headers(self, memory_router: MemoryRouter):
        """Test handling of special characters in headers."""
        headers = {
            "user-agent": "Test@#$%^&*(){}[]|\\;:'\"<>?,./`~",
            "x-custom": "value with\nnewlines\tand\ttabs",
        }

        # Should not crash
        user_id = memory_router.detect_user_id(headers)
        assert user_id is not None

    def test_unicode_in_headers(self, memory_router: MemoryRouter):
        """Test handling of Unicode characters in headers."""
        headers = {
            "user-agent": "Test-客户端-🚀",
            "x-custom": "Тест",
        }

        # Should handle gracefully
        user_id = memory_router.detect_user_id(headers)
        assert user_id is not None

    def test_case_sensitivity_edge_cases(self, memory_router: MemoryRouter):
        """Test various case sensitivity scenarios."""
        test_cases = [
            {"USER-AGENT": "Claude Code/1.0"},
            {"user-AGENT": "Claude Code/1.0"},
            {"UsEr-AgEnT": "Claude Code/1.0"},
        ]

        for headers in test_cases:
            user_id = memory_router.detect_user_id(headers)
            assert user_id == "claude-code"

    def test_duplicate_headers(self, memory_router: MemoryRouter):
        """Test handling when header appears multiple times."""
        # In dict form, only one will exist
        headers = {"user-agent": "Claude Code/1.0"}

        user_id = memory_router.detect_user_id(headers)
        assert user_id == "claude-code"

    def test_none_values_in_headers(self, memory_router: MemoryRouter):
        """Test handling of None values in headers."""
        headers = {"user-agent": "test", "x-custom": None}

        # Should handle gracefully
        user_id = memory_router.detect_user_id(headers)
        assert user_id is not None

    def test_very_large_request_body(self, test_client: TestClient):
        """Test handling of very large request bodies."""
        # Create large payload
        large_messages = [
            {"role": "user", "content": "A" * 1000} for _ in range(100)
        ]
        request_data = {"model": "gpt-4", "messages": large_messages}

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = Mock()
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)

            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.headers = {"content-type": "application/json"}
            mock_response.content = b'{"result": "ok"}'
            mock_instance.request = AsyncMock(return_value=mock_response)

            mock_client.return_value = mock_instance

            response = test_client.post("/v1/chat/completions", json=request_data)

            # Should handle large payloads
            assert response.status_code == 200

    def test_regex_pattern_edge_cases(self):
        """Test regex patterns with special cases."""
        config_dict = {
            "user_id_mappings": {
                "custom_header": "x-memory-user-id",
                "default_user_id": "default",
                "header_patterns": [
                    {
                        "header": "user-agent",
                        "pattern": "^Test.*",  # Starts with Test
                        "user_id": "test-user",
                    },
                    {
                        "header": "user-agent",
                        "pattern": ".*Special$",  # Ends with Special
                        "user_id": "special-user",
                    },
                    {
                        "header": "user-agent",
                        "pattern": "\\d{3}",  # Contains 3 digits
                        "user_id": "number-user",
                    },
                ],
            }
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(config_dict, f)
            f.flush()
            temp_path = f.name

        try:
            config = load_config_with_env_resolution(temp_path)
            router = MemoryRouter(config)

            # Test various patterns
            assert router.detect_user_id({"user-agent": "TestClient/1.0"}) == "test-user"
            assert router.detect_user_id({"user-agent": "ClientSpecial"}) == "special-user"
            assert router.detect_user_id({"user-agent": "Version123"}) == "number-user"
            assert router.detect_user_id({"user-agent": "NoMatch"}) == "default"
        finally:
            Path(temp_path).unlink(missing_ok=True)


# ============================================================================
# PERFORMANCE TESTS (Optional)
# ============================================================================


class TestPerformance:
    """Optional performance tests."""

    @pytest.mark.slow
    def test_router_performance_many_patterns(self):
        """Test router performance with many patterns."""
        # Create config with many patterns
        config_dict = {
            "user_id_mappings": {
                "custom_header": "x-memory-user-id",
                "default_user_id": "default",
                "header_patterns": [
                    {
                        "header": "user-agent",
                        "pattern": f"^Client{i}",
                        "user_id": f"user-{i}",
                    }
                    for i in range(100)
                ],
            }
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(config_dict, f)
            f.flush()
            temp_path = f.name

        try:
            config = load_config_with_env_resolution(temp_path)
            router = MemoryRouter(config)

            # Test detection speed
            import time

            start = time.time()
            for i in range(1000):
                router.detect_user_id({"user-agent": f"Client{i % 100}/1.0"})
            elapsed = time.time() - start

            # Should be reasonably fast (< 1 second for 1000 operations)
            assert elapsed < 1.0, f"Too slow: {elapsed:.3f}s for 1000 operations"
        finally:
            Path(temp_path).unlink(missing_ok=True)

    @pytest.mark.slow
    def test_concurrent_requests(self, test_client: TestClient):
        """Test handling of concurrent requests."""
        import concurrent.futures

        def make_request():
            with patch("httpx.AsyncClient") as mock_client:
                mock_instance = Mock()
                mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
                mock_instance.__aexit__ = AsyncMock(return_value=None)

                mock_response = Mock()
                mock_response.status_code = 200
                mock_response.headers = {"content-type": "application/json"}
                mock_response.content = b'{"result": "ok"}'
                mock_instance.request = AsyncMock(return_value=mock_response)

                mock_client.return_value = mock_instance

                return test_client.get("/health")

        # Run concurrent requests
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(make_request) for _ in range(50)]
            results = [f.result() for f in futures]

        # All should succeed
        assert all(r.status_code == 200 for r in results)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
