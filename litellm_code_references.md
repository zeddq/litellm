# LiteLLM Database Persistence - Code Reference Guide

## File Structure Summary

### Proxy Database Layer
```
litellm/proxy/db/
├── db_spend_update_writer.py          # Main spend logging orchestrator (1394 lines)
│   ├── DBSpendUpdateWriter class      # Queue pattern implementation
│   ├── Entity-specific update methods
│   └── Batch transaction handlers
├── db_transaction_queue/
│   ├── spend_update_queue.py          # In-memory queue for incremental updates
│   ├── daily_spend_update_queue.py    # Daily aggregate queue
│   ├── redis_update_buffer.py         # Optional Redis buffer layer
│   └── pod_lock_manager.py            # Distributed locking for multi-instance
└── utils/
    └── PrismaClient wrapper classes
```

### Integration Layer
```
litellm/integrations/
├── supabase.py                        # Direct Supabase writes (callback-based)
├── dynamodb.py                        # Direct DynamoDB writes (callback-based)
├── custom_logger.py                   # Base logger interface
└── [60+ other integrations]
```

### Proxy Server
```
litellm/proxy/
├── proxy_server.py                    # Main FastAPI app (4000+ lines)
│   ├── ProxyServerConfig class        # Initialization and config loading
│   ├── Model loading from DB
│   └── Router management
├── _types.py                          # Type definitions (2000+ lines)
│   ├── ConfigGeneralSettings          # Configuration schema
│   ├── SupportedDBObjectType enum     # Fine-grained DB control
│   └── Spend log types
├── utils.py                           # Utilities
│   └── PrismaClient class             # Database connection wrapper
└── spend_tracking/
    ├── spend_tracking_utils.py        # Spend log payload construction
    ├── spend_management_endpoints.py  # API endpoints
    └── cold_storage_handler.py        # Archival storage
```

---

## Critical Code Snippets

### 1. Spend Update Initialization
**Source**: `/Volumes/code/litellm/litellm/proxy/db/db_spend_update_writer.py:69-195`

```python
async def update_database(
    self,
    token: Optional[str],
    user_id: Optional[str],
    end_user_id: Optional[str],
    team_id: Optional[str],
    org_id: Optional[str],
    kwargs: Optional[dict],
    completion_response: Optional[Union[litellm.ModelResponse, Any, Exception]],
    start_time: Optional[datetime],
    end_time: Optional[datetime],
    response_cost: Optional[float],
):
    # Creates 5 async tasks for updating different entities
    asyncio.create_task(
        self._update_user_db(
            response_cost=response_cost,
            user_id=user_id,
            prisma_client=prisma_client,
            user_api_key_cache=user_api_key_cache,
            litellm_proxy_budget_name=litellm_proxy_budget_name,
            end_user_id=end_user_id,
        )
    )
    # ... more async tasks
```

### 2. Redis Buffer Pattern
**Source**: `/Volumes/code/litellm/litellm/proxy/db/db_spend_update_writer.py:444-520`

```python
async def _commit_spend_updates_to_db_with_redis(
    self,
    prisma_client: PrismaClient,
    n_retry_times: int,
    proxy_logging_obj: ProxyLogging,
):
    # Step 1: Buffer in-memory updates to Redis
    await self.redis_update_buffer.store_in_memory_spend_updates_in_redis(
        spend_update_queue=self.spend_update_queue,
        daily_spend_update_queue=self.daily_spend_update_queue,
        daily_team_spend_update_queue=self.daily_team_spend_update_queue,
        daily_tag_spend_update_queue=self.daily_tag_spend_update_queue,
    )

    # Step 2: Try to acquire distributed lock
    if await self.pod_lock_manager.acquire_lock(
        cronjob_id=DB_SPEND_UPDATE_JOB_NAME,
    ):
        # Step 3: Only lock holder fetches and commits
        db_spend_update_transactions = (
            await self.redis_update_buffer.get_all_update_transactions_from_redis_buffer()
        )
        await self._commit_spend_updates_to_db(...)
```

### 3. Supabase Callback Implementation
**Source**: `/Volumes/code/litellm/litellm/integrations/supabase.py:34-121`

```python
class Supabase:
    supabase_table_name = "request_logs"
    
    def __init__(self):
        self.supabase_url = os.getenv("SUPABASE_URL")
        self.supabase_key = os.getenv("SUPABASE_KEY")
        self.supabase_client = supabase.create_client(
            self.supabase_url, self.supabase_key
        )
    
    def log_event(self, model, messages, end_user, response_obj, 
                  start_time, end_time, litellm_call_id, print_verbose):
        try:
            total_cost = litellm.completion_cost(completion_response=response_obj)
            response_time = (end_time - start_time).total_seconds()
            
            supabase_data_obj = {
                "response_time": response_time,
                "model": response_obj["model"],
                "total_cost": total_cost,
                "messages": messages,
                "response": response_obj["choices"][0]["message"]["content"],
                "end_user": end_user,
                "litellm_call_id": litellm_call_id,
                "status": "success",
            }
            
            # Upsert with conflict resolution
            data, count = (
                self.supabase_client.table(self.supabase_table_name)
                .upsert(supabase_data_obj, on_conflict="litellm_call_id")
                .execute()
            )
        except Exception:
            print_verbose(f"Supabase Logging Error - {traceback.format_exc()}")
            pass
```

### 4. Model Loading from Database
**Source**: `/Volumes/code/litellm/litellm/proxy/proxy_server.py:2810-2896`

```python
def decrypt_model_list_from_db(self, new_models: list) -> list:
    _model_list: list = []
    for m in new_models:
        _litellm_params = m.litellm_params
        
        # Decrypt sensitive API credentials
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

async def _update_llm_router(
    self,
    new_models: list,
    proxy_logging_obj: ProxyLogging,
):
    global llm_router, llm_model_list, master_key, general_settings
    
    try:
        if llm_router is None and master_key is not None:
            _model_list: list = self.decrypt_model_list_from_db(
                new_models=new_models
            )
            if len(_model_list) > 0:
                llm_router = litellm.Router(
                    model_list=_model_list,
                    router_general_settings=RouterGeneralSettings(
                        async_only_mode=True
                    ),
                    ignore_invalid_deployments=True,
                )
```

### 5. PrismaClient Database Connection
**Source**: `/Volumes/code/litellm/litellm/proxy/utils.py:1664-1710`

```python
class PrismaClient:
    spend_log_transactions: List = []
    
    def __init__(
        self,
        database_url: str,
        proxy_logging_obj: ProxyLogging,
        http_client: Optional[Any] = None,
    ):
        self.proxy_logging_obj = proxy_logging_obj
        self.iam_token_db_auth: Optional[bool] = str_to_bool(
            os.getenv("IAM_TOKEN_DB_AUTH")
        )
        
        from prisma import Prisma
        
        if http_client is not None:
            self.db = PrismaWrapper(
                original_prisma=Prisma(http=http_client),
                iam_token_db_auth=(
                    self.iam_token_db_auth
                    if self.iam_token_db_auth is not None
                    else False
                ),
            )
        else:
            self.db = PrismaWrapper(
                original_prisma=Prisma(),
                iam_token_db_auth=(
                    self.iam_token_db_auth
                    if self.iam_token_db_auth is not None
                    else False
                ),
            )
```

### 6. Batch Transaction Pattern
**Source**: `/Volumes/code/litellm/litellm/proxy/db/db_spend_update_writer.py:620-641`

```python
# UPDATE USER TABLE
user_list_transactions = db_spend_update_transactions["user_list_transactions"]

if (
    user_list_transactions is not None
    and len(user_list_transactions.keys()) > 0
):
    for i in range(n_retry_times + 1):
        start_time = time.time()
        try:
            async with prisma_client.db.tx(
                timeout=timedelta(seconds=60)
            ) as transaction:
                async with transaction.batch_() as batcher:
                    for (
                        user_id,
                        response_cost,
                    ) in user_list_transactions.items():
                        batcher.litellm_usertable.update_many(
                            where={"user_id": user_id},
                            data={"spend": {"increment": response_cost}},
                        )
            break
        except DB_CONNECTION_ERROR_TYPES as e:
            if (
                i >= n_retry_times
            ):  # If we've reached the maximum number of retries
                _raise_failed_update_spend_exception(
                    e=e,
                    start_time=start_time,
                    proxy_logging_obj=proxy_logging_obj,
                )
            # Optionally, sleep for a bit before retrying
            await asyncio.sleep(2**i)  # Exponential backoff
```

### 7. Daily Spend Upsert Pattern
**Source**: `/Volumes/code/litellm/litellm/proxy/db/db_spend_update_writer.py:1014-1113`

```python
async with prisma_client.db.batch_() as batcher:
    for _, transaction in transactions_to_process.items():
        entity_id = transaction.get(entity_id_field)
        
        # Construct unique constraint key
        where_clause = {
            unique_constraint_name: {
                entity_id_field: entity_id,
                "date": transaction["date"],
                "api_key": transaction["api_key"],
                "model": transaction["model"],
                "custom_llm_provider": transaction.get(
                    "custom_llm_provider"
                ) or "",
                "mcp_namespaced_tool_name": transaction.get(
                    "mcp_namespaced_tool_name"
                ) or "",
            }
        }
        
        # Get the table dynamically
        table = getattr(batcher, table_name)
        
        # Common data structure for both create and update
        common_data = {
            entity_id_field: entity_id,
            "date": transaction["date"],
            "api_key": transaction["api_key"],
            "model": transaction.get("model"),
            "prompt_tokens": transaction["prompt_tokens"],
            "completion_tokens": transaction["completion_tokens"],
            "spend": transaction["spend"],
            "api_requests": transaction["api_requests"],
            "successful_requests": transaction["successful_requests"],
            "failed_requests": transaction["failed_requests"],
        }
        
        # Create update data structure
        update_data = {
            "prompt_tokens": {"increment": transaction["prompt_tokens"]},
            "completion_tokens": {"increment": transaction["completion_tokens"]},
            "spend": {"increment": transaction["spend"]},
            "api_requests": {"increment": transaction["api_requests"]},
            "successful_requests": {"increment": transaction["successful_requests"]},
            "failed_requests": {"increment": transaction["failed_requests"]},
        }
        
        table.upsert(
            where=where_clause,
            data={
                "create": common_data,
                "update": update_data,
            },
        )
```

### 8. Configuration Loading
**Source**: `/Volumes/code/litellm/litellm/proxy/_types.py:1711-1823`

```python
class ConfigGeneralSettings(LiteLLMPydanticObjectBase):
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
        description="custom args for instantiating dynamodb client",
    )
    supported_db_objects: Optional[List[SupportedDBObjectType]] = Field(
        None,
        description="Fine-grained control over which object types to load from the database when store_model_in_db is True. Available types: 'models', 'mcp', 'guardrails', 'vector_stores', 'pass_through_endpoints', 'prompts', 'model_cost_map'. If not set, all objects are loaded (default behavior).",
    )
```

---

## Entity Types and Database Tables

### Supported Entities (from _types.py)
```python
class Litellm_EntityType(enum.Enum):
    KEY = "key"                  # API keys
    USER = "user"                # Individual users
    END_USER = "end_user"        # End users of API users
    TEAM = "team"                # Team groups
    TEAM_MEMBER = "team_member"  # Users within teams
    ORGANIZATION = "organization" # Org-level entities
    TAG = "tag"                  # Custom tags
    PROXY = "proxy"              # Global proxy level
```

### Database Tables Updated by Proxy (from schema.prisma)
```
LiteLLM_VerificationToken          (API keys)
LiteLLM_UserTable                  (Users)
LiteLLM_EndUserTable               (End users)
LiteLLM_TeamTable                  (Teams)
LiteLLM_TeamMembership             (Team users)
LiteLLM_OrganizationTable          (Organizations)
LiteLLM_TagTable                   (Tags)
LiteLLM_DailyUserSpend             (Daily aggregates)
LiteLLM_DailyTeamSpend             (Team daily aggregates)
LiteLLM_DailyTagSpend              (Tag daily aggregates)
LiteLLM_ProxyModelTable            (Models on proxy)
```

---

## Environment Variables and Configuration

### Database Configuration
```bash
DATABASE_URL              # PostgreSQL connection string
DATABASE_TYPE            # Optional: "dynamo_db"
IAM_TOKEN_DB_AUTH        # Use IAM tokens for DB auth
```

### Spend Log Configuration
```bash
SPEND_LOGS_URL           # Optional URL for spend logs endpoint
DISABLE_SPEND_LOGS       # Set to true to skip spend log writes
```

### Redis Configuration
```bash
# In config.yaml:
general_settings:
  use_redis_transaction_buffer: true  # Enable multi-instance mode
```

---

## Testing and Integration Examples

### SDK Integration Test
**File**: `/Volumes/code/litellm/tests/local_testing/test_supabase_integration.py`

```python
# Enable callbacks
litellm.input_callback = ["supabase"]
litellm.success_callback = ["supabase"]
litellm.failure_callback = ["supabase"]

# Make completion call
response = completion(
    model="gpt-3.5-turbo",
    messages=[{"role": "user", "content": "Hello tell me hi"}],
    user="ishaanRegular",
    max_tokens=10,
)
```

### Async Integration Test
```python
async def completion_call():
    response = await litellm.acompletion(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": "write a poem"}],
        max_tokens=10,
        stream=True,
        user="ishaanStreamingUser",
        timeout=5,
    )
    async for chunk in response:
        # Process streaming response
        pass
```

