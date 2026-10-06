---
name: pumpup-inbox
description: Use when the user wants to see or work their Pump Up inbox — the runs waiting on a person — or answer an approval or information request from a Pump Up agent.
---

Before anything else, check that the Pump Up tools (pumpup_*) are available. If they are not, stop and tell the user to connect Pump Up: open Customize > Plugins > Pump Up > Connectors, select Connect, sign in with their Pump Up account, then ask again. If they have no account, they can sign up at https://pumpup.com.

# Work the Pump Up inbox

1. Call pumpup_run_list with status=WAITING. Show each run by name with its playbook (pumpup_playbook_list gives the names) and how long it has waited (waitingSince), oldest first, with its inbox link. If none are waiting, say so and stop.
2. When the user picks a run, call pumpup_run_get, then pumpup_request_get for each of its openRequests.
3. Show what the agent is asking and why: the summary, the context, and for an information request the form fields. If pending is false it is already answered: say so and do not ask again. Show the agent's recommendation as a suggestion only.
4. Ask the user for their answer. Submit it only once they have given or confirmed it: pumpup_request_approve for an approval, pumpup_request_provide for an information request. It is recorded as their decision and cannot be changed. A file field cannot be answered here — send them to the inbox link instead.
5. Confirm what was recorded, give the run link, and move on to the next waiting run.
