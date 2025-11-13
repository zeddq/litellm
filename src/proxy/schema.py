"""
Pydantic schema for LiteLLM proxy configuration validation.

This module provides comprehensive Pydantic models for validating config.yaml
files used by the LiteLLM Memory Proxy. It includes:
- Type validation for all configuration sections
- Custom validators for regex patterns, URLs, and cross-field validation
- Environment variable resolution support
- Helper functions for loading and validating configurations

Example:
    >>> from proxy.schema import load_config
    >>> config = load_config("config.yaml")
    >>> print(config.general_settings.master_key)
    'sk-1234'
"""

import logging
import os
import re
from enum import Enum, StrEnum
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Union, Self

import yaml
from pydantic import (
    BaseModel,
    Field,
    HttpUrl,
    field_validator,
    model_validator,
    ConfigDict,
)
from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)


# =============================================================================
# Type Aliases
# =============================================================================

EnvVarStr = str  # Supports "value" or "os.environ/VAR_NAME"


# =============================================================================
# Enums
# =============================================================================


class DatabaseType(str, Enum):
    """Supported database types for LiteLLM proxy."""

    PRISMA = "prisma"
    POSTGRESQL = "postgresql"
    POSTGRES = "postgres"
    SQLITE = "sqlite"


class CacheType(str, Enum):
    """Supported cache backend types."""

    REDIS = "redis"
    S3 = "s3"
    MEMORY = "memory"


class OTELExporter(StrEnum):
    """OpenTelemetry exporter types."""

    OTLP_HTTP = "otlp_http"
    OTLP_GRPC = "otlp_grpc"
    CONSOLE = "console"


class MCPTransport(str, Enum):
    """MCP server transport protocols."""

    SSE = "sse"
    STDIO = "stdio"


class MCPAuthType(str, Enum):
    """MCP server authentication types."""

    NONE = "none"
    BEARER = "bearer"
    BASIC = "basic"


class ThinkingType(str, Enum):
    """Extended thinking configuration types."""

    ENABLED = "enabled"
    DISABLED = "disabled"


# =============================================================================
# Helper Functions for Environment Variable Synchronization
# =============================================================================


def sync_field_to_env(field_name: str, field_value: Any, env_var_name: str) -> None:
    """
    Synchronize a field value to an environment variable.

    This helper function sets an environment variable to the resolved value
    of a Pydantic field. It handles environment variable reference resolution
    and type conversion automatically.

    Args:
        field_name: Name of the field being synced (for logging)
        field_value: Value to sync (can contain env var references like 'os.environ/VAR')
        env_var_name: Target environment variable name

    Example:
        >>> sync_field_to_env("database_url", "postgresql://localhost/db", "DATABASE_URL")
        >>> os.getenv("DATABASE_URL")
        'postgresql://localhost/db'

        >>> # With env var reference
        >>> os.environ["SOURCE_URL"] = "postgresql://from-env/db"
        >>> sync_field_to_env("database_url", "os.environ/SOURCE_URL", "DATABASE_URL")
        >>> os.getenv("DATABASE_URL")
        'postgresql://from-env/db'
    """
    if field_value is None:
        return

    # Resolve any env var references in the value first
    resolved_value = resolve_env_vars(field_value)

    # Convert to string and set environment variable
    os.environ[env_var_name] = str(resolved_value)

    logger.debug(f"Synced field '{field_name}' → {env_var_name}")

def sync_model_fields_to_env(model: BaseModel) -> None:
    """
    Sync all fields marked with sync_to_env metadata to environment variables.

    This function scans a Pydantic model's fields for 'sync_to_env' markers
    in the field's json_schema_extra metadata and automatically sets the
    corresponding environment variables to the field values.

    This enables declarative environment variable management where field
    definitions explicitly declare which env vars they should populate.

    Args:
        model: Pydantic model instance to process

    Example:
        >>> class MyConfig(BaseModel):
        ...     db_url: str = Field(
        ...         ...,
        ...         json_schema_extra={"sync_to_env": "DATABASE_URL"}
        ...     )
        >>>
        >>> config = MyConfig(db_url="postgresql://localhost/db")
        >>> sync_model_fields_to_env(config)
        >>> os.getenv("DATABASE_URL")
        'postgresql://localhost/db'

    Note:
        If multiple fields sync to the same environment variable, the last
        field processed will win. Field processing order follows Pydantic's
        model_fields dictionary order.
    """
    for field_name, field_info in model.__class__.model_fields.items():
        # Check if field has sync_to_env metadata
        extras = field_info.json_schema_extra or {}
        env_var_name = extras.get("sync_to_env")

        if env_var_name:
            field_value = getattr(model, field_name, None)
            sync_field_to_env(field_name, field_value, str(env_var_name))


class EnvSyncMixin(BaseModel):
    """
    Mixin to automatically sync field values to environment variables.

    This mixin provides automatic environment variable synchronization for
    Pydantic models. Fields marked with json_schema_extra={"sync_to_env": "ENV_VAR"}
    will have their values automatically written to the specified environment
    variable after model validation.

    This is useful for:
    - Ensuring environment variables match config file values
    - Making config values available to subprocesses or external tools
    - Maintaining backward compatibility with env-var-based configuration

    Usage:
        Inherit from this mixin in your Pydantic model and mark fields
        with the sync_to_env metadata:

        >>> class MySettings(EnvSyncMixin):
        ...     database_url: str = Field(
        ...         ...,
        ...         description="Database connection URL",
        ...         json_schema_extra={"sync_to_env": "DATABASE_URL"}
        ...     )
        ...     redis_host: str = Field(
        ...         default="localhost",
        ...         json_schema_extra={"sync_to_env": "REDIS_HOST"}
        ...     )
        >>>
        >>> # When model is instantiated, env vars are automatically set
        >>> settings = MySettings(database_url="postgresql://localhost/db")
        >>> os.getenv("DATABASE_URL")
        'postgresql://localhost/db'
        >>> os.getenv("REDIS_HOST")
        'localhost'

    Note:
        - Synchronization happens AFTER validation in the model_validator
        - Environment variable references (os.environ/VAR) are resolved before syncing
        - None values are skipped (don't set env vars)
        - Non-string values are converted to strings
        - If multiple fields sync to the same env var, last field wins
    """

    @model_validator(mode='after')
    def _sync_fields_to_env(self) -> Self:
        """Sync marked fields to environment variables after validation."""
        sync_model_fields_to_env(self)
        return self


# =============================================================================
# General Settings Models
# =============================================================================


class GeneralSettings(EnvSyncMixin):
    """
    General proxy settings including authentication, database, and forwarding rules.

    Attributes:
        master_key: Master API key for proxy authentication
        forward_openai_org_id: Whether to forward OpenAI organization ID headers
        forward_client_headers_to_llm_api: Forward all client headers to LLM providers
        database_url: Database connection URL (supports env vars, auto-syncs to DATABASE_URL)
        database_connection_pool_limit: Maximum database connections in pool
        store_model_in_db: Whether to store model information in database
        store_prompts_in_spend_logs: Whether to log prompts in spending logs
    """

    model_config = ConfigDict(extra="allow")

    master_key: EnvVarStr = Field(
        ...,
        description="Master API key for proxy authentication. Can be literal or 'os.environ/VAR_NAME'",
    )
    forward_openai_org_id: bool = Field(
        default=False,
        description="Forward OpenAI-Organization-Id header to LLM providers",
    )
    forward_client_headers_to_llm_api: bool = Field(
        default=False,
        description="Forward all client headers to LLM API (recommended for Supermemory)",
    )
    database_url: Optional[EnvVarStr] = Field(
        default=None,
        description="Database connection URL. Format: postgresql://user:pass@host:port/db",
        json_schema_extra={"sync_to_env": "DATABASE_URL"},
    )
    database_connection_pool_limit: int = Field(
        default=100,
        ge=1,
        le=1000,
        description="Maximum number of database connections in pool",
    )
    store_model_in_db: bool = Field(
        default=True,
        description="Store model information in database for analytics",
    )
    store_prompts_in_spend_logs: bool = Field(
        default=False,
        description="Log full prompts in spending logs (warning: may contain sensitive data)",
    )

    @field_validator("master_key", "database_url")
    @classmethod
    def validate_env_var(cls, v: Optional[str]) -> Optional[str]:
        """Validate environment variable references but don't resolve them yet."""
        if v is None:
            return v
        if v.startswith("os.environ/"):
            env_var = v.split("/", 1)[1]
            if not env_var.isidentifier():
                raise ValueError(
                    f"Invalid environment variable name: {env_var}. "
                    f"Must be a valid Python identifier."
                )
        return v


# =============================================================================
# User ID Mapping Models (Memory Routing)
# =============================================================================


class HeaderPattern(BaseModel):
    """
    Pattern-based user ID detection from HTTP headers.

    Attributes:
        header: HTTP header name (case-insensitive)
        pattern: Regex pattern to match against header value
        user_id: User ID to assign when pattern matches
    """

    model_config = ConfigDict(extra="forbid")

    header: str = Field(
        ...,
        description="HTTP header name to match (e.g., 'user-agent', 'x-custom-id')",
        min_length=1,
    )
    pattern: str = Field(
        ...,
        description="Regex pattern to match header value (e.g., '^OpenAIClientImpl/Java')",
        min_length=1,
    )
    user_id: str = Field(
        ...,
        description="User ID to assign when pattern matches",
        min_length=1,
    )
    pattern_compiled: re.Pattern | None = Field(
        default=None,
        exclude=True,  # Exclude from serialization
        description="Compiled regex pattern (auto-generated)",
    )

    @field_validator("header")
    @classmethod
    def normalize_header_name(cls, v: str) -> str:
        """Normalize header name to lowercase for case-insensitive matching."""
        return v.lower().strip()

    @field_validator("pattern")
    @classmethod
    def validate_regex_pattern(cls, v: str) -> str:
        """Validate that pattern is a valid regex and compiles successfully."""
        try:
            re.compile(v)
        except re.error as e:
            raise ValueError(f"Invalid regex pattern '{v}': {e}")
        return v

    @model_validator(mode="after")
    def compile_pattern(self) -> "HeaderPattern":
        """Compile the regex pattern for efficient matching."""
        self.pattern_compiled = re.compile(self.pattern, re.IGNORECASE)
        return self

    @field_validator("user_id")
    @classmethod
    def validate_user_id(cls, v: str) -> str:
        """Ensure user_id is valid (no control characters)."""
        if any(c.isspace() or ord(c) < 32 for c in v):
            raise ValueError(
                f"user_id contains invalid characters (whitespace or control chars): {v}"
            )
        return v.strip()


class UserIDMappings(BaseModel):
    """
    User ID detection and routing configuration for Supermemory integration.

    This enables automatic user/project isolation by detecting clients
    via HTTP headers and assigning unique user IDs for memory segregation.

    Attributes:
        custom_header: Header name for explicit user ID specification
        header_patterns: List of patterns for auto-detecting user IDs
        default_user_id: Fallback user ID when no pattern matches
    """

    model_config = ConfigDict(extra="forbid")

    custom_header: str = Field(
        default="x-memory-user-id",
        description="Custom header for explicit user ID (takes precedence over patterns)",
        min_length=1,
    )
    header_patterns: List[HeaderPattern] = Field(
        default_factory=list,
        description="Pattern-based user ID detection rules (evaluated in order)",
    )
    default_user_id: str = Field(
        default="default-dev",
        description="Default user ID when no pattern matches",
        min_length=1,
    )

    @field_validator("custom_header")
    @classmethod
    def normalize_custom_header(cls, v: str) -> str:
        """Normalize custom header name to lowercase."""
        return v.lower().strip()

    @model_validator(mode="after")
    def validate_unique_patterns(self) -> "UserIDMappings":
        """Ensure header/pattern combinations are unique."""
        seen = set()
        for pattern in self.header_patterns:
            key = (pattern.header, pattern.pattern)
            if key in seen:
                raise ValueError(
                    f"Duplicate pattern: header='{pattern.header}' pattern='{pattern.pattern}'"
                )
            seen.add(key)
        return self


# =============================================================================
# Model Configuration Models
# =============================================================================


class ThinkingConfig(BaseModel):
    """
    Extended thinking configuration for Claude models.

    Attributes:
        type: Whether extended thinking is enabled
        budget_tokens: Maximum tokens to allocate for thinking
    """

    model_config = ConfigDict(extra="forbid")

    type: ThinkingType = Field(
        default=ThinkingType.ENABLED,
        description="Enable or disable extended thinking mode",
    )
    budget_tokens: int = Field(
        default=4096,
        ge=1,
        le=100000,
        description="Maximum tokens for thinking (default: 4096)",
    )


class LiteLLMParams(BaseModel):
    """
    LiteLLM model parameters for provider integration.

    Attributes:
        model: Model identifier in format 'provider/model-name'
        api_key: API key for provider (supports env vars)
        api_base: Custom API base URL (e.g., for Supermemory)
        custom_llm_provider: Explicit provider name override
        extra_headers: Additional HTTP headers to send with requests
        thinking: Extended thinking configuration (Claude models)
        timeout: Request timeout in seconds
        max_retries: Maximum retry attempts on failure
        stream_timeout: Timeout for streaming responses
    """

    model_config = ConfigDict(extra="allow")  # Allow provider-specific params

    model: str = Field(
        ...,
        description="Model identifier (format: 'provider/model-name' e.g., 'openai/gpt-4')",
        min_length=1,
    )
    api_key: EnvVarStr = Field(
        ...,
        description="API key for provider. Use 'os.environ/VAR_NAME' for env vars",
    )
    api_base: Optional[str] = Field(
        default=None,
        description="Custom API base URL (e.g., for Supermemory integration)",
    )
    custom_llm_provider: Optional[str] = Field(
        default=None,
        description="Explicit provider name (e.g., 'anthropic', 'openai')",
    )
    extra_headers: Optional[Dict[str, EnvVarStr]] = Field(
        default=None,
        description="Additional HTTP headers for API requests",
    )
    thinking: Optional[Union[ThinkingConfig, Dict[str, Any]]] = Field(
        default=None,
        description="Extended thinking configuration (Claude models)",
    )
    timeout: Optional[float] = Field(
        default=None,
        ge=0.1,
        description="Request timeout in seconds",
    )
    max_retries: Optional[int] = Field(
        default=None,
        ge=0,
        description="Maximum retry attempts on failure",
    )
    stream_timeout: Optional[float] = Field(
        default=None,
        ge=0.1,
        description="Timeout for streaming responses",
    )
    web_search_options: Optional[dict] = Field(default=None)

    @field_validator("model")
    @classmethod
    def validate_model_format(cls, v: str) -> str:
        """Validate model identifier format (provider/model-name)."""
        if "/" not in v:
            raise ValueError(
                f"Model must be in format 'provider/model-name', got: {v}"
            )
        provider, model_name = v.split("/", 1)
        if not provider or not model_name:
            raise ValueError(
                f"Invalid model format. Both provider and model name required: {v}"
            )
        return v

    @field_validator("api_base")
    @classmethod
    def validate_api_base(cls, v: Optional[str]) -> Optional[str]:
        """Validate API base URL format."""
        if v is None:
            return v
        if not v.startswith(("http://", "https://")):
            raise ValueError(f"api_base must start with http:// or https://, got: {v}")
        return v


class ModelConfig(BaseModel):
    """
    Model configuration entry.

    Attributes:
        model_name: Public model name exposed by proxy
        litellm_params: LiteLLM-specific configuration
    """

    model_config = ConfigDict(extra="forbid")

    model_name: str = Field(
        ...,
        description="Public model name exposed by proxy (e.g., 'claude-sonnet-4.5')",
        min_length=1,
    )
    litellm_params: LiteLLMParams = Field(
        ...,
        description="LiteLLM model parameters",
    )
    model_info: Optional[dict] = Field(default=None, description="Additional model info")


# =============================================================================
# MCP Server Models
# =============================================================================


class MCPServerConfig(BaseModel):
    """
    MCP (Model Context Protocol) server configuration.

    Attributes:
        transport: Transport protocol (sse or stdio)
        url: Server URL (required for SSE transport)
        auth_type: Authentication type
        command: Command to start MCP server (required for stdio)
        args: Command arguments (for stdio)
        env: Environment variables for MCP server
    """

    model_config = ConfigDict(extra="forbid")

    transport: MCPTransport = Field(
        ...,
        description="Transport protocol (sse for HTTP, stdio for local process)",
    )
    url: Optional[str] = Field(
        default=None,
        description="Server URL (required for SSE transport)",
    )
    auth_type: MCPAuthType = Field(
        default=MCPAuthType.NONE,
        description="Authentication type (none, bearer, basic)",
    )
    command: Optional[str] = Field(
        default=None,
        description="Command to start MCP server (required for stdio)",
    )
    args: Optional[List[str]] = Field(
        default=None,
        description="Command line arguments (for stdio transport)",
    )
    env: Optional[Dict[str, str]] = Field(
        default=None,
        description="Environment variables for MCP server process",
    )

    @model_validator(mode="after")
    def validate_transport_requirements(self) -> "MCPServerConfig":
        """Validate transport-specific requirements."""
        if self.transport == MCPTransport.SSE and not self.url:
            raise ValueError("url is required when transport is 'sse'")
        if self.transport == MCPTransport.STDIO and not self.command:
            raise ValueError("command is required when transport is 'stdio'")
        return self

    @field_validator("url")
    @classmethod
    def validate_url_format(cls, v: Optional[str]) -> Optional[str]:
        """Validate URL format."""
        if v is None:
            return v
        if not v.startswith(("http://", "https://")):
            raise ValueError(f"URL must start with http:// or https://, got: {v}")
        return v


# =============================================================================
# Cache Configuration Models
# =============================================================================


class RedisCacheParams(EnvSyncMixin, BaseModel):
    """
    Redis cache configuration parameters.

    Attributes:
        type: Cache type (must be 'redis')
        host: Redis server host (auto-syncs to REDIS_HOST env var)
        port: Redis server port (auto-syncs to REDIS_PORT env var)
        password: Redis password (supports env vars, auto-syncs to REDIS_PASSWORD)
        db: Redis database number
        ttl: Cache TTL in seconds
        ssl: Enable SSL/TLS
    """

    model_config = ConfigDict(extra="forbid")

    type: Literal[CacheType.REDIS] = Field(
        default=CacheType.REDIS,
        description="Cache backend type (must be 'redis')",
    )
    host: str = Field(
        default="localhost",
        description="Redis server hostname or IP",
        json_schema_extra={"sync_to_env": "REDIS_HOST"},
    )
    port: int = Field(
        default=6379,
        ge=1,
        le=65535,
        description="Redis server port",
        json_schema_extra={"sync_to_env": "REDIS_PORT"},
    )
    password: Optional[EnvVarStr] = Field(
        default=None,
        description="Redis password (use 'os.environ/VAR' for env vars)",
        json_schema_extra={"sync_to_env": "REDIS_PASSWORD"},
    )
    db: int = Field(
        default=0,
        ge=0,
        description="Redis database number",
    )
    ttl: int = Field(
        default=3600,
        ge=0,
        description="Cache TTL (time-to-live) in seconds",
    )
    ssl: bool = Field(
        default=False,
        description="Enable SSL/TLS connection to Redis",
    )


class S3CacheParams(BaseModel):
    """
    S3 cache configuration parameters.

    Attributes:
        type: Cache type (must be 's3')
        s3_bucket_name: S3 bucket name
        s3_region_name: AWS region
        s3_api_key: AWS access key ID (supports env vars)
        s3_api_secret: AWS secret access key (supports env vars)
        ttl: Cache TTL in seconds
    """

    model_config = ConfigDict(extra="forbid")

    type: Literal[CacheType.S3] = Field(
        default=CacheType.S3,
        description="Cache backend type (must be 's3')",
    )
    s3_bucket_name: str = Field(
        ...,
        description="S3 bucket name for cache storage",
        min_length=1,
    )
    s3_region_name: str = Field(
        default="us-east-1",
        description="AWS region for S3 bucket",
    )
    s3_api_key: Optional[EnvVarStr] = Field(
        default=None,
        description="AWS access key ID (use 'os.environ/VAR' for env vars)",
    )
    s3_api_secret: Optional[EnvVarStr] = Field(
        default=None,
        description="AWS secret access key (use 'os.environ/VAR' for env vars)",
    )
    ttl: int = Field(
        default=3600,
        ge=0,
        description="Cache TTL in seconds",
    )


# Union type for cache params
CacheParams = Union[RedisCacheParams, S3CacheParams]


# =============================================================================
# Context Retrieval Models
# =============================================================================


class QueryStrategy(str, Enum):
    """Strategy for extracting query from messages for context retrieval."""

    LAST_USER = "last_user"
    FIRST_USER = "first_user"
    ALL_USER = "all_user"
    LAST_ASSISTANT = "last_assistant"


class InjectionStrategy(str, Enum):
    """Strategy for injecting retrieved context into messages."""

    SYSTEM = "system"
    USER_PREFIX = "user_prefix"
    USER_SUFFIX = "user_suffix"


class ContextRetrievalConfig(BaseModel):
    """
    Configuration for Supermemory context retrieval.

    Enables automatic enhancement of prompts with relevant user memories/documents
    retrieved from Supermemory's /v4/profile endpoint.

    Attributes:
        enabled: Enable context retrieval globally
        api_key: Supermemory API key (supports env vars)
        base_url: Supermemory API base URL
        query_strategy: How to extract query from messages
        injection_strategy: Where to inject context in messages
        container_tag: Default container tag for queries
        max_context_length: Maximum context length in characters
        max_results: Maximum number of results to retrieve
        timeout: Request timeout in seconds
        enabled_for_models: List of model names to enable context retrieval for
        disabled_for_models: List of model names to disable context retrieval for
    """

    model_config = ConfigDict(extra="forbid")

    enabled: bool = Field(
        default=False,
        description="Enable context retrieval feature globally",
    )
    api_key: Optional[EnvVarStr] = Field(
        default=None,
        description="Supermemory API key (use 'os.environ/VAR' for env vars)",
    )
    base_url: str = Field(
        default="https://api.supermemory.ai",
        description="Supermemory API base URL",
    )
    query_strategy: QueryStrategy = Field(
        default=QueryStrategy.LAST_USER,
        description="Strategy for extracting query from messages",
    )
    injection_strategy: InjectionStrategy = Field(
        default=InjectionStrategy.SYSTEM,
        description="Strategy for injecting context into messages",
    )
    container_tag: str = Field(
        default="supermemory",
        description="Default container tag for Supermemory queries",
    )
    max_context_length: int = Field(
        default=4000,
        ge=100,
        le=100000,
        description="Maximum context length in characters",
    )
    max_results: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Maximum number of results to retrieve from Supermemory",
    )
    timeout: float = Field(
        default=10.0,
        ge=1.0,
        le=60.0,
        description="Request timeout in seconds",
    )
    enabled_for_models: Optional[List[str]] = Field(
        default=None,
        description="Model names to enable context retrieval for (whitelist)",
    )
    disabled_for_models: Optional[List[str]] = Field(
        default=None,
        description="Model names to disable context retrieval for (blacklist)",
    )

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, v: str) -> str:
        """Validate base URL format."""
        if not v.startswith(("http://", "https://")):
            raise ValueError(f"base_url must start with http:// or https://, got: {v}")
        return v.rstrip("/")

    @model_validator(mode="after")
    def validate_api_key_if_enabled(self) -> "ContextRetrievalConfig":
        """Ensure API key is provided when context retrieval is enabled."""
        if self.enabled and not self.api_key:
            raise ValueError(
                "api_key is required when context_retrieval.enabled=true"
            )
        return self

    @model_validator(mode="after")
    def validate_model_filters(self) -> "ContextRetrievalConfig":
        """Ensure enabled_for_models and disabled_for_models are not both set."""
        if self.enabled_for_models and self.disabled_for_models:
            raise ValueError(
                "Cannot specify both enabled_for_models and disabled_for_models. "
                "Use one or the other."
            )
        return self


# =============================================================================
# LiteLLM Settings Models
# =============================================================================


class LiteLLMSettings(EnvSyncMixin, BaseModel):
    """
    General LiteLLM proxy settings including database, callbacks, OTEL, and cache.

    Attributes:
        database_type: Database backend type
        database_url: Database connection URL (auto-syncs to DATABASE_URL env var)
        store_model_in_db: Store model metadata in database
        success_callback: Success event callbacks (e.g., ['postgres', 'otel'])
        failure_callback: Failure event callbacks
        otel: Enable OpenTelemetry tracing
        otel_exporter: OTEL exporter type
        otel_endpoint: OTEL collector endpoint URL
        otel_service_name: Service name for OTEL traces
        otel_headers: Additional OTEL headers
        cache: Enable response caching
        cache_params: Cache configuration parameters
        mcp_aliases: MCP server name aliases
        set_verbose: Enable verbose logging
        json_logs: Output logs in JSON format
        drop_params: Drop unsupported parameters from requests
        forward_traceparent_to_llm_provider: Forward traceparent header for distributed tracing
    """

    model_config = ConfigDict(extra="allow")  # Allow additional LiteLLM settings

    # Database settings
    database_type: Optional[DatabaseType] = Field(
        default=None,
        description="Database backend type (prisma, postgresql, sqlite)",
    )
    database_url: Optional[EnvVarStr] = Field(
        default=None,
        description="Database connection URL",
        json_schema_extra={"sync_to_env": "DATABASE_URL"},
    )
    store_model_in_db: bool = Field(
        default=True,
        description="Store model metadata in database",
    )

    # Callback settings
    success_callback: Optional[List[str]] = Field(
        default=None,
        description="Success callbacks (e.g., ['postgres', 'otel'])",
    )
    failure_callback: Optional[List[str]] = Field(
        default=None,
        description="Failure callbacks (e.g., ['postgres', 'otel'])",
    )

    # OpenTelemetry settings
    otel: bool = Field(
        default=False,
        description="Enable OpenTelemetry tracing",
    )
    otel_exporter: Optional[OTELExporter] = Field(
        default=None,
        description="OTEL exporter type (otlp_http, otlp_grpc, console)",
        json_schema_extra={"sync_to_env": "OTEL_EXPORTER"},
    )
    otel_endpoint: Optional[str] = Field(
        default=None,
        description="OTEL collector endpoint URL (e.g., http://localhost:4318/v1/traces)",
        json_schema_extra={"sync_to_env": "OTEL_ENDPOINT"},
    )
    otel_service_name: Optional[str] = Field(
        default="litellm-proxy",
        description="Service name for OTEL traces",
        json_schema_extra={"sync_to_env": "OTEL_SERVICE"},
    )
    otel_headers: Optional[str] = Field(
        default="",
        description="Additional OTEL headers (comma-separated key=value pairs)",
        json_schema_extra={"sync_to_env": "OTEL_HEADERS"},
    )

    # Cache settings
    cache: bool = Field(
        default=False,
        description="Enable response caching",
    )
    cache_params: Optional[Union[RedisCacheParams, S3CacheParams, Dict[str, Any]]] = (
        Field(
            default=None,
            description="Cache configuration (Redis or S3)",
        )
    )

    # MCP settings
    mcp_aliases: Optional[Dict[str, str]] = Field(
        default=None,
        description="MCP server name aliases (e.g., {'jetbrains': 'jetbrains_mcp'})",
    )

    # Logging settings
    set_verbose: bool = Field(
        default=False,
        description="Enable verbose logging",
    )
    json_logs: bool = Field(
        default=False,
        description="Output logs in JSON format",
    )
    drop_params: bool = Field(
        default=False,
        description="Drop unsupported parameters instead of erroring",
    )

    # Distributed tracing
    forward_traceparent_to_llm_provider: bool = Field(
        default=False,
        description="Forward traceparent header to LLM providers for distributed tracing",
    )

    @model_validator(mode="after")
    def validate_cache_config(self) -> "LiteLLMSettings":
        """Validate cache configuration when cache is enabled."""
        if self.cache and not self.cache_params:
            raise ValueError("cache_params is required when cache=true")
        return self

    @model_validator(mode="after")
    def validate_otel_config(self) -> "LiteLLMSettings":
        """Validate OTEL configuration when OTEL is enabled."""
        if self.otel:
            if not self.otel_exporter:
                raise ValueError("otel_exporter is required when otel=true")
            if not self.otel_endpoint:
                raise ValueError("otel_endpoint is required when otel=true")
        return self

    @field_validator("otel_endpoint")
    @classmethod
    def validate_otel_endpoint(cls, v: Optional[str]) -> Optional[str]:
        """Validate OTEL endpoint URL format."""
        if v is None:
            return v
        if not v.startswith(("http://", "https://")):
            raise ValueError(
                f"otel_endpoint must start with http:// or https://, got: {v}"
            )
        return v


# =============================================================================
# Root Configuration Model
# =============================================================================


class LiteLLMProxyConfig(BaseModel):
    """
    Root configuration model for LiteLLM Memory Proxy.

    This is the top-level schema that validates the entire config.yaml file.

    Attributes:
        general_settings: General proxy settings (authentication, database, etc.)
        user_id_mappings: User ID detection and routing configuration
        model_list: List of available models and their configurations
        mcp_servers: MCP server configurations
        litellm_settings: LiteLLM-specific settings (callbacks, OTEL, cache, etc.)
        context_retrieval: Context retrieval configuration for Supermemory integration
        tool_execution: Tool execution configuration for automatic tool calling
    """

    model_config = ConfigDict(extra="forbid")

    general_settings: Optional[GeneralSettings] = Field(
        default=None,
        description="General proxy settings",
    )
    user_id_mappings: Optional[UserIDMappings] = Field(
        default=None,
        description="User ID detection and routing configuration",
    )
    model_list: List[ModelConfig] = Field(
        default_factory=list,
        description="List of available models",
    )
    mcp_servers: Optional[Dict[str, MCPServerConfig]] = Field(
        default=None,
        description="MCP server configurations (key: server name)",
    )
    litellm_settings: Optional[LiteLLMSettings] = Field(
        default=None,
        description="LiteLLM proxy settings",
    )
    context_retrieval: Optional[ContextRetrievalConfig] = Field(
        default=None,
        description="Context retrieval configuration for Supermemory integration",
    )
    tool_execution: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Tool execution configuration for automatic tool calling",
    )

    @model_validator(mode="after")
    def validate_unique_model_names(self) -> "LiteLLMProxyConfig":
        """Ensure all model names are unique."""
        model_names = [model.model_name for model in self.model_list]
        duplicates = [name for name in model_names if model_names.count(name) > 1]
        if duplicates:
            raise ValueError(
                f"Duplicate model names found: {', '.join(set(duplicates))}"
            )
        return self

    @model_validator(mode="after")
    def validate_mcp_aliases(self) -> "LiteLLMProxyConfig":
        """Validate MCP aliases reference existing servers."""
        if (
            self.litellm_settings
            and self.litellm_settings.mcp_aliases
            and self.mcp_servers
        ):
            for alias, server_name in self.litellm_settings.mcp_aliases.items():
                if server_name not in self.mcp_servers:
                    raise ValueError(
                        f"MCP alias '{alias}' references non-existent server '{server_name}'"
                    )
        return self


# =============================================================================
# Helper Functions
# =============================================================================


def resolve_env_vars(value: Any) -> Any:
    """
    Recursively resolve environment variable references in configuration values.

    Supports the format: "os.environ/VAR_NAME"

    Args:
        value: Configuration value (can be str, dict, list, or any JSON type)

    Returns:
        Resolved value with environment variables substituted

    Raises:
        ValueError: If referenced environment variable is not set

    Example:
        >>> os.environ["MY_KEY"] = "secret-123"
        >>> resolve_env_vars("os.environ/MY_KEY")
        'secret-123'
        >>> resolve_env_vars({"key": "os.environ/MY_KEY"})
        {'key': 'secret-123'}
    """
    if isinstance(value, str):
        if value.startswith("os.environ/"):
            env_var = value.split("/", 1)[1]
            if env_var not in os.environ:
                raise ValueError(
                    f"Environment variable '{env_var}' is not set. "
                    f"Required by config value: {value}"
                )
            return os.environ[env_var]
        return value
    elif isinstance(value, dict):
        return {k: resolve_env_vars(v) for k, v in value.items()}
    elif isinstance(value, list):
        return [resolve_env_vars(item) for item in value]
    else:
        return value


def _load_yaml_file(config_path: Path) -> Dict[str, Any]:
    """
    Load and parse YAML configuration file.

    Args:
        config_path: Path to config.yaml file

    Returns:
        Parsed YAML as dictionary

    Raises:
        FileNotFoundError: If config file doesn't exist
        ValueError: If config file is empty
        yaml.YAMLError: If YAML parsing fails
    """
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(config_path, "r", encoding="utf-8") as f:
        raw_data = yaml.safe_load(f)

    if raw_data is None:
        raise ValueError(f"Config file is empty: {config_path}")

    return raw_data


def load_config(config_path: Union[str, Path]) -> LiteLLMProxyConfig:
    """
    Load and validate LiteLLM proxy configuration from YAML file.

    This function:
    1. Loads YAML configuration file
    2. Validates structure against Pydantic schema
    3. Does NOT resolve environment variables (handled at runtime)

    Args:
        config_path: Path to config.yaml file

    Returns:
        Validated LiteLLMProxyConfig instance

    Raises:
        FileNotFoundError: If config file doesn't exist
        yaml.YAMLError: If YAML parsing fails
        pydantic.ValidationError: If configuration is invalid

    Example:
        >>> validated_config = load_config("config.yaml")
        >>> print(validated_config.model_list[0].model_name)
        'claude-sonnet-4.5'
    """
    config_path = Path(config_path)
    raw_config = _load_yaml_file(config_path)

    # Validate configuration (without resolving env vars)
    validated_config = LiteLLMProxyConfig.model_validate(raw_config)

    return validated_config


def load_config_with_env_resolution(
    config_path: Union[str, Path],
) -> LiteLLMProxyConfig:
    """
    Load configuration and resolve all environment variables.

    WARNING: This function resolves env vars immediately. Use load_config()
    instead if you want to delay env var resolution until runtime.

    Args:
        config_path: Path to config.yaml file

    Returns:
        Validated LiteLLMProxyConfig with all env vars resolved

    Raises:
        ValueError: If any required environment variable is not set

    Example:
        >>> resolved_config = load_config_with_env_resolution("config.yaml")
        >>> print(resolved_config.general_settings.master_key)
        'sk-1234'  # Actual value, not 'os.environ/MASTER_KEY'
    """
    config_path = Path(config_path)
    raw_config = _load_yaml_file(config_path)

    # Resolve environment variables
    resolved_data = resolve_env_vars(raw_config)

    # Validate resolved configuration
    resolved_config = LiteLLMProxyConfig.model_validate(resolved_data)

    return resolved_config


def export_json_schema(output_path: Union[str, Path]) -> None:
    """
    Export JSON Schema for LiteLLM configuration.

    Useful for:
    - IDE autocompletion in YAML files
    - Documentation generation
    - Third-party validation tools

    Args:
        output_path: Path to save JSON Schema file

    Example:
        >>> export_json_schema("config_schema.json")
    """
    output_path = Path(output_path)

    schema = LiteLLMProxyConfig.model_json_schema()

    with open(output_path, "w", encoding="utf-8") as f:
        import json

        json.dump(schema, f, indent=2)

    print(f"JSON Schema exported to: {output_path}")


def validate_config_dict(input_dict: Dict[str, Any]) -> LiteLLMProxyConfig:
    """
    Validate a configuration dictionary (useful for testing).

    Args:
        input_dict: Configuration as Python dict

    Returns:
        Validated LiteLLMProxyConfig instance

    Raises:
        pydantic.ValidationError: If configuration is invalid

    Example:
        >>> test_config = {
        ...     "model_list": [
        ...         {
        ...             "model_name": "gpt-4",
        ...             "litellm_params": {
        ...                 "model": "openai/gpt-4",
        ...                 "api_key": "sk-..."
        ...             }
        ...         }
        ...     ]
        ... }
        >>> validated = validate_config_dict(test_config)
    """
    return LiteLLMProxyConfig.model_validate(input_dict)


# =============================================================================
# CLI Entrypoint (for testing)
# =============================================================================


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python schema.py <config.yaml>")
        sys.exit(1)

    config_file = sys.argv[1]

    try:
        loaded_config = load_config(config_file)
        print(f"Configuration valid: {config_file}")
        print(f"\nModels: {len(loaded_config.model_list)}")
        for model in loaded_config.model_list:
            print(f"  - {model.model_name}")

        if loaded_config.mcp_servers:
            print(f"\nMCP Servers: {len(loaded_config.mcp_servers)}")
            for name, server in loaded_config.mcp_servers.items():
                print(f"  - {name} ({server.transport.value})")

    except Exception as e:
        print(f"Configuration invalid: {e}")
        sys.exit(1)
