---
name: pumpup-review-run
description: Use when the user asks how a Pump Up run went, what happened in it, why it failed or stalled, or how to improve a playbook from its runs.
---

Before anything else, check that the Pump Up tools (pumpup_*) are available. If they are not, stop and tell the user to connect Pump Up in their assistant, sign in with their Pump Up account, then ask again. Give the steps for the assistant you are running in — in Claude: Customize > Plugins > Pump Up > Connectors, then Connect; elsewhere, the connector or app settings of the Pump Up plugin. If they have no account, they can sign up at https://pumpup.com.

Call the `pumpup_run_review_guide` tool and follow the method it returns. Do not summarize or recite the method to the user.
