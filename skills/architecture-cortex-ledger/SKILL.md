---
name: architecture-cortex-ledger
description: Architectural specification for the Theseus Database Cortex - the Event Sourcing ledger that replaces static file-based memory with a continuous stream of structured events (emails, file changes, git commits) organized into dynamic Dossiers by asynchronous agents.
version: 1.0.0
author: zeus
license: MIT
metadata:
  hermes:
    tags: [Architecture, Memory, Database, Event-Sourcing, Theseus]
---

# The Theseus Database Cortex (Event Sourcing Ledger)

This specification defines the schema and architectural flow for transforming the agent memory paradigm from static Markdown files (`~/office/`) into a continuous, remote, event-driven PostgreSQL ledger (`mothership`).

## Core Philosophy

As outlined in `01-db-cortex-abstraction.md`, agents do not write static files. They emit a continuous stream of structured exhaust (events). Specialized "Dreaming" agents asynchronously process this timeline, grouping related events into thematic "Dossiers".

Human life (Ph.D., Work, Personal Infrastructure) is a single temporal stream composed of different event types (Emails, Git Commits, Calendar Appointments, File Edits).

## Database Schema (Atlas HCL Target for `mothership`)

### 1. `events` (The Immutable Timeline)
The raw stream of consciousness and external inputs.

*   `id` (UUID, Primary Key)
*   `timestamp` (Timestamptz, Index) - The absolute point in time.
*   `source` (String, Index) - Where the event originated (`hermes_email`, `wsl_inotify`, `github_webhook`, `zeus_execution`, `calendar_sync`).
*   `event_type` (String) - `received`, `created`, `updated`, `deleted`, `completed`.
*   `dossier_id` (UUID, Foreign Key, Nullable, Index) - To which ongoing context does this event belong?
*   `payload` (JSONB) - The fluid cognition. Contains the raw email body, the git diff, the tool output, or the file content.
*   `processed` (Boolean, Default: false) - Has a dreaming agent classified and summarized this event yet?

### 2. `dossiers` (The Dynamic Office / Contexts)
The structured output of asynchronous agent processing. Replaces `~/office/` folders.

*   `id` (UUID, Primary Key)
*   `title` (String) - e.g., "Ph.D. Thesis Writing", "Theseus VIA4 Proxy Setup", "House Mortgage 2026".
*   `status` (String, Index) - `active`, `blocked`, `archived`, `backlog`.
*   `category` (String) - `academic`, `work`, `infrastructure`, `personal`.
*   `summary` (JSONB) - Maintained by Consolidation Agents. Contains the "State of the World", current blockers, key entities, and active risks.
*   `created_at` (Timestamptz)
*   `last_activity_at` (Timestamptz, Index) - Updated whenever a new event is linked.

## The Asynchronous Flow

1.  **Ingestion (The Sensors):**
    *   `poll_emails.py` checks Himalaya and `INSERT INTO events (source='hermes_email', payload='{...}')`.
    *   A local WSL watcher detects a save on `via4-proxy-config.md` and `INSERT INTO events (source='wsl_inotify', payload='{...}')`.
2.  **Processing (The Dreaming Agents / Subconscious):**
    *   A continuous WASM worker or background vLLM script polls `SELECT * FROM events WHERE processed = false`.
    *   The agent reads the JSONB payload.
    *   It queries active dossiers: *Does this email about Traefik belong to the 'Theseus VIA4' dossier?*
    *   It links the event (`UPDATE events SET dossier_id = X, processed = true`).
    *   It updates the dossier's state (`UPDATE dossiers SET summary = new_summary, last_activity_at = NOW()`).
3.  **Retrieval (The Reflex / Context Injection):**
    *   When the user asks Zeus "What's the status of my Ph.D. work?", Zeus doesn't search a massive Obsidian vault.
    *   Zeus fetches `SELECT summary FROM dossiers WHERE title ILIKE '%Ph.D.%'` and `SELECT payload FROM events WHERE dossier_id = X ORDER BY timestamp DESC LIMIT 5`.
    *   Zeus gets a hyper-dense, up-to-date context payload instantly.

## Next Steps for Implementation
1.  Translate the `events` and `dossiers` tables into HCL format in the `theseus-kubernetes/sql/` directory.
2.  Apply the schema using `sync.sh diff` and `sync.sh pull`.
3.  Modify the `poll_emails.py` ear to write directly to the `mothership` PostgreSQL database instead of printing to stdout.
