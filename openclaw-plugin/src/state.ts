/// Durable TaskFlow state for a parked Pump Up request. `pumpUp.eventId` is the poll handle;
/// `origin` locates the live agent session the decision resumes (rolled-origin rehydration is deferred).
/// Fields use `null` (not optional) so the value is assignable to the strict TaskFlow `JsonValue`.
export type PumpUpRequestType = "approval" | "elicitation";

export type PumpUpOrigin = {
  sessionId: string | null;
  sessionKey: string | null;
  agentId: string | null;
};

export type PumpUpFlowState = {
  pumpUp: { eventId: string; type: PumpUpRequestType; requestedAt: string };
  origin: PumpUpOrigin;
  /// Failed resume attempts so far; a transient resume requeues and bumps this, capped to bound a poison turn.
  resumeAttempts: number;
};

/// Build the stateJson persisted on a parked request flow, normalising absent origin ids to null.
export function buildFlowState(
  eventId: string,
  type: PumpUpRequestType,
  origin: { sessionId?: string; sessionKey?: string; agentId?: string },
): PumpUpFlowState {
  return {
    pumpUp: { eventId, type, requestedAt: new Date().toISOString() },
    origin: {
      sessionId: origin.sessionId ?? null,
      sessionKey: origin.sessionKey ?? null,
      agentId: origin.agentId ?? null,
    },
    resumeAttempts: 0,
  };
}

/// Tolerantly parse a flow's stored stateJson back into our shape — undefined if it isn't ours.
export function parseFlowState(stateJson: unknown): PumpUpFlowState | undefined {
  if (!stateJson || typeof stateJson !== "object") {
    return undefined;
  }
  const candidate = stateJson as { pumpUp?: { eventId?: unknown; type?: unknown } };
  const pumpUp = candidate.pumpUp;
  if (!pumpUp || typeof pumpUp.eventId !== "string" || (pumpUp.type !== "approval" && pumpUp.type !== "elicitation")) {
    return undefined;
  }
  return stateJson as PumpUpFlowState;
}
