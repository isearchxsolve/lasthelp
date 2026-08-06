"""
Multitenant rate limiting with token buckets, priority queues, and adaptive backoff.

Supports:
- Per-tenant rate limits (fair allocation across users)
- Per-model rate limit tracking (learn actual limits from 429s)
- Priority queue scheduling (urgent requests first)
- Horizontal scaling via Redis coordination
- Adaptive backoff based on historical 429 patterns
"""

import asyncio
import logging
import os
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Dict, Optional, Set
from enum import Enum, auto

logger = logging.getLogger("omega_agent.rate_limiter")


class RequestPriority(Enum):
    CRITICAL = auto()    # User-facing, blocking
    HIGH = auto()        # Important background tasks
    NORMAL = auto()      # Standard processing
    LOW = auto()         # Batch/non-urgent


@dataclass
class RateLimitConfig:
    """Rate limit configuration per tier."""
    requests_per_minute: int
    tokens_per_minute: int
    burst_allowance: int = 2  # Allow short bursts


# Default rate limits per provider tier
PROVIDER_LIMITS: Dict[str, RateLimitConfig] = {
    "tier1": RateLimitConfig(requests_per_minute=10, tokens_per_minute=200_000, burst_allowance=3),
    "tier2": RateLimitConfig(requests_per_minute=5, tokens_per_minute=50_000, burst_allowance=1),
    "tier3": RateLimitConfig(requests_per_minute=2, tokens_per_minute=10_000, burst_allowance=0),
}


@dataclass
class TenantBucket:
    """Token bucket for a single tenant."""
    tokens: float
    last_update: float
    config: RateLimitConfig
    
    def can_consume(self, tokens: float = 1.0) -> bool:
        """Check if request can be consumed."""
        now = time.time()
        elapsed = now - self.last_update
        
        # Refill tokens based on rate
        refill_rate = self.config.requests_per_minute / 60.0
        self.tokens = min(
            self.config.requests_per_minute + self.config.burst_allowance,
            self.tokens + elapsed * refill_rate
        )
        self.last_update = now
        
        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        return False


@dataclass
class ModelTracker:
    """Track rate limits per model from 429 / 503 responses."""
    success_count: int = 0
    failure_count: int = 0
    failure_503_count: int = 0
    last_error_time: float = 0
    backoff_until: float = 0
    estimated_rpm: Optional[int] = None

    def record_success(self):
        self.success_count += 1
        # Decay failure counts on success so backoff shrinks over time
        self.failure_count = max(0, self.failure_count - 1)
        self.failure_503_count = max(0, self.failure_503_count - 1)

    def record_failure_429(self, delay: Optional[float] = None):
        """Rate-limited: longer exponential backoff (2^n, max 60 s)."""
        self.failure_count += 1
        self.last_error_time = time.time()
        backoff = delay if delay is not None else min(60, 2 ** self.failure_count)
        self.backoff_until = time.time() + backoff

    def record_failure_503(self, delay: Optional[float] = None):
        """Server overload: shorter backoff (5 * 2^n, max 40 s)."""
        self.failure_503_count += 1
        self.last_error_time = time.time()
        backoff = delay if delay is not None else min(40, 5 * (2 ** (self.failure_503_count - 1)))
        # Only extend backoff — never shorten it if already cooling down
        self.backoff_until = max(self.backoff_until, time.time() + backoff)

    # Keep legacy name so existing call-sites don't break
    def record_failure(self, delay: Optional[float] = None):
        self.record_failure_429(delay)

    def is_available(self) -> bool:
        """Check if model is currently available (not in backoff)."""
        return time.time() > self.backoff_until

    def get_success_rate(self) -> float:
        """Calculate recent success rate."""
        total = self.success_count + self.failure_count + self.failure_503_count
        if total == 0:
            return 1.0
        return self.success_count / total


@dataclass
class QueuedRequest:
    """Request waiting in priority queue."""
    future: asyncio.Future
    priority: RequestPriority
    tenant_id: str
    model: str
    timestamp: float = field(default_factory=time.time)
    
    def __lt__(self, other):
        # Higher priority first, then older requests first
        priority_order = {
            RequestPriority.CRITICAL: 0,
            RequestPriority.HIGH: 1,
            RequestPriority.NORMAL: 2,
            RequestPriority.LOW: 3,
        }
        return (priority_order[self.priority], self.timestamp) < \
               (priority_order[other.priority], other.timestamp)


class MultitenantRateLimiter:
    """
    Centralized rate limiter supporting:
    - Per-tenant token buckets
    - Per-model adaptive backoff
    - Priority queue scheduling
    - Redis coordination for horizontal scaling
    """
    
    def __init__(
        self,
        default_tenant_rpm: int = 200,
        default_tenant_burst: int = 50,
        enable_redis: bool = False,
        redis_url: Optional[str] = None,
    ):
        self.default_tenant_rpm = default_tenant_rpm
        self.default_tenant_burst = default_tenant_burst
        
        # Per-tenant token buckets
        self.tenant_buckets: Dict[str, TenantBucket] = {}
        
        # Per-model rate limit tracking
        self.model_trackers: Dict[str, ModelTracker] = defaultdict(ModelTracker)
        
        # Priority queue for pending requests
        self.request_queue: deque[QueuedRequest] = deque()
        self.queue_lock = asyncio.Lock()
        
        # Redis for distributed coordination (optional)
        self.enable_redis = enable_redis
        self.redis_client = None
        if enable_redis and redis_url:
            try:
                import redis.asyncio as redis
                self.redis_client = redis.from_url(redis_url)
                logger.info("Redis rate limiter initialized")
            except ImportError:
                logger.warning("Redis not available, using local rate limiting")
                self.enable_redis = False
        
        # Background queue processor
        self.queue_processor_task: Optional[asyncio.Task] = None
        self._shutdown = False
        
    async def start(self):
        """Start background queue processor."""
        if not self.queue_processor_task:
            self.queue_processor_task = asyncio.create_task(self._process_queue())
            logger.info("Rate limiter queue processor started")
    
    async def stop(self):
        """Stop background queue processor."""
        self._shutdown = True
        if self.queue_processor_task:
            self.queue_processor_task.cancel()
            try:
                await self.queue_processor_task
            except asyncio.CancelledError:
                pass
        if self.redis_client:
            await self.redis_client.close()
    
    def get_tenant_bucket(self, tenant_id: str) -> TenantBucket:
        """Get or create tenant bucket."""
        if tenant_id not in self.tenant_buckets:
            config = RateLimitConfig(
                requests_per_minute=self.default_tenant_rpm,
                tokens_per_minute=self.default_tenant_rpm * 1000,  # Assume 1k tokens/request
                burst_allowance=self.default_tenant_burst,
            )
            self.tenant_buckets[tenant_id] = TenantBucket(
                tokens=config.requests_per_minute + config.burst_allowance,
                last_update=time.time(),
                config=config,
            )
        return self.tenant_buckets[tenant_id]
    
    async def acquire(
        self,
        tenant_id: str,
        model: str,
        priority: RequestPriority = RequestPriority.NORMAL,
    ) -> bool:
        """
        Acquire rate limit permission.
        Returns True if request can proceed immediately.
        Returns False if request was queued (caller should await the future).
        """
        if not self.queue_processor_task:
            await self.start()
            
        # Check model availability (adaptive backoff)
        tracker = self.model_trackers[model]
        if not tracker.is_available():
            backoff_rem = tracker.backoff_until - time.time()
            if backoff_rem > 60.0:
                raise RuntimeError(
                    f"Model {model} is rate-limited/overloaded with a long backoff of {backoff_rem:.1f}s. "
                    f"Fail-fast triggered to avoid process hang."
                )
            logger.debug(f"Model {model} in backoff until {tracker.backoff_until}")
            return await self._enqueue(tenant_id, model, priority)
        
        # Check tenant rate limit
        bucket = self.get_tenant_bucket(tenant_id)
        if bucket.can_consume():
            return True
        
        # Rate limited - enqueue request
        logger.debug(f"Tenant {tenant_id} rate limited, queuing request")
        return await self._enqueue(tenant_id, model, priority)
    
    async def _enqueue(self, tenant_id: str, model: str, priority: RequestPriority) -> bool:
        """Enqueue request and return False (indicating queued)."""
        future = asyncio.Future()
        request = QueuedRequest(
            future=future,
            priority=priority,
            tenant_id=tenant_id,
            model=model,
        )
        
        async with self.queue_lock:
            self.request_queue.append(request)
        
        # Wait for queue processing
        try:
            await future
            return True
        except asyncio.CancelledError:
            # Request cancelled, remove from queue
            async with self.queue_lock:
                self.request_queue.remove(request)
            raise
    
    async def _process_queue(self):
        """Background task to process queued requests."""
        while not self._shutdown:
            try:
                processed = False
                async with self.queue_lock:
                    if self.request_queue:
                        # Sort request queue for priority
                        sorted_requests = sorted(self.request_queue)
                        for req in sorted_requests:
                            if req.future.cancelled():
                                self.request_queue.remove(req)
                                continue
                            tracker = self.model_trackers[req.model]
                            bucket = self.get_tenant_bucket(req.tenant_id)
                            if tracker.is_available() and bucket.can_consume():
                                self.request_queue.remove(req)
                                req.future.set_result(True)
                                processed = True
                                break
                
                if not processed:
                    await asyncio.sleep(0.1)
                    
            except Exception as e:
                logger.error(f"Queue processor error: {e}")
                await asyncio.sleep(1)
    
    def record_success(self, model: str):
        """Record successful API call."""
        self.model_trackers[model].record_success()

    def record_failure(self, model: str, error_code: int, delay: Optional[float] = None):
        """Record failed API call and apply appropriate backoff."""
        tracker = self.model_trackers[model]
        if error_code == 429:
            tracker.record_failure_429(delay)
            logger.warning(
                "Model %s hit rate limit (429), backoff until %.1f",
                model, tracker.backoff_until,
            )
        elif error_code in (500, 503, 529):
            tracker.record_failure_503(delay)
            logger.warning(
                "Model %s server overloaded (%d), backoff until %.1f",
                model, error_code, tracker.backoff_until,
            )
        # Other error codes (400, 402, 404) — no backoff, they're not transient

    def get_model_stats(self, model: str) -> Dict:
        """Get statistics for a model."""
        tracker = self.model_trackers[model]
        return {
            "success_count": tracker.success_count,
            "failure_count": tracker.failure_count,
            "success_rate": tracker.get_success_rate(),
            "backoff_until": tracker.backoff_until,
            "is_available": tracker.is_available(),
        }
    
    def get_tenant_stats(self, tenant_id: str) -> Dict:
        """Get statistics for a tenant."""
        bucket = self.get_tenant_bucket(tenant_id)
        return {
            "tokens_remaining": bucket.tokens,
            "rpm_limit": bucket.config.requests_per_minute,
            "burst_allowance": bucket.config.burst_allowance,
        }
    
    def get_best_available_model(
        self,
        model_list: list,
        skip_models: Optional[Set[str]] = None,
    ) -> Optional[str]:
        """Get best available model from list, excluding models in skip_models.

        Args:
            model_list: Ordered list of model IDs to consider.
            skip_models: Set of model IDs to exclude (already failed this pass).
        """
        skip = skip_models or set()
        available = [
            (m, self.model_trackers[m].get_success_rate())
            for m in model_list
            if m not in skip and self.model_trackers[m].is_available()
        ]
        if not available:
            return None
        # Sort by success rate descending
        available.sort(key=lambda x: x[1], reverse=True)
        return available[0][0]


# Global singleton instance
_global_limiter: Optional[MultitenantRateLimiter] = None


def get_rate_limiter() -> MultitenantRateLimiter:
    """Get global rate limiter instance."""
    global _global_limiter
    if _global_limiter is None:
        rpm = int(os.environ.get("OMEGA_TENANT_RPM_LIMIT", "30"))
        burst = int(os.environ.get("OMEGA_TENANT_BURST_ALLOWANCE", "2"))
        _global_limiter = MultitenantRateLimiter(
            default_tenant_rpm=rpm,
            default_tenant_burst=burst,
        )
    return _global_limiter


async def init_rate_limiter(enable_redis: bool = False, redis_url: Optional[str] = None):
    """Initialize global rate limiter."""
    global _global_limiter
    if _global_limiter is None:
        rpm = int(os.environ.get("OMEGA_TENANT_RPM_LIMIT", "30"))
        burst = int(os.environ.get("OMEGA_TENANT_BURST_ALLOWANCE", "2"))
        _global_limiter = MultitenantRateLimiter(
            default_tenant_rpm=rpm,
            default_tenant_burst=burst,
            enable_redis=enable_redis,
            redis_url=redis_url,
        )
        await _global_limiter.start()
    return _global_limiter
