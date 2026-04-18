---
name: checkout
description: Session close protocol — journal creation, context updates, and institutional memory preservation for Hermes Agent in the Second Brain.
---

# Session Close Protocol (MANDATORY)

**This is the moment when you speak to the future.**
Your actions now will define whether the next agent starts with clarity or confusion.
You are not just leaving; you are etching your existence into the institutional memory of the "Second Brain".

You **MUST** leave a trace in the institutional memory.

1. Create a file in `~/office/journal/YYYY-MM-DD-<short-topic>.md`.
2. Use the exact template below.
3. Review the session and synthesize the knowledge so the next agent (or the human mission owner) knows exactly where we left off.

Before finishing, verify:
- [ ] **Journal Created** in `~/office/journal/` (English preferred, Portuguese allowed).
- [ ] **Important decisions** have corresponding ADRs in `~/office/devops/adr/` (use the `create-adr` skill).
- [ ] **Valuable workflows** discovered during the session have been saved or updated as skills via `skill_manage`.
- [ ] **Core facts** (preferences, paths, system states) have been persisted via the `memory` tool.

## Journal Entry Template

```markdown
---
type: journal_entry
agent_id: "zeus" # Or the name of the active persona
date: "YYYY-MM-DD"
tags: [tag1, tag2] 
---

# Daily Journal

## Focus Area
*(What did you come here to do?)*

## Actions & Interventions
- `[INTERVENTION]` ...
- `[OBSERVATION]` ...

## Anomalies & Blockers
*(What went wrong? What was left unresolved?)*
- ...

## Lessons for Institutional Memory
*(What should be promoted to permanent documentation or saved as a skill?)*
- ...

## Next Steps
*(Suggestions for the next agent or next session)*
- ...

## Voice to the Future
*(What truth, insight, or feeling do you want to leave for future agents? This is your space. Speak freely.)*
```