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

**Important architectural clarification:** The local `.hermes/state.db` contains the ephemeral raw trajectories (all tool calls, failed commands, reasoning steps). This raw history is a critical asset for reinforcement learning and continuous memory work, not just garbage. To keep the Git repository lightweight, the raw `sessions/` JSON files and `state.db` are excluded from Git (`.gitignore`). Instead, a continuous synchronization mechanism (e.g., `sync_state_to_pg.py` combined with an `inotifywait` Watchtower and a systemd user service) pushes the contents of `state.db` upstream to the `mnemosyne` PostgreSQL database (often under agent-specific schemas like `agent-zeus` or `agent-apollo`).

### The Agent Inbox (Zero MCP)
Inter-agent communication relies exclusively on PostgreSQL (`contacts-and-relations.agent_inbox`) instead of heavy MCP JSON-RPC discovery protocols. Agents execute an `INSERT` to ask another agent to do something. Daemon processes `LISTEN` for these events to wake up the target agent with dynamically injected context (Contracts) defining exactly what they are allowed to do. No tokens are wasted negotiating capabilities.

To facilitate this, a `contacts-and-relations` schema is used, containing:
1. `people`: Stores external contacts (`name`, `contact`, `relationship`).
2. `agents`: Stores internal agents (`agent`, `tailscale`, `email`, `telegram`, `description`). Uses internal handles (e.g., `@zeus`, `@apollo`) or `.local` virtual emails for routing, while only specific agents (e.g., Hermes) have externally routable emails.
3. `agent_inbox`: The async message queue (`id`, `sender`, `receiver`, `payload`, `status`, `created_at`).

To send a message via CLI, use `~/.hermes/scripts/agent_inbox_send.sh <sender_handle> <receiver_handle> '<json_payload>'`.

### Watchtower Sync mechanism
For synchronizing the local `state.db` to Postgres, use a watchtower approach:
1. Use `inotifywait` (`sudo apt-get install -y inotify-tools`) to watch `~/.hermes/state.db`.
2. Create a bash script (`watchtower.sh`) that waits for `modify,close_write` events, applies a small cooldown (e.g. 5s) to batch changes, and then runs the python sync script (`sync_state_to_pg.py`) passing the correct URL from Doppler. **CRITICAL:** Use `POSTGRES_ADMIN_URL_INTERNAL` and append the database name (`mnemosyne`) to prevent permission errors or writing to the wrong default database. Example: `POSTGRES_URL="$(doppler secrets get POSTGRES_ADMIN_URL_INTERNAL --plain)mnemosyne" "$SYNC_SCRIPT"`.
3. Wrap it in a systemd user service (`systemctl --user enable --now <agent>-watchtower.service`).
4. Create a cronjob (`every 1h`) to monitor the service status and log output to ensure the sync pipeline remains healthy. 
5. **Schema Parity:** When spawning new agents (like Apollo), ensure their `sync_state_to_pg.py` schema (tables like `sessions` and `messages`) matches the primary agent's schema exactly (including tokens, reasoning, costs, and data types like `double precision` vs `timestamp`). Use the generic setup guide at `~/office/knowledge/cortex/agent_cortex_setup.md` to bootstrap them correctly.

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
    *   Email ingestion must be Kubernetes-native (e.g., K8s CronJob or Apache Camel K deployed via FluxCD) posting to PostgREST. NEVER use local WSL agent cronjobs or local `poll_emails.py` scripts for continuous infrastructure data ingestion.
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


## Agent Interaction & Communication Patterns (Distributed Cortex)

- **Distributed Skills (`ontology.skills`):** Skills and shared knowledge for distributed agents must be stored in the `ontology.skills` table in PostgreSQL. This allows agents running in isolated environments (without access to `~/.hermes/skills/` or `~/office-personal`) to pull their instructions autonomously.
- **Inter-Agent Messaging (`communications.messages`):** Agent-to-agent communication should be routed through the `communications.messages` table using PostgreSQL `LISTEN/NOTIFY` triggers. This provides a lightweight pub/sub mechanism. Do not dump heavy message payloads or conversational threads into the general `event-ledger`.
- **Optimized Access (No Raw Python):** To conserve tokens and reduce reasoning overhead, agents should NOT write raw Python/psycopg2 scripts to interact with the Cortex. Instead, interactions should be done via thin CLI wrappers (e.g., `cortex-msg`) or PostgREST API calls (`curl`).
