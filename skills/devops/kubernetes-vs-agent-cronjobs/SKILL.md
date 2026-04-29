---
name: kubernetes-vs-agent-cronjobs
description: Rules for deciding whether to use the local agent cronjob tool or a Kubernetes native CronJob, and understanding "server-side" terminology.
category: devops
---

# Kubernetes CronJobs vs. Local Agent Cronjobs

When the user mentions running something on the \"server\", \"server-side\", or \"in the server\", they are referring to the **Theseus Kubernetes Cluster**, NOT the local WSL environment where the agent runs.

Do not confuse the agent's local `cronjob` tool with Kubernetes native `CronJob` resources.

## Strict Rule: No Local Scripts for Server-Side Automation
If the user wants a task to run automatically in the background (e.g., polling an API, database sync, email ingestion), **always build a Kubernetes `CronJob` managed via FluxCD (GitOps)**. The user strongly dislikes standalone python/bash scripts or local agent cronjobs for backend infrastructure logic.

### When to use Kubernetes `CronJob` (Always for Infra)
*   **Data Ingestion:** Polling external APIs (like IMAP for emails) and inserting into the database (`mnemosyne`).
*   **Database Syncing:** Synchronizing state between systems.
*   **Backups:** Any data export or backup routine.
*   **Implementation:** Requires creating a Docker image (or using a standard one like `python:3.11-alpine`), mounting a `ConfigMap` for scripts, an `ExternalSecret` for credentials, and a `CronJob` manifest, all committed to `theseus-kubernetes` and reconciled by FluxCD.

## Agent Cronjobs (Local WSL)
Use the agent's `cronjob` tool ONLY for:
- Temporary, cognitive tasks.
- Agent-specific routines (e.g., sending a daily briefing to Telegram, checking the status of local WSL services like `watchtower`).
- Ephemeral reminders or personal assistant functions.

## Kubernetes CronJobs (Server-Side)
Use Kubernetes `CronJob` manifests (committed via GitOps/FluxCD to the `theseus-kubernetes` repository) for:
- **Infrastructure Tasks:** Backups, database pruning, metrics extraction.
- **Data Ingestion Pipelines:** Polling external APIs, IMAP email ingestion, syncing cloud storage.
- **Stateful/Permanent Operations:** Anything that belongs to the system's core architecture and should survive the agent's local machine reboot.

**Rule of Thumb:** If it ingests data into the Database Cortex (like reading emails and pushing to `mnemosyne`), it is an infrastructure task. It MUST run as a K8s CronJob or via Integration as Code (like Apache Camel K), never as a local python script triggered by the agent's internal cron tool.