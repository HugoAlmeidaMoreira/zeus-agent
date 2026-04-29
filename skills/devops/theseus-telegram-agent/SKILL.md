---
name: theseus-telegram-agent
description: Configure a platform agent in the Theseus cluster to use Telegram via OpenBao ExternalSecrets
---

# Configuring Telegram for Theseus Agents

When the user wants to communicate with an agent (e.g., Mnemosyne, Diana) via Telegram, the agent needs its Telegram credentials injected into its Kubernetes Deployment from OpenBao.

## Prerequisites
The Telegram credentials must exist in OpenBao (Vault) at the path: `tenants/personal/<agent_name>` with properties `telegram-bot-token` and `telegram-allowed-users`.

## Steps

1. **Create `externalsecret.yaml`** in the agent's base directory (`manifests/platform-agents/<agent_name>/base/externalsecret.yaml`):
   ```yaml
apiVersion: external-secrets.io/v1
   kind: ExternalSecret
   metadata:
     name: <agent_name>-telegram-secret
     namespace: platform-agents
   spec:
     refreshInterval: 1h
     secretStoreRef:
       kind: ClusterSecretStore
       name: vault-backend
     target:
       name: <agent_name>-telegram-secret
       creationPolicy: Owner
       template:
         type: Opaque
         data:
           TELEGRAM_BOT_TOKEN: "{{ .TELEGRAM_BOT_TOKEN }}"
           TELEGRAM_ALLOWED_USERS: "{{ .TELEGRAM_ALLOWED_USERS }}"
     data:
       - secretKey: TELEGRAM_BOT_TOKEN
         remoteRef:
           key: tenants/personal/<agent_name>
           property: telegram-bot-token
       - secretKey: TELEGRAM_ALLOWED_USERS
         remoteRef:
           key: tenants/personal/<agent_name>
           property: telegram-allowed-users
   ```

2. **Update `kustomization.yaml`** in the same directory to include `- externalsecret.yaml` in the resources list.

3. **Update `deployment.yaml`** to inject the environment variables into the agent's container:
   ```yaml
         image: nousresearch/hermes-agent:latest
         args: ["gateway", "run"]
         env:
           - name: HERMES_INFERENCE_PROVIDER
             value: "custom"
           # ... existing env vars ...
           - name: TELEGRAM_BOT_TOKEN
             valueFrom:
               secretKeyRef:
                 name: <agent_name>-telegram-secret
                 key: TELEGRAM_BOT_TOKEN
           - name: TELEGRAM_ALLOWED_USERS
             valueFrom:
               secretKeyRef:
                 name: <agent_name>-telegram-secret
                 key: TELEGRAM_ALLOWED_USERS
   ```

4. **Commit and Push** the changes to the GitOps repository.

5. **Reconcile Flux** to apply the changes immediately:
   ```bash
   flux reconcile kustomization flux-system --with-source
   ```

## ⚠️ CRITICAL PITFALLS (Experiential Findings)
- **ExternalSecrets API Version**: The API version for `ExternalSecret` in the cluster is now `external-secrets.io/v1`. Using `v1beta1` will cause Flux/Kustomize to fail to reconcile.
- **Agent Base Image**: Platform agents must use the `nousresearch/hermes-agent:latest` image and the args `["gateway", "run"]` to start the agent headless gateway. Do not use older runtime images like `node:22-bookworm` with `openclaw`.
- **vLLM / Local Provider Authentication:** If the agent is configured to use a local or in-cluster model provider (like vLLM) that does not require authentication, you MUST explicitly set the environment variable `HERMES_INFERENCE_PROVIDER=\"custom\"` in the deployment. If omitted, Hermes defaults to cloud providers (like OpenRouter) which strictly require an `OPENROUTER_API_KEY` header, resulting in `401 Missing Authentication header` errors even if the `OPENAI_BASE_URL` points to the local cluster.
- **OpenCode GO Agents Provider:** When using the `opencode-go` API provider for an agent, set `HERMES_INFERENCE_PROVIDER=\"opencode-go\"` (not `"openai"` or `"custom"`). Do NOT set `OPENAI_BASE_URL`, as the internal logic automatically handles it. You MUST provide the authentication key via `OPENCODE_GO_API_KEY` (not `OPENAI_API_KEY`).
- **Name-mapping Pitfall for OpenCode GO:** Keep the pod-facing secret key aligned with the env var expected by Hermes: `OPENCODE_GO_API_KEY`. If the upstream OpenBao property is named differently (for example `opencode-go-agents`) or the Doppler secret is named differently (for example `OPENCODE_GO_AGENTS`), map that difference explicitly in the `ExternalSecret`. Do not reuse the Doppler/OpenBao name as the Kubernetes secret key unless the pod env var also expects that exact name.
- **Persistent Model Config Override:** If a `hermes-agent` pod was previously run and generated a default `/opt/data/config.yaml`, that file's `model.default` value will permanently override any `DEFAULT_MODEL` env var you set in the deployment. If you change the deployment's model and the pod keeps crashing with "Model X not supported", you must delete the persisted config (`kubectl exec ... -- rm /opt/data/config.yaml`) and restart the pod so it reads the fresh environment variables. vLLM instances in the cluster are often launched with a `max_model_len` (e.g., 32768) that is lower than Hermes' minimum requirement (64000) for context compression. Hermes queries the endpoint, sees 32K, and crashes. You must explicitly configure Hermes to override the endpoint's limit by setting `model.context_length: 131072` (or similar) in the agent's `config.yaml`. This cannot be set via an environment variable; it requires editing the config file directly via `hermes config set model.context_length 131072` inside the pod, or mounting a ConfigMap.
- **NEVER use `sed`, `awk`, or `perl` to inject multiline YAML blocks** into `deployment.yaml` or Kustomization files. These tools frequently mishandle newlines and indentation in the terminal, leading to corrupted files with literal `\n` strings.
- **Literal `\n` in YAML breaks FluxCD**: If a Kustomization file gets corrupted with literal `\n` characters instead of real line breaks, Flux will crash with `invalid document separator: ---` or `error converting YAML to JSON: yaml: mapping values are not allowed in this context`.
- **Use `write_file`** to completely rewrite the file with the new content, OR use `patch` if the target block is unique and well-defined. Avoid overly complex `execute_code` scripts with heavy string manipulation for simple YAML edits, as backslash escaping in Python strings within JSON payloads often leads to `SyntaxError`. Do NOT use `echo -e` with here-docs or large strings in `terminal`, as the `\n` parsing is inconsistent and often results in malformed YAML files.

- **PVC Claiming Conflicts:** If you replace a deployment (e.g. migrating from `openclaw` to `hermes-agent`) and the new pod stays in `Pending` due to `pod has unbound immediate PersistentVolumeClaims. not found`, it's because the Persistent Volume (PV) is stuck in a `Released` state and holding onto the old claim reference. You must patch the PV to drop the old claim reference before the new PVC can bind to it: `kubectl patch pv <pv-name> -p '{"spec":{"claimRef": null}}'`.