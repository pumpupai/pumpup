# Pump Up × Hermes plugin

Lets a [Hermes](https://hermes-agent.nousresearch.com) agent request a human approval/elicitation
from [Pump Up](https://pumpup.com) and **act on the human decision in its original conversation** —
hours later, with no inbound network access. Design: this repo's
`tech-docs/current/hermes-plugin.md`.

It's also the first real consumer of the Pump Up Python SDK (`AsyncPumpUp`), so it doubles as an
SDK smoke test.

## How it works

1. The agent calls `pumpup_request_approval` (or `_elicitation`). The tool resolves a Pump Up task
   (one per Hermes session), creates the request, writes a durable breadcrumb
   `{request_id → session_id}`, and returns `{request_id, status: "pending"}` immediately. The
   turn ends — **nothing blocks** (HITL takes hours; Hermes tools hard-timeout at 300s).
2. A human decides in the Pump Up web app.
3. The plugin's `pumpup` gateway platform runs a background poll loop (outbound only). For each open
   breadcrumb it asks Pump Up whether the request is decided.
4. On a decision it POSTs the formatted result to the local API server
   (`/api/sessions/{session_id}/chat`), which replays the full transcript and runs a real agent turn
   in the **origin** session — so the agent continues the task it started. The breadcrumb is cleared.

Because the poll is outbound and the resume is localhost, this works for every deployment shape,
including a fully NAT'd host with no inbound access (a webhook could never reach it).

## Requirements

The plugin needs an **always-on Hermes gateway with the API server enabled** — that gateway hosts
the poll loop and is the target of the resume. A purely-ephemeral CLI Hermes can't resume an
hours-old conversation (no process to return to).

```sh
export API_SERVER_ENABLED=true
export API_SERVER_KEY=$(openssl rand -hex 32)   # required; the resume call authenticates with it
# optional: API_SERVER_HOST (default 127.0.0.1), API_SERVER_PORT (default 8642)
```

## Install

**From PyPI** (recommended):

```sh
pip install pumpup-hermes-plugin
hermes plugins enable pumpup
```

Hermes auto-discovers it via the `hermes_agent.plugins` entry point, and pip pulls its deps (incl.
`pumpup-sdk`). Then enable the `pumpup` gateway platform.

**From the OSS repo** (no PyPI):

```sh
hermes plugins install pumpupai/pumpup/hermes-plugin --enable
```

`hermes plugins install` accepts a subdirectory, so this works even though the plugin lives under
`hermes-plugin/` in the mirror.

**Local development:** `uv sync` — the Pump Up SDK resolves from the SDK repo's `dev` branch via
`[tool.uv.sources]` (`mise run fern:sdk:dev` regenerates it); a built wheel instead depends on
`pumpup-sdk` from PyPI, as uv strips the dev source. Then enable the `pumpup` gateway platform.

## Config (env)

| Var | Required | Notes |
|---|---|---|
| `PUMPUP_BASE_URL` | yes | Pump Up agent API base URL |
| `PUMPUP_API_KEY` | yes | Pump Up agent API key (read natively by the SDK) |
| `PUMPUP_POLL_INTERVAL_SEC` | no | Decision poll interval (default 30 — HITL is hours) |
| `API_SERVER_KEY` / `API_SERVER_HOST` / `API_SERVER_PORT` | — | Hermes's own gateway env; reused for resume |

The `pumpup` tools and platform self-enable when `PUMPUP_BASE_URL` + `PUMPUP_API_KEY` are present.

## Tools

| Tool | What |
|---|---|
| `pumpup_request_approval` | Request human sign-off; returns pending, resumes on decision |
| `pumpup_request_elicitation` | Ask a human for structured fields; returns pending, resumes on answer |
| `pumpup_record_action` | Record agent activity on the task timeline (attach files, patch metadata, transition) |
| `pumpup_report_exception` | Report an agent error/exception |
| `pumpup_add_note` | Add a freeform note |
| `pumpup_get_decision` | One-shot, non-blocking check whether a request was decided |

## Develop

```sh
uv sync          # dev venv (pytest, ruff)
uv run pytest    # unit tests
uv run ruff check .
```

The contract schemas in `pumpup_hermes/generated/contract_schemas.json` (the `Field` union etc.) are a
committed, generated artifact — produced from the Pump Up SDK types by the shared generator in the
OpenClaw plugin (`cd ../openclaw-plugin && npm run gen:schemas`). One generator, two consumers; don't
hand-edit. Regenerate after a contract-type change.
