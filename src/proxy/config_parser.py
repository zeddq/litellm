"""
Configuration Parser for LiteLLM SDK Proxy.

This module provides configuration parsing and management for the SDK-based
LiteLLM proxy. It extends the existing schema.py validation with SDK-specific
functionality for extracting and preparing model parameters.

Key Features:
- Parses config.yaml using existing schema validation
- Resolves environment variables recursively
- Provides model configuration lookup
- Prepares parameters for litellm.acompletion() calls
- Immutable configuration caching

Architecture:
    This parser bridges the validated Pydantic models from schema.py with
    the runtime requirements of the SDK proxy. It provides a clean interface
    for extracting model-specific parameters needed for LiteLLM SDK calls.

References:
    - docs/architecture/LITELLM_SDK_INTEGRATION_PATTERNS.md (Section 3)
    - src/proxy/schema.py (configuration validation)
"""

import logging
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from proxy.schema import (
    LiteLLMProxyConfig,
    load_config_with_env_resolution,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ModelConfig:
    """
    Immutable model configuration for LiteLLM SDK.

    This dataclass provides a clean interface for model-specific parameters
    needed for litellm.acompletion() calls. It is immutable to ensure
    configuration stability throughout the application lifecycle.

    Attributes:
        model_name: Public model name (e.g., "claude-sonnet-4.5")
        litellm_model: LiteLLM model identifier (e.g., "anthropic/claude-sonnet-4-5-20250929")
        api_base: Custom API base URL (None for default provider endpoint)
        api_key: API key for the provider (resolved from environment if needed)
        extra_headers: Additional HTTP headers to send with requests
        custom_llm_provider: Explicit provider name override (e.g., "anthropic")
        timeout: Request timeout in seconds (None for default)
        max_retries: Maximum retry attempts (None for default)
        stream_timeout: Timeout for streaming responses (None for default)

    Example:
        ```python
        config = ModelConfig(
            model_name="claude-sonnet-4.5",
            litellm_model="anthropic/claude-sonnet-4-5-20250929",
            api_base="https://api.supermemory.ai/v3/api.anthropic.com",
            api_key="sk-ant-...",
            extra_headers={"x-supermemory-api-key": "sm_..."},
            custom_llm_provider="anthropic",
            timeout=600.0,
            max_retries=2,
            stream_timeout=None,
        )
        ```
    """

    model_name: str
    litellm_model: str
    api_base: Optional[str]
    api_key: Optional[str]
    extra_headers: Dict[str, str]
    custom_llm_provider: Optional[str]
    timeout: Optional[float] = None
    max_retries: Optional[int] = None
    stream_timeout: Optional[float] = None

    def to_litellm_params(self) -> Dict[str, Any]:
        """
        Convert to parameters suitable for litellm.acompletion().

        This method builds a dictionary with all necessary parameters for
        making LiteLLM SDK calls. It only includes non-None values.

        Returns:
            Dict[str, Any]: Parameters ready for **kwargs unpacking

        Example:
            ```python
            params = model_config.to_litellm_params()
            response = await litellm.acompletion(
                messages=[...],
                **params
            )
            ```
        """
        params: Dict[str, Any] = {
            "model": self.litellm_model,
        }

        if self.api_base:
            params["api_base"] = self.api_base

        if self.api_key:
            params["api_key"] = self.api_key

        if self.extra_headers:
            params["extra_headers"] = self.extra_headers.copy()

        if self.custom_llm_provider:
            params["custom_llm_provider"] = self.custom_llm_provider

        if self.timeout is not None:
            params["timeout"] = self.timeout

        if self.max_retries is not None:
            params["max_retries"] = self.max_retries

        if self.stream_timeout is not None:
            params["stream_timeout"] = self.stream_timeout

        return params


class LiteLLMConfig:
    """
    Configuration parser and manager for SDK proxy.

    This class provides a high-level interface for managing LiteLLM proxy
    configuration. It loads and validates config.yaml, resolves environment
    variables, and provides efficient lookup methods for model configurations.

    The class implements caching to avoid repeated parsing and provides
    immutable ModelConfig objects for thread-safe access.

    Usage:
        ```python
        # Load configuration
        config = LiteLLMConfig("config/config.yaml")

        # Get model parameters
        params = config.get_litellm_params("claude-sonnet-4.5")

        # Make completion call
        response = await litellm.acompletion(
            messages=[{"role": "user", "content": "Hello"}],
            **params
        )
        ```

    Attributes:
        config_path: Path to config.yaml file
        config: Validated configuration object from schema.py
        _models: Cached dictionary of ModelConfig objects
    """

    def __init__(self, config_path: str):
        """
        Initialize configuration parser.

        This loads and validates the config.yaml file, resolves all environment
        variables, and builds a cache of ModelConfig objects for efficient lookup.

        Args:
            config_path: Path to config.yaml file (relative or absolute)

        Raises:
            FileNotFoundError: If config file doesn't exist
            ValueError: If configuration is invalid or env vars missing
            yaml.YAMLError: If YAML parsing fails

        Example:
            ```python
            config = LiteLLMConfig("config/config.yaml")
            ```
        """
        self.config_path = config_path

        # Load and validate configuration with env var resolution
        logger.info(f"Loading configuration from: {config_path}")
        self.config: LiteLLMProxyConfig = load_config_with_env_resolution(config_path)

        # Build model configuration cache
        self._models: Dict[str, ModelConfig] = {}
        self._build_model_cache()

        logger.info(f"✅ Configuration loaded successfully")
        logger.info(f"   Models configured: {len(self._models)}")
        logger.info(f"   Model names: {list(self._models.keys())}")

    def _build_model_cache(self):
        """
        Build cache of ModelConfig objects from validated configuration.

        This method processes the model_list from the validated configuration
        and creates immutable ModelConfig objects for each model. The cache
        enables O(1) lookup performance.

        Note:
            This is called automatically during __init__. You should not
            need to call this method directly.
        """
        for model_entry in self.config.model_list:
            model_name = model_entry.model_name
            params = model_entry.litellm_params

            # Build ModelConfig object
            model_config = ModelConfig(
                model_name=model_name,
                litellm_model=params.model,
                api_base=params.api_base,
                api_key=self._resolve_env_var(params.api_key),
                extra_headers=self._resolve_extra_headers(params.extra_headers or {}),
                custom_llm_provider=params.custom_llm_provider,
                timeout=params.timeout,
                max_retries=params.max_retries,
                stream_timeout=params.stream_timeout,
            )

            self._models[model_name] = model_config

            logger.debug(
                f"Cached model config: {model_name} -> {model_config.litellm_model}"
            )

    @staticmethod
    def _resolve_env_var(value: Optional[str]) -> Optional[str]:
        """
        Resolve a single environment variable reference.

        Handles values in the format "os.environ/VAR_NAME" and resolves them
        to their actual values from environment variables.

        Args:
            value: String value (may be a literal or an env var reference)

        Returns:
            Resolved value or None

        Raises:
            ValueError: If env var reference exists but variable is not set

        Example:
            ```python
            # Environment: OPENAI_API_KEY="sk-123"
            resolved = self._resolve_env_var("os.environ/OPENAI_API_KEY")
            # Returns: "sk-123"
            ```
        """
        if not value:
            return None

        if value.startswith("os.environ/"):
            env_var = value.replace("os.environ/", "")
            resolved = os.getenv(env_var)

            if resolved is None:
                raise ValueError(
                    f"Environment variable '{env_var}' is not set. "
                    f"Required by configuration value: {value}"
                )

            logger.debug(f"Resolved env var: {env_var} -> <hidden>")
            return resolved

        return value

    def _resolve_extra_headers(self, headers: Dict[str, str]) -> Dict[str, str]:
        """
        Resolve environment variables in extra_headers dictionary.

        Processes all values in extra_headers and resolves any environment
        variable references. Returns a new dictionary with resolved values.

        Args:
            headers: Dictionary of header name -> value pairs

        Returns:
            New dictionary with resolved values

        Example:
            ```python
            headers = {"x-api-key": "os.environ/MY_KEY"}
            resolved = self._resolve_extra_headers(headers)
            # Returns: {"x-api-key": "actual-key-value"}
            ```
        """
        resolved_headers = {}

        for header_name, header_value in headers.items():
            resolved_value = self._resolve_env_var(header_value)
            if resolved_value:
                resolved_headers[header_name] = resolved_value

        return resolved_headers

    def get_model_config(self, model_name: str) -> Optional[ModelConfig]:
        """
        Get full ModelConfig for a specific model.

        Returns the cached ModelConfig object for the requested model, or None
        if the model is not configured.

        Args:
            model_name: Public model name (e.g., "claude-sonnet-4.5")

        Returns:
            ModelConfig object or None if model not found

        Example:
            ```python
            config = litellm_config.get_model_config("claude-sonnet-4.5")
            if config:
                print(f"Model: {config.litellm_model}")
                print(f"API Base: {config.api_base}")
            ```
        """
        model_config = self._models.get(model_name)

        if not model_config:
            logger.warning(f"Model not found in configuration: {model_name}")
            logger.debug(f"Available models: {list(self._models.keys())}")

        return model_config

    def get_litellm_params(self, model_name: str) -> Dict[str, Any]:
        """
        Get parameters ready for litellm.acompletion() call.

        This is the main method for extracting parameters needed to make
        LiteLLM SDK calls. It returns a dictionary suitable for **kwargs
        unpacking.

        Args:
            model_name: Public model name

        Returns:
            Dictionary of parameters for litellm.acompletion()

        Raises:
            ValueError: If model not found in configuration

        Example:
            ```python
            params = config.get_litellm_params("claude-sonnet-4.5")
            response = await litellm.acompletion(
                messages=[{"role": "user", "content": "Hello"}],
                **params
            )
            ```
        """
        model_config = self.get_model_config(model_name)

        if not model_config:
            available_models = list(self._models.keys())
            raise ValueError(
                f"Model '{model_name}' not found in configuration. "
                f"Available models: {available_models}"
            )

        params = model_config.to_litellm_params()

        logger.debug(
            f"Prepared litellm params for {model_name}: " f"keys={list(params.keys())}"
        )

        return params

    def get_master_key(self) -> Optional[str]:
        """
        Get the master API key for proxy authentication.

        Returns:
            Master key string or None if not configured

        Example:
            ```python
            master_key = config.get_master_key()
            if api_key == master_key:
                # Authentication successful
                pass
            ```
        """
        if not self.config.general_settings:
            return None

        master_key = self.config.general_settings.master_key

        # Resolve env var if needed (should already be resolved, but double-check)
        if master_key and master_key.startswith("os.environ/"):
            return self._resolve_env_var(master_key)

        return master_key

    def get_all_models(self) -> List[str]:
        """
        Get list of all configured model names.

        Returns:
            List of public model names

        Example:
            ```python
            models = config.get_all_models()
            print(f"Available models: {', '.join(models)}")
            ```
        """
        return list(self._models.keys())

    def model_exists(self, model_name: str) -> bool:
        """
        Check if a model is configured.

        Args:
            model_name: Model name to check

        Returns:
            True if model exists, False otherwise

        Example:
            ```python
            if config.model_exists("gpt-4"):
                # Proceed with request
                pass
            else:
                # Return 404
                pass
            ```
        """
        return model_name in self._models

    def get_litellm_settings(self) -> Dict[str, Any]:
        """
        Get litellm_settings section from configuration.

        Returns:
            Dictionary of LiteLLM settings (empty dict if not configured)

        Example:
            ```python
            settings = config.get_litellm_settings()
            if settings.get("set_verbose"):
                litellm.set_verbose = True
            ```
        """
        if not self.config.litellm_settings:
            return {}

        # Convert Pydantic model to dict
        return self.config.litellm_settings.model_dump(exclude_none=True)

    def get_config_summary(self) -> Dict[str, Any]:
        """
        Get a summary of the configuration for debugging.

        Returns:
            Dictionary with configuration summary

        Example:
            ```python
            summary = config.get_config_summary()
            logger.info(f"Config summary: {summary}")
            ```
        """
        return {
            "config_path": self.config_path,
            "model_count": len(self._models),
            "models": list(self._models.keys()),
            "has_general_settings": self.config.general_settings is not None,
            "has_user_id_mappings": self.config.user_id_mappings is not None,
            "has_litellm_settings": self.config.litellm_settings is not None,
        }


# =============================================================================
# Helper functions for common tasks
# =============================================================================


def validate_environment_variables(required_vars: List[str]) -> Dict[str, bool]:
    """
    Validate that required environment variables are set.

    Args:
        required_vars: List of environment variable names to check

    Returns:
        Dictionary mapping variable names to whether they are set

    Example:
        ```python
        status = validate_environment_variables([
            "ANTHROPIC_API_KEY",
            "OPENAI_API_KEY",
            "SUPERMEMORY_API_KEY"
        ])

        missing = [k for k, v in status.items() if not v]
        if missing:
            logger.error(f"Missing env vars: {missing}")
        ```
    """
    return {var: os.getenv(var) is not None for var in required_vars}


def get_missing_env_vars(required_vars: List[str]) -> List[str]:
    """
    Get list of missing environment variables.

    Args:
        required_vars: List of required variable names

    Returns:
        List of missing variable names

    Example:
        ```python
        missing = get_missing_env_vars(["API_KEY", "SECRET"])
        if missing:
            raise ValueError(f"Missing: {', '.join(missing)}")
        ```
    """
    return [var for var in required_vars if os.getenv(var) is None]


# =============================================================================
# Testing and validation
# =============================================================================

if __name__ == "__main__":
    """
    Test configuration parser functionality.

    Usage:
        python -m src.proxy.config_parser
    """
    import sys

    def test_config_parser():
        """Test basic configuration parser operations."""
        print("\n" + "=" * 70)
        print("Testing LiteLLMConfig")
        print("=" * 70 + "\n")

        try:
            # Test 1: Load configuration
            print("Test 1: Load Configuration")
            config = LiteLLMConfig("config/config.yaml")
            print(f"  ✅ Config loaded")
            print(f"  Models: {len(config.get_all_models())}")

            # Test 2: Get model list
            print("\nTest 2: Get Model List")
            models = config.get_all_models()
            for i, model in enumerate(models, 1):
                print(f"  {i}. {model}")

            # Test 3: Get model config
            print("\nTest 3: Get Model Config")
            if models:
                first_model = models[0]
                model_config = config.get_model_config(first_model)
                print(f"  Model: {first_model}")
                print(f"  LiteLLM Model: {model_config.litellm_model}")
                print(f"  API Base: {model_config.api_base or 'Default'}")
                print(
                    f"  Custom Provider: {model_config.custom_llm_provider or 'Auto'}"
                )

            # Test 4: Get litellm params
            print("\nTest 4: Get LiteLLM Params")
            if models:
                params = config.get_litellm_params(models[0])
                print(f"  Parameters: {list(params.keys())}")

            # Test 5: Model existence check
            print("\nTest 5: Model Existence Check")
            print(
                f"  Exists (first model): {config.model_exists(models[0]) if models else 'N/A'}"
            )
            print(f"  Exists (fake-model): {config.model_exists('fake-model')}")

            # Test 6: Config summary
            print("\nTest 6: Config Summary")
            summary = config.get_config_summary()
            for key, value in summary.items():
                print(f"  {key}: {value}")

            print("\n" + "=" * 70)
            print("✅ All tests passed!")
            print("=" * 70 + "\n")

        except Exception as e:
            print(f"\n❌ Test failed: {e}")
            import traceback

            traceback.print_exc()
            sys.exit(1)

    test_config_parser()
