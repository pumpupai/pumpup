---
name: pumpup
description: How to use the Pump Up human-in-the-loop tools: when to request an approval or elicitation, the pending/resume model (end your turn, don't busy-poll), and recording timeline events.
---

# Using Pump Up from an agent

Pump Up is a human-in-the-loop control plane: you drop work for a human and get their decision back. The `pumpup_*` tools let you ask a person to approve an action or provide input, and record what you did on a shared timeline — without writing any wait-and-resume machinery yourself.

## When to use it

Reach for Pump Up when a human is in the loop for **authority or missing input**, not for things you can decide or look up yourself.

- **Approval** — you did the work (or are about to take an action) and a person with authority must bless it: anything irreversible, high-stakes, or governed by policy/liability.
- **Elicitation** — you need structured information only a human can supply and can't safely infer: a missing value, a category decision, a confirmation. Don't guess — ask.

If you can answer it yourself, do that. HITL is for sign-off and human-only input, not a substitute for your own reasoning.

## The pending/resume contract — read this first

The two request tools (`pumpup_request_approval`, `pumpup_request_elicitation`) return `{ requestId, status: "pending" }` **immediately** and never block.

A human decision takes minutes to hours. So after you call a request tool:

- **Stop. End your turn.** Don't wait, don't loop, don't keep working as if you have the answer.
- You will be **resumed automatically in this same conversation** when the decision arrives, carrying the human's decision or answers. Continue the task from there.
- **Do not busy-wait** by calling `pumpup_get_decision` in a loop — you'll be resumed for free, and polling just burns the turn.

This is the single most important thing to get right.

## The request tools

- **`pumpup_request_approval`** — ask for a yes/no sign-off. Optionally include a `recommendation` (your suggested decision + confidence + rationale) so the reviewer can move fast.
- **`pumpup_request_elicitation`** — ask for typed `fields` (date, select, number, text, slider, switch, …). Each field has an `id`; the answer comes back keyed by that id. Optionally include a `recommendation` of per-field bids (a pre-fill + confidence).

Both also take:

- `summary` — a clear, human-readable description of what's needed and why (required).
- `keyValueContext` — context shown to the reviewer as key→value pairs. Give them what they need to decide without leaving the screen.
- `attachments` — workspace-relative file paths (confined to the workspace) rendered alongside the request: photos, documents, evidence.

## Capture tools — fire-and-forget, no wait

Use these to keep the human's timeline rich, so whoever picks up the work has the full context. They return an event id immediately and never block or resume.

- **`pumpup_record_action`** — record something you did. Can also attach files, patch the task's metadata (`metadataPatch`), and move the task to a declared state (`transitionsTo`).
- **`pumpup_report_exception`** — record that something went wrong. Transition-only (no metadata or attachments).
- **`pumpup_add_note`** — leave a freeform annotation.

## `pumpup_get_decision`

A one-shot, non-blocking check of a single request (by `requestId` + `type`): decided → the decision payload, otherwise still pending. Use it only if you deliberately want to peek mid-turn. It is **not** how you wait for a decision — resume is.

## Projects and tasks

You pass a `projectName` (the Pump Up project slug) on every call. The plugin owns the **task** for you — one durable task per conversation — so you never create or handle task ids.

## Linking your traces

Every event and request takes an optional `externalTraceId` — set it to your own run/trace id to line a Pump Up record up with your agent's observability.

## A typical flow

1. Do the work.
2. Need sign-off → call `pumpup_request_approval` with a clear `summary`, the `keyValueContext` a reviewer needs, your `recommendation` if you have a lean, and any `attachments` as evidence.
3. **End your turn.**
4. You're resumed with the decision → act on it: proceed on approve, revise or escalate on reject.
