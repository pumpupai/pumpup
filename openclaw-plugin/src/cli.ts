import type { OpenClawPluginApi } from "openclaw/plugin-sdk/plugin-entry";

import type { PumpUpPluginConfig } from "./config.js";
import type { FlowRecord } from "./poll.js";
import { parseFlowState, type PumpUpFlowState } from "./state.js";

/// The CLI registrar's context (carries the commander `program`), derived from the api by name-free.
type CliContext = Parameters<Parameters<OpenClawPluginApi["registerCli"]>[0]>[0];
type PumpUpFlow = { record: FlowRecord; state: PumpUpFlowState };

/// Register `openclaw pumpup` — a read-only operator view over parked request flows (no backend call).
export function registerOperatorCli(api: OpenClawPluginApi, cfg: PumpUpPluginConfig): void {
  api.registerCli((ctx) => defineCommands(ctx, api, cfg), {
    descriptors: [{ name: "pumpup", description: "Inspect Pump Up request flows", hasSubcommands: true }],
  });
}

/// Wire the `pumpup list` / `pumpup get` subcommands onto the root CLI program.
function defineCommands(ctx: CliContext, api: OpenClawPluginApi, cfg: PumpUpPluginConfig): void {
  const pumpup = ctx.program.command("pumpup").description("Inspect Pump Up request flows");
  pumpup
    .command("list")
    .description("List parked Pump Up request flows (waiting only unless --all)")
    .option("--all", "Include flows in any status")
    .option("--json", "Emit JSON instead of a table")
    .action((opts: { all?: boolean; json?: boolean }) => listFlows(api, cfg, opts));
  pumpup
    .command("get")
    .argument("<flowId>", "Flow id to inspect")
    .description("Show one Pump Up flow by id")
    .action((flowId: string) => getFlow(api, cfg, flowId));
}

/// List our parked flows under the owner session, as a table or JSON.
function listFlows(api: OpenClawPluginApi, cfg: PumpUpPluginConfig, opts: { all?: boolean; json?: boolean }): void {
  const flow = api.runtime.tasks.flow.bindSession({ sessionKey: cfg.ownerSessionKey });
  const rows = collectFlows(flow.list(), opts.all ?? false);
  if (opts.json) {
    console.log(JSON.stringify(rows.map(toJson), null, 2));
    return;
  }
  printTable(rows);
}

/// Show a single flow by id, including its parsed Pump Up state and origin session.
function getFlow(api: OpenClawPluginApi, cfg: PumpUpPluginConfig, flowId: string): void {
  const flow = api.runtime.tasks.flow.bindSession({ sessionKey: cfg.ownerSessionKey });
  const record = flow.get(flowId);
  if (!record) {
    console.error(`No flow ${flowId} under ${cfg.ownerSessionKey}.`);
    process.exitCode = 1;
    return;
  }
  const state = parseFlowState(record.stateJson);
  const view = {
    flowId: record.flowId,
    status: record.status,
    revision: record.revision,
    goal: record.goal,
    pumpUp: state?.pumpUp ?? null,
    origin: state?.origin ?? null,
  };
  console.log(JSON.stringify(view, null, 2));
}

/// Keep only our flows (those with parseable Pump Up state), waiting-only unless `all`.
function collectFlows(records: FlowRecord[], all: boolean): PumpUpFlow[] {
  return records
    .map((record) => ({ record, state: parseFlowState(record.stateJson) }))
    .filter((row): row is PumpUpFlow => row.state !== undefined && (all || row.record.status === "waiting"));
}

/// Flatten a flow to the JSON row shape emitted by `--json`.
function toJson(row: PumpUpFlow) {
  const { record, state } = row;
  return {
    flowId: record.flowId,
    status: record.status,
    type: state.pumpUp.type,
    requestId: state.pumpUp.eventId,
    requestedAt: state.pumpUp.requestedAt,
    origin: state.origin,
  };
}

/// Print the flows as a column-aligned table (or a friendly empty line).
function printTable(rows: PumpUpFlow[]): void {
  if (rows.length === 0) {
    console.log("No Pump Up flows.");
    return;
  }
  const header = ["STATUS", "TYPE", "REQUEST ID", "REQUESTED AT", "FLOW ID"];
  const cells = rows.map(({ record, state }) => [
    record.status,
    state.pumpUp.type,
    state.pumpUp.eventId,
    state.pumpUp.requestedAt,
    record.flowId,
  ]);
  const widths = header.map((label, i) => Math.max(label.length, ...cells.map((cols) => cols[i].length)));
  const line = (cols: string[]) => cols.map((value, i) => value.padEnd(widths[i])).join("  ");
  console.log(line(header));
  for (const cols of cells) {
    console.log(line(cols));
  }
  console.log(`\n${rows.length} flow(s).`);
}
