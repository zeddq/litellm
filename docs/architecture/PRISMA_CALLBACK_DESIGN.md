# Prisma Callback Integration Design (Option 1)

**Status**: Design Phase  
**Version**: 1.0  
**Last Updated**: 2025-11-02  
**Author**: AI Assistant (Claude Code)

---

## Executive Summary

This document specifies the design for implementing a Prisma-based database persistence callback for the LiteLLM SDK. This enables the SDK to write directly to the same PostgreSQL database that the LiteLLM Proxy reads from, allowing the Proxy to serve as a read-only UI for SDK-persisted data.

**Key Design Principles:**
1. **Reuse over Reinvention**: Wrap existing `DBSpendUpdateWriter` logic
2. **Compatibility**: Works alongside OpenTelemetry and other callbacks
3. **Performance**: <50ms write latency (negligible vs 500-2000ms LLM API calls)
4. **Simplicity**: Minimal code, maximum leverage of battle-tested patterns

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Component Design](#component-design)
3. [Database Schema](#database-schema)
4. [Implementation Strategy](#implementation-strategy)
5. [Configuration](#configuration)
6. [Testing Strategy](#testing-strategy)
7. [Performance Characteristics](#performance-characteristics)
8. [Monitoring & Observability](#monitoring--observability)
9. [Rollout Plan](#rollout-plan)
10. [Risk Mitigation](#risk-mitigation)

---

## Architecture Overview

### High-Level Data Flow

```mermaid
graph TD
    User[User Application<br>SDK Client] -->|litellm.completion| SDK[LiteLLM SDK]
    
    subgraph SDK_Process[LiteLLM SDK Process]
        SDK -->|Completion Logic| API[LLM Provider API]
        SDK -->|Trigger Callbacks| Manager[Callback Manager]
        
        Manager -->|Parallel Execution| Prisma[Prisma Callback]
        Manager -->|Parallel Execution| OTel[OpenTelemetry Callback]
        Manager -->|Parallel Execution| Langfuse[Langfuse Callback]
        Manager -->|Parallel Execution| Prom[Prometheus Callback]
        
        Prisma -->|Async Write| Writer[DBSpendUpdateWriter]
        
        subgraph Writer_Logic[DBSpendUpdateWriter]
            Writer --> Queue[In-Memory Queues]
            Queue -->|Batch Writes| Buffer[Optional: Redis Buffer]
            Buffer -->|Distributed Lock| Lock[PodLockManager]
            Lock -->|Transaction| Commit[Batch Transaction Commit]
        end
    end
    
    Commit -->|SQL INSERT/UPDATE| DB[(PostgreSQL Database)]
    
    subgraph Database[PostgreSQL Database]
        Entities[Entity Tables<br>Users, Teams, Keys]
        Aggregates[Daily Aggregate Tables<br>Spend, Usage]
    end
    
    Proxy[LiteLLM Proxy<br>Read-Only UI] -->|SQL SELECT| DB
```

### Component Interaction

```mermaid
sequenceDiagram
    participant User as User Code
    participant SDK as LiteLLM SDK
    participant Callback as Prisma Callback
    participant Database as Database

    User->>SDK: completion(...)
    SDK->>SDK: API call to LLM provider<br>(500-2000ms)
    SDK-->>User: Response
    
    par Async Execution
        SDK->>Callback: Trigger callbacks (async)
        Callback->>Callback: Queue update (1-5ms)
        Callback-->>SDK: Callback returns<br>(non-blocking)
    end
    
    loop Background Process (every 10-30s)
        Callback->>Database: Batch write
        Database-->>Callback: Write confirmed<br>(10-50ms batch)
    end
```

**Key Characteristics:**
- **Non-blocking**: Callback returns immediately after queueing
- **Async batching**: Writes accumulated and committed in batches
- **Retry logic**: Exponential backoff on connection errors
- **Multi-instance safe**: Optional Redis buffer + distributed locking

---

## Component Design

### 1. PrismaProxyLogger (New Class)

**File**: `litellm/integrations/prisma_proxy.py`

**Purpose**: CustomLogger implementation that routes SDK completion events to the Prisma database

**Interface:**
```python
class PrismaProxyLogger(CustomLogger):
    """
    Database persistence callback for LiteLLM SDK.
    
    Writes completion events to PostgreSQL via Prisma ORM,
    enabling the LiteLLM Proxy to display SDK-persisted data.
    
    Compatible with other callbacks (OpenTelemetry, Langfuse, etc.)
    
    Example:
        >>> import litellm
        >>> litellm.success_callback = ["prisma_proxy", "opentelemetry"]
        >>> response = litellm.completion(
        ...     model="gpt-4",
        ...     messages=[{"role": "user", "content": "Hello"}],
        ...     user="sdk-user-123"
        ... )
    """
    
    def __init__(
        self,
        database_url: Optional[str] = None,
        redis_url: Optional[str] = None,
        use_redis_buffer: bool = False,
        **kwargs
    ):
        """
        Initialize Prisma database callback.
        
        Args:
            database_url: PostgreSQL connection string (default: from env DATABASE_URL)
            redis_url: Redis connection string (default: from env REDIS_URL)
            use_redis_buffer: Enable Redis buffer for multi-instance deployments
            **kwargs: Additional CustomLogger parameters
        """
        super().__init__(**kwargs)
        
        # Initialize database connection
        self.database_url = database_url or os.getenv("DATABASE_URL")
        self.redis_url = redis_url or os.getenv("REDIS_URL")
        self.use_redis_buffer = use_redis_buffer
        
        # Initialize components
        self.prisma_client: Optional[PrismaClient] = None
        self.spend_writer: Optional[DBSpendUpdateWriter] = None
        self._initialized = False
    
    async def _ensure_initialized(self):
        """Lazy initialization of database connections."""
        if self._initialized:
            return
        
        # Initialize PrismaClient
        self.prisma_client = await self._init_prisma_client()
        
        # Initialize DBSpendUpdateWriter
        redis_cache = await self._init_redis_cache() if self.use_redis_buffer else None
        self.spend_writer = DBSpendUpdateWriter(redis_cache=redis_cache)
        
        self._initialized = True
    
    async def async_log_success_event(
        self,
        kwargs: dict,
        response_obj: ModelResponse,
        start_time: datetime,
        end_time: datetime
    ):
        """
        Log successful completion to database.
        
        Args:
            kwargs: Completion call parameters (model, messages, user, etc.)
            response_obj: LLM response object
            start_time: Request start timestamp
            end_time: Request end timestamp
        """
        try:
            await self._ensure_initialized()
            
            # Extract entity IDs from kwargs
            user_id = kwargs.get("user")
            team_id = kwargs.get("metadata", {}).get("team_id")
            org_id = kwargs.get("metadata", {}).get("org_id")
            token = kwargs.get("api_key")  # If using API key tracking
            end_user_id = kwargs.get("metadata", {}).get("end_user_id")
            
            # Calculate response cost
            response_cost = litellm.completion_cost(completion_response=response_obj)
            
            # Delegate to DBSpendUpdateWriter
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
            
        except Exception as e:
            # Non-blocking: log error but don't raise
            verbose_logger.error(f"PrismaProxyLogger error: {e}")
            verbose_logger.error(traceback.format_exc())
    
    async def async_log_failure_event(
        self,
        kwargs: dict,
        response_obj: Exception,
        start_time: datetime,
        end_time: datetime
    ):
        """Log failed completion to database (optional tracking)."""
        # Similar to async_log_success_event but marks as failed
        pass
```

**Key Design Decisions:**

1. **Lazy Initialization**: Database connections initialized on first use
   - Avoids startup overhead if callback not used
   - Handles connection pool warmup gracefully

2. **Exception Safety**: All errors caught and logged, never propagated
   - Prevents callback failures from breaking SDK calls
   - Follows LiteLLM callback contract

3. **Delegation Pattern**: Delegates to `DBSpendUpdateWriter`
   - Reuses battle-tested batch/retry logic
   - Maintains consistency with Proxy behavior
   - ~100 lines vs ~1400 lines if reimplemented

---

### 2. Database Connection Management

**Challenge**: SDK runs in user's application process, Proxy runs separately

**Solution**: SDK creates its own `PrismaClient` instance

```python
async def _init_prisma_client(self) -> PrismaClient:
    """
    Initialize PrismaClient for SDK use.
    
    Creates a separate database connection pool for SDK callbacks,
    independent of the Proxy's connection pool.
    """
    from litellm.proxy.utils import PrismaClient, ProxyLogging
    from prisma import Prisma
    
    # Create minimal ProxyLogging instance for SDK
    sdk_logging = ProxyLogging()
    
    # Initialize Prisma client
    prisma_client = PrismaClient(
        database_url=self.database_url,
        proxy_logging_obj=sdk_logging,
    )
    
    # Connect to database
    await prisma_client.db.connect()
    
    return prisma_client
```

**Connection Pool Settings:**
- Default: 20 connections (lower than Proxy's 100)
- Timeout: 60 seconds
- Rationale: SDK typically lower RPS than Proxy

---

### 3. Multi-Instance Coordination (Optional)

**Scenario**: Multiple SDK instances writing to same database

**Problem**: Database lock contention, deadlocks at high RPS

**Solution**: Redis buffer + distributed locking (same as Proxy)

```python
async def _init_redis_cache(self) -> Optional[RedisCache]:
    """
    Initialize Redis cache for multi-instance coordination.
    
    Only required if use_redis_buffer=True.
    Enables horizontal scaling with multiple SDK instances.
    """
    if not self.redis_url:
        return None
    
    from litellm.caching import RedisCache
    
    redis_cache = RedisCache(
        host=self.redis_url,
        # Additional Redis configuration
    )
    
    return redis_cache
```

**When to Enable:**
- [ ] Single SDK instance: **No** (unnecessary overhead)
- [x] Multiple SDK instances (>2): **Yes** (prevents lock contention)
- [x] High RPS (>100 req/s): **Yes** (batch efficiency)

---

## Database Schema

### Entity Tables (Incremental Spend Updates)

#### litellm_usertable
**Purpose**: Track per-user spend

```sql
CREATE TABLE litellm_usertable (
    user_id VARCHAR(255) PRIMARY KEY,
    spend DECIMAL(10, 2) DEFAULT 0.00,  -- Incremented on each completion
    max_budget DECIMAL(10, 2),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_usertable_spend ON litellm_usertable(spend DESC);
```

**Updates**: `spend = spend + response_cost` (atomic increment)

#### litellm_teamtable
**Purpose**: Track per-team spend

```sql
CREATE TABLE litellm_teamtable (
    team_id VARCHAR(255) PRIMARY KEY,
    team_alias VARCHAR(255),
    spend DECIMAL(10, 2) DEFAULT 0.00,
    max_budget DECIMAL(10, 2),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

#### litellm_verificationtoken
**Purpose**: Track per-API-key spend

```sql
CREATE TABLE litellm_verificationtoken (
    token VARCHAR(255) PRIMARY KEY,
    key_name VARCHAR(255),
    spend DECIMAL(10, 2) DEFAULT 0.00,
    max_budget DECIMAL(10, 2),
    expires TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);
```

#### litellm_endusertable
**Purpose**: Track end-user spend (customer's end users)

```sql
CREATE TABLE litellm_endusertable (
    user_id VARCHAR(255) PRIMARY KEY,
    end_user_id VARCHAR(255) UNIQUE,
    spend DECIMAL(10, 2) DEFAULT 0.00,
    created_at TIMESTAMP DEFAULT NOW()
);
```

#### litellm_organizationtable
**Purpose**: Track organization-level spend

```sql
CREATE TABLE litellm_organizationtable (
    organization_id VARCHAR(255) PRIMARY KEY,
    organization_alias VARCHAR(255),
    spend DECIMAL(10, 2) DEFAULT 0.00,
    max_budget DECIMAL(10, 2),
    created_at TIMESTAMP DEFAULT NOW()
);
```

#### litellm_tagtable
**Purpose**: Track spend by custom tags

```sql
CREATE TABLE litellm_tagtable (
    tag VARCHAR(255) PRIMARY KEY,
    spend DECIMAL(10, 2) DEFAULT 0.00,
    created_at TIMESTAMP DEFAULT NOW()
);
```

---

### Daily Aggregate Tables (Upsert Pattern)

#### litellm_dailyuserspend
**Purpose**: Daily spend breakdown per user/model/provider

```sql
CREATE TABLE litellm_dailyuserspend (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id VARCHAR(255) NOT NULL,
    date DATE NOT NULL,
    api_key VARCHAR(255),
    model VARCHAR(255),
    custom_llm_provider VARCHAR(255),
    prompt_tokens BIGINT DEFAULT 0,
    completion_tokens BIGINT DEFAULT 0,
    spend DECIMAL(10, 2) DEFAULT 0.00,
    api_requests INTEGER DEFAULT 0,
    successful_requests INTEGER DEFAULT 0,
    failed_requests INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    
    CONSTRAINT unique_daily_user_spend UNIQUE (
        user_id, date, api_key, model, custom_llm_provider
    )
);

CREATE INDEX idx_dailyuserspend_date ON litellm_dailyuserspend(date DESC);
CREATE INDEX idx_dailyuserspend_user ON litellm_dailyuserspend(user_id, date DESC);
```

**Upsert Logic:**
```python
# On each completion
await prisma_client.litellm_dailyuserspend.upsert(
    where={
        "unique_daily_user_spend": {
            "user_id": user_id,
            "date": current_date,
            "api_key": api_key,
            "model": model,
            "custom_llm_provider": provider,
        }
    },
    data={
        "create": {
            "user_id": user_id,
            "date": current_date,
            "api_key": api_key,
            "model": model,
            "custom_llm_provider": provider,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "spend": spend,
            "api_requests": 1,
            "successful_requests": 1,
            "failed_requests": 0,
        },
        "update": {
            "prompt_tokens": {"increment": prompt_tokens},
            "completion_tokens": {"increment": completion_tokens},
            "spend": {"increment": spend},
            "api_requests": {"increment": 1},
            "successful_requests": {"increment": 1},
        },
    },
)
```

#### litellm_dailyteamspend
**Purpose**: Daily team-level spend breakdown

```sql
CREATE TABLE litellm_dailyteamspend (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    team_id VARCHAR(255) NOT NULL,
    date DATE NOT NULL,
    api_key VARCHAR(255),
    model VARCHAR(255),
    custom_llm_provider VARCHAR(255),
    prompt_tokens BIGINT DEFAULT 0,
    completion_tokens BIGINT DEFAULT 0,
    spend DECIMAL(10, 2) DEFAULT 0.00,
    api_requests INTEGER DEFAULT 0,
    successful_requests INTEGER DEFAULT 0,
    failed_requests INTEGER DEFAULT 0,
    
    CONSTRAINT unique_daily_team_spend UNIQUE (
        team_id, date, api_key, model, custom_llm_provider
    )
);
```

#### litellm_dailytagspend
**Purpose**: Daily tag-based spend breakdown

```sql
CREATE TABLE litellm_dailytagspend (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tag VARCHAR(255) NOT NULL,
    date DATE NOT NULL,
    api_key VARCHAR(255),
    model VARCHAR(255),
    custom_llm_provider VARCHAR(255),
    prompt_tokens BIGINT DEFAULT 0,
    completion_tokens BIGINT DEFAULT 0,
    spend DECIMAL(10, 2) DEFAULT 0.00,
    api_requests INTEGER DEFAULT 0,
    
    CONSTRAINT unique_daily_tag_spend UNIQUE (
        tag, date, api_key, model, custom_llm_provider
    )
);
```

---

### Schema Migrations

**File**: `deploy/schema.prisma` (already exists in LiteLLM)

**No changes required** - Prisma callback uses existing schema

**Migration steps** (if database is fresh):
```bash
cd deploy/
prisma generate
prisma db push
```

---

## Implementation Strategy

### Phase 1: Core Implementation (Days 1-2)

**Deliverables:**
1. `litellm/integrations/prisma_proxy.py` (~200-300 lines)
2. Unit tests for PrismaProxyLogger
3. Integration test with real database

**Steps:**

**Day 1 Morning**: Scaffold PrismaProxyLogger class
```python
# litellm/integrations/prisma_proxy.py
from litellm.integrations.custom_logger import CustomLogger
from litellm.proxy.db.db_spend_update_writer import DBSpendUpdateWriter

class PrismaProxyLogger(CustomLogger):
    def __init__(self, database_url=None, **kwargs):
        super().__init__(**kwargs)
        self.database_url = database_url or os.getenv("DATABASE_URL")
        self._initialized = False
    
    async def async_log_success_event(self, kwargs, response_obj, start_time, end_time):
        # TODO: Implement
        pass
```

**Day 1 Afternoon**: Implement database initialization
```python
async def _ensure_initialized(self):
    """Initialize Prisma client and spend writer."""
    if self._initialized:
        return
    
    self.prisma_client = await self._init_prisma_client()
    self.spend_writer = DBSpendUpdateWriter()
    self._initialized = True
```

**Day 2 Morning**: Implement callback logic
```python
async def async_log_success_event(self, kwargs, response_obj, start_time, end_time):
    await self._ensure_initialized()
    
    # Extract entity IDs
    user_id = kwargs.get("user")
    team_id = kwargs.get("metadata", {}).get("team_id")
    # ... etc
    
    # Calculate cost
    response_cost = litellm.completion_cost(completion_response=response_obj)
    
    # Delegate to writer
    await self.spend_writer.update_database(
        user_id=user_id,
        team_id=team_id,
        kwargs=kwargs,
        completion_response=response_obj,
        start_time=start_time,
        end_time=end_time,
        response_cost=response_cost,
    )
```

**Day 2 Afternoon**: Testing
- Unit tests: Mock PrismaClient, verify method calls
- Integration test: Real database, verify writes
- Multi-callback test: With OpenTelemetry

---

### Phase 2: Redis Buffer Support (Day 3, Optional)

**Only if targeting multi-instance deployments**

**Deliverables:**
1. Redis configuration support
2. PodLockManager integration
3. Multi-instance tests

**Implementation:**
```python
async def _init_redis_cache(self) -> Optional[RedisCache]:
    if not self.redis_url or not self.use_redis_buffer:
        return None
    
    redis_cache = RedisCache(host=self.redis_url)
    return redis_cache
```

---

### Phase 3: Documentation & Examples (Day 4)

**Deliverables:**
1. Usage guide (`docs/guides/sdk-database-persistence.md`)
2. Configuration examples
3. Troubleshooting guide

---

## Configuration

### Basic Configuration (Single Instance)

```python
import litellm

# Enable Prisma callback
litellm.success_callback = ["prisma_proxy"]

# Set database URL (or via environment variable)
import os
os.environ["DATABASE_URL"] = "postgresql://user:pass@localhost:5432/litellm"

# Make completion calls
response = litellm.completion(
    model="gpt-4",
    messages=[{"role": "user", "content": "Hello"}],
    user="sdk-user-123",  # Tracked in litellm_usertable
    metadata={
        "team_id": "team-alpha",  # Tracked in litellm_teamtable
        "tags": ["production", "api-v2"]  # Tracked in litellm_tagtable
    }
)
```

### Multi-Callback Configuration

```python
import litellm

# Enable multiple callbacks
litellm.success_callback = ["prisma_proxy", "opentelemetry", "langfuse"]

# Each callback executes independently
response = litellm.completion(
    model="gpt-4",
    messages=[{"role": "user", "content": "Hello"}],
    user="sdk-user-123"
)
# → Writes to Prisma database
# → Exports to OpenTelemetry
# → Logs to Langfuse
```

### Multi-Instance Configuration (with Redis)

```python
import litellm
from litellm.integrations.prisma_proxy import PrismaProxyLogger

# Initialize with Redis buffer
prisma_logger = PrismaProxyLogger(
    database_url="postgresql://user:pass@localhost:5432/litellm",
    redis_url="redis://localhost:6379",
    use_redis_buffer=True,  # Enable for multi-instance
)

# Register callback
litellm.callbacks = [prisma_logger]
litellm.success_callback = [prisma_logger.async_log_success_event]

# Now multiple SDK instances can write safely
```

### Environment Variables

```bash
# Required
export DATABASE_URL="postgresql://user:pass@localhost:5432/litellm"

# Optional (for multi-instance)
export REDIS_URL="redis://localhost:6379"
export USE_REDIS_TRANSACTION_BUFFER="true"

# Optional (logging)
export LITELLM_LOG="DEBUG"
```

---

## Testing Strategy

### Unit Tests

**File**: `tests/test_prisma_proxy_callback.py`

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime
import litellm
from litellm.integrations.prisma_proxy import PrismaProxyLogger

@pytest.mark.asyncio
async def test_prisma_callback_initialization():
    """Test PrismaProxyLogger initializes correctly."""
    logger = PrismaProxyLogger(database_url="postgresql://test")
    assert logger.database_url == "postgresql://test"
    assert not logger._initialized

@pytest.mark.asyncio
async def test_callback_success_event():
    """Test successful completion logging."""
    # Mock PrismaClient and DBSpendUpdateWriter
    with patch("litellm.integrations.prisma_proxy.PrismaClient") as mock_prisma:
        with patch("litellm.integrations.prisma_proxy.DBSpendUpdateWriter") as mock_writer:
            logger = PrismaProxyLogger()
            
            # Mock response
            response = litellm.ModelResponse(
                id="chatcmpl-123",
                choices=[...],
                usage={"prompt_tokens": 10, "completion_tokens": 20}
            )
            
            kwargs = {"user": "test-user", "model": "gpt-4"}
            await logger.async_log_success_event(
                kwargs=kwargs,
                response_obj=response,
                start_time=datetime.now(),
                end_time=datetime.now()
            )
            
            # Verify DBSpendUpdateWriter.update_database was called
            mock_writer.return_value.update_database.assert_called_once()

@pytest.mark.asyncio
async def test_multiple_callbacks():
    """Test Prisma callback works alongside others."""
    litellm.success_callback = ["prisma_proxy", "opentelemetry"]
    
    response = litellm.completion(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": "Test"}],
        user="test-user",
        mock_response="Hello!"  # Use mock to avoid real API call
    )
    
    # Verify both callbacks were triggered
    # (check logs or mock calls)
```

### Integration Tests

**File**: `tests/integration/test_prisma_callback_integration.py`

```python
import pytest
import litellm
from litellm.proxy.utils import PrismaClient

@pytest.mark.integration
@pytest.mark.asyncio
async def test_end_to_end_database_write():
    """Test SDK writes to database and Proxy can read."""
    # Setup: Clean database
    prisma_client = PrismaClient(database_url=os.getenv("DATABASE_URL"))
    await prisma_client.db.connect()
    
    # Clear test user data
    await prisma_client.db.litellm_usertable.delete_many(
        where={"user_id": "integration-test-user"}
    )
    
    # Enable Prisma callback
    litellm.success_callback = ["prisma_proxy"]
    
    # Make SDK call
    response = litellm.completion(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": "Hello"}],
        user="integration-test-user"
    )
    
    # Wait for async write to complete (up to 5 seconds)
    await asyncio.sleep(5)
    
    # Verify database write
    user = await prisma_client.db.litellm_usertable.find_unique(
        where={"user_id": "integration-test-user"}
    )
    
    assert user is not None
    assert user.spend > 0
    
    # Cleanup
    await prisma_client.db.litellm_usertable.delete_many(
        where={"user_id": "integration-test-user"}
    )
    await prisma_client.db.disconnect()
```

### Load Tests

**File**: `tests/load/test_prisma_callback_performance.py`

```python
import pytest
import asyncio
import litellm
from datetime import datetime

@pytest.mark.load
@pytest.mark.asyncio
async def test_concurrent_requests():
    """Test callback performance under load."""
    litellm.success_callback = ["prisma_proxy"]
    
    async def make_completion(i):
        start = datetime.now()
        response = litellm.completion(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": f"Request {i}"}],
            user=f"load-test-user-{i % 10}",  # 10 different users
            mock_response="Response"  # Mock to avoid API cost
        )
        end = datetime.now()
        return (end - start).total_seconds()
    
    # Run 100 concurrent requests
    latencies = await asyncio.gather(*[make_completion(i) for i in range(100)])
    
    # Assert callback overhead < 100ms for 95th percentile
    p95 = sorted(latencies)[94]
    assert p95 < 0.1, f"95th percentile latency: {p95}s (expected <0.1s)"
```

---

## Performance Characteristics

### Latency Profile

| Operation | Target Latency | Notes |
|-----------|---------------|-------|
| Callback trigger | <1ms | Async fire-and-forget |
| Queue write | 1-5ms | In-memory append |
| Batch commit | 10-50ms | Every 10-30s, batched updates |
| End-to-end (user perspective) | +0ms | Non-blocking, happens in background |

### Throughput Targets

| Configuration | Max RPS | Notes |
|--------------|---------|-------|
| Single instance (no Redis) | ~100 RPS | Limited by DB connection pool |
| Multi-instance (with Redis) | ~1000+ RPS | Scales horizontally |

### Resource Usage

| Resource | Expected Usage | Notes |
|----------|---------------|-------|
| Database connections | 10-20 per SDK instance | Lower than Proxy (100) |
| Memory | ~50-100MB per instance | Queue buffers, Prisma client |
| CPU | <5% per instance | Mostly I/O bound |

---

## Monitoring & Observability

### Key Metrics

**Database Metrics:**
```python
# Track via OpenTelemetry or custom metrics
prisma_callback_writes_total          # Counter: Total write attempts
prisma_callback_writes_success        # Counter: Successful writes
prisma_callback_writes_failed         # Counter: Failed writes
prisma_callback_batch_size            # Histogram: Updates per batch
prisma_callback_batch_latency_ms      # Histogram: Batch write latency
prisma_callback_queue_depth           # Gauge: Pending updates in queue
```

**Example OpenTelemetry Integration:**
```python
from opentelemetry import metrics

meter = metrics.get_meter("prisma_callback")
writes_counter = meter.create_counter(
    "prisma_callback.writes.total",
    description="Total database write attempts"
)

# In async_log_success_event:
writes_counter.add(1, {"status": "success"})
```

### Logging

**Structured Logging:**
```python
import logging

logger = logging.getLogger("litellm.prisma_callback")

# On successful write
logger.info(
    "Database write successful",
    extra={
        "user_id": user_id,
        "team_id": team_id,
        "response_cost": response_cost,
        "batch_size": batch_size,
        "latency_ms": latency_ms
    }
)

# On error
logger.error(
    "Database write failed",
    extra={
        "error": str(e),
        "user_id": user_id,
        "retry_count": retry_count
    },
    exc_info=True
)
```

### Health Checks

```python
class PrismaProxyLogger(CustomLogger):
    async def health_check(self) -> dict:
        """
        Check callback health status.
        
        Returns:
            dict: Health status with diagnostics
        """
        try:
            await self._ensure_initialized()
            
            # Test database connection
            await self.prisma_client.db.query_raw("SELECT 1")
            
            return {
                "status": "healthy",
                "database_connected": True,
                "queue_depth": len(self.spend_writer.spend_update_queue.updates),
                "initialized": self._initialized
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e),
                "database_connected": False
            }
```

---

## Rollout Plan

### Day 1: Implementation
- [ ] Create `litellm/integrations/prisma_proxy.py`
- [ ] Implement `PrismaProxyLogger` class
- [ ] Add database initialization logic
- [ ] Implement callback methods

### Day 2: Testing
- [ ] Unit tests (mocked dependencies)
- [ ] Integration test (real database)
- [ ] Multi-callback test (with OpenTelemetry)
- [ ] Load test (100 concurrent requests)

### Day 3: Documentation
- [ ] Usage guide (`docs/guides/sdk-database-persistence.md`)
- [ ] Configuration examples
- [ ] Troubleshooting section

### Day 4: Deployment (Local Dev)
- [ ] Enable callback in your local SDK code
- [ ] Verify writes in database
- [ ] Check Proxy UI displays SDK data
- [ ] Monitor performance metrics

---

## Risk Mitigation

### Risk 1: Database Connection Pool Exhaustion

**Scenario**: SDK creates too many connections, exhausts PostgreSQL pool

**Mitigation:**
- Limit SDK connection pool to 20 (vs Proxy's 100)
- Monitor connection count via `pg_stat_activity`
- Implement connection timeout (60s)

**Detection:**
```sql
-- Check active connections
SELECT count(*) FROM pg_stat_activity 
WHERE datname = 'litellm' AND application_name LIKE '%prisma%';
```

### Risk 2: Callback Failures Breaking SDK Calls

**Scenario**: Database error causes callback exception, breaks completion call

**Mitigation:**
- Wrap all callback code in try-except
- Never propagate exceptions to SDK
- Log errors but continue execution

**Implementation:**
```python
async def async_log_success_event(self, kwargs, response_obj, start_time, end_time):
    try:
        # All callback logic here
        pass
    except Exception as e:
        # Log but don't raise
        logger.error(f"Callback failed: {e}")
        # SDK call continues successfully
```

### Risk 3: Multi-Instance Write Conflicts

**Scenario**: Two SDK instances write to same entity simultaneously, causing deadlock

**Mitigation:**
- Enable Redis buffer for multi-instance deployments
- Use PodLockManager for distributed coordination
- Implement exponential backoff on conflicts

**Detection:**
```python
# Monitor deadlock errors
if "deadlock detected" in str(error).lower():
    logger.warning("Deadlock detected, consider enabling Redis buffer")
```

### Risk 4: Stale Data in Proxy UI

**Scenario**: SDK writes queued, not yet committed to DB when Proxy queries

**Mitigation:**
- Document eventual consistency (100-500ms lag)
- Batch commits every 10-30s (configurable)
- Add "last updated" timestamp to UI

**User Communication:**
"SDK data may take up to 30 seconds to appear in the dashboard due to batching."

---

## Future Enhancements (Post-Phase 1)

### Enhancement 1: Spend Log Table
Track full request/response details (not just aggregates)

```sql
CREATE TABLE litellm_spendlogs (
    id UUID PRIMARY KEY,
    user_id VARCHAR(255),
    model VARCHAR(255),
    request_id VARCHAR(255),
    prompt_tokens INTEGER,
    completion_tokens INTEGER,
    spend DECIMAL(10, 2),
    request JSONB,
    response JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);
```

### Enhancement 2: Real-time Updates
WebSocket connection to push updates to Proxy UI immediately

### Enhancement 3: Query Optimization
Add materialized views for common dashboard queries

```sql
CREATE MATERIALIZED VIEW mv_user_spend_summary AS
SELECT 
    user_id,
    SUM(spend) as total_spend,
    COUNT(*) as request_count,
    MAX(updated_at) as last_activity
FROM litellm_usertable
GROUP BY user_id;
```

### Enhancement 4: Data Archival
Move old daily aggregate rows to cold storage (S3, Glacier)

---

## Appendix

### A. Code References

- **DBSpendUpdateWriter**: `/Volumes/code/litellm/litellm/proxy/db/db_spend_update_writer.py`
- **CustomLogger**: `/Volumes/code/litellm/litellm/integrations/custom_logger.py`
- **Prisma Schema**: `/Volumes/code/litellm/deploy/schema.prisma`
- **Supabase Integration** (reference): `/Volumes/code/litellm/litellm/integrations/supabase.py`

### B. Related Documents

- **Investigation Report**: `/Users/cezary/litellm/litellm_investigation_report.md`
- **Code References**: `/Users/cezary/litellm/litellm_code_references.md`
- **Queue Architecture** (future): `docs/architecture/QUEUE_BASED_PERSISTENCE.md` (TBD)

### C. Database Schema Diagram

```mermaid
classDiagram
    class PROXY {
        +Global Scope
    }
    class ORGANIZATION {
        +org_id
        +spend
    }
    class TEAM {
        +team_id
        +spend
    }
    class USER {
        +user_id
        +spend
    }
    class END_USER {
        +end_user_id
        +spend
    }
    class API_KEY {
        +token
        +spend
    }
    class TAG {
        +tag_name
        +spend
    }

    PROXY *-- ORGANIZATION
    ORGANIZATION *-- TEAM
    TEAM *-- USER
    TEAM *-- API_KEY
    USER *-- END_USER
    TAG .. TEAM : Orthogonal
    TAG .. USER : Orthogonal
```

---

**End of Design Document**

**Next Steps**: Proceed to implementation (Phase 1)

**Questions?** Refer to:
- Investigation Report: `litellm_investigation_report.md`
- LiteLLM Docs: https://docs.litellm.ai
- Prisma Docs: https://prisma.io/docs
