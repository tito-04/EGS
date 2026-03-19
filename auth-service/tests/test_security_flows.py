import uuid
from collections.abc import Iterator

import httpx
import pytest

BASE_URL = "http://127.0.0.1:8000"
SERVICE_KEY = "change-me-in-production"


@pytest.fixture
def client() -> Iterator[httpx.Client]:
    with httpx.Client(follow_redirects=False, timeout=20.0) as c:
        yield c


def _unique_email(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}@example.com"


def _client_headers() -> dict[str, str]:
    return {"X-Forwarded-For": f"198.51.100.{uuid.uuid4().int % 200 + 1}"}


def _register_user(client: httpx.Client, email: str, password: str) -> int:
    response = client.post(
        f"{BASE_URL}/api/v1/auth/register",
        json={
            "email": email,
            "password": password,
            "full_name": "Security Test User",
            "role": "fan",
        },
    )
    return response.status_code


def _login_api(client: httpx.Client, email: str, password: str) -> httpx.Response:
    return client.post(
        f"{BASE_URL}/api/v1/auth/login",
        headers=_client_headers(),
        json={"email": email, "password": password},
    )


def test_verify_endpoint_requires_service_auth(client: httpx.Client) -> None:
    email = _unique_email("verify")
    password = "InitialPass123"
    assert _register_user(client, email, password) == 201

    response = _login_api(client, email, password)
    assert response.status_code == 200
    access_token = response.json()["access_token"]

    response = client.post(
        f"{BASE_URL}/api/v1/auth/verify",
        json={"token": access_token},
    )
    assert response.status_code == 403

    response = client.post(
        f"{BASE_URL}/api/v1/auth/verify",
        headers={"X-Service-Auth": SERVICE_KEY},
        json={"token": access_token},
    )
    assert response.status_code == 200
    assert response.json().get("valid") is True


def test_logout_revokes_token_with_denylist(client: httpx.Client) -> None:
    email = _unique_email("denylist")
    password = "InitialPass123"
    assert _register_user(client, email, password) == 201

    response = _login_api(client, email, password)
    assert response.status_code == 200
    access_token = response.json()["access_token"]

    response = client.get(
        f"{BASE_URL}/api/v1/auth/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert response.status_code == 200

    response = client.post(
        f"{BASE_URL}/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert response.status_code == 204

    response = client.get(
        f"{BASE_URL}/api/v1/auth/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert response.status_code == 401

    response = client.post(
        f"{BASE_URL}/api/v1/auth/verify",
        headers={"X-Service-Auth": SERVICE_KEY},
        json={"token": access_token},
    )
    assert response.status_code == 200
    assert response.json().get("valid") is False


def test_refresh_rotation_revokes_previous_refresh_token(client: httpx.Client) -> None:
    email = _unique_email("rotation")
    password = "InitialPass123"
    assert _register_user(client, email, password) == 201

    response = _login_api(client, email, password)
    assert response.status_code == 200
    refresh_token_1 = response.json()["refresh_token"]

    response = client.post(
        f"{BASE_URL}/api/v1/auth/refresh",
        json={"refresh_token": refresh_token_1},
    )
    assert response.status_code == 200
    refresh_token_2 = response.json()["refresh_token"]
    assert refresh_token_2 != refresh_token_1

    response = client.post(
        f"{BASE_URL}/api/v1/auth/refresh",
        json={"refresh_token": refresh_token_1},
    )
    assert response.status_code == 401

    response = client.post(
        f"{BASE_URL}/api/v1/auth/refresh",
        json={"refresh_token": refresh_token_2},
    )
    assert response.status_code == 200


def test_forgot_and_reset_api_paths(client: httpx.Client) -> None:
    email = _unique_email("reset")
    password = "InitialPass123"
    assert _register_user(client, email, password) == 201

    response = client.post(
        f"{BASE_URL}/api/v1/auth/forgot-password",
        json={"email": email},
    )
    assert response.status_code == 200
    assert response.json().get("message") == "If the account exists, a password reset link was sent"

    response = client.post(
        f"{BASE_URL}/api/v1/auth/reset-password",
        json={"token": "invalid", "new_password": "ChangedPass123"},
    )
    assert response.status_code == 401


def test_delete_account_requires_password_and_revokes_access(client: httpx.Client) -> None:
    email = _unique_email("delete")
    password = "InitialPass123"
    assert _register_user(client, email, password) == 201

    response = _login_api(client, email, password)
    assert response.status_code == 200
    access_token = response.json()["access_token"]

    response = client.request(
        "DELETE",
        f"{BASE_URL}/api/v1/auth/me",
        headers={"Authorization": f"Bearer {access_token}"},
        json={"password": "wrong-password"},
    )
    assert response.status_code == 401

    response = client.request(
        "DELETE",
        f"{BASE_URL}/api/v1/auth/me",
        headers={"Authorization": f"Bearer {access_token}"},
        json={"password": password},
    )
    assert response.status_code == 200

    response = client.get(
        f"{BASE_URL}/api/v1/auth/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert response.status_code == 401


