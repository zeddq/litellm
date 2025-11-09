"""
Unit tests for the refactored LiteLLM proxy with memory routing.

These tests demonstrate the improved testability achieved by:
1. Eliminating global variables
2. Using factory function pattern
3. Dependency injection
4. app.state for configuration

Run with: pytest test_litellm_proxy_refactored.py -v
"""

import json
from typing import Dict, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from proxy.litellm_proxy_with_memory import create_app, get_memory_router, get_litellm_base_url
from proxy.memory_router import MemoryRouter

@pytest.fixture
def with_litellm_auth():
    return "Bearer test-key"

@pytest.fixture
def mock_memory_router(with_litellm_auth):
    """Create a mock MemoryRouter for testing."""
    router = MagicMock(spec=MemoryRouter)
    router.header_patterns = [
        {
            "header": "user-agent",
            "pattern": "PyCharm",
            "user_id": "pycharm-project",
        }
    ]
    router.should_use_supermemory.return_value = True
    router.get_routing_info.return_value = {
        "user_id": "test-user",
        "matched_pattern": {
            "header": "user-agent",
            "value": "PyCharm",
            "pattern": "PyCharm",
            "user_id": "pycharm-project",
        },
        "custom_header_present": False,
        "is_default": False,
    }
    router.inject_memory_headers.return_value = {
        "authorization": with_litellm_auth,
        "x-sm-user-id": "test-user",
        "x-supermemory-api-key": "test-sm-key",
    }
    return router


@pytest.fixture
def app_with_router(with_litellm_auth, mock_memory_router):
    """Create FastAPI app with mocked MemoryRouter."""
    return create_app(
        litellm_auth_token=with_litellm_auth, memory_router=mock_memory_router, litellm_base_url="http://test-litellm:4000"
    )


@pytest.fixture
def app_without_router(with_litellm_auth):
    """Create FastAPI app without MemoryRouter (disabled memory routing)."""
    return create_app(litellm_auth_token=with_litellm_auth, memory_router=None, litellm_base_url="http://test-litellm:4000")


@pytest.fixture
def client_with_router(app_with_router):
    """Create test client with memory routing enabled."""
    return TestClient(app_with_router)


@pytest.fixture
def client_without_router(app_without_router):
    """Create test client with memory routing disabled."""
    return TestClient(app_without_router)


class TestAppCreation:
    """Test the factory function and app creation."""

    def test_create_app_with_router(self, with_litellm_auth, mock_memory_router):
        """Test app creation with MemoryRouter."""
        app = create_app(
            litellm_auth_token=with_litellm_auth,
            memory_router=mock_memory_router,
            litellm_base_url="http://custom-litellm:5000",
        )

        assert app.title == "LiteLLM Proxy with Memory Routing"
        # Check instance attributes (state is set in lifespan which runs with TestClient)
        assert app.memory_router == mock_memory_router
        assert app.litellm_base_url == "http://custom-litellm:5000"
        assert app.litellm_auth_token == with_litellm_auth

    def test_create_app_without_router(self, with_litellm_auth):
        """Test app creation without MemoryRouter."""
        app = create_app(litellm_auth_token=with_litellm_auth, memory_router=None, litellm_base_url="http://localhost:4000")

        assert app.title == "LiteLLM Proxy with Memory Routing"
        # When None is passed, memory_router stays None (no default created)
        assert app.memory_router is None
        assert app.litellm_base_url == "http://localhost:4000"

    def test_create_multiple_app_instances(self, with_litellm_auth, mock_memory_router):
        """Test that multiple app instances can be created independently."""
        app1 = create_app(
            litellm_auth_token=with_litellm_auth,
            memory_router=mock_memory_router, litellm_base_url="http://litellm1:4000"
        )
        app2 = create_app(litellm_auth_token=with_litellm_auth, memory_router=None, litellm_base_url="http://litellm2:5000")

        # Each app has independent configuration
        assert app1.memory_router == mock_memory_router
        assert app2.memory_router is None  # None stays None (no default router)
        assert app1.litellm_base_url == "http://litellm1:4000"
        assert app2.litellm_base_url == "http://litellm2:5000"


class TestDependencyInjection:
    """Test dependency injection functions."""

    def test_get_memory_router_with_router(self, client_with_router):
        """Test dependency injection retrieves MemoryRouter from app state."""
        with client_with_router as c:
            response = c.get("/health")
            assert response.status_code == 200
            data = response.json()
            assert data["memory_router"] is True
            assert data["litellm_base_url"] == "http://test-litellm:4000"

    def test_get_memory_router_without_router(self, client_without_router):
        """Test dependency injection when MemoryRouter is not initialized."""
        with client_without_router as c:
            response = c.get("/health")
            assert response.status_code == 200
            data = response.json()
            # When None is passed, memory_router stays None
            assert data["memory_router"] is False
            assert data["litellm_base_url"] == "http://test-litellm:4000"


class TestHealthEndpoint:
    """Test the health check endpoint."""

    def test_health_with_memory_routing(self, client_with_router):
        """Test health endpoint with memory routing enabled."""
        with client_with_router as client:
            response = client.get("/health")
            assert response.status_code == 200

            data = response.json()
            assert data["status"] == "healthy"
            assert data["memory_router"] is True
            assert data["litellm_base_url"] == "http://test-litellm:4000"

    def test_health_without_memory_routing(self, client_without_router):
        """Test health endpoint without memory router."""
        with client_without_router as client:
            response = client.get("/health")
            assert response.status_code == 200

            data = response.json()
            assert data["status"] == "healthy"
            # When None is passed, memory_router stays None
            assert data["memory_router"] is False
            assert data["litellm_base_url"] == "http://test-litellm:4000"


class TestMemoryRoutingInfoEndpoint:
    """Test the memory routing info debug endpoint."""

    def test_routing_info_with_router(self, client_with_router, mock_memory_router):
        """Test routing info endpoint with memory routing enabled."""
        with client_with_router as client:
            response = client.get(
                "/memory-routing/info", headers={"User-Agent": "PyCharm"}
            )
            assert response.status_code == 200

            data = response.json()
            # API returns nested structure: {"routing": {...}, "request_headers": {...}}
            assert "routing" in data
            routing = data["routing"]
            assert "user_id" in routing
            assert routing["user_id"] == "test-user"
            assert "matched_pattern" in routing

            # Verify the mock was called
            mock_memory_router.get_routing_info.assert_called_once()

    def test_routing_info_without_router(self, client_without_router):
        """Test routing info endpoint when router is not initialized."""
        with client_without_router as client:
            response = client.get(
                "/memory-routing/info", headers={"User-Agent": "PyCharm"}
            )
            assert response.status_code == 200

            data = response.json()
            # Should return error when router is not initialized
            assert "error" in data
            assert "not initialized" in data["error"]


class TestProxyHandler:
    """Test the main proxy handler with various scenarios."""

    @patch("proxy.litellm_proxy_with_memory.proxy_request")
    async def test_proxy_handler_non_chat_endpoint(
        self, mock_proxy_request, client_with_router, mock_httpx_client
    ):
        """Test proxying a non-chat endpoint (no memory routing applied)."""
        mock_proxy_request.return_value = (
            200,
            {"content-type": "application/json"},
            b'{"status": "ok"}',
        )

        with client_with_router as client:
            response = client.get("/v1/models")
            assert response.status_code == 200

    @patch("proxy.litellm_proxy_with_memory.proxy_request")
    @patch.dict("os.environ", {"SUPERMEMORY_API_KEY": "test-sm-key"})
    async def test_proxy_handler_chat_with_memory_routing(
        self, mock_proxy_request, client_with_router, mock_memory_router, mock_httpx_client
    ):
        """Test chat completions with memory routing enabled."""
        mock_proxy_request.return_value = (
            200,
            {"content-type": "application/json"},
            b'{"choices": [{"message": {"content": "Hello"}}]}',
        )

        request_body = {
            "model": "gpt-4-with-memory",
            "messages": [{"role": "user", "content": "Hello"}],
        }

        with client_with_router as client:
            response = client.post(
                "/v1/chat/completions",
                json=request_body,
                headers={"Authorization": "Bearer test-key"},
            )

            assert response.status_code == 200

            # Verify memory routing was applied
            mock_memory_router.should_use_supermemory.assert_called_with(
                "gpt-4-with-memory"
            )
            mock_memory_router.get_routing_info.assert_called()
            mock_memory_router.inject_memory_headers.assert_called()

    @patch("proxy.litellm_proxy_with_memory.proxy_request")
    async def test_proxy_handler_chat_without_memory_routing(
        self, mock_proxy_request, client_without_router, mock_httpx_client
    ):
        """Test chat completions with memory routing disabled."""
        mock_proxy_request.return_value = (
            200,
            {"content-type": "application/json"},
            b'{"choices": [{"message": {"content": "Hello"}}]}',
        )

        request_body = {
            "model": "gpt-4",
            "messages": [{"role": "user", "content": "Hello"}],
        }

        with client_without_router as client:
            response = client.post(
                "/v1/chat/completions",
                json=request_body,
                headers={"Authorization": "Bearer test-key"},
            )

            assert response.status_code == 200


class TestNoGlobalState:
    """Test that no global state is used."""

    def test_multiple_clients_independent_state(self, with_litellm_auth, mock_memory_router):
        """Test that multiple clients have independent state."""
        # Create two apps with different configurations
        app1 = create_app(
            litellm_auth_token=with_litellm_auth,
            memory_router=mock_memory_router, litellm_base_url="http://litellm1:4000"
        )
        app2 = create_app(litellm_auth_token=with_litellm_auth, memory_router=None, litellm_base_url="http://litellm2:5000")

        with TestClient(app1) as client1, TestClient(app2) as client2:
            # Check that each client has independent state
            response1 = client1.get("/health")
            response2 = client2.get("/health")

            data1 = response1.json()
            data2 = response2.json()

            assert data1["memory_router"] is True
            assert data2["memory_router"] is False  # None stays None (no default router)
            assert data1["litellm_base_url"] == "http://litellm1:4000"
            assert data2["litellm_base_url"] == "http://litellm2:5000"

    def test_app_state_isolated_from_module_globals(self, with_litellm_auth):
        """Test that app state is isolated and doesn't leak to module level."""
        from proxy import litellm_proxy_with_memory

        # Check that no global memory_router variable exists
        assert not hasattr(litellm_proxy_with_memory, "memory_router")

        # Create an app
        app = create_app(litellm_auth_token=with_litellm_auth, memory_router=MagicMock(), litellm_base_url="http://test:4000")

        # Still no global variable should exist
        assert not hasattr(litellm_proxy_with_memory, "memory_router")

        # Configuration is stored as instance attributes
        assert hasattr(app, "memory_router")
        assert app.memory_router is not None


class TestIntegration:
    """Integration tests for the complete flow."""

    @patch("proxy.litellm_proxy_with_memory.proxy_request")
    @patch.dict("os.environ", {"SUPERMEMORY_API_KEY": "test-sm-key"})
    async def test_full_chat_completion_flow(
        self, mock_proxy_request, client_with_router, mock_memory_router, mock_httpx_client
    ):
        """Test the complete flow from request to response with memory routing."""
        # Setup mock response
        mock_proxy_request.return_value = (
            200,
            {"content-type": "application/json"},
            json.dumps(
                {
                    "id": "chatcmpl-123",
                    "choices": [{"message": {"content": "Hello from memory!"}}],
                }
            ).encode(),
        )

        # Make request
        request_body = {
            "model": "gpt-4-with-memory",
            "messages": [{"role": "user", "content": "Tell me about my past"}],
        }

        with client_with_router as client:
            response = client.post(
                "/v1/chat/completions",
                json=request_body,
                headers={
                    "Authorization": "Bearer test-key",
                    "User-Agent": "PyCharm",
                },
            )

            # Verify response
            assert response.status_code == 200
            data = response.json()
            assert "choices" in data
            assert data["choices"][0]["message"]["content"] == "Hello from memory!"

            # Verify memory routing was triggered
            mock_memory_router.should_use_supermemory.assert_called_once()
            mock_memory_router.get_routing_info.assert_called_once()
            mock_memory_router.inject_memory_headers.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
