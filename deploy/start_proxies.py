#!/usr/bin/env python3
"""
Start LiteLLM and Memory Proxy

This script starts both the LiteLLM proxy and the memory routing proxy
in the correct order with configurable ports and config file.

Usage:
    poetry run start-proxies
    poetry run start-proxies --litellm-port 8765 --memoryproxy-port 8764
    poetry run start-proxies --config ./config.yaml
"""

import argparse
import logging
import multiprocessing
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import uvicorn
# Import memory proxy app here to avoid import-time issues
from proxy.litellm_proxy_with_memory import create_app

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("start_proxies")


def start_litellm_proxy(port: int, config_path: str):
    """
    Start LiteLLM proxy server as external binary process.

    Args:
        port: Port to run LiteLLM on
        config_path: Path to config.yaml
    """
    logger.info(f"Starting LiteLLM proxy binary on port {port} with config {config_path}")

    try:
        # Run litellm as external binary
        cmd = [
            "litellm",
            "--config", str(config_path),
            "--port", str(port),
            "--host", "0.0.0.0",
        ]

        logger.info(f"Executing command: {' '.join(cmd)}")

        # Start the process and wait for it
        process = subprocess.run(
            cmd,
            stdout=sys.stdout,
            stderr=sys.stderr,
            check=False
        )

        if process.returncode != 0:
            logger.error(f"LiteLLM proxy exited with code {process.returncode}")
            sys.exit(process.returncode)

    except FileNotFoundError:
        logger.error("LiteLLM binary not found in PATH")
        logger.error("Please ensure LiteLLM is installed: pip install litellm")
        logger.error("Or: poetry add litellm")
        sys.exit(1)
    except Exception as e:
        logger.error(f"LiteLLM proxy failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


def start_memory_proxy(port: int, litellm_port: int, config_path: str):
    """
    Start memory routing proxy.

    Args:
        port: Port to run memory proxy on
        litellm_port: Port where LiteLLM is running
        config_path: Path to config.yaml
    """
    logger.info(
        f"Starting Memory Proxy on port {port}, forwarding to LiteLLM at localhost:{litellm_port}"
    )

    # Set environment variables
    os.environ["LITELLM_CONFIG"] = str(config_path)
    os.environ["LITELLM_BASE_URL"] = f"http://localhost:{litellm_port}"

    app = create_app()
    try:
        # Run the memory proxy
        uvicorn.run(
            app,
            host="0.0.0.0",
            port=port,
            log_level="info",
        )
    except Exception as e:
        logger.error(f"Memory proxy failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


def wait_for_litellm(port: int, timeout: int = 30) -> bool:
    """
    Wait for LiteLLM proxy to be ready.

    Args:
        port: Port where LiteLLM is running
        timeout: Maximum time to wait in seconds

    Returns:
        True if LiteLLM is ready, False otherwise
    """
    import httpx

    url = f"http://localhost:{port}/health"
    start_time = time.time()

    logger.info(f"Waiting for LiteLLM to be ready at {url}...")

    while time.time() - start_time < timeout:
        try:
            response = httpx.get(url, timeout=2.0)
            if response.status_code == 200:
                logger.info("LiteLLM is ready!")
                return True
        except (httpx.RequestError, httpx.ConnectError):
            pass

        time.sleep(1)

    logger.error(f"LiteLLM failed to start within {timeout} seconds")
    return False


def signal_handler(signum, frame):
    """Handle termination signals."""
    logger.info(f"Received signal {signum}, shutting down...")
    sys.exit(0)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Start LiteLLM and Memory Proxy",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--litellm-port",
        type=int,
        default=8765,
        help="Port for LiteLLM proxy",
    )
    parser.add_argument(
        "--memoryproxy-port",
        type=int,
        default=8764,
        help="Port for Memory Proxy",
    )
    parser.add_argument(
        "--config",
        type=str,
        default="./config.yaml",
        help="Path to config.yaml",
    )

    args = parser.parse_args()

    # Validate config file exists
    config_path = Path(args.config).resolve()
    if not config_path.exists():
        logger.error(f"Config file not found: {config_path}")
        sys.exit(1)

    logger.info("=" * 80)
    logger.info("Starting Proxy Servers")
    logger.info("=" * 80)
    logger.info(f"LiteLLM Port:      {args.litellm_port}")
    logger.info(f"Memory Proxy Port: {args.memoryproxy_port}")
    logger.info(f"Config File:       {config_path}")
    logger.info("=" * 80)

    # Set up signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Start LiteLLM in a separate process
    litellm_process = multiprocessing.Process(
        target=start_litellm_proxy,
        args=(args.litellm_port, str(config_path)),
        name="LiteLLM-Proxy",
    )
    litellm_process.start()

    # Wait for LiteLLM to be ready
    if not wait_for_litellm(args.litellm_port):
        logger.error("Failed to start LiteLLM, aborting")
        litellm_process.terminate()
        sys.exit(1)

    # Start Memory Proxy in a separate process
    memory_process = multiprocessing.Process(
        target=start_memory_proxy,
        args=(args.memoryproxy_port, args.litellm_port, str(config_path)),
        name="Memory-Proxy",
    )
    memory_process.start()

    logger.info("=" * 80)
    logger.info("Both proxies are running!")
    logger.info(f"LiteLLM:      http://localhost:{args.litellm_port}")
    logger.info(f"Memory Proxy: http://localhost:{args.memoryproxy_port}")
    logger.info("Press Ctrl+C to stop")
    logger.info("=" * 80)

    try:
        # Wait for processes
        litellm_process.join()
        memory_process.join()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        litellm_process.terminate()
        memory_process.terminate()
        litellm_process.join(timeout=5)
        memory_process.join(timeout=5)
        logger.info("Shutdown complete")


if __name__ == "__main__":
    main()