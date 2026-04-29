---
name: gitops-manifest-audit
description: >
  Systematically audit an existing FluxCD GitOps repo before onboarding or
  reviving an app. Prevents duplicate ImageRepositories, conflicting policies,
  and orphaned resources by inspecting current tree state, not just git history.
version: 1.0.0
author: Zeus
---

# GitOps Manifest Audit

Use this skill whenever you need to add, revive, or migrate an app into a
FluxCD GitOps repository (especially in decoupled repo architectures where
app source and K8s manifests live separately).

## Trigger

- User says they "removed" or "moved" an app and need to recreate CI/CD.
- User wants to add a new app to an existing GitOps setup.
- User asks about missing manifests, ingress, or image automation.

## Audit Steps

1. **Check current tree — not just git history**
   - `git ls-tree -r --name-only HEAD | grep <app-name>`
   - Manifests may still exist (e.g., scaled to `replicas: 0`, or referenced
     in a Kustomization that was never cleaned up).

2. **Inspect tenant/namespace structure**
   - Find the Kustomization that reconciles the tenant:
     `grep -r "tenant-<name>" manifests/admin/`
   - Read the tenant's `base/kustomization.yaml` and `overlays/prod/` to
     understand the resource inclusion path.

3. **Look for cluster-wide automation resources**
   - Check if `ImageUpdateAutomation` exists:
     `manifests/admin/flux-system/image-update-automation.yaml`
   - If it exists, note its `update.path` scope (e.g., `./` means it scans
     the entire repo).

4. **Verify existing ImageRepository and ImagePolicy**
   - Search for existing `ImageRepository` or `ImagePolicy` targeting the
     app's image.
   - Check the policy's `filterTags.pattern` — if it uses `"latest"`,
     consider whether SHA-based or semver tagging is more appropriate for
     traceability.

5. **Read all app manifests in dependency order**
   - ExternalSecret (or Secret)
   - Deployment (check `replicas`, image tag, resource limits, probes)
   - Service
   - Ingress (check `host`, TLS block, annotations)
   - Any ImageRepository / ImagePolicy

6. **Identify gaps**
   - Missing TLS on Ingress?
   - Deployment scaled to zero?
   - ImagePolicy matching wrong tag strategy?
   - Missing `dependsOn` in tenant Kustomization?

## Common Pitfalls

- **Assuming "removed" means gone:** In GitOps repos, manifests are often
  left in place with `replicas: 0` instead of being deleted.
- **Creating duplicate ImageUpdateAutomation:** Most clusters only need one
  cluster-wide automation resource.
- **Overwriting existing secrets:** If an `ExternalSecret` already exists,
  verify its `remoteRef` paths before assuming they need to change.

## Decision Tree

```
Manifests still exist?
  ├── YES → Read them. Identify what's dormant vs missing.
  │         Update in place (replicas, TLS, image tag strategy).
  └── NO  → Check templates/ or scaffold new manifests.
            Verify cluster-wide automation exists before creating
            a new ImageUpdateAutomation.
```

## Verification

After any changes, confirm:
- `flux get kustomizations` shows the tenant is reconciled.
- `flux get images all` shows the ImagePolicy reflects the desired tag.
- The ImageUpdateAutomation has made commits (if enabled).
