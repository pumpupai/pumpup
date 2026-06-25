import { definePluginEntry } from "openclaw/plugin-sdk/plugin-entry";

import { registerOperatorCli } from "./cli.js";
import { buildClient } from "./client.js";
import { readConfig } from "./config.js";
import { PumpUpPollService } from "./poll.js";
import { registerCaptureTools, registerGuideTool, registerRequestTools } from "./tools.js";

/// Pump Up × OpenClaw plugin entry. Wires config + the SDK client + request tools + the
/// poll/resume service that drives decided requests back into their live agent session.
export default definePluginEntry({
  id: "pumpup",
  name: "Pump Up",
  description: "Request human approvals/elicitations from Pump Up and resume agent work on the decision.",
  register: (api) => {
    const cfg = readConfig(api);
    const client = buildClient(cfg, api.config);
    registerRequestTools(api, cfg, client);
    registerCaptureTools(api, client);
    registerGuideTool(api);
    registerOperatorCli(api, cfg);
    const poll = new PumpUpPollService(api, cfg, client);
    api.registerService({ id: "pumpup-poll", start: () => poll.start(), stop: () => poll.stop() });
    api.logger.info(
      `pumpup: ready (baseUrl=${cfg.baseUrl}, ownerSessionKey=${cfg.ownerSessionKey}, pollIntervalMs=${cfg.pollIntervalMs})`,
    );
  },
});
