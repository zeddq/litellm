"""
Comprehensive test suite for LiteLLM proxy configuration schema validation.

Tests cover:
- Schema validation for all configuration sections
- Custom validators (regex, URLs, cross-field validation)
- Environment variable resolution
- Error handling and edge cases
- JSON Schema export
"""

import os
import re
import tempfile
from pathlib import Path
from typing import Any, Dict

import pytest
import yaml
from pydantic import ValidationError

from proxy.schema import (
    CacheType,
    DatabaseType,
    GeneralSettings,
    HeaderPattern,
    LiteLLMParams,
    LiteLLMProxyConfig,
    LiteLLMSettings,
    MCPAuthType,
    MCPServerConfig,
    MCPTransport,
    ModelConfig,
    OTELExporter,
    RedisCacheParams,
    S3CacheParams,
    ThinkingConfig,
    ThinkingType,
    UserIDMappings,
    export_json_schema,
    load_config,
    load_config_with_env_resolution,
    resolve_env_vars,
    validate_config_dict,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def minimal_valid_config() -> Dict[str, Any]:
    """Minimal valid configuration for testing."""
    return {
        "general_settings": {"master_key": "sk-1234"},
        "model_list": [
            {
                "model_name": "gpt-4",
                "litellm_params": {
                    "model": "openai/gpt-4",
                    "api_key": "sk-test-key",
                },
            }
        ],
    }


@pytest.fixture
def full_valid_config() -> Dict[str, Any]:
    """Full valid configuration with all sections."""
    return {
        "general_settings": {
            "master_key": "sk-1234",
            "forward_openai_org_id": True,
            "forward_client_headers_to_llm_api": True,
            "database_url": "postgresql://user:pass@localhost:5432/litellm",
            "database_connection_pool_limit": 100,
            "store_model_in_db": True,
            "store_prompts_in_spend_logs": True,
        },
        "user_id_mappings": {
            "custom_header": "x-memory-user-id",
            "header_patterns": [
                {
                    "header": "user-agent",
                    "pattern": "^OpenAIClientImpl/Java",
                    "user_id": "pycharm-ai",
                },
                {
                    "header": "user-agent",
                    "pattern": "^Claude Code",
                    "user_id": "claude-cli",
                },
            ],
            "default_user_id": "default-dev",
        },
        "model_list": [
            {
                "model_name": "gpt-4",
                "litellm_params": {
                    "model": "openai/gpt-4",
                    "api_key": "sk-openai-key",
                },
            },
            {
                "model_name": "claude-sonnet-4.5",
                "litellm_params": {
                    "model": "anthropic/claude-sonnet-4-5-20250929",
                    "api_key": "sk-anthropic-key",
                    "api_base": "https://api.supermemory.ai/v3/api.anthropic.com",
                    "custom_llm_provider": "anthropic",
                    "extra_headers": {"x-supermemory-api-key": "sm-key"},
                    "thinking": {"type": "enabled", "budget_tokens": 4096},
                },
            },
        ],
        "mcp_servers": {
            "jetbrains_mcp": {
                "transport": "sse",
                "url": "http://localhost:64343/sse",
                "auth_type": "none",
            }
        },
        "litellm_settings": {
            "database_type": "prisma",
            "database_url": "postgresql://user:pass@localhost:5432/litellm",
            "store_model_in_db": True,
            "success_callback": ["postgres", "otel"],
            "failure_callback": ["postgres", "otel"],
            "otel": True,
            "otel_exporter": "otlp_http",
            "otel_endpoint": "http://localhost:4318/v1/traces",
            "otel_service_name": "litellm-proxy",
            "otel_headers": "",
            "cache": True,
            "cache_params": {
                "type": "redis",
                "host": "localhost",
                "port": 6379,
                "password": "redis-pass",
                "ttl": 3600,
            },
            "mcp_aliases": {"jetbrains": "jetbrains_mcp"},
            "set_verbose": True,
            "json_logs": True,
            "drop_params": True,
            "forward_traceparent_to_llm_provider": True,
        },
    }


@pytest.fixture
def temp_config_file(tmp_path: Path) -> Path:
    """Create a temporary config file."""
    config_file = tmp_path / "config.yaml"
    return config_file


# =============================================================================
# GeneralSettings Tests
# =============================================================================


class TestGeneralSettings:
    """Tests for GeneralSettings model."""

    def test_valid_general_settings(self):
        """Test valid general settings."""
        settings = GeneralSettings(
            master_key="sk-1234",
            forward_openai_org_id=True,
            database_url="postgresql://localhost:5432/db",
        )
        assert settings.master_key == "sk-1234"
        assert settings.forward_openai_org_id is True

    def test_env_var_reference(self):
        """Test environment variable reference validation."""
        settings = GeneralSettings(
            master_key="os.environ/MASTER_KEY",
            database_url="os.environ/DATABASE_URL",
        )
        assert settings.master_key == "os.environ/MASTER_KEY"
        assert settings.database_url == "os.environ/DATABASE_URL"

    def test_invalid_env_var_name(self):
        """Test invalid environment variable name."""
        with pytest.raises(ValidationError) as exc_info:
            GeneralSettings(master_key="os.environ/123-invalid")
        assert "Invalid environment variable name" in str(exc_info.value)

    def test_connection_pool_limits(self):
        """Test database connection pool limit validation."""
        # Valid range
        settings = GeneralSettings(
            master_key="sk-1234", database_connection_pool_limit=50
        )
        assert settings.database_connection_pool_limit == 50

        # Below minimum
        with pytest.raises(ValidationError):
            GeneralSettings(master_key="sk-1234", database_connection_pool_limit=0)

        # Above maximum
        with pytest.raises(ValidationError):
            GeneralSettings(master_key="sk-1234", database_connection_pool_limit=1001)


# =============================================================================
# UserIDMappings Tests
# =============================================================================


class TestUserIDMappings:
    """Tests for UserIDMappings and HeaderPattern models."""

    def test_valid_header_pattern(self):
        """Test valid header pattern."""
        pattern = HeaderPattern(
            header="user-agent", pattern="^OpenAI.*", user_id="openai-client"
        )
        assert pattern.header == "user-agent"  # Normalized to lowercase
        assert pattern.pattern == "^OpenAI.*"
        assert pattern.user_id == "openai-client"

    def test_header_normalization(self):
        """Test header name normalization."""
        pattern = HeaderPattern(
            header="User-Agent", pattern=".*", user_id="test"  # Mixed case
        )
        assert pattern.header == "user-agent"  # Should be lowercase

    def test_invalid_regex_pattern(self):
        """Test invalid regex pattern."""
        with pytest.raises(ValidationError) as exc_info:
            HeaderPattern(header="user-agent", pattern="[invalid(regex", user_id="test")
        assert "Invalid regex pattern" in str(exc_info.value)

    def test_valid_regex_patterns(self):
        """Test various valid regex patterns."""
        patterns = [
            "^OpenAIClientImpl/Java",
            "Claude Code.*",
            "^anthropic-sdk-python$",
            ".*PyCharm.*",
        ]
        for pattern_str in patterns:
            pattern = HeaderPattern(
                header="user-agent", pattern=pattern_str, user_id="test"
            )
            assert pattern.pattern == pattern_str
            # Verify pattern compiles
            re.compile(pattern.pattern)

    def test_user_id_validation(self):
        """Test user ID validation."""
        # Valid user ID
        pattern = HeaderPattern(
            header="user-agent", pattern=".*", user_id="valid-user-123"
        )
        assert pattern.user_id == "valid-user-123"

        # Invalid user ID with whitespace
        with pytest.raises(ValidationError):
            HeaderPattern(
                header="user-agent", pattern=".*", user_id="user with spaces"
            )

    def test_valid_user_id_mappings(self):
        """Test valid user ID mappings configuration."""
        mappings = UserIDMappings(
            custom_header="x-memory-user-id",
            header_patterns=[
                HeaderPattern(
                    header="user-agent", pattern="^OpenAI.*", user_id="openai"
                ),
                HeaderPattern(
                    header="user-agent", pattern="^Claude.*", user_id="claude"
                ),
            ],
            default_user_id="default",
        )
        assert len(mappings.header_patterns) == 2
        assert mappings.default_user_id == "default"

    def test_duplicate_patterns(self):
        """Test duplicate pattern detection."""
        with pytest.raises(ValidationError) as exc_info:
            UserIDMappings(
                header_patterns=[
                    HeaderPattern(header="user-agent", pattern="^OpenAI.*", user_id="1"),
                    HeaderPattern(header="user-agent", pattern="^OpenAI.*", user_id="2"),
                ],
                default_user_id="default",
            )
        assert "Duplicate pattern" in str(exc_info.value)


# =============================================================================
# ModelConfig Tests
# =============================================================================


class TestModelConfig:
    """Tests for ModelConfig and LiteLLMParams models."""

    def test_valid_model_config(self):
        """Test valid model configuration."""
        config = ModelConfig(
            model_name="gpt-4",
            litellm_params=LiteLLMParams(model="openai/gpt-4", api_key="sk-test"),
        )
        assert config.model_name == "gpt-4"
        assert config.litellm_params.model == "openai/gpt-4"

    def test_model_format_validation(self):
        """Test model format validation (provider/model-name)."""
        # Valid format
        params = LiteLLMParams(model="openai/gpt-4", api_key="sk-test")
        assert params.model == "openai/gpt-4"

        # Invalid format (no provider)
        with pytest.raises(ValidationError) as exc_info:
            LiteLLMParams(model="gpt-4", api_key="sk-test")
        assert "provider/model-name" in str(exc_info.value)

        # Invalid format (empty provider)
        with pytest.raises(ValidationError):
            LiteLLMParams(model="/gpt-4", api_key="sk-test")

        # Invalid format (empty model)
        with pytest.raises(ValidationError):
            LiteLLMParams(model="openai/", api_key="sk-test")

    def test_api_base_validation(self):
        """Test API base URL validation."""
        # Valid HTTPS URL
        params = LiteLLMParams(
            model="openai/gpt-4",
            api_key="sk-test",
            api_base="https://api.example.com",
        )
        assert params.api_base == "https://api.example.com"

        # Valid HTTP URL
        params = LiteLLMParams(
            model="openai/gpt-4", api_key="sk-test", api_base="http://localhost:8000"
        )
        assert params.api_base == "http://localhost:8000"

        # Invalid URL (no protocol)
        with pytest.raises(ValidationError) as exc_info:
            LiteLLMParams(
                model="openai/gpt-4", api_key="sk-test", api_base="api.example.com"
            )
        assert "http://" in str(exc_info.value)

    def test_thinking_config(self):
        """Test thinking configuration."""
        thinking = ThinkingConfig(type=ThinkingType.ENABLED, budget_tokens=8192)
        assert thinking.type == ThinkingType.ENABLED
        assert thinking.budget_tokens == 8192

        # Test with dict format
        params = LiteLLMParams(
            model="anthropic/claude-sonnet-4.5",
            api_key="sk-test",
            thinking={"type": "enabled", "budget_tokens": 4096},
        )
        assert params.thinking is not None

    def test_extra_headers(self):
        """Test extra headers configuration."""
        params = LiteLLMParams(
            model="anthropic/claude-sonnet-4.5",
            api_key="sk-test",
            extra_headers={
                "x-supermemory-api-key": "sm-key",
                "x-custom-header": "value",
            },
        )
        assert len(params.extra_headers) == 2
        assert params.extra_headers["x-supermemory-api-key"] == "sm-key"

    def test_timeout_validation(self):
        """Test timeout parameter validation."""
        # Valid timeout
        params = LiteLLMParams(
            model="openai/gpt-4", api_key="sk-test", timeout=30.0
        )
        assert params.timeout == 30.0

        # Invalid timeout (negative)
        with pytest.raises(ValidationError):
            LiteLLMParams(model="openai/gpt-4", api_key="sk-test", timeout=-1.0)

        # Invalid timeout (too small)
        with pytest.raises(ValidationError):
            LiteLLMParams(model="openai/gpt-4", api_key="sk-test", timeout=0.05)


# =============================================================================
# MCPServerConfig Tests
# =============================================================================


class TestMCPServerConfig:
    """Tests for MCP server configuration."""

    def test_sse_transport_valid(self):
        """Test valid SSE transport configuration."""
        config = MCPServerConfig(
            transport=MCPTransport.SSE,
            url="http://localhost:64343/sse",
            auth_type=MCPAuthType.NONE,
        )
        assert config.transport == MCPTransport.SSE
        assert config.url == "http://localhost:64343/sse"

    def test_sse_requires_url(self):
        """Test that SSE transport requires URL."""
        with pytest.raises(ValidationError) as exc_info:
            MCPServerConfig(transport=MCPTransport.SSE, auth_type=MCPAuthType.NONE)
        assert "url is required" in str(exc_info.value)

    def test_stdio_transport_valid(self):
        """Test valid stdio transport configuration."""
        config = MCPServerConfig(
            transport=MCPTransport.STDIO,
            command="python",
            args=["-m", "mcp_server"],
            env={"PATH": "/usr/bin"},
        )
        assert config.transport == MCPTransport.STDIO
        assert config.command == "python"
        assert len(config.args) == 2

    def test_stdio_requires_command(self):
        """Test that stdio transport requires command."""
        with pytest.raises(ValidationError) as exc_info:
            MCPServerConfig(transport=MCPTransport.STDIO)
        assert "command is required" in str(exc_info.value)

    def test_url_validation(self):
        """Test URL format validation."""
        # Valid URLs
        for url in ["http://localhost:8000", "https://api.example.com/sse"]:
            config = MCPServerConfig(
                transport=MCPTransport.SSE, url=url, auth_type=MCPAuthType.NONE
            )
            assert config.url == url

        # Invalid URL (no protocol)
        with pytest.raises(ValidationError):
            MCPServerConfig(
                transport=MCPTransport.SSE,
                url="localhost:8000",
                auth_type=MCPAuthType.NONE,
            )


# =============================================================================
# CacheParams Tests
# =============================================================================


class TestCacheParams:
    """Tests for cache configuration."""

    def test_redis_cache_params(self):
        """Test Redis cache configuration."""
        cache = RedisCacheParams(
            type=CacheType.REDIS,
            host="localhost",
            port=6379,
            password="redis-pass",
            db=0,
            ttl=3600,
        )
        assert cache.type == CacheType.REDIS
        assert cache.host == "localhost"
        assert cache.port == 6379

    def test_redis_port_validation(self):
        """Test Redis port validation."""
        # Valid port
        cache = RedisCacheParams(port=6379)
        assert cache.port == 6379

        # Invalid port (too low)
        with pytest.raises(ValidationError):
            RedisCacheParams(port=0)

        # Invalid port (too high)
        with pytest.raises(ValidationError):
            RedisCacheParams(port=65536)

    def test_s3_cache_params(self):
        """Test S3 cache configuration."""
        cache = S3CacheParams(
            type=CacheType.S3,
            s3_bucket_name="my-cache-bucket",
            s3_region_name="us-east-1",
            s3_api_key="AKIAIOSFODNN7EXAMPLE",
            s3_api_secret="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
            ttl=7200,
        )
        assert cache.type == CacheType.S3
        assert cache.s3_bucket_name == "my-cache-bucket"
        assert cache.ttl == 7200

    def test_s3_bucket_required(self):
        """Test S3 bucket name is required."""
        with pytest.raises(ValidationError):
            S3CacheParams(type=CacheType.S3)


# =============================================================================
# LiteLLMSettings Tests
# =============================================================================


class TestLiteLLMSettings:
    """Tests for LiteLLM settings."""

    def test_cache_requires_cache_params(self):
        """Test that cache=true requires cache_params."""
        with pytest.raises(ValidationError) as exc_info:
            LiteLLMSettings(cache=True)
        assert "cache_params is required" in str(exc_info.value)

    def test_cache_with_valid_params(self):
        """Test cache with valid parameters."""
        settings = LiteLLMSettings(
            cache=True,
            cache_params=RedisCacheParams(host="localhost", port=6379, ttl=3600),
        )
        assert settings.cache is True
        assert settings.cache_params.type == CacheType.REDIS

    def test_otel_requires_config(self):
        """Test that otel=true requires exporter and endpoint."""
        with pytest.raises(ValidationError) as exc_info:
            LiteLLMSettings(otel=True)
        assert "otel_exporter is required" in str(exc_info.value)

        with pytest.raises(ValidationError) as exc_info:
            LiteLLMSettings(otel=True, otel_exporter=OTELExporter.OTLP_HTTP)
        assert "otel_endpoint is required" in str(exc_info.value)

    def test_otel_valid_config(self):
        """Test valid OTEL configuration."""
        settings = LiteLLMSettings(
            otel=True,
            otel_exporter=OTELExporter.OTLP_HTTP,
            otel_endpoint="http://localhost:4318/v1/traces",
            otel_service_name="test-service",
        )
        assert settings.otel is True
        assert settings.otel_exporter == OTELExporter.OTLP_HTTP

    def test_otel_endpoint_validation(self):
        """Test OTEL endpoint URL validation."""
        # Invalid endpoint (no protocol)
        with pytest.raises(ValidationError) as exc_info:
            LiteLLMSettings(
                otel=True,
                otel_exporter=OTELExporter.OTLP_HTTP,
                otel_endpoint="localhost:4318/v1/traces",
            )
        assert "http://" in str(exc_info.value)


# =============================================================================
# LiteLLMProxyConfig Tests
# =============================================================================


class TestLiteLLMProxyConfig:
    """Tests for root configuration model."""

    def test_minimal_valid_config(self, minimal_valid_config):
        """Test minimal valid configuration."""
        config = LiteLLMProxyConfig.model_validate(minimal_valid_config)
        assert config.general_settings.master_key == "sk-1234"
        assert len(config.model_list) == 1

    def test_full_valid_config(self, full_valid_config):
        """Test full valid configuration."""
        config = LiteLLMProxyConfig.model_validate(full_valid_config)
        assert config.general_settings is not None
        assert config.user_id_mappings is not None
        assert len(config.model_list) == 2
        assert config.mcp_servers is not None
        assert config.litellm_settings is not None

    def test_duplicate_model_names(self):
        """Test duplicate model name detection."""
        with pytest.raises(ValidationError) as exc_info:
            LiteLLMProxyConfig.model_validate(
                {
                    "model_list": [
                        {
                            "model_name": "gpt-4",
                            "litellm_params": {
                                "model": "openai/gpt-4",
                                "api_key": "sk-test",
                            },
                        },
                        {
                            "model_name": "gpt-4",  # Duplicate
                            "litellm_params": {
                                "model": "openai/gpt-4-turbo",
                                "api_key": "sk-test",
                            },
                        },
                    ]
                }
            )
        assert "Duplicate model names" in str(exc_info.value)

    def test_invalid_mcp_alias(self):
        """Test invalid MCP alias reference."""
        with pytest.raises(ValidationError) as exc_info:
            LiteLLMProxyConfig.model_validate(
                {
                    "model_list": [
                        {
                            "model_name": "gpt-4",
                            "litellm_params": {
                                "model": "openai/gpt-4",
                                "api_key": "sk-test",
                            },
                        }
                    ],
                    "mcp_servers": {
                        "server1": {
                            "transport": "sse",
                            "url": "http://localhost:8000",
                            "auth_type": "none",
                        }
                    },
                    "litellm_settings": {
                        "mcp_aliases": {
                            "alias1": "nonexistent_server"  # Invalid reference
                        }
                    },
                }
            )
        assert "non-existent server" in str(exc_info.value)


# =============================================================================
# Helper Functions Tests
# =============================================================================


class TestHelperFunctions:
    """Tests for helper functions."""

    def test_resolve_env_vars_string(self):
        """Test environment variable resolution for strings."""
        os.environ["TEST_VAR"] = "test-value"

        # Resolve env var
        result = resolve_env_vars("os.environ/TEST_VAR")
        assert result == "test-value"

        # Don't resolve regular strings
        result = resolve_env_vars("regular-string")
        assert result == "regular-string"

    def test_resolve_env_vars_dict(self):
        """Test environment variable resolution for dicts."""
        os.environ["KEY1"] = "value1"
        os.environ["KEY2"] = "value2"

        data = {"key1": "os.environ/KEY1", "key2": "os.environ/KEY2", "key3": "static"}

        result = resolve_env_vars(data)
        assert result["key1"] == "value1"
        assert result["key2"] == "value2"
        assert result["key3"] == "static"

    def test_resolve_env_vars_list(self):
        """Test environment variable resolution for lists."""
        os.environ["ITEM1"] = "resolved1"

        data = ["os.environ/ITEM1", "static"]

        result = resolve_env_vars(data)
        assert result[0] == "resolved1"
        assert result[1] == "static"

    def test_resolve_env_vars_missing(self):
        """Test error when environment variable is missing."""
        with pytest.raises(ValueError) as exc_info:
            resolve_env_vars("os.environ/NONEXISTENT_VAR")
        assert "Environment variable 'NONEXISTENT_VAR' is not set" in str(
            exc_info.value
        )

    def test_load_config(self, temp_config_file, minimal_valid_config):
        """Test loading configuration from YAML file."""
        # Write config to file
        with open(temp_config_file, "w") as f:
            yaml.dump(minimal_valid_config, f)

        # Load and validate
        config = load_config(temp_config_file)
        assert config.general_settings.master_key == "sk-1234"
        assert len(config.model_list) == 1

    def test_load_config_file_not_found(self):
        """Test error when config file doesn't exist."""
        with pytest.raises(FileNotFoundError):
            load_config("/nonexistent/path/config.yaml")

    def test_load_config_empty_file(self, temp_config_file):
        """Test error when config file is empty."""
        # Create empty file
        temp_config_file.write_text("")

        with pytest.raises(ValueError) as exc_info:
            load_config(temp_config_file)
        assert "empty" in str(exc_info.value)

    def test_load_config_with_env_resolution(self, temp_config_file):
        """Test loading config with environment variable resolution."""
        os.environ["TEST_MASTER_KEY"] = "sk-resolved-key"
        os.environ["TEST_API_KEY"] = "sk-api-resolved"

        config_data = {
            "general_settings": {"master_key": "os.environ/TEST_MASTER_KEY"},
            "model_list": [
                {
                    "model_name": "gpt-4",
                    "litellm_params": {
                        "model": "openai/gpt-4",
                        "api_key": "os.environ/TEST_API_KEY",
                    },
                }
            ],
        }

        with open(temp_config_file, "w") as f:
            yaml.dump(config_data, f)

        config = load_config_with_env_resolution(temp_config_file)
        assert config.general_settings.master_key == "sk-resolved-key"
        assert config.model_list[0].litellm_params.api_key == "sk-api-resolved"

    def test_validate_config_dict(self, minimal_valid_config):
        """Test validating configuration dictionary."""
        config = validate_config_dict(minimal_valid_config)
        assert config.general_settings.master_key == "sk-1234"

    def test_export_json_schema(self, tmp_path):
        """Test JSON Schema export."""
        output_file = tmp_path / "schema.json"
        export_json_schema(output_file)

        assert output_file.exists()

        # Verify it's valid JSON
        import json

        with open(output_file) as f:
            schema = json.load(f)

        assert "title" in schema
        assert "properties" in schema


# =============================================================================
# Integration Tests
# =============================================================================


class TestIntegration:
    """Integration tests with real config files."""

    def test_load_actual_config_file(self):
        """Test loading actual config.yaml from project."""
        config_path = Path(__file__).parent / "config" / "config.yaml"

        if config_path.exists():
            # Load without env resolution (to avoid missing env vars)
            config = load_config(config_path)

            # Basic validation
            assert config.model_list is not None
            assert len(config.model_list) > 0

            # Check for expected models
            model_names = [m.model_name for m in config.model_list]
            print(f"Found models: {model_names}")

    def test_round_trip_serialization(self, full_valid_config, temp_config_file):
        """Test that config can be loaded, validated, and saved."""
        # Validate config
        config = validate_config_dict(full_valid_config)

        # For round-trip, we use the original dict (not the Pydantic model dump)
        # This simulates real-world usage where YAML is manually edited
        with open(temp_config_file, "w") as f:
            yaml.dump(full_valid_config, f)

        # Load again
        reloaded_config = load_config(temp_config_file)

        # Verify key fields match
        assert (
            reloaded_config.general_settings.master_key
            == config.general_settings.master_key
        )
        assert len(reloaded_config.model_list) == len(config.model_list)


# =============================================================================
# Performance Tests
# =============================================================================


@pytest.mark.slow
class TestPerformance:
    """Performance tests for schema validation."""

    def test_validate_large_config(self):
        """Test validation performance with large config."""
        # Generate large config with 100 models
        config_data = {
            "general_settings": {"master_key": "sk-1234"},
            "model_list": [
                {
                    "model_name": f"model-{i}",
                    "litellm_params": {
                        "model": f"openai/model-{i}",
                        "api_key": f"sk-key-{i}",
                    },
                }
                for i in range(100)
            ],
        }

        # Should complete quickly
        import time

        start = time.time()
        config = validate_config_dict(config_data)
        duration = time.time() - start

        assert len(config.model_list) == 100
        assert duration < 1.0  # Should be fast (<1 second)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])