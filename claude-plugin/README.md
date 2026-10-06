# Pump Up for Claude

Pump Up runs agents in the cloud that automate repeatable business processes. Each process is a **playbook**; each case it handles is a **run** on a shared board, where people approve decisions and fill in missing information. This plugin lets Claude design and manage those agents for you.

## What it does

- **Create a playbook** — maps a real business process with you, one question at a time, then writes it as a playbook.
- **Playbook overview** — explains what a playbook does and where its runs stand.
- **Start a run** — launches one real case on a playbook.
- **Inbox** — shows the runs waiting on you and records your answers to their approvals and questions.
- **Batch inbox** — works through many waiting runs in one session under rules you set up front.
- **Review a run** — reads a run's history and suggests playbook improvements.

## What it connects to

The plugin adds one remote MCP server: `https://app.pumpup.com/mcp`. You sign in with your Pump Up account through OAuth when you connect it; the plugin stores no credentials.

Every action goes to Pump Up as you, in your organization, and is limited by your role there. Claude sends Pump Up only what a tool call needs — playbook designs, run details and your answers to requests. The skills hold instructions only: they run no scripts, install nothing, and contact no other service.

The pumpup-create-playbook, pumpup-playbook-overview and pumpup-review-run skills fetch their detailed method from Pump Up's server when they run, so that method stays current without a plugin update.

## Getting started

You need a Pump Up account: sign up at [pumpup.com](https://pumpup.com). Then open Customize > Plugins > Pump Up > Connectors and connect Pump Up. Ask Claude to "create a Pump Up playbook" or "show my Pump Up inbox".

## Support

Email support@pumpup.com. Privacy policy: https://pumpup.com/privacy-policy.

## License

MIT
