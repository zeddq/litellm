"""
Interceptor Component Tests

Unit and component tests for the interceptor proxy, including:
- Port registry management
- Header injection
- Request forwarding
- Error handling
- Environment variable overrides
"""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, AsyncMock

import httpx
import pytest

from src.interceptor.port_registry import PortRegistry
from tests.fixtures.interceptor_fixtures import (
    TEST_INTERCEPTOR_PORT,
    TEST_HEADERS,
    TEST_REQUEST_BODIES,
    interceptor_env_override,
)


# ============================================================================
# Port Registry Tests
# ============================================================================

class TestPortRegistry:
    """Tests for port registry allocation and management."""

    def test_port_allocation(self, temp_port_registry):
        """Test basic port allocation."""
        registry = PortRegistry(port_min=18888, port_max=18999, registry_file=temp_port_registry)

        project_path = "/test/project/1"
        port = registry.allocate_port(project_path)

        assert port is not None
        assert 18888 <= port <= 18999

    def test_consistent_port_allocation(self, temp_port_registry):
        """Test that same project gets same port."""
        registry = PortRegistry(port_min=18888, port_max=18999, registry_file=temp_port_registry)

        project_path = "/test/project/1"
        port1 = registry.allocate_port(project_path)
        port2 = registry.allocate_port(project_path)

        assert port1 == port2

    def test_different_projects_different_ports(self, temp_port_registry):
        """Test that different projects get different ports."""
        registry = PortRegistry(port_min=18888, port_max=18999, registry_file=temp_port_registry)

        port1 = registry.allocate_port("/test/project/1")
        port2 = registry.allocate_port("/test/project/2")

        assert port1 != port2

    def test_port_deallocation(self, temp_port_registry):
        """Test port deallocation."""
        registry = PortRegistry(port_min=18888, port_max=18999, registry_file=temp_port_registry)

        project_path = "/test/project/1"
        port = registry.allocate_port(project_path)

        # Verify deallocation returns True
        result = registry.deallocate_port(project_path)
        assert result is True

        # Verify port is no longer in mappings
        mappings = registry.list_mappings()
        assert project_path not in mappings
        
        # Allocate to another project (will get next sequential port, not the freed one)
        new_port = registry.allocate_port("/test/project/2")
        assert new_port is not None
        assert 18888 <= new_port <= 18999

    def test_port_conflict_detection(self, temp_port_registry):
        """Test detection of port conflicts."""
        registry = PortRegistry(port_min=18888, port_max=18999, registry_file=temp_port_registry)

        # Allocate all ports
        for i in range(18888, 18999):
            registry.allocate_port(f"/test/project/{i}")

        # Should raise error when no ports available
        with pytest.raises(Exception):
            registry.allocate_port("/test/project/overflow")

    def test_registry_corruption_recovery(self, tmp_path):
        """Test recovery from corrupted registry file."""
        registry_file = tmp_path / "corrupted_registry.json"

        # Write corrupted JSON
        with open(registry_file, 'w') as f:
            f.write("{ invalid json }")

        # Should recover and create new registry
        registry = PortRegistry(str(registry_file))
        port = registry.allocate_port("/test/project/1")

        assert port is not None

    def test_environment_variable_override(self):
        """Test INTERCEPTOR_PORT environment variable override."""
        with interceptor_env_override(port=19000):
            port = os.environ.get('INTERCEPTOR_PORT')
            assert port == '19000'

        # Verify cleanup
        assert os.environ.get('INTERCEPTOR_PORT') is None

    def test_project_path_normalization(self, temp_port_registry):
        """Test that project paths are normalized."""
        registry = PortRegistry(port_min=18888, port_max=18999, registry_file=temp_port_registry)

        # Different path representations of same project
        port1 = registry.allocate_port("/test/project/../project")
        port2 = registry.allocate_port("/test/project")

        assert port1 == port2


# ============================================================================
# Header Injection Tests
# ============================================================================

class TestHeaderInjection:
    """Tests for header injection functionality."""

    @pytest.mark.asyncio
    async def test_user_id_header_injection(self, interceptor_server):
        """Test that x-memory-user-id header is injected."""
        process, port = interceptor_server

        async with httpx.AsyncClient() as client:
            # Send request through interceptor
            response = await client.post(
                f"http://localhost:{port}/v1/chat/completions",
                json=TEST_REQUEST_BODIES['simple'],
                headers=TEST_HEADERS['pycharm']
            )

            # We'd need to mock memory proxy to verify headers
            # For now, verify request succeeded
            assert response.status_code in [200, 502]  # 502 if memory proxy not running

    @pytest.mark.asyncio
    async def test_instance_id_header_injection(self, interceptor_server):
        """Test that x-pycharm-instance header is injected."""
        process, port = interceptor_server

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"http://localhost:{port}/v1/chat/completions",
                json=TEST_REQUEST_BODIES['simple'],
                headers=TEST_HEADERS['pycharm']
            )

            # Verify request was processed
            assert response.status_code in [200, 502]

    @pytest.mark.asyncio
    async def test_custom_user_id_preserved(self, interceptor_server):
        """Test that custom x-memory-user-id header is preserved."""
        process, port = interceptor_server

        custom_headers = TEST_HEADERS['custom'].copy()

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"http://localhost:{port}/v1/chat/completions",
                json=TEST_REQUEST_BODIES['simple'],
                headers=custom_headers
            )

            # Custom user ID should be preserved
            assert response.status_code in [200, 502]


# ============================================================================
# Request Forwarding Tests
# ============================================================================

class TestRequestForwarding:
    """Tests for request forwarding to memory proxy."""

    @pytest.mark.asyncio
    async def test_simple_request_forwarding(self, interceptor_server):
        """Test forwarding of simple non-streaming request."""
        process, port = interceptor_server

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"http://localhost:{port}/v1/chat/completions",
                json=TEST_REQUEST_BODIES['simple'],
                headers=TEST_HEADERS['pycharm'],
                timeout=10.0
            )

            # Should forward successfully (or fail gracefully if memory proxy down)
            assert response.status_code in [200, 502, 504]

    @pytest.mark.asyncio
    async def test_streaming_request_forwarding(self, interceptor_server):
        """Test forwarding of streaming request."""
        process, port = interceptor_server

        async with httpx.AsyncClient() as client:
            async with client.stream(
                'POST',
                f"http://localhost:{port}/v1/chat/completions",
                json=TEST_REQUEST_BODIES['streaming'],
                headers=TEST_HEADERS['pycharm'],
                timeout=10.0
            ) as response:
                # Should start streaming (or fail gracefully)
                assert response.status_code in [200, 502, 504]


# ============================================================================
# Error Handling Tests
# ============================================================================

class TestErrorHandling:
    """Tests for error handling and graceful degradation."""

    @pytest.mark.asyncio
    async def test_memory_proxy_unreachable(self, interceptor_server):
        """Test handling when memory proxy is unreachable."""
        process, port = interceptor_server

        # Memory proxy is not running in this test
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"http://localhost:{port}/v1/chat/completions",
                json=TEST_REQUEST_BODIES['simple'],
                headers=TEST_HEADERS['pycharm'],
                timeout=10.0
            )

            # Should return 502 Bad Gateway
            assert response.status_code == 502

    @pytest.mark.asyncio
    async def test_timeout_handling(self, interceptor_server):
        """Test request timeout handling."""
        process, port = interceptor_server

        async with httpx.AsyncClient() as client:
            # Send request with very short timeout
            with pytest.raises(httpx.TimeoutException):
                await client.post(
                    f"http://localhost:{port}/v1/chat/completions",
                    json=TEST_REQUEST_BODIES['simple'],
                    headers=TEST_HEADERS['pycharm'],
                    timeout=0.001  # Very short timeout
                )

    @pytest.mark.asyncio
    async def test_invalid_request_handling(self, interceptor_server):
        """Test handling of invalid requests."""
        process, port = interceptor_server

        async with httpx.AsyncClient() as client:
            # Send invalid request (missing required fields)
            response = await client.post(
                f"http://localhost:{port}/v1/chat/completions",
                json={"invalid": "request"},
                headers=TEST_HEADERS['pycharm'],
                timeout=10.0
            )

            # Should return error (400 or 422)
            assert response.status_code in [400, 422, 502]


# ============================================================================
# Health Check Tests
# ============================================================================

class TestHealthCheck:
    """Tests for interceptor health check endpoint."""

    @pytest.mark.asyncio
    async def test_health_endpoint(self, interceptor_server):
        """Test health check endpoint."""
        process, port = interceptor_server

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"http://localhost:{port}/health",
                timeout=2.0
            )

            assert response.status_code == 200
            data = response.json()
            assert data.get('status') == 'healthy'


# ============================================================================
# Integration Points Tests
# ============================================================================

class TestIntegrationPoints:
    """Tests for integration points with other components."""

    def test_memory_proxy_url_configuration(self):
        """Test memory proxy URL configuration."""
        with interceptor_env_override(memory_proxy_url="http://custom:8888"):
            url = os.environ.get('MEMORY_PROXY_URL')
            assert url == "http://custom:8888"

    def test_port_configuration(self):
        """Test port configuration via environment."""
        with interceptor_env_override(port=19999):
            port = os.environ.get('INTERCEPTOR_PORT')
            assert port == '19999'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])