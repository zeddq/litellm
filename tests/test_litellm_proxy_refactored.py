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
def mock_memory_router():
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
        "authorization": "Bearer test-key",
        "x-sm-user-id": "test-user",
        "x-supermemory-api-key": "test-sm-key",
    }
    return router


@pytest.fixture
def app_with_router(mock_memory_router):
    """Create FastAPI app with mocked MemoryRouter."""
    return create_app(
        memory_router=mock_memory_router, litellm_base_url="http://test-litellm:4000"
    )


@pytest.fixture
def app_without_router():
    """Create FastAPI app without MemoryRouter (disabled memory routing)."""
    return create_app(memory_router=None, litellm_base_url="http://test-litellm:4000")


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

    def test_create_app_with_router(self, mock_memory_router):
        """Test app creation with MemoryRouter."""
        app = create_app(
            memory_router=mock_memory_router,
            litellm_base_url="http://custom-litellm:5000",
        )

        assert app.title == "LiteLLM Proxy with Memory Routing"
        assert app.state.memory_router == mock_memory_router
        assert app.state.litellm_base_url == "http://custom-litellm:5000"

    def test_create_app_without_router(self):
        """Test app creation without MemoryRouter."""
        app = create_app(memory_router=None, litellm_base_url="http://localhost:4000")

        assert app.title == "LiteLLM Proxy with Memory Routing"
        assert app.state.memory_router is None
        assert app.state.litellm_base_url == "http://localhost:4000"

    def test_create_multiple_app_instances(self, mock_memory_router):
        """Test that multiple app instances can be created independently."""
        app1 = create_app(
            memory_router=mock_memory_router, litellm_base_url="http://litellm1:4000"
        )
        app2 = create_app(memory_router=None, litellm_base_url="http://litellm2:5000")

        # Each app has independent state
        assert app1.state.memory_router == mock_memory_router
        assert app2.state.memory_router is None
        assert app1.state.litellm_base_url == "http://litellm1:4000"
        assert app2.state.litellm_base_url == "http://litellm2:5000"


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
            assert data["memory_router"] is False
            assert data["litellm_base_url"] == "http://test-litellm:4000"


class TestHealthEndpoint:
    """Test the health check endpoint."""

    def test_health_with_memory_routing(self, client_with_router):
        """Test health endpoint with memory routing enabled."""
        response = client_with_router.get("/health")
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "healthy"
        assert data["memory_router"] is True
        assert data["litellm_base_url"] == "http://test-litellm:4000"

    def test_health_without_memory_routing(self, client_without_router):
        """Test health endpoint with memory routing disabled."""
        response = client_without_router.get("/health")
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "healthy"
        assert data["memory_router"] is False
        assert data["litellm_base_url"] == "http://test-litellm:4000"


class TestMemoryRoutingInfoEndpoint:
    """Test the memory routing info debug endpoint."""

    def test_routing_info_with_router(self, client_with_router, mock_memory_router):
        """Test routing info endpoint with memory routing enabled."""
        response = client_with_router.get(
            "/memory-routing/info", headers={"User-Agent": "PyCharm"}
        )
        assert response.status_code == 200

        data = response.json()
        assert "user_id" in data
        assert data["user_id"] == "test-user"
        assert "matched_pattern" in data

        # Verify the mock was called
        mock_memory_router.get_routing_info.assert_called_once()

    def test_routing_info_without_router(self, client_without_router):
        """Test routing info endpoint with memory routing disabled."""
        response = client_without_router.get(
            "/memory-routing/info", headers={"User-Agent": "PyCharm"}
        )
        assert response.status_code == 200

        data = response.json()
        assert data == {"error": "Memory router not initialized"}


class TestProxyHandler:
    """Test the main proxy handler with various scenarios."""

    @patch("litellm_proxy_with_memory.proxy_request")
    async def test_proxy_handler_non_chat_endpoint(
        self, mock_proxy_request, client_with_router
    ):
        """Test proxying a non-chat endpoint (no memory routing applied)."""
        mock_proxy_request.return_value = (
            200,
            {"content-type": "application/json"},
            b'{"status": "ok"}',
        )

        response = client_with_router.get("/v1/models")
        assert response.status_code == 200

    @patch("litellm_proxy_with_memory.proxy_request")
    @patch.dict("os.environ", {"SUPERMEMORY_API_KEY": "test-sm-key"})
    async def test_proxy_handler_chat_with_memory_routing(
        self, mock_proxy_request, client_with_router, mock_memory_router
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

        response = client_with_router.post(
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

    @patch("litellm_proxy_with_memory.proxy_request")
    async def test_proxy_handler_chat_without_memory_routing(
        self, mock_proxy_request, client_without_router
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

        response = client_without_router.post(
            "/v1/chat/completions",
            json=request_body,
            headers={"Authorization": "Bearer test-key"},
        )

        assert response.status_code == 200


class TestNoGlobalState:
    """Test that no global state is used."""

    def test_multiple_clients_independent_state(self, mock_memory_router):
        """Test that multiple clients have independent state."""
        # Create two apps with different configurations
        app1 = create_app(
            memory_router=mock_memory_router, litellm_base_url="http://litellm1:4000"
        )
        app2 = create_app(memory_router=None, litellm_base_url="http://litellm2:5000")

        client1 = TestClient(app1)
        client2 = TestClient(app2)

        # Check that each client has independent state
        response1 = client1.get("/health")
        response2 = client2.get("/health")

        data1 = response1.json()
        data2 = response2.json()

        assert data1["memory_router"] is True
        assert data2["memory_router"] is False
        assert data1["litellm_base_url"] == "http://litellm1:4000"
        assert data2["litellm_base_url"] == "http://litellm2:5000"

    def test_app_state_isolated_from_module_globals(self):
        """Test that app state is isolated and doesn't leak to module level."""
        import litellm_proxy_with_memory

        # Check that no global memory_router variable exists
        assert not hasattr(litellm_proxy_with_memory, "memory_router")

        # Create an app
        app = create_app(memory_router=MagicMock(), litellm_base_url="http://test:4000")

        # Still no global variable should exist
        assert not hasattr(litellm_proxy_with_memory, "memory_router")

        # State is only in app.state
        assert hasattr(app.state, "memory_router")
        assert app.state.memory_router is not None


class TestIntegration:
    """Integration tests for the complete flow."""

    @patch("litellm_proxy_with_memory.proxy_request")
    @patch.dict("os.environ", {"SUPERMEMORY_API_KEY": "test-sm-key"})
    async def test_full_chat_completion_flow(
        self, mock_proxy_request, client_with_router, mock_memory_router
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

        response = client_with_router.post(
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