# Multitenant Scalability Guide

## Architecture Overview

The OMEGA Agent now supports multitenant rate limiting with the following components:

1. **Per-Tenant Token Buckets**: Each tenant gets their own rate limit allocation
2. **Per-Model Adaptive Backoff**: Track 429 errors per model and automatically back off
3. **Priority Queue Scheduling**: Urgent requests get processed first
4. **Redis Coordination**: Horizontal scaling across multiple instances (optional)

## Configuration

Set these environment variables:

```bash
# Enable multitenant rate limiting
export OMEGA_ENABLE_MULTITENANT_RATE_LIMITING=true

# Set tenant ID (unique per user/organization)
export OMEGA_TENANT_ID="tenant-123"

# Rate limit per tenant (requests per minute)
export OMEGA_TENANT_RPM_LIMIT=10

# Burst allowance (allow short bursts above limit)
export OMEGA_TENANT_BURST_ALLOWANCE=2

# Optional: Redis for distributed coordination
export OMEGA_REDIS_URL="redis://localhost:6379"
```

## Usage Examples

### 1. Single-Tenant (Default)

```python
from omega_agent.core.config import Config
from omega_agent.core.orchestrator import ModelOrchestrator

config = Config()
orchestrator = ModelOrchestrator(config)  # Uses default tenant

result = await orchestrator.invoke("Build a CRM app")
```

### 2. Per-Tenant Isolation

```python
from omega_agent.core.config import Config
from omega_agent.core.orchestrator import ModelOrchestrator

# Create orchestrator for specific tenant
config = Config(tenant_id="customer-A")
orchestrator_a = ModelOrchestrator(config, tenant_id="customer-A")

# Different tenant gets separate rate limit
config_b = Config(tenant_id="customer-B")
orchestrator_b = ModelOrchestrator(config_b, tenant_id="customer-B")

# These won't interfere with each other's rate limits
result_a = await orchestrator_a.invoke("Task for customer A")
result_b = await orchestrator_b.invoke("Task for customer B")
```

### 3. Priority-Based Requests

```python
from omega_agent.core.rate_limiter import RequestPriority

# Critical user-facing request
result = await orchestrator.invoke(
    "Urgent task",
    priority=RequestPriority.CRITICAL
)

# Background batch processing
result = await orchestrator.invoke(
    "Batch analysis",
    priority=RequestPriority.LOW
)
```

### 4. Startup Initialization

```python
from omega_agent.core.rate_limiter import init_rate_limiter
from omega_agent.core.config import Config

async def startup():
    config = Config()
    
    # Initialize rate limiter with Redis for horizontal scaling
    rate_limiter = await init_rate_limiter(
        enable_redis=bool(config.redis_url),
        redis_url=config.redis_url
    )
    
    # Rate limiter will automatically be used by orchestrators
    print("Rate limiter initialized for multitenant scalability")
```

## Scalability Patterns

### Vertical Scaling (Single Instance)

- **Capacity**: Handles 100+ concurrent tenants with 10 RPM each
- **Rate Limiting**: In-memory token buckets per tenant
- **Best For**: Single-server deployments, development, testing

### Horizontal Scaling (Multiple Instances)

- **Capacity**: Unlimited (add more instances)
- **Rate Limiting**: Redis-backed coordination
- **Best For**: Production, high-traffic deployments

```bash
# Instance 1
export OMEGA_REDIS_URL="redis://redis-cluster:6379"
export OMEGA_TENANT_ID="instance-1"
python -m omega_agent.api

# Instance 2
export OMEGA_REDIS_URL="redis://redis-cluster:6379"
export OMEGA_TENANT_ID="instance-2"
python -m omega_agent.api
```

### Tenant Tiering

Configure different rate limits per tenant tier:

```python
from omega_agent.core.config import Config

# Free tier: 5 RPM
config_free = Config(tenant_id="free-user", tenant_rpm_limit=5)

# Pro tier: 50 RPM
config_pro = Config(tenant_id="pro-user", tenant_rpm_limit=50)

# Enterprise tier: 500 RPM
config_enterprise = Config(tenant_id="enterprise", tenant_rpm_limit=500)
```

## Monitoring

### Get Tenant Statistics

```python
from omega_agent.core.rate_limiter import get_rate_limiter

rate_limiter = get_rate_limiter()
stats = rate_limiter.get_tenant_stats("tenant-123")
print(f"Tokens remaining: {stats['tokens_remaining']}")
print(f"RPM limit: {stats['rpm_limit']}")
```

### Get Model Statistics

```python
stats = rate_limiter.get_model_stats("openai/gpt-oss-120b:free")
print(f"Success rate: {stats['success_rate']:.2%}")
print(f"Available: {stats['is_available']}")
```

## Adaptive Backoff

The system automatically learns from 429 errors:

1. **First 429**: Back off for 2 seconds
2. **Second 429**: Back off for 4 seconds
3. **Third 429**: Back off for 8 seconds
4. **Fourth+ 429**: Back off for 60 seconds (max)

Models with high success rates are prioritized over models with frequent 429s.

## Queue Behavior

When rate limits are hit:

1. Request is queued with priority
2. Background processor checks queue every 100ms
3. Highest priority, oldest requests processed first
4. Queue automatically drains when capacity available

## Migration from Simple Semaphore

The new system is backward compatible:

- If rate limiter fails to load, falls back to simple semaphore (max 2 concurrent)
- Existing code continues to work without changes
- Gradual migration: enable rate limiting per tenant

## Production Checklist

- [ ] Set `OMEGA_ENABLE_MULTITENANT_RATE_LIMITING=true`
- [ ] Configure unique `OMEGA_TENANT_ID` per deployment
- [ ] Set appropriate `OMEGA_TENANT_RPM_LIMIT` based on capacity
- [ ] Add Redis for horizontal scaling (multi-instance deployments)
- [ ] Monitor queue depth and tenant statistics
- [ ] Set up alerts for high backoff rates
- [ ] Configure different RPM limits per tenant tier
