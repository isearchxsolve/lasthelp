"""Rate limiting and retry logic with exponential backoff."""
import time
import random
from functools import wraps
from typing import Callable, Any, Optional


class RateLimiter:
    """Simple rate limiter to avoid hammering sites."""

    def __init__(self, min_delay: float = 2.0, max_delay: float = 8.0):
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.last_request_time: Optional[float] = None

    def wait(self) -> None:
        """Wait if needed before next request."""
        if self.last_request_time is not None:
            elapsed = time.time() - self.last_request_time
            needed = random.uniform(self.min_delay, self.max_delay)
            if elapsed < needed:
                sleep_time = needed - elapsed
                print(f"[RateLimiter] Sleeping {sleep_time:.1f}s...")
                time.sleep(sleep_time)
        self.last_request_time = time.time()


def retry_with_backoff(
    max_retries: int = 3,
    base_delay: float = 2.0,
    max_delay: float = 30.0,
    exceptions: tuple = (Exception,),
    on_retry: Optional[Callable] = None,
):
    """Decorator: retry a function with exponential backoff + jitter."""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            for attempt in range(1, max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    if attempt == max_retries:
                        raise

                    delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
                    jitter = random.uniform(0, delay * 0.3)
                    total_delay = delay + jitter

                    print(f"[Retry] {func.__name__} failed (attempt {attempt}/{max_retries}): {e}")
                    print(f"[Retry] Waiting {total_delay:.1f}s before retry...")

                    if on_retry:
                        on_retry(attempt, e)

                    time.sleep(total_delay)
            return None
        return wrapper
    return decorator


class CircuitBreaker:
    """Circuit breaker: stop trying after N consecutive failures."""

    def __init__(self, failure_threshold: int = 5, recovery_timeout: float = 60.0):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failures = 0
        self.last_failure_time: Optional[float] = None
        self.state = "closed"  # closed, open, half-open

    def call(self, func: Callable, *args, **kwargs) -> Any:
        if self.state == "open":
            if self.last_failure_time and (time.time() - self.last_failure_time) > self.recovery_timeout:
                self.state = "half-open"
                print("[CircuitBreaker] Entering half-open state...")
            else:
                raise Exception(f"[CircuitBreaker] Circuit is OPEN. Wait {self.recovery_timeout}s.")

        try:
            result = func(*args, **kwargs)
            if self.state == "half-open":
                self.state = "closed"
                self.failures = 0
                print("[CircuitBreaker] Circuit CLOSED. Service recovered.")
            return result
        except Exception as e:
            self.failures += 1
            self.last_failure_time = time.time()
            if self.failures >= self.failure_threshold:
                self.state = "open"
                print(f"[CircuitBreaker] Circuit OPENED after {self.failures} failures.")
            raise e
