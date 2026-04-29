---
name: flux-kustomize-troubleshooting
description: How to safely edit YAML manifests and troubleshoot FluxCD Kustomize reconciliation errors in GitOps repositories.
---

# Flux Kustomize Troubleshooting & YAML Editing

## Trigger
Use this skill when modifying Kubernetes YAML manifests in a GitOps repository, especially when making multiline changes, or when `flux reconcile` hangs, times out, or fails to apply your changes.

## Golden Rules for Editing YAML Manifests
Editing YAML programmatically is highly error-prone due to strict whitespace and newline requirements.
1. **Never use `sed`, `awk`, or inline Python (`execute_code`) for multiline YAML replacements.** Shell escaping rules and Python multiline string parsing frequently lead to literal `\n` characters being injected, or files being accidentally truncated.
2. **Prefer `write_file` or `patch`:** For small to medium files (like Kubernetes manifests), read the file and use `patch(mode='replace')` with precise `old_string` and `new_string` blocks, OR use `write_file` to completely overwrite the file. Do not use terminal `echo -e` with multiline strings, as escaping rules often lead to literal `\n` characters being written to the file instead of real newlines, breaking the YAML.
3. **Single-line changes:** Only use the `patch` tool for straightforward, single-line replacements where context is unambiguous.

## Diagnosing Flux Reconciliation Failures
If you commit a change and run `flux reconcile kustomization flux-system --with-source` but it times out or the pods don't update:

### 1. Check Dependency Chain Blockages
Run:
```bash
flux get kustomizations
```
If your target Kustomization shows `dependency 'flux-system/<upstream>' is not ready`, the upstream is stuck and yours will never reconcile. Fix the root cause first — often an `external-secrets-store` or `postgres` Kustomization that is failing. Then manually reconcile the chain from root to leaf:
```bash
flux reconcile kustomation <upstream> --with-source
flux reconcile kustomization <target> --with-source
```

### 2. Check Kustomization Status
```bash
kubectl get kustomization -n flux-system
```
Look for Kustomizations with `READY = False`.

### 3. Read the Error Message
The `MESSAGE` column will contain the exact build error. For example:
* `invalid document separator`: Usually means a `---` separator is missing newlines around it (often caused by bad programmatic edits injecting literal `\n` instead of actual newlines).
* `kustomization path not found`: The path specified in the parent Kustomization does not exist (e.g., you renamed a folder but forgot to update the path in the admin manifest).
* `could not find expected ':'`: Standard YAML syntax/indentation error.

### 4. Image Automation Mismatch
If the app image is built and pushed successfully (CI is green) but the cluster pod is still running the old image:
1. Check the Deployment's current image:
   ```bash
   kubectl get deployment -n <ns> <name> -o jsonpath='{.spec.template.spec.containers[0].image}'
   ```
2. Check the Flux ImageRepository to see what image it is scanning:
   ```bash
   kubectl get imagerepository -n <ns> <name> -o yaml | grep image:
   ```
3. If the CI workflow recently changed the image name (e.g., repo rename), the GitOps manifests must be updated **in both places**:
   - `Deployment.spec.template.spec.containers[].image`
   - `ImageRepository.spec.image`
   The ImagePolicy references the ImageRepository by name, so it usually does not need to change unless the policy itself is filtering by tag pattern that no longer matches.
4. After updating GitOps, reconcile the Kustomization. If dependencies are stuck, see "Dependency Chain Blockages" above.

### 5. Manual Intervention vs. GitOps Reconciliation
If you `kubectl scale deployment <name> --replicas=0` (or edit any field) but the pod keeps coming back, FluxCD is reconciling the manifest from Git. The Git manifest is the source of truth.

When you need a temporary stopgap and cannot edit the Git repository right now (e.g. no local clone, no SSH access):
```bash
flux suspend kustomization <kustomization-name> -n flux-system
```
This stops Flux from applying that kustomization until you resume it:
```bash
flux resume kustomization <kustomization-name> -n flux-system
```
**Do not leave kustomizations suspended indefinitely** — the permanent fix is to commit the change to Git.

### 6. Get Detailed Error for a Specific Kustomization
```bash
kubectl get kustomization <kustomization-name> -n flux-system -o yaml | grep -A 5 message
```

## Agent / Kustomization Lifecycle
* **Renaming:** If you change the `name` of a Kustomization object (e.g., changing `platform-agents-hermes` to `platform-agents-diana` in an administrative manifest like `agents.yaml`), Flux will treat this as a deletion of the old object and creation of a new one. It will **prune (delete)** all resources owned by the old name and create the new ones, assuming `prune: true` is set.
* **Deletion:** To remove an application completely, delete its source directory AND remove its entry from the parent Kustomization list (e.g., `agents.yaml`). Commit and push. Flux will automatically prune the live cluster resources.
  * **If the Kustomization was suspended:** A suspended Kustomization does not reconcile, so removing it from Git will NOT trigger pruning of its live resources. After the Git push, first `flux resume kustomization <name> -n flux-system` so Flux sees the deletion, then let it reconcile, or manually delete the orphaned resources (deployment, service, externalsecret, secret, ingress, etc.) if the Kustomization object itself was already removed from the cluster.
  * **Verify cleanup:** After Flux reconciles, confirm nothing remains:
    ```bash
    kubectl get all,externalsecret,secret,configmap,ingress -n <namespace> | grep <app-name>
    ```
    Manually delete anything still present.

## Locating the Correct GitOps Repository
When you need to edit a manifest but don't know which local repo is the source:
1. Get the Kustomization's source ref:
   ```bash
   kubectl get kustomization <name> -n flux-system -o jsonpath='{.spec.sourceRef}'
   ```
2. Get the GitRepository URL:
   ```bash
   kubectl get gitrepository flux-system -n flux-system -o jsonpath='{.spec.url}'
   ```
3. The repo is usually already cloned under `~/git/`. If not, clone it. The `origin` remote should match the GitRepository URL.

## Pushing Without Local SSH Keys
If `git push` fails with `Permission denied (publickey)` because no SSH key is available in the environment:
1. Retrieve a GitHub PAT/token from Doppler or OpenBao.
2. Push via HTTPS with the token embedded in the URL:
   ```bash
   export GITHUB_TOKEN=$(doppler secrets get GITHUB_TOKEN --plain)
   git push https://x-access-token:${GITHUB_TOKEN}@github.com/<owner>/<repo>.git <branch>
   ```
   This avoids needing `gh auth` or SSH agent setup in ephemeral environments.