import uuid
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

BASE_URL = "http://127.0.0.1:8000"
SERVICE_KEY = "change-me-in-production"
SSO_COOKIE_NAME = "egs_sso"


@pytest.fixture
def client() -> httpx.Client:
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


def _extract_code_from_location(location: str) -> str:
    parsed = urlparse(location)
    query = parse_qs(parsed.query)
    codes = query.get("code", [])
    return codes[0] if codes else ""


def _ui_login_get_code(client: httpx.Client, email: str, password: str) -> str:
    response = client.get(
        f"{BASE_URL}/ui/login",
        params={
            "client_id": "flash-sale",
            "redirect_uri": "http://localhost:3000/callback",
            "state": "security-test",
        },
    )
    if response.status_code == 303:
        location = response.headers.get("location", "")
        code = _extract_code_from_location(location)
        assert code
        return code

    assert response.status_code == 200

    csrf_token = client.cookies.get("csrf_token", "")
    assert csrf_token

    response = client.post(
        f"{BASE_URL}/ui/login",
        data={
            "email": email,
            "password": password,
            "client_id": "flash-sale",
            "redirect_uri": "http://localhost:3000/callback",
            "csrf_token": csrf_token,
            "state": "security-test",
        },
    )
    assert response.status_code == 303

    location = response.headers.get("location", "")
    code = _extract_code_from_location(location)
    assert code
    return code


def test_ui_login_client_id_and_redirect_validation(client: httpx.Client) -> None:
    response = client.get(
        f"{BASE_URL}/ui/login",
        params={"redirect_uri": "http://localhost:3000/callback"},
    )
    assert response.status_code == 422

    response = client.get(
        f"{BASE_URL}/ui/login",
        params={
            "client_id": "flash-sale",
            "redirect_uri": "http://localhost:3001/callback",
        },
    )
    assert response.status_code == 400

    response = client.get(
        f"{BASE_URL}/ui/login",
        params={
            "client_id": "unknown-client",
            "redirect_uri": "http://localhost:3000/callback",
        },
    )
    assert response.status_code == 400


def test_authorization_code_replay_and_client_mismatch(client: httpx.Client) -> None:
    email = _unique_email("replay")
    password = "InitialPass123"
    assert _register_user(client, email, password) == 201

    code = _ui_login_get_code(client, email, password)

    response = client.post(
        f"{BASE_URL}/api/v1/auth/exchange-code",
        json={"code": code, "client_id": "flash-sale"},
    )
    assert response.status_code == 200

    response = client.post(
        f"{BASE_URL}/api/v1/auth/exchange-code",
        json={"code": code, "client_id": "flash-sale"},
    )
    assert response.status_code == 401

    code_2 = _ui_login_get_code(client, email, password)
    response = client.post(
        f"{BASE_URL}/api/v1/auth/exchange-code",
        json={"code": code_2, "client_id": "payment"},
    )
    assert response.status_code == 401


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


def test_ui_logout_revokes_sso_cookie_token(client: httpx.Client) -> None:
    email = _unique_email("ui-logout")
    password = "InitialPass123"
    assert _register_user(client, email, password) == 201

    _ui_login_get_code(client, email, password)
    sso_token = client.cookies.get(SSO_COOKIE_NAME)
    assert sso_token

    response = client.get(
        f"{BASE_URL}/ui/logout",
        params={"client_id": "flash-sale", "redirect_uri": "http://localhost:3000/callback"},
    )
    assert response.status_code == 303

    response = client.post(
        f"{BASE_URL}/api/v1/auth/verify",
        headers={"X-Service-Auth": SERVICE_KEY},
        json={"token": sso_token},
    )
    assert response.status_code == 200
    assert response.json().get("valid") is False


def test_forgot_reset_api_and_ui_paths(client: httpx.Client) -> None:
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

    response = client.get(
        f"{BASE_URL}/ui/forgot-password",
        params={
            "client_id": "flash-sale",
            "redirect_uri": "http://localhost:3000/callback",
        },
    )
    assert response.status_code == 200

    response = client.post(
        f"{BASE_URL}/ui/forgot-password",
        data={
            "email": email,
            "client_id": "flash-sale",
            "redirect_uri": "http://localhost:3000/callback",
            "csrf_token": "invalid",
        },
    )
    assert response.status_code == 403

    response = client.get(
        f"{BASE_URL}/ui/reset-password",
        params={
            "token": "dummy-token",
            "client_id": "flash-sale",
            "redirect_uri": "http://localhost:3000/callback",
        },
    )
    assert response.status_code == 200
