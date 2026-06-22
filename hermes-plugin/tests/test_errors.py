"""Error → tool-failure mapping: SDK errors become a structured {status:"failed"} the agent can branch on,
with status-specific guidance."""

from __future__ import annotations

import json

from pumpup.core.api_error import ApiError

from pumpup_hermes.errors import to_tool_failure


def test_api_error_carries_status_and_message():
    out = json.loads(to_tool_failure("decide", ApiError(status_code=409, body={"error": "already decided"})))
    assert out["status"] == "failed"
    assert out["http_status"] == 409
    assert "already decided" in out["message"]


def test_non_api_error_has_null_status():
    out = json.loads(to_tool_failure("decide", ValueError("boom")))
    assert out["http_status"] is None
    assert "boom" in out["message"]


def test_advice_is_status_specific():
    not_found = json.loads(to_tool_failure("x", ApiError(status_code=404, body={"error": "nope"})))["message"]
    server = json.loads(to_tool_failure("x", ApiError(status_code=500, body={"error": "oops"})))["message"]
    assert not_found != server
