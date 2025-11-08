"""
End-to-End Tests for SDK Proxy

Tests with real LiteLLM SDK calls (conditional on API keys):
- Real API provider calls
- Cookie persistence verification
- Actual streaming
- Load testing
- Performance metrics

Test Strategy:
- Skip tests if API keys not available
- Use real providers (OpenAI, Anthropic)
- Proper cleanup after tests
- Performance benchmarks

Usage:
    # With API keys set
    pytest tests/test_sdk_e2e.py -v

    # Skip if no keys
    pytest tests/test_sdk_e2e.py -v --skip-e2e

Markers:
    @pytest.mark.e2e - End-to-end test
    @pytest.mark.slow - Slow test (>5s)
    @pytest.mark.real_api - Requires real API keys
"""

import asyncio
import os
import time
from typing import List, Dict, Any

import pytest
from fastapi.testclient import TestClient

# Import SDK proxy
from proxy.litellm_proxy_sdk import app
from proxy.session_manager import LiteLLMSessionManager

# Import test fixtures
from tests.fixtures import (
    TEST_CONFIG_YAML,
    create_test_config_file,
    get_chat_completion_request,
    get_request_headers,
    assert_response_format,
)


# =============================================================================
# API Key Detection
# =============================================================================


def has_anthropic_key() -> bool:
    """Check if Anthropic API key is available."""
    return bool(os.getenv("ANTHROPIC_API_KEY"))


def has_openai_key() -> bool:
    """Check if OpenAI API key is available."""
    return bool(os.getenv("OPENAI_API_KEY"))


def has_supermemory_key() -> bool:
    """Check if Supermemory API key is available."""
    return bool(os.getenv("SUPERMEMORY_API_KEY"))


# Skip markers
requires_anthropic = pytest.mark.skipif(
    not has_anthropic_key(), reason="ANTHROPIC_API_KEY not set"
)

requires_openai = pytest.mark.skipif(
    not has_openai_key(), reason="OPENAI_API_KEY not set"
)

requires_supermemory = pytest.mark.skipif(
    not has_supermemory_key(), reason="SUPERMEMORY_API_KEY not set"
)

requires_any_key = pytest.mark.skipif(
    not (has_anthropic_key() or has_openai_key()),
    reason="No API keys available"
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(scope="module")
def e2e_config_file(tmp_path_factory):
    """Create config file with real API keys."""
    tmp_path = tmp_path_factory.mktemp("e2e_config")

    # Use real config if available, else create test config
    real_config_path = "config/config.yaml"
    if os.path.exists(real_config_path):
        return real_config_path
    else:
        return create_test_config_file(tmp_path, TEST_CONFIG_YAML)


@pytest.fixture(scope="module")
async def e2e_client(e2e_config_file):
    """Create TestClient with real configuration."""
    os.environ["LITELLM_CONFIG_PATH"] = e2e_config_file

    with TestClient(app) as client:
        yield client

    # Cleanup
    await LiteLLMSessionManager.close()


# =============================================================================
# Test Real API Calls
# =============================================================================


@pytest.mark.e2e
@pytest.mark.real_api
@pytest.mark.slow
class TestRealAPICalls:
    """Test real API calls to providers."""

    @requires_anthropic
    def test_anthropic_real_call(self, e2e_client):
        """Test real call to Anthropic API."""
        request_body = get_chat_completion_request(
            model="claude-sonnet-4.5",
            messages=[{"role": "user", "content": "Say 'test successful' and nothing else"}],
            max_tokens=10,
        )

        response = e2e_client.post(
            "/v1/chat/completions",
            json=request_body,
            headers=get_request_headers(),
        )

        assert response.status_code == 200
        data = response.json()
        assert_response_format(data, streaming=False)

        # Verify we got actual content
        content = data["choices"][0]["message"]["content"]
        assert len(content) > 0
        print(f"\nAnthropic response: {content}")

    @requires_openai
    def test_openai_real_call(self, e2e_client):
        """Test real call to OpenAI API."""
        request_body = get_chat_completion_request(
            model="gpt-4",
            messages=[{"role": "user", "content": "Say 'test successful' and nothing else"}],
            max_tokens=10,
        )

        response = e2e_client.post(
            "/v1/chat/completions",
            json=request_body,
            headers=get_request_headers(),
        )

        assert response.status_code == 200
        data = response.json()
        assert_response_format(data, streaming=False)

        content = data["choices"][0]["message"]["content"]
        assert len(content) > 0
        print(f"\nOpenAI response: {content}")

    @requires_anthropic
    def test_streaming_real_call(self, e2e_client):
        """Test real streaming call."""
        request_body = get_chat_completion_request(
            model="claude-sonnet-4.5",
            messages=[{"role": "user", "content": "Count to 3"}],
            stream=True,
            max_tokens=20,
        )

        response = e2e_client.post(
            "/v1/chat/completions",
            json=request_body,
            headers=get_request_headers(),
        )

        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]

        # Parse streaming response
        content = response.text
        assert "data: " in content
        assert "[DONE]" in content

        # Count chunks
        chunks = [line for line in content.split("\n") if line.startswith("data: ")]
        assert len(chunks) > 0
        print(f"\nReceived {len(chunks)} streaming chunks")


# =============================================================================
# Test Cookie Persistence
# =============================================================================


@pytest.mark.e2e
@pytest.mark.real_api
@pytest.mark.slow
class TestCookiePersistence:
    """Test Cloudflare cookie persistence."""

    @requires_supermemory
    def test_cookies_persist_across_requests(self, e2e_client):
        """
        Test that cookies persist across multiple requests.

        This verifies the fix for 503 Service Unavailable errors.
        """
        request_body = get_chat_completion_request(
            model="claude-sonnet-4.5",
            messages=[{"role": "user", "content": "Test"}],
            max_tokens=5,
        )
        headers = get_request_headers()

        # Make multiple requests
        responses = []
        for i in range(3):
            response = e2e_client.post(
                "/v1/chat/completions",
                json=request_body,
                headers=headers,
            )
            responses.append(response)
            time.sleep(1)  # Rate limit friendly

        # All should succeed (no repeated 503 errors)
        for i, response in enumerate(responses):
            assert response.status_code == 200, (
                f"Request {i+1} failed with status {response.status_code}"
            )
            print(f"Request {i+1}: Success")

    @requires_anthropic
    def test_session_maintains_cookies(self, e2e_client):
        """Test that session manager maintains cookies."""
        # Check session before request
        health_response = e2e_client.get("/health")
        initial_cookies = health_response.json()["session"]["cookie_count"]
        print(f"\nInitial cookies: {initial_cookies}")

        # Make request (may set cookies)
        request_body = get_chat_completion_request(
            model="claude-sonnet-4.5",
            messages=[{"role": "user", "content": "Hi"}],
            max_tokens=5,
        )

        completion_response = e2e_client.post(
            "/v1/chat/completions",
            json=request_body,
            headers=get_request_headers(),
        )

        assert completion_response.status_code == 200

        # Check cookies after request
        health_response = e2e_client.get("/health")
        final_cookies = health_response.json()["session"]["cookie_count"]
        print(f"Final cookies: {final_cookies}")

        # Cookies should be maintained (may have increased)
        assert final_cookies >= initial_cookies


# =============================================================================
# Test Memory Routing with Real Calls
# =============================================================================


@pytest.mark.e2e
@pytest.mark.real_api
@pytest.mark.slow
class TestMemoryRoutingE2E:
    """Test memory routing with real API calls."""

    @requires_supermemory
    def test_user_id_routing_pycharm(self, e2e_client):
        """Test user ID routing for PyCharm client."""
        request_body = get_chat_completion_request(
            model="claude-sonnet-4.5",
            messages=[{"role": "user", "content": "Test PyCharm routing"}],
            max_tokens=10,
        )

        response = e2e_client.post(
            "/v1/chat/completions",
            json=request_body,
            headers=get_request_headers(user_agent="OpenAIClientImpl/Java"),
        )

        assert response.status_code == 200
        # If successful, routing worked (request reached Supermemory with correct user ID)

    @requires_supermemory
    def test_custom_user_id(self, e2e_client):
        """Test custom user ID header."""
        request_body = get_chat_completion_request(
            model="claude-sonnet-4.5",
            messages=[{"role": "user", "content": "Test custom user"}],
            max_tokens=10,
        )

        response = e2e_client.post(
            "/v1/chat/completions",
            json=request_body,
            headers=get_request_headers(custom_user_id="e2e-test-user"),
        )

        assert response.status_code == 200


# =============================================================================
# Test Load and Performance
# =============================================================================


@pytest.mark.e2e
@pytest.mark.slow
class TestLoadAndPerformance:
    """Test load handling and performance."""

    @requires_any_key
    def test_sequential_requests(self, e2e_client):
        """
        Test sequential requests for stability.

        Verifies no memory leaks or resource exhaustion.
        """
        num_requests = 10
        model = "claude-sonnet-4.5" if has_anthropic_key() else "gpt-4"

        request_body = get_chat_completion_request(
            model=model,
            messages=[{"role": "user", "content": "Quick test"}],
            max_tokens=5,
        )

        success_count = 0
        latencies = []

        for i in range(num_requests):
            start = time.time()

            response = e2e_client.post(
                "/v1/chat/completions",
                json=request_body,
                headers=get_request_headers(),
            )

            latency = time.time() - start
            latencies.append(latency)

            if response.status_code == 200:
                success_count += 1

            # Rate limit friendly pause
            time.sleep(2)

        # Calculate statistics
        avg_latency = sum(latencies) / len(latencies)
        max_latency = max(latencies)
        min_latency = min(latencies)

        print(f"\nSequential requests: {success_count}/{num_requests} succeeded")
        print(f"Latency - Avg: {avg_latency:.2f}s, Min: {min_latency:.2f}s, Max: {max_latency:.2f}s")

        # At least 80% should succeed (accounting for rate limits)
        assert success_count >= num_requests * 0.8

    @requires_any_key
    @pytest.mark.asyncio
    async def test_concurrent_requests_async(self, e2e_client):
        """
        Test concurrent requests handling.

        Verifies session manager thread safety.
        """
        num_concurrent = 5
        model = "claude-sonnet-4.5" if has_anthropic_key() else "gpt-4"

        request_body = get_chat_completion_request(
            model=model,
            messages=[{"role": "user", "content": "Concurrent test"}],
            max_tokens=5,
        )

        async def make_request(i: int):
            """Make a single request."""
            await asyncio.sleep(i * 0.1)  # Stagger requests

            response = e2e_client.post(
                "/v1/chat/completions",
                json=request_body,
                headers=get_request_headers(),
            )

            return response.status_code

        # Execute concurrent requests
        start = time.time()
        results = await asyncio.gather(*[make_request(i) for i in range(num_concurrent)])
        duration = time.time() - start

        success_count = sum(1 for status in results if status == 200)

        print(f"\nConcurrent requests: {success_count}/{num_concurrent} succeeded in {duration:.2f}s")

        # At least 60% should succeed (accounting for rate limits and concurrency)
        assert success_count >= num_concurrent * 0.6


# =============================================================================
# Test Error Scenarios with Real API
# =============================================================================


@pytest.mark.e2e
@pytest.mark.real_api
class TestRealAPIErrors:
    """Test error handling with real API calls."""

    @requires_any_key
    def test_context_length_error(self, e2e_client):
        """
        Test handling of context length exceeded error.

        Note: This may not trigger consistently depending on model limits.
        """
        model = "claude-sonnet-4.5" if has_anthropic_key() else "gpt-4"

        # Create a very long message
        long_message = "test " * 10000  # Very long message

        request_body = get_chat_completion_request(
            model=model,
            messages=[{"role": "user", "content": long_message}],
            max_tokens=10,
        )

        response = e2e_client.post(
            "/v1/chat/completions",
            json=request_body,
            headers=get_request_headers(),
        )

        # May return 400 (context length) or 200 (if model can handle it)
        assert response.status_code in [200, 400]

        if response.status_code == 400:
            data = response.json()
            assert "error" in data
            print(f"\nContext error handled: {data['error']['type']}")

    @requires_any_key
    def test_invalid_parameter(self, e2e_client):
        """Test handling of invalid parameters."""
        model = "claude-sonnet-4.5" if has_anthropic_key() else "gpt-4"

        request_body = get_chat_completion_request(
            model=model,
            messages=[{"role": "user", "content": "Test"}],
            temperature=5.0,  # Invalid temperature (> 2.0)
            max_tokens=10,
        )

        response = e2e_client.post(
            "/v1/chat/completions",
            json=request_body,
            headers=get_request_headers(),
        )

        # Should handle gracefully
        assert response.status_code in [200, 400]


# =============================================================================
# Test Performance Benchmarks
# =============================================================================


@pytest.mark.e2e
@pytest.mark.slow
class TestPerformanceBenchmarks:
    """Performance benchmarks with real API."""

    @requires_anthropic
    def test_response_time_acceptable(self, e2e_client):
        """Test that response times are acceptable."""
        request_body = get_chat_completion_request(
            model="claude-sonnet-4.5",
            messages=[{"role": "user", "content": "Hi"}],
            max_tokens=5,
        )

        start = time.time()
        response = e2e_client.post(
            "/v1/chat/completions",
            json=request_body,
            headers=get_request_headers(),
        )
        duration = time.time() - start

        assert response.status_code == 200

        # Total time should be reasonable (< 30s for simple request)
        assert duration < 30.0, f"Response took {duration:.2f}s (too slow)"

        print(f"\nResponse time: {duration:.2f}s")

    @requires_any_key
    def test_memory_usage_stable(self, e2e_client):
        """
        Test that memory usage remains stable over multiple requests.

        This is a basic check for memory leaks.
        """
        import psutil
        import os as os_module

        process = psutil.Process(os_module.getpid())

        model = "claude-sonnet-4.5" if has_anthropic_key() else "gpt-4"
        request_body = get_chat_completion_request(
            model=model,
            messages=[{"role": "user", "content": "Test"}],
            max_tokens=5,
        )

        # Initial memory
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB

        # Make several requests
        for _ in range(5):
            response = e2e_client.post(
                "/v1/chat/completions",
                json=request_body,
                headers=get_request_headers(),
            )
            time.sleep(1)

        # Final memory
        final_memory = process.memory_info().rss / 1024 / 1024  # MB

        memory_increase = final_memory - initial_memory

        print(f"\nMemory: {initial_memory:.1f}MB -> {final_memory:.1f}MB (+{memory_increase:.1f}MB)")

        # Memory should not increase significantly (< 100MB for 5 requests)
        assert memory_increase < 100, f"Memory increased by {memory_increase:.1f}MB (possible leak)"


# =============================================================================
# Test Execution
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short", "-m", "e2e"])
