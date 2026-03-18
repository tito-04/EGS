import uuid

import httpx

BASE_URL = "http://127.0.0.1:8000"


def _forwarded_ip_headers() -> dict[str, str]:
    return {"X-Forwarded-For": f"203.0.113.{uuid.uuid4().int % 200 + 1}"}


def test_login_rate_limit_returns_429() -> None:
    """Burst failed login attempts and assert limiter starts rejecting requests."""
    headers = _forwarded_ip_headers()
    hit_unauthorized = False
    hit_rate_limit = False

    with httpx.Client(timeout=20.0) as client:
        for _ in range(30):
            response = client.post(
                f"{BASE_URL}/api/v1/auth/login",
                headers=headers,
                json={"email": "ratelimit@example.com", "password": "wrong-password"},
            )

            if response.status_code == 401:
                hit_unauthorized = True

            if response.status_code == 429:
                hit_rate_limit = True
                break

    assert hit_unauthorized
    assert hit_rate_limit


def test_forgot_password_rate_limit_returns_429() -> None:
    """Forgot-password endpoint should eventually reject burst requests."""
    headers = _forwarded_ip_headers()
    hit_ok = False
    hit_rate_limit = False

    with httpx.Client(timeout=20.0) as client:
        for _ in range(20):
            response = client.post(
                f"{BASE_URL}/api/v1/auth/forgot-password",
                headers=headers,
                json={"email": "nobody@example.com"},
            )

            if response.status_code == 200:
                hit_ok = True

            if response.status_code == 429:
                hit_rate_limit = True
                break

    assert hit_ok
    assert hit_rate_limit
