---
name: cloudflare-k8s-ingress-pattern
description: Detect and follow the existing TLS/ingress pattern of a Kubernetes cluster before adding new ingresses. Avoids redirect loops and cert-manager assumptions.
version: 1.0.0
author: Zeus
metadata:
  hermes:
    tags: [kubernetes, gitops, ingress, cloudflare, tls, cert-manager]
---

# Cloudflare + K8s Ingress Pattern Detection

Use this skill whenever adding or modifying an Ingress resource in a cluster that sits behind Cloudflare or another CDN/proxy.

## The Trap

It is easy to assume that because a domain serves HTTPS publicly, the cluster must have cert-manager and local TLS termination. **This is often false.** Cloudflare's "Flexible" SSL mode terminates TLS at Cloudflare's edge and speaks plain HTTP to the cluster origin.

Adding a `tls:` block or `cert-manager.io/cluster-issuer` annotation to an Ingress in such a cluster will cause an **ERR_TOO_MANY_REDIRECTS** loop (HTTP 308).

## Diagnosing Redirect Loops from Outside the Cluster

Before touching manifests, confirm the loop from your machine:
```bash
curl -s -I -L "https://my-app.example.com/" 2>&1 | head -30
```
If you see repeated `HTTP/2 308` responses with `location: https://...`, you have a redirect loop.

Also check the TLS certificate:
```bash
echo | openssl s_client -servername my-app.example.com -connect my-app.example.com:443 2>/dev/null | openssl x509 -noout -issuer -subject
```
If the subject is `CN = example.com` (Cloudflare/Google Trust Services) rather than `CN = my-app.example.com` (Let's Encrypt), TLS is being terminated at Cloudflare, not at the cluster.

## Tailscale Exit Node Pitfall

If `kubectl`, `flux`, or `curl` to the cluster timeout with "connection refused" or 100% packet loss, check whether Tailscale is routing through an exit node:
```bash
tailscale status
```
An active exit node routes **all** traffic through that node, including traffic to local IPs like `192.168.1.64`. Disable the exit node to restore cluster connectivity:
```bash
tailscale up --exit-node=
```

## Detection Steps (run before modifying any Ingress)

1. **Inspect existing ingresses for TLS patterns**
   ```bash
   grep -ri "tls:" manifests/ 2>/dev/null | head -20
   grep -ri "secretName" manifests/ 2>/dev/null | head -20
   grep -ri "cert-manager" manifests/ 2>/dev/null | head -20
   grep -ri "ssl-redirect\|force-ssl-redirect" manifests/ 2>/dev/null | head -20
   ```

2. **Look at a working ingress as reference**
   Pick the ingress for the main app (e.g., `theseus-command-center`) and read its annotations. If it has `ssl-redirect: "false"`, the cluster serves HTTP internally.

3. **Check if cert-manager is installed**
   ```bash
   kubectl get clusterissuer -A 2>/dev/null || echo "no cert-manager"
   kubectl get pods -n cert-manager 2>/dev/null || echo "no cert-manager namespace"
   ```

4. **Check Cloudflare SSL mode**
   Cloudflare Dashboard → Domain → SSL/TLS → Overview. Note whether it says Flexible, Full, or Full (strict).

## Decision Matrix

| cert-manager installed? | Cloudflare mode | Ingress should have `tls:`? | Ingress should disable ssl-redirect? |
|------------------------|-----------------|---------------------------|-------------------------------------|
| No                     | Flexible        | **NO**                    | **YES**                             |
| No                     | Full / Strict   | **NO** (install cert-manager first) | Maybe                               |
| Yes                    | Full (strict)   | **YES**                   | NO                                  |
| Yes                    | Flexible        | NO (wasteful)             | YES                                 |

## Safe Ingress Template for "Flexible" Clusters

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: my-app
  namespace: my-namespace
  annotations:
    nginx.ingress.kubernetes.io/proxy-body-size: "50m"
    nginx.ingress.kubernetes.io/ssl-redirect: "false"
    nginx.ingress.kubernetes.io/force-ssl-redirect: "false"
spec:
  ingressClassName: nginx
  rules:
    - host: my-app.example.com
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: my-app
                port:
                  number: 80
```

## Recovery (if you already caused a redirect loop)

1. Revert the Ingress change (remove `tls:` block and cert-manager annotations).
2. Add `ssl-redirect: "false"` and `force-ssl-redirect: "false"`.
3. Commit and push; wait for FluxCD to reconcile.
4. If Cloudflare was changed from Flexible to Full/Strict, change it back to Flexible.
5. Clear browser cache/cookies and retry.

## What We Learned Here

In the `theseus-kubernetes` cluster:
- No cert-manager installed.
- No Ingress resource uses a `tls:` block.
- All ingresses explicitly disable `ssl-redirect`.
- Cloudflare terminates TLS in Flexible mode.
- The correct pattern is: **Cloudflare HTTPS → Nginx HTTP → Pod HTTP**.
