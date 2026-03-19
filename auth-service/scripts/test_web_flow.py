#!/usr/bin/env python3
"""End-to-end API flow checker for Auth Service security contracts."""

import argparse
import sys
import uuid

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


class ApiFlowRunner:
    def __init__(self, base_url: str, service_key: str, timeout: float) -> None:
        self.base_url = base_url.rstrip("/")
        self.service_key = service_key
        self.http = httpx.Client(follow_redirects=False, timeout=timeout)
        self.email = f"apiflow_{uuid.uuid4().hex[:10]}@example.com"
        self.password = "InitialPass123"

    def close(self) -> None:
        self.http.close()

    def _health_check(self) -> None:
        _print_step("Health check")
        response = self.http.get(f"{self.base_url}/health")
        _require(response.status_code == 200, f"health expected 200 got {response.status_code}")
        _print_ok("Service is healthy")

    def _register(self) -> None:
        _print_step("Register user")
        response = self.http.post(
            f"{self.base_url}/api/v1/auth/register",
            json={
                "email": self.email,
                "password": self.password,
                "full_name": "API Flow User",
                "role": "fan",
            },
        )
        _require(response.status_code == 201, f"register expected 201 got {response.status_code}")
        _print_ok("User registration succeeded")

    def _login(self) -> tuple[str, str]:
        _print_step("Login and obtain tokens")
        response = self.http.post(
            f"{self.base_url}/api/v1/auth/login",
            json={"email": self.email, "password": self.password},
        )
        _require(response.status_code == 200, f"login expected 200 got {response.status_code}")
        payload = response.json()
        access_token = payload.get("access_token", "")
        refresh_token = payload.get("refresh_token", "")
        _require(bool(access_token and refresh_token), "login did not return both access and refresh tokens")
        _print_ok("Login returned access + refresh tokens")
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
        _print_ok("Service-auth verification contract validated")

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
        _print_ok("Refresh token rotation is enforced")
        return refresh_token_2

    def _logout_revokes_access(self, access_token: str) -> None:
        _print_step("Logout revokes access token")
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

    def _forgot_and_invalid_reset(self) -> None:
        _print_step("Forgot-password and reset-token guard")
        forgot = self.http.post(
            f"{self.base_url}/api/v1/auth/forgot-password",
            json={"email": self.email},
        )
        _require(forgot.status_code == 200, f"forgot-password expected 200 got {forgot.status_code}")

        reset = self.http.post(
            f"{self.base_url}/api/v1/auth/reset-password",
            json={"token": "invalid-token", "new_password": "ChangedPass123"},
        )
        _require(reset.status_code == 401, f"invalid reset token expected 401 got {reset.status_code}")
        _print_ok("Password reset endpoints enforce token validation")

    def run(self) -> int:
        _print_info(f"Base URL: {self.base_url}")

        self._health_check()
        self._register()
        access_token, refresh_token = self._login()

        self._verify_contract(access_token)
        rotated_refresh = self._refresh_rotation(refresh_token)
        _require(bool(rotated_refresh), "missing rotated refresh token")

        self._logout_revokes_access(access_token)
        self._forgot_and_invalid_reset()

        print(f"\n{GREEN}{BOLD}ALL API FLOW CHECKS PASSED{RESET}")
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Run API flow checks for Auth Service")
    parser.add_argument("--base-url", default="http://localhost:8000", help="Auth service base URL")
    parser.add_argument("--service-key", default="change-me-in-production", help="X-Service-Auth internal service key")
    parser.add_argument("--timeout", type=float, default=20.0, help="HTTP timeout seconds")
    args = parser.parse_args()

    runner = ApiFlowRunner(
        base_url=args.base_url,
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
