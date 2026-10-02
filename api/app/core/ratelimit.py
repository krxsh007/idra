import time
from collections import defaultdict
from dataclasses import dataclass

from fastapi import Request, status

from app.core.config import settings
from app.core.errors import AppException, ErrorCode


@dataclass
class TokenBucket:
    tokens: float
    last_updated: float
    rate: float  # tokens per second
    capacity: float  # burst capacity


class RateLimiter:
    def __init__(self) -> None:
        self.buckets: dict[str, TokenBucket] = defaultdict(self._default_bucket)

    def _default_bucket(self) -> TokenBucket:
        # Default 10 requests per minute = 10 / 60 tokens per second
        rate = settings.RATE_LIMIT_PUBLIC_PER_MIN / 60.0
        return TokenBucket(
            tokens=float(settings.RATE_LIMIT_PUBLIC_PER_MIN),
            last_updated=time.time(),
            rate=rate,
            capacity=float(settings.RATE_LIMIT_PUBLIC_PER_MIN),
        )

    def check(
        self,
        key: str,
        requests_per_minute: int = 10,
    ) -> None:
        now = time.time()
        bucket = self.buckets[key]

        # Recalculate rate and capacity if different from default
        rate = requests_per_minute / 60.0
        capacity = float(requests_per_minute)

        # Replenish tokens based on elapsed time
        elapsed = now - bucket.last_updated
        bucket.tokens = min(capacity, bucket.tokens + elapsed * rate)
        bucket.last_updated = now

        if bucket.tokens < 1.0:
            retry_after = int(max(1, (1.0 - bucket.tokens) / rate))
            raise AppException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                code=ErrorCode.RATE_LIMITED,
                message=f"Rate limit exceeded. Try again in {retry_after} seconds.",
                headers={"Retry-After": str(retry_after)},
            )

        bucket.tokens -= 1.0


rate_limiter = RateLimiter()


async def limit_public_reports(request: Request) -> None:
    """Dependency enforcing public rate limit on report submissions."""
    client_ip = request.client.host if request.client else "127.0.0.1"
    rate_limiter.check(
        key=f"reports:{client_ip}",
        requests_per_minute=settings.RATE_LIMIT_PUBLIC_PER_MIN,
    )


async def limit_public_assistant(request: Request) -> None:
    """Dependency enforcing public rate limit on citizen assistance queries."""
    client_ip = request.client.host if request.client else "127.0.0.1"
    rate_limiter.check(
        key=f"assistant:{client_ip}",
        requests_per_minute=settings.RATE_LIMIT_PUBLIC_PER_MIN,
    )
