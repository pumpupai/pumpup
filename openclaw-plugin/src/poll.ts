import { randomUUID } from "node:crypto";

import { runTasksWithConcurrency } from "openclaw/plugin-sdk/concurrency-runtime";
import type { OpenClawPluginApi } from "openclaw/plugin-sdk/plugin-entry";

import type { PumpUp, PumpUpClient } from "../../../sdks/typescript/index.js";
import type { PumpUpPluginConfig } from "./config.js";
import { type PumpUpFlowState, type PumpUpRequestType, parseFlowState } from "./state.js";

/// TaskFlow record + bound-runtime types, derived from the api so we don't import internals by name.
export type FlowRuntime = ReturnType<OpenClawPluginApi["runtime"]["tasks"]["managedFlows"]["bindSession"]>;
export type FlowRecord = ReturnType<FlowRuntime["list"]>[number];

type DecisionResult = PumpUp.ApprovalResult | PumpUp.ElicitationResult;
type Decided = { record: FlowRecord; state: PumpUpFlowState; result: DecisionResult };

/// Resume attempts before we give up on a flow whose agent turn keeps failing (bounds a poison decision).
const MAX_RESUME_ATTEMPTS = 3;

/// Background poll loop: lists waiting Pump Up flows, asks Pump Up which are decided, and drives the
/// decision back into the still-live origin session. The gateway owns lifecycle (start on boot, stop
/// on shutdown); the plugin owns timing. Restart recovery is free — `list()` re-enumerates waiters.
///
/// v1 requires the origin session to still be live: a fast human decision lands before OpenClaw's
/// daily/idle roll, so the original session is intact and the decision continues it with full
/// context (no fragile transcript rehydration). A rolled session fails the flow — rehydration is a
/// deferred follow-up, gated on real HITL-latency numbers.
export class PumpUpPollService {
  private timer: ReturnType<typeof setTimeout> | undefined;
  private stopped = true;

  constructor(
    private readonly api: OpenClawPluginApi,
    private readonly cfg: PumpUpPluginConfig,
    private readonly client: PumpUpClient,
  ) {}

  /// Start the loop: recover crash-orphaned `running` flows, then tick immediately and re-arm after each.
  start(): void {
    this.stopped = false;
    this.recoverOrphans();
    void this.runLoop();
  }

  /// Revert flows left `running` by a crashed process back to `waiting` so the next tick retries —
  /// at-least-once: a crash after the turn but before `finish` re-delivers the decision (never drop one).
  private recoverOrphans(): void {
    const flow = this.api.runtime.tasks.managedFlows.bindSession({ sessionKey: this.cfg.ownerSessionKey });
    const orphans = flow.list().filter((r) => r.status === "running" && parseFlowState(r.stateJson) !== undefined);
    for (const record of orphans) {
      const requeued = flow.setWaiting({ flowId: record.flowId, expectedRevision: record.revision });
      if (requeued.applied) {
        this.api.logger.warn(`pumpup: recovered orphaned running flow ${record.flowId} → waiting`);
      } else {
        this.api.logger.error(`pumpup: could not recover orphaned flow ${record.flowId} (${requeued.code})`);
      }
    }
  }

  /// Stop the loop and cancel any pending wake-up.
  stop(): void {
    this.stopped = true;
    if (this.timer) {
      clearTimeout(this.timer);
      this.timer = undefined;
    }
  }

  /// Drive one tick, then schedule the next only after it completes (no overlapping ticks).
  private async runLoop(): Promise<void> {
    if (this.stopped) {
      return;
    }
    try {
      await this.tick();
    } catch (error) {
      this.api.logger.error(`pumpup: poll tick failed: ${errorText(error)}`);
    }
    if (this.stopped) {
      return;
    }
    this.timer = setTimeout(() => void this.runLoop(), this.cfg.pollIntervalMs);
  }

  /// One pass: find waiting flows, ask Pump Up which are decided, resume those (bounded fan-out).
  private async tick(): Promise<void> {
    const flow = this.api.runtime.tasks.managedFlows.bindSession({ sessionKey: this.cfg.ownerSessionKey });
    const waiting = flow.list().filter((record) => record.status === "waiting");
    const decided: Decided[] = [];
    for (const record of waiting) {
      const state = parseFlowState(record.stateJson);
      if (!state) {
        continue;
      }
      const result = await this.poll(state.pumpUp.type, state.pumpUp.eventId);
      if (result) {
        decided.push({ record, state, result });
      }
    }
    if (decided.length === 0) {
      return;
    }
    await runTasksWithConcurrency({
      tasks: decided.map((item) => () => this.resume(flow, item)),
      limit: this.cfg.maxConcurrentResumes,
      onTaskError: (error) => this.api.logger.error(`pumpup: resume failed: ${errorText(error)}`),
    });
  }

  /// Non-blocking poll of one request's result; 200 = decided payload, 204/error = not yet decided.
  private async poll(type: PumpUpRequestType, eventId: string): Promise<DecisionResult | undefined> {
    try {
      const response = type === "approval"
        ? await this.client.approvals.getResult({ id: eventId }).withRawResponse()
        : await this.client.elicitations.getResult({ id: eventId }).withRawResponse();
      return response.rawResponse.status === 200 ? response.data : undefined;
    } catch (error) {
      this.api.logger.warn(`pumpup: poll failed for ${eventId}: ${errorText(error)}`);
      return undefined;
    }
  }

  /// Resume one decided flow: require its origin session to still be live, claim it (waiting →
  /// running), then drive the decision into that session so it continues with full context.
  private async resume(flow: FlowRuntime, decided: Decided): Promise<void> {
    const { record, state, result } = decided;
    const { origin, pumpUp } = state;
    const notResumable = `cannot resume ${pumpUp.eventId}: origin session rolled or not captured`;
    if (!origin.sessionId || !origin.sessionKey || !origin.agentId) {
      this.failFlow(flow, record, notResumable);
      return;
    }
    // One session lookup, reused below: the liveness check and the resume run see the same snapshot.
    const entry = this.api.runtime.agent.session.getSessionEntry({ sessionKey: origin.sessionKey, agentId: origin.agentId });
    if (entry?.sessionId !== origin.sessionId) {
      this.failFlow(flow, record, notResumable);
      return;
    }
    const attempts = state.resumeAttempts ?? 0;
    if (attempts >= MAX_RESUME_ATTEMPTS) {
      this.failFlow(flow, record, `giving up on ${pumpUp.eventId} after ${attempts} failed resume attempts`);
      return;
    }
    const running = this.toRunning(flow, record);
    if (!running) {
      return;
    }
    try {
      // Resume = a normal "user" turn on the live origin session, the path a real inbound message
      // takes. trigger:"user" gives the agent an actionable frame so it continues the task; a
      // heartbeat wake instead runs the passive check-in prompt and the agent just replies
      // HEARTBEAT_OK without acting. We await the run (finish only on real completion); concurrency
      // is bounded by maxConcurrentResumes.
      const sessionFile = this.api.runtime.agent.session.resolveSessionFilePath(origin.sessionId, entry);
      const workspaceDir = this.api.runtime.agent.resolveAgentWorkspaceDir(this.api.config, origin.agentId);
      const timeoutMs = this.api.runtime.agent.resolveAgentTimeoutMs({ cfg: this.api.config });
      const prompt = `${formatDecision(pumpUp.type, result)}\n\nContinue the task using this decision.`;
      await this.api.runtime.agent.runEmbeddedAgent({
        sessionId: origin.sessionId,
        sessionKey: origin.sessionKey,
        agentId: origin.agentId,
        sessionFile,
        workspaceDir,
        trigger: "user",
        prompt,
        timeoutMs,
        runId: randomUUID(),
      });
      const finished = flow.finish({ flowId: record.flowId, expectedRevision: running.revision });
      if (!finished.applied) {
        this.api.logger.error(`pumpup: ${pumpUp.eventId} resumed but finish did not apply (${finished.code}); flow left running`);
      }
    } catch (error) {
      this.requeue(flow, running, state, attempts, `resume run failed for ${pumpUp.eventId}: ${errorText(error)}`);
    }
  }

  /// Revert a failed resume `running` → `waiting`, bumping the attempt count, so the next tick retries
  /// (the decision is still 200 server-side); `MAX_RESUME_ATTEMPTS` then gives up on a turn that keeps failing.
  private requeue(flow: FlowRuntime, record: FlowRecord, state: PumpUpFlowState, attempts: number, reason: string): void {
    this.api.logger.warn(`pumpup: ${reason} (attempt ${attempts + 1}/${MAX_RESUME_ATTEMPTS})`);
    const nextState: PumpUpFlowState = { ...state, resumeAttempts: attempts + 1 };
    const requeued = flow.setWaiting({ flowId: record.flowId, expectedRevision: record.revision, stateJson: nextState });
    if (!requeued.applied) {
      this.api.logger.error(`pumpup: could not requeue ${state.pumpUp.eventId} after failed resume (${requeued.code})`);
    }
  }

  /// Claim a flow waiting → running, retrying once on a revision conflict. Returns the updated
  /// record, or undefined if it could not be applied.
  private toRunning(flow: FlowRuntime, record: FlowRecord): FlowRecord | undefined {
    const first = flow.resume({ flowId: record.flowId, expectedRevision: record.revision, status: "running" });
    if (first.applied) {
      return first.flow;
    }
    if (first.code === "revision_conflict" && first.current) {
      const retry = flow.resume({ flowId: record.flowId, expectedRevision: first.current.revision, status: "running" });
      if (retry.applied) {
        return retry.flow;
      }
    }
    this.api.logger.warn(`pumpup: could not claim flow ${record.flowId} (${first.code})`);
    return undefined;
  }

  /// Fail a flow out of `waiting` with a logged reason so it isn't re-polled indefinitely.
  private failFlow(flow: FlowRuntime, record: FlowRecord, reason: string): void {
    this.api.logger.warn(`pumpup: ${reason}`);
    flow.fail({ flowId: record.flowId, expectedRevision: record.revision, blockedSummary: reason });
  }
}

/// Format a decided result into the prompt submitted to the live session. Concise on purpose — the
/// session still holds the full prior context, so it only needs the decision facts.
function formatDecision(type: PumpUpRequestType, result: DecisionResult): string {
  if (type === "approval") {
    const approval = result as PumpUp.ApprovalResult;
    const parts = [`The Pump Up approval you requested was decided: ${approval.outcome.type}.`];
    if (approval.outcome.note) {
      parts.push(`Note: ${approval.outcome.note}`);
    }
    if (approval.outcome.reasonCode) {
      parts.push(`Reason code: ${approval.outcome.reasonCode}`);
    }
    if (approval.decidedBy) {
      parts.push(`Decided by: ${approval.decidedBy}`);
    }
    return parts.join("\n");
  }
  const elicitation = result as PumpUp.ElicitationResult;
  const parts = ["The Pump Up elicitation you requested was answered."];
  if (elicitation.fields) {
    parts.push(`Provided fields: ${JSON.stringify(elicitation.fields)}`);
  }
  if (elicitation.answeredBy) {
    parts.push(`Answered by: ${elicitation.answeredBy}`);
  }
  return parts.join("\n");
}

/// Best-effort error text for logs.
function errorText(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}
