import json
import logging
import time
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import Request


class JsonFormatter(logging.Formatter):
    """Format logs as single-line JSON for ingestion-friendly output."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        request_log = getattr(record, "request_log", None)
        if isinstance(request_log, dict):
            payload.update(request_log)

        audit_log = getattr(record, "audit_log", None)
        if isinstance(audit_log, dict):
            payload.update(audit_log)

        return json.dumps(payload, separators=(",", ":"))


def configure_observability(log_level: str = "info") -> None:
    """Configure root logging once with JSON formatting."""
    root_logger = logging.getLogger()
    if root_logger.handlers:
        for handler in root_logger.handlers:
            handler.setFormatter(JsonFormatter())
        root_logger.setLevel(log_level.upper())
        return

    logging.basicConfig(level=log_level.upper())
    for handler in root_logger.handlers:
        handler.setFormatter(JsonFormatter())


def _request_ids(request: Request) -> tuple[str, str]:
    request_id = getattr(request.state, "request_id", "")
    correlation_id = getattr(request.state, "correlation_id", request_id)
    return request_id, correlation_id


def get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        ip = forwarded.split(",", 1)[0].strip()
        if ip:
            return ip

    if request.client:
        return request.client.host
    return ""


def initialize_request_context(request: Request) -> tuple[str, str]:
    request_id = request.headers.get("X-Request-ID") or str(uuid4())
    correlation_id = request.headers.get("X-Correlation-ID") or request_id

    request.state.request_id = request_id
    request.state.correlation_id = correlation_id

    return request_id, correlation_id


def log_request(request: Request, status_code: int, duration_ms: float) -> None:
    request_id, correlation_id = _request_ids(request)
    logging.getLogger("auth.request").info(
        "request",
        extra={
            "request_log": {
                "event_type": "request",
                "request_id": request_id,
                "correlation_id": correlation_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": status_code,
                "duration_ms": round(duration_ms, 2),
                "client_ip": get_client_ip(request),
            }
        },
    )


def emit_audit_event(
    request: Request,
    action: str,
    outcome: str,
    user_id: str | None = None,
    email: str | None = None,
    role: str | None = None,
    client_id: str | None = None,
    details: dict | None = None,
) -> None:
    request_id, correlation_id = _request_ids(request)
    payload = {
        "event_type": "auth_audit",
        "request_id": request_id,
        "correlation_id": correlation_id,
        "action": action,
        "outcome": outcome,
        "path": request.url.path,
        "client_ip": get_client_ip(request),
    }

    if user_id:
        payload["user_id"] = user_id
    if email:
        payload["email"] = email
    if role:
        payload["role"] = role
    if client_id:
        payload["client_id"] = client_id
    elif isinstance(details, dict) and details.get("client_id"):
        payload["client_id"] = str(details["client_id"])
    if details:
        payload["details"] = details

    logging.getLogger("auth.audit").info(
        "auth_audit",
        extra={"audit_log": payload},
    )


def now_monotonic() -> float:
    return time.perf_counter()
