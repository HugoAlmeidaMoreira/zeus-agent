---
name: tailscale-expose-service
description: How to expose an internal Kubernetes service directly to the Tailnet using Tailscale Operator LoadBalancers.
tags:
  - kubernetes
  - tailscale
  - networking
  - devops
---

# Exposing Kubernetes Services to Tailscale

When the user wants to access an internal cluster service (like a database, cache, or API) "locally" via their Tailnet without setting up a public Ingress, use the Tailscale Operator's LoadBalancer integration.

## How it works

The cluster runs the Tailscale Operator. By creating a `Service` of `type: LoadBalancer` and setting the `loadBalancerClass: tailscale`, the operator will automatically provision a Tailscale device for that service and assign it an IP/DNS on the Tailnet.

## Implementation Steps

1. **Create the Service Manifest**
   Create a new service (e.g., `<app>-tailscale.yaml`) or modify an existing one. It MUST include:
   ```yaml
   spec:
     type: LoadBalancer
     loadBalancerClass: tailscale
   ```

   *Example for PostgreSQL:*
   ```yaml
   apiVersion: v1
   kind: Service
   metadata:
     name: postgres-tailscale
     namespace: infrastructure
   spec:
     type: LoadBalancer
     loadBalancerClass: tailscale
     ports:
       - name: postgres
         port: 5432
         targetPort: 5432
         protocol: TCP
     selector:
       app: postgres
   ```

2. **GitOps Deployment**
   * Add the manifest to the respective `kustomization.yaml`.
   * Commit and push to the master branch.
   * Trigger Flux reconciliation:
     ```bash
     flux reconcile kustomization flux-system --with-source
     ```

3. **Handle Flux Dependencies (Pitfall)**
   If the reconciliation doesn't immediately apply (e.g., stuck on dependencies), you may need to force-reconcile the specific Kustomization tree:
   ```bash
   flux get kustomizations
   # If something like infrastructure-postgres is stuck on a dependency:
   flux reconcile kustomization infrastructure-external-secrets-operator
   flux reconcile kustomization infrastructure-external-secrets-stores
   flux reconcile kustomization infrastructure-postgres
   ```

4. **Retrieve Tailscale DNS/IP**
   Once applied, the operator takes a few seconds to assign the Tailnet IP. Check the service:
   ```bash
   kubectl get svc -n <namespace> <service-name>
   ```
   Look at the `EXTERNAL-IP` column. It will contain the Tailnet IP and the MagicDNS name (e.g., `100.x.y.z, namespace-app.tailxxxxx.ts.net`).

## Verification

You can verify the exposure by hitting the Tailnet DNS name from within the cluster (or from the user's Tailscale-connected machine):
```bash
# For a web service
curl -s http://<namespace>-<app>.tailxxxxx.ts.net:<port>

# For a database
nc -zv <namespace>-<app>.tailxxxxx.ts.net <port>
```