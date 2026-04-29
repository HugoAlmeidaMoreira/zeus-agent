---
name: flux-image-automation-cicd
description: End-to-end CI/CD pipeline using GitHub Actions (GHCR) and FluxCD Image Automation. Covers common pitfalls with registry permissions, mutable tags, and missing ImageUpdateAutomation.
---

# CI/CD with GitHub Actions + FluxCD Image Automation

## Trigger
Use when:
- GitHub Actions builds the image successfully but FluxCD does not update the cluster deployment.
- The cluster pod is running an old image while CI pushes new ones.
- GHCR push fails with `403 Forbidden` or `repository name must be lowercase`.
- Flux ImagePolicy is configured but the deployment never changes.

## Architecture

```
GitHub Actions ──push──> GHCR ──scan──> ImageRepository ──resolve──> ImagePolicy
                                                                      │
                                                                      ▼
                                                               ImageUpdateAutomation
                                                                      │
                                                                      ▼
                                                               Git commit (new tag)
                                                                      │
                                                                      ▼
                                                               Kustomization ──apply──> Deployment
```

## GitHub Actions (CI)

### Registry Permissions
The `GITHUB_TOKEN` with `packages: write` can **only** push to a GHCR package whose name matches the repository.
- Good: `github.repository` → `hugoalmeidamoreira/vectorized-gestao-clinica`
- Bad: hardcoded `hugoalmeidamoreira/gestao-clinica` when repo is `vectorized-gestao-clinica` → `403 Forbidden`

### Lowercase Requirement
Docker registries require the image name to be lowercase. `github.repository` may contain uppercase letters (e.g. `HugoAlmeidaMoreira/...`).
Always lowercase the image name before tagging:

```yaml
- name: Extract vars
  id: vars
  run: |
    echo "sha=$(git rev-parse --short HEAD)" >> "$GITHUB_OUTPUT"
    echo "image_name=$(echo '${{ github.repository }}' | tr '[:upper:]' '[:lower:]')" >> "$GITHUB_OUTPUT"
    echo "ts=$(date -u +%Y%m%d-%H%M%S)" >> "$GITHUB_OUTPUT"

- name: Build and push
  uses: docker/build-push-action@v5
  with:
    tags: |
      ${{ env.REGISTRY }}/${{ steps.vars.outputs.image_name }}:${{ steps.vars.outputs.ts }}-${{ steps.vars.outputs.sha }}
      ${{ env.REGISTRY }}/${{ steps.vars.outputs.image_name }}:latest
```

### Immutable Tags with Chronological Ordering
**Do NOT use bare git SHAs as Flux ImagePolicy tags.** Git commit SHAs are hexadecimal strings with no chronological ordering. `alphabetical: desc` will select the lexicographically largest SHA, which is effectively random and can pin the cluster to an old image permanently.

Instead, prepend an ISO-like timestamp so alphabetical sort equals chronological sort:

| Tag format | Alphabetical = Chronological? | Example |
|---|---|---|
| `sha-abc1234` | ❌ No | `sha-ffffff0` > `sha-abc1234` even if older |
| `20260425-213810-abc1234` | ✅ Yes | Lexicographic order matches time order |

Always push both the timestamped tag (for Flux) and `latest` (for human convenience).

## FluxCD Image Automation (CD)

Flux needs three objects plus the Deployment annotation:

### 1. ImageRepository
Scans the registry for available tags.

```yaml
apiVersion: image.toolkit.fluxcd.io/v1beta2
kind: ImageRepository
metadata:
  name: my-app
  namespace: my-ns
spec:
  image: ghcr.io/hugoalmeidamoreira/vectorized-gestao-clinica
  interval: 1m0s
  secretRef:
    name: ghcr-pull-secret
```

### 2. ImagePolicy
Selects the tag to deploy. **Never use mutable tags like `latest` as the primary policy.**
The Flux ImagePolicy resolves a tag name; if the tag name never changes (e.g. `latest`), Flux sees no change and will not trigger a rollout, even if the underlying digest changed.

Use immutable tags with a timestamp prefix so alphabetical sort equals chronological sort. Never use bare git SHAs.

```yaml
apiVersion: image.toolkit.fluxcd.io/v1beta2
kind: ImagePolicy
metadata:
  name: my-app
  namespace: my-ns
spec:
  imageRepositoryRef:
    name: my-app
  filterTags:
    pattern: "^[0-9]{8}-[0-9]{6}-[a-f0-9]+$"
    extract: "$0"
  policy:
    alphabetical:
      order: desc
```

### 3. ImageUpdateAutomation
Writes the resolved tag back into the Git repository so that the Kustomization can apply it.
Without this object, the ImagePolicy resolves a tag but nothing updates the Deployment manifest.

```yaml
apiVersion: image.toolkit.fluxcd.io/v1
kind: ImageUpdateAutomation
metadata:
  name: my-app-automation
  namespace: my-ns
spec:
  interval: 1m0s
  sourceRef:
    kind: GitRepository
    name: flux-system
    namespace: flux-system
  git:
    checkout:
      ref:
        branch: master
    commit:
      author:
        email: fluxcdbot@users.noreply.github.com
        name: fluxcdbot
    push:
      branch: master
  update:
    path: ./manifests/tenants/vectorized/base/my-app
    strategy: Setters
```

### 4. Deployment Marker
The Deployment container image line must include the marker comment so Flux knows where to write the new tag:

```yaml
spec:
  template:
    spec:
      containers:
        - image: ghcr.io/hugoalmeidamoreira/vectorized-gestao-clinica:latest # {"$imagepolicy": "vectorized:my-app"}
```

## Verification Commands

### Check the whole chain
```bash
# ImageRepository scan status
flux get images repository -n <ns>

# ImagePolicy resolved tag
flux get images policy -n <ns>

# ImageUpdateAutomation last run
flux get images update -n <ns>

# Deployment current image
kubectl get deployment -n <ns> <name> -o jsonpath='{.spec.template.spec.containers[0].image}'

# Running pods images
kubectl get pods -n <ns> -l app=<name> -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.spec.containers[0].image}{"\n"}{end}'
```

### Forced end-to-end reconcile sequence
Use this when CI has already pushed a new image, but the cluster is still on the old tag and you want to drive the full Flux chain manually instead of waiting for intervals.

```bash
# 1. Re-scan the registry
flux reconcile image repository <name> -n <ns>

# 2. Recompute the policy
flux reconcile image policy <name> -n <ns>

# 3. Trigger image automation to write the GitOps commit
flux reconcile image update <automation-name> -n <ns>

# 4. Verify whether image automation actually pushed a commit
kubectl get imageupdateautomation -n <ns> <automation-name> \
  -o jsonpath='{.status.lastPushCommit}{"\n"}{.status.lastAutomationRunTime}{"\n"}{.status.conditions[-1:].message}{"\n"}'

# 5. Refresh the Flux Git source so the new GitOps commit is fetched
flux reconcile source git flux-system -n flux-system

# 6. Reconcile the target tenant/app kustomization
flux reconcile kustomization <target-kustomization> -n flux-system --with-source

# 7. Confirm rollout
kubectl rollout status deployment/<name> -n <ns> --timeout=180s
kubectl get deployment -n <ns> <name> -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'
```

Notes:
- `ImageUpdateAutomation` may briefly report `repository up-to-date` even after the ImagePolicy has advanced; check its logs and `lastPushCommit` before assuming nothing changed.
- The deployment does not update until the GitRepository source and the relevant Kustomization have both reconciled to the new GitOps commit.
- Useful log command:
```bash
flux logs --kind=ImageUpdateAutomation --name=<automation-name> -n <ns> --since=30m
```

### Check Flux logs for image automation
```bash
flux logs --level=info --name=my-app-automation -n <ns>
```

## Troubleshooting

### Symptom: CI passes but cluster stays on old image
1. Verify `ImageRepository` is scanning the correct image URL.
2. Verify `ImagePolicy` is resolving the expected tag (not stuck on `latest`).
3. Verify `ImageUpdateAutomation` exists and has `READY=True`.
4. Verify the Deployment has the `# {"$imagepolicy": ...}` marker.
5. Check if the Kustomization is blocked by upstream dependencies:
   ```bash
   flux get kustomizations
   ```
   If `dependency 'flux-system/<upstream>' is not ready`, reconcile upstream first:
   ```bash
   flux reconcile kustomization <upstream>
   flux reconcile kustomization <target>
   ```

### Symptom: GHCR push returns 403
The image name does not match the repository. Ensure `IMAGE_NAME` is derived from `github.repository` (lowercased).

### Symptom: GHCR push returns "repository name must be lowercase"
The owner or repo name contains uppercase letters. Lowercase the full image name with `tr '[:upper:]' '[:lower:]'` before tagging.

### Symptom: ImagePolicy resolves an old tag while newer builds exist
**Root cause 1 — Tag format lacks chronological ordering.** If using bare git SHAs (`sha-abc1234`), `alphabetical: desc` picks the lexicographically largest SHA, which is not the most recent commit.
**Fix:** Change the GitHub Actions workflow to emit timestamp-prefixed tags (`YYYYMMDD-HHMMSS-<short-sha>`) and update the ImagePolicy `filterTags.pattern` to match.

**Root cause 2 — GHCR pagination in FluxCD image-reflector-controller.** GHCR may host hundreds of image versions. FluxCD's image-reflector-controller (observed in v1.0.4) appears to read only the first page of tags. If that page is saturated with old tags (e.g. bare `sha-XXXXXXX` tags), newer `timestamp-sha` tags never appear in `lastScanResult.latestTags`, so the ImagePolicy stays pinned to the newest tag it *can* see.

**Diagnose:**
```bash
# Check how many tags Flux sees vs how many exist in GHCR
kubectl get imagerepository -n <ns> <name> -o jsonpath='{.status.lastScanResult.tagCount}{"\n"}'
# If this number is suspiciously low and never grows (e.g. stuck at 31 while GHCR has 77 versions),
# pagination is the likely culprit.

# Check the actual latestTags Flux sees
kubectl get imagerepository -n <ns> <name> -o jsonpath='{.status.lastScanResult.latestTags}' | jq .
# If the list only contains old tags and none from today's builds, pagination is confirmed.
```

**Fix options:**
1. **Clean up old tags** via GitHub API to bring the total below the pagination threshold (~30–50), so newer tags enter the first page. Requires `delete:packages` scope on the PAT.
2. **Disable ImagePolicy/ImageUpdateAutomation** for this app and switch to manual tag bumps in the GitOps repo (commit the exact tag, remove the `# {"$imagepolicy": ...}` marker, or delete the ImagePolicy/ImageUpdateAutomation objects).
3. **Switch to semantic versioning** — this is the industry-standard solution and eliminates the problem entirely.

**Warning about manual bumps:** If ImageUpdateAutomation is still active, it will detect that the Deployment marker does not match the ImagePolicy's resolved tag and will commit a revert. Either disable the automation or align the ImagePolicy so it resolves the tag you want.

---

## The Industry-Standard Solution: Semantic Versioning

If you are building continuously (e.g. agents committing to `main`), timestamp-sha tags accumulate indefinitely and eventually break FluxCD pagination. **Semantic versioning (`1.2.3`) is the correct long-term fix.**

### Why semver wins
- FluxCD's `semver` policy is deterministic and does not depend on tag count or pagination.
- Tags are human-readable and communicate change magnitude (`1.0.37` vs `20260426-072625-a6f0868`).
- Git tags (`v1.0.37`) provide traceability in the repo history.
- No tag accumulation — each release bumps the version, old tags can be left in place.

### GitHub Actions (semver variant)

```yaml
name: Build and Push Docker Image

on:
  push:
    branches: [main]
  workflow_dispatch:

env:
  REGISTRY: ghcr

jobs:
  build-and-push:
    runs-on: ubuntu-latest
    permissions:
      contents: write      # Required to push git tags
      packages: write

    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0   # Required for git tag push

      - uses: docker/setup-buildx-action@v3
      - uses: docker/login-action@v3
        with:
          registry: ${{ env.REGISTRY }}.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - id: version
        run: |
          MAJOR=1
          MINOR=0
          PATCH=${{ github.run_number }}
          VERSION="${MAJOR}.${MINOR}.${PATCH}"
          echo "version=$VERSION" >> "$GITHUB_OUTPUT"
          echo "image_name=$(echo '${{ github.repository }}' | tr '[:upper:]' '[:lower:]')" >> "$GITHUB_OUTPUT"
          echo "sha=$(git rev-parse --short HEAD)" >> "$GITHUB_OUTPUT"

      - uses: docker/build-push-action@v5
        with:
          context: .
          push: true
          tags: |
            ${{ env.REGISTRY }}.io/${{ steps.version.outputs.image_name }}:${{ steps.version.outputs.version }}
            ${{ env.REGISTRY }}.io/${{ steps.version.outputs.image_name }}:latest
          build-args: |
            APP_BUILD_SHA=${{ steps.version.outputs.sha }}
            APP_BUILD_VERSION=${{ steps.version.outputs.version }}
          cache-from: type=gha
          cache-to: type=gha,mode=max

      - name: Create Git tag
        run: |
          git config user.name "github-actions"
          git config user.email "github-actions@github.com"
          git tag -a "v${{ steps.version.outputs.version }}" -m "Release v${{ steps.version.outputs.version }}"
          git push origin "v${{ steps.version.outputs.version }}"
```

### FluxCD (semver variant)

**ImageRepository** — slower interval is fine because semver does not change unpredictably:
```yaml
apiVersion: image.toolkit.fluxcd.io/v1beta2
kind: ImageRepository
metadata:
  name: my-app
  namespace: my-ns
spec:
  image: ghcr.io/hugoalmeidamoreira/vectorized-gestao-clinica
  interval: 5m0s          # Was 1m; slower is fine for semver
  secretRef:
    name: ghcr-pull-secret
```

**ImagePolicy** — `semver` instead of `alphabetical`:
```yaml
apiVersion: image.toolkit.fluxcd.io/v1beta2
kind: ImagePolicy
metadata:
  name: my-app
  namespace: my-ns
spec:
  imageRepositoryRef:
    name: my-app
  policy:
    semver:
      range: ">=1.0.0"   # Accept any 1.x.y or higher
```

**Deployment** — reset to baseline semver tag; FluxCD will manage bumps:
```yaml
spec:
  template:
    spec:
      containers:
        - image: ghcr.io/hugoalmeidamoreira/vectorized-gestao-clinica:1.0.0 # {"$imagepolicy": "vectorized:my-app"}
```

**ImageUpdateAutomation** — unchanged:
```yaml
apiVersion: image.toolkit.fluxcd.io/v1
kind: ImageUpdateAutomation
metadata:
  name: my-app-automation
  namespace: my-ns
spec:
  interval: 1m0s
  sourceRef:
    kind: GitRepository
    name: flux-system
    namespace: flux-system
  git:
    checkout:
      ref:
        branch: master
    commit:
      author:
        email: fluxcdbot@users.noreply.github.com
        name: fluxcdbot
    push:
      branch: master
  update:
    path: ./manifests/tenants/vectorized/base/my-app
    strategy: Setters
```

### Result
1. Every `git push` to `main` triggers a build with tag `1.0.RUN_NUMBER`.
2. The GitHub Actions workflow also creates a git tag `v1.0.RUN_NUMBER` for traceability.
3. FluxCD image-reflector scans GHCR, sees the new semver tag, and the ImagePolicy resolves it.
4. ImageUpdateAutomation commits the new tag to the GitOps repo.
5. Kustomization applies the updated Deployment automatically.
6. **Agents never need to manually review or bump the deployment image again.**


### Symptom: Kustomization never applies even after ImageUpdateAutomation pushes commits
The target Kustomization may have a `dependsOn` that is stuck. Check the full dependency chain:
```bash
flux get kustomizations
```
If any upstream dependency shows `False`, reconcile it first, then the target:
```bash
flux reconcile kustomization <upstream>
flux reconcile kustomization <target>
```
Common chain: `tenant-*` → `infrastructure-postgres` → `infrastructure-external-secrets-stores`.
