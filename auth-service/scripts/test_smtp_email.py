#!/usr/bin/env python3
"""Trigger dev SMTP test email endpoint."""

import argparse
import sys

import httpx


def main() -> int:
    parser = argparse.ArgumentParser(description="Send SMTP test email via auth-service")
    parser.add_argument("--base-url", default="http://localhost:8000", help="Auth service base URL")
    parser.add_argument("--email", default="dev-inbox@example.com", help="Recipient email")
    args = parser.parse_args()

    endpoint = f"{args.base_url.rstrip('/')}/api/v1/auth/dev/test-email"

    try:
        response = httpx.post(endpoint, json={"email": args.email}, timeout=15.0)
    except Exception as exc:
        print(f"Request failed: {exc}")
        return 1

    print(f"Status: {response.status_code}")
    try:
        print(response.json())
    except Exception:
        print(response.text)

    return 0 if response.status_code == 200 else 1


if __name__ == "__main__":
    sys.exit(main())
