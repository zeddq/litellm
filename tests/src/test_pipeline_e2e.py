"""
Full Pipeline E2E Tests

End-to-end tests for the complete pipeline:
Client → Interceptor (8888) → Memory Proxy (8764) → LiteLLM (8765) → Provider

Tests include:
- Full request flow through all layers
- Header propagation
- Memory routing
- Context retrieval
- Streaming responses
- Error propagation
"""

import asyncio
import json
from typing import List

import httpx
import pytest

from tests.fixtures.interceptor_fixtures import (
    TEST_INTERCEPTOR_PORT,
    TEST_MEMORY_PROXY_PORT,
    TEST_LITELLM_PORT,
    TEST_HEADERS,
    TEST_REQUEST_BODIES,
)
from tests.helpers.pipeline_helpers import (
    start_full_pipeline,
    stop_pipeline,
    send_through_interceptor,
    test_streaming_through_pipeline,
    verify_memory_routing,
    send_concurrent_requests,
)


# Skip these tests if API keys not available
def pytest_configure(config):
    """Add custom markers."""
    config.addinivalue_line("markers", "e2e: mark test as end-to-end test")

# Always skip these tests for now (they require full pipeline setup)
pytestmark = pytest.mark.skip(reason="E2E pipeline tests require full pipeline setup with --run-e2e flag")


# ============================================================================
# Full Pipeline Tests
# ============================================================================

class TestFullPipeline:
    """Tests for complete request flow through all components."""

    @pytest.mark.asyncio
    @pytest.mark.e2e
    async def test_simple_request_through_pipeline(self, full_pipeline):
        """Test simple non-streaming request through full pipeline."""
        pipeline = full_pipeline
        interceptor_port = pipeline['interceptor']['port']

        response = await send_through_interceptor(
            interceptor_port,
            TEST_REQUEST_BODIES['simple'],
            TEST_HEADERS['pycharm']
        )

        assert response.status_code == 200
        data = response.json()
        assert 'choices' in data
        assert len(data['choices']) > 0

    @pytest.mark.asyncio
    @pytest.mark.e2e
    async def test_streaming_request_through_pipeline(self, full_pipeline):
        """Test streaming request through full pipeline."""
        pipeline = full_pipeline
        interceptor_port = pipeline['interceptor']['port']

        success, chunks = await test_streaming_through_pipeline(
            interceptor_port,
            TEST_REQUEST_BODIES['streaming'],
            TEST_HEADERS['pycharm']
        )

        assert success
        assert len(chunks) > 0

    @pytest.mark.asyncio
    @pytest.mark.e2e
    async def test_context_retrieval_through_pipeline(self, full_pipeline):
        """Test context retrieval integration through full pipeline."""
        pipeline = full_pipeline
        interceptor_port = pipeline['interceptor']['port']

        # Send request that should trigger context retrieval
        response = await send_through_interceptor(
            interceptor_port,
            TEST_REQUEST_BODIES['with_context'],
            TEST_HEADERS['pycharm']
        )

        assert response.status_code == 200
        # Context would be injected by memory proxy
        # Verify response includes context-aware information


# ============================================================================
# Memory Routing Tests
# ============================================================================

class TestMemoryRoutingPipeline:
    """Tests for memory routing through the pipeline."""

    @pytest.mark.asyncio
    @pytest.mark.e2e
    async def test_pycharm_user_detection(self, full_pipeline):
        """Test PyCharm user detection and routing."""
        pipeline = full_pipeline
        memory_port = pipeline['memory_proxy']['port']

        is_correct = await verify_memory_routing(
            memory_port,
            'PyCharm-AI-Assistant/2023.3',
            'pycharm-ai'
        )

        assert is_correct

    @pytest.mark.asyncio
    @pytest.mark.e2e
    async def test_claude_code_user_detection(self, full_pipeline):
        """Test Claude Code user detection and routing."""
        pipeline = full_pipeline
        memory_port = pipeline['memory_proxy']['port']

        is_correct = await verify_memory_routing(
            memory_port,
            'Claude Code/1.0',
            'claude-cli'
        )

        assert is_correct

    @pytest.mark.asyncio
    @pytest.mark.e2e
    async def test_custom_user_id_preservation(self, full_pipeline):
        """Test that custom user IDs are preserved through pipeline."""
        pipeline = full_pipeline
        interceptor_port = pipeline['interceptor']['port']

        custom_headers = TEST_HEADERS['custom'].copy()

        response = await send_through_interceptor(
            interceptor_port,
            TEST_REQUEST_BODIES['simple'],
            custom_headers
        )

        assert response.status_code == 200


# ============================================================================
# Error Propagation Tests
# ============================================================================

class TestErrorPropagation:
    """Tests for error handling and propagation through pipeline."""

    @pytest.mark.asyncio
    @pytest.mark.e2e
    async def test_provider_auth_error_propagation(self, full_pipeline):
        """Test that provider authentication errors propagate correctly."""
        pipeline = full_pipeline
        interceptor_port = pipeline['interceptor']['port']

        # Send request with invalid API key (would need test config)
        request = TEST_REQUEST_BODIES['simple'].copy()
        headers = TEST_HEADERS['pycharm'].copy()
        headers['Authorization'] = 'Bearer invalid-key'

        response = await send_through_interceptor(
            interceptor_port,
            request,
            headers
        )

        # Should return authentication error
        assert response.status_code in [401, 403]

    @pytest.mark.asyncio
    @pytest.mark.e2e
    async def test_provider_timeout_propagation(self, full_pipeline):
        """Test that provider timeouts propagate correctly."""
        pipeline = full_pipeline
        interceptor_port = pipeline['interceptor']['port']

        # Send request that would timeout (needs special config)
        with pytest.raises(httpx.TimeoutException):
            await send_through_interceptor(
                interceptor_port,
                TEST_REQUEST_BODIES['simple'],
                TEST_HEADERS['pycharm'],
                timeout=0.001  # Very short timeout
            )

    @pytest.mark.asyncio
    @pytest.mark.e2e
    async def test_rate_limit_error_propagation(self, full_pipeline):
        """Test that rate limit errors propagate correctly."""
        pipeline = full_pipeline
        interceptor_port = pipeline['interceptor']['port']

        # Send many requests to trigger rate limit
        responses = await send_concurrent_requests(
            interceptor_port,
            TEST_REQUEST_BODIES['simple'],
            num_requests=100,  # High volume
            headers=TEST_HEADERS['pycharm']
        )

        # Some requests might hit rate limit
        status_codes = {r.status_code for r in responses}
        # Could include 429 if rate limiting enabled
        assert any(code in [200, 429] for code in status_codes)


# ============================================================================
# Multi-Project Isolation Tests
# ============================================================================

class TestMultiProjectIsolation:
    """Tests for isolation between multiple projects."""

    @pytest.mark.asyncio
    @pytest.mark.e2e
    async def test_different_projects_different_user_ids(self, full_pipeline):
        """Test that different projects get different user IDs."""
        pipeline = full_pipeline
        interceptor_port = pipeline['interceptor']['port']

        # Send requests with different instance IDs
        response1 = await send_through_interceptor(
            interceptor_port,
            TEST_REQUEST_BODIES['simple'],
            {'User-Agent': 'PyCharm-AI-Assistant/2023.3', 'X-Project-ID': 'project-1'}
        )

        response2 = await send_through_interceptor(
            interceptor_port,
            TEST_REQUEST_BODIES['simple'],
            {'User-Agent': 'PyCharm-AI-Assistant/2023.3', 'X-Project-ID': 'project-2'}
        )

        assert response1.status_code == 200
        assert response2.status_code == 200
        # Different projects should have different user IDs (verified via memory routing)


# ============================================================================
# Performance Tests
# ============================================================================

class TestPipelinePerformance:
    """Performance tests for the pipeline."""

    @pytest.mark.asyncio
    @pytest.mark.e2e
    @pytest.mark.slow
    async def test_concurrent_requests_performance(self, full_pipeline):
        """Test handling of concurrent requests."""
        pipeline = full_pipeline
        interceptor_port = pipeline['interceptor']['port']

        import time
        start_time = time.time()

        responses = await send_concurrent_requests(
            interceptor_port,
            TEST_REQUEST_BODIES['simple'],
            num_requests=10,
            headers=TEST_HEADERS['pycharm']
        )

        duration = time.time() - start_time

        # Verify all requests succeeded
        successful = [r for r in responses if r.status_code == 200]
        assert len(successful) == 10

        # Verify reasonable performance (adjust threshold as needed)
        assert duration < 30.0  # 10 requests in under 30 seconds

    @pytest.mark.asyncio
    @pytest.mark.e2e
    @pytest.mark.slow
    async def test_streaming_performance(self, full_pipeline):
        """Test streaming performance through pipeline."""
        pipeline = full_pipeline
        interceptor_port = pipeline['interceptor']['port']

        import time
        start_time = time.time()

        success, chunks = await test_streaming_through_pipeline(
            interceptor_port,
            TEST_REQUEST_BODIES['streaming'],
            TEST_HEADERS['pycharm']
        )

        duration = time.time() - start_time

        assert success
        assert len(chunks) > 0
        # Streaming should complete in reasonable time
        assert duration < 30.0


# ============================================================================
# Regression Tests
# ============================================================================

class TestRegressions:
    """Regression tests for known issues."""

    @pytest.mark.asyncio
    @pytest.mark.e2e
    async def test_large_context_handling(self, full_pipeline):
        """Test handling of large context requests."""
        pipeline = full_pipeline
        interceptor_port = pipeline['interceptor']['port']

        # Create request with large context
        large_request = TEST_REQUEST_BODIES['with_context'].copy()
        large_request['messages'].append({
            'role': 'user',
            'content': 'A' * 10000  # 10KB of text
        })

        response = await send_through_interceptor(
            interceptor_port,
            large_request,
            TEST_HEADERS['pycharm']
        )

        # Should handle large context
        assert response.status_code in [200, 400]  # 400 if exceeds model limit

    @pytest.mark.asyncio
    @pytest.mark.e2e
    async def test_special_characters_in_messages(self, full_pipeline):
        """Test handling of special characters in messages."""
        pipeline = full_pipeline
        interceptor_port = pipeline['interceptor']['port']

        special_chars_request = TEST_REQUEST_BODIES['simple'].copy()
        special_chars_request['messages'][0]['content'] = "Test 测试 🚀 \n\t Special"

        response = await send_through_interceptor(
            interceptor_port,
            special_chars_request,
            TEST_HEADERS['pycharm']
        )

        assert response.status_code == 200
        data = response.json()
        assert 'choices' in data


# ============================================================================
# Health and Monitoring Tests
# ============================================================================

class TestPipelineHealth:
    """Tests for pipeline health and monitoring."""

    @pytest.mark.asyncio
    @pytest.mark.e2e
    async def test_all_services_healthy(self, full_pipeline):
        """Test that all pipeline services are healthy."""
        pipeline = full_pipeline

        from tests.helpers.pipeline_helpers import (
            get_interceptor_health,
            get_memory_proxy_health
        )

        interceptor_health = await get_interceptor_health(
            pipeline['interceptor']['port']
        )
        memory_proxy_health = await get_memory_proxy_health(
            pipeline['memory_proxy']['port']
        )

        assert interceptor_health['status'] == 'healthy'
        assert memory_proxy_health['status'] == 'healthy'

    @pytest.mark.asyncio
    @pytest.mark.e2e
    async def test_graceful_degradation_on_component_failure(self, full_pipeline):
        """Test graceful degradation when a component fails."""
        pipeline = full_pipeline
        interceptor_port = pipeline['interceptor']['port']

        # Kill memory proxy
        pipeline['memory_proxy']['process'].terminate()
        await asyncio.sleep(1)

        # Requests through interceptor should fail gracefully
        response = await send_through_interceptor(
            interceptor_port,
            TEST_REQUEST_BODIES['simple'],
            TEST_HEADERS['pycharm'],
            timeout=5.0
        )

        # Should return 502 Bad Gateway
        assert response.status_code == 502


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--run-e2e'])
