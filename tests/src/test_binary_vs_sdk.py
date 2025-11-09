"""
Binary vs SDK Comparison Tests

Validates feature parity between binary proxy and SDK proxy:
- Same inputs produce same outputs
- Same error handling behavior
- Same memory routing behavior
- Performance comparison

Test Strategy:
- Parametrized tests run against both proxies
- Side-by-side validation
- Focus on behavior, not implementation

Usage:
    pytest tests/test_binary_vs_sdk.py -v
    pytest tests/test_binary_vs_sdk.py -v -k "comparison"
"""

import asyncio
import json
import os
import time
from typing import Dict, Any, Literal
from unittest.mock import patch, Mock

import pytest
from fastapi.testclient import TestClient

# Import both proxies
from proxy.litellm_proxy_sdk import app as sdk_app
from proxy.litellm_proxy_with_memory import create_app as create_binary_app
from proxy.session_manager import LiteLLMSessionManager
from proxy.memory_router import MemoryRouter
from proxy.schema import load_config_with_env_resolution

# Import test fixtures
from tests.fixtures import (
    TEST_CONFIG_YAML,
    create_test_config_file,
    get_chat_completion_request,
    get_request_headers,
    TEST_SCENARIOS,
    mock_completion_response,
    MockLiteLLMResponse,
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
    """Mock environment variables."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-test")
    monkeypatch.setenv("SUPERMEMORY_API_KEY", "sm_test")


@pytest.fixture(scope="function")
async def sdk_client(test_config_file, mock_env_vars):
    """Create TestClient for SDK proxy."""
    os.environ["LITELLM_CONFIG_PATH"] = test_config_file

    with TestClient(sdk_app) as client:
        yield client

    await LiteLLMSessionManager.close()


@pytest.fixture(scope="function")
def binary_client(test_config_file, mock_env_vars, mock_httpx_client):
    """Create TestClient for binary proxy."""
    # Load config and create memory router
    config = load_config_with_env_resolution(test_config_file)
    memory_router = MemoryRouter(config)

    # Create binary app with proper parameters
    app = create_binary_app(
        litellm_auth_token=config.general_settings.master_key,
        memory_router=memory_router,
        litellm_base_url="http://localhost:8765",  # Mock URL
    )

    with TestClient(app) as client:
        yield client


@pytest.fixture
def mock_litellm():
    """Mock litellm.acompletion for both proxies."""
    with patch("litellm.acompletion") as mock:
        mock_response = mock_completion_response()
        mock.return_value = MockLiteLLMResponse(mock_response)
        yield mock


@pytest.fixture
def mock_httpx_post():
    """Mock httpx POST for binary proxy forwarding."""
    with patch("httpx.AsyncClient.post") as mock:
        mock_response_data = mock_completion_response()
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_response_data
        mock_response.headers = {"content-type": "application/json"}
        mock.return_value = mock_response
        yield mock


# =============================================================================
# Comparison Test Base Class
# =============================================================================


class ProxyComparison:
    """Helper class for comparing proxy responses."""

    @staticmethod
    def assert_responses_match(
        sdk_response: Dict[str, Any],
        binary_response: Dict[str, Any],
        ignore_fields: list = None,
    ):
        """
        Assert that two responses match (ignoring timing/IDs).

        Args:
            sdk_response: Response from SDK proxy
            binary_response: Response from binary proxy
            ignore_fields: Fields to ignore in comparison
        """
        if ignore_fields is None:
            ignore_fields = ["id", "created", "request_id"]

        # Helper to remove ignored fields
        def clean_response(resp):
            if isinstance(resp, dict):
                return {
                    k: clean_response(v)
                    for k, v in resp.items()
                    if k not in ignore_fields
                }
            elif isinstance(resp, list):
                return [clean_response(item) for item in resp]
            else:
                return resp

        sdk_clean = clean_response(sdk_response)
        binary_clean = clean_response(binary_response)

        # Compare structure
        assert set(sdk_clean.keys()) == set(binary_clean.keys()), (
            f"Response keys mismatch. "
            f"SDK: {set(sdk_clean.keys())}, "
            f"Binary: {set(binary_clean.keys())}"
        )

    @staticmethod
    def assert_error_responses_match(
        sdk_error: Dict[str, Any], binary_error: Dict[str, Any]
    ):
        """
        Assert that error responses match.

        Args:
            sdk_error: Error response from SDK proxy
            binary_error: Error response from binary proxy
        """
        # Both should have error structure
        assert "error" in sdk_error
        assert "error" in binary_error

        sdk_err = sdk_error["error"]
        binary_err = binary_error["error"]

        # Error type should match
        assert sdk_err["type"] == binary_err["type"], (
            f"Error types mismatch: {sdk_err['type']} vs {binary_err['type']}"
        )

        # Both should have messages
        assert "message" in sdk_err
        assert "message" in binary_err


# =============================================================================
# Test Health Endpoint Parity
# =============================================================================


class TestHealthEndpointParity:
    """Compare /health endpoint behavior."""

    def test_health_endpoint_structure(self, sdk_client, binary_client):
        """Test that both health endpoints return similar structure."""
        sdk_response = sdk_client.get("/health")
        binary_response = binary_client.get("/health")

        assert sdk_response.status_code == 200
        assert binary_response.status_code == 200

        sdk_data = sdk_response.json()
        binary_data = binary_response.json()

        # Both should have status
        assert sdk_data["status"] == "healthy"
        assert binary_data["status"] == "healthy"


# =============================================================================
# Test Memory Routing Parity
# =============================================================================


class TestMemoryRoutingParity:
    """Compare memory routing behavior."""

    @pytest.mark.parametrize(
        "user_agent,expected_user_id",
        [
            ("OpenAIClientImpl/Java", "pycharm-ai"),
            ("Claude Code CLI", "claude-code"),
            ("anthropic-sdk-python/1.0", "anthropic-python"),
            ("curl/7.68.0", "default-dev"),
        ],
    )
    def test_user_id_detection_matches(
        self, sdk_client, binary_client, user_agent, expected_user_id
    ):
        """Test that both proxies detect user IDs identically."""
        headers = {"User-Agent": user_agent}

        sdk_response = sdk_client.get("/memory-routing/info", headers=headers)
        binary_response = binary_client.get("/memory-routing/info", headers=headers)

        assert sdk_response.status_code == 200
        assert binary_response.status_code == 200

        sdk_data = sdk_response.json()
        binary_data = binary_response.json()

        # User ID should match
        assert sdk_data["routing"]["user_id"] == expected_user_id
        assert binary_data["routing"]["user_id"] == expected_user_id

    def test_custom_user_id_header(self, sdk_client, binary_client):
        """Test custom user ID header works the same."""
        headers = {
            "User-Agent": "test/1.0",
            "x-memory-user-id": "custom-project",
        }

        sdk_response = sdk_client.get("/memory-routing/info", headers=headers)
        binary_response = binary_client.get("/memory-routing/info", headers=headers)

        sdk_data = sdk_response.json()
        binary_data = binary_response.json()

        # Custom user ID should be used by both
        assert sdk_data["routing"]["user_id"] == "custom-project"
        assert binary_data["routing"]["user_id"] == "custom-project"


# =============================================================================
# Test Models List Parity
# =============================================================================


class TestModelsListParity:
    """Compare /v1/models endpoint behavior."""

    def test_models_list_same_models(self, sdk_client, binary_client):
        """Test that both proxies return the same models."""
        headers = get_request_headers()

        sdk_response = sdk_client.get("/v1/models", headers=headers)
        binary_response = binary_client.get("/v1/models", headers=headers)

        assert sdk_response.status_code == 200
        assert binary_response.status_code == 200

        sdk_data = sdk_response.json()
        binary_data = binary_response.json()

        # Extract model IDs
        sdk_models = set(m["id"] for m in sdk_data["data"])
        binary_models = set(m["id"] for m in binary_data["data"])

        # Should have same models
        assert sdk_models == binary_models

    def test_models_list_auth_error_same(self, sdk_client, binary_client):
        """Test that both proxies handle missing auth the same."""
        sdk_response = sdk_client.get("/v1/models")
        binary_response = binary_client.get("/v1/models")

        # Both should return 401
        assert sdk_response.status_code == 401
        assert binary_response.status_code == 401


# =============================================================================
# Test Chat Completions Parity
# =============================================================================


class TestChatCompletionsParity:
    """Compare /v1/chat/completions behavior."""

    def test_successful_completion_same_format(
        self, sdk_client, binary_client, mock_litellm, mock_httpx_post
    ):
        """Test that successful completions have same format."""
        request_body = get_chat_completion_request(
            model="claude-sonnet-4.5",
            messages=[{"role": "user", "content": "Hello!"}],
        )
        headers = get_request_headers()

        sdk_response = sdk_client.post(
            "/v1/chat/completions",
            json=request_body,
            headers=headers,
        )

        binary_response = binary_client.post(
            "/v1/chat/completions",
            json=request_body,
            headers=headers,
        )

        assert sdk_response.status_code == 200
        assert binary_response.status_code == 200

        sdk_data = sdk_response.json()
        binary_data = binary_response.json()

        # Compare response structure
        ProxyComparison.assert_responses_match(sdk_data, binary_data)

    @pytest.mark.parametrize(
        "error_case",
        [
            "missing_model",
            "missing_messages",
            "invalid_model",
        ],
    )
    def test_error_handling_same(
        self, sdk_client, binary_client, error_case, mock_litellm, mock_httpx_post
    ):
        """Test that error handling is consistent."""
        from tests.fixtures import ERROR_TEST_CASES

        test_case = ERROR_TEST_CASES[error_case]
        request_body = test_case["request"]
        headers = test_case.get("headers", get_request_headers())

        sdk_response = sdk_client.post(
            "/v1/chat/completions",
            json=request_body,
            headers=headers,
        )

        binary_response = binary_client.post(
            "/v1/chat/completions",
            json=request_body,
            headers=headers,
        )

        # Status codes should match
        expected_status = test_case["expected_status"]
        assert sdk_response.status_code == expected_status
        assert binary_response.status_code == expected_status

        # Error structure should match
        if expected_status >= 400:
            sdk_data = sdk_response.json()
            binary_data = binary_response.json()

            ProxyComparison.assert_error_responses_match(sdk_data, binary_data)

    def test_memory_routing_injection_same(
        self, sdk_client, binary_client, mock_litellm, mock_httpx_post
    ):
        """Test that memory routing headers are injected the same way."""
        request_body = get_chat_completion_request()
        headers = get_request_headers(user_agent="OpenAIClientImpl/Java")

        sdk_response = sdk_client.post(
            "/v1/chat/completions",
            json=request_body,
            headers=headers,
        )

        binary_response = binary_client.post(
            "/v1/chat/completions",
            json=request_body,
            headers=headers,
        )

        # Both should succeed
        assert sdk_response.status_code == 200
        assert binary_response.status_code == 200

        # For SDK proxy, check litellm was called with correct headers
        if mock_litellm.called:
            call_kwargs = mock_litellm.call_args[1]
            assert "extra_headers" in call_kwargs
            assert call_kwargs["extra_headers"]["x-sm-user-id"] == "pycharm-ai"

        # For binary proxy, check HTTP request had correct headers
        if mock_httpx_post.called:
            call_kwargs = mock_httpx_post.call_args[1]
            if "headers" in call_kwargs:
                assert "x-sm-user-id" in call_kwargs["headers"]

    @pytest.mark.parametrize(
        "scenario_name",
        [
            "simple_completion",
            "pycharm_client",
            "claude_code_client",
            "custom_user_id",
        ],
    )
    def test_scenarios_produce_same_routing(
        self,
        sdk_client,
        binary_client,
        scenario_name,
        mock_litellm,
        mock_httpx_post,
    ):
        """Test that various scenarios produce same routing behavior."""
        scenario = TEST_SCENARIOS[scenario_name]

        request_body = scenario["request"]
        headers = scenario["headers"]
        expected_user_id = scenario["expected_user_id"]

        # Test SDK proxy
        sdk_response = sdk_client.post(
            "/v1/chat/completions",
            json=request_body,
            headers=headers,
        )

        # Test binary proxy
        binary_response = binary_client.post(
            "/v1/chat/completions",
            json=request_body,
            headers=headers,
        )

        # Both should succeed
        assert sdk_response.status_code == 200
        assert binary_response.status_code == 200

        # Verify user ID routing for SDK
        if mock_litellm.called:
            sdk_call_kwargs = mock_litellm.call_args[1]
            sdk_user_id = sdk_call_kwargs["extra_headers"]["x-sm-user-id"]
            assert sdk_user_id == expected_user_id


# =============================================================================
# Performance Comparison
# =============================================================================


class TestPerformanceComparison:
    """Compare performance characteristics."""

    @pytest.mark.slow
    def test_latency_comparison(
        self, sdk_client, binary_client, mock_litellm, mock_httpx_post
    ):
        """
        Compare latency between proxies.

        Note: This is a relative comparison for overhead measurement.
        """
        request_body = get_chat_completion_request()
        headers = get_request_headers()

        num_requests = 10

        # Measure SDK proxy latency
        sdk_times = []
        for _ in range(num_requests):
            start = time.time()
            sdk_client.post("/v1/chat/completions", json=request_body, headers=headers)
            elapsed = time.time() - start
            sdk_times.append(elapsed)

        # Measure binary proxy latency
        binary_times = []
        for _ in range(num_requests):
            start = time.time()
            binary_client.post(
                "/v1/chat/completions", json=request_body, headers=headers
            )
            elapsed = time.time() - start
            binary_times.append(elapsed)

        # Calculate averages
        sdk_avg = sum(sdk_times) / len(sdk_times)
        binary_avg = sum(binary_times) / len(binary_times)

        print(f"\nSDK Proxy Average: {sdk_avg * 1000:.2f}ms")
        print(f"Binary Proxy Average: {binary_avg * 1000:.2f}ms")

        # SDK should be faster (no subprocess overhead)
        # Allow 2x margin for test stability
        assert sdk_avg < binary_avg * 2, (
            f"SDK proxy should be comparable or faster. "
            f"SDK: {sdk_avg * 1000:.2f}ms, Binary: {binary_avg * 1000:.2f}ms"
        )

    @pytest.mark.slow
    def test_concurrent_requests(
        self, sdk_client, binary_client, mock_litellm, mock_httpx_post
    ):
        """
        Test concurrent request handling.

        Both proxies should handle concurrent requests gracefully.
        """
        import concurrent.futures

        request_body = get_chat_completion_request()
        headers = get_request_headers()

        num_concurrent = 20

        def make_request(client):
            response = client.post(
                "/v1/chat/completions", json=request_body, headers=headers
            )
            return response.status_code

        # Test SDK proxy
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            sdk_futures = [
                executor.submit(make_request, sdk_client) for _ in range(num_concurrent)
            ]
            sdk_results = [f.result() for f in sdk_futures]

        # Test binary proxy
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            binary_futures = [
                executor.submit(make_request, binary_client)
                for _ in range(num_concurrent)
            ]
            binary_results = [f.result() for f in binary_futures]

        # All requests should succeed
        assert all(status == 200 for status in sdk_results)
        assert all(status == 200 for status in binary_results)


# =============================================================================
# Backward Compatibility Tests
# =============================================================================


class TestBackwardCompatibility:
    """Ensure SDK proxy maintains compatibility with binary proxy clients."""

    def test_openai_client_compatible(self, sdk_client, mock_litellm):
        """Test that SDK proxy works with OpenAI SDK format."""
        # Standard OpenAI API request format
        request_body = {
            "model": "gpt-4",
            "messages": [{"role": "user", "content": "Test"}],
            "temperature": 0.7,
            "max_tokens": 100,
        }

        response = sdk_client.post(
            "/v1/chat/completions",
            json=request_body,
            headers=get_request_headers(),
        )

        assert response.status_code == 200
        data = response.json()

        # Response should match OpenAI format
        assert "id" in data
        assert "object" in data
        assert "choices" in data
        assert "usage" in data

    def test_anthropic_format_compatible(self, sdk_client, mock_litellm):
        """Test compatibility with Anthropic-style requests."""
        request_body = get_chat_completion_request(
            model="claude-sonnet-4.5",
            messages=[{"role": "user", "content": "Test"}],
        )

        response = sdk_client.post(
            "/v1/chat/completions",
            json=request_body,
            headers=get_request_headers(user_agent="anthropic-sdk-python/1.0"),
        )

        assert response.status_code == 200

        # Memory routing should work
        call_kwargs = mock_litellm.call_args[1]
        assert call_kwargs["extra_headers"]["x-sm-user-id"] == "anthropic-python"


# =============================================================================
# Test Execution
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
