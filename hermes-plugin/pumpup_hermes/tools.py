"""The pumpup_* tool handlers, task resolution, and the dispatch wrapper that routes every error to
a structured failure (the single choke point). Handlers are async, return a JSON string, and read
the Hermes session_id from **kwargs to bind a durable Pump Up task. All share the one global client.
"""

from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

from . import schemas
from .attachments import upload_attachments
from .client import get_client
from .config import is_configured
from .errors import to_tool_failure
from .state import Breadcrumb, get_store

from pydantic import TypeAdapter
from pumpup import ApprovalRecommendation, AsyncPumpUp, Field, FieldBid, MetadataPatchDto

TOOLSET = "pumpup"

# Build the agent's wire dicts into the SDK's typed request models, validating at construction — a malformed
# recommendation / field / bid fails locally with a precise error before the request. A TypeAdapter handles
# the Field discriminated union (each arm constructed by its `type`), which a single model class can't.
_RECOMMENDATION = TypeAdapter(Optional[ApprovalRecommendation])
_FIELD_BIDS = TypeAdapter(Optional[list[FieldBid]])
_FIELDS = TypeAdapter(list[Field])
_METADATA_PATCH = TypeAdapter(Optional[MetadataPatchDto])

# The agent guide — embedded markdown (generated artifact) returned by pumpup_guide, plus the SKILL.md
# backing the pull-loadable `pumpup:guide` skill.
_GUIDE_TEXT = (Path(__file__).parent / "generated" / "agent_guide.md").read_text(encoding="utf-8")
_GUIDE_SKILL = Path(__file__).parent / "skills" / "guide" / "SKILL.md"

# Per-process cache of the auto-created task id per session_id — keyed exactly like the idempotency key
# (one task per session), so a cache miss after a restart re-resolves the same task; the cache only spares
# a round-trip. Guarded by a lock: tool calls run on multiple worker threads.
_session_tasks: dict[str, str] = {}
_session_tasks_lock = threading.Lock()


async def resolve_task_id(client: AsyncPumpUp, project_name: str, session_id: Optional[str]) -> str:
    """Find-or-create this session's one durable task, cached in-process. Keyed by session_id so a new
    session opens a fresh task — a decision must land in the session that opened it (project of first use)."""
    if not session_id:
        raise RuntimeError("pumpup: no Hermes session_id to bind a task to")
    with _session_tasks_lock:
        cached = _session_tasks.get(session_id)
    if cached:
        return cached
    task = await client.tasks.create(
        idempotency_key=f"hermes-task:{session_id}",
        project_name=project_name,
        name=f"Hermes session {session_id}",
        external_id=session_id,
    )
    with _session_tasks_lock:
        _session_tasks[session_id] = task.id
    return task.id


async def fetch_result(client: AsyncPumpUp, kind: str, request_id: str) -> Any:
    """Fetch a request's decision: the result once decided, None while pending (the SDK maps the 204
    pending response to a None body). An unknown id / server error raises and propagates."""
    if kind == "approval":
        return await client.approvals.get_result(request_id)
    return await client.elicitations.get_result(request_id)


async def _record_action(args: dict, session_id: Optional[str]) -> str:
    """Record autonomous agent activity on the task timeline; may attach files, patch metadata, transition."""
    client = get_client()
    project_name = args["projectName"]
    task_id = await resolve_task_id(client, project_name, session_id)
    add_attachments = await upload_attachments(client, args.get("attachments"))
    created = await client.events.agent_action(
        idempotency_key=str(uuid.uuid4()),
        project_name=project_name,
        description=args["description"],
        task_id=task_id,
        detail=args.get("detail"),
        transitions_to=args.get("transitionsTo"),
        metadata_patch=_METADATA_PATCH.validate_python(args.get("metadataPatch")),
        add_attachments=add_attachments or None,
        external_trace_id=args.get("externalTraceId"),
    )
    return json.dumps({"event_id": created.event_id})


async def _report_exception(args: dict, session_id: Optional[str]) -> str:
    """Report an agent error/exception; transition-only (no metadata/attachments — those ride an action)."""
    client = get_client()
    project_name = args["projectName"]
    task_id = await resolve_task_id(client, project_name, session_id)
    created = await client.events.exception(
        idempotency_key=str(uuid.uuid4()),
        project_name=project_name,
        message=args["message"],
        task_id=task_id,
        detail=args.get("detail"),
        transitions_to=args.get("transitionsTo"),
        external_trace_id=args.get("externalTraceId"),
    )
    return json.dumps({"event_id": created.event_id})


async def _add_note(args: dict, session_id: Optional[str]) -> str:
    """Add a freeform annotation to the task timeline (no attachments / state changes)."""
    client = get_client()
    project_name = args["projectName"]
    task_id = await resolve_task_id(client, project_name, session_id)
    created = await client.events.note(
        idempotency_key=str(uuid.uuid4()),
        project_name=project_name,
        message=args["message"],
        task_id=task_id,
        external_trace_id=args.get("externalTraceId"),
    )
    return json.dumps({"event_id": created.event_id})


async def _get_decision(args: dict, _session_id: Optional[str]) -> str:
    """One-shot, non-blocking read of a request's decision; 200 = decided payload, else still pending."""
    client = get_client()
    result = await fetch_result(client, args["type"], args["requestId"])
    if result is None:
        return json.dumps({"status": "pending"})
    return json.dumps({"status": "decided", "decision": result.model_dump(mode="json", by_alias=True)})


async def _guide(args: dict, _session_id: Optional[str]) -> str:
    """Return the Pump Up usage guide (how/when to use the tools, the pending/resume model). Static text."""
    return json.dumps({"guide": _GUIDE_TEXT})


async def _attach_to_task(
    client: AsyncPumpUp, project_name: str, task_id: str, inputs: Optional[list[dict[str, Any]]]
) -> list[str]:
    """Upload attachments, attach them to the task via an action event, and return their upload ids.
    The API attaches files only through an action; a request then renders an already-attached file by id."""
    refs = await upload_attachments(client, inputs)
    if not refs:
        return []
    await client.events.agent_action(
        idempotency_key=str(uuid.uuid4()),
        project_name=project_name,
        task_id=task_id,
        description=f"Attached {len(refs)} file(s) for review",
        add_attachments=refs,
    )
    return [ref.upload_id for ref in refs]


def _park(request_id: str, kind: str, summary: str, session_id: str) -> None:
    """Durably record a request→session breadcrumb so the poll loop can resume the origin session on a decision."""
    store = get_store()
    crumb = Breadcrumb(
        request_id=request_id,
        session_id=session_id,
        type=kind,
        summary=summary,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    store.record(crumb)


async def _request_approval(args: dict, session_id: Optional[str]) -> str:
    """Request human sign-off; create the approval, durably park the wait, return pending immediately."""
    client = get_client()
    project_name = args["projectName"]
    task_id = await resolve_task_id(client, project_name, session_id)
    attachment_ids = await _attach_to_task(client, project_name, task_id, args.get("attachments"))
    summary = args["summary"]
    created = await client.approvals.create(
        idempotency_key=str(uuid.uuid4()),
        project_name=project_name,
        summary=summary,
        task_id=task_id,
        key_value_context=args.get("keyValueContext"),
        recommendation=_RECOMMENDATION.validate_python(args.get("recommendation")),
        attachments=attachment_ids or None,
    )
    _park(created.event_id, "approval", summary, session_id)
    return json.dumps({"requestId": created.event_id, "status": "pending"})


async def _request_elicitation(args: dict, session_id: Optional[str]) -> str:
    """Ask a human for structured fields; create the elicitation, durably park the wait, return pending."""
    client = get_client()
    project_name = args["projectName"]
    task_id = await resolve_task_id(client, project_name, session_id)
    attachment_ids = await _attach_to_task(client, project_name, task_id, args.get("attachments"))
    summary = args["summary"]
    created = await client.elicitations.create(
        idempotency_key=str(uuid.uuid4()),
        project_name=project_name,
        summary=summary,
        task_id=task_id,
        fields=_FIELDS.validate_python(args["fields"]),
        key_value_context=args.get("keyValueContext"),
        recommendation=_FIELD_BIDS.validate_python(args.get("recommendation")),
        attachments=attachment_ids or None,
    )
    _park(created.event_id, "elicitation", summary, session_id)
    return json.dumps({"requestId": created.event_id, "status": "pending"})


def _tool_handler(action: str, core: Callable[[dict, Optional[str]], Awaitable[str]]) -> Callable[..., Awaitable[str]]:
    """Wrap a tool's core coroutine: pass the dispatched session_id, map any error to a failure JSON."""

    async def handler(args: dict, **kwargs: Any) -> str:
        try:
            return await core(args, kwargs.get("session_id"))
        except Exception as exc:  # noqa: BLE001 — the choke point; nothing should escape into Hermes
            return to_tool_failure(action, exc)

    return handler


def _register(ctx: Any, schema: dict, handler: Callable[..., Awaitable[str]]) -> None:
    """Register one async tool into the `pumpup` toolset, gated on Pump Up being configured."""
    ctx.register_tool(
        name=schema["name"],
        toolset=TOOLSET,
        schema=schema,
        handler=handler,
        check_fn=is_configured,
        is_async=True,
        description=schema["description"],
    )


def register_request_tools(ctx: Any) -> None:
    """Register the two request tools (approval, elicitation): create → park breadcrumb → return pending."""
    _register(ctx, schemas.REQUEST_APPROVAL, _tool_handler("request_approval", _request_approval))
    _register(ctx, schemas.REQUEST_ELICITATION, _tool_handler("request_elicitation", _request_elicitation))


def register_capture_tools(ctx: Any) -> None:
    """Register the fire-and-forget timeline tools plus the one-shot decision read (no wait, no resume)."""
    _register(ctx, schemas.RECORD_ACTION, _tool_handler("record_action", _record_action))
    _register(ctx, schemas.REPORT_EXCEPTION, _tool_handler("report_exception", _report_exception))
    _register(ctx, schemas.ADD_NOTE, _tool_handler("add_note", _add_note))
    _register(ctx, schemas.GET_DECISION, _tool_handler("get_decision", _get_decision))


def register_guide(ctx: Any) -> None:
    """Register the pumpup_guide tool and, when configured, the pull-loadable `pumpup:guide` skill."""
    _register(ctx, schemas.GUIDE, _tool_handler("guide", _guide))
    if is_configured():
        ctx.register_skill("guide", _GUIDE_SKILL, description=schemas.GUIDE["description"])
