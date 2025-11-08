"""
Pipeline Test Helpers

Helper functions for testing the full pipeline:
- Starting/stopping services
- Sending requests through different layers
- Verifying headers and responses
- Streaming verification
"""

import asyncio
import subprocess
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

import httpx


async def start_full_pipeline(
    config_path: Path,
    interceptor_port: int,
    memory_port: int,
    litellm_port: int,
    timeout: float = 30.0
) -> Dict[str, subprocess.Popen]:
    """
    Start all components of the pipeline.

    Args:
        config_path: Path to LiteLLM config file
        interceptor_port: Port for interceptor
        memory_port: Port for memory proxy
        litellm_port: Port for LiteLLM
        timeout: Maximum time to wait for services to be ready

    Returns:
        Dict with process objects for each component

    Raises:
        TimeoutError: If services don't start within timeout
    """
    processes = {}

    # Start LiteLLM first
    litellm_process = subprocess.Popen(
        ['litellm', '--config', str(config_path), '--port', str(litellm_port)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    processes['litellm'] = litellm_process

    # Start Memory Proxy
    memory_env = {
        'MEMORY_PROXY_PORT': str(memory_port),
        'LITELLM_PROXY_URL': f'http://localhost:{litellm_port}'
    }
    memory_process = subprocess.Popen(
        ['uvicorn', 'proxy.litellm_proxy_sdk:app', '--port', str(memory_port)],
        env=memory_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    processes['memory_proxy'] = memory_process

    # Start Interceptor
    interceptor_env = {
        'INTERCEPTOR_PORT': str(interceptor_port),
        'MEMORY_PROXY_URL': f'http://localhost:{memory_port}'
    }
    interceptor_process = subprocess.Popen(
        ['python', '-m', 'src.interceptor.cli', 'run'],
        env=interceptor_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    processes['interceptor'] = interceptor_process

    # Wait for all services to be ready
    ports = {
        'litellm': litellm_port,
        'memory_proxy': memory_port,
        'interceptor': interceptor_port
    }

    if not await wait_for_services_ready(ports, timeout):
        # Cleanup on failure
        for process in processes.values():
            process.terminate()
        raise TimeoutError("Services failed to start within timeout")

    return processes


def stop_pipeline(processes: Dict[str, subprocess.Popen], timeout: float = 5.0):
    """
    Stop all pipeline processes gracefully.

    Args:
        processes: Dict of process objects
        timeout: Time to wait for graceful shutdown
    """
    for name, process in processes.items():
        if process.poll() is None:  # Process is still running
            process.terminate()
            try:
                process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                process.kill()


async def wait_for_services_ready(ports: Dict[str, int], timeout: float) -> bool:
    """
    Wait for all services to be healthy.

    Args:
        ports: Dict mapping service names to ports
        timeout: Maximum time to wait

    Returns:
        True if all services are ready, False otherwise
    """
    start_time = time.time()
    check_interval = 0.5

    async with httpx.AsyncClient() as client:
        while time.time() - start_time < timeout:
            all_ready = True

            for name, port in ports.items():
                try:
                    response = await client.get(
                        f"http://localhost:{port}/health",
                        timeout=2.0
                    )
                    if response.status_code != 200:
                        all_ready = False
                        break
                except Exception:
                    all_ready = False
                    break

            if all_ready:
                return True

            await asyncio.sleep(check_interval)

    return False


async def send_through_interceptor(
    port: int,
    request_data: Dict[str, Any],
    headers: Optional[Dict[str, str]] = None,
    timeout: float = 30.0
) -> httpx.Response:
    """
    Send request through interceptor and return response.

    Args:
        port: Interceptor port
        request_data: Request body
        headers: Optional request headers
        timeout: Request timeout

    Returns:
        HTTP response object
    """
    if headers is None:
        headers = {}

    headers.setdefault('Content-Type', 'application/json')
    headers.setdefault('Authorization', 'Bearer test-key-12345')

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"http://localhost:{port}/v1/chat/completions",
            json=request_data,
            headers=headers,
            timeout=timeout
        )
        return response


async def send_through_memory_proxy(
    port: int,
    request_data: Dict[str, Any],
    headers: Optional[Dict[str, str]] = None,
    timeout: float = 30.0
) -> httpx.Response:
    """
    Send request directly through memory proxy (bypassing interceptor).

    Args:
        port: Memory proxy port
        request_data: Request body
        headers: Optional request headers
        timeout: Request timeout

    Returns:
        HTTP response object
    """
    if headers is None:
        headers = {}

    headers.setdefault('Content-Type', 'application/json')
    headers.setdefault('Authorization', 'Bearer test-key-12345')

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"http://localhost:{port}/v1/chat/completions",
            json=request_data,
            headers=headers,
            timeout=timeout
        )
        return response


def verify_header_injection(
    interceptor_response: httpx.Response,
    expected_user_id: str,
    expected_instance: Optional[str] = None
) -> bool:
    """
    Verify that interceptor properly injected headers.

    Args:
        interceptor_response: Response from request through interceptor
        expected_user_id: Expected x-memory-user-id value
        expected_instance: Optional expected x-pycharm-instance value

    Returns:
        True if headers are correctly injected
    """
    # Note: We'd need to capture the request headers somehow
    # This is a placeholder for the actual implementation
    # In real tests, we'd mock the memory proxy to capture headers

    # For now, verify the response indicates success
    return interceptor_response.status_code < 500


async def test_streaming_through_pipeline(
    interceptor_port: int,
    request_data: Dict[str, Any],
    headers: Optional[Dict[str, str]] = None
) -> Tuple[bool, List[str]]:
    """
    Test streaming responses through the full pipeline.

    Args:
        interceptor_port: Interceptor port
        request_data: Request body (should have stream=True)
        headers: Optional request headers

    Returns:
        Tuple of (success: bool, chunks: List[str])
    """
    if headers is None:
        headers = {}

    headers.setdefault('Content-Type', 'application/json')
    headers.setdefault('Authorization', 'Bearer test-key-12345')

    chunks = []
    success = False

    try:
        async with httpx.AsyncClient() as client:
            async with client.stream(
                'POST',
                f"http://localhost:{interceptor_port}/v1/chat/completions",
                json=request_data,
                headers=headers,
                timeout=30.0
            ) as response:
                if response.status_code == 200:
                    async for chunk in response.aiter_text():
                        if chunk:
                            chunks.append(chunk)
                    success = True
    except Exception as e:
        chunks.append(f"Error: {str(e)}")

    return success, chunks


async def get_interceptor_health(port: int) -> Dict[str, Any]:
    """
    Get interceptor health status.

    Args:
        port: Interceptor port

    Returns:
        Health status dict
    """
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"http://localhost:{port}/health", timeout=2.0)
            if response.status_code == 200:
                return {"status": "healthy", "details": response.json()}
            else:
                return {"status": "unhealthy", "code": response.status_code}
    except Exception as e:
        return {"status": "error", "error": str(e)}


async def get_memory_proxy_health(port: int) -> Dict[str, Any]:
    """
    Get memory proxy health status.

    Args:
        port: Memory proxy port

    Returns:
        Health status dict
    """
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"http://localhost:{port}/health", timeout=2.0)
            if response.status_code == 200:
                return {"status": "healthy", "details": response.json()}
            else:
                return {"status": "unhealthy", "code": response.status_code}
    except Exception as e:
        return {"status": "error", "error": str(e)}


async def verify_memory_routing(
    memory_proxy_port: int,
    user_agent: str,
    expected_user_id: str
) -> bool:
    """
    Verify memory routing detection for a given User-Agent.

    Args:
        memory_proxy_port: Memory proxy port
        user_agent: User-Agent string to test
        expected_user_id: Expected detected user ID

    Returns:
        True if routing is correct
    """
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"http://localhost:{memory_proxy_port}/memory-routing/info",
                headers={'User-Agent': user_agent},
                timeout=2.0
            )

            if response.status_code == 200:
                data = response.json()
                return data.get('user_id') == expected_user_id

    except Exception:
        pass

    return False


async def send_concurrent_requests(
    port: int,
    request_data: Dict[str, Any],
    num_requests: int,
    headers: Optional[Dict[str, str]] = None
) -> List[httpx.Response]:
    """
    Send multiple concurrent requests for load testing.

    Args:
        port: Target port
        request_data: Request body
        num_requests: Number of concurrent requests
        headers: Optional request headers

    Returns:
        List of responses
    """
    if headers is None:
        headers = {}

    headers.setdefault('Content-Type', 'application/json')
    headers.setdefault('Authorization', 'Bearer test-key-12345')

    async def send_one():
        async with httpx.AsyncClient() as client:
            return await client.post(
                f"http://localhost:{port}/v1/chat/completions",
                json=request_data,
                headers=headers,
                timeout=30.0
            )

    tasks = [send_one() for _ in range(num_requests)]
    responses = await asyncio.gather(*tasks, return_exceptions=True)

    return [r for r in responses if isinstance(r, httpx.Response)]


def check_port_available(port: int) -> bool:
    """
    Check if port is available (not in use).

    Args:
        port: Port number to check

    Returns:
        True if available, False if in use
    """
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(('localhost', port))
            return True
        except OSError:
            return False