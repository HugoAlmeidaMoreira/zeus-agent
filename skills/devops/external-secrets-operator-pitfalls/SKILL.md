---
name: external-secrets-operator-pitfalls
description: Troubleshooting External Secrets Operator crash loops, API version mismatches, and Vault pathing.
---

# External Secrets Operator Pitfalls

## Trigger
- You are writing `ExternalSecret` manifests for the cluster.
- The `external-secrets` controller pod enters `CrashLoopBackOff` with logs showing: `unable to create controller ... no matches for kind "ExternalSecret" in version "external-secrets.io/v1"`.
- `ExternalSecret` status shows `SecretSyncedError` when fetching from Vault.

## Pitfalls & Rules

### 1. API Version Mismatch
**NEVER** use `apiVersion: external-secrets.io/v1` in this cluster.
The installed version of External Secrets Operator (v0.16.x) **only** supports `external-secrets.io/v1beta1`.

Applying a `v1` manifest does not just fail locally; it can crash the global ESO controller, halting all secret synchronization across the entire cluster.

**Correct:**
```yaml
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
```

### 2. Missing Individual Properties (SecretSyncedError)
`ExternalSecret` status `SecretSyncedError` does not always mean the entire secret path is missing. If the path exists but one or more `remoteRef.property` keys are absent, ESO fails with an error like:
```
cannot find secret data for key: "<property-name>"
```

**Diagnosis:**
1. List the actual keys stored in OpenBao:
   ```bash
   curl -s -H "X-Vault-Token: $VAULT_TOKEN" \
     http://127.0.0.1:8200/v1/secret/data/<path> | jq -r '.data.data | keys[]'
   ```
2. Compare against the `remoteRef.property` list in the `ExternalSecret` manifest.
3. If the K8s secret has `deletionPolicy: Retain`, old values may still exist in the cluster Secret even while OpenBao is incomplete. You can recover missing values from the existing K8s secret:
   ```bash
   kubectl get secret <target-name> -n <namespace> -o jsonpath='{.data.<KEY>}' | base64 -d
   ```

**Fix:** Add all missing properties to OpenBao (preserving existing ones), then force-sync.

### 3. Recovery from CrashLoop
If the controller is crashing due to a bad API version:
1. Revert the `apiVersion` to `v1beta1` in your GitOps repository and push the changes.
2. If Flux cannot reconcile because the ESO webhook is down, manually delete the offending `ExternalSecret` from the cluster (`kubectl delete externalsecret <name> -n <namespace>`). You may need to patch out finalizers if it hangs.
3. Delete the crashing `external-secrets` controller pod in the `external-secrets` namespace to force a clean restart.
4. If the `HelmRelease` is completely wedged or CRDs are corrupt, delete the helm release (`flux delete hr external-secrets -n external-secrets`) and reconcile the flux kustomization to reinstall cleanly.

### 3. Private Registry Authentication (Dockerconfigjson)
When pulling images from private registries (like `ghcr.io`):
- Make sure the `target.template.type` is explicitly set to `kubernetes.io/dockerconfigjson`.
- Use the exact formatting below to avoid Go template quote escaping errors (`unexpected "\" in operand`).

**Correct Template:**
```yaml
  target:
    name: ghcr-pull-secret
    creationPolicy: Owner
    template:
      type: kubernetes.io/dockerconfigjson
      data:
        .dockerconfigjson: |
          {
            "auths": {
              "ghcr.io": {
                "username": "hugoalmeidamoreira",
                "password": "***",
                "auth": "{{ printf \"%s:%s\" \"hugoalmeidamoreira\" .GH_PAT | b64enc }}"
              }
            }
          }
  data:
    - secretKey: GH_PAT
      remoteRef:
        key: infrastructure/github
        property: pat
```

### 4. Vault (OpenBao) KV-v2 Pathing & Bitwarden\n**Note:** Bitwarden SDK and integration have been completely removed from this cluster. The External Secrets Operator is now dedicated exclusively to OpenBao (Vault).\n\nWhen the `ClusterSecretStore` is configured for Vault v2 with `path: secret` (the default in this cluster):
- **DO NOT** prefix the `remoteRef.key` with `secret/data/`. The operator handles this automatically.
- **Incorrect:** `key: secret/data/infrastructure/postgres`
- **Correct:** `key: infrastructure/postgres`