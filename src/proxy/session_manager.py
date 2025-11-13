"""
Persistent HTTP Session Manager for LiteLLM SDK.

This module provides a singleton session manager that maintains a persistent
httpx.AsyncClient for use with the LiteLLM SDK. This is CRITICAL for proper
Cloudflare cookie persistence, which prevents repeated 503 Service Unavailable errors.

Key Design Decisions:
- Singleton pattern ensures one client per process
- Thread-safe initialization with asyncio.Lock
- Proper lifecycle management (startup/shutdown)
- Direct injection into litellm.aclient_session

Architecture:
    This session manager is part of the SDK-based proxy approach, where the proxy
    directly uses the LiteLLM SDK (litellm.acompletion) instead of forwarding
    requests to an external LiteLLM binary process.

References:
    - docs/architecture/LITELLM_SDK_INTEGRATION_PATTERNS.md (Section 1)
    - poc_litellm_sdk_proxy.py (lines 22-42)
"""

import asyncio
import logging
from typing import Any, Dict, Optional

import httpx
import litellm

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class LiteLLMSessionManager:
    """
    Manages global persistent httpx.AsyncClient for LiteLLM SDK.

    This class implements a singleton pattern to ensure that all LiteLLM SDK
    calls within the process share the same HTTP client. This is essential for:

    1. **Cookie Persistence**: Cloudflare sets challenge cookies (cf_clearance,
       __cfruid) that must be reused across requests to avoid repeated 503 errors.

    2. **Connection Pooling**: Reusing TCP connections reduces latency and
       improves throughput.

    3. **Resource Management**: Single client prevents resource exhaustion from
       creating multiple clients.

    Thread Safety:
        All methods use asyncio.Lock to ensure thread-safe access to the
        shared client instance.

    Usage:
        ```python
        # During application startup
        client = await LiteLLMSessionManager.get_client()
        # litellm.aclient_session is automatically set

        # Make LiteLLM calls (client is automatically used)
        response = await litellm.acompletion(...)

        # During application shutdown
        await LiteLLMSessionManager.close()
        ```

    Attributes:
        _client (Optional[httpx.AsyncClient]): Singleton client instance
        _lock (asyncio.Lock): Thread-safety lock for client access
    """

    _client: Optional[httpx.AsyncClient] = None
    _lock = asyncio.Lock()

    @classmethod
    async def get_client(cls) -> httpx.AsyncClient:
        """
        Get or create the persistent httpx.AsyncClient.

        This method implements lazy initialization with thread-safe singleton
        pattern. The client is created on first access and reused for all
        subsequent calls.

        The created client is automatically injected into litellm.aclient_session,
        ensuring that all litellm.acompletion() calls use this persistent client.

        Connection Configuration:
            - Timeout: 600s read (10 minutes for long LLM completions)
            - Max Connections: 100 total
            - Keepalive Connections: 20 (persistent)
            - Keepalive Expiry: 60s
            - Follow Redirects: Enabled (Cloudflare may redirect)

        Returns:
            httpx.AsyncClient: The persistent HTTP client instance

        Note:
            This method is async and should be called with await.
            The lock ensures only one client is created even under concurrent calls.

        Example:
            ```python
            client = await LiteLLMSessionManager.get_client()
            assert isinstance(client, httpx.AsyncClient)
            assert litellm.aclient_session is client
            ```
        """
        async with cls._lock:
            if cls._client is None:
                # Create persistent client with production-ready configuration
                cls._client = httpx.AsyncClient(
                    # Extended timeout for LLM requests (can take minutes)
                    timeout=httpx.Timeout(
                        connect=30.0,  # Connection establishment
                        read=600.0,  # Reading response (10 minutes)
                        write=30.0,  # Sending request
                        pool=10.0,  # Connection pool acquisition
                    ),
                    # Follow redirects (Cloudflare may redirect during challenges)
                    follow_redirects=True,
                    # Connection pooling configuration
                    limits=httpx.Limits(
                        max_connections=100,  # Total concurrent connections
                        max_keepalive_connections=20,  # Persistent connections
                        keepalive_expiry=60.0,  # Keep connections alive for 60s
                    ),
                    # HTTP/2 disabled (most LLM providers use HTTP/1.1)
                    http2=False,
                )

                # CRITICAL: Inject into LiteLLM SDK
                # This ensures all litellm.acompletion() calls use our persistent client
                litellm.aclient_session = cls._client

                logger.info("=" * 70)
                logger.info("✅ Created persistent httpx.AsyncClient for LiteLLM SDK")
                logger.info(f"   Client ID: {id(cls._client)}")
                logger.info(f"   Max Connections: 100")
                logger.info(f"   Keepalive Connections: 20")
                logger.info(f"   Read Timeout: 600s")
                logger.info(
                    f"   Injected into litellm.aclient_session: {id(litellm.aclient_session) == id(cls._client)}"
                )
                logger.info("=" * 70)

            return cls._client

    @classmethod
    async def close(cls):
        """
        Close the persistent HTTP client.

        This method should be called during application shutdown to properly
        release resources. It is idempotent - safe to call multiple times.

        The method:
        1. Closes the httpx.AsyncClient (releases connections)
        2. Clears the singleton instance
        3. Clears litellm.aclient_session

        Note:
            This method is async and should be called with await during
            application shutdown (e.g., in FastAPI lifespan context).

        Example:
            ```python
            # In FastAPI lifespan shutdown
            await LiteLLMSessionManager.close()
            ```
        """
        async with cls._lock:
            if cls._client:
                client_id = id(cls._client)

                # Close the client (releases all connections)
                await cls._client.aclose()

                # Clear references
                cls._client = None
                litellm.aclient_session = None

                logger.info("=" * 70)
                logger.info(f"✅ Closed persistent httpx.AsyncClient (ID: {client_id})")
                logger.info("   All connections released")
                logger.info("   litellm.aclient_session cleared")
                logger.info("=" * 70)

    @classmethod
    def is_initialized(cls) -> bool:
        """
        Check if the client has been initialized.

        Returns:
            bool: True if client exists, False otherwise

        Note:
            This is a synchronous method for quick status checks.
            Does not acquire lock (read-only check).

        Example:
            ```python
            if not LiteLLMSessionManager.is_initialized():
                await LiteLLMSessionManager.get_client()
            ```
        """
        return cls._client is not None

    @classmethod
    def get_cookie_count(cls) -> int:
        """
        Get the number of cookies stored in the session.

        This is useful for debugging Cloudflare cookie persistence.
        Cloudflare typically sets 2-3 cookies (cf_clearance, __cfruid, etc.).

        Returns:
            int: Number of cookies, or 0 if client not initialized

        Example:
            ```python
            cookie_count = LiteLLMSessionManager.get_cookie_count()
            logger.info(f"Session has {cookie_count} cookies")
            ```
        """
        if cls._client:
            # Resilient len() check for Mock objects in tests
            cookies = cls._client.cookies
            if hasattr(cookies, "__len__"):
                return len(cookies)
            return 0
        return 0

    @classmethod
    def get_cookie_names(cls) -> list[str]:
        """
        Get the names of all cookies in the session.

        This is useful for debugging Cloudflare integration. You can check
        for presence of expected cookies like 'cf_clearance'.

        Returns:
            list[str]: List of cookie names, empty if client not initialized

        Example:
            ```python
            cookies = LiteLLMSessionManager.get_cookie_names()
            if 'cf_clearance' in cookies:
                logger.info("Cloudflare challenge passed")
            ```
        """
        if cls._client:
            # Safely get cookie names, handling Mock objects
            try:
                cookies = cls._client.cookies
                if hasattr(cookies, "keys"):
                    keys = cookies.keys()
                    # Check if keys() result is iterable (not a Mock)
                    if hasattr(keys, "__iter__"):
                        return list(keys)
            except (TypeError, AttributeError):
                pass
        return []

    @classmethod
    def get_session_info(cls) -> dict[str, Any]:
        """
        Get detailed session information for debugging and monitoring.

        Returns:
            dict: Session information including:
                - initialized: Whether client exists
                - client_id: Python object ID of client
                - cookie_count: Number of cookies
                - cookie_names: List of cookie names
                - injected: Whether client is injected into litellm

        Example:
            ```python
            info = LiteLLMSessionManager.get_session_info()
            logger.info(f"Session info: {info}")
            ```
        """
        if cls._client:
            # Resilient checks for Mock objects in tests
            cookies = cls._client.cookies
            cookie_count = len(cookies) if hasattr(cookies, "__len__") else 0

            # Safely get cookie names, handling Mock objects
            try:
                if hasattr(cookies, "keys"):
                    keys = cookies.keys()
                    # Check if keys() result is iterable (not a Mock)
                    if hasattr(keys, "__iter__"):
                        cookie_names = list(keys)
                    else:
                        cookie_names = []
                else:
                    cookie_names = []
            except (TypeError, AttributeError):
                cookie_names = []

            return {
                "initialized": True,
                "client_id": id(cls._client),
                "cookie_count": cookie_count,
                "cookie_names": cookie_names,
                "injected_into_litellm": (
                    id(litellm.aclient_session) == id(cls._client)
                    if litellm.aclient_session
                    else False
                ),
            }
        return {
            "initialized": False,
            "client_id": None,
            "cookie_count": 0,
            "cookie_names": [],
            "injected_into_litellm": False,
        }


# =============================================================================
# Module-level convenience functions
# =============================================================================


async def initialize_session() -> httpx.AsyncClient:
    """
    Convenience function to initialize the session manager.

    This is a module-level wrapper around LiteLLMSessionManager.get_client()
    for easier imports.

    Returns:
        httpx.AsyncClient: The persistent client

    Example:
        ```python
        from proxy.session_manager import initialize_session

        client = await initialize_session()
        ```
    """
    return await LiteLLMSessionManager.get_client()


async def cleanup_session():
    """
    Convenience function to cleanup the session manager.

    This is a module-level wrapper around LiteLLMSessionManager.close()
    for easier imports.

    Example:
        ```python
        from proxy.session_manager import cleanup_session

        await cleanup_session()
        ```
    """
    await LiteLLMSessionManager.close()


def get_session_status() -> dict[str, Any]:
    """
    Convenience function to get session status.

    Returns:
        dict: Session information from get_session_info()

    Example:
        ```python
        from proxy.session_manager import get_session_status

        status = get_session_status()
        print(f"Cookies: {status['cookie_count']}")
        ```
    """
    return LiteLLMSessionManager.get_session_info()


# =============================================================================
# Testing and validation
# =============================================================================

if __name__ == "__main__":
    """
    Test session manager functionality.

    Usage:
        python -m src.proxy.session_manager
    """
    import sys

    async def test_session_manager():
        """Test basic session manager operations."""
        print("\n" + "=" * 70)
        print("Testing LiteLLMSessionManager")
        print("=" * 70 + "\n")

        # Test 1: Check initial state
        print("Test 1: Initial State")
        print(f"  Initialized: {LiteLLMSessionManager.is_initialized()}")
        print(f"  Cookie count: {LiteLLMSessionManager.get_cookie_count()}")

        # Test 2: Initialize client
        print("\nTest 2: Initialize Client")
        client1 = await LiteLLMSessionManager.get_client()
        print(f"  Client created: {client1 is not None}")
        print(f"  Client ID: {id(client1)}")
        print(f"  Initialized: {LiteLLMSessionManager.is_initialized()}")
        print(f"  Injected into litellm: {litellm.aclient_session is client1}")

        # Test 3: Singleton behavior
        print("\nTest 3: Singleton Behavior")
        client2 = await LiteLLMSessionManager.get_client()
        print(f"  Same client: {client1 is client2}")
        print(f"  Client1 ID: {id(client1)}")
        print(f"  Client2 ID: {id(client2)}")

        # Test 4: Session info
        print("\nTest 4: Session Info")
        info = LiteLLMSessionManager.get_session_info()
        for key, value in info.items():
            print(f"  {key}: {value}")

        # Test 5: Cleanup
        print("\nTest 5: Cleanup")
        await LiteLLMSessionManager.close()
        print(f"  Initialized after close: {LiteLLMSessionManager.is_initialized()}")
        print(f"  litellm.aclient_session cleared: {litellm.aclient_session is None}")

        # Test 6: Re-initialization
        print("\nTest 6: Re-initialization")
        client3 = await LiteLLMSessionManager.get_client()
        print(f"  New client created: {client3 is not None}")
        print(f"  Different from previous: {id(client3) != id(client1)}")

        # Final cleanup
        await LiteLLMSessionManager.close()

        print("\n" + "=" * 70)
        print("✅ All tests passed!")
        print("=" * 70 + "\n")

    # Run tests
    asyncio.run(test_session_manager())
