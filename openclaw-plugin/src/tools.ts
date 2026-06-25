import { randomUUID } from "node:crypto";

import { jsonResult } from "openclaw/plugin-sdk/core";
import type { AnyAgentTool, OpenClawPluginApi, OpenClawPluginToolContext } from "openclaw/plugin-sdk/plugin-entry";
import { type Static, type TSchema, Type } from "typebox";

import type { PumpUp, PumpUpClient } from "@pumpupai/pumpup-sdk";
import { type AttachmentInput, uploadAttachments } from "./attachments.js";
import type { PumpUpPluginConfig } from "./config.js";
import { toToolFailure } from "./errors.js";
import { agentGuide } from "./generated/agent-guide.js";
import {
  approvalRecommendationSchema,
  fieldBidSchema,
  fieldSchema,
  metadataPatchSchema,
} from "./generated/contract-schemas.js";
import { buildFlowState, type PumpUpRequestType } from "./state.js";

const AttachmentParam = Type.Object({
  path: Type.String({ description: "Workspace-relative file path" }),
  label: Type.String({ description: "Display label shown to the human reviewer" }),
});

const KeyValueContext = Type.Optional(
  Type.Record(Type.String(), Type.String(), { description: "Context shown to the reviewer, as key→value" }),
);

const DetailContext = Type.Optional(
  Type.Record(Type.String(), Type.Unknown(), { description: "Freeform structured detail recorded on the event" }),
);

/// SDK contract schemas (generated from openapi.yaml → SDK), typed back to their SDK types. The
/// agent-declared elicitation field union is the canonical `Field` schema; recommendations mirror
/// the SDK's `ApprovalRecommendation` / `FieldBid`; `MetadataPatch` mirrors `MetadataPatchDto`.
const ElicitationField = Type.Unsafe<PumpUp.Field>(fieldSchema);
const ApprovalRecommendationSchema = Type.Unsafe<PumpUp.ApprovalRecommendation>(approvalRecommendationSchema);
const FieldBidSchema = Type.Unsafe<PumpUp.FieldBid>(fieldBidSchema);
const MetadataPatch = Type.Unsafe<PumpUp.MetadataPatchDto>(metadataPatchSchema);

const ApprovalParams = Type.Object({
  projectName: Type.String({ description: "Pump Up project slug" }),
  summary: Type.String({ description: "Human-readable description of what needs approval" }),
  keyValueContext: KeyValueContext,
  recommendation: Type.Optional(ApprovalRecommendationSchema),
  attachments: Type.Optional(Type.Array(AttachmentParam)),
});

const ElicitationParams = Type.Object({
  projectName: Type.String({ description: "Pump Up project slug" }),
  summary: Type.String({ description: "Human-readable description of the input needed" }),
  fields: Type.Array(ElicitationField, { description: "Fields to elicit; each is validated per type server-side" }),
  keyValueContext: KeyValueContext,
  recommendation: Type.Optional(Type.Array(FieldBidSchema)),
  attachments: Type.Optional(Type.Array(AttachmentParam)),
});

/// Fields shared by both task-event tools (action + exception). `detail` is freeform; `transitionsTo`
/// mutates the target task and must match its declared step graph.
const EventTaskFields = {
  detail: DetailContext,
  transitionsTo: Type.Optional(Type.String({ description: "Declared task state to transition into" })),
  externalTraceId: Type.Optional(Type.String({ description: "Links this event to your agent's trace/run id" })),
};

/// Governed-data fields carried only by `action` — the API drops them from `exception` (transition-only):
/// `metadataPatch` mutates the task bag; `attachments` are workspace files attached to the case.
const ActionGovernedFields = {
  metadataPatch: Type.Optional(MetadataPatch),
  attachments: Type.Optional(Type.Array(AttachmentParam)),
};

const RecordActionParams = Type.Object({
  projectName: Type.String({ description: "Pump Up project slug" }),
  description: Type.String({ description: "What the agent did" }),
  ...EventTaskFields,
  ...ActionGovernedFields,
});

const ExceptionParams = Type.Object({
  projectName: Type.String({ description: "Pump Up project slug" }),
  message: Type.String({ description: "What went wrong" }),
  ...EventTaskFields,
});

const NoteParams = Type.Object({
  projectName: Type.String({ description: "Pump Up project slug" }),
  message: Type.String({ description: "The annotation text" }),
  externalTraceId: Type.Optional(Type.String({ description: "Links this event to your agent's trace/run id" })),
});

const GetDecisionParams = Type.Object({
  requestId: Type.String({ description: "The requestId returned by request_approval / request_elicitation" }),
  type: Type.Union([Type.Literal("approval"), Type.Literal("elicitation")], {
    description: "Which kind of request this id refers to",
  }),
});

/// Register the request tools that POST to Pump Up and durably park the wait as a TaskFlow.
export function registerRequestTools(api: OpenClawPluginApi, cfg: PumpUpPluginConfig, client: PumpUpClient): void {
  api.registerTool((ctx) => buildApprovalTool(api, cfg, client, ctx));
  api.registerTool((ctx) => buildElicitationTool(api, cfg, client, ctx));
}

/// Register the fire-and-forget timeline tools plus the one-shot decision read (no flow, no wait).
export function registerCaptureTools(api: OpenClawPluginApi, client: PumpUpClient): void {
  api.registerTool((ctx) => buildRecordActionTool(client, ctx));
  api.registerTool((ctx) => buildReportExceptionTool(client, ctx));
  api.registerTool((ctx) => buildAddNoteTool(client, ctx));
  api.registerTool(() => buildGetDecisionTool(client));
}

/// Register the read-only guide tool — the agent's pull path to the holistic Pump Up usage model.
export function registerGuideTool(api: OpenClawPluginApi): void {
  api.registerTool(() => buildGuideTool());
}

/// Return the Pump Up usage guide (how/when to use the tools, the pending/resume model). Static, no I/O.
function buildGuideTool(): AnyAgentTool {
  return defineTool({
    name: "pumpup_guide",
    label: "Pump Up guide",
    description: "How and when to use the Pump Up tools — read this before your first approval/elicitation.",
    parameters: Type.Object({}),
    execute: async () => jsonResult({ guide: agentGuide }),
  });
}

/// Approval request tool: POST → park flow as waiting → return the pending handle.
function buildApprovalTool(
  api: OpenClawPluginApi,
  cfg: PumpUpPluginConfig,
  client: PumpUpClient,
  ctx: OpenClawPluginToolContext,
): AnyAgentTool {
  return defineTool({
    name: "pumpup_request_approval",
    label: "Request approval",
    description:
      "Request human sign-off in Pump Up. Returns pending, then end your turn — the decision later resumes "
      + "this session (don't poll). New to Pump Up? Call pumpup_guide first.",
    parameters: ApprovalParams,
    execute: async (params) => {
      const taskId = await resolveTaskId(client, params.projectName, ctx);
      const attachments = await attachToTask(client, ctx, params.projectName, taskId, params.attachments);
      const created = await client.approvals.create({
        "Idempotency-Key": randomUUID(),
        projectName: params.projectName,
        summary: params.summary,
        taskId,
        keyValueContext: params.keyValueContext,
        recommendation: params.recommendation,
        attachments: attachments.length > 0 ? attachments : undefined,
      });
      const flowId = parkRequest(api, cfg, "approval", created.eventId, params.summary, ctx);
      return jsonResult({ requestId: created.eventId, flowId, status: "pending" });
    },
  });
}

/// Elicitation request tool: POST agent-declared fields → park flow as waiting → return pending handle.
function buildElicitationTool(
  api: OpenClawPluginApi,
  cfg: PumpUpPluginConfig,
  client: PumpUpClient,
  ctx: OpenClawPluginToolContext,
): AnyAgentTool {
  return defineTool({
    name: "pumpup_request_elicitation",
    label: "Request elicitation",
    description:
      "Ask a human for structured input in Pump Up. Returns pending, then end your turn — the answer later "
      + "resumes this session (don't poll). New to Pump Up? Call pumpup_guide first.",
    parameters: ElicitationParams,
    execute: async (params) => {
      const taskId = await resolveTaskId(client, params.projectName, ctx);
      const attachments = await attachToTask(client, ctx, params.projectName, taskId, params.attachments);
      const created = await client.elicitations.create({
        "Idempotency-Key": randomUUID(),
        projectName: params.projectName,
        summary: params.summary,
        fields: params.fields,
        taskId,
        keyValueContext: params.keyValueContext,
        recommendation: params.recommendation,
        attachments: attachments.length > 0 ? attachments : undefined,
      });
      const flowId = parkRequest(api, cfg, "elicitation", created.eventId, params.summary, ctx);
      return jsonResult({ requestId: created.eventId, flowId, status: "pending" });
    },
  });
}

/// Record autonomous agent activity on the task timeline; may attach files, patch metadata, transition state.
function buildRecordActionTool(client: PumpUpClient, ctx: OpenClawPluginToolContext): AnyAgentTool {
  return defineTool({
    name: "pumpup_record_action",
    label: "Record action",
    description: "Record something the agent did on the Pump Up timeline. Fire-and-forget; returns the event id.",
    parameters: RecordActionParams,
    execute: async (params) => {
      const taskId = await resolveTaskId(client, params.projectName, ctx);
      const addAttachments = await uploadAttachments(client, ctx.workspaceDir, params.attachments);
      const created = await client.events.agentAction({
        "Idempotency-Key": randomUUID(),
        projectName: params.projectName,
        description: params.description,
        taskId,
        detail: params.detail,
        metadataPatch: params.metadataPatch,
        transitionsTo: params.transitionsTo,
        addAttachments: addAttachments.length > 0 ? addAttachments : undefined,
        externalTraceId: params.externalTraceId,
      });
      return jsonResult({ eventId: created.eventId });
    },
  });
}

/// Report something that went wrong; transition-only (no metadata/attachments — those ride `action`).
function buildReportExceptionTool(client: PumpUpClient, ctx: OpenClawPluginToolContext): AnyAgentTool {
  return defineTool({
    name: "pumpup_report_exception",
    label: "Report exception",
    description: "Report an agent error/exception on the Pump Up timeline. Fire-and-forget; returns the event id.",
    parameters: ExceptionParams,
    execute: async (params) => {
      const taskId = await resolveTaskId(client, params.projectName, ctx);
      const created = await client.events.exception({
        "Idempotency-Key": randomUUID(),
        projectName: params.projectName,
        message: params.message,
        taskId,
        detail: params.detail,
        transitionsTo: params.transitionsTo,
        externalTraceId: params.externalTraceId,
      });
      return jsonResult({ eventId: created.eventId });
    },
  });
}

/// Add a freeform annotation to the task timeline (no attachments / state changes).
function buildAddNoteTool(client: PumpUpClient, ctx: OpenClawPluginToolContext): AnyAgentTool {
  return defineTool({
    name: "pumpup_add_note",
    label: "Add note",
    description: "Add a freeform note to the Pump Up timeline. Fire-and-forget; returns the event id.",
    parameters: NoteParams,
    execute: async (params) => {
      const taskId = await resolveTaskId(client, params.projectName, ctx);
      const created = await client.events.note({
        "Idempotency-Key": randomUUID(),
        projectName: params.projectName,
        message: params.message,
        taskId,
        externalTraceId: params.externalTraceId,
      });
      return jsonResult({ eventId: created.eventId });
    },
  });
}

/// One-shot, non-blocking read of a request's decision; 200 = decided payload, 204 = still pending.
function buildGetDecisionTool(client: PumpUpClient): AnyAgentTool {
  return defineTool({
    name: "pumpup_get_decision",
    label: "Get decision",
    description: "Check once whether a Pump Up request has been decided yet. Non-blocking; does not resume.",
    parameters: GetDecisionParams,
    execute: async (params) => {
      const response = params.type === "approval"
        ? await client.approvals.getResult({ id: params.requestId }).withRawResponse()
        : await client.elicitations.getResult({ id: params.requestId }).withRawResponse();
      return response.rawResponse.status === 200
        ? jsonResult({ status: "decided", decision: response.data })
        : jsonResult({ status: "pending" });
    },
  });
}

/// Per-process cache of the auto-created task id per `sessionId` — keyed exactly like the idempotency key
/// (one task per session), so a cache miss after a restart re-resolves to the same task; the cache only
/// spares the repeat round-trip, it isn't the source of truth.
const sessionTasks = new Map<string, string>();

/// Find-or-create this session's one durable task, cached in-process. Keyed by `sessionId` so a roll/`/reset`
/// starts a fresh task — correct while rehydration is deferred (a decision must land in the session that opened
/// it, in the project of first use). The plugin owns the task lifecycle so the agent never handles task ids.
async function resolveTaskId(client: PumpUpClient, projectName: string, ctx: OpenClawPluginToolContext): Promise<string> {
  if (!ctx.sessionId) {
    throw new Error("pumpup: no session to create a task for");
  }
  const cached = sessionTasks.get(ctx.sessionId);
  if (cached) {
    return cached;
  }
  const task = await client.tasks.create({
    "Idempotency-Key": `openclaw-task:${ctx.sessionId}`,
    projectName,
    name: `OpenClaw session ${ctx.sessionKey ?? ctx.sessionId}`,
    externalId: ctx.sessionId,
  });
  sessionTasks.set(ctx.sessionId, task.id);
  return task.id;
}

/// Upload workspace files, attach them to the task via an `action` event, then return their upload ids
/// — the API attaches files only through `action`, and a request renders an already-attached file by id.
async function attachToTask(
  client: PumpUpClient,
  ctx: OpenClawPluginToolContext,
  projectName: string,
  taskId: string,
  inputs: AttachmentInput[] | undefined,
): Promise<string[]> {
  const refs = await uploadAttachments(client, ctx.workspaceDir, inputs);
  if (refs.length === 0) {
    return [];
  }
  await client.events.agentAction({
    "Idempotency-Key": randomUUID(),
    projectName,
    taskId,
    description: `Attached ${refs.length} file(s) for review`,
    addAttachments: refs,
  });
  return refs.map((ref) => ref.uploadId);
}

/// Create a managed TaskFlow for the request and transition it to `waiting` (durable until decided).
function parkRequest(
  api: OpenClawPluginApi,
  cfg: PumpUpPluginConfig,
  type: PumpUpRequestType,
  eventId: string,
  summary: string,
  ctx: OpenClawPluginToolContext,
): string {
  const flow = api.runtime.tasks.managedFlows.bindSession({ sessionKey: cfg.ownerSessionKey });
  const state = buildFlowState(eventId, type, { sessionId: ctx.sessionId, sessionKey: ctx.sessionKey, agentId: ctx.agentId });
  const created = flow.tryCreateManaged({ controllerId: "pumpup", goal: `${type}: ${summary}`, stateJson: state });
  if (!created) {
    throw new Error("pumpup: could not create a TaskFlow for the request");
  }
  const waited = flow.setWaiting({ flowId: created.flowId, expectedRevision: created.revision });
  if (!waited.applied) {
    throw new Error(`pumpup: could not park the request flow as waiting (${waited.code})`);
  }
  return created.flowId;
}

/// Build an agent tool from a TypeBox-typed spec, erasing param types at the registry boundary and
/// mapping any thrown error into a structured tool failure (single choke point for all tools).
function defineTool<S extends TSchema>(spec: {
  name: string;
  label: string;
  description: string;
  parameters: S;
  execute: (params: Static<S>) => Promise<ReturnType<typeof jsonResult>>;
}): AnyAgentTool {
  return {
    name: spec.name,
    label: spec.label,
    description: spec.description,
    parameters: spec.parameters,
    execute: async (_toolCallId: string, params: unknown) => {
      try {
        return await spec.execute(params as Static<S>);
      } catch (error) {
        return toToolFailure(spec.name, error);
      }
    },
  } as AnyAgentTool;
}
