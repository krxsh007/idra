import pytest
from app.core.errors import AppException
from app.core.ratelimit import RateLimiter


def test_rate_limiter_allows_under_limit() -> None:
    limiter = RateLimiter()
    key = "test_client_1"
    for _ in range(5):
        limiter.check(key=key, requests_per_minute=10)


def test_rate_limiter_blocks_over_limit() -> None:
    limiter = RateLimiter()
    key = "test_client_2"
    for _ in range(10):
        limiter.check(key=key, requests_per_minute=10)

    with pytest.raises(AppException) as exc_info:
        limiter.check(key=key, requests_per_minute=10)

    assert exc_info.value.status_code == 429
    assert exc_info.value.code == "RATE_LIMITED"
    assert exc_info.value.headers is not None
    assert "Retry-After" in exc_info.value.headers
