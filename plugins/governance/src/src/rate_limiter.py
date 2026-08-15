"Token-bucket rate limiter (TASK-SCHED-003)."

class RateLimiter:
    "Per-key token bucket with capacity cap."

    def __init__(self, capacity: int = 10) -> None:
        if capacity <= 0:
            raise ValueError("capacity must be positive")
        self.capacity = capacity
        self._buckets: dict[str, int] = {}

    def _check_key(self, key: str) -> None:
        if not key.strip():
            raise ValueError("key must be non-empty")

    def _check_tokens(self, tokens: int) -> None:
        if not isinstance(tokens, int):
            raise ValueError("tokens must be int")
        if tokens <= 0:
            raise ValueError("tokens must be positive")

    def allow(self, key: str, tokens: int = 1) -> bool:
        "Consume tokens atomically; no consumption on failure."
        self._check_key(key)
        self._check_tokens(tokens)
        self._buckets[key] = self._buckets.get(key, self.capacity)
        if self._buckets[key] < tokens:
            return False
        self._buckets[key] -= tokens
        return True

    def refill(self, key: str, n: int) -> None:
        "Add tokens, capped at capacity."
        self._check_key(key)
        self._check_tokens(n)
        self._buckets[key] = min(self.capacity, self._buckets.get(key, self.capacity) + n)

    def remaining(self, key: str) -> int:
        "Return available tokens; unknown key returns capacity."
        self._check_key(key)
        return self._buckets.get(key, self.capacity)
