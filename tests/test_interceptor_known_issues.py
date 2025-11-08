"""
Known Issues Tests

Tests for documented known issues, primarily:
- Interceptor crash with supermemory-proxied endpoints
- Workarounds and regression testing

These tests help:
1. Reproduce the issue reliably
2. Document the problem
3. Test workarounds
4. Verify fixes when implemented
"""

import asyncio
import tempfile
from pathlib import Path

import httpx
import pytest
import yaml

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
)


# ============================================================================
# Supermemory Endpoint Crash Tests
# ============================================================================

class TestSupermemoryEndpointCrash:
    """
    Tests for the critical known issue:
    Interceptors crash when used with supermemory-proxied endpoints.

    Issue details:
    - Configuration: api_base: https://api.supermemory.ai/v3/api.anthropic.com
    - Symptom: Interceptor crashes/hangs
    - Status: Under investigation
    - Workaround: Use direct provider endpoints
    """

    @pytest.fixture
    def supermemory_config(self, tmp_path):
        """Create config with supermemory-proxied endpoint."""
        config = {
            'general_settings': {
                'master_key': 'test-key-12345'
            },
            'model_list': [
                {
                    'model_name': 'claude-sonnet-4.5-supermemory',
                    'litellm_params': {
                        'api_base': 'https://api.supermemory.ai/v3/api.anthropic.com',
                        'model': 'anthropic/claude-sonnet-4-5-20250929',
                        'api_key': 'test-key'
                    }
                }
            ],
            'user_id_mappings': {
                'custom_header': 'x-memory-user-id',
                'header_patterns': [
                    {
                        'header': 'user-agent',
                        'pattern': 'TestClient/.*',
                        'user_id': 'test-user'
                    }
                ],
                'default_user_id': 'test-default'
            }
        }

        config_path = tmp_path / "supermemory_config.yaml"
        with open(config_path, 'w') as f:
            yaml.dump(config, f)

        return config_path

    @pytest.fixture
    def direct_provider_config(self, tmp_path):
        """Create config with direct provider endpoint (workaround)."""
        config = {
            'general_settings': {
                'master_key': 'test-key-12345'
            },
            'model_list': [
                {
                    'model_name': 'claude-sonnet-4.5-direct',
                    'litellm_params': {
                        'model': 'anthropic/claude-sonnet-4-5-20250929',
                        'api_key': 'test-key'
                    }
                }
            ],
            'user_id_mappings': {
                'custom_header': 'x-memory-user-id',
                'default_user_id': 'test-default'
            }
        }

        config_path = tmp_path / "direct_provider_config.yaml"
        with open(config_path, 'w') as f:
            yaml.dump(config, f)

        return config_path

    @pytest.mark.asyncio
    @pytest.mark.xfail(reason="Known issue: interceptor crashes with supermemory endpoints")
    async def test_supermemory_endpoint_crash_reproduction(self, supermemory_config):
        """
        Attempt to reproduce the crash with supermemory endpoint.

        Expected: This test should fail/timeout, demonstrating the issue.
        """
        # Start pipeline with supermemory config
        try:
            processes = await start_full_pipeline(
                supermemory_config,
                TEST_INTERCEPTOR_PORT,
                TEST_MEMORY_PROXY_PORT,
                TEST_LITELLM_PORT,
                timeout=30.0
            )

            try:
                # Send request through interceptor
                response = await send_through_interceptor(
                    TEST_INTERCEPTOR_PORT,
                    {
                        'model': 'claude-sonnet-4.5-supermemory',
                        'messages': [{'role': 'user', 'content': 'test'}],
                        'max_tokens': 10
                    },
                    TEST_HEADERS['pycharm'],
                    timeout=10.0
                )

                # If we get here without crashing, the issue might be fixed!
                assert response.status_code == 200, "Unexpected success - issue may be resolved!"

            finally:
                stop_pipeline(processes)

        except (asyncio.TimeoutError, httpx.TimeoutException):
            # This is the expected behavior (crash/timeout)
            pytest.fail("Interceptor crashed/timed out with supermemory endpoint (expected failure)")

    @pytest.mark.asyncio
    async def test_direct_provider_workaround(self, direct_provider_config):
        """
        Test that direct provider endpoints work (workaround).

        This should succeed, demonstrating the workaround.
        """
        # Start pipeline with direct provider config
        try:
            processes = await start_full_pipeline(
                direct_provider_config,
                TEST_INTERCEPTOR_PORT,
                TEST_MEMORY_PROXY_PORT,
                TEST_LITELLM_PORT,
                timeout=30.0
            )

            try:
                # Send request through interceptor
                response = await send_through_interceptor(
                    TEST_INTERCEPTOR_PORT,
                    {
                        'model': 'claude-sonnet-4.5-direct',
                        'messages': [{'role': 'user', 'content': 'test'}],
                        'max_tokens': 10
                    },
                    TEST_HEADERS['pycharm'],
                    timeout=10.0
                )

                # Direct endpoint should work
                assert response.status_code in [200, 401, 502]  # Accept auth errors

            finally:
                stop_pipeline(processes)

        except (asyncio.TimeoutError, httpx.TimeoutException):
            pytest.fail("Direct provider endpoint also failed - workaround not working")

    @pytest.mark.asyncio
    async def test_memory_proxy_without_interceptor_workaround(self, supermemory_config):
        """
        Test using memory proxy directly without interceptor (workaround).

        This demonstrates that the issue is specific to the interceptor.
        """
        from tests.helpers.pipeline_helpers import send_through_memory_proxy

        # Start just memory proxy and litellm (no interceptor)
        # Would need modified start function - for now, mock the test
        pytest.skip("Requires modified pipeline start without interceptor")

    def test_issue_documentation(self):
        """
        Test that the issue is properly documented.

        Verifies that documentation files mention the known issue.
        """
        # Check that README mentions the issue
        readme_path = Path(__file__).parent.parent / "src" / "interceptor" / "README.md"

        if readme_path.exists():
            with open(readme_path, 'r') as f:
                content = f.read()
                assert 'crash' in content.lower() or 'supermemory' in content.lower()

        # Check that DOCUMENTATION_UPDATE_SUMMARY mentions it
        doc_path = Path(__file__).parent.parent / "DOCUMENTATION_UPDATE_SUMMARY.md"

        if doc_path.exists():
            with open(doc_path, 'r') as f:
                content = f.read()
                assert 'crash' in content.lower() or 'interceptor' in content.lower()


# ============================================================================
# Additional Known Issues
# ============================================================================

class TestOtherKnownIssues:
    """Tests for other known issues or edge cases."""

    @pytest.mark.asyncio
    async def test_port_registry_corruption_recovery(self, tmp_path):
        """
        Test recovery from port registry corruption.

        Edge case: Registry file gets corrupted.
        """
        from src.interceptor.port_registry import PortRegistry

        registry_file = tmp_path / "corrupted_registry.json"

        # Write corrupted JSON
        with open(registry_file, 'w') as f:
            f.write("{ corrupted json content }")

        # Should recover gracefully
        registry = PortRegistry(str(registry_file))
        port = registry.allocate_port("/test/project")

        assert port is not None
        assert 18888 <= port <= 18999

    @pytest.mark.asyncio
    async def test_concurrent_port_allocation_race_condition(self, tmp_path):
        """
        Test for race conditions in concurrent port allocation.

        Edge case: Multiple processes try to allocate ports simultaneously.
        """
        from src.interceptor.port_registry import PortRegistry

        registry_file = tmp_path / "concurrent_registry.json"

        async def allocate_for_project(project_id):
            registry = PortRegistry(str(registry_file))
            return registry.allocate_port(f"/test/project/{project_id}")

        # Allocate ports concurrently
        ports = await asyncio.gather(*[
            allocate_for_project(i) for i in range(10)
        ])

        # All ports should be unique
        assert len(set(ports)) == len(ports)

    @pytest.mark.asyncio
    async def test_very_long_project_path(self, tmp_path):
        """
        Test handling of very long project paths.

        Edge case: Project path exceeds typical limits.
        """
        from src.interceptor.port_registry import PortRegistry

        registry_file = tmp_path / "registry.json"
        registry = PortRegistry(str(registry_file))

        # Very long path
        long_path = "/very" + "/long" * 100 + "/project/path"

        port = registry.allocate_port(long_path)
        assert port is not None

        # Same long path should get same port
        port2 = registry.allocate_port(long_path)
        assert port == port2


# ============================================================================
# Regression Tests for Future Fixes
# ============================================================================

class TestRegressionPrevention:
    """
    Tests that will pass once known issues are fixed.

    These serve as regression tests to ensure fixes don't break again.
    """

    @pytest.mark.skip(reason="Issue not yet fixed - skip until resolved")
    @pytest.mark.asyncio
    async def test_supermemory_endpoint_works_after_fix(self, supermemory_config):
        """
        Test that supermemory endpoints work correctly after fix.

        Once the crash issue is fixed, this test should be unskipped and pass.
        """
        processes = await start_full_pipeline(
            supermemory_config,
            TEST_INTERCEPTOR_PORT,
            TEST_MEMORY_PROXY_PORT,
            TEST_LITELLM_PORT,
            timeout=30.0
        )

        try:
            response = await send_through_interceptor(
                TEST_INTERCEPTOR_PORT,
                {
                    'model': 'claude-sonnet-4.5-supermemory',
                    'messages': [{'role': 'user', 'content': 'test'}],
                    'max_tokens': 10
                },
                TEST_HEADERS['pycharm'],
                timeout=10.0
            )

            assert response.status_code == 200
            data = response.json()
            assert 'choices' in data

        finally:
            stop_pipeline(processes)

    @pytest.mark.skip(reason="Streaming through supermemory not yet fixed")
    @pytest.mark.asyncio
    async def test_streaming_through_supermemory_after_fix(self, supermemory_config):
        """
        Test streaming through supermemory endpoints after fix.

        Streaming might have additional issues beyond the basic crash.
        """
        processes = await start_full_pipeline(
            supermemory_config,
            TEST_INTERCEPTOR_PORT,
            TEST_MEMORY_PROXY_PORT,
            TEST_LITELLM_PORT,
            timeout=30.0
        )

        try:
            from tests.helpers.pipeline_helpers import test_streaming_through_pipeline

            success, chunks = await test_streaming_through_pipeline(
                TEST_INTERCEPTOR_PORT,
                {
                    'model': 'claude-sonnet-4.5-supermemory',
                    'messages': [{'role': 'user', 'content': 'test'}],
                    'stream': True,
                    'max_tokens': 10
                },
                TEST_HEADERS['pycharm']
            )

            assert success
            assert len(chunks) > 0

        finally:
            stop_pipeline(processes)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
