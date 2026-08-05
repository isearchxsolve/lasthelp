class TokenBucket:
    """Thread-safe token bucket for RPM enforcement with jitter."""

    def __init__(self, rpm: float, burst: int = 2, min_gap: float = 0.5, safety: float = 0.80):
        self.rpm = max(1.0, rpm) * safety
        self.burst = burst
        self.min_gap = min_gap
        self.tokens = float(burst)
        self.last_update = time.monotonic()
        self.last_request = 0.0
        self.lock = threading.RLock()
        self.history: deque[float] = deque()

    def _refill(self):
        now = time.monotonic()
        elapsed = now - self.last_update
        self.tokens = min(self.burst, self.tokens + elapsed * (self.rpm / 60.0))
        self.last_update = now

    def _prune(self):
        cutoff = time.monotonic() - 60.0
        while self.history and self.history[0] < cutoff:
            self.history.popleft()

    def wait_time(self) -> float:
        with self.lock:
            self._refill()
            self._prune()
            waits = []
            if self.tokens < 1.0:
                waits.append((1.0 - self.tokens) / (self.rpm / 60.0))
            if self.history and len(self.history) >= int(self.rpm):
                waits.append(60.0 - (time.monotonic() - self.history[0]) + 0.5)
            since_last = time.monotonic() - self.last_request
            if since_last < self.min_gap:
                waits.append(self.min_gap - since_last)
            return max(waits) if waits else 0.0

    def try_acquire(self) -> bool:
        with self.lock:
            self._refill()
            self._prune()
            self._refill()
            self._prune()
            waits = []
            if self.tokens < 1.0:
                waits.append((1.0 - self.tokens) / (self.rpm / 60.0))
            if self.history and len(self.history) >= int(self.rpm):
                waits.append(60.0 - (time.monotonic() - self.history[0]) + 0.5)
            since_last = time.monotonic() - self.last_request
            if since_last < self.min_gap:
                waits.append(self.min_gap - since_last)
            wait = max(waits) if waits else 0.0
            if wait <= 0.01:
                self.tokens -= 1.0
                self.last_request = time.monotonic()
                return True
            return False

    def acquire(self, timeout: float = 5.0) -> bool:
        start = time.monotonic()
        while time.monotonic() - start < timeout:
            with self.lock:
                self._refill()
                self._prune()
                waits = []
                if self.tokens < 1.0:
                    waits.append((1.0 - self.tokens) / (self.rpm / 60.0))
                if self.history and len(self.history) >= int(self.rpm):
                    waits.append(60.0 - (time.monotonic() - self.history[0]) + 0.5)
                since_last = time.monotonic() - self.last_request
                if since_last < self.min_gap:
                    waits.append(self.min_gap - since_last)
                wait = max(waits) if waits else 0.0
                if wait <= 0.01:
                    self.tokens -= 1.0
                    self.last_request = time.monotonic()
                    return True
            time.sleep(min(max(wait, 0.05), 0.25))
        return False

    def commit(self):
        with self.lock:
            self.history.append(time.monotonic())

    def penalize(self, seconds: float):
        with self.lock:
            self.tokens = 0.0
            self.last_update = time.monotonic()
            self.last_request = time.monotonic() + max(0.0, seconds) - self.min_gap


@dataclass
class TokenMeter:
    prompt: int = 0
    completion: int = 0
    lock: threading.Lock = field(default_factory=threading.Lock)

    def record(self, prompt: int, completion: int):
        with self.lock:
            self.prompt += max(0, prompt)
            self.completion += max(0, completion)

    def report(self) -> str:
        total = self.prompt + self.completion
        return f"{total:,} tok total ({self.prompt:,} prompt + {self.completion:,} completion)"


# ═══════════════════════════════════════════════════════════════════════════════
#  SECTION 4: PROVIDER POOL (Self-Healing)
# ═══════════════════════════════════════════════════════════════════════════════

class Provider:
    def __init__(self, name: str, base_url: str, api_key: str, model_cfg: Dict[str, Any],
                 connect_timeout: float = 10.0, read_timeout: float = 20.0, bucket: Optional[TokenBucket] = None):
        self.name = name
        self.model_cfg = model_cfg
        self.model_id = model_cfg["id"]
        self.bucket = bucket if bucket is not None else TokenBucket(model_cfg.get("rpm", 20), safety=0.80)
        # Identity of the account/endpoint this provider talks to. Used
        # solely to find "sibling" providers that share the same real
        # quota (same base_url + api_key) when one of them gets a LIVE
        # 429 from the server — see ProviderPool.propagate_shared_cooldown.
        # Providers already share a TokenBucket instance when they share
        # this key (see build_pool's get_or_create_bucket), which correctly
        # prevents new *local* over-request; this additional identity is
        # for the separate case of a 429 that has already happened on the
        # wire, where every sibling provider should skip straight to its
        # own cooldown instead of each one havi