#!/usr/bin/env python3
"""
Unified Proxy Launcher - Supports Both Binary and SDK Approaches

This script provides a unified interface to launch either the binary-based
LiteLLM proxy or the SDK-based proxy, with easy switching via environment
variables or command-line flags.

Usage:
    # Use SDK proxy (recommended)
    python deploy/run_unified_proxy.py --mode sdk

    # Use binary proxy (legacy)
    python deploy/run_unified_proxy.py --mode binary

    # Environment variable
    USE_SDK_PROXY=true python deploy/run_unified_proxy.py

    # Run both for testing
    python deploy/run_unified_proxy.py --mode both

Features:
    - Easy switching between binary and SDK proxies
    - Graceful startup and shutdown
    - Health checks before declaring ready
    - Proper cleanup on exit
    - Logging and monitoring
    - Support for custom ports and config files

Author: Migration Team
Date: 2025-11-02
"""

import argparse
import asyncio
import logging
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

import httpx
import uvicorn
from litellm.proxy.proxy_server import litellm_proxy_admin_name

from proxy.memory_router import MemoryRouter

# Setup logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Project root
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


class ProxyMode:
    """Proxy mode enumeration."""

    BINARY = "binary"
    SDK = "sdk"
    BOTH = "both"


class ProxyLauncher:
    """
    Unified launcher for binary and SDK proxies.

    Manages the lifecycle of proxy processes, including:
    - Starting proxies
    - Health checking
    - Graceful shutdown
    - Process monitoring
    """

    def __init__(
        self,
        mode: str,
        litellm_port: int = 4000,
        proxy_port: int = 8764,
        sdk_port: int = 8765,
        config_path: str = "config/config.yaml",
    ):
        """
        Initialize the launcher.

        Args:
            mode: Proxy mode (binary, sdk, or both)
            litellm_port: Port for LiteLLM binary (binary mode only)
            proxy_port: Port for memory proxy (binary mode)
            sdk_port: Port for SDK proxy
            config_path: Path to config.yaml
        """
        self.mode = mode
        self.litellm_port = litellm_port
        self.proxy_port = proxy_port
        self.sdk_port = sdk_port
        self.config_path = config_path

        self.litellm_process: Optional[subprocess.Popen] = None
        self.binary_proxy_task: Optional[asyncio.Task] = None
        self.sdk_proxy_task: Optional[asyncio.Task] = None

        # Register signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals."""
        logger.info(f"Received signal {signum}, initiating shutdown...")
        asyncio.create_task(self.shutdown())

    async def check_health(self, url: str, timeout: int = 30) -> bool:
        """
        Check if a proxy is healthy.

        Args:
            url: Health check URL
            timeout: Maximum time to wait (seconds)

        Returns:
            True if healthy, False otherwise
        """
        start_time = time.time()
        async with httpx.AsyncClient() as client:
            while time.time() - start_time < timeout:
                try:
                    response = await client.get(url, timeout=5.0)
                    if response.status_code == 200:
                        logger.info(f"✅ {url} is healthy")
                        return True
                except Exception as e:
                    logger.debug(f"Health check failed: {e}")
                await asyncio.sleep(1)

        logger.error(f"❌ {url} failed health check after {timeout}s")
        return False

    async def start_litellm_binary(self) -> bool:
        """
        Start the LiteLLM binary process.

        Returns:
            True if started successfully, False otherwise
        """
        logger.info(f"🚀 Starting LiteLLM binary on port {self.litellm_port}...")

        try:
            self.litellm_process = subprocess.Popen(
                [
                    "litellm",
                    "--config",
                    self.config_path,
                    "--port",
                    str(self.litellm_port),
                    "--detailed_debug",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            # Wait for LiteLLM to be ready
            health_url = f"http://localhost:{self.litellm_port}/health"
            is_healthy = await self.check_health(health_url, timeout=30)

            if not is_healthy:
                logger.error("Failed to start LiteLLM binary")
                if self.litellm_process:
                    self.litellm_process.terminate()
                    self.litellm_process = None
                return False

            logger.info(f"✅ LiteLLM binary started on port {self.litellm_port}")
            return True

        except Exception as e:
            logger.error(f"Error starting LiteLLM binary: {e}")
            return False

    async def start_binary_proxy(self) -> bool:
        """
        Start the binary-based memory proxy.

        Returns:
            True if started successfully, False otherwise
        """
        logger.info(f"🚀 Starting binary memory proxy on port {self.proxy_port}...")

        try:
            # Import the binary proxy module
            from proxy.litellm_proxy_with_memory import create_app

            app = create_app(litellm_auth_token=os.getenv("LITELLM_VIRTUAL_KEY", ""))

            # Run with uvicorn
            config = uvicorn.Config(
                app,
                host="0.0.0.0",
                port=self.proxy_port,
                log_level="info",
            )
            server = uvicorn.Server(config)

            # Start in background task
            self.binary_proxy_task = asyncio.create_task(server.serve())

            # Wait for proxy to be ready
            await asyncio.sleep(2)  # Give it time to start
            health_url = f"http://localhost:{self.proxy_port}/health"
            is_healthy = await self.check_health(health_url, timeout=10)

            if not is_healthy:
                logger.error("Failed to start binary proxy")
                if self.binary_proxy_task:
                    self.binary_proxy_task.cancel()
                    self.binary_proxy_task = None
                return False

            logger.info(f"✅ Binary proxy started on port {self.proxy_port}")
            return True

        except Exception as e:
            logger.error(f"Error starting binary proxy: {e}")
            return False

    async def start_sdk_proxy(self) -> bool:
        """
        Start the SDK-based proxy.

        Returns:
            True if started successfully, False otherwise
        """
        logger.info(f"🚀 Starting SDK proxy on port {self.sdk_port}...")

        try:
            # Import the SDK proxy module
            from proxy.litellm_proxy_sdk import app

            # app = create_app(litellm_auth_token=os.getenv("LITELLM_VIRTUAL_KEY"), config_path=self.config_path)

            # Run with uvicorn
            config = uvicorn.Config(
                app,
                host="0.0.0.0",
                port=self.sdk_port,
                log_level="info",
            )
            server = uvicorn.Server(config)

            # Start in background task
            self.sdk_proxy_task = asyncio.create_task(server.serve())

            # Wait for proxy to be ready
            await asyncio.sleep(2)  # Give it time to start
            health_url = f"http://localhost:{self.sdk_port}/health"
            is_healthy = await self.check_health(health_url, timeout=10)

            if not is_healthy:
                logger.error("Failed to start SDK proxy")
                if self.sdk_proxy_task:
                    self.sdk_proxy_task.cancel()
                    self.sdk_proxy_task = None
                return False

            logger.info(f"✅ SDK proxy started on port {self.sdk_port}")
            return True

        except Exception as e:
            logger.error(f"Error starting SDK proxy: {e}")
            return False

    async def start(self) -> bool:
        """
        Start proxies based on mode.

        Returns:
            True if all started successfully, False otherwise
        """
        logger.info(f"Starting in {self.mode} mode...")

        if self.mode == ProxyMode.BINARY:
            # Start LiteLLM binary
            if not await self.start_litellm_binary():
                return False

            # Start binary proxy
            if not await self.start_binary_proxy():
                return False

            logger.info(f"🎉 Binary mode ready at http://localhost:{self.proxy_port}")
            return True

        elif self.mode == ProxyMode.SDK:
            # Start SDK proxy only
            if not await self.start_sdk_proxy():
                return False

            logger.info(f"🎉 SDK mode ready at http://localhost:{self.sdk_port}")
            return True

        elif self.mode == ProxyMode.BOTH:
            # Start LiteLLM binary
            if not await self.start_litellm_binary():
                return False

            # Start binary proxy
            if not await self.start_binary_proxy():
                logger.warning("Binary proxy failed to start, continuing with SDK only")

            # Start SDK proxy
            if not await self.start_sdk_proxy():
                logger.error("SDK proxy failed to start")
                return False

            logger.info("🎉 Both proxies ready:")
            logger.info(f"  - Binary: http://localhost:{self.proxy_port}")
            logger.info(f"  - SDK: http://localhost:{self.sdk_port}")
            return True

        else:
            logger.error(f"Unknown mode: {self.mode}")
            return False

    async def shutdown(self):
        """Graceful shutdown of all proxies."""
        logger.info("Shutting down proxies...")

        # Stop SDK proxy
        if self.sdk_proxy_task:
            logger.info("Stopping SDK proxy...")
            self.sdk_proxy_task.cancel()
            try:
                await self.sdk_proxy_task
            except asyncio.CancelledError:
                pass
            self.sdk_proxy_task = None

        # Stop binary proxy
        if self.binary_proxy_task:
            logger.info("Stopping binary proxy...")
            self.binary_proxy_task.cancel()
            try:
                await self.binary_proxy_task
            except asyncio.CancelledError:
                pass
            self.binary_proxy_task = None

        # Stop LiteLLM binary
        if self.litellm_process:
            logger.info("Stopping LiteLLM binary...")
            self.litellm_process.terminate()
            try:
                self.litellm_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                logger.warning("LiteLLM didn't stop gracefully, killing...")
                self.litellm_process.kill()
            self.litellm_process = None

        logger.info("✅ All proxies stopped")

    async def run(self):
        """Main run loop."""
        # Start proxies
        if not await self.start():
            logger.error("Failed to start proxies, exiting")
            await self.shutdown()
            sys.exit(1)

        # Wait for tasks
        try:
            tasks = []
            if self.binary_proxy_task:
                tasks.append(self.binary_proxy_task)
            if self.sdk_proxy_task:
                tasks.append(self.sdk_proxy_task)

            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            else:
                # No async tasks, just wait
                while True:
                    await asyncio.sleep(1)

        except KeyboardInterrupt:
            logger.info("Received interrupt signal")
        except Exception as e:
            logger.error(f"Error in main loop: {e}")
        finally:
            await self.shutdown()


def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Unified proxy launcher for LiteLLM",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Start SDK proxy (recommended)
  python deploy/run_unified_proxy.py --mode sdk

  # Start binary proxy
  python deploy/run_unified_proxy.py --mode binary

  # Start both for testing
  python deploy/run_unified_proxy.py --mode both

  # Use environment variable
  USE_SDK_PROXY=true python deploy/run_unified_proxy.py

  # Custom ports
  python deploy/run_unified_proxy.py --mode sdk --sdk-port 8080

  # Custom config
  python deploy/run_unified_proxy.py --mode sdk --config my_config.yaml
        """,
    )

    parser.add_argument(
        "--mode",
        choices=[ProxyMode.BINARY, ProxyMode.SDK, ProxyMode.BOTH],
        default=None,
        help="Proxy mode (binary, sdk, or both). If not specified, checks USE_SDK_PROXY env var.",
    )

    parser.add_argument(
        "--litellm-port",
        type=int,
        default=4000,
        help="Port for LiteLLM binary (default: 4000)",
    )

    parser.add_argument(
        "--proxy-port",
        type=int,
        default=8764,
        help="Port for binary memory proxy (default: 8764)",
    )

    parser.add_argument(
        "--sdk-port",
        type=int,
        default=8765,
        help="Port for SDK proxy (default: 8765)",
    )

    parser.add_argument(
        "--config",
        type=str,
        default="config/config.yaml",
        help="Path to config.yaml (default: config/config.yaml)",
    )

    args = parser.parse_args()

    # If mode not specified, check environment variable
    if args.mode is None:
        use_sdk = os.getenv("USE_SDK_PROXY", "false").lower() in ("true", "1", "yes")
        args.mode = ProxyMode.SDK if use_sdk else ProxyMode.BINARY

    return args


async def main():
    """Main entry point."""
    args = parse_args()

    logger.level = logging.DEBUG
    logger.info("=" * 60)
    logger.info("LiteLLM Unified Proxy Launcher")
    logger.info("=" * 60)
    logger.info(f"Mode: {args.mode}")
    logger.info(f"Config: {args.config}")
    logger.info(
        f"Ports: LiteLLM={args.litellm_port}, Binary={args.proxy_port}, SDK={args.sdk_port}"
    )
    logger.info("=" * 60)

    # Verify config exists
    config_path = Path(args.config)
    if not config_path.exists():
        logger.error(f"Config file not found: {config_path}")
        sys.exit(1)

    # Create launcher
    launcher = ProxyLauncher(
        mode=args.mode,
        litellm_port=args.litellm_port,
        proxy_port=args.proxy_port,
        sdk_port=args.sdk_port,
        config_path=str(config_path),
    )

    # Run
    await launcher.run()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)
