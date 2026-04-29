---
name: hermes-theseus-vllm
description: Configurar o Hermes Agent (local ou cluster) para usar o modelo 'theseus' servido pelo vLLM do cluster Theseus, via endpoint Tailscale ou DNS interno.
---

# Hermes + Theseus (vLLM) Setup

## O que é o "theseus"

O nome `theseus` não é um modelo real. É o `--served-model-name` que o vLLM expõe na API OpenAI-compatible.

- **Modelo real**: `Qwen/Qwen3.6-35B-A3B`
- **Nome servido**: `theseus`
- **Contexto máximo**: 262144 tokens
- **Max model len live**: configurado via `vllm-model-intent` ConfigMap (default 32768 para smoke test)

## Endpoints do vLLM

| Origem | URL | Notas |
|--------|-----|-------|
| Dentro do cluster (pods) | `http://vllm.cognition.svc.cluster.local:8000/v1` | Usado pelo Mnemosyne e outros agents no cluster |
| Tailscale (acesso externo) | `http://100.111.71.31:8000/v1` | IP Tailscale do LoadBalancer |
| Tailscale DNS | `http://cognition-vllm.tail5ce214.ts.net:8000/v1` | Alternativa ao IP |

## Configurar Hermes local

### Método recomendado: `custom_providers`

Adiciona o endpoint à lista `custom_providers` no `config.yaml`:

```yaml
custom_providers:
- name: vllm
  base_url: http://100.111.71.31:8000/v1
  api_key: dummy
  model: theseus
```

Depois ativa-o como provider:

```bash
hermes config set model.provider custom:vllm
hermes config set model.default theseus
hermes config set model.context_length 262144
```

O nome após `custom:` corresponde ao campo `name` da entrada (normalizado: minúsculas, espaços → hífens).

### Método alternativo: singleton no bloco `model`

Se não quiseres usar `custom_providers`, podes configurar diretamente:

```bash
hermes config set model.default theseus
hermes config set model.provider custom
hermes config set model.base_url http://100.111.71.31:8000/v1
hermes config set model.api_key dummy
hermes config set model.context_length 262144
```

Ou no `config.yaml`:

```yaml
model:
  default: theseus
  provider: custom
  base_url: http://100.111.71.31:8000/v1
  api_key: dummy
  context_length: 262144
```

Depois de alterar: `/reset` na sessão para recarregar.

### Pitfalls

- **Provider string**: quando usas `custom_providers`, o provider não é `custom` mas sim `custom:<nome>` (ex: `custom:vllm`). `hermes config set model.provider custom` sozinho ignora a lista `custom_providers`.
- **Nome normalizado**: o sufixo do pool key é o `name` em minúsculas com espaços substituídos por hífens. Uma entrada com `name: "VLLM Local"` torna-se `custom:vllm-local`.
- **OpenCode CLI vs Hermes Agent**: o OpenCode CLI (`opencode`) é uma ferramenta separada. Para adicionar um endpoint local ao OpenCode, usa `opencode auth login http://<url>:8000/v1`. O `custom_providers` descrito acima é apenas para o Hermes Agent.

## Configurar agent no cluster (ex: Mnemosyne)

Ver o deployment em:
`~/git/theseus-kubernetes/manifests/platform-agents/mnemosyne/base/deployment.yaml`

```yaml
env:
  - name: HERMES_INFERENCE_PROVIDER
    value: "custom"
  - name: OPENAI_API_KEY
    value: "sk-none"
  - name: OPENAI_BASE_URL
    value: "http://vllm.cognition.svc.cluster.local:8000/v1"
  - name: DEFAULT_MODEL
    value: "theseus"
```

## Port-forward vs Tailscale

| Método | Quando usar |
|--------|-------------|
| `kubectl port-forward` | Apenas para debug temporário ou quando Tailscale não está disponível |
| Tailscale IP/DNS | Uso normal e permanente. Não depende do kubectl estar aberto |

**Nunca usar port-forward como solução permanente** para o Hermes. O port-forward morre quando o processo termina ou a sessão expira.

## Verificar que o vLLM responde

```bash
curl http://100.111.71.31:8000/v1/models
```

Deve retornar `{"id":"theseus", ...}`.

## Ficheiros relevantes

- vLLM deployment: `~/git/theseus-kubernetes/manifests/platform-computational/vllm/base/vllm-deployment.yaml`
- Model intent (ConfigMap): `~/git/theseus-kubernetes/manifests/platform-computational/vllm/base/vllm-model-intent.yaml`
- Mnemosyne deployment: `~/git/theseus-kubernetes/manifests/platform-agents/mnemosyne/base/deployment.yaml`
