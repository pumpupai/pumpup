"""Map SDK errors to a structured tool failure (a JSON string) — the single choke point so a
failing Pump Up call surfaces as a branchable result the agent can read, never a raw exception."""

from __future__ import annotations

import json
from typing import Any, Optional

from pumpup.core.api_error import ApiError


def to_tool_failure(action: str, exc: BaseException) -> str:
    """Render any error raised while calling Pump Up as a {status:"failed", ...} JSON string."""
    if isinstance(exc, ApiError):
        http_status = exc.status_code
        message, code = _describe_body(exc.body)
        message = message or str(exc)
        prefix = f"{action} failed" + (f" (HTTP {http_status})" if http_status else "") + f": {message}."
        tip = _advice(http_status)
        return json.dumps(
            {
                "status": "failed",
                "http_status": http_status,
                "code": code,
                "message": f"{prefix} {tip}".strip() if tip else prefix,
            }
        )
    message = str(exc) or type(exc).__name__
    return json.dumps(
        {"status": "failed", "http_status": None, "code": None, "message": f"{action} failed: {message}."}
    )


def _describe_body(body: Any) -> tuple[Optional[str], Optional[str]]:
    """Pull a human message (+ optional code) out of an SDK error body — `ApiError` (400) carries
    message+code, `ErrorResponse` (404/409/500) carries `error`; a connection error has no body."""
    message = getattr(body, "message", None)
    code = getattr(body, "code", None)
    error = getattr(body, "error", None)
    if isinstance(body, dict):
        message = message or body.get("message")
        code = code or body.get("code")
        error = error or body.get("error")
    if isinstance(message, str):
        return message, code if isinstance(code, str) else None
    if isinstance(error, str):
        return error, None
    return None, None


def _advice(http_status: Optional[int]) -> str:
    """Short, status-specific guidance so the agent knows whether to retry."""
    match http_status:
        case 400:
            return "The request was invalid — fix the input and try again."
        case 404:
            return "The referenced project or task was not found — check the identifiers."
        case 409:
            return "This conflicts with the current state (it may already be decided) — do not retry unchanged."
        case status if status is not None and status >= 500:
            return "Pump Up had a server error; you may retry later."
        case _:
            return ""
