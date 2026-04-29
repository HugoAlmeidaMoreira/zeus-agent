---
name: sglang-qwen36-gb10-debugging
description: Diagnóstico e rollout de Qwen3.6-35B-A3B em SGLang num node NVIDIA GB10/Grace-Blackwell via GitOps.
---

# SGLang + Qwen3.6 no GB10 (Grace-Blackwell)

## Quando usar
Usa isto quando estiveres a testar SGLang no node GB10/Grace-Blackwell (`gx10-d5e3`) do cluster Theseus, sobretudo com modelos Qwen3.6/Qwen3.5 MoE e variantes quantizadas no namespace `cognition`.

## Contexto observado
- Node: `gx10-d5e3`
- GPU: `NVIDIA GB10`
- Driver observado via `nvidia-smi`: `580.142`
- Imagem oficial funcional para arrancar: `lmsysorg/sglang:latest-cu130-runtime`
- Repo GitOps: `~/git/theseus-kubernetes`
- Deployment: `manifests/platform-computational/sglang/base/sglang-deployment.yaml`
- ConfigMap do modelo: `manifests/platform-computational/sglang/base/sglang-model-intent.yaml`

## Achados já confirmados
1. O problema inicial NÃO era driver desatualizado.
   - O node estava alinhado com o stack DGX Spark público: driver `580.142`, kernel 6.17, CUDA 13.x.
2. Trocar de uma imagem custom (`scitrera/dgx-spark-sglang:0.5.9-t5`) para a oficial `lmsysorg/sglang:latest-cu130-runtime` não resolveu o erro do checkpoint NVFP4.
3. O checkpoint `vrfai/Qwen3.6-35B-A3B-NVFP4` falhava com shape mismatch MoE:
   - `RuntimeError: The size of tensor a (1024) must match the size of tensor b (2048)`
   - stack em `qwen3_5.py` / `load_fused_expert_weights` / `fused_moe_triton`
4. O repositório oficial `Qwen/Qwen3.6-35B-A3B` é um checkpoint Transformers/Safetensors standard, multimodal (`Qwen3_5MoeForConditionalGeneration`), com 26 shards `.safetensors` e README a dizer compatibilidade com SGLang.
5. Ao remover `--quantization modelopt_fp4` e flags específicas FP4/MoE, e apontar para `Qwen/Qwen3.6-35B-A3B`, o pod deixa de cair logo e fica longamente a descarregar pesos. Isto separa bem dois estados:
   - NVFP4 custom: falha de compatibilidade logo no load
   - BF16 oficial: arranque prolongado e download em curso

## Procedimento recomendado
1. Ler os ficheiros base:
   - `sglang-deployment.yaml`
   - `sglang-model-intent.yaml`
2. Para testar checkpoint oficial não quantizado/BF16:
   - remover estas flags do comando do `launch_server` se estiverem presentes:
     - `--quantization modelopt_fp4`
     - `--attention-backend triton` (não é obrigatório para este teste)
     - `--fp4-gemm-backend ...`
     - `--moe-runner-backend ...`
   - mudar `data.model` para `Qwen/Qwen3.6-35B-A3B`
3. Commit + push GitOps.
4. Reconciliar:
   - `flux reconcile kustomization tenant-sglang -n flux-system --with-source`
5. Verificar rollout e logs:
   - `kubectl get pods -n cognition -l app=sglang -o wide`
   - `kubectl describe pod -n cognition -l app=sglang`
   - `kubectl logs -n cognition -l app=sglang --tail=200`
6. Se parecer bloqueado, medir progresso de download dentro do pod:
   - `du -sh /root/.cache/huggingface/hub/models--Qwen--Qwen3.6-35B-A3B`

## Interpretação dos sinais
- Se vês o erro `1024 vs 2048` durante `load_fused_expert_weights`, isso aponta para incompatibilidade do checkpoint/export quantizado com o loader MoE atual do SGLang, não para drivers.
- Se o pod fica `Running` sem restart e o tamanho do cache cresce de forma contínua, o servidor está a descarregar shards e ainda não chegou à fase de servir.
- O log pode mostrar:
  - `Local HF snapshot ... has no files matching ['*.safetensors', '*.bin', '*.pt']; will attempt download.`
  Isso quer dizer que a snapshot existe mas ainda não tem os pesos completos materializados.
- `HTTP 200` em `/health` e `/v1/chat/completions` NÃO prova que o serving esteja útil. Neste caso observado, o SGLang respondeu `200` mas gerou lixo (`!!!!` / sequências longas de `!`) tanto em smoke tests externos como em requests feitos de dentro do pod do agente. Isso deve ser tratado como problema de serving/model quality, não como sucesso funcional.

## Verificação mínima obrigatória
Depois de o servidor subir, não pares em `/health`:
1. Testa `/health`
2. Testa `/v1/models`
3. Testa `/v1/chat/completions` com prompt sem ambiguidade, por exemplo `Say only ok`
4. Testa também um prompt curto natural, por exemplo `Oi`
5. Se a resposta vier com pontuação repetida, tokens aleatórios, ou texto sem relação com o prompt, considera o backend semanticamente avariado mesmo com `200 OK`

## Pitfalls
- `kubectl rollout status` pode dar timeout enquanto o modelo ainda está a ser descarregado. Isso não significa crash.
- O pod pode ficar vários minutos sem `/health` responder porque ainda está em bootstrap/download.
- O SGLang no GB10 pode fazer auto-deteção de backend FP4 (`SM120 (Blackwell) detected...`) mesmo quando estás a testar BF16; isso por si só não prova que esteja a usar um checkpoint FP4.
- O modelo Qwen3.6-35B-A3B é multimodal; o loader vai inicializar `Qwen3VLProcessor` e configs de vídeo/imagem mesmo que o teste seja só textual.

## Estado conhecido no fim desta investigação
- Commit GitOps BF16 test: `69147a9` (`chore: test qwen bf16 on sglang`)
- O pod `sglang` no namespace `cognition` arrancou com `lmsysorg/sglang:latest-cu130-runtime` e começou a descarregar o modelo `Qwen/Qwen3.6-35B-A3B` sem repetir o crash imediato do NVFP4.
