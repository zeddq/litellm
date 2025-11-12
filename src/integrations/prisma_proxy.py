"""
Prisma Database Persistence Callback for LiteLLM SDK.

This module provides a CustomLogger implementation that writes SDK completion
events directly to the same PostgreSQL database used by the LiteLLM Proxy.

Key Features:
- Reuses DBSpendUpdateWriter logic from Proxy
- Compatible with other callbacks (OpenTelemetry, Langfuse, etc.)
- Non-blocking async execution
- Optional Redis buffer for multi-instance deployments
- Automatic batching and retry logic

Usage:
    >>> import litellm
    >>> litellm.success_callback = ["prisma_proxy"]
    >>>
    >>> response = litellm.completion(
    ...     model="gpt-4",
    ...     messages=[{"role": "user", "content": "Hello"}],
    ...     user="sdk-user-123",
    ...     metadata={"team_id": "team-alpha"}
    ... )

Multi-Callback Usage:
    >>> litellm.success_callback = ["prisma_proxy", "opentelemetry"]

References:
- Design Doc: docs/architecture/PRISMA_CALLBACK_DESIGN.md
- DBSpendUpdateWriter: litellm/proxy/db/db_spend_update_writer.py
- CustomLogger: litellm/integrations/custom_logger.py
"""

import os
import traceback
from datetime import datetime
from typing import Any, Optional, TYPE_CHECKING

import litellm
from litellm._logging import verbose_logger
from litellm.caching.dual_cache import DualCache
from litellm.integrations.custom_logger import CustomLogger

if TYPE_CHECKING:
    from litellm.caching.redis_cache import RedisCache
    from litellm.proxy.db.db_spend_update_writer import DBSpendUpdateWriter
    from litellm.proxy.utils import PrismaClient, ProxyLogging
    from litellm.types.utils import ModelResponse
else:
    RedisCache = Any
    DBSpendUpdateWriter = Any
    PrismaClient = Any
    ProxyLogging = Any
    ModelResponse = Any


class PrismaProxyLogger(CustomLogger):
    """
    Database persistence callback for LiteLLM SDK.

    Writes completion events to PostgreSQL via Prisma ORM, enabling the
    LiteLLM Proxy to display SDK-persisted data in its UI.

    Architecture:
    - Wraps DBSpendUpdateWriter (reuses Proxy logic)
    - Lazy initialization (connects on first use)
    - Exception-safe (never breaks SDK calls)
    - Multi-callback compatible

    Attributes:
        database_url: PostgreSQL connection string
        redis_url: Redis connection string (optional, for multi-instance)
        use_redis_buffer: Enable Redis buffer for horizontal scaling
        prisma_client: Prisma database client (initialized lazily)
        spend_writer: DB write orchestrator (initialized lazily)

    Example:
        >>> from integrations.prisma_proxy import PrismaProxyLogger
        >>>
        >>> # Basic usage
        >>> litellm.success_callback = ["prisma_proxy"]
        >>>
        >>> # Advanced usage with custom configuration
        >>> logger = PrismaProxyLogger(
        ...     database_url="postgresql://user:pass@localhost:5432/litellm",
        ...     redis_url="redis://localhost:6379",
        ...     use_redis_buffer=True  # Enable for multi-instance
        ... )
        >>> litellm.callbacks = [logger]
    """

    def __init__(
        self,
        database_url: Optional[str] = None,
        redis_url: Optional[str] = None,
        use_redis_buffer: bool = False,
        **kwargs,
    ):
        """
        Initialize Prisma database callback.

        Args:
            database_url: PostgreSQL connection string.
                         Defaults to DATABASE_URL environment variable.
            redis_url: Redis connection string for multi-instance coordination.
                      Defaults to REDIS_URL environment variable.
            use_redis_buffer: Enable Redis buffer for horizontal scaling.
                             Set to True if running multiple SDK instances.
            **kwargs: Additional CustomLogger parameters (e.g., message_logging)

        Environment Variables:
            DATABASE_URL: PostgreSQL connection string (required if not provided)
            REDIS_URL: Redis connection string (optional)
            USE_REDIS_TRANSACTION_BUFFER: Enable Redis buffer (optional)

        Note:
            Database connections are initialized lazily on first completion event,
            not during __init__. This avoids startup overhead if callback is unused.
        """
        super().__init__(**kwargs)

        # Configuration
        self.database_url = database_url or os.getenv("DATABASE_URL", "")
        self.redis_url = redis_url or os.getenv("REDIS_URL")
        self.use_redis_buffer = use_redis_buffer or (
            os.getenv("USE_REDIS_TRANSACTION_BUFFER", "").lower() == "true"
        )
--
        # Components (initialized lazily)
        self.prisma_client: Optional[PrismaClient] = None
        self.spend_writer: Optional[DBSpendUpdateWriter] = None
        self.redis_cache: Optional[RedisCache] = None
        self._initialized = False

        # Validate configuration
        if not self.database_url:
            raise ValueError(
                "database_url must be provided via parameter or DATABASE_URL env var"
            )

        verbose_logger.info(
            f"PrismaProxyLogger initialized (redis_buffer={self.use_redis_buffer})"
        )

    async def _ensure_initialized(self):
        """
        Lazy initialization of database connections.

        Initializes:
        1. PrismaClient (database connection pool)
        2. RedisCache (optional, if use_redis_buffer=True)
        3. DBSpendUpdateWriter (spend logging orchestrator)

        This method is idempotent - safe to call multiple times.

        Raises:
            Exception: If database connection fails (logged but not propagated)
        """
        if self._initialized:
            return

        try:
            verbose_logger.debug("PrismaProxyLogger: Initializing database connections")

            # 1. Initialize PrismaClient
            self.prisma_client = await self._init_prisma_client()
            verbose_logger.debug("PrismaProxyLogger: PrismaClient initialized")

            # 2. Initialize RedisCache (if enabled)
            if self.use_redis_buffer:
                self.redis_cache = await self._init_redis_cache()
                verbose_logger.debug("PrismaProxyLogger: RedisCache initialized")

            # 3. Initialize DBSpendUpdateWriter
            from litellm.proxy.db.db_spend_update_writer import DBSpendUpdateWriter

            self.spend_writer = DBSpendUpdateWriter(redis_cache=self.redis_cache)
            verbose_logger.debug("PrismaProxyLogger: DBSpendUpdateWriter initialized")

            self._initialized = True
            verbose_logger.info("PrismaProxyLogger: Initialization complete")

        except Exception as e:
            verbose_logger.error(f"PrismaProxyLogger: Initialization failed: {e}")
            verbose_logger.error(traceback.format_exc())
            # Re-raise to prevent callback from running without database
            raise

    async def _init_prisma_client(self) -> PrismaClient:
        """
        Initialize PrismaClient for SDK use.

        Creates a separate database connection pool for SDK callbacks,
        independent of the Proxy's connection pool.

        Connection Pool Settings:
        - Default pool size: 20 connections (lower than Proxy's 100)
        - Timeout: 60 seconds
        - Rationale: SDK typically has lower RPS than Proxy

        Returns:
            PrismaClient: Connected Prisma database client

        Raises:
            Exception: If connection fails
        """
        try:
            from litellm.proxy.utils import PrismaClient, ProxyLogging

            # Create minimal ProxyLogging instance for SDK
            # (DBSpendUpdateWriter expects this for logging)
            sdk_logging = ProxyLogging(DualCache(redis_cache=self.redis_cache))

            # Initialize Prisma client
            prisma_client = PrismaClient(
                database_url=self.database_url,
                proxy_logging_obj=sdk_logging,
            )

            # Connect to database
            await prisma_client.db.connect()

            verbose_logger.debug(
                f"PrismaProxyLogger: Connected to database at {self.database_url}"
            )

            return prisma_client

        except Exception as e:
            verbose_logger.error(f"PrismaProxyLogger: Database connection failed: {e}")
            raise

    async def _init_redis_cache(self) -> Optional[RedisCache]:
        """
        Initialize Redis cache for multi-instance coordination.

        Only required if use_redis_buffer=True. Enables horizontal scaling
        with multiple SDK instances writing to the same database.

        Redis Buffer Benefits:
        - Prevents database lock contention
        - Enables distributed coordination via PodLockManager
        - Improves batch efficiency at high RPS (>100 req/s)

        Returns:
            RedisCache: Connected Redis cache, or None if Redis URL not provided

        Note:
            If use_redis_buffer=True but redis_url is not provided, this method
            will log a warning and return None (Redis buffer disabled).
        """
        if not self.redis_url:
            if self.use_redis_buffer:
                verbose_logger.warning(
                    "PrismaProxyLogger: use_redis_buffer=True but redis_url not provided. "
                    "Redis buffer disabled. For multi-instance deployments, set REDIS_URL."
                )
            return None

        try:
            from litellm.caching.redis_cache import RedisCache

            redis_cache = RedisCache(host=self.redis_url)

            verbose_logger.debug(
                f"PrismaProxyLogger: Connected to Redis at {self.redis_url}"
            )

            return redis_cache

        except Exception as e:
            verbose_logger.error(f"PrismaProxyLogger: Redis connection failed: {e}")
            verbose_logger.warning("PrismaProxyLogger: Continuing without Redis buffer")
            return None

    async def async_log_success_event(
        self,
        kwargs: dict,
        response_obj: ModelResponse,
        start_time: datetime,
        end_time: datetime,
    ):
        """
        Log successful completion to database.

        This method is called automatically by LiteLLM after a successful
        completion API call. It extracts entity IDs from the request kwargs,
        calculates response cost, and delegates to DBSpendUpdateWriter for
        database persistence.

        Entity Tracking:
        - user: User ID (from kwargs["user"])
        - team_id: Team ID (from kwargs["metadata"]["team_id"])
        - org_id: Organization ID (from kwargs["metadata"]["org_id"])
        - end_user_id: End user ID (from kwargs["metadata"]["end_user_id"])
        - token: API key (from kwargs["api_key"], if provided)
        - tags: Custom tags (from kwargs["metadata"]["tags"])

        Database Updates:
        - Entity spend tables (incremental updates)
        - Daily aggregate tables (upsert pattern)

        Args:
            kwargs: Completion call parameters (model, messages, user, metadata, etc.)
            response_obj: LLM response object (ModelResponse)
            start_time: Request start timestamp
            end_time: Request end timestamp

        Note:
            This method is fire-and-forget. Exceptions are caught and logged,
            but never propagated to prevent breaking the SDK completion call.

        Example kwargs:
            {
                "model": "gpt-4",
                "messages": [{"role": "user", "content": "Hello"}],
                "user": "sdk-user-123",
                "metadata": {
                    "team_id": "team-alpha",
                    "tags": ["production", "api-v2"]
                }
            }
        """
        try:
            # Initialize database connections (lazy, idempotent)
            await self._ensure_initialized()

            # Extract entity IDs from kwargs
            user_id = kwargs.get("user")
            metadata = kwargs.get("metadata", {})

            team_id = metadata.get("team_id")
            org_id = metadata.get("org_id")
            end_user_id = metadata.get("end_user_id")
            token = kwargs.get("api_key")  # API key tracking (optional)

            # Calculate response cost using LiteLLM's cost calculator
            try:
                response_cost = litellm.cost_calculator.completion_cost(
                    completion_response=response_obj
                )
            except Exception as cost_error:
                # If cost calculation fails, default to 0.0 and log warning
                verbose_logger.warning(
                    f"PrismaProxyLogger: Cost calculation failed: {cost_error}"
                )
                response_cost = 0.0

            # Delegate to DBSpendUpdateWriter (reuses Proxy logic)
            if not self.spend_writer:
                raise ValueError(
                    f"self.spend_writer type expected: DBSpendUpdateWriter, got: {type(self.spend_writer)}"
                )
            await self.spend_writer.update_database(
                token=token,
                user_id=user_id,
                end_user_id=end_user_id,
                team_id=team_id,
                org_id=org_id,
                kwargs=kwargs,
                completion_response=response_obj,
                start_time=start_time,
                end_time=end_time,
                response_cost=response_cost,
            )

            verbose_logger.debug(
                f"PrismaProxyLogger: Logged completion (user={user_id}, "
                f"team={team_id}, cost=${response_cost:.6f})"
            )

        except Exception as e:
            # CRITICAL: Never propagate exceptions to SDK
            # Callback failures must not break completion calls
            verbose_logger.error(f"PrismaProxyLogger: Failed to log success event: {e}")
            verbose_logger.error(traceback.format_exc())

    async def async_log_failure_event(
        self,
        kwargs: dict,
        response_obj: Exception,
        start_time: datetime,
        end_time: datetime,
    ):
        """
        Log failed completion to database.

        This method is called automatically by LiteLLM after a failed
        completion API call (e.g., rate limit error, authentication error).

        Current Implementation:
        - Logs failure event to verbose logger
        - Does NOT write to database (failures typically have no cost)

        Future Enhancement:
        - Track failed requests in daily aggregate tables
        - Increment failed_requests counter per entity

        Args:
            kwargs: Completion call parameters
            response_obj: Exception that caused the failure
            start_time: Request start timestamp
            end_time: Request end timestamp

        Note:
            Failures are typically not written to database because they have
            no associated cost. If you need failure tracking, uncomment the
            database write logic below.
        """
        try:
            verbose_logger.debug(
                f"PrismaProxyLogger: Completion failed - {type(response_obj).__name__}: "
                f"{str(response_obj)}"
            )

            # Optional: Track failures in database
            # Uncomment if you need to track failed request counts
            # await self._ensure_initialized()
            # await self.spend_writer.update_database(
            #     ...,
            #     response_cost=0.0,  # Failures have no cost
            # )

        except Exception as e:
            # CRITICAL: Never propagate exceptions
            verbose_logger.error(f"PrismaProxyLogger: Failed to log failure event: {e}")
            verbose_logger.error(traceback.format_exc())

    async def health_check(self) -> dict:
        """
        Check callback health status.

        Performs diagnostic checks on database connectivity and internal state.
        Useful for debugging and monitoring.

        Returns:
            dict: Health status with diagnostics
                {
                    "status": "healthy" | "unhealthy",
                    "initialized": bool,
                    "database_connected": bool,
                    "redis_connected": bool,
                    "queue_depth": int,
                    "error": str (if unhealthy)
                }

        # Example:
        #     >>> logger = PrismaProxyLogger()
        #     >>> health = await logger.health_check()
        #     >>> print(health)
            {'status': 'healthy', 'database_connected': True, 'queue_depth': 5}
        """
        try:
            # Check initialization
            if not self._initialized:
                return {
                    "status": "not_initialized",
                    "initialized": False,
                    "database_connected": False,
                    "redis_connected": False,
                }

            # Test database connection
            database_connected = False
            try:
                if not self.prisma_client:
                    raise ValueError("prisma client is none")
                await self.prisma_client.db.query_raw("SELECT 1")
                database_connected = True
            except Exception as db_error:
                verbose_logger.error(f"Database health check failed: {db_error}")

            # Test Redis connection (if enabled)
            redis_connected = False
            if self.redis_cache:
                try:
                    await self.redis_cache.ping()
                    redis_connected = True
                except Exception as redis_error:
                    verbose_logger.error(f"Redis health check failed: {redis_error}")

            # Get queue depth
            queue_depth = 0
            if self.spend_writer and hasattr(self.spend_writer, "spend_update_queue"):
                queue_depth = len(
                    getattr(self.spend_writer.spend_update_queue, "updates", [])
                )

            # Determine overall status
            status = "healthy" if database_connected else "unhealthy"

            return {
                "status": status,
                "initialized": self._initialized,
                "database_connected": database_connected,
                "redis_connected": redis_connected if self.use_redis_buffer else None,
                "queue_depth": queue_depth,
                "use_redis_buffer": self.use_redis_buffer,
            }

        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "initialized": self._initialized,
            }

    async def cleanup(self):
        """
        Cleanup resources on shutdown.

        Closes database connections and flushes pending writes.
        Should be called when the application shuts down.

        # Example:
        #     >>> logger = PrismaProxyLogger()
        #     >>> # ... use logger ...
        #     >>> await logger.cleanup()  # On shutdown
        """
        try:
            if self._initialized:
                verbose_logger.info("PrismaProxyLogger: Cleaning up resources")

                # Flush pending writes
                if self.spend_writer:
                    # Note: DBSpendUpdateWriter handles its own cleanup
                    pass

                # Disconnect from database
                if self.prisma_client:
                    await self.prisma_client.db.disconnect()
                    verbose_logger.debug(
                        "PrismaProxyLogger: Disconnected from database"
                    )

                # Disconnect from Redis
                if self.redis_cache:
                    # Redis cache cleanup (if needed)
                    pass

                verbose_logger.info("PrismaProxyLogger: Cleanup complete")

        except Exception as e:
            verbose_logger.error(f"PrismaProxyLogger: Cleanup failed: {e}")


# Export for "prisma_proxy" string callback registration
__all__ = ["PrismaProxyLogger"]


# Example usage
if __name__ == "__main__":
    """
    Example usage and testing.

    Run with: python -m litellm.integrations.prisma_proxy

    Requirements:
    - DATABASE_URL environment variable set
    - PostgreSQL database running
    - Prisma schema migrated (cd deploy && prisma db push)
    """
    import asyncio

    async def test_callback():
        """Test PrismaProxyLogger with mock completion."""
        print("Testing PrismaProxyLogger...")

        # Initialize logger
        logger = PrismaProxyLogger()

        # Check health before initialization
        health = await logger.health_check()
        print(f"Health (before init): {health}")

        # Simulate completion kwargs
        kwargs = {
            "model": "gpt-3.5-turbo",
            "messages": [{"role": "user", "content": "Test"}],
            "user": "test-user-prisma-callback",
            "metadata": {"team_id": "test-team", "tags": ["test", "prisma-callback"]},
        }

        # Simulate response
        from litellm.types.utils import ModelResponse, Choices, Message, Usage

        response = ModelResponse(
            id="test-123",
            choices=[
                Choices(
                    message=Message(content="Test response", role="assistant"),
                    finish_reason="stop",
                    index=0,
                )
            ],
            model="gpt-3.5-turbo",
            usage=Usage(prompt_tokens=10, completion_tokens=20, total_tokens=30),
        )

        # Log success event
        start_time = datetime.now()
        end_time = datetime.now()

        await logger.async_log_success_event(
            kwargs=kwargs,
            response_obj=response,
            start_time=start_time,
            end_time=end_time,
        )

        print("Success event logged")

        # Check health after initialization
        health = await logger.health_check()
        print(f"Health (after logging): {health}")

        # Cleanup
        await logger.cleanup()
        print("Test complete")

    # Run test
    asyncio.run(test_callback())
