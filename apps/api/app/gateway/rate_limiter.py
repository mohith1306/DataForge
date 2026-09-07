"""Rate Limiter middleware for API Gateway."""
from typing import Any, Dict, Optional, Tuple
from datetime import datetime, timezone, timedelta
from pydantic import BaseModel, Field
from enum import Enum
import hashlib
import time
from collections import defaultdict


class RateLimitStrategy(str, Enum):
    """Rate limiting strategies."""
    FIXED_WINDOW = "fixed_window"
    SLIDING_WINDOW = "sliding_window"
    TOKEN_BUCKET = "token_bucket"


class RateLimitConfig(BaseModel):
    """Configuration for rate limiting."""
    requests_per_minute: int = 60
    requests_per_hour: int = 1000
    requests_per_day: int = 10000
    burst_size: int = 10
    strategy: RateLimitStrategy = RateLimitStrategy.SLIDING_WINDOW


class RateLimitResult(BaseModel):
    """Result of rate limit check."""
    allowed: bool
    limit: int
    remaining: int
    reset_at: datetime
    retry_after: Optional[int] = None
    metadata: Dict[str, Any] = {}


class RateLimiter:
    """Rate limiter with multiple strategies."""

    def __init__(self, config: Optional[RateLimitConfig] = None):
        self.config = config or RateLimitConfig()
        self.requests: Dict[str, list] = defaultdict(list)
        self.tokens: Dict[str, float] = {}
        self.window_start: Dict[str, datetime] = {}

    def check_rate_limit(
        self,
        client_id: str,
        endpoint: Optional[str] = None
    ) -> RateLimitResult:
        """Check if request is allowed under rate limit."""
        key = self._make_key(client_id, endpoint)

        if self.config.strategy == RateLimitStrategy.FIXED_WINDOW:
            return self._check_fixed_window(key)
        elif self.config.strategy == RateLimitStrategy.SLIDING_WINDOW:
            return self._check_sliding_window(key)
        elif self.config.strategy == RateLimitStrategy.TOKEN_BUCKET:
            return self._check_token_bucket(key)

        return RateLimitResult(allowed=True, limit=0, remaining=0, reset_at=datetime.now(timezone.utc))

    def _make_key(self, client_id: str, endpoint: Optional[str]) -> str:
        """Make a unique key for rate limiting."""
        if endpoint:
            return hashlib.md5(f"{client_id}:{endpoint}".encode()).hexdigest()
        return client_id

    def _check_fixed_window(self, key: str) -> RateLimitResult:
        """Fixed window rate limiting."""
        now = datetime.now(timezone.utc)
        window_start = now.replace(second=0, microsecond=0)

        if key not in self.window_start or self.window_start[key] != window_start:
            self.window_start[key] = window_start
            self.requests[key] = []

        self.requests[key].append(now)
        count = len(self.requests[key])

        limit = self.config.requests_per_minute
        remaining = max(0, limit - count)

        reset_at = window_start + timedelta(minutes=1)

        if count > limit:
            return RateLimitResult(
                allowed=False,
                limit=limit,
                remaining=0,
                reset_at=reset_at,
                retry_after=int((reset_at - now).total_seconds()),
                metadata={"window": "fixed", "count": count}
            )

        return RateLimitResult(
            allowed=True,
            limit=limit,
            remaining=remaining,
            reset_at=reset_at,
            metadata={"window": "fixed", "count": count}
        )

    def _check_sliding_window(self, key: str) -> RateLimitResult:
        """Sliding window rate limiting."""
        now = time.time()
        window = 60  # 1 minute

        # Clean old requests
        self.requests[key] = [
            t for t in self.requests[key]
            if now - t < window
        ]

        self.requests[key].append(now)
        count = len(self.requests[key])

        limit = self.config.requests_per_minute
        remaining = max(0, limit - count)

        reset_at = datetime.fromtimestamp(now + window, timezone.utc)

        if count > limit:
            oldest = self.requests[key][0]
            retry_after = int(window - (now - oldest)) + 1
            return RateLimitResult(
                allowed=False,
                limit=limit,
                remaining=0,
                reset_at=reset_at,
                retry_after=retry_after,
                metadata={"window": "sliding", "count": count}
            )

        return RateLimitResult(
            allowed=True,
            limit=limit,
            remaining=remaining,
            reset_at=reset_at,
            metadata={"window": "sliding", "count": count}
        )

    def _check_token_bucket(self, key: str) -> RateLimitResult:
        """Token bucket rate limiting."""
        now = time.time()
        refill_rate = self.config.requests_per_minute / 60.0  # tokens per second

        if key not in self.tokens:
            self.tokens[key] = float(self.config.burst_size)

        # Refill tokens
        last_refill = self.window_start.get(key, now)
        elapsed = now - last_refill
        self.tokens[key] = min(
            self.config.burst_size,
            self.tokens[key] + elapsed * refill_rate
        )
        self.window_start[key] = now

        if self.tokens[key] >= 1:
            self.tokens[key] -= 1
            return RateLimitResult(
                allowed=True,
                limit=self.config.burst_size,
                remaining=int(self.tokens[key]),
                reset_at=datetime.fromtimestamp(now + 1, timezone.utc),
                metadata={"strategy": "token_bucket", "tokens": self.tokens[key]}
            )
        else:
            retry_after = int((1 - self.tokens[key]) / refill_rate) + 1
            return RateLimitResult(
                allowed=False,
                limit=self.config.burst_size,
                remaining=0,
                reset_at=datetime.fromtimestamp(now + retry_after, timezone.utc),
                retry_after=retry_after,
                metadata={"strategy": "token_bucket", "tokens": self.tokens[key]}
            )

    def record_request(self, client_id: str, endpoint: Optional[str] = None) -> None:
        """Record a request for rate limiting."""
        key = self._make_key(client_id, endpoint)
        now = time.time()
        self.requests[key].append(now)

    def get_usage(self, client_id: str, endpoint: Optional[str] = None) -> Dict[str, Any]:
        """Get current usage for a client."""
        key = self._make_key(client_id, endpoint)
        now = time.time()
        window = 60

        recent = [t for t in self.requests[key] if now - t < window]

        return {
            "client_id": client_id,
            "endpoint": endpoint,
            "requests_last_minute": len(recent),
            "limit": self.config.requests_per_minute,
            "remaining": max(0, self.config.requests_per_minute - len(recent))
        }

    def reset(self, client_id: str, endpoint: Optional[str] = None) -> None:
        """Reset rate limit for a client."""
        key = self._make_key(client_id, endpoint)
        self.requests[key] = []
        self.tokens.pop(key, None)
        self.window_start.pop(key, None)
