# Queue-Based Persistence Architecture (Option 3 - Future Reference)

**Status**: Future Enhancement  
**Priority**: Low (implement only if Option 1 becomes bottleneck)  
**Version**: 1.0  
**Last Updated**: 2025-11-02  

---

## Purpose

This document provides a high-level architecture for a queue-based persistence system (Option 3) as a future enhancement to the current Prisma callback implementation (Option 1).

**⚠️ Important**: This is a reference document for future consideration. **Do not implement unless:**
- Option 1 becomes a performance bottleneck (>100 RPS per instance)
- Multi-instance deployment at scale is required
- Complex event processing pipelines are needed

---

## When to Consider Migration

| Metric | Option 1 (Prisma Callback) | Migrate to Option 3? |
|--------|----------------------------|----------------------|
| RPS < 100 | ✅ Sufficient | ❌ Stay with Option 1 |
| Single instance | ✅ Works well | ❌ Unnecessary complexity |
| Write latency < 50ms | ✅ Good enough | ❌ No migration needed |
| **RPS > 500** | ⚠️ May struggle | ✅ Consider migration |
| **Multi-instance (>5)** | ⚠️ Lock contention | ✅ Queue scales better |
| **Complex analytics** | ⚠️ Limited | ✅ Multiple consumers |

---

## High-Level Architecture

```
SDK Instances                 Queue Layer              Consumer Layer            Database
─────────────                 ───────────              ──────────────            ────────

┌──────────┐                                          ┌──────────────┐
│ SDK #1   │  Write events                            │  Consumer #1 │
│ Instance │  (~1-5ms)        ┌─────────────────┐    │  (Batch      │
│          ├─────────────────>│                 │    │   Processor) │
└──────────┘                  │  Redis Streams  │    │              │         ┌─────────┐
                              │  or             ├───>│ Reads batches├────────>│ Postgres│
┌──────────┐                  │  Apache Kafka   │    │ Commits to DB│         │ Database│
│ SDK #2   │  Write events    │                 │    │              │         └─────────┘
│ Instance │  (~1-5ms)        │  (Message Queue)│    └──────────────┘
│          ├─────────────────>│                 │
└──────────┘                  │  - Partitioned  │    ┌──────────────┐
                              │  - Replicated   │    │  Consumer #2 │
┌──────────┐                  │  - Durable      │    │  (Analytics  │
│ SDK #N   │  Write events    │  - Ordered      │───>│   Pipeline)  │
│ Instance │  (~1-5ms)        │                 │    │              │
│          ├─────────────────>│                 │    └──────────────┘
└──────────┘                  └─────────────────┘
                                                       ┌──────────────┐
                                                       │  Consumer #3 │
                                                       │  (Archival   │
                                                       │   to S3)     │
                                                       └──────────────┘
```

---

## Key Components

### 1. Producer (SDK Callback)

Similar to Option 1, but writes to queue instead of database:

```python
class QueueProxyLogger(CustomLogger):
    async def async_log_success_event(self, kwargs, response_obj, start_time, end_time):
        # Serialize event to JSON
        event = {
            "user_id": kwargs.get("user"),
            "team_id": kwargs.get("metadata", {}).get("team_id"),
            "response_cost": litellm.completion_cost(response_obj),
            "timestamp": datetime.now().isoformat(),
            # ... more fields
        }
        
        # Write to queue (1-5ms)
        await self.queue_client.publish(
            topic="litellm-completions",
            message=json.dumps(event),
            partition_key=event["user_id"]  # Partition by user for ordering
        )
```

**Performance**: ~1-5ms per write (vs 10-50ms for Option 1 batch commit)

### 2. Queue (Redis Streams or Kafka)

**Option A: Redis Streams** (Recommended for <10K RPS)
```python
# Producer
await redis.xadd("litellm:completions", {"event": json.dumps(event)})

# Consumer
messages = await redis.xread({"litellm:completions": last_id}, count=100)
```

**Pros:**
- Simple setup
- Low latency (<1ms)
- Good for moderate scale

**Cons:**
- Limited durability
- No multi-datacenter replication

---

**Option B: Apache Kafka** (For >10K RPS, enterprise scale)
```python
# Producer
await kafka_producer.send("litellm-completions", value=event)

# Consumer
async for message in kafka_consumer:
    process_batch([message])
```

**Pros:**
- Highly durable
- Excellent horizontal scaling
- Multi-datacenter replication
- Multiple consumer groups

**Cons:**
- Complex operations
- Higher infrastructure cost

---

### 3. Consumer (Batch Processor)

Reads from queue in batches, commits to database:

```python
class CompletionEventConsumer:
    async def run(self):
        while True:
            # Read batch from queue
            events = await self.queue.read_batch(size=100, timeout=10)
            
            # Process batch
            await self.process_batch(events)
    
    async def process_batch(self, events: List[dict]):
        # Group by entity type
        user_updates = {}
        team_updates = {}
        
        for event in events:
            user_id = event["user_id"]
            cost = event["response_cost"]
            user_updates[user_id] = user_updates.get(user_id, 0.0) + cost
        
        # Batch commit to database (reuse DBSpendUpdateWriter logic)
        await self.spend_writer.commit_batch(user_updates, team_updates, ...)
        
        # Acknowledge messages (commit offset)
        await self.queue.acknowledge(events)
```

**Processing Time**: 10-50ms per batch (100 events)  
**Lag Target**: <500ms (end-to-end)

---

## Data Flow & Timing

```
Time   SDK          Queue        Consumer      Database
────   ───          ─────        ────────      ────────
T+0    Write event
       (1-5ms) ────>
       
T+0    ← Ack
       
T+10               Read batch
                   (100 events)
                   ─────────────>
                   
T+20                             Commit batch
                                 (10-50ms) ───>
                                 
T+30                             ← Success
                   
T+30               Ack messages
                   (commit offset)
```

**Total Latency**: ~30-100ms (from SDK write to database commit)  
**User Latency**: +1-5ms (only queue write, rest is async)

---

## Advantages Over Option 1

1. **Lower Write Latency**: 1-5ms (queue) vs 10-50ms (database batch)
2. **Better Horizontal Scaling**: Add more consumers independently
3. **Multiple Consumers**: Same queue → multiple use cases
   - Consumer #1: Database persistence
   - Consumer #2: Real-time analytics
   - Consumer #3: Data lake archival (S3, Snowflake)
4. **Failure Isolation**: Queue failures don't block SDK
5. **Replay Capability**: Reprocess events from queue history

---

## Disadvantages vs Option 1

1. **Eventual Consistency**: 100-500ms lag (vs immediate in Option 1)
2. **Infrastructure Complexity**: Requires queue management (Redis/Kafka)
3. **Operational Overhead**: Monitor queue depth, consumer lag
4. **Cost**: Additional infrastructure (queue cluster, consumers)
5. **Implementation Time**: 2-3 weeks vs 2-3 days for Option 1

---

## Migration Path (Option 1 → Option 3)

### Phase 1: Dual Write (2 weeks)

Enable both Prisma callback and queue callback:

```python
litellm.success_callback = [
    "prisma_proxy",      # Existing (Option 1)
    "queue_proxy",       # New (Option 3)
    "opentelemetry"      # Observability
]
```

**Validation:**
- Compare database writes from both paths
- Monitor discrepancies
- Alert on inconsistencies

### Phase 2: Validate & Monitor (1-2 weeks)

- Run load tests (1000+ RPS)
- Compare latencies
- Verify data consistency
- Monitor queue lag

### Phase 3: Cut Over (1 week)

Once validated:
```python
litellm.success_callback = [
    "queue_proxy",       # Primary (Option 3)
    # "prisma_proxy" disabled
    "opentelemetry"
]
```

**Rollback Plan**: Re-enable `prisma_proxy` if issues arise

---

## Technology Choices

### Queue Technology

| Technology | Best For | RPS Capacity | Complexity | Cost |
|------------|----------|--------------|------------|------|
| **Redis Streams** | <10K RPS, single datacenter | ~10K | Low | Low |
| **Apache Kafka** | >10K RPS, multi-datacenter | ~100K+ | High | High |
| AWS Kinesis | AWS-native deployments | ~10K | Medium | Medium |
| GCP Pub/Sub | GCP-native deployments | ~100K | Medium | Medium |

**Recommendation**: Start with **Redis Streams** (simpler), migrate to Kafka if needed

### Consumer Framework

| Framework | Language | Best For |
|-----------|----------|----------|
| **Faust** | Python | Kafka consumers, stream processing |
| **Celery** | Python | Redis-backed task queues |
| **Dramatiq** | Python | Redis/RabbitMQ task queues |
| Custom | Python | Full control, asyncio-based |

**Recommendation**: Custom asyncio-based consumer (full control, minimal deps)

---

## Performance Targets

| Metric | Target | Notes |
|--------|--------|-------|
| Producer write latency | <5ms | 99th percentile |
| Consumer batch latency | <50ms | Per 100 events |
| End-to-end lag | <500ms | From SDK to database |
| Queue depth | <1000 messages | Alert if exceeded |
| Consumer lag | <10 seconds | Alert if exceeded |
| Throughput | >1000 RPS | Per consumer instance |

---

## Monitoring & Alerting

### Key Metrics

```python
# Producer metrics
queue_writes_total              # Counter
queue_write_latency_ms          # Histogram
queue_write_errors_total        # Counter

# Consumer metrics
consumer_batch_size             # Histogram
consumer_batch_latency_ms       # Histogram
consumer_lag_seconds            # Gauge (CRITICAL)
queue_depth                     # Gauge (CRITICAL)

# Database metrics
db_commit_latency_ms            # Histogram
db_commit_errors_total          # Counter
```

### Alerts

```yaml
# Critical: High consumer lag
- alert: HighConsumerLag
  expr: consumer_lag_seconds > 30
  severity: critical
  
# Warning: Growing queue depth
- alert: GrowingQueueDepth
  expr: queue_depth > 1000
  severity: warning

# Critical: Consumer not processing
- alert: ConsumerStuck
  expr: rate(consumer_batch_size[5m]) == 0
  severity: critical
```

---

## Cost Analysis

### Option 1 (Prisma Callback) - Current

| Resource | Cost/Month | Notes |
|----------|-----------|-------|
| PostgreSQL | $50-200 | Depends on instance size |
| Redis (optional) | $30-100 | For multi-instance coordination |
| **Total** | **$80-300** | Simple deployment |

### Option 3 (Queue-Based) - Future

| Resource | Cost/Month | Notes |
|----------|-----------|-------|
| PostgreSQL | $50-200 | Same as Option 1 |
| Redis Streams | $50-150 | Queue cluster (3 nodes) |
| Consumer instances | $100-300 | 2-5 instances |
| Monitoring | $50-100 | Enhanced observability |
| **Total** | **$250-750** | More infrastructure |

**Cost Increase**: 3-5x higher than Option 1

---

## Decision Matrix

### Stay with Option 1 if:
- [x] RPS < 100
- [x] Single SDK instance or <5 instances
- [x] Budget-conscious
- [x] Simple operations preferred
- [x] Write latency <50ms acceptable

### Migrate to Option 3 if:
- [ ] RPS > 500
- [ ] Multi-instance deployment (>5 instances)
- [ ] Need multiple consumers (analytics, archival)
- [ ] Budget allows 3-5x infrastructure cost
- [ ] Team has queue management expertise

---

## Implementation Checklist (If Migrating)

### Prerequisites
- [ ] Option 1 (Prisma callback) running in production
- [ ] Performance bottleneck identified (>100 RPS)
- [ ] Budget approved (~3-5x infrastructure cost)
- [ ] Team trained on queue operations

### Phase 1: Infrastructure
- [ ] Deploy Redis Streams cluster (3 nodes)
- [ ] Configure replication and persistence
- [ ] Set up monitoring (Grafana, Prometheus)

### Phase 2: Implementation
- [ ] Implement `QueueProxyLogger` (producer)
- [ ] Implement `CompletionEventConsumer` (consumer)
- [ ] Add dual-write capability (both Option 1 and 3)

### Phase 3: Testing
- [ ] Unit tests (producer, consumer)
- [ ] Integration tests (end-to-end)
- [ ] Load tests (1000+ RPS)
- [ ] Chaos testing (consumer failures)

### Phase 4: Deployment
- [ ] Enable dual-write in staging
- [ ] Validate data consistency (2 weeks)
- [ ] Enable dual-write in production
- [ ] Monitor for 1-2 weeks
- [ ] Cut over to Option 3 (disable Option 1)

### Phase 5: Optimization
- [ ] Tune batch sizes
- [ ] Optimize consumer count
- [ ] Set up auto-scaling
- [ ] Implement circuit breakers

---

## Future Enhancements (Post-Migration)

### 1. Stream Processing
Use Faust or custom stream processor for real-time analytics:

```python
import faust

app = faust.App("litellm-analytics")

@app.agent(kafka_topic="litellm-completions")
async def process_completions(stream):
    async for event in stream:
        # Real-time cost tracking
        user_spend[event["user_id"]] += event["cost"]
        
        # Anomaly detection
        if event["cost"] > threshold:
            await alert_service.send(f"High cost: {event}")
```

### 2. Data Lake Integration
Archive to S3/Snowflake for long-term analytics:

```python
@app.agent(kafka_topic="litellm-completions")
async def archive_to_s3(stream):
    batch = []
    async for event in stream:
        batch.append(event)
        if len(batch) >= 1000:
            await s3_client.put_object(
                Bucket="litellm-archives",
                Key=f"completions/{date}/{uuid}.parquet",
                Body=to_parquet(batch)
            )
            batch = []
```

### 3. Multi-Region Deployment
Replicate queue across regions for global deployments

---

## References

- **Option 1 Design**: `docs/architecture/PRISMA_CALLBACK_DESIGN.md`
- **DBSpendUpdateWriter**: `/Volumes/code/litellm/litellm/proxy/db/db_spend_update_writer.py`
- **Redis Streams**: https://redis.io/docs/data-types/streams/
- **Apache Kafka**: https://kafka.apache.org/documentation/
- **Faust**: https://faust.readthedocs.io/

---

## Conclusion

**Option 3 (Queue-Based) is a powerful future enhancement, but NOT needed for most use cases.**

**Current Recommendation**: 
✅ Use Option 1 (Prisma Callback) - simple, cost-effective, sufficient for <100 RPS

**Future Consideration**: 
⏸️ Revisit Option 3 when you hit performance bottlenecks or need complex event processing

---

**Last Updated**: 2025-11-02  
**Next Review**: When RPS exceeds 100 or multi-instance coordination becomes painful
