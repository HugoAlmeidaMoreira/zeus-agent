---
name: gitops-workload-refactoring
description: Safe practices for refactoring/renaming K8s workloads in GitOps, especially handling PVCs, Multi-doc YAMLs, and CRD versions.
---
# GitOps Workload Refactoring & Renaming

When renaming or refactoring applications managed by GitOps (e.g., FluxCD), you must avoid destructive side effects to Persistent Volumes, YAML formatting, and API versions.

## 1. Renaming Stateful Workloads (PVCs)
**Pitfall:** Renaming a Deployment and its `PersistentVolumeClaim` (PVC) will cause the new pod to hang in `Pending` with `unbound immediate PersistentVolumeClaims`. K8s creates a fresh PVC which has no data and may fail to bind. The old PV remains bound to the old (now deleted) PVC.
**Solution:**
- **Option A (Safest):** Rename the Deployment, but **keep the old `claimName`** in the `volumes` section. Do not rename the PVC manifest.
- **Option B (Data Migration):** If you MUST rename the PVC, create the new PVC, scale down the workload, run a Job/temporary pod to `rsync` data from the old PVC to the new PVC, then update the deployment to use the new PVC, and finally delete the old PVC.
- **Option C (Data Destruction / Re-binding):** If the data is ephemeral or you don't care about destroying the old volume entirely, you can delete the old PVC. However, if the old PV's Reclaim Policy is Retain, the PV will stay `Released` and won't bind to the new PVC even if capacities match, because it still holds a `claimRef` to the old PVC UID. To force a released PV to bind to a new PVC (if you wiped it or don't care), patch the PV to remove the `claimRef`:
  ```bash
  kubectl patch pv <pv-name> -p '{"spec":{"claimRef": null}}'
  ```

## 2. Multi-Document YAML Formatting
**Pitfall:** Editing multi-document YAMLs (e.g., Kustomization lists separated by `---`) using `sed`, `awk`, or bash string replacement often breaks real newlines (replacing them with literal `\n`), causing Flux to fail with `invalid document separator: ---`.
**Solution:**
- Use the agent's `patch` tool or a Python script with proper multiline strings via `execute_code`.
- Never use `sed -i` for complex multi-line YAML injection or replacing text that spans documents.
- If a YAML file gets corrupted with literal `\n`, fix it using `perl -pi -e 's/\\n/\n/g' file.yaml`.

## 3. Verifying CRD API Versions
**Pitfall:** Creating manifests (like `ExternalSecret`) using generic templates or assumptions might use outdated or unsupported API versions (e.g., `v1beta1` instead of `v1`), causing GitOps reconciliation to fail with `no matches for kind`.
**Solution:**
Always verify the supported API versions on the cluster before creating CRD instances:
```bash
kubectl get crd externalsecrets.external-secrets.io -o jsonpath='{.spec.versions[*].name}'
```