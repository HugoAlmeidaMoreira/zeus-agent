---
name: theseus-agent-secrets-and-persistence
description: Diagnose and fix Theseus platform-agent secret injection for opencode-go, verify pod env/auth, and inspect what agent state persists on PVCs.
triggers:
  - Need to fix 401/auth issues for Diana/Mnemosyne using opencode-go in Theseus Kubernetes
  - Need to trace a secret from Doppler to OpenBao to ExternalSecret to the running pod
  - Need to understand whether skills, memories, and language preferences survive pod restarts
  - Need to fix a Theseus platform agent still using an old model or base URL after the Deployment/env vars were changed
  - Need to determine whether live agent behaviour comes from manifest env vars or from persisted `/opt/data/config.yaml`
  - Need to repoint a Theseus Hermes agent from one OpenAI-compatible backend to another (for example vLLM -> SGLang) without changing the logical model name used by the agent
  - Need to fix a Theseus Hermes agent that crashes on startup or on first message with an auxiliary compression model context-window error
  - Need to stop Qwen/vLLM from exposing visible thinking/reasoning text in Telegram or other Hermes gateway responses while keeping tool calling enabled
---

# Theseus agent secrets and persistence

Use this when a Theseus platform agent (for example Diana or Mnemosyne) is not authenticating correctly with `opencode-go`, or when you need to know what agent state persists.

## Preconditions

- Repo is at `~/git/theseus-kubernetes`
- Cluster access via `kubectl`
- OpenBao CLI available, often via `kubectl exec -- env BAO_ADDR=... BAO_TOKEN=... bao ...`
- Doppler CLI available
- ExternalSecrets API is `external-secrets.io/v1`

## Secret naming model

There may be **three different names** for the same underlying secret. Do not assume they match.

Example from Diana:

- Doppler secret name: `OPENCODE_GO_AGENTS`
- OpenBao property/key: `opencode-go-agents`
- Pod environment variable expected by Hermes/opencode-go: `OPENCODE_GO_API_KEY`

The pod must ultimately receive `OPENCODE_GO_API_KEY`.

## Workflow: fix opencode-go auth for an agent

1. Inspect the repo manifests.
   - Check the agent `Deployment`, `ExternalSecret`, and `kustomization.yaml`.
   - Verify what env var the container expects.
   - Verify what `secretKey` the `ExternalSecret` creates in the Kubernetes Secret.

2. Inspect the live ExternalSecret and target Secret.
   - Confirm the target Kubernetes Secret exists.
   - Confirm the expected key is present and non-empty.
   - If needed, decode it and verify length only; avoid printing the full secret.

3. Inspect the OpenBao source value.
   - Read the source secret from the relevant path.
   - Confirm whether the property is present and non-empty.
   - If empty, the issue is upstream of Kubernetes.

4. Inspect Doppler.
   - Search for likely names such as `OPENCODE_GO_API_KEY` and `OPENCODE_GO_AGENTS`.
   - In this setup, the correct Doppler source was `OPENCODE_GO_AGENTS`.

5. Apply the minimum fix.
   - Write/update the OpenBao secret with the correct value.
   - Force or trigger ExternalSecret reconciliation.
   - Restart the agent deployment if needed.

6. Verify end-to-end.
   - Confirm Kubernetes Secret now contains the expected key.
   - Confirm inside the pod that `OPENCODE_GO_API_KEY` is set.
   - Confirm `DEFAULT_MODEL=glm-5.1` if relevant.
   - Check logs for disappearance of `401 Invalid API key` or similar auth failures.

## Recommended manifest pattern

Prefer explicit mapping so the naming mismatch is documented and safe:

- External secret source can point to OpenBao property `opencode-go-agents`
- But the resulting Kubernetes Secret key should be `OPENCODE_GO_API_KEY`
- The Deployment should reference `secretKeyRef.key: OPENCODE_GO_API_KEY`

This avoids silent mismatch where the pod expects `OPENCODE_GO_API_KEY` but the Secret only contains `OPENCODE_GO_AGENTS`.

## Persistence inspection workflow

To understand what survives restart:

1. Inspect volume mounts in the Deployment/Pod.
2. Check whether `/opt/data` is mounted from a PVC.
3. List key runtime directories under `/opt/data`.
4. Check both the live env vars and `/opt/data/config.yaml`.
5. Note whether init containers overwrite any files on boot.

Observed pattern for Diana/Mnemosyne:

- `/opt/data/skills` persists custom and synced skills
- `/opt/data/memories` persists user/profile memory and preferences
- `/opt/data/sessions` persists session history/artifacts
- `/opt/data/state.db` persists local runtime state
- Agent runtime may still read `model.default` from `/opt/data/config.yaml` even after Deployment env vars were changed
- Diana init container rewrites `/opt/data/config.yaml` at startup

## Interpretation

- Skills created/edited at runtime generally persist because they live under `/opt/data/skills`
- Language/preferences stored as memories generally persist because they live under `/opt/data/memories`
- `config.yaml` may override or outlive manifest changes, so manifest/env inspection alone is not enough
- `config.yaml` may not persist manual edits if the init container regenerates it on every boot

## Ways to distribute skills to agents

### 1. Bundled in image
Good for baseline skills, but requires image/bundle changes.

### 2. Write directly into the PVC
Place files under `/opt/data/skills/<category>/<skill>/SKILL.md`.
This is immediate and survives restarts, but can create manual drift.

### 3. GitOps injection (ConfigMap + initContainer)
Preferred for stable/shared skills:
- Create a `ConfigMap` in the agent's manifest directory containing the skill file(s)
- Add an `initContainer` (busybox) that copies from the ConfigMap into the PVC mount (`/opt/data/skills`)
- **Critical**: If the SKILL.md content contains `---` (YAML multi-document separator), DO NOT embed it directly in the Deployment YAML — it will break kustomize, which interprets `---` as document separators and fails with `missing Resource metadata: file is not directory`. Instead, put the skill content in a separate `configmap.yaml` file
- Reference the ConfigMap in both `kustomization.yaml` and the initContainer's `volumeMounts`/`volumes`
- The initContainer should use `cp -r` to copy the skill directory from the ConfigMap volume into the PVC path
- The main container's PVC mount must match the copy target (typically `/opt/data/skills/<category>/<skill>/SKILL.md`)

## GitOps-managed agent configuration (split PVC pattern)

The PVC (`/opt/data`) is the runtime source of truth. It contains **both declarative config** (`config.yaml`, `.env`) and **runtime state** (`sessions/`, `logs/`, `.tick.lock`). Mounting a Git volume over `/opt/data` will break the agent because runtime directories need write access.

### Pattern: split volumes with merge initContainer

Mount declarative config from Git into a separate path, then merge on boot:

```yaml
volumes:
  - name: data-volume
    persistentVolumeClaim:
      claimName: mnemosyne-data       # runtime: sessions, logs, .tick.lock
  - name: declarative-config-volume
    # git-sync sidecar, downwardAPI, or emptyDir populated by another initContainer

initContainers:
  - name: merge-config
    image: busybox
    command:
      - sh
      - -c
      - |
        # Merge declarative config.yaml over existing PVC config
        if [ -f /declarative/config.yaml ]; then
          # Use Python for YAML merge (or yq if available)
          python3 -c "
import yaml
with open('/declarative/config.yaml') as f:
  new = yaml.safe_load(f)
with open('/data/config.yaml') as f:
  current = yaml.safe_load(f)
def deep_merge(base, override):
    for k, v in override.items():
        if k in base and isinstance(base[k], dict) and isinstance(v, dict):
            deep_merge(base[k], v)
        else:
            base[k] = v
deep_merge(current, new)
with open('/data/config.yaml', 'w') as f:
    yaml.dump(current, f)
"
        fi
    volumeMounts:
      - name: declarative-config-volume
        mountPath: /declarative
        readOnly: true
      - name: data-volume
        mountPath: /data
```

### What to version in Git vs what stays in PVC

| File | Git-managed | PVC | Reason |
|------|-------------|-----|--------|
| `config.yaml` | Declarative template only | Runtime (merged) | Declarative = source of truth, but runtime merges with existing |
| `.env` | Yes (via secret or GitOps) | Merged | Tool variables, not API keys |
| `skills/` | Yes (ConfigMap injection) | Merged | Skills from Git are preferred source |
| `sessions/` | No | Yes | Runtime state, constantly written |
| `logs/` | No | Yes | Runtime state |
| `.tick.lock` | No | Yes | Runtime lock file |

### Agent config structure (Hermes)

Hermes uses:
- `/opt/data/config.yaml` — full config including model, providers, personalities inline (~403 lines). The `personality` field references a named personality defined inline in this same file.
- `/opt/data/.env` — tool environment variables (TERMINAL_TIMEOUT, BROWSERBASE etc.), NOT API keys for the agent itself
- No `soul.md` or `user.md` — Hermes does not use these files. Personality is defined via the `personalities:` map in `config.yaml` and activated via `personality: <name>`.

To manage config declaratively, extract `personalities` into a separate file (e.g., `personalities.yaml`), and have the merge initContainer combine them. The `config.yaml` in Git should only contain the declarative subset (model, providers, network, toolsets) and let the merge overlay the personalities.

## Workflow: fix model/config drift in a Theseus Hermes agent

Use this when the live agent still calls an old model after you changed the Deployment manifest.

1. Inspect the live Deployment env vars.
   - Confirm `DEFAULT_MODEL`, `OPENAI_BASE_URL`, and provider-related env vars.

2. Inspect the running pod directly.
   - Check pod env.
   - Read `/opt/data/config.yaml`.
   - Compare the two sources.

3. Check the logs for the effective model name.
   - Hermes gateway errors often reveal the actual model being sent upstream, e.g. `The model <name> does not exist`.

4. If `/opt/data/config.yaml` is stale, patch it in place on the PVC.
   - Make a timestamped backup first.
   - Edit only the minimal key, typically `model.default`.

5. Restart the Deployment.
   - Roll the pod so Hermes reloads the persisted config.

6. Verify end-to-end.
   - New pod is running.
   - `/opt/data/config.yaml` now matches the desired model.
   - Pod env still matches.
   - Logs no longer show the old model or 404s for it.

## Workflow: fix auxiliary compression context mismatch in a Theseus Hermes agent

Use this when a Theseus Hermes agent starts failing after a backend/model change with an error saying the auxiliary compression model is below Hermes Agent's minimum context requirement.

Typical symptom:

- `ValueError: Auxiliary compression model <model> has a context window of <n> tokens, which is below the minimum 64,000 required by Hermes Agent`

What this usually means in this environment:

- `compression.enabled` is still `true`
- Hermes auto-detects the main runtime as the auxiliary compression model
- the main model/backend is valid for chat, but its configured context window is below the 64k floor required for auxiliary compression
- in practice, this can happen after moving Mnemosyne to a local/custom OpenAI-compatible backend with a smaller context limit

### Steps

1. Confirm the error in live logs.
   - Check the running pod logs, not just the user-facing error.
   - Confirm the stack trace points to `run_agent.py` and `_check_compression_model_feasibility()`.

2. Inspect the persisted config inside the pod.
   - Read `/opt/data/config.yaml`.
   - Check `model.default`, `model.provider`, `model.base_url`, `model.context_length`, and the top-level `compression` block.
   - Do not assume the Deployment manifest is enough; the live agent may be reading the PVC config.

3. Verify whether an explicit auxiliary compression model is configured.
   - If there is no `auxiliary.compression` override, Hermes may auto-detect and reuse the main model.
   - If the main model is a small-window local/custom backend, that can trigger the failure.

4. Apply the minimum safe fix for immediate recovery.
   - Make a timestamped backup of `/opt/data/config.yaml`.
   - If the goal is to restore service quickly, set:
     - `compression.enabled: false`
   - This avoids the startup feasibility check and lets the agent boot with the current main model.

5. Validate before restart if possible.
   - Instantiate the agent in-pod using the Hermes venv Python (`/opt/hermes/.venv/bin/python`) so imports resolve.
   - Confirm `AIAgent(...)` initializes successfully and reports `compression_enabled=False`.

6. Restart and verify.
   - Roll the Deployment.
   - Confirm the new pod is `Running`.
   - Re-read `/opt/data/config.yaml` in the new pod to ensure the persisted change survived.
   - Check recent logs for disappearance of the compression `ValueError`.

### Interpretation

- This is not necessarily a backend outage.
- It is a Hermes startup/config compatibility issue between the selected main model and the auxiliary compression requirement.
- Disabling compression is the fastest recovery path when no suitable 64k+ auxiliary model is configured.

### Follow-up options

After recovery, decide whether to keep compression disabled or configure a proper auxiliary model with at least 64k context.

### Pitfalls

- Patching only Deployment env vars will not fix this if `/opt/data/config.yaml` still enables compression.
- Using plain `python3` inside the pod may fail to import Hermes dependencies; use `/opt/hermes/.venv/bin/python`.
- Do not “fix” this by lying about `auxiliary.compression.context_length` unless you have verified the detected value is actually wrong.

## Workflow: disable visible Qwen thinking in a Theseus Hermes + vLLM deployment

Use this when a Theseus Hermes agent is wired correctly to a Qwen model behind vLLM, but Telegram or another gateway shows the model's reasoning/thinking text and you want normal replies to stay clean.

Typical symptom:

- a simple prompt such as `Say only ok` returns a long reasoning block and only then the final answer
- the response may contain literal thinking text or a `</think>` boundary in `message.content`
- tool calling may already be working, so the goal is to suppress visible reasoning without breaking tools

### Root cause pattern

For Qwen3-family models, the chat template can enable thinking by default. In vLLM this is controlled by chat-template kwargs, not by Hermes display settings alone.

What was confirmed in this environment:

- default request to `/v1/chat/completions` produced visible reasoning text before the final answer
- request-level override with `chat_template_kwargs: {"enable_thinking": false}` returned only the final answer
- tool calling still worked with thinking disabled

### Decision rule

Prefer fixing this at the vLLM backend when the same model serves a Hermes gateway, because:

- the problem is model/template behaviour, not Telegram rendering
- server-side defaults remove reasoning for all normal calls consistently
- Hermes can still override per-request later if explicit visible reasoning is wanted

### Steps

1. Reproduce with a direct backend call.
   - Call `/v1/chat/completions` with a deterministic prompt such as `Say only ok`.
   - Inspect `message.content` for visible reasoning text.

2. Prove the request-level override first.
   - Send the same request with:
     - `chat_template_kwargs: {"enable_thinking": false}`
   - Confirm the response now contains only the final answer.

3. Patch the vLLM server defaults.
   - In the vLLM serve args, add:
     - `--reasoning-parser qwen3`
     - `--default-chat-template-kwargs '{"enable_thinking": false}'`
   - Keep existing tool-calling flags if already needed:
     - `--enable-auto-tool-choice`
     - `--tool-call-parser qwen3_xml`

4. Roll out by GitOps.
   - Commit and push the manifest change.
   - Reconcile the relevant Flux kustomization.
   - Wait for the `vllm` rollout to finish.

5. Verify both clean replies and tools.
   - Re-run `/v1/chat/completions` without any override; it should now return only the final answer.
   - Re-run a tool-calling request with `tool_choice: auto` and confirm `tool_calls` still appear when the prompt really requires a tool.

### Interpretation

- If disabling thinking per request works but default behaviour still shows it, the fix belongs in vLLM server args.
- If thinking disappears but tool calls stop appearing, review the interaction between `--reasoning-parser` and `--tool-call-parser` before changing Hermes.
- If the backend reply is already clean but Telegram still shows reasoning, then inspect Hermes/gateway formatting separately.

### Pitfalls

- Testing only with a weak tool prompt can make it look like tool calling broke when the model simply chose not to call a tool.
- A server that supports `chat_template_kwargs` per request can still need `--default-chat-template-kwargs` for a clean default UX.
- Suppressing visible thinking does not mean disabling all reasoning capability; it only changes the template mode exposed by default.

## Workflow: repoint a Theseus Hermes agent from vLLM to SGLang

Use this when the agent is already configured with Hermes `provider: custom` and you want to swap the OpenAI-compatible backend while preserving the agent-facing model name.

1. Inspect the live agent config first.
   - Read the Deployment env vars for `HERMES_INFERENCE_PROVIDER`, `OPENAI_BASE_URL`, and `DEFAULT_MODEL`.
   - Read `/opt/data/config.yaml` inside the pod because persisted config can outlive GitOps/env changes.

2. Check the target backend, not just the source.
   - Confirm the old service endpoint really has live endpoints.
   - Confirm the new service endpoint has live endpoints.
   - In the observed Mnemosyne case, `vllm` had `endpoints: <none>` while `sglang` had a live backend pod.

3. Verify the target backend accepts the model name the agent expects.
   - For SGLang, inspect `python3 -m sglang.launch_server --help` and confirm `--served-model-name` exists.
   - Test `/v1/chat/completions` against the SGLang pod with both the physical model name and the logical alias (for example `theseus`).
   - Do not assume `/v1/models` is the whole truth; in the observed case chat completions accepted `model: theseus` even though `/v1/models` reported the HF model ID.

4. Apply the GitOps changes.
   - In the SGLang Deployment, declare `--served-model-name <logical-name>` explicitly.
   - In the Hermes agent Deployment, change `OPENAI_BASE_URL` from the old backend service to the SGLang service.
   - Keep `DEFAULT_MODEL` unchanged if the goal is to preserve the agent's logical model name.

5. Distinguish repo edits from live cluster state.
   - A local edit in `~/git/theseus-kubernetes` does nothing to the running Deployment until you commit/push and Flux reconciles.
   - Check the live Deployment spec directly with `kubectl get deploy ... -o jsonpath=...` instead of assuming your local file has already propagated.
   - If you need an immediate hotfix before GitOps reconciliation, patch the live Deployment as well (for example `kubectl set env deployment/<name> OPENAI_BASE_URL=http://sglang...`).

6. Reconcile and restart.
   - Reconcile the Flux Kustomizations.
   - Restart the Hermes agent deployment if needed so it reloads env/config.
   - If the restarted pod still shows the old env var, inspect `Deployment.spec.template.spec.containers[].env` and patch the live Deployment before retrying the rollout.

7. Verify from the running agent.
   - Re-check pod env, `Deployment.spec` env, and `/opt/data/config.yaml`.
   - Check logs for disappearance of connection errors to the old backend.
   - From inside the agent pod, call the backend directly (`/health`, `/v1/models`, `/v1/chat/completions`) with a tiny deterministic prompt such as `Say only ok`.
   - Treat `200 OK` with junk output (`!!!!`, repeated punctuation, unrelated garbage) as a serving/model failure, not as proof that the agent wiring is correct.
   - Confirm the agent can complete a request through the new backend.

## Workflow: decide whether a broken agent needs backend failover

Use this when Mnemosyne/Diana looks silent or useless after a backend switch and you need to decide whether the problem is the agent or the inference engine.

1. Verify the platform side first.
   - Check the gateway state file and logs.
   - Confirm Telegram/other platform is connected.

2. Inspect the live agent state.
   - Check pod env.
   - Read `/opt/data/config.yaml`.
   - Inspect recent session files under `/opt/data/sessions/`.

3. Test the backend from inside the agent pod.
   - Call `/health`, `/v1/models`, and `/v1/chat/completions` directly.
   - Use one deterministic prompt and one natural prompt.

4. Interpret the result carefully.
   - If the backend is unreachable or 5xx: integration/backend availability issue.
   - If the backend returns 404 model not found: model/alias drift.
   - If the backend returns 200 with nonsense output: the agent is wired correctly, but the serving stack is not usable.

5. Before failing over to vLLM, inspect live capacity.
   - Check whether the `vllm` Deployment actually has replicas and endpoints.
   - Do not assume the service is usable just because the Service object exists.
   - If the current vLLM command is pinned to another model family (for example Gemma), remove model-specific parsers/chat templates before swapping to Qwen.
   - On the observed Theseus brain node there is only one allocatable `nvidia.com/gpu`, so `sglang` and `vllm` cannot both schedule at the same time. If the new backend pod stays `Pending` with `Insufficient nvidia.com/gpu` or `Insufficient memory`, inspect `kubectl describe pod` and `kubectl describe node` before blaming image or driver issues.
   - In that single-GPU case, treat backend validation as a cutover sequence, not a side-by-side canary: reconcile the new manifest first, then scale down or pause the old backend so the replacement pod can schedule, and only then run `/health`, `/v1/models`, and `/v1/chat/completions`.

## Pitfalls

- Updating the GitOps manifest alone may be insufficient because the agent can keep reading a stale `/opt/data/config.yaml` from its PVC.
- Live env vars can already show the new value while Hermes still uses the old `model.default` from the persisted config.
- Session history under `/opt/data/sessions/` may still contain references to the old model; that is not itself proof of an active misconfiguration.
- Manual edits inside the pod can fix the immediate issue but may drift from GitOps if there is no follow-up reconciliation strategy.
- Some agents may regenerate `config.yaml` on startup via init containers, so always verify after restart.

## Verification checklist

- [ ] Deployment env vars show the intended model/base URL
- [ ] Running pod env vars match the Deployment
- [ ] `/opt/data/config.yaml` matches the intended model
- [ ] Backup of the old config was created before manual edit
- [ ] Deployment restarted successfully
- [ ] New pod logs no longer reference the stale model
