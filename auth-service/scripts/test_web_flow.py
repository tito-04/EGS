#!/usr/bin/env python3
"""End-to-end web flow checker for Auth Service UI + critical API handshakes."""

import argparse
import json
import re
import sys
import time
import uuid
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

import httpx


GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
RESET = "\033[0m"
BOLD = "\033[1m"


def _print_step(text: str) -> None:
    print(f"{BOLD}{BLUE}==>{RESET} {text}")


def _print_ok(text: str) -> None:
    print(f"{GREEN}PASS{RESET} {text}")


def _print_fail(text: str) -> None:
    print(f"{RED}FAIL{RESET} {text}")


def _print_info(text: str) -> None:
    print(f"{YELLOW}INFO{RESET} {text}")


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _extract_code_from_location(location: str) -> str:
    query = parse_qs(urlparse(location).query)
    return query.get("code", [""])[0]


class WebFlowRunner:
    def __init__(
        self,
        base_url: str,
        mailpit_url: str,
        client_id: str,
        redirect_uri: str,
        service_key: str,
        timeout: float,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.mailpit_url = mailpit_url.rstrip("/")
        self.client_id = client_id
        self.redirect_uri = redirect_uri
        self.service_key = service_key
        self.http = httpx.Client(follow_redirects=False, timeout=timeout)

    def close(self) -> None:
        self.http.close()

    def _csrf_cookie(self) -> str:
        return self.http.cookies.get("csrf_token", "")

    def _state(self, prefix: str) -> str:
        return f"{prefix}-{uuid.uuid4().hex[:8]}"

    def _health_check(self) -> None:
        _print_step("Health check")
        response = self.http.get(f"{self.base_url}/health")
        _require(response.status_code == 200, f"health expected 200 got {response.status_code}")
        _print_ok("Service is healthy")

    def _ui_register(self, email: str, password: str, full_name: str, state: str) -> None:
        _print_step("UI register")
        response = self.http.get(
            f"{self.base_url}/ui/register",
            params={"client_id": self.client_id, "redirect_uri": self.redirect_uri, "state": state},
        )
        _require(response.status_code == 200, f"register page expected 200 got {response.status_code}")

        csrf = self._csrf_cookie()
        _require(bool(csrf), "missing csrf cookie on register page")

        response = self.http.post(
            f"{self.base_url}/ui/register",
            data={
                "email": email,
                "password": password,
                "full_name": full_name,
                "client_id": self.client_id,
                "redirect_uri": self.redirect_uri,
                "state": state,
                "csrf_token": csrf,
            },
        )
        _require(response.status_code == 303, f"register submit expected 303 got {response.status_code}")
        _print_ok("User registered via UI")

    def _ui_login_get_code(self, email: str, password: str, state: str) -> str:
        _print_step("UI login and redirect code")
        response = self.http.get(
            f"{self.base_url}/ui/login",
            params={"client_id": self.client_id, "redirect_uri": self.redirect_uri, "state": state},
        )

        if response.status_code == 303:
            location = response.headers.get("location", "")
            code = _extract_code_from_location(location)
            _require(bool(code), "missing code in SSO auto-redirect")
            _print_ok("SSO auto-login produced authorization code")
            return code

        _require(response.status_code == 200, f"login page expected 200 got {response.status_code}")
        csrf = self._csrf_cookie()
        _require(bool(csrf), "missing csrf cookie on login page")

        response = self.http.post(
            f"{self.base_url}/ui/login",
            data={
                "email": email,
                "password": password,
                "client_id": self.client_id,
                "redirect_uri": self.redirect_uri,
                "state": state,
                "csrf_token": csrf,
            },
        )
        _require(response.status_code == 303, f"login submit expected 303 got {response.status_code}")

        location = response.headers.get("location", "")
        _require(location.startswith(self.redirect_uri), "login redirect target mismatch")
        code = _extract_code_from_location(location)
        _require(bool(code), "missing code in login redirect")
        _print_ok("UI login produced authorization code")
        return code

    def _exchange_code(self, code: str) -> tuple[str, str]:
        _print_step("Exchange authorization code")
        response = self.http.post(
            f"{self.base_url}/api/v1/auth/exchange-code",
            json={"code": code, "client_id": self.client_id},
        )
        _require(response.status_code == 200, f"exchange expected 200 got {response.status_code}")
        data = response.json()
        access_token = data.get("access_token", "")
        refresh_token = data.get("refresh_token", "")
        _require(bool(access_token and refresh_token), "exchange did not return tokens")
        _print_ok("Exchange returned access + refresh tokens")
        return access_token, refresh_token

    def _verify_contract(self, access_token: str) -> None:
        _print_step("Verify endpoint contract")
        forbidden = self.http.post(
            f"{self.base_url}/api/v1/auth/verify",
            json={"token": access_token},
        )
        _require(forbidden.status_code == 403, f"verify without header expected 403 got {forbidden.status_code}")

        ok = self.http.post(
            f"{self.base_url}/api/v1/auth/verify",
            headers={"X-Service-Auth": self.service_key},
            json={"token": access_token},
        )
        _require(ok.status_code == 200, f"verify with header expected 200 got {ok.status_code}")
        _require(ok.json().get("valid") is True, "verify response did not mark token valid")
        _print_ok("Verify header contract validated")

    def _refresh_rotation(self, refresh_token: str) -> str:
        _print_step("Refresh rotation and old-token revocation")
        response = self.http.post(
            f"{self.base_url}/api/v1/auth/refresh",
            json={"refresh_token": refresh_token},
        )
        _require(response.status_code == 200, f"refresh expected 200 got {response.status_code}")
        refresh_token_2 = response.json().get("refresh_token", "")
        _require(bool(refresh_token_2 and refresh_token_2 != refresh_token), "refresh token was not rotated")

        replay = self.http.post(
            f"{self.base_url}/api/v1/auth/refresh",
            json={"refresh_token": refresh_token},
        )
        _require(replay.status_code == 401, f"old refresh replay expected 401 got {replay.status_code}")
        _print_ok("Refresh rotation is enforced")
        return refresh_token_2

    def _api_logout_revokes_access(self, access_token: str) -> None:
        _print_step("API logout revokes access token")
        response = self.http.post(
            f"{self.base_url}/api/v1/auth/logout",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        _require(response.status_code == 204, f"logout expected 204 got {response.status_code}")

        me = self.http.get(
            f"{self.base_url}/api/v1/auth/me",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        _require(me.status_code == 401, f"me with revoked token expected 401 got {me.status_code}")
        _print_ok("Access token revoked after logout")

    def _ui_logout_revokes_sso_cookie(self, email: str, password: str) -> None:
        _print_step("UI logout revokes SSO cookie token")
        _ = self._ui_login_get_code(email, password, self._state("ui-logout"))
        sso_token = self.http.cookies.get("egs_sso", "")
        _require(bool(sso_token), "missing SSO cookie after login")

        response = self.http.get(
            f"{self.base_url}/ui/logout",
            params={"client_id": self.client_id, "redirect_uri": self.redirect_uri},
        )
        _require(response.status_code == 303, f"ui logout expected 303 got {response.status_code}")

        verify = self.http.post(
            f"{self.base_url}/api/v1/auth/verify",
            headers={"X-Service-Auth": self.service_key},
            json={"token": sso_token},
        )
        _require(verify.status_code == 200, f"verify revoked sso expected 200 got {verify.status_code}")
        _require(verify.json().get("valid") is False, "SSO token should be invalid after UI logout")
        _print_ok("UI logout revoked SSO token")

    def _mailpit_messages(self) -> list[dict[str, Any]]:
        response = self.http.get(f"{self.mailpit_url}/api/v1/messages")
        _require(response.status_code == 200, f"mailpit messages expected 200 got {response.status_code}")
        data = response.json()
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        if isinstance(data, dict):
            messages = data.get("messages")
            if isinstance(messages, list):
                return [item for item in messages if isinstance(item, dict)]
        return []

    def _mailpit_message_body(self, message_id: str) -> str:
        response = self.http.get(f"{self.mailpit_url}/api/v1/message/{message_id}")
        _require(response.status_code == 200, f"mailpit message expected 200 got {response.status_code}")
        try:
            payload = response.json()
            return json.dumps(payload)
        except Exception:
            return response.text

    def _extract_reset_token(self, email: str, timeout_seconds: int = 20) -> str:
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            messages = self._mailpit_messages()
            for message in messages:
                if email not in json.dumps(message):
                    continue
                message_id = message.get("ID") or message.get("id")
                if not message_id:
                    continue
                body = self._mailpit_message_body(str(message_id))
                match = re.search(r"token=([A-Za-z0-9_\-\.]+)", body)
                if match:
                    return unquote(match.group(1))
            time.sleep(1)
        return ""

    def _forgot_and_reset_password_ui(self, email: str, new_password: str) -> None:
        _print_step("Forgot + reset password via UI")
        response = self.http.get(
            f"{self.base_url}/ui/forgot-password",
            params={"client_id": self.client_id, "redirect_uri": self.redirect_uri},
        )
        _require(response.status_code == 200, f"forgot page expected 200 got {response.status_code}")
        csrf = self._csrf_cookie()
        _require(bool(csrf), "missing csrf cookie on forgot page")

        response = self.http.post(
            f"{self.base_url}/ui/forgot-password",
            data={
                "email": email,
                "client_id": self.client_id,
                "redirect_uri": self.redirect_uri,
                "csrf_token": csrf,
            },
        )
        _require(response.status_code == 200, f"forgot submit expected 200 got {response.status_code}")

        token = self._extract_reset_token(email)
        _require(bool(token), "could not extract reset token from Mailpit")

        response = self.http.get(
            f"{self.base_url}/ui/reset-password",
            params={
                "token": token,
                "client_id": self.client_id,
                "redirect_uri": self.redirect_uri,
            },
        )
        _require(response.status_code == 200, f"reset page expected 200 got {response.status_code}")
        csrf = self._csrf_cookie()
        _require(bool(csrf), "missing csrf cookie on reset page")

        response = self.http.post(
            f"{self.base_url}/ui/reset-password",
            data={
                "token": token,
                "new_password": new_password,
                "confirm_password": new_password,
                "client_id": self.client_id,
                "redirect_uri": self.redirect_uri,
                "csrf_token": csrf,
            },
        )
        _require(response.status_code == 200, f"reset submit expected 200 got {response.status_code}")
        _print_ok("Password reset via UI + Mailpit works")

    def run(self) -> int:
        email = f"webflow_{uuid.uuid4().hex[:10]}@example.com"
        password = "InitialPass123"
        new_password = "ChangedPass123"

        _print_info(f"Base URL: {self.base_url}")
        _print_info(f"Mailpit URL: {self.mailpit_url}")
        _print_info(f"Client ID: {self.client_id}")

        self._health_check()
        self._ui_register(email, password, "Web Flow User", self._state("register"))

        code = self._ui_login_get_code(email, password, self._state("login"))
        access_token, refresh_token = self._exchange_code(code)

        self._verify_contract(access_token)
        refresh_token = self._refresh_rotation(refresh_token)
        _require(bool(refresh_token), "rotated refresh token missing")

        self._api_logout_revokes_access(access_token)
        self._ui_logout_revokes_sso_cookie(email, password)

        self._forgot_and_reset_password_ui(email, new_password)
        _ = self._ui_login_get_code(email, new_password, self._state("login-new-pass"))
        _print_ok("New password login successful")

        print(f"\n{GREEN}{BOLD}ALL WEB FLOW CHECKS PASSED{RESET}")
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Run end-to-end web flow checks for Auth Service")
    parser.add_argument("--base-url", default="http://localhost:8000", help="Auth service base URL")
    parser.add_argument("--mailpit-url", default="http://localhost:8025", help="Mailpit base URL")
    parser.add_argument("--client-id", default="flash-sale", help="Configured auth client_id")
    parser.add_argument("--redirect-uri", default="http://localhost:3000/callback", help="Configured redirect URI for client")
    parser.add_argument("--service-key", default="change-me-in-production", help="X-Service-Auth internal service key")
    parser.add_argument("--timeout", type=float, default=20.0, help="HTTP timeout seconds")
    args = parser.parse_args()

    runner = WebFlowRunner(
        base_url=args.base_url,
        mailpit_url=args.mailpit_url,
        client_id=args.client_id,
        redirect_uri=args.redirect_uri,
        service_key=args.service_key,
        timeout=args.timeout,
    )

    try:
        return runner.run()
    except Exception as exc:
        _print_fail(str(exc))
        return 1
    finally:
        runner.close()


if __name__ == "__main__":
    sys.exit(main())
