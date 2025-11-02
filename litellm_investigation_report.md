# LiteLLM Database Persistence Investigation Report

## 1. How the Proxy Writes Spend Logs to Database (DBSpendUpdateWriter)

### Queue Pattern Architecture
**File**: `/Volumes/code/litellm/litellm/proxy/db/db_spend_update_writer.py` (Lines 49-1394)

The DBSpendUpdateWriter implements a **two-tier queue pattern with optional Redis buffer**:

#### Queue Components:
1. **In-Memory Queues** (always active):
   - `SpendUpdateQueue` (Line 64): Handles individual entity spend updates (key, user, team, etc.)
   - `DailySpendUpdateQueue` (Line 65-67): Aggregates daily spend per entity

2. **Redis Buffer** (optional, for high-throughput):
   - `RedisUpdateBuffer` (Line 62): When enabled via `general_settings["use_redis_transaction_buffer"]`
   - Stores in-memory queues to Redis to minimize database locks
   - Uses `PodLockManager` to ensure only one instance commits to DB

#### Spend Update Flow:
```
LLM Completion Response
    ↓
update_database() (Line 69-195)
    ├─→ _update_key_db() (Line 197-218)
    ├─→ _update_user_db() (Line 220-267)
    ├─→ _update_team_db() (Line 269-309)
    ├─→ _update_org_db() (Line 311-335)
    ├─→ _update_tag_db() (Line 337-383)
    └─→ Each calls: SpendUpdateQueue.add_update()
                      ↓
            db_update_spend_transaction_handler() (Line 407-442)
                ├─→ WITH Redis Buffer: _commit_spend_updates_to_db_with_redis()
                │   ├─ Store queues to Redis
                │   ├─ Pod acquires lock (PodLockManager)
                │   └─ Pull from Redis and commit to DB
                │
                └─→ WITHOUT Redis Buffer: _commit_spend_updates_to_db_without_redis_buffer()
                    └─ Direct aggregation and commit (for lower RPS)
```

#### Key Implementation Details:

**Lines 620-641**: Batch Updates with Retry Logic
```python
async with prisma_client.db.tx(timeout=timedelta(seconds=60)) as transaction:
    async with transaction.batch_() as batcher:
        for user_id, response_cost in user_list_transactions.items():
            batcher.litellm_usertable.update_many(
                where={"user_id": user_id},
                data={"spend": {"increment": response_cost}},
            )
```

**Lines 728-730**: Entity-Level Spend Updates
```python
batcher.litellm_teamtable.update_many(
    where={"team_id": team_id},
    data={"spend": {"increment": response_cost}},
)
```

**Lines 1014-1113**: Daily Spend Upsert Pattern
```python
table.upsert(
    where={unique_constraint_name: {...}},
    data={
        "create": common_data,
        "update": update_data,
    },
)
```

#### Supported Entities Updated (Lines 606-852):
- **Users**: `litellm_usertable`
- **End Users**: `litellm_endusertable`
- **API Keys**: `litellm_verificationtoken`
- **Teams**: `litellm_teamtable`
- **Team Members**: `litellm_teammembership`
- **Organizations**: `litellm_organizationtable`
- **Tags**: `litellm_tagtable`
- **Daily User Spend**: `litellm_dailyuserspend` (unique constraint on user_id, date, api_key, model, custom_llm_provider)
- **Daily Team Spend**: `litellm_dailyteamspend`
- **Daily Tag Spend**: `litellm_dailytagspend`

#### Redis Buffer Configuration:
**File**: `/Volumes/code/litellm/litellm/proxy/db/db_transaction_queue/redis_update_buffer.py` (Lines 54-71)

```python
@staticmethod
def _should_commit_spend_updates_to_redis() -> bool:
    from litellm.proxy.proxy_server import general_settings
    
    _use_redis_transaction_buffer: Optional[Union[bool, str]] = (
        general_settings.get("use_redis_transaction_buffer", False)
    )
    if isinstance(_use_redis_transaction_buffer, str):
        _use_redis_transaction_buffer = str_to_bool(_use_redis_transaction_buffer)
    if _use_redis_transaction_buffer is None:
        return False
    return _use_redis_transaction_buffer
```

**Benefits** (Lines 424-442):
- Check `general_settings.use_redis_transaction_buffer`
- If enabled, write in-memory transactions to Redis first
- Only one Pod reads from Redis and commits to DB (lock-based)
- Solves deadlock issues at 1K+ RPS

---

## 2. SDK Database Persistence Examples

### Supabase Integration (Direct Database Write)
**File**: `/Volumes/code/litellm/litellm/integrations/supabase.py`

This is a **callback-based integration** that writes directly to a Supabase database:

```python
class Supabase:
    def __init__(self):
        self.supabase_url = os.getenv("SUPABASE_URL")
        self.supabase_key = os.getenv("SUPABASE_KEY")
        self.supabase_client = supabase.create_client(self.supabase_url, self.supabase_key)
    
    def log_event(self, model, messages, end_user, response_obj, start_time, end_time, ...):
        # Line 78-95: Upsert on success
        data, count = (
            self.supabase_client.table(self.supabase_table_name)
            .upsert(supabase_data_obj, on_conflict="litellm_call_id")
            .execute()
        )
        
        # Line 112-116: Upsert on failure
        data, count = (
            self.supabase_client.table(self.supabase_table_name)
            .upsert(supabase_data_obj, on_conflict="litellm_call_id")
            .execute()
        )
```

**Usage Pattern** (Test File: `/Volumes/code/litellm/tests/local_testing/test_supabase_integration.py`):
```python
litellm.input_callback = ["supabase"]
litellm.success_callback = ["supabase"]
litellm.failure_callback = ["supabase"]

response = completion(
    model="gpt-3.5-turbo",
    messages=[{"role": "user", "content": "Hello"}],
    user="ishaanRegular",
)
```

### DynamoDB Integration (Another Direct Database Write)
**File**: `/Volumes/code/litellm/litellm/integrations/dynamodb.py` (Lines 33-89)

```python
class DyanmoDBLogger:
    def __init__(self):
        self.dynamodb = boto3.resource("dynamodb", region_name=os.environ["AWS_REGION_NAME"])
        self.table_name = litellm.dynamodb_table_name
    
    def log_event(self, kwargs, response_obj, start_time, end_time, print_verbose):
        # Line 77-79: Direct put_item to DynamoDB
        table = self.dynamodb.Table(self.table_name)
        response = table.put_item(Item=payload)
```

**Callback Registration Pattern**:
- Uses `litellm.success_callback`, `litellm.failure_callback`, `litellm.input_callback`
- Callbacks are triggered automatically during completion/embedding calls
- Non-blocking: Wrapped in try-except, passes on failure

---

## 3. Model Loading from Database in Proxy

### Database Model Loading Flow
**File**: `/Volumes/code/litellm/litellm/proxy/proxy_server.py`

#### Initial Router Initialization:
**Lines 2810-2839**: `decrypt_model_list_from_db()` method
```python
def decrypt_model_list_from_db(self, new_models: list) -> list:
    _model_list: list = []
    for m in new_models:
        _litellm_params = m.litellm_params  # Retrieved from DB
        
        # Decrypt sensitive values
        for k, v in _litellm_params.items():
            decrypted_value = decrypt_value_helper(
                value=v, key=k, return_original_value=True
            )
            _litellm_params[k] = decrypted_value
        
        _model_info = self.get_model_info_with_id(model=m)
        _model_list.append(
            Deployment(
                model_name=m.model_name,
                litellm_params=_litellm_params,
                model_info=_model_info,
            ).to_json(exclude_none=True)
        )
    return _model_list
```

#### Router Update from DB:
**Lines 2841-2896**: `_update_llm_router()` method

When models are added/updated in database:
1. **First Init** (Lines 2849-2863): If router is None, create new router with all DB models
2. **Subsequent Updates** (Lines 2865-2871):
   - Delete removed deployments
   - Add new deployments
3. **Update Model List** (Line 2879):
   ```python
   if llm_router is not None:
       llm_model_list = llm_router.get_model_list()
   ```

#### Config-Based Loading:
**Lines 2443-2459**: Load from YAML/Config
```python
model_list = config.get("model_list", None)
if model_list:
    router_params["model_list"] = model_list
    for model in model_list:
        # Load from environment variables
        for k, v in model["litellm_params"].items():
            if isinstance(v, str) and v.startswith("os.environ/"):
                model["litellm_params"][k] = get_secret(v)
```

#### Database Schema for Models:
**File**: `/Volumes/code/litellm/schema.prisma` (Lines 46-55)

```prisma
model LiteLLM_ProxyModelTable {
  model_id String @id @default(uuid())
  model_name String 
  litellm_params Json          // Contains API keys, base URLs, etc.
  model_info Json?             // Pricing, context window, etc.
  created_at DateTime @default(now())
  created_by String
  updated_at DateTime @default(now()) @updatedAt
  updated_by String
}
```

---

## 4. Database Initialization and Connection Management

### PrismaClient Initialization
**File**: `/Volumes/code/litellm/litellm/proxy/utils.py` (Lines 1664-1710)

```python
class PrismaClient:
    spend_log_transactions: List = []
    
    def __init__(
        self,
        database_url: str,
        proxy_logging_obj: ProxyLogging,
        http_client: Optional[Any] = None,
    ):
        from prisma import Prisma
        
        # Line 1692-1709: Create wrapper around Prisma
        if http_client is not None:
            self.db = PrismaWrapper(
                original_prisma=Prisma(http=http_client),
                iam_token_db_auth=self.iam_token_db_auth,
            )
        else:
            self.db = PrismaWrapper(
                original_prisma=Prisma(),
                iam_token_db_auth=self.iam_token_db_auth,
            )
```

### Configuration Options
**File**: `/Volumes/code/litellm/litellm/proxy/_types.py` (Lines 1711-1823)

```python
class ConfigGeneralSettings(LiteLLMPydanticObjectBase):
    # Database Connection Settings
    database_url: Optional[str] = Field(
        None,
        description="connect to a postgres db - needed for generating temporary keys + tracking spend / key",
    )
    
    database_connection_pool_limit: Optional[int] = Field(
        100,
        description="default connection pool for prisma client connecting to postgres db",
    )
    
    database_connection_timeout: Optional[float] = Field(
        60, description="default timeout for a connection to the database"
    )
    
    database_type: Optional[Literal["dynamo_db"]] = Field(
        None, description="to use dynamodb instead of postgres db"
    )
    
    database_args: Optional[DynamoDBArgs] = Field(
        None,
        description="custom args for instantiating dynamodb client - e.g. billing provision",
    )
    
    # Fine-grained DB control
    supported_db_objects: Optional[List[SupportedDBObjectType]] = Field(
        None,
        description="Fine-grained control over which object types to load from the database...",
    )
```

### Supported DB Object Types
**File**: `/Volumes/code/litellm/litellm/proxy/_types.py` (Lines 55-71)

```python
class SupportedDBObjectType(str, enum.Enum):
    MODELS = "models"
    MCP = "mcp"
    GUARDRAILS = "guardrails"
    VECTOR_STORES = "vector_stores"
    PASS_THROUGH_ENDPOINTS = "pass_through_endpoints"
    PROMPTS = "prompts"
    MODEL_COST_MAP = "model_cost_map"
```

### IAM Token Auth Support
**Line 1675-1677** in utils.py:
```python
self.iam_token_db_auth: Optional[bool] = str_to_bool(
    os.getenv("IAM_TOKEN_DB_AUTH")
)
```

---

## 5. Multi-Instance and Read-Only Configuration Options

### Redis Transaction Buffer (Multi-Instance Support)
**Enables**: Horizontal scaling with multiple proxy instances

Configuration:
```yaml
general_settings:
  use_redis_transaction_buffer: true  # Enable for multi-instance mode
```

**Benefits** (From db_spend_update_writer.py, Lines 424-442):
- All pods write in-memory transactions to Redis
- Only 1 pod (with lock) reads from Redis and commits to DB
- Reduces database contention and deadlocks

### Pod Lock Manager
**File**: `/Volumes/code/litellm/litellm/proxy/db/db_transaction_queue/pod_lock_manager.py`

Implements distributed lock using Redis:
```python
if await self.pod_lock_manager.acquire_lock(
    cronjob_id=DB_SPEND_UPDATE_JOB_NAME,
):
    # Only this pod commits to DB
    await self._commit_spend_updates_to_db(...)
finally:
    await self.pod_lock_manager.release_lock(...)
```

### Supported DB Object Types (Fine-Grained Control)
**Allows**: Selective loading from database

```python
supported_db_objects: Optional[List[SupportedDBObjectType]] = Field(
    None,
    description="Fine-grained control over which object types to load from the database when store_model_in_db is True. Available types: 'models', 'mcp', 'guardrails', 'vector_stores', 'pass_through_endpoints', 'prompts', 'model_cost_map'. If not set, all objects are loaded (default behavior).",
)
```

### Potential Read-Only Mode Indicators
While explicit "read-only" mode isn't implemented, the architecture supports:

1. **Multiple Databases**: DynamoDB support suggests potential for read replicas
   ```python
   database_type: Optional[Literal["dynamo_db"]]
   ```

2. **Cold Storage for Spend Logs**:
   **File**: `/Volumes/code/litellm/litellm/proxy/spend_tracking/cold_storage_handler.py`
   - Separate cold storage for archival spend logs
   - Suggests multi-tier storage pattern

3. **Configuration Overrides**:
   **File**: `/Volumes/code/litellm/litellm/constants.py`
   ```python
   LITELLM_SETTINGS_SAFE_DB_OVERRIDES  # Whitelist of overridable settings
   ```

---

## Key Patterns for SDK Database Persistence Implementation

### 1. Callback Pattern (Current SDK Model)
- Use `litellm.success_callback`, `litellm.failure_callback`, `litellm.input_callback`
- Non-blocking async execution
- Exception-safe (try-except, pass)
- Fires after completion/embedding calls

### 2. Spend Logging Payload Structure
**From**: `/Volumes/code/litellm/litellm/proxy/spend_tracking/spend_tracking_utils.py`

Key fields available:
```python
SpendLogsPayload:
    - user
    - model
    - api_key
    - startTime
    - endTime
    - prompt_tokens
    - completion_tokens
    - spend
    - metadata (SpendLogsMetadata)
    - request_id
    - request_tags
    - team_id
    - custom_llm_provider
    - model_group
```

### 3. Transactional Updates
- Batch updates with retry logic
- Exponential backoff on connection errors
- Transaction timeout: 60 seconds
- Default retry count + 1

### 4. Database Entity Relationships
- Support for hierarchical spend tracking: Proxy → Org → Team → User → EndUser
- Tag-based spend tracking
- Daily aggregate tables for reporting

