"""
Interceptor Test Fixtures

Fixtures for testing the interceptor proxy component, including:
- Interceptor server management
- Full pipeline setup (interceptor + memory proxy + LiteLLM)
- Port registry management
- Mock supermemory endpoints
"""

import asyncio
import json
import os
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, Optional, Tuple
from unittest.mock import patch

import httpx
import pytest
import yaml

# Test ports (avoid conflicts with dev instances)
TEST_INTERCEPTOR_PORT = 18888
TEST_MEMORY_PROXY_PORT = 18764
TEST_LITELLM_PORT = 18765
TEST_SUPERMEMORY_MOCK_PORT = 18766

# Timeouts
SERVICE_START_TIMEOUT = 10  # seconds
SERVICE_HEALTH_CHECK_INTERVAL = 0.5  # seconds


@pytest.fixture
def temp_port_registry(tmp_path):
    """
    Create temporary port registry for testing.

    Prevents tests from modifying the user's actual registry.
    """
    registry_file = tmp_path / "port_registry.json"
    registry_data = {
        "version": "1.0",
        "port_range": {"start": 18888, "end": 18999},
        "mappings": {},
        "next_available": 18888
    }

    with open(registry_file, 'w') as f:
        json.dump(registry_data, f)

    # Patch the registry path
    with patch.dict(os.environ, {'PORT_REGISTRY_PATH': str(registry_file)}):
        yield registry_file


@pytest.fixture
def cleanup_port_registry(temp_port_registry):
    """
    Clean up test port allocations after each test.
    """
    yield
    # Cleanup happens via temp_port_registry tmp_path


@pytest.fixture
async def interceptor_server(temp_port_registry):
    """
    Start interceptor server on test port.

    Returns:
        Tuple[subprocess.Popen, int]: Process and port number
    """
    port = TEST_INTERCEPTOR_PORT

    # Start interceptor
    env = os.environ.copy()
    env['INTERCEPTOR_PORT'] = str(port)
    env['MEMORY_PROXY_URL'] = f'http://localhost:{TEST_MEMORY_PROXY_PORT}'
    env['PORT_REGISTRY_PATH'] = str(temp_port_registry)

    process = subprocess.Popen(
        [sys.executable, '-m', 'src.interceptor.cli', 'run'],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    # Wait for server to be ready
    if not await wait_for_service(port, SERVICE_START_TIMEOUT):
        process.kill()
        pytest.fail(f"Interceptor failed to start on port {port}")

    yield process, port

    # Cleanup
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()


@pytest.fixture
async def memory_proxy_server():
    """
    Start memory proxy server on test port.

    Returns:
        Tuple[subprocess.Popen, int]: Process and port number
    """
    port = TEST_MEMORY_PROXY_PORT

    # Create test config
    config_path = create_test_config()

    env = os.environ.copy()
    env['MEMORY_PROXY_PORT'] = str(port)
    env['LITELLM_PROXY_URL'] = f'http://localhost:{TEST_LITELLM_PORT}'

    process = subprocess.Popen(
        [sys.executable, '-m', 'uvicorn', 'proxy.litellm_proxy_sdk:app', '--port', str(port)],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    # Wait for server to be ready
    if not await wait_for_service(port, SERVICE_START_TIMEOUT):
        process.kill()
        pytest.fail(f"Memory proxy failed to start on port {port}")

    yield process, port

    # Cleanup
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()


@pytest.fixture
async def litellm_server():
    """
    Start LiteLLM server on test port.

    Returns:
        Tuple[subprocess.Popen, int]: Process and port number
    """
    port = TEST_LITELLM_PORT

    # Create test config
    config_path = create_test_config()

    process = subprocess.Popen(
        ['litellm', '--config', str(config_path), '--port', str(port)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    # Wait for server to be ready
    if not await wait_for_service(port, SERVICE_START_TIMEOUT):
        process.kill()
        pytest.fail(f"LiteLLM failed to start on port {port}")

    yield process, port

    # Cleanup
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()


@pytest.fixture
async def full_pipeline(interceptor_server, memory_proxy_server, litellm_server):
    """
    Start all components for full pipeline testing.

    Returns:
        Dict with process info and ports for all components
    """
    interceptor_process, interceptor_port = interceptor_server
    memory_process, memory_port = memory_proxy_server
    litellm_process, litellm_port = litellm_server

    pipeline = {
        'interceptor': {'process': interceptor_process, 'port': interceptor_port},
        'memory_proxy': {'process': memory_process, 'port': memory_port},
        'litellm': {'process': litellm_process, 'port': litellm_port},
    }

    # Verify all services are healthy
    for name, info in pipeline.items():
        if not await health_check(info['port']):
            pytest.fail(f"{name} health check failed")

    yield pipeline

    # Cleanup handled by individual fixtures


@pytest.fixture
def mock_supermemory_endpoint():
    """
    Mock supermemory API endpoint for testing crash scenarios.

    This simulates the behavior that causes interceptor crashes.
    """
    from fastapi import FastAPI
    from fastapi.responses import StreamingResponse
    import uvicorn

    app = FastAPI()

    @app.post("/v3/api.anthropic.com/v1/messages")
    async def mock_anthropic():
        """
        Mock endpoint that simulates supermemory's anthropic proxy.

        This can be configured to return various problematic responses
        to help reproduce and debug the crash issue.
        """
        # TODO: Implement response that causes crash
        return {"error": "Not implemented"}

    # Start server in thread
    port = TEST_SUPERMEMORY_MOCK_PORT
    config = uvicorn.Config(app, host="localhost", port=port, log_level="error")
    server = uvicorn.Server(config)

    import threading
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    # Wait for server to start
    time.sleep(1)

    yield f"http://localhost:{port}"

    # Cleanup
    server.should_exit = True


# Helper functions

async def wait_for_service(port: int, timeout: float) -> bool:
    """
    Wait for service to be ready on given port.

    Args:
        port: Port number to check
        timeout: Maximum time to wait in seconds

    Returns:
        True if service is ready, False otherwise
    """
    start_time = time.time()

    async with httpx.AsyncClient() as client:
        while time.time() - start_time < timeout:
            try:
                response = await client.get(f"http://localhost:{port}/health")
                if response.status_code == 200:
                    return True
            except (httpx.ConnectError, httpx.RemoteProtocolError):
                pass

            await asyncio.sleep(SERVICE_HEALTH_CHECK_INTERVAL)

    return False


async def health_check(port: int) -> bool:
    """
    Perform health check on service.

    Args:
        port: Port number to check

    Returns:
        True if healthy, False otherwise
    """
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"http://localhost:{port}/health", timeout=2.0)
            return response.status_code == 200
    except Exception:
        return False


def create_test_config() -> Path:
    """
    Create test configuration file.

    Returns:
        Path to config file
    """
    config = {
        'general_settings': {
            'master_key': 'test-key-12345'
        },
        'model_list': [
            {
                'model_name': 'test-model',
                'litellm_params': {
                    'model': 'openai/gpt-3.5-turbo',
                    'api_key': 'test-api-key'
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

    # Create temp config file
    fd, path = tempfile.mkstemp(suffix='.yaml', prefix='test_config_')
    with os.fdopen(fd, 'w') as f:
        yaml.dump(config, f)

    return Path(path)


@contextmanager
def interceptor_env_override(port: Optional[int] = None,
                             memory_proxy_url: Optional[str] = None):
    """
    Context manager to temporarily override interceptor environment variables.

    Args:
        port: Custom interceptor port
        memory_proxy_url: Custom memory proxy URL
    """
    old_env = {}

    if port is not None:
        old_env['INTERCEPTOR_PORT'] = os.environ.get('INTERCEPTOR_PORT')
        os.environ['INTERCEPTOR_PORT'] = str(port)

    if memory_proxy_url is not None:
        old_env['MEMORY_PROXY_URL'] = os.environ.get('MEMORY_PROXY_URL')
        os.environ['MEMORY_PROXY_URL'] = memory_proxy_url

    try:
        yield
    finally:
        # Restore old environment
        for key, value in old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


# Test data constants

TEST_INTERCEPTOR_CONFIG = {
    'port_range': {'start': 18888, 'end': 18999},
    'memory_proxy_url': f'http://localhost:{TEST_MEMORY_PROXY_PORT}',
    'timeout': 30.0,
}

TEST_HEADERS = {
    'pycharm': {
        'User-Agent': 'PyCharm-AI-Assistant/2023.3',
        'Content-Type': 'application/json'
    },
    'claude_code': {
        'User-Agent': 'Claude Code/1.0',
        'Content-Type': 'application/json'
    },
    'custom': {
        'User-Agent': 'CustomClient/1.0',
        'x-memory-user-id': 'custom-user-123'
    }
}

TEST_REQUEST_BODIES = {
    'simple': {
        'model': 'test-model',
        'messages': [{'role': 'user', 'content': 'Hello'}],
        'max_tokens': 10
    },
    'streaming': {
        'model': 'test-model',
        'messages': [{'role': 'user', 'content': 'Hello'}],
        'stream': True,
        'max_tokens': 10
    },
    'with_context': {
        'model': 'test-model',
        'messages': [
            {'role': 'system', 'content': 'You are helpful'},
            {'role': 'user', 'content': 'Hello'}
        ],
        'max_tokens': 10
    }
}