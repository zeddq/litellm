"""
Memory Router Middleware for LiteLLM Proxy
Dynamically routes requests to Supermemory with client-specific user IDs
"""

import logging
from typing import Dict, Optional, Any

from starlette.datastructures import MutableHeaders, Headers
from starlette.requests import Request

from proxy.schema import (
    LiteLLMProxyConfig,
    UserIDMappings,
    load_config_with_env_resolution,
)

logger = logging.getLogger(__name__)


class MemoryRouter:
    """
    Routes requests to Supermemory with dynamic user ID detection.

    Detects client type from headers and assigns appropriate user IDs
    for memory isolation across different projects/clients.
    """

    def __init__(self, config: LiteLLMProxyConfig):
        """Initialize router with configuration."""
        self.config = config
        mappings = config.user_id_mappings or UserIDMappings()
        self.header_patterns = mappings.header_patterns
        self.custom_header = mappings.custom_header
        self.default_user_id = mappings.default_user_id
        # Resilient len() check for Mock objects in tests
        pattern_count = (
            len(self.header_patterns)
            if hasattr(self.header_patterns, "__len__")
            else "unknown"
        )
        logger.info(f"MemoryRouter initialized with {pattern_count} patterns")

    def detect_user_id(self, headers: Headers) -> str:
        """
        Detect user ID from request headers.

        Priority:
        1. Custom header (x-memory-user-id)
        2. Pattern matching on headers
        3. Default user ID

        Args:
            headers: Request headers (case-insensitive dict)

        Returns:
            User ID string for Supermemory
        """
        # Priority 1: Check custom header (case-insensitive)
        custom_header_lower = self.custom_header.lower()
        for orig_header, user_id in headers.items():
            # Check if header NAME matches custom header (case-insensitive)
            # and value is not None
            if orig_header.lower() == custom_header_lower and user_id is not None:
                logger.info(f"User ID from custom header '{orig_header}': {user_id}")
                return user_id

        # Priority 2: Pattern matching (case-insensitive header names)
        header_list = headers.items()
        for pattern_config in self.header_patterns:
            header_name = pattern_config.header.lower()
            pattern = pattern_config.pattern_compiled
            if not pattern:
                logger.warning("No pattern compiled for header: '%s'", header_name)
                continue

            for h, v in header_list:
                if h.lower() == header_name and v is not None:
                    if pattern.search(v):
                        user_id = pattern_config.user_id
                        logger.info(
                            f"User ID matched via {header_name}: {user_id} (pattern: {pattern.pattern})"
                        )
                        return user_id

        # Priority 3: Default
        logger.info(f"Using default user ID: {self.default_user_id}")
        return self.default_user_id

    def inject_memory_headers(
        self, headers: MutableHeaders, supermemory_api_key: Optional[str] = None
    ) -> MutableHeaders:
        """
        Inject Supermemory headers into request.

        Args:
            headers: Original request headers
            supermemory_api_key: Supermemory API key (optional, uses env if not provided)

        Returns:
            Updated headers with Supermemory routing
        """
        # Always inject user ID for routing and debugging
        user_id = self.detect_user_id(headers)
        # headers["x-sm-user-id"] = user_id
        headers["x-sm-user-id"] = "litellm-memory"

        # Only inject API key if provided
        if supermemory_api_key:
            headers["x-supermemory-api-key"] = supermemory_api_key
            logger.debug(
                f"Injected headers: x-sm-user-id={user_id}, x-supermemory-api-key=***"
            )
        else:
            logger.debug(f"Injected headers: x-sm-user-id={user_id} (no API key)")

        return headers

    def should_use_supermemory(self, model_name: str) -> bool:
        """
        Determine if request should be routed through Supermemory.

        Args:
            model_name: Model name from request

        Returns:
            True if model should use Supermemory
        """
        # Check if model has supermemory enabled in config
        for model in self.config.model_list:
            if model.model_name == model_name:
                # Check if api_base points to supermemory
                api_base = model.litellm_params.api_base or ""
                return "supermemory.ai" in api_base

        return False

    def get_routing_info(self, headers: Headers) -> Dict[str, Any]:
        """
        Get detailed routing information for debugging.

        Args:
            headers: Request headers

        Returns:
            Dict with routing details
        """
        user_id = self.detect_user_id(headers)

        # Detect which pattern matched (if any)
        matched_pattern = None
        custom_header_lower = self.custom_header.lower()
        custom_header_present = any(
            h.lower() == custom_header_lower for h in headers.keys()
        )

        header_list = headers.items()
        for pattern_config in self.header_patterns:
            header_name = pattern_config.header.lower()
            pattern = pattern_config.pattern_compiled
            if not pattern:
                logger.warning("No pattern compiled for header: '%s'", header_name)
                continue

            for h, v in header_list:
                if h.lower() == header_name and v is not None:
                    if pattern.search(v):
                        matched_pattern = {
                            "header": header_name,
                            "value": v,
                            "pattern": pattern.pattern,
                            "user_id": pattern_config.user_id,
                        }
                        break
            if matched_pattern:
                break

        return {
            "user_id": user_id,
            "matched_pattern": matched_pattern,
            "custom_header_present": custom_header_present,
            "is_default": matched_pattern is None and not custom_header_present,
        }


# Example usage in your proxy
if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(level=logging.INFO)

    # Initialize router
    router = MemoryRouter(load_config_with_env_resolution(config_path="config.yaml"))

    # Example: PyCharm AI Chat request
    pycharm_headers = Headers(
        {
            "user-agent": "OpenAIClientImpl/Java unknown",
            "x-stainless-lang": "java",
            "Authorization": "Bearer sk-1234",
        }
    )

    print("\n=== PyCharm AI Chat Request ===")
    routing_info = router.get_routing_info(pycharm_headers)
    print(f"User ID: {routing_info['user_id']}")
    print(f"Matched Pattern: {routing_info['matched_pattern']}")

    # Example: Custom header request
    custom_headers = Headers(
        {
            "user-agent": "MyApp/1.0",
            "x-memory-user-id": "project-alpha",
            "Authorization": "Bearer sk-1234",
        }
    )

    print("\n=== Custom Header Request ===")
    routing_info = router.get_routing_info(custom_headers)
    print(f"User ID: {routing_info['user_id']}")
    print(f"Custom Header Present: {routing_info['custom_header_present']}")

    # Example: Default request
    default_headers = Headers(
        {"user-agent": "curl/7.68.0", "Authorization": "Bearer sk-1234"}
    )

    print("\n=== Default Request ===")
    routing_info = router.get_routing_info(default_headers)
    print(f"User ID: {routing_info['user_id']}")
    print(f"Is Default: {routing_info['is_default']}")
