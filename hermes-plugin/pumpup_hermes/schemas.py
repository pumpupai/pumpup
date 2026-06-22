"""Agent-facing JSON schemas for the six pumpup_* tools.

The contract-typed parameters (elicitation `fields`, recommendations, `metadataPatch`) are loaded
from a committed, generated artifact — `generated/contract_schemas.json`, emitted by the shared
`gen-schemas` generator in the OpenClaw plugin from the Pump Up SDK types (themselves generated from
backend/openapi.yaml). One generator, two consumers; the contract types can't drift from the wire.
Param names are camelCase, matching the agent API request bodies and the OpenClaw plugin's tools.
"""

from __future__ import annotations

import json
from pathlib import Path

_CONTRACTS = json.loads((Path(__file__).parent / "generated" / "contract_schemas.json").read_text())
_FIELD = _CONTRACTS["field"]
_APPROVAL_RECOMMENDATION = _CONTRACTS["approvalRecommendation"]
_FIELD_BID = _CONTRACTS["fieldBid"]
_METADATA_PATCH = _CONTRACTS["metadataPatch"]

_PROJECT_NAME = {"type": "string", "description": "Pump Up project slug"}
_KEY_VALUE_CONTEXT = {
    "type": "object",
    "additionalProperties": {"type": "string"},
    "description": "Context shown to the reviewer, as key→value strings",
}
_DETAIL = {"type": "object", "additionalProperties": True, "description": "Freeform structured event detail"}
_TRANSITIONS_TO = {"type": "string", "description": "Declared task state to transition into"}
_EXTERNAL_TRACE_ID = {"type": "string", "description": "Links this event to your agent's trace/run id"}
_ATTACHMENTS = {
    "type": "array",
    "description": "Workspace files to upload and attach for the reviewer",
    "items": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Workspace-relative file path"},
            "label": {"type": "string", "description": "Display label shown to the reviewer"},
        },
        "required": ["path", "label"],
    },
}


def _tool(name: str, description: str, properties: dict, required: list) -> dict:
    """Assemble a tool schema from its (camelCase) properties."""
    return {
        "name": name,
        "description": description,
        "parameters": {"type": "object", "properties": properties, "required": required},
    }


REQUEST_APPROVAL = _tool(
    "pumpup_request_approval",
    "Request human sign-off in Pump Up. Returns pending immediately; the decision later resumes this session.",
    {
        "projectName": _PROJECT_NAME,
        "summary": {"type": "string", "description": "What needs approval"},
        "keyValueContext": _KEY_VALUE_CONTEXT,
        "recommendation": _APPROVAL_RECOMMENDATION,
        "attachments": _ATTACHMENTS,
    },
    ["projectName", "summary"],
)

REQUEST_ELICITATION = _tool(
    "pumpup_request_elicitation",
    "Ask a human for structured input in Pump Up. Returns pending immediately; the answer later resumes this session.",
    {
        "projectName": _PROJECT_NAME,
        "summary": {"type": "string", "description": "What input is needed"},
        "fields": {"type": "array", "items": _FIELD, "description": "Fields to elicit; validated per type server-side"},
        "keyValueContext": _KEY_VALUE_CONTEXT,
        "recommendation": {"type": "array", "items": _FIELD_BID, "description": "Per-field suggested values"},
        "attachments": _ATTACHMENTS,
    },
    ["projectName", "summary", "fields"],
)

RECORD_ACTION = _tool(
    "pumpup_record_action",
    "Record something the agent did on the Pump Up timeline. Fire-and-forget; returns the event id.",
    {
        "projectName": _PROJECT_NAME,
        "description": {"type": "string", "description": "What the agent did"},
        "detail": _DETAIL,
        "transitionsTo": _TRANSITIONS_TO,
        "externalTraceId": _EXTERNAL_TRACE_ID,
        "metadataPatch": _METADATA_PATCH,
        "attachments": _ATTACHMENTS,
    },
    ["projectName", "description"],
)

REPORT_EXCEPTION = _tool(
    "pumpup_report_exception",
    "Report an agent error/exception on the Pump Up timeline. Fire-and-forget; returns the event id.",
    {
        "projectName": _PROJECT_NAME,
        "message": {"type": "string", "description": "What went wrong"},
        "detail": _DETAIL,
        "transitionsTo": _TRANSITIONS_TO,
        "externalTraceId": _EXTERNAL_TRACE_ID,
    },
    ["projectName", "message"],
)

ADD_NOTE = _tool(
    "pumpup_add_note",
    "Add a freeform note to the Pump Up timeline. Fire-and-forget; returns the event id.",
    {
        "projectName": _PROJECT_NAME,
        "message": {"type": "string", "description": "The annotation text"},
        "externalTraceId": _EXTERNAL_TRACE_ID,
    },
    ["projectName", "message"],
)

GET_DECISION = _tool(
    "pumpup_get_decision",
    "Check once whether a Pump Up request has been decided. Non-blocking; does not resume.",
    {
        "requestId": {"type": "string", "description": "The requestId returned by a request_* tool"},
        "type": {"type": "string", "enum": ["approval", "elicitation"], "description": "Which kind of request"},
    },
    ["requestId", "type"],
)
