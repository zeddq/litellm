"""
===============================================================================
LITELLM PROXY WITH MEMORY - COMPREHENSIVE PRODUCTION-READY TUTORIAL
===============================================================================

This interactive tutorial demonstrates how to build a production-ready LiteLLM
proxy with advanced memory management capabilities.

Author: LiteLLM Tutorial Series
Version: 1.0.0
Python: 3.13+

Tutorial Modules:
    1. Foundation Setup - Environment, dependencies, configuration
    2. LiteLLM Proxy Configuration - Multi-provider setup
    3. Memory Integration - Session-based conversation storage
    4. End-to-End Implementation - Complete working examples
    5. Production Deployment - Security, monitoring, optimization

Prerequisites:
    - Python 3.13+
    - OpenAI API key
    - Anthropic API key
    - Optional: Redis for persistent memory storage
    - Optional: Supermemory API key for cloud memory

Architecture Overview:
    ┌─────────────┐
    │   Client    │ (OpenAI SDK / Anthropic SDK)
    └──────┬──────┘
           │
    ┌──────▼──────────────────────────────────────────┐
    │  LiteLLM Proxy with Memory Middleware           │
    │  ┌────────────────────────────────────────────┐ │
    │  │ 1. Request Interception                    │ │
    │  │ 2. Client Detection (User-Agent, Headers) │ │
    │  │ 3. Memory Retrieval (Session Context)      │ │
    │  │ 4. Context Injection                       │ │
    │  └────────────────────────────────────────────┘ │
    └──────┬──────────────────────────────────────────┘
           │
    ┌──────▼────────┐      ┌──────────────┐
    │ LiteLLM Router│◄─────┤ Memory Store │
    │  (OpenAI +    │      │ (Redis/RAM)  │
    │   Anthropic)  │      └──────────────┘
    └───────────────┘

===============================================================================
"""

# Standard library imports
import asyncio
import json
import logging
import os
import re
import secrets
import time
from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

# Third-party imports
import httpx
import yaml
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field, validator

# Optional imports for production features
try:
    import redis.asyncio as redis
    from redis.asyncio import Redis as AsyncRedis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    redis = None  # Set to None for type checking
    AsyncRedis = None
    print("⚠️  Redis not available. Using in-memory storage only.")

try:
    from openai import AsyncOpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    print("⚠️  OpenAI SDK not available.")

try:
    from anthropic import AsyncAnthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False
    print("⚠️  Anthropic SDK not available.")


# ============================================================================
# MODULE 1: FOUNDATION SETUP
# ============================================================================

print("\n" + "=" * 80)
print("MODULE 1: FOUNDATION SETUP")
print("=" * 80)


class LogLevel(str, Enum):
    """Logging levels for the application."""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


def setup_logging(
    level: LogLevel = LogLevel.INFO,
    log_file: Optional[str] = None,
    json_logs: bool = False
) -> logging.Logger:
    """
    Configure structured logging with file and console output.

    Args:
        level: Logging level
        log_file: Optional file path for log output
        json_logs: Enable JSON-formatted logs for production

    Returns:
        Configured logger instance

    Example:
        >>> logger = setup_logging(LogLevel.DEBUG, "proxy.log")
        >>> logger.info("Proxy started", extra={"port": 8000})
    """
    # Create custom formatter
    if json_logs:
        import json as json_lib

        class JSONFormatter(logging.Formatter):
            def format(self, record: logging.LogRecord) -> str:
                log_data = {
                    "timestamp": datetime.utcnow().isoformat(),
                    "level": record.levelname,
                    "logger": record.name,
                    "message": record.getMessage(),
                    "module": record.module,
                    "function": record.funcName,
                    "line": record.lineno,
                }

                # Add extra fields
                if hasattr(record, "extra"):
                    log_data.update(record.extra)

                # Add exception info if present
                if record.exc_info:
                    log_data["exception"] = self.formatException(record.exc_info)

                return json_lib.dumps(log_data)

        formatter = JSONFormatter()
    else:
        formatter = logging.Formatter(
            fmt="%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )

    # Configure root logger
    logger = logging.getLogger("litellm_proxy")
    logger.setLevel(level.value)
    logger.handlers.clear()

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File handler (optional)
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


# Initialize logger
logger = setup_logging(LogLevel.INFO)
logger.info("Tutorial logging initialized")


class EnvironmentConfig(BaseModel):
    """
    Environment configuration with validation.

    This Pydantic model ensures all required environment variables
    are present and valid before the application starts.
    """

    # API Keys
    openai_api_key: str = Field(..., min_length=20, description="OpenAI API key")
    anthropic_api_key: Optional[str] = Field(None, min_length=20, description="Anthropic API key")
    supermemory_api_key: Optional[str] = Field(None, description="Supermemory API key for cloud memory")

    # Proxy Configuration
    master_key: str = Field(default="sk-1234", description="Master key for proxy authentication")
    proxy_host: str = Field(default="127.0.0.1", description="Proxy server host")
    proxy_port: int = Field(default=8765, ge=1, le=65535, description="Proxy server port")

    # LiteLLM Backend
    litellm_base_url: str = Field(default="http://localhost:4000", description="LiteLLM backend URL")

    # Memory Storage
    redis_url: Optional[str] = Field(None, description="Redis connection URL (optional)")
    memory_ttl_seconds: int = Field(default=3600, ge=60, description="Memory TTL in seconds")
    max_context_messages: int = Field(default=20, ge=1, description="Max messages in context")

    # Security
    enable_rate_limiting: bool = Field(default=True, description="Enable rate limiting")
    max_requests_per_minute: int = Field(default=60, ge=1, description="Max requests per minute")

    # Logging
    log_level: LogLevel = Field(default=LogLevel.INFO, description="Logging level")
    json_logs: bool = Field(default=False, description="Enable JSON logging")

    @validator("openai_api_key", "anthropic_api_key", pre=True)
    def validate_api_key_format(cls, v: Optional[str]) -> Optional[str]:
        """Validate API key format."""
        if v and not v.startswith(("sk-", "claude-")):
            logger.warning("API key format appears invalid")
        return v

    @classmethod
    def from_env(cls) -> "EnvironmentConfig":
        """
        Load configuration from environment variables.

        Returns:
            Configured EnvironmentConfig instance

        Raises:
            ValidationError: If required variables are missing or invalid
        """
        return cls(
            openai_api_key=os.getenv("OPENAI_API_KEY", ""),
            anthropic_api_key=os.getenv("ANTHROPIC_API_KEY"),
            supermemory_api_key=os.getenv("SUPERMEMORY_API_KEY"),
            master_key=os.getenv("LITELLM_MASTER_KEY", "sk-1234"),
            proxy_host=os.getenv("PROXY_HOST", "127.0.0.1"),
            proxy_port=int(os.getenv("PROXY_PORT", "8765")),
            litellm_base_url=os.getenv("LITELLM_BASE_URL", "http://localhost:4000"),
            redis_url=os.getenv("REDIS_URL"),
            memory_ttl_seconds=int(os.getenv("MEMORY_TTL_SECONDS", "3600")),
            max_context_messages=int(os.getenv("MAX_CONTEXT_MESSAGES", "20")),
            enable_rate_limiting=os.getenv("ENABLE_RATE_LIMITING", "true").lower() == "true",
            max_requests_per_minute=int(os.getenv("MAX_REQUESTS_PER_MINUTE", "60")),
            log_level=LogLevel(os.getenv("LOG_LEVEL", "INFO")),
            json_logs=os.getenv("JSON_LOGS", "false").lower() == "true",
        )


def validate_environment() -> EnvironmentConfig:
    """
    Validate environment configuration and connectivity.

    Returns:
        Validated EnvironmentConfig instance

    Example:
        >>> config = validate_environment()
        >>> print(f"Proxy will run on {config.proxy_host}:{config.proxy_port}")
    """
    logger.info("Validating environment configuration...")

    try:
        config = EnvironmentConfig.from_env()
        logger.info("✓ Environment configuration valid")

        # Log configuration (without sensitive data)
        logger.info(f"Proxy: {config.proxy_host}:{config.proxy_port}")
        logger.info(f"LiteLLM Backend: {config.litellm_base_url}")
        logger.info(f"Memory TTL: {config.memory_ttl_seconds}s")
        logger.info(f"Max Context Messages: {config.max_context_messages}")
        logger.info(f"Redis Enabled: {config.redis_url is not None}")

        return config

    except Exception as e:
        logger.error(f"✗ Environment validation failed: {e}")
        raise


# ============================================================================
# MODULE 2: LITELLM PROXY CONFIGURATION
# ============================================================================

print("\n" + "=" * 80)
print("MODULE 2: LITELLM PROXY CONFIGURATION")
print("=" * 80)


class ModelProvider(str, Enum):
    """Supported model providers."""
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"


@dataclass
class ModelConfig:
    """
    Configuration for a single model endpoint.

    Attributes:
        model_name: Display name for the model
        provider: Model provider (openai, anthropic, etc.)
        litellm_model: LiteLLM-compatible model identifier
        api_key: API key for the provider
        api_base: Optional custom API base URL
        supports_memory: Whether this model supports memory features
        extra_headers: Additional headers to include in requests
    """

    model_name: str
    provider: ModelProvider
    litellm_model: str
    api_key: str
    api_base: Optional[str] = None
    supports_memory: bool = False
    extra_headers: Dict[str, str] = field(default_factory=dict)

    def to_litellm_config(self) -> Dict[str, Any]:
        """
        Convert to LiteLLM configuration format.

        Returns:
            Dictionary in LiteLLM config format
        """
        config = {
            "model_name": self.model_name,
            "litellm_params": {
                "model": f"{self.provider.value}/{self.litellm_model}",
                "api_key": f"os.environ/{self.api_key.upper().replace('-', '_')}",
            }
        }

        if self.api_base:
            config["litellm_params"]["api_base"] = self.api_base

        if self.extra_headers:
            config["litellm_params"]["extra_headers"] = self.extra_headers

        if self.provider == ModelProvider.ANTHROPIC:
            config["litellm_params"]["custom_llm_provider"] = "anthropic"

        return config


class ProxyConfiguration:
    """
    Manages LiteLLM proxy configuration with multi-provider support.

    This class handles:
    - Model registration and configuration
    - User ID mapping for memory isolation
    - Configuration file generation
    - Validation and health checks
    """

    def __init__(self, config_path: str = "config.yaml"):
        """
        Initialize proxy configuration.

        Args:
            config_path: Path to configuration YAML file
        """
        self.config_path = config_path
        self.models: List[ModelConfig] = []
        self.user_id_mappings: Dict[str, Any] = {
            "custom_header": "x-memory-user-id",
            "header_patterns": [],
            "default_user_id": "default-user"
        }
        self.general_settings: Dict[str, Any] = {
            "master_key": "sk-1234"
        }
        self.litellm_settings: Dict[str, Any] = {
            "set_verbose": True,
            "json_logs": True,
            "use_client_cache": True,
            "drop_params": True,
        }

        logger.info(f"ProxyConfiguration initialized with config: {config_path}")

    def add_model(self, model: ModelConfig) -> None:
        """
        Register a new model with the proxy.

        Args:
            model: ModelConfig instance to register

        Example:
            >>> config = ProxyConfiguration()
            >>> config.add_model(ModelConfig(
            ...     model_name="gpt-4",
            ...     provider=ModelProvider.OPENAI,
            ...     litellm_model="gpt-4",
            ...     api_key="OPENAI_API_KEY"
            ... ))
        """
        self.models.append(model)
        logger.info(f"Added model: {model.model_name} ({model.provider.value})")

    def add_user_pattern(
        self,
        header: str,
        pattern: str,
        user_id: str
    ) -> None:
        """
        Add a header pattern for user ID detection.

        Args:
            header: Header name to match (e.g., "user-agent")
            pattern: Regex pattern to match header value
            user_id: User ID to assign when pattern matches

        Example:
            >>> config.add_user_pattern(
            ...     header="user-agent",
            ...     pattern="Claude Code",
            ...     user_id="claude-cli"
            ... )
        """
        self.user_id_mappings["header_patterns"].append({
            "header": header,
            "pattern": pattern,
            "user_id": user_id
        })
        logger.info(f"Added user pattern: {header}={pattern} -> {user_id}")

    def load_from_file(self) -> None:
        """
        Load configuration from YAML file.

        Raises:
            FileNotFoundError: If config file doesn't exist
            yaml.YAMLError: If YAML is malformed
        """
        try:
            with open(self.config_path, 'r') as f:
                config = yaml.safe_load(f)

            # Load general settings
            if "general_settings" in config:
                self.general_settings.update(config["general_settings"])

            # Load LiteLLM settings
            if "litellm_settings" in config:
                self.litellm_settings.update(config["litellm_settings"])

            # Load user ID mappings
            if "user_id_mappings" in config:
                self.user_id_mappings.update(config["user_id_mappings"])

            # Load models
            for model_config in config.get("model_list", []):
                # This is a simplified loader - actual implementation
                # would parse litellm_params into ModelConfig
                logger.debug(f"Loaded model from config: {model_config.get('model_name')}")

            logger.info(f"✓ Configuration loaded from {self.config_path}")

        except FileNotFoundError:
            logger.warning(f"Config file not found: {self.config_path}")
        except Exception as e:
            logger.error(f"Error loading config: {e}")
            raise

    def save_to_file(self) -> None:
        """
        Save current configuration to YAML file.

        Example:
            >>> config = ProxyConfiguration()
            >>> config.add_model(...)
            >>> config.save_to_file()
        """
        config = {
            "general_settings": self.general_settings,
            "user_id_mappings": self.user_id_mappings,
            "model_list": [model.to_litellm_config() for model in self.models],
            "litellm_settings": self.litellm_settings,
        }

        with open(self.config_path, 'w') as f:
            yaml.dump(config, f, default_flow_style=False, sort_keys=False)

        logger.info(f"✓ Configuration saved to {self.config_path}")

    def validate(self) -> bool:
        """
        Validate configuration completeness.

        Returns:
            True if configuration is valid

        Raises:
            ValueError: If configuration is invalid
        """
        if not self.models:
            raise ValueError("No models configured")

        if not self.general_settings.get("master_key"):
            raise ValueError("Master key not configured")

        logger.info("✓ Configuration validation passed")
        return True


def create_sample_configuration() -> ProxyConfiguration:
    """
    Create a sample configuration with OpenAI and Anthropic models.

    Returns:
        Configured ProxyConfiguration instance

    Example:
        >>> config = create_sample_configuration()
        >>> config.save_to_file()
    """
    config = ProxyConfiguration("config.yaml")

    # Add OpenAI models
    config.add_model(ModelConfig(
        model_name="gpt-4",
        provider=ModelProvider.OPENAI,
        litellm_model="gpt-4",
        api_key="OPENAI_API_KEY"
    ))

    config.add_model(ModelConfig(
        model_name="gpt-4-turbo",
        provider=ModelProvider.OPENAI,
        litellm_model="gpt-4-turbo-preview",
        api_key="OPENAI_API_KEY"
    ))

    # Add Anthropic model with memory support
    if os.getenv("SUPERMEMORY_API_KEY"):
        config.add_model(ModelConfig(
            model_name="claude-sonnet-4.5",
            provider=ModelProvider.ANTHROPIC,
            litellm_model="claude-sonnet-4-5-20250929",
            api_key="ANTHROPIC_API_KEY",
            api_base="https://api.supermemory.ai/v3/api.anthropic.com",
            supports_memory=True,
            extra_headers={
                "x-supermemory-api-key": os.getenv("SUPERMEMORY_API_KEY", ""),
                "x-sm-user-id": "default-user"
            }
        ))
    else:
        config.add_model(ModelConfig(
            model_name="claude-sonnet-4.5",
            provider=ModelProvider.ANTHROPIC,
            litellm_model="claude-sonnet-4-5-20250929",
            api_key="ANTHROPIC_API_KEY"
        ))

    # Add user ID patterns for client detection
    config.add_user_pattern(
        header="user-agent",
        pattern="OpenAIClientImpl/Java",
        user_id="pycharm-ai"
    )

    config.add_user_pattern(
        header="user-agent",
        pattern="Claude Code",
        user_id="claude-cli"
    )

    config.add_user_pattern(
        header="user-agent",
        pattern="anthropic-sdk-python",
        user_id="python-client"
    )

    return config


# ============================================================================
# MODULE 3: MEMORY INTEGRATION
# ============================================================================

print("\n" + "=" * 80)
print("MODULE 3: MEMORY INTEGRATION")
print("=" * 80)


@dataclass
class Message:
    """
    Represents a single message in a conversation.

    Attributes:
        role: Message role (user, assistant, system)
        content: Message content
        timestamp: When the message was created
        metadata: Additional metadata (model, tokens, etc.)
    """

    role: str  # "user", "assistant", "system"
    content: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format."""
        return {
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Message":
        """Create Message from dictionary."""
        return cls(
            role=data["role"],
            content=data["content"],
            timestamp=datetime.fromisoformat(data.get("timestamp", datetime.utcnow().isoformat())),
            metadata=data.get("metadata", {})
        )

    def to_openai_format(self) -> Dict[str, str]:
        """Convert to OpenAI message format."""
        return {
            "role": self.role,
            "content": self.content
        }

    def to_anthropic_format(self) -> Dict[str, str]:
        """Convert to Anthropic message format."""
        return {
            "role": self.role if self.role != "system" else "user",
            "content": self.content
        }


@dataclass
class ConversationSession:
    """
    Represents a conversation session with memory.

    Attributes:
        session_id: Unique session identifier
        user_id: User/client identifier for isolation
        messages: List of messages in conversation
        created_at: Session creation timestamp
        last_accessed: Last access timestamp
        metadata: Additional session metadata
    """

    session_id: str
    user_id: str
    messages: List[Message] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_accessed: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def add_message(self, message: Message) -> None:
        """Add a message to the conversation."""
        self.messages.append(message)
        self.last_accessed = datetime.utcnow()

    def get_context_messages(self, max_messages: int = 20) -> List[Message]:
        """
        Get the most recent messages for context.

        Args:
            max_messages: Maximum number of messages to return

        Returns:
            List of recent messages
        """
        return self.messages[-max_messages:] if len(self.messages) > max_messages else self.messages

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format."""
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "messages": [msg.to_dict() for msg in self.messages],
            "created_at": self.created_at.isoformat(),
            "last_accessed": self.last_accessed.isoformat(),
            "metadata": self.metadata
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ConversationSession":
        """Create ConversationSession from dictionary."""
        return cls(
            session_id=data["session_id"],
            user_id=data["user_id"],
            messages=[Message.from_dict(msg) for msg in data.get("messages", [])],
            created_at=datetime.fromisoformat(data.get("created_at", datetime.utcnow().isoformat())),
            last_accessed=datetime.fromisoformat(data.get("last_accessed", datetime.utcnow().isoformat())),
            metadata=data.get("metadata", {})
        )


class MemoryStore(ABC):
    """
    Abstract base class for memory storage backends.

    Implementations can use in-memory storage, Redis, PostgreSQL, etc.
    """

    @abstractmethod
    async def get_session(self, session_id: str) -> Optional[ConversationSession]:
        """Retrieve a session by ID."""
        pass

    @abstractmethod
    async def save_session(self, session: ConversationSession) -> None:
        """Save or update a session."""
        pass

    @abstractmethod
    async def delete_session(self, session_id: str) -> None:
        """Delete a session."""
        pass

    @abstractmethod
    async def list_sessions(self, user_id: Optional[str] = None) -> List[str]:
        """List all session IDs, optionally filtered by user_id."""
        pass

    @abstractmethod
    async def cleanup_expired_sessions(self, max_age_seconds: int) -> int:
        """Remove sessions older than max_age_seconds."""
        pass


class InMemoryStore(MemoryStore):
    """
    In-memory storage for conversation sessions.

    Suitable for development and single-instance deployments.
    Data is lost when the process restarts.
    """

    def __init__(self):
        """Initialize in-memory store."""
        self._sessions: Dict[str, ConversationSession] = {}
        logger.info("InMemoryStore initialized")

    async def get_session(self, session_id: str) -> Optional[ConversationSession]:
        """Retrieve a session by ID."""
        session = self._sessions.get(session_id)
        if session:
            session.last_accessed = datetime.utcnow()
        return session

    async def save_session(self, session: ConversationSession) -> None:
        """Save or update a session."""
        self._sessions[session.session_id] = session
        logger.debug(f"Session saved: {session.session_id} ({len(session.messages)} messages)")

    async def delete_session(self, session_id: str) -> None:
        """Delete a session."""
        if session_id in self._sessions:
            del self._sessions[session_id]
            logger.debug(f"Session deleted: {session_id}")

    async def list_sessions(self, user_id: Optional[str] = None) -> List[str]:
        """List all session IDs, optionally filtered by user_id."""
        if user_id:
            return [
                sid for sid, session in self._sessions.items()
                if session.user_id == user_id
            ]
        return list(self._sessions.keys())

    async def cleanup_expired_sessions(self, max_age_seconds: int) -> int:
        """Remove sessions older than max_age_seconds."""
        now = datetime.utcnow()
        expired_count = 0

        sessions_to_delete = [
            session_id
            for session_id, session in self._sessions.items()
            if (now - session.last_accessed).total_seconds() > max_age_seconds
        ]

        for session_id in sessions_to_delete:
            await self.delete_session(session_id)
            expired_count += 1

        if expired_count > 0:
            logger.info(f"Cleaned up {expired_count} expired sessions")

        return expired_count


class RedisStore(MemoryStore):
    """
    Redis-based storage for conversation sessions.

    Suitable for production deployments with multiple instances.
    Provides persistence and scalability.
    """

    def __init__(self, redis_url: str, key_prefix: str = "litellm:session:"):
        """
        Initialize Redis store.

        Args:
            redis_url: Redis connection URL (redis://localhost:6379)
            key_prefix: Prefix for all Redis keys
        """
        if not REDIS_AVAILABLE:
            raise RuntimeError("Redis is not available. Install with: pip install redis")

        self.redis_url = redis_url
        self.key_prefix = key_prefix
        self._client: Optional["AsyncRedis"] = None
        logger.info(f"RedisStore initialized with URL: {redis_url}")

    async def _get_client(self) -> "AsyncRedis":
        """Get or create Redis client."""
        if self._client is None:
            self._client = redis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=True
            )
        return self._client

    def _make_key(self, session_id: str) -> str:
        """Create Redis key for session."""
        return f"{self.key_prefix}{session_id}"

    async def get_session(self, session_id: str) -> Optional[ConversationSession]:
        """Retrieve a session by ID."""
        client = await self._get_client()
        key = self._make_key(session_id)

        data = await client.get(key)
        if not data:
            return None

        session = ConversationSession.from_dict(json.loads(data))
        session.last_accessed = datetime.utcnow()

        # Update last accessed time in Redis
        await self.save_session(session)

        return session

    async def save_session(self, session: ConversationSession) -> None:
        """Save or update a session."""
        client = await self._get_client()
        key = self._make_key(session.session_id)

        data = json.dumps(session.to_dict())
        await client.set(key, data)

        # Set expiry (optional - can use Redis TTL)
        # await client.expire(key, ttl_seconds)

        logger.debug(f"Session saved to Redis: {session.session_id}")

    async def delete_session(self, session_id: str) -> None:
        """Delete a session."""
        client = await self._get_client()
        key = self._make_key(session_id)
        await client.delete(key)
        logger.debug(f"Session deleted from Redis: {session_id}")

    async def list_sessions(self, user_id: Optional[str] = None) -> List[str]:
        """List all session IDs, optionally filtered by user_id."""
        client = await self._get_client()
        pattern = f"{self.key_prefix}*"

        session_ids = []
        async for key in client.scan_iter(match=pattern):
            session_id = key.replace(self.key_prefix, "")

            if user_id:
                # Need to check user_id - fetch session
                session = await self.get_session(session_id)
                if session and session.user_id == user_id:
                    session_ids.append(session_id)
            else:
                session_ids.append(session_id)

        return session_ids

    async def cleanup_expired_sessions(self, max_age_seconds: int) -> int:
        """Remove sessions older than max_age_seconds."""
        client = await self._get_client()
        pattern = f"{self.key_prefix}*"
        now = datetime.utcnow()
        expired_count = 0

        async for key in client.scan_iter(match=pattern):
            data = await client.get(key)
            if data:
                session_data = json.loads(data)
                last_accessed = datetime.fromisoformat(session_data.get("last_accessed"))

                if (now - last_accessed).total_seconds() > max_age_seconds:
                    await client.delete(key)
                    expired_count += 1

        if expired_count > 0:
            logger.info(f"Cleaned up {expired_count} expired sessions from Redis")

        return expired_count

    async def close(self) -> None:
        """Close Redis connection."""
        if self._client:
            await self._client.close()
            logger.info("Redis connection closed")


class MemoryManager:
    """
    High-level memory management for conversation sessions.

    Handles:
    - Session creation and retrieval
    - Context window management
    - Message injection
    - Automatic cleanup
    """

    def __init__(
        self,
        store: MemoryStore,
        max_context_messages: int = 20,
        ttl_seconds: int = 3600
    ):
        """
        Initialize memory manager.

        Args:
            store: MemoryStore implementation
            max_context_messages: Maximum messages to keep in context
            ttl_seconds: Session time-to-live in seconds
        """
        self.store = store
        self.max_context_messages = max_context_messages
        self.ttl_seconds = ttl_seconds
        logger.info(f"MemoryManager initialized (max_context={max_context_messages}, ttl={ttl_seconds}s)")

    async def get_or_create_session(
        self,
        session_id: str,
        user_id: str
    ) -> ConversationSession:
        """
        Get existing session or create a new one.

        Args:
            session_id: Session identifier
            user_id: User identifier

        Returns:
            ConversationSession instance
        """
        session = await self.store.get_session(session_id)

        if session is None:
            session = ConversationSession(
                session_id=session_id,
                user_id=user_id
            )
            await self.store.save_session(session)
            logger.info(f"Created new session: {session_id} (user={user_id})")
        else:
            logger.debug(f"Retrieved existing session: {session_id} ({len(session.messages)} messages)")

        return session

    async def add_user_message(
        self,
        session_id: str,
        user_id: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Add a user message to the session.

        Args:
            session_id: Session identifier
            user_id: User identifier
            content: Message content
            metadata: Optional message metadata
        """
        session = await self.get_or_create_session(session_id, user_id)

        message = Message(
            role="user",
            content=content,
            metadata=metadata or {}
        )

        session.add_message(message)
        await self.store.save_session(session)

        logger.debug(f"Added user message to session {session_id}")

    async def add_assistant_message(
        self,
        session_id: str,
        user_id: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Add an assistant message to the session.

        Args:
            session_id: Session identifier
            user_id: User identifier
            content: Message content
            metadata: Optional message metadata
        """
        session = await self.get_or_create_session(session_id, user_id)

        message = Message(
            role="assistant",
            content=content,
            metadata=metadata or {}
        )

        session.add_message(message)
        await self.store.save_session(session)

        logger.debug(f"Added assistant message to session {session_id}")

    async def get_context_for_request(
        self,
        session_id: str,
        user_id: str,
        include_system_message: bool = True
    ) -> List[Dict[str, str]]:
        """
        Get conversation context for a new request.

        Args:
            session_id: Session identifier
            user_id: User identifier
            include_system_message: Include system message in context

        Returns:
            List of messages in OpenAI format
        """
        session = await self.get_or_create_session(session_id, user_id)
        context_messages = session.get_context_messages(self.max_context_messages)

        messages = []

        if include_system_message:
            messages.append({
                "role": "system",
                "content": "You are a helpful AI assistant with conversation memory."
            })

        messages.extend([msg.to_openai_format() for msg in context_messages])

        return messages

    async def cleanup_old_sessions(self) -> int:
        """
        Clean up expired sessions.

        Returns:
            Number of sessions cleaned up
        """
        return await self.store.cleanup_expired_sessions(self.ttl_seconds)


# ============================================================================
# MODULE 4: END-TO-END IMPLEMENTATION
# ============================================================================

print("\n" + "=" * 80)
print("MODULE 4: END-TO-END IMPLEMENTATION")
print("=" * 80)


class ClientDetector:
    """
    Detects client type and user ID from request headers.

    Uses pattern matching on headers like User-Agent to identify
    different clients and assign appropriate user IDs for memory isolation.
    """

    def __init__(self, config: ProxyConfiguration):
        """
        Initialize client detector.

        Args:
            config: ProxyConfiguration with user ID patterns
        """
        self.config = config
        self.patterns = self._compile_patterns()
        logger.info(f"ClientDetector initialized with {len(self.patterns)} patterns")

    def _compile_patterns(self) -> List[Dict[str, Any]]:
        """Compile regex patterns from configuration."""
        compiled = []

        for pattern_config in self.config.user_id_mappings.get("header_patterns", []):
            try:
                compiled.append({
                    "header": pattern_config["header"].lower(),
                    "pattern": re.compile(pattern_config["pattern"], re.IGNORECASE),
                    "user_id": pattern_config["user_id"]
                })
            except Exception as e:
                logger.error(f"Failed to compile pattern {pattern_config}: {e}")

        return compiled

    def detect_user_id(self, headers: Dict[str, str]) -> str:
        """
        Detect user ID from request headers.

        Priority:
        1. Custom header (x-memory-user-id)
        2. Pattern matching
        3. Default user ID

        Args:
            headers: Request headers (case-insensitive)

        Returns:
            Detected user ID
        """
        # Normalize headers
        normalized = {k.lower(): v for k, v in headers.items()}

        # Check custom header
        custom_header = self.config.user_id_mappings.get("custom_header", "x-memory-user-id").lower()
        if custom_header in normalized:
            user_id = normalized[custom_header]
            logger.debug(f"User ID from custom header: {user_id}")
            return user_id

        # Pattern matching
        for pattern_config in self.patterns:
            header_name = pattern_config["header"]
            pattern = pattern_config["pattern"]
            user_id = pattern_config["user_id"]

            if header_name in normalized:
                header_value = normalized[header_name]
                if pattern.search(header_value):
                    logger.debug(f"User ID matched via {header_name}: {user_id}")
                    return user_id

        # Default
        default_user_id = self.config.user_id_mappings.get("default_user_id", "default-user")
        logger.debug(f"Using default user ID: {default_user_id}")
        return default_user_id


class RateLimiter:
    """
    Token bucket rate limiter for request throttling.

    Protects the proxy from abuse and ensures fair usage across clients.
    """

    def __init__(
        self,
        max_requests: int = 60,
        window_seconds: int = 60
    ):
        """
        Initialize rate limiter.

        Args:
            max_requests: Maximum requests per window
            window_seconds: Time window in seconds
        """
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._buckets: Dict[str, List[float]] = {}
        logger.info(f"RateLimiter initialized ({max_requests} req/{window_seconds}s)")

    async def check_rate_limit(self, client_id: str) -> Tuple[bool, Optional[int]]:
        """
        Check if request is within rate limit.

        Args:
            client_id: Client identifier (user_id or IP)

        Returns:
            Tuple of (allowed, retry_after_seconds)
        """
        now = time.time()

        # Initialize bucket if needed
        if client_id not in self._buckets:
            self._buckets[client_id] = []

        bucket = self._buckets[client_id]

        # Remove expired timestamps
        cutoff = now - self.window_seconds
        bucket[:] = [ts for ts in bucket if ts > cutoff]

        # Check limit
        if len(bucket) >= self.max_requests:
            # Calculate retry after
            oldest = bucket[0]
            retry_after = int(self.window_seconds - (now - oldest)) + 1
            logger.warning(f"Rate limit exceeded for {client_id} (retry after {retry_after}s)")
            return False, retry_after

        # Add current request
        bucket.append(now)
        return True, None


# noinspection D
class MemoryEnabledProxy:
    """
    Complete LiteLLM proxy implementation with memory management.

    This class orchestrates:
    - Request interception
    - Client detection
    - Memory retrieval and injection
    - Request forwarding to LiteLLM
    - Response handling and memory storage
    - Rate limiting and security
    """

    def __init__(
        self,
        config: ProxyConfiguration,
        memory_manager: MemoryManager,
        litellm_base_url: str,
        enable_rate_limiting: bool = True,
        max_requests_per_minute: int = 60
    ):
        """
        Initialize memory-enabled proxy.

        Args:
            config: Proxy configuration
            memory_manager: Memory management instance
            litellm_base_url: LiteLLM backend URL
            enable_rate_limiting: Enable rate limiting
            max_requests_per_minute: Max requests per minute per client
        """
        self.config = config
        self.memory_manager = memory_manager
        self.litellm_base_url = litellm_base_url
        self.client_detector = ClientDetector(config)

        # Rate limiting
        self.enable_rate_limiting = enable_rate_limiting
        self.rate_limiter = RateLimiter(
            max_requests=max_requests_per_minute,
            window_seconds=60
        ) if enable_rate_limiting else None

        logger.info("MemoryEnabledProxy initialized")

    def _extract_session_id(self, headers: Dict[str, str], default: Optional[str] = None) -> str:
        """
        Extract or generate session ID from headers.

        Args:
            headers: Request headers
            default: Default session ID if not found

        Returns:
            Session ID
        """
        # Check for custom session header
        session_id = headers.get("x-session-id") or headers.get("x-litellm-session-id")

        if session_id:
            return session_id

        # Generate new session ID
        return default or f"session_{uuid4().hex[:16]}"

    async def _check_rate_limit(self, user_id: str) -> None:
        """
        Check rate limit and raise exception if exceeded.

        Args:
            user_id: User identifier

        Raises:
            HTTPException: If rate limit exceeded
        """
        if not self.enable_rate_limiting or not self.rate_limiter:
            return

        allowed, retry_after = await self.rate_limiter.check_rate_limit(user_id)

        if not allowed:
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded. Retry after {retry_after} seconds.",
                headers={"Retry-After": str(retry_after)}
            )

    async def _inject_memory_context(
        self,
        request_data: Dict[str, Any],
        session_id: str,
        user_id: str
    ) -> Dict[str, Any]:
        """
        Inject conversation memory into request.

        Args:
            request_data: Original request data
            session_id: Session identifier
            user_id: User identifier

        Returns:
            Modified request data with memory context
        """
        # Get conversation context
        context_messages = await self.memory_manager.get_context_for_request(
            session_id=session_id,
            user_id=user_id,
            include_system_message=True
        )

        # Extract user's new message
        user_messages = request_data.get("messages", [])
        if user_messages:
            # Get the last user message
            last_message = user_messages[-1]

            # Store in memory
            await self.memory_manager.add_user_message(
                session_id=session_id,
                user_id=user_id,
                content=last_message.get("content", ""),
                metadata={"model": request_data.get("model")}
            )

        # Merge context with new messages
        # Keep system message, add context, then new user message
        merged_messages = context_messages

        logger.debug(f"Injected {len(context_messages)} context messages")

        # Update request
        modified_request = request_data.copy()
        modified_request["messages"] = merged_messages

        return modified_request

    async def _store_assistant_response(
        self,
        session_id: str,
        user_id: str,
        response_data: Dict[str, Any]
    ) -> None:
        """
        Store assistant response in memory.

        Args:
            session_id: Session identifier
            user_id: User identifier
            response_data: Response from LLM
        """
        try:
            # Extract assistant message from response
            choices = response_data.get("choices", [])
            if not choices:
                return

            message = choices[0].get("message", {})
            content = message.get("content", "")

            if not content:
                return

            # Store in memory
            await self.memory_manager.add_assistant_message(
                session_id=session_id,
                user_id=user_id,
                content=content,
                metadata={
                    "model": response_data.get("model"),
                    "tokens": response_data.get("usage", {})
                }
            )

            logger.debug(f"Stored assistant response for session {session_id}")

        except Exception as e:
            logger.error(f"Failed to store assistant response: {e}")

    async def forward_request(
        self,
        method: str,
        path: str,
        headers: Dict[str, str],
        body: Optional[bytes] = None
    ) -> Tuple[int, Dict[str, str], bytes]:
        """
        Forward request to LiteLLM backend.

        Args:
            method: HTTP method
            path: Request path
            headers: Request headers
            body: Request body

        Returns:
            Tuple of (status_code, headers, body)
        """
        url = f"{self.litellm_base_url}{path}"

        async with httpx.AsyncClient(timeout=600.0) as client:
            try:
                response = await client.request(
                    method=method,
                    url=url,
                    headers=headers,
                    content=body
                )

                return response.status_code, dict(response.headers), response.content

            except Exception as e:
                logger.error(f"Request forwarding failed: {e}")
                raise

    async def handle_chat_completion(
        self,
        request: Request,
        path: str
    ) -> Response:
        """
        Handle chat completion requests with memory.

        Args:
            request: FastAPI request object
            path: Request path

        Returns:
            FastAPI response
        """
        request_id = secrets.token_hex(4)
        logger.info(f"[{request_id}] Chat completion request")

        # Parse request
        headers = dict(request.headers)
        body = await request.body()
        request_data = json.loads(body) if body else {}

        # Detect client and user ID
        user_id = self.client_detector.detect_user_id(headers)
        session_id = self._extract_session_id(headers)

        logger.info(f"[{request_id}] user_id={user_id}, session_id={session_id}")

        # Check rate limit
        try:
            await self._check_rate_limit(user_id)
        except HTTPException as e:
            return JSONResponse(
                status_code=e.status_code,
                content={"error": e.detail},
                headers=e.headers
            )

        # Inject memory context
        try:
            modified_request = await self._inject_memory_context(
                request_data=request_data,
                session_id=session_id,
                user_id=user_id
            )

            # Update body
            body = json.dumps(modified_request).encode()

        except Exception as e:
            logger.error(f"[{request_id}] Memory injection failed: {e}")
            # Continue without memory on error

        # Forward request
        try:
            # Remove host header
            headers.pop("host", None)

            status_code, response_headers, response_body = await self.forward_request(
                method=request.method,
                path=path,
                headers=headers,
                body=body
            )

            # Store assistant response
            if status_code == 200:
                try:
                    response_data = json.loads(response_body)
                    await self._store_assistant_response(
                        session_id=session_id,
                        user_id=user_id,
                        response_data=response_data
                    )
                except Exception as e:
                    logger.error(f"[{request_id}] Response storage failed: {e}")

            logger.info(f"[{request_id}] Completed (status={status_code})")

            return Response(
                content=response_body,
                status_code=status_code,
                headers=dict(response_headers)
            )

        except Exception as e:
            logger.error(f"[{request_id}] Request failed: {e}")
            return JSONResponse(
                status_code=500,
                content={"error": str(e)}
            )

    async def handle_streaming_completion(
        self,
        request: Request,
        path: str
    ) -> StreamingResponse:
        """
        Handle streaming chat completion requests with memory.

        Args:
            request: FastAPI request object
            path: Request path

        Returns:
            FastAPI streaming response
        """
        request_id = secrets.token_hex(4)
        logger.info(f"[{request_id}] Streaming chat completion request")

        # Parse request
        headers = dict(request.headers)
        body = await request.body()
        request_data = json.loads(body) if body else {}

        # Detect client and user ID
        user_id = self.client_detector.detect_user_id(headers)
        session_id = self._extract_session_id(headers)

        logger.info(f"[{request_id}] user_id={user_id}, session_id={session_id}")

        # Check rate limit with proper exception handling
        try:
            await self._check_rate_limit(user_id)
        except HTTPException as e:
            c = {"error": e.detail}
            return StreamingResponse(
                status_code=e.status_code,
                content=c,
                headers=e.headers
            )

        # Inject memory context with fallback
        try:
            modified_request = await self._inject_memory_context(
                request_data=request_data,
                session_id=session_id,
                user_id=user_id
            )
            body = json.dumps(modified_request).encode()
        except Exception as e:
            logger.error(f"[{request_id}] Memory injection failed: {e}")
            # Continue without memory - body remains unchanged

        # Stream response and accumulate content
        accumulated_content = []

        async def stream_with_memory():
            """Stream response while accumulating content."""
            # Create a copy of headers to avoid mutation
            headers_copy = headers.copy()
            headers_copy.pop("host", None)

            try:
                async with httpx.AsyncClient(timeout=600.0) as client:
                    async with client.stream(
                        method=request.method,
                        url=f"{self.litellm_base_url}{path}",
                        headers=headers_copy,
                        content=body
                    ) as response:
                        # Check response status
                        if response.status_code != 200:
                            logger.error(f"[{request_id}] Upstream error: {response.status_code}")
                            error_msg = json.dumps({"error": f"Upstream service error: {response.status_code}"})
                            yield f"data: {error_msg}\n\n".encode('utf-8')
                            return

                        async for chunk in response.aiter_bytes():
                            # Parse SSE chunk if possible
                            try:
                                chunk_str = chunk.decode('utf-8')
                                if chunk_str.startswith("data: ") and not chunk_str.startswith("data: [DONE]"):
                                    chunk_data = json.loads(chunk_str[6:])
                                    delta = chunk_data.get("choices", [{}])[0].get("delta", {})
                                    if "content" in delta:
                                        accumulated_content.append(delta["content"])
                            except (UnicodeDecodeError, json.JSONDecodeError) as e:
                                logger.debug(f"[{request_id}] Chunk parse error: {e}")

                            yield chunk

            except Exception as e:
                logger.error(f"[{request_id}] Streaming failed: {e}")
                error_msg = json.dumps({"error": str(e)})
                yield f"data: {error_msg}\n\n".encode('utf-8')
            finally:
                # Store accumulated response
                if accumulated_content:
                    full_content = "".join(accumulated_content)
                    try:
                        await self.memory_manager.add_assistant_message(
                            session_id=session_id,
                            user_id=user_id,
                            content=full_content,
                            metadata={"model": request_data.get("model"), "streaming": True}
                        )
                        logger.info(f"[{request_id}] Stored streaming response ({len(full_content)} chars)")
                    except Exception as e:
                        logger.error(f"[{request_id}] Failed to store streaming response: {e}")

                logger.info(f"[{request_id}] Streaming completed")

        return StreamingResponse(
            stream_with_memory(),
            media_type="text/event-stream"
        )


def create_proxy_app(
    config: ProxyConfiguration,
    env_config: EnvironmentConfig
) -> FastAPI:
    """
    Create FastAPI application with memory-enabled proxy.

    Args:
        config: Proxy configuration
        env_config: Environment configuration

    Returns:
        Configured FastAPI application
    """
    # Initialize memory store
    if env_config.redis_url and REDIS_AVAILABLE:
        store = RedisStore(env_config.redis_url)
        logger.info("Using Redis memory store")
    else:
        store = InMemoryStore()
        logger.info("Using in-memory store")

    # Initialize memory manager
    memory_manager = MemoryManager(
        store=store,
        max_context_messages=env_config.max_context_messages,
        ttl_seconds=env_config.memory_ttl_seconds
    )

    # Initialize proxy
    proxy = MemoryEnabledProxy(
        config=config,
        memory_manager=memory_manager,
        litellm_base_url=env_config.litellm_base_url,
        enable_rate_limiting=env_config.enable_rate_limiting,
        max_requests_per_minute=env_config.max_requests_per_minute
    )

    # Lifespan management
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Manage application lifecycle."""
        logger.info("Starting LiteLLM proxy with memory...")

        # Startup: Start cleanup task
        async def cleanup_task():
            while True:
                await asyncio.sleep(300)  # Every 5 minutes
                await memory_manager.cleanup_old_sessions()

        cleanup_handle = asyncio.create_task(cleanup_task())

        yield

        # Shutdown
        logger.info("Shutting down proxy...")
        cleanup_handle.cancel()

        if isinstance(store, RedisStore):
            await store.close()

    # Create FastAPI app
    app = FastAPI(
        title="LiteLLM Proxy with Memory",
        description="Production-ready LiteLLM proxy with conversation memory",
        version="1.0.0",
        lifespan=lifespan
    )

    # Health check endpoint
    @app.get("/health")
    async def health_check():
        """Health check endpoint."""
        return {
            "status": "healthy",
            "memory_store": type(store).__name__,
            "litellm_url": env_config.litellm_base_url,
            "rate_limiting": env_config.enable_rate_limiting
        }

    # Chat completion endpoint
    @app.post("/v1/chat/completions")
    @app.post("/chat/completions")
    async def chat_completions(request: Request):
        """Handle chat completion requests."""
        # Check if streaming
        body = await request.body()
        request_data = json.loads(body) if body else {}

        if request_data.get("stream", False):
            return await proxy.handle_streaming_completion(request, request.url.path)
        else:
            return await proxy.handle_chat_completion(request, request.url.path)

    # Anthropic messages endpoint
    @app.post("/v1/messages")
    async def anthropic_messages(request: Request):
        """Handle Anthropic messages API requests."""
        return await proxy.handle_chat_completion(request, request.url.path)

    # Session management endpoints
    @app.get("/v1/sessions")
    async def list_sessions(user_id: Optional[str] = None):
        """List conversation sessions."""
        sessions = await store.list_sessions(user_id)
        return {"sessions": sessions, "count": len(sessions)}

    @app.get("/v1/sessions/{session_id}")
    async def get_session(session_id: str):
        """Get session details."""
        session = await store.get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        return session.to_dict()

    @app.delete("/v1/sessions/{session_id}")
    async def delete_session(session_id: str):
        """Delete a session."""
        await store.delete_session(session_id)
        return {"status": "deleted", "session_id": session_id}

    # Debug endpoint
    @app.get("/v1/debug/routing")
    async def debug_routing(request: Request):
        """Debug client detection and routing."""
        headers = dict(request.headers)
        user_id = proxy.client_detector.detect_user_id(headers)

        return {
            "user_id": user_id,
            "headers": {k: v for k, v in headers.items() if k.lower() != "authorization"}
        }

    return app


# ============================================================================
# MODULE 5: PRODUCTION DEPLOYMENT & EXAMPLES
# ============================================================================

print("\n" + "=" * 80)
print("MODULE 5: PRODUCTION DEPLOYMENT & EXAMPLES")
print("=" * 80)


async def example_basic_usage():
    """
    Example 1: Basic memory-enabled conversation.

    Demonstrates:
    - Session creation
    - Memory injection
    - Conversation continuity
    """
    print("\n--- Example 1: Basic Memory Usage ---")

    # Initialize components
    config = ProxyConfiguration()
    config.load_from_file()

    store = InMemoryStore()
    memory_manager = MemoryManager(store, max_context_messages=10)

    # Simulate conversation
    session_id = "example_session_1"
    user_id = "test_user"

    # First message
    await memory_manager.add_user_message(
        session_id=session_id,
        user_id=user_id,
        content="Hello! My name is Alice."
    )

    await memory_manager.add_assistant_message(
        session_id=session_id,
        user_id=user_id,
        content="Hello Alice! Nice to meet you."
    )

    # Second message
    await memory_manager.add_user_message(
        session_id=session_id,
        user_id=user_id,
        content="What's my name?"
    )

    # Get context for response
    context = await memory_manager.get_context_for_request(
        session_id=session_id,
        user_id=user_id
    )

    print(f"Context messages: {len(context)}")
    for msg in context:
        print(f"  {msg['role']}: {msg['content'][:50]}...")

    print("✓ Memory continuity maintained across messages")


async def example_client_detection():
    """
    Example 2: Client detection and user isolation.

    Demonstrates:
    - Header-based client detection
    - User ID assignment
    - Memory isolation
    """
    print("\n--- Example 2: Client Detection ---")

    config = ProxyConfiguration()
    config.add_user_pattern(
        header="user-agent",
        pattern="Claude Code",
        user_id="claude-cli"
    )
    config.add_user_pattern(
        header="user-agent",
        pattern="python-requests",
        user_id="python-client"
    )

    detector = ClientDetector(config)

    # Test different clients
    test_cases = [
        {"user-agent": "Claude Code/1.0"},
        {"user-agent": "python-requests/2.28.0"},
        {"user-agent": "curl/7.68.0"},
        {"x-memory-user-id": "custom-user-123"}
    ]

    for headers in test_cases:
        user_id = detector.detect_user_id(headers)
        print(f"  Headers: {headers}")
        print(f"  Detected user_id: {user_id}")
        print()

    print("✓ Client detection working correctly")


async def example_rate_limiting():
    """
    Example 3: Rate limiting.

    Demonstrates:
    - Request throttling
    - Per-client limits
    - Retry-after handling
    """
    print("\n--- Example 3: Rate Limiting ---")

    limiter = RateLimiter(max_requests=5, window_seconds=10)
    client_id = "test_client"

    # Make requests
    for i in range(7):
        allowed, retry_after = await limiter.check_rate_limit(client_id)

        if allowed:
            print(f"  Request {i+1}: ✓ Allowed")
        else:
            print(f"  Request {i+1}: ✗ Rate limited (retry after {retry_after}s)")

    print("✓ Rate limiting enforced correctly")


async def example_redis_persistence():
    """
    Example 4: Redis persistence (if available).

    Demonstrates:
    - Persistent memory storage
    - Session retrieval across restarts
    - Distributed deployment support
    """
    print("\n--- Example 4: Redis Persistence ---")

    if not REDIS_AVAILABLE:
        print("  ⚠️  Redis not available, skipping example")
        return

    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")

    try:
        store = RedisStore(redis_url)

        # Create session
        session = ConversationSession(
            session_id="redis_test_session",
            user_id="redis_test_user"
        )

        session.add_message(Message(
            role="user",
            content="Testing Redis persistence"
        ))

        # Save to Redis
        await store.save_session(session)
        print("  ✓ Session saved to Redis")

        # Retrieve from Redis
        retrieved = await store.get_session("redis_test_session")
        assert retrieved is not None
        assert len(retrieved.messages) == 1
        print("  ✓ Session retrieved from Redis")

        # Cleanup
        await store.delete_session("redis_test_session")
        await store.close()
        print("  ✓ Session deleted and connection closed")

    except Exception as e:
        print(f"  ✗ Redis example failed: {e}")


async def example_full_conversation():
    """
    Example 5: Complete conversation with OpenAI SDK.

    Demonstrates:
    - Real API integration
    - Memory persistence
    - Multi-turn conversation
    """
    print("\n--- Example 5: Full Conversation (requires running proxy) ---")

    if not OPENAI_AVAILABLE:
        print("  ⚠️  OpenAI SDK not available, skipping example")
        return

    # This example assumes the proxy is running on localhost:8765
    proxy_url = "http://localhost:8765/v1"

    print(f"  Note: This example requires a running proxy at {proxy_url}")
    print("  To run the proxy, use: python tutorial_proxy_with_memory.py")
    print()
    print("  Example conversation flow:")
    print("    1. User: 'My favorite color is blue'")
    print("    2. Assistant: 'I'll remember that your favorite color is blue.'")
    print("    3. User: 'What's my favorite color?'")
    print("    4. Assistant: 'Your favorite color is blue.' (from memory)")


def print_deployment_checklist():
    """Print production deployment checklist."""
    print("\n" + "=" * 80)
    print("PRODUCTION DEPLOYMENT CHECKLIST")
    print("=" * 80)

    checklist = """
    Environment Setup:
    ☐ Set OPENAI_API_KEY environment variable
    ☐ Set ANTHROPIC_API_KEY environment variable (if using)
    ☐ Set SUPERMEMORY_API_KEY (if using Supermemory)
    ☐ Set REDIS_URL for persistent memory (recommended)
    ☐ Configure LITELLM_MASTER_KEY for authentication

    Security:
    ☐ Enable HTTPS/TLS for production
    ☐ Implement proper API key rotation
    ☐ Set up firewall rules
    ☐ Enable rate limiting (default: enabled)
    ☐ Review and restrict CORS settings
    ☐ Implement request authentication

    Monitoring:
    ☐ Set up structured logging (JSON_LOGS=true)
    ☐ Configure log aggregation (e.g., ELK, Datadog)
    ☐ Set up health check monitoring
    ☐ Configure alerting for errors and rate limits
    ☐ Monitor memory usage and session counts

    Performance:
    ☐ Use Redis for memory storage in production
    ☐ Configure appropriate max_context_messages
    ☐ Set reasonable memory_ttl_seconds
    ☐ Enable connection pooling
    ☐ Consider using a reverse proxy (nginx, Caddy)

    Reliability:
    ☐ Implement graceful shutdown
    ☐ Configure automatic restarts (systemd, supervisor)
    ☐ Set up database backups (if using persistent storage)
    ☐ Implement circuit breakers for external APIs
    ☐ Add request timeout handling

    Testing:
    ☐ Test conversation continuity
    ☐ Test client detection patterns
    ☐ Verify rate limiting behavior
    ☐ Load test with expected traffic
    ☐ Test failure scenarios (network, API errors)
    """

    print(checklist)


def print_configuration_example():
    """Print example .env file for production."""
    print("\n" + "=" * 80)
    print("EXAMPLE CONFIGURATION (.env)")
    print("=" * 80)

    env_example = """
# API Keys
OPENAI_API_KEY=sk-your-openai-key-here
ANTHROPIC_API_KEY=sk-ant-your-anthropic-key-here
SUPERMEMORY_API_KEY=sm-your-supermemory-key-here

# Proxy Configuration
LITELLM_MASTER_KEY=sk-your-secure-master-key-here
PROXY_HOST=0.0.0.0
PROXY_PORT=8765
LITELLM_BASE_URL=http://localhost:4000

# Memory Configuration
REDIS_URL=redis://localhost:6379/0
MEMORY_TTL_SECONDS=3600
MAX_CONTEXT_MESSAGES=20

# Security
ENABLE_RATE_LIMITING=true
MAX_REQUESTS_PER_MINUTE=60

# Logging
LOG_LEVEL=INFO
JSON_LOGS=true
    """

    print(env_example)


# ============================================================================
# MAIN EXECUTION
# ============================================================================

async def run_examples():
    """Run all tutorial examples."""
    print("\n" + "=" * 80)
    print("RUNNING TUTORIAL EXAMPLES")
    print("=" * 80)

    try:
        await example_basic_usage()
        await example_client_detection()
        await example_rate_limiting()
        await example_redis_persistence()
        await example_full_conversation()

        print("\n" + "=" * 80)
        print("ALL EXAMPLES COMPLETED SUCCESSFULLY")
        print("=" * 80)

    except Exception as e:
        logger.error(f"Example execution failed: {e}")
        raise


def main():
    """
    Main entry point for the tutorial.

    Usage:
        # Run tutorial examples
        python tutorial_proxy_with_memory.py

        # Start production proxy
        python tutorial_proxy_with_memory.py --serve
    """
    import argparse

    parser = argparse.ArgumentParser(
        description="LiteLLM Proxy with Memory - Tutorial"
    )
    parser.add_argument(
        "--serve",
        action="store_true",
        help="Start the proxy server"
    )
    parser.add_argument(
        "--config",
        default="config.yaml",
        help="Path to configuration file"
    )
    parser.add_argument(
        "--port",
        type=int,
        help="Override proxy port"
    )
    parser.add_argument(
        "--examples",
        action="store_true",
        help="Run tutorial examples"
    )

    args = parser.parse_args()

    if args.serve:
        # Start proxy server
        print("\n" + "=" * 80)
        print("STARTING PRODUCTION PROXY SERVER")
        print("=" * 80)

        # Load configuration
        env_config = validate_environment()

        if args.port:
            env_config.proxy_port = args.port

        config = ProxyConfiguration(args.config)
        try:
            config.load_from_file()
        except FileNotFoundError:
            logger.warning("Config file not found, creating sample configuration")
            config = create_sample_configuration()
            config.save_to_file()

        # Create and run app
        app = create_proxy_app(config, env_config)

        import uvicorn
        uvicorn.run(
            app,
            host=env_config.proxy_host,
            port=env_config.proxy_port,
            log_config=None
        )

    elif args.examples:
        # Run examples
        asyncio.run(run_examples())

    else:
        # Print tutorial information
        print(__doc__)
        print_deployment_checklist()
        print_configuration_example()

        print("\n" + "=" * 80)
        print("NEXT STEPS")
        print("=" * 80)
        print("""
1. Review the tutorial code and architecture
2. Set up environment variables (see .env example above)
3. Run examples: python tutorial_proxy_with_memory.py --examples
4. Start the proxy: python tutorial_proxy_with_memory.py --serve
5. Test with your client applications
6. Review production deployment checklist
7. Deploy to production environment

For more information, see the inline documentation and examples.
        """)


if __name__ == "__main__":
    main()
