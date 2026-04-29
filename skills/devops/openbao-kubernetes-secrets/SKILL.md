---
name: openbao-kubernetes-secrets
description: "Update OpenBao secrets directly via K8s pod and force ExternalSecrets sync"
prerequisites:
  - kubectl
  - doppler
---
# OpenBao Secrets Management in Kubernetes

When you need to update a secret managed by OpenBao (Vault) inside the cluster and don't have the Bao CLI configured locally, execute the commands directly inside the `openbao-0` pod and force the `ExternalSecret` operator to sync the changes.

## Steps

1. **Retrieve the Root Token**
   The OpenBao root token is usually stored in Doppler.
   ```bash
   export BAO_TOKEN=$(doppler secrets get OPENBAO_ROOT_TOKEN --plain)
   ```

2. **Patch or Write the Secret in OpenBao**
   Use `kubectl exec` to run the `bao kv patch` (or `put`) command inside the `openbao-0` pod.

   **Important Pitfall: pass variables to the remote process, not only to your local shell**
   If you write `kubectl exec ... -- sh -lc 'VAULT_TOKEN="$BAO_TOKEN" ...'`, the variable expansion happens in the container shell, where `$BAO_TOKEN` is usually unset, and you can accidentally write an empty value. Prefer `kubectl exec -- env ... bao ...` so the token and values are injected into the remote process environment explicitly.

   **Important Pitfall: HTTP vs HTTPS on localhost**
   If you try to use `bao kv put secret/path` directly without specifying `BAO_ADDR`, it defaults to `https://127.0.0.1:8200` which fails if the server is serving HTTP (`http: server gave HTTP response to HTTPS client`).
   
   ```bash
   # Example: patch a tenant secret safely from Doppler -> OpenBao
   export BAO_TOKEN=$(doppler secrets get OPENBAO_ROOT_TOKEN --plain)
   export OPK=$(doppler secrets get OPENCODE_GO_AGENTS --plain)

   kubectl exec -i -n infrastructure openbao-0 -- \
     env VAULT_TOKEN="$BAO_TOKEN" VAULT_ADDR=http://127.0.0.1:8200 \
     bao kv patch secret/tenants/personal/diana opencode-go-agents="$OPK"
   ```
   *Note: OpenBao uses `bao` but still accepts `VAULT_TOKEN` and `VAULT_ADDR` variables. The KV v2 engine requires the `secret/...` path for writes. Using `vault` alias might not be available depending on the image.*

   **Naming Pitfall: Doppler vs OpenBao vs Pod env names may differ**
   In this environment the Doppler secret is named `OPENCODE_GO_AGENTS`, the OpenBao property is `opencode-go-agents`, and the pod env var should still be `OPENCODE_GO_API_KEY`. Keep those mappings explicit in the `ExternalSecret` template to avoid silent empty secrets or 401 auth errors.

## Alternative: Port-Forward + curl (when `bao` CLI is unavailable)

If the `openbao-0` pod does not have a working `vault` or `bao` CLI, use port-forward and `curl` instead:

```bash
# Start port-forward (background)
kubectl port-forward -n infrastructure openbao-0 8200:8200 &

# Get token from Doppler
export VAULT_TOKEN=$(doppler secrets get OPENBAO_ROOT_TOKEN --plain)

# Read current values
curl -s -H "X-Vault-Token: $VAULT_TOKEN" \
  http://127.0.0.1:8200/v1/secret/data/tenants/<tenant>/<app> | jq

# Write new values
curl -s -H "X-Vault-Token: $VAULT_TOKEN" -X POST \
  http://127.0.0.1:8200/v1/secret/data/tenants/<tenant>/<app> \
  -H "Content-Type: application/json" \
  -d '{"data":{"db-url":"...","auth-secret":"..."}}'

# Stop port-forward
kill %1
```

## The "Placeholder" Pitfall

When an `ExternalSecret` reports `Status: SecretSynced` but the app still crashes with auth or URL errors, the values in OpenBao may be literal strings like `placeholder`. Always verify the actual stored values:

```bash
curl -s -H "X-Vault-Token: $VAULT_TOKEN" \
  http://127.0.0.1:8200/v1/secret/data/tenants/<tenant>/<app> | jq -r '.data.data'
```

## The "Wrong Endpoint / Stale Hostname" Pitfall

If the app logs show DNS errors like `server IP address could not be found` for a service hostname (e.g., `minio.media.svc.cluster.local`), the stored `endpoint` value in OpenBao is likely outdated or references a service that no longer exists.

**Diagnosis:**
1. Check the exact endpoint the app is using from pod env or K8s secret:
   ```bash
   kubectl get secret -n <namespace> <secret-name> -o jsonpath='{.data.MINIO_ENDPOINT}' | base64 -d
   ```
2. Verify the actual service name and namespace in the cluster:
   ```bash
   kubectl get svc --all-namespaces | grep -i minio
   ```
   The correct cluster-internal FQDN follows the pattern: `<svc>.<namespace>.svc.cluster.local`.

**Fix:**
Update the OpenBao path that holds the endpoint (commonly `infrastructure/minio` or `tenants/<tenant>/<app>`) with the correct FQDN, then force-sync and restart:
```bash
curl -s -X POST -H "X-Vault-Token: $VAULT_TOKEN" \
  http://127.0.0.1:8200/v1/secret/data/infrastructure/minio \
  -H "Content-Type: application/json" \
  -d '{"data":{"endpoint":"http://minio.infrastructure.svc.cluster.local:9000","root-user":"...","root-password":"..."}}'
```

## Full Secret Flow

```
Doppler (source of truth for some values)
    ↓
OpenBao (headless secret store, KV v2)
    ↓
ExternalSecret (ESO operator, sync interval ~1h)
    ↓
Kubernetes Secret (namespace-scoped)
    ↓
Pod envFrom / env
```

After updating OpenBao, always force-sync the ExternalSecret, verify the Kubernetes Secret, and restart the deployment.
   The `ExternalSecret` resource syncs periodically (e.g., every 1h). To force an immediate sync so Kubernetes creates/updates the underlying native Secret, annotate the ExternalSecret:
   ```bash
   kubectl annotate externalsecret -n <namespace> <externalsecret-name> force-sync=$(date +%s) --overwrite
   ```

4. **Verify the Synced Kubernetes Secret**
   Confirm the native Secret was updated with the expected value before restarting pods:
   ```bash
   kubectl get secret -n <namespace> <secret-name> -o jsonpath='{.data.<KEY>}' | base64 -d
   ```
   **Troubleshooting stale credentials:** If the app still fails after sync, the OpenBao value may be outdated. Cross-check against the source-of-truth secret in another namespace (e.g., MinIO credentials in `infrastructure/minio-credentials`) and re-write the correct value into OpenBao.

5. **Restart Dependent Pods**
   For Next.js / Node.js apps, environment variables are read at process startup, so a rolling restart is required:
   ```bash
   kubectl rollout restart deployment -n <namespace> <deployment-name>
   ```
   As a fallback, delete pods directly:
   ```bash
   kubectl delete pod -l app=<app-label> -n <namespace>
   ```