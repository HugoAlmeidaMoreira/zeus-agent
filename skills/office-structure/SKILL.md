---
name: office-structure
description: Understand the structure and purpose of the ~/office directory (Second Brain and workflows).
---

# Office Structure (Second Brain & Workflows)

The `~/office` directory is the central hub for the "Second Brain" and task workflows.

## Directory Tree and Purposes

*   **journal/**: For checkouts and end-of-session notes.
*   **backlog/**: Task management, synced with Linear concepts.
    *   **drafts/**: Initial ideas and unstructured tasks.
    *   **requisites/**: Refined requirements.
*   **scripts/**: Automation scripts.
*   **devops/adr/**: Architecture Decision Records.
*   **wsl/**: WSL-specific configurations or notes.
*   **inbox/**: General incoming items.

## Medallion Architecture for Documents/Tasks
*   **landing/**: Raw, incoming documents or data.
*   **processed/**: Cleaned and structured data.
*   **transformed/**: Data enriched or combined for specific purposes.
*   **outputs/**: Final deliverables or reports.
*   **workbench/**: Active workspace for ongoing tasks. A low-structure space used for early-stage development of projects or ideas before requirements and final solutions are clear.
*   **archive/**: Completed or deprecated items (Global archive).

## Workbench Iteration & Archiving Workflow
When consolidating or evolving ideas within a `workbench/` topic:
1. **Archiving is NON-DESTRUCTIVE:** Never delete the original source files.
2. **Local Archives:** Move older iterations to a local archive folder within the specific topic directory (e.g., `workbench/<topic>/archive/`), *not* the global `archive/`.
3. **Historical Context:** Add frontmatter to the archived files with `id`, `date`, and `title` to preserve the chronological evolution of the idea.
4. **Consolidation:** Create a new consolidated file at the root of the topic directory (e.g., `workbench/<topic>/<new-consolidated-file>.md`) which serves as the new starting point.