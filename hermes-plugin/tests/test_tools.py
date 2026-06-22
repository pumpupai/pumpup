"""Tool handlers: typed-object construction (incl. the Field union), local validation, task idempotency,
and the error choke point. The SDK client is mocked; the breadcrumb store is the real temp-dir store."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

from pumpup import ApprovalRecommendation, FieldBid
from pumpup.core.api_error import ApiError
from pumpup.types.field import Field_Text

from pumpup_hermes import tools
from pumpup_hermes.state import get_store

_FIELD = {"type": "Text", "id": "name", "label": "Name", "required": True}
_REC = {"outcome": {"type": "APPROVE"}, "confidence": 0.8}


def _client() -> MagicMock:
    client = MagicMock()
    client.tasks.create = AsyncMock(return_value=MagicMock(id="task-1"))
    client.approvals.create = AsyncMock(return_value=MagicMock(event_id="ev-appr"))
    client.elicitations.create = AsyncMock(return_value=MagicMock(event_id="ev-elic"))
    client.events.agent_action = AsyncMock(return_value=MagicMock(event_id="ev-act"))
    return client


async def test_request_approval_parks_breadcrumb_and_sends_typed_model(monkeypatch):
    client = _client()
    monkeypatch.setattr(tools, "get_client", lambda: client)
    out = json.loads(
        await tools._request_approval({"projectName": "p", "summary": "ship?", "recommendation": _REC}, "sA")
    )
    assert out == {"requestId": "ev-appr", "status": "pending"}
    assert [c.request_id for c in get_store().list_open()] == ["ev-appr"]
    sent = client.approvals.create.await_args.kwargs["recommendation"]
    assert isinstance(sent, ApprovalRecommendation)  # a typed object reached the SDK, not a raw dict


async def test_request_elicitation_constructs_union_arms_and_bids(monkeypatch):
    client = _client()
    monkeypatch.setattr(tools, "get_client", lambda: client)
    await tools._request_elicitation(
        {
            "projectName": "p",
            "summary": "s",
            "fields": [_FIELD],
            "recommendation": [{"fieldId": "name", "value": "Ada"}],
        },
        "sA",
    )
    kwargs = client.elicitations.create.await_args.kwargs
    assert isinstance(kwargs["fields"][0], Field_Text)  # union resolved to the right arm
    assert isinstance(kwargs["recommendation"][0], FieldBid)


async def test_malformed_field_fails_locally_without_calling_the_api(monkeypatch):
    client = _client()
    monkeypatch.setattr(tools, "get_client", lambda: client)
    handler = tools._tool_handler("request_elicitation", tools._request_elicitation)
    out = json.loads(await handler({"projectName": "p", "summary": "s", "fields": [{"type": "Nope"}]}, session_id="sA"))
    assert out["status"] == "failed"
    client.elicitations.create.assert_not_awaited()


async def test_resolve_task_id_is_idempotent_per_session():
    client = _client()
    first = await tools.resolve_task_id(client, "proj", "sA")
    second = await tools.resolve_task_id(client, "proj", "sA")
    assert first == second == "task-1"
    client.tasks.create.assert_awaited_once()
    assert client.tasks.create.await_args.kwargs["idempotency_key"] == "hermes-task:sA"


async def test_record_action_returns_event_id(monkeypatch):
    client = _client()
    monkeypatch.setattr(tools, "get_client", lambda: client)
    out = json.loads(await tools._record_action({"projectName": "p", "description": "did x"}, "sA"))
    assert out == {"event_id": "ev-act"}


async def test_get_decision_reports_pending_then_decided(monkeypatch):
    client = _client()
    client.approvals.get_result = AsyncMock(return_value=None)
    monkeypatch.setattr(tools, "get_client", lambda: client)
    pending = json.loads(await tools._get_decision({"requestId": "x", "type": "approval"}, None))
    assert pending == {"status": "pending"}

    decided = MagicMock()
    decided.model_dump.return_value = {"outcome": {"type": "APPROVE"}}
    client.approvals.get_result = AsyncMock(return_value=decided)
    out = json.loads(await tools._get_decision({"requestId": "x", "type": "approval"}, None))
    assert out["status"] == "decided" and out["decision"] == {"outcome": {"type": "APPROVE"}}


async def test_tool_handler_maps_sdk_error_to_structured_failure():
    async def boom(args, session_id):
        raise ApiError(status_code=409, body={"error": "already decided"})

    out = json.loads(await tools._tool_handler("decide", boom)({}, session_id="sA"))
    assert out["status"] == "failed" and out["http_status"] == 409
