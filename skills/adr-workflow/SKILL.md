---
name: adr-workflow
description: Workflow and template for creating Architecture Decision Records (ADRs), specifically tailored for the Theseus Kubernetes cluster.
---

# ADR Workflow (Theseus & DevOps)

This skill defines the process for documenting architectural, infrastructure, and configuration decisions, especially those related to the Kubernetes cluster managed by **Theseus**, but applicable to any major system decision.

## Storage Location
All ADRs must be saved in the Second Brain at:
`~/office/devops/adr/`

## Naming Convention
Files must be named sequentially using a 4-digit number and kebab-case:
`NNNN-short-title-of-decision.md`
*(Example: `0001-use-cilium-for-cni.md`, `0002-adopt-gitops-with-argocd.md`)*

## When to use this skill
- When introducing a new tool, operator, or framework to the K8s cluster.
- When making a significant change to network topology, security, or storage.
- When defining a new internal standard or convention.
- When the user (Hugo) asks explicitly to "write an ADR" or "document this decision".

## Pitfalls & Important Guidelines
- **Do not create ADRs prematurely:** If an architectural idea, database schema, or workflow is still being brainstormed, sketched, or explored, do **not** create an ADR. Drafts and early sketches belong in `~/office/workbench/`. Only formally document an ADR when the decision is solid and ready to be accepted.

## ADR Template

When creating a new ADR, use the following Markdown structure:

```markdown
# ADR [NNNN]: [Title of the Decision]

**Date:** YYYY-MM-DD
**Status:** [Proposed | Accepted | Deprecated | Superseded]
**Author(s):** Hugo / Theseus / Zeus

## Context
What is the problem or situation that requires a decision? What are the constraints, assumptions, and alternatives considered? Keep it objective and factual.

## Decision
What is the specific choice we are making? (e.g., "We will use ArgoCD for GitOps instead of Flux"). Be clear and direct.

## Consequences
What happens because of this decision?
- **Positive:** (What becomes easier, faster, or more secure?)
- **Negative:** (What becomes harder, what tech debt is introduced, what maintenance is required?)
- **Neutral:** (What just changes without being inherently good or bad?)
```

## Execution Steps for Agents
1. **Check existing:** Run `ls ~/office/devops/adr/` to find the highest existing ADR number.
2. **Increment:** Determine the next available `NNNN` number.
3. **Draft:** Generate the content using the template above.
4. **Save:** Write the file to `~/office/devops/adr/NNNN-title.md`.
5. **Report:** Confirm to the user that the ADR was created and provide a brief summary of the decision recorded.