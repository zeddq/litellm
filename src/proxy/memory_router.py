"""
Memory Router Middleware for LiteLLM Proxy
Dynamically routes requests to Supermemory with client-specific user IDs
"""

import re
from typing import Dict, List, Optional, Any

import yaml
import logging

from starlette.datastructures import MutableHeaders, Headers

logger = logging.getLogger(__name__)


class MemoryRouter:
    """
    Routes requests to Supermemory with dynamic user ID detection.

    Detects client type from headers and assigns appropriate user IDs
    for memory isolation across different projects/clients.
    """

    def __init__(self, config_path: str = "config.yaml"):
        """Initialize router with configuration."""
        self.config = self._load_config(config_path)
        self.header_patterns = self._parse_header_patterns()
        self.custom_header = self.config.get('user_id_mappings', {}).get('custom_header', 'x-memory-user-id')
        self.default_user_id = self.config.get('user_id_mappings', {}).get('default_user_id', 'default-user')
        logger.info(f"MemoryRouter initialized with {len(self.header_patterns)} patterns")

    @staticmethod
    def _load_config( config_path: str) -> Dict:
        """Load configuration from YAML file."""
        try:
            with open(config_path, 'r') as f:
                return yaml.safe_load(f) or {}
        except FileNotFoundError:
            logger.warning(f"Config file {config_path} not found, using defaults")
            return {}
        except Exception as e:
            logger.error(f"Error loading config: {e}")
            return {}

    def _parse_header_patterns(self) -> List[Dict[str, str]]:
        """Parse header patterns from config."""
        mappings = self.config.get('user_id_mappings', {})
        patterns = mappings.get('header_patterns', [])

        # Compile regex patterns
        compiled_patterns = []
        for pattern in patterns:
            try:
                compiled = {
                    'header': pattern['header'].lower(),
                    'pattern': re.compile(pattern['pattern'], re.IGNORECASE),
                    'user_id': pattern['user_id']
                }
                compiled_patterns.append(compiled)
                logger.debug(f"Loaded pattern: {pattern['header']} -> {pattern['user_id']}")
            except Exception as e:
                logger.error(f"Error compiling pattern {pattern}: {e}")

        return compiled_patterns

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
        # Filter out None values to prevent AttributeError

        # Priority 1: Check custom header
        custom_header_lower = self.custom_header.lower()
        for orig_header, user_id in headers.items():
            # Check if header NAME matches custom header (case-insensitive)
            # and value is not None
            if orig_header == custom_header_lower and user_id is not None:
                logger.info(f"User ID from custom header '{orig_header}': {user_id}")
                return user_id
        
        # Priority 2: Pattern matching
        header_list = headers.items()
        for pattern_config in self.header_patterns:
            header_name = pattern_config['header'].lower()
            pattern = re.compile(pattern_config['pattern'])

            for h, v in header_list:
                if header_name == h:
                    if pattern.search(v):
                        user_id = pattern_config['user_id']
                        logger.info(f"User ID matched via {header_name}: {user_id} (pattern: {pattern.pattern})")
                        return user_id

        # Priority 3: Default
        logger.info(f"Using default user ID: {self.default_user_id}")
        return self.default_user_id

    def inject_memory_headers(
        self,
        headers: MutableHeaders,
        supermemory_api_key: Optional[str] = None
    ) -> MutableHeaders:
        """
        Inject Supermemory headers into request.

        Args:
            headers: Original request headers
            supermemory_api_key: Supermemory API key (optional, uses env if not provided)

        Returns:
            Updated headers with Supermemory routing
        """
        if supermemory_api_key:
            user_id = self.detect_user_id(headers)
            
            # Create new headers dict with Supermemory headers
            headers['x-sm-user-id'] = user_id
            headers['x-supermemory-api-key'] = supermemory_api_key

            logger.debug(f"Injected headers: x-sm-user-id={user_id}")
        else:
            logger.info("Supermemory API key not provided")
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
        for model in self.config.get('model_list', []):
            if model.get('model_name') == model_name:
                params = model.get('litellm_params', {})
                # Check if api_base points to supermemory
                api_base = params.get('api_base', '')
                return 'supermemory.ai' in api_base

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

        header_list = headers.items()
        for pattern_config in self.header_patterns:
            header_name = pattern_config['header']
            pattern = re.compile(pattern_config['pattern'])

            for h, v in header_list:
                if h == header_name:
                    if pattern.search(v):
                        matched_pattern = {
                            'header': header_name,
                            'value': v,
                            'pattern': pattern.pattern,
                            'user_id': pattern_config['user_id']
                    }
                    break

        return {
            'user_id': user_id,
            'matched_pattern': matched_pattern,
            'custom_header_present': self.custom_header.lower() in headers,
            'is_default': matched_pattern is None and self.custom_header.lower() not in headers
        }


# Example usage in your proxy
if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(level=logging.INFO)

    # Initialize router
    router = MemoryRouter("config.yaml")

    # Example: PyCharm AI Chat request
    pycharm_headers = Headers({
        'user-agent': 'OpenAIClientImpl/Java unknown',
        'x-stainless-lang': 'java',
        'Authorization': 'Bearer sk-1234'
    })

    print("\n=== PyCharm AI Chat Request ===")
    routing_info = router.get_routing_info(pycharm_headers)
    print(f"User ID: {routing_info['user_id']}")
    print(f"Matched Pattern: {routing_info['matched_pattern']}")

    # Example: Custom header request
    custom_headers = Headers({
        'user-agent': 'MyApp/1.0',
        'x-memory-user-id': 'project-alpha',
        'Authorization': 'Bearer sk-1234'
    })

    print("\n=== Custom Header Request ===")
    routing_info = router.get_routing_info(custom_headers)
    print(f"User ID: {routing_info['user_id']}")
    print(f"Custom Header Present: {routing_info['custom_header_present']}")

    # Example: Default request
    default_headers = Headers({
        'user-agent': 'curl/7.68.0',
        'Authorization': 'Bearer sk-1234'
    })

    print("\n=== Default Request ===")
    routing_info = router.get_routing_info(default_headers)
    print(f"User ID: {routing_info['user_id']}")
    print(f"Is Default: {routing_info['is_default']}")
