---
name: agent-runtime-capability-audit
description: Diagnose why a Theseus platform agent pod is structurally unable to perform its intended tasks — missing skills, missing CLI tools, or network gaps preventing external service access. Use when an agent manifest looks correct (env vars, secrets, config all present) but the agent still can't perform tasks that should be possible.
triggers:
  - Agent manifest has all env vars and secrets but the agent still can't access a required DB or API
  - Agent cannot use a known skill because it was never distributed to that agent's PVC or image
  - Agent pod lacks curl/wget or other CLI tools needed for HTTP-based workflows
  - Agent needs to reach a Tailscale-internal service but Tailscale is not installed in the container
  - You suspect the agent is "blind" to something that should be available

---

# Agent runtime capability audit

Use this when an agent's manifest and secrets are correct but the agent still cannot perform its intended tasks. The problem is a **runtime capability gap**, not a config or secret problem.

## The 3-layer audit

When diagnosing a capability gap, check these layers in order:

### Layer 1 — Skills

Skills are the agent's procedural knowledge. An agent can't do something it doesn't have a skill for.

1. **List skills in the image** (baked-in baseline):
   ```bash
   kubectl exec -n <ns> <pod> -- find /opt/hermes/skills -name SKILL.md 2>/dev/null | sort
   ```

2. **List skills in the PVC** (custom/runtime-persisted):
   ```bash
   kubectl exec -n <ns> <pod> -- find /opt/data/skills -name SKILL.md 2>/dev/null | sort
   ```

3. **Check for the required skill** by name:
   ```bash
   kubectl exec -n <ns> <pod> -- find /opt/hermes/skills /opt/data/skills -name '*<skill-name>*' 2>/dev/null
   ```

4. **Check `skills.external_dirs` in the agent's config**:
   ```bash
   kubectl exec -n <ns> <pod> -- grep -A 5 '^skills:' /opt/data/config.yaml
   ```
   If `external_dirs: []`, the agent only loads skills from the image and PVC — no custom paths.

5. **Verify the skill exists** in the agent's loaded skill list:
   The agent loads skills from `/opt/hermes/skills` (image) and `/opt/data/skills` (PVC), merging them. The `skills.external_dirs` list can add additional paths.

### Layer 2 — CLI tools

The agent can only use tools that exist in the container's `$PATH` or are available via Python.

1. **Check for common CLI tools**:
   ```bash
   kubectl exec -n <ns> <pod> -- which curl wget nc nmap 2>&1
   ```

2. **Check what Python is available**:
   ```bash
   kubectl exec -n <ns> <pod> -- which python3
   ```

3. **Check for the agent's venv** (Hermes uses a venv with extra packages):
   ```bash
   kubectl exec -n <ns> <pod> -- ls /opt/hermes/.venv/bin/ 2>/dev/null | head -20
   ```

4. **If the agent needs HTTP access** (e.g., to PostgREST, OpenBao, Doppler) but has no `curl`, it can use Python `urllib` as fallback — but only if the network is reachable.

### Layer 3 — Network access

The agent can only reach services that are:
- In the same cluster (K8s DNS: `<service>.<namespace>.svc.cluster.local`)
- Exposed via the agent's network namespace (ingress, service, Tailscale)

1. **Check if Tailscale is installed**:
   ```bash
   kubectl exec -n <ns> <pod> -- which tailscale 2>&1
   ```

2. **Check if the target service is cluster-internal** (reachable via K8s DNS) or external (requires Tailscale/DNS):
   - Cluster-internal services: `http://<service>.<namespace>.svc.cluster.local:<port>`
   - Tailscale services: `http://<tailscale-ip>:<port>` or `http://<tailscale-fqdn>`

3. **Test cluster-internal reachability** (if the container has a networking tool):
   ```bash
   kubectl exec -n <ns> <pod> -- python3 -c "
   import urllib.request
   try:
       r = urllib.request.urlopen('http://<service>.<ns>.svc.cluster.local:<port>', timeout=3)
       print('OK:', r.status)
   except Exception as e:
       print('FAIL:', e)
   "
   ```
   Ask the user to allow the test first.

## Common failure patterns

### Pattern A: Missing skill file
**Symptom**: Agent says "I don't know how to do X" or tries to do something manually instead of using a structured workflow.
**Cause**: The skill file (e.g., `cortex-postgrest-api`) exists in your local `~/.hermes/skills/` but was never copied into the agent's PVC or image.
**Fix**: Copy the skill into the PVC or add it to the image. See `theseus-agent-secrets-and-persistence` for skill distribution methods.

### Pattern B: Missing CLI tool
**Symptom**: Agent needs to make an HTTP request but has no `curl`.
**Cause**: The container image is minimal and doesn't include standard CLI tools.
**Fix**: Either install the tool in the image (preferred for frequently-used tools) or use Python's `urllib`/`httpx` as a fallback.

### Pattern C: Network gap (Tailscale missing)
**Symptom**: Agent needs to reach a Tailscale-internal service (e.g., PostgREST at `100.127.157.80`) but can't.
**Cause**: Tailscale is not installed in the agent's container, or the container has no network policy allowing the Tailscale interface.
**Fix options**:
- Install Tailscale in the agent container (add to Dockerfile or as a sidecar)
- Expose the target service via K8s ClusterIP instead of Tailscale (e.g., `postgrest.infrastructure.svc.cluster.local`)
- Use a service mesh or internal load balancer to make the service reachable without Tailscale

### Pattern D: PVC/image config drift
**Symptom**: Manifest looks correct but the agent behaves as if it has an old config.
**Cause**: The agent reads `/opt/data/config.yaml` from its PVC, which may be stale.
**Fix**: See `theseus-agent-secrets-and-persistence` — inspect both manifest env vars AND `/opt/data/config.yaml`.

## Fix strategies

### Adding skills to a specific agent
1. Identify which skills the agent is missing.
2. Copy the skill files into the PVC under `/opt/data/skills/<category>/<skill>/SKILL.md`.
3. Restart the deployment so the agent picks up the new skills.

### Exposing internal services to agents
Prefer K8s ClusterIP over Tailscale for inter-service communication:
- If PostgREST is in `infrastructure` namespace, the agent can reach it via `postgrest.infrastructure.svc.cluster.local`
- This avoids needing Tailscale in every agent pod
- Only use Tailscale for external access (outside the cluster)

### Adding CLI tools to the agent image
This is a Dockerfile change, not a manifest change. Options:
1. **Multi-stage build**: Add `curl`/`wget` to the base image during Docker build
2. **Init container**: A busybox init container that installs tools into a shared volume
3. **Sidecar**: A sidecar container that provides CLI tools via a shared filesystem
4. **Python fallback**: Use Python's built-in libraries for simple HTTP tasks

## Checklist

- [ ] Skills: Required skill file exists in image (`/opt/hermes/skills`) or PVC (`/opt/data/skills`)?
- [ ] Tools: Required CLI tools (curl, wget) exist in `$PATH` or are available as Python fallbacks?
- [ ] Network: Target service is reachable via K8s DNS (ClusterIP) or Tailscale (installed)?
- [ ] Config: `/opt/data/config.yaml` is not stale and matches the manifest?
- [ ] External dirs: `skills.external_dirs` in config doesn't need to be set to a custom path?

## Related skills

- `theseus-agent-secrets-and-persistence` — Secret injection, PVC persistence, config drift, skill distribution methods
- `cortex-postgrest-api` — How agents should interact with the mnemosyne DB via PostgREST API
- `hermes-agent` — General Hermes Agent usage and configuration
