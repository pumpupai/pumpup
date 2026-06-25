<div align="center">

# Pump Up

**The operations workspace for AI-augmented teams.**

[![PyPI version](https://img.shields.io/pypi/v/pumpup-sdk?logo=pypi&logoColor=white&label=pip%20install%20pumpup-sdk)](https://pypi.org/project/pumpup-sdk/) [![npm version](https://img.shields.io/npm/v/@pumpupai/pumpup-sdk?logo=npm&logoColor=white&label=npm%20install%20%40pumpupai%2Fpumpup-sdk)](https://www.npmjs.com/package/@pumpupai/pumpup-sdk)<br/>[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](./LICENSE) [![Python versions](https://img.shields.io/pypi/pyversions/pumpup-sdk?logo=python&logoColor=white)](https://pypi.org/project/pumpup-sdk/) [![GitHub stars](https://img.shields.io/github/stars/pumpupai/pumpup?logo=github&logoColor=white&label=stars)](https://github.com/pumpupai/pumpup/stargazers)

[Docs](https://docs.pumpup.com) · [Website](https://pumpup.com) · [Discussions](https://github.com/pumpupai/pumpup/discussions) · [Issues](https://github.com/pumpupai/pumpup/issues)

</div>

---

When you ship an agent into production, it handles most of the work — and then a human still has to approve, route, or decide on the slice it can't. Pump Up is where that handoff lives: **the place agents drop work for humans, and the place humans approve / route / decide.**

It's the control panel for the team that processes the residual 30% of agent work — reviewing, approving, routing, handling exceptions. One coherent surface: **queue → item view → audit log → manager view**. The agent declares the work; we render it beautifully and keep an immutable record of who decided what and why.

We're **agent-agnostic** — run agents from any vendor (or your own) and Pump Up ingests work from all of them.

## What's in this repo

This is the public home for everything a developer wires up to Pump Up:

- **SDKs** — the `pumpup-sdk` clients for **Python** and **TypeScript**.
- **Integrations** — drop-in plugins for the agent frameworks developers actually build on ([`openclaw-plugin`](./openclaw-plugin) and [`hermes-plugin`](./hermes-plugin) today; more driven by where you are).
- **Docs** *(soon)* — guides and the full API reference at [docs.pumpup.com](https://docs.pumpup.com).

> [!NOTE]
> This repo is a **read-only mirror**. The code is authored in an upstream monorepo and synced here automatically — so the history you see is squashed sync commits, not the real development log. See [CONTRIBUTING.md](./CONTRIBUTING.md) for how to get involved (spoiler: Issues and Discussions, not PRs).

## Get started

Install the SDK for your language:

```bash
pip install pumpup-sdk             # Python
npm install @pumpupai/pumpup-sdk   # TypeScript
```

Then drop a human in the loop in about 20 lines — a single call parks the work, routes it to the right person, and hands you back the decision:

```ts
const decision = await pumpup.requestApproval({
  type: "refund_over_threshold",
  context: { customer, amount, agentRecommendation },
  schema,            // the agent declares the shape; we render the item view
  sla: "4h",
  routingHint: { team: "claims" },
  idempotencyKey,    // exactly-once, safe to retry
});
```

The human reviews it in a fast, keyboard-driven item view; your agent gets the answer back. Full walkthrough at [docs.pumpup.com](https://docs.pumpup.com).

### Integrations

Already building on a framework? Skip the wiring:

- **[OpenClaw](./openclaw-plugin)** — request approvals/elicitations and resume your agent when the decision lands.
- **[Hermes](./hermes-plugin)** — request approvals/elicitations and act on the decision back in the original conversation, hours later, with no inbound network access.

More integrations land here as siblings — open a [Discussion](https://github.com/pumpupai/pumpup/discussions) to tell us which framework you want next.

## Community

We'd love to hear from you:

- 🐛 **Found a bug or hit a rough edge?** [Open an issue](https://github.com/pumpupai/pumpup/issues).
- 💡 **Want a feature or a new integration?** [Start a discussion](https://github.com/pumpupai/pumpup/discussions).
- 🔒 **Found a security issue?** See [SECURITY.md](./SECURITY.md) — please report privately.

One thing up front: because the code is authored upstream and mirrored here, **pull requests are turned off on this repo** — there's nowhere for them to land. Issues and Discussions are where the real conversation happens, and we're listening. ❤️

## License

[MIT](./LICENSE)
