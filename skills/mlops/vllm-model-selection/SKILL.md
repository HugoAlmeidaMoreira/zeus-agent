---
name: vllm-model-selection
description: >
  Evaluate, compare, and recommend LLM models for vLLM, SGLang, or Ollama
  deployment based on available hardware specs (VRAM / unified memory),
  supported quantizations, and engine architecture compatibility. Use when
  the user asks "what model should I run", "will X model fit on Y GPU",
  "can I quantize Z to FP4", "does vLLM/SGLang support this model",
  or wants to compare inference engines for their hardware.
triggers:
  - "what model should I download for my GPU"
  - "will model X fit on Y GB VRAM"
  - "can I run this model on vLLM"
  - "compare these models for my hardware"
  - "is FP4/GPTQ/AWQ available for model X"
  - "which quantization for model X on vLLM"
  - "model too slow / too big / OOM with vLLM"
  - "does an official vLLM or SGLang image exist for arm64 / Blackwell / DGX Spark"
  - "which Docker tag should I try first on GB10 / Grace-Blackwell"
---

# vLLM Model Selection Workflow

## 1. Gather Hardware Constraints

Ask the user (or read from cluster context):
- Total GPU / unified memory available (e.g. 128GB GB10)
- Number of GPUs and interconnect (NVLink, PCIe)
- vLLM version running
- Target context length and batch size

Rule of thumb for vLLM VRAM (with KV cache):
```
VRAM_model  = param_count * bytes_per_param * 1.15  (weights + overhead)
VRAM_cache  = batch_size * seq_len * num_layers * hidden_size * 2 * sizeof(kv)
VRAM_total  = VRAM_model + VRAM_cache + ~5GB overhead
```

| Quantization | bytes/param | Quality loss | vLLM support | Hardware req. |
|-------------|-------------|-------------|--------------|---------------|
| bf16/fp16   | 2.0         | None        | Universal    | Any           |
| FP8         | 1.0         | Minimal     | Good         | Ada/Hopper+   |
| GPTQ-Int4   | ~0.5        | Low         | Good         | Any           |
| AWQ-Int4    | ~0.5        | Low         | Good         | Any           |
| GGUF Q4_K_M | ~0.5        | Low         | Via llama.cpp| Any           |
| GGUF Q8_0   | 1.0         | Minimal     | Via llama.cpp| Any           |
| **NVFP4**   | ~0.5        | Low         | **Nightly only** | **Blackwell only** |

## 2. Query Hugging Face Hub

Search for candidate models via API:
```bash
curl -s "https://huggingface.co/api/models?search=<MODEL_NAME>&limit=10&sort=downloads"
```

For each candidate, fetch the model card / config to get:
- `hidden_size`, `num_hidden_layers`, `num_attention_heads`
- `num_key_value_heads` (GQA/MQA indicator — affects KV cache size)
- `architectures` (check vLLM support)
- `quantization_config` if present

Check if vLLM supports the architecture:
```bash
curl -s https://raw.githubusercontent.com/vllm-project/vllm/main/vllm/model_executor/models/<model_file>.py
```
If 404, the architecture is likely NOT supported yet.

## 3. Calculate On-Disk and In-Memory Size

List safetensors files via API:
```bash
python3 -c "
import urllib.request, json
url = 'https://huggingface.co/api/models/<org>/<model>/tree/main'
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
with urllib.request.urlopen(req, timeout=30) as resp:
    data = json.load(resp)
total = sum(item['size'] for item in data if item['path'].endswith('.safetensors'))
print(f'Total weights: {total / 1e9:.2f} GB')
"
```

On-disk size != VRAM usage. vLLM loads weights into GPU memory with overhead.
Multiply on-disk bf16 by ~1.15 for VRAM. Quantized models are closer to 1:1.

## 4. Check Available Quantizations

Search HF for quantized variants:
```bash
for q in AWQ GPTQ marlin exl2 fp8 gguf; do
  curl -s "https://huggingface.co/api/models?search=<MODEL>+$q&limit=5"
done
```

For GGUF variants, list specific quants:
```bash
python3 -c "
import urllib.request, json
url = 'https://huggingface.co/api/models/<org>/<model>-GGUF/tree/main'
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
with urllib.request.urlopen(req, timeout=30) as resp:
    data = json.load(resp)
for item in data:
    if item['path'].endswith('.gguf'):
        print(f\"{item['path']}: {item['size'] / 1e9:.2f} GB\")
"
```

### NVFP4 / ModelOpt caution

NVIDIA ModelOpt produces `hf_quant_config.json` files with `quant_algo: "NVFP4"`. Even if vLLM or SGLang has NVFP4 kernels, the ModelOpt format may not be directly loadable through auto-detection. Before declaring a ModelOpt-quantized model compatible with vLLM or SGLang:

1. Check the model card README for documented serving methods. If only SGLang or TensorRT-LLM is mentioned, vLLM likely won't work.
2. Verify the runtime image version in the cluster. NVFP4 support requires recent builds.
3. NVFP4 requires **Blackwell architecture** (compute capability 100+). GB10/GB200 work; Hopper/Ada do not.
4. If the model has `conv1d` layers (linear attention / Mamba hybrids), check if those are excluded from quantization — partial quantization can break loading.

### SGLang + ModelOpt FP4 / NVFP4 specifics

For **SGLang on Blackwell**, do not rely blindly on offline quantization auto-detection for ModelOpt NVFP4 models.

Observed safe pattern:
- pass `--quantization modelopt_fp4` explicitly
- for Qwen MoE / Qwen3-Coder style NVFP4 deployments on NVIDIA Blackwell, pass `--moe-runner-backend flashinfer_cutlass`
- a local filesystem model path on a shared PVC is valid; if tokenizer/config load succeeds and the crash happens during weight init, the path is probably fine

If SGLang crashes with an error like:
`ModelOptFp8Config only supports static FP8 quantization in SGLang. For FP4 quantization, use ModelOptFp4Config.`
that usually means **the runtime fell into the FP8 loader path instead of FP4**, not that the model is impossible to serve on SGLang.

Treat that error as a configuration mismatch first:
1. retry with explicit `--quantization modelopt_fp4`
2. add `--moe-runner-backend flashinfer_cutlass` for NVFP4 MoE models on Blackwell
3. if FP4 GEMM still fails on Blackwell, try `--fp4-gemm-backend flashinfer_trtllm` before giving up
4. only after that suspect image/version bugs or unsupported architecture details

If the retry gets past the old FP8/FP4 loader error and the logs now show lines such as:
- `Using CLI-specified quantization (modelopt_fp4)`
- `Detected nvfp4 checkpoint`
then the quantization path is probably correct.

At that point, a later crash during MoE weight loading — for example inside `qwen3_5.py`, `load_fused_expert_weights`, or `fused_moe_triton`, with a tensor shape mismatch like `The size of tensor a (1024) must match the size of tensor b (2048)` — should be treated as a **checkpoint/layout compatibility problem between that specific NVFP4 export and the current SGLang version**, not as another generic flag problem.

Observed examples worth pattern-matching:
- checkpoint: `vrfai/Qwen3.6-35B-A3B-NVFP4`
- image lineage: `scitrera/dgx-spark-sglang:0.5.9-t5`
- hardware family: GB10 / DGX Spark-like Blackwell
- result: quantization path fixed, then crash in fused MoE expert weight load with `1024 vs 2048`
- cluster-level confirmation pattern: if the pod schedules on the GB10 node, pulls the image, starts SGLang, prints `Using CLI-specified quantization (modelopt_fp4)` and `Detected nvfp4 checkpoint`, then dies later inside `qwen3_5.py` / `fused_moe_triton` with a tensor shape mismatch, treat that as evidence that **platform + image + GPU runtime are basically working** and the remaining problem is the checkpoint/runtime compatibility layer

When you reach that state, stop adding random serving flags. The next useful moves are:
1. try a newer SGLang image/version
2. try a more canonical checkpoint from the same family (to separate "this checkpoint" from "all Qwen NVFP4 MoE")
3. search community issues for that exact tensor-shape mismatch or checkpoint name
4. treat further flag-tweaking as low-yield unless new evidence points back to backend selection

### Runtime image discovery for arm64 / Blackwell / DGX Spark

When the user doubts whether an engine even has a usable container image for their hardware, verify the registry directly before discussing source builds.

Practical workflow:
1. Query Docker Hub tags for both engine families (`vllm/vllm-openai`, `lmsysorg/sglang`).
2. Inspect the `images` array per tag and record actual published architectures, not assumptions from README text.
3. Prefer tags that explicitly mention `aarch64`, `arm64`, `cu130`, `runtime`, `ubuntu2404`, `grace-blackwell`, or `nightly` when targeting GB10 / DGX Spark-like systems.
4. Cross-check docs to see which tags the project itself recommends for CUDA 13 / Blackwell before recommending a first test image.

Observed patterns worth remembering:
- **SGLang** publishes official multi-arch images, including `latest`, `latest-runtime`, `latest-cu130-runtime`, `dev`, and `dev-cu13`, with `arm64/linux` variants. Docs explicitly recommend Docker for CUDA 13 environments and point Blackwell-style users toward the CUDA 13 image line.
- **SGLang** also has highly specific hardware-oriented tags such as `deepseek-v4-grace-blackwell` with `arm64/linux`, which is strong evidence that Grace-Blackwell is a supported image target, not just a source-build target.
- **vLLM** publishes official `arm64/linux` images too. Confirmed useful tag families include `latest`, `latest-aarch64`, `latest-cu130`, `latest-aarch64-cu130`, `latest-cu130-ubuntu2404`, `latest-aarch64-cu130-ubuntu2404`, plus `nightly`, `nightly-aarch64`, `cu130-nightly`, and `cu130-nightly-aarch64`.
- For **GB10 / Grace-Blackwell / CUDA 13**, a reasonable first-pass recommendation is usually:
  - **SGLang:** `lmsysorg/sglang:latest-cu130-runtime` or `lmsysorg/sglang:dev-cu13`
  - **vLLM:** `vllm/vllm-openai:latest-aarch64-cu130` or `vllm/vllm-openai:latest-aarch64-cu130-ubuntu2404`

Interpretation rule:
- If an official image exists with `arm64/linux`, do not frame the situation as "there may be no image". The next debugging layer is tag choice, CUDA/runtime mismatch, or engine/model flags — not image nonexistence.


- For **Qwen3.5-35B-A3B BF16** on GB10 with SGLang, community-tested launches use:
  - `--attention-backend triton`
  - `--trust-remote-code`
  - `--context-length 131072`
  - `--mem-fraction-static 0.7`
- On this hardware family, treat **32k only as a smoke-test context**, not as a realistic target for long-context models that are meant to run much larger windows.
- For Qwen hybrid / MoE variants on GB10, `triton` is the safer attention backend signal from the field; do not assume FlashAttention is stable there.
- If running on DGX Spark-like hardware without a purpose-built image, expect **sgl-kernel / CUDA 13 / SM121(a)** friction. Community reports show that native installs can fail even before model load with `common_ops` / ABI issues. Prefer a tested Docker image or image lineage known to support GB10/Blackwell.
- Distinguish two layers of failure:
  1. **platform/runtime failure** (e.g. `common_ops` / kernel import / CUDA ABI)
  2. **model quantization failure** (e.g. wrong FP8 vs FP4 loader path)
  Fix the platform/runtime layer first.

### vLLM + Qwen3.6 MoE rollout pattern

When evaluating `Qwen/Qwen3.6-35B-A3B` or `Qwen/Qwen3.6-35B-A3B-FP8` on vLLM, separate **harmless runtime warnings** from real serving failures.

Observed online pattern from a vLLM forum thread (`v0.19.0`) serving `Qwen/Qwen3.6-35B-A3B-FP8`:
- `Resolved architecture: Qwen3_5MoeForConditionalGeneration`
- `Chunked prefill is enabled with max_num_batched_tokens=4096`
- `Setting attention block size ... to ensure that attention page size is >= mamba page size`
- `Padding mamba page size ...`
- `Enforce eager set, disabling torch.compile and CUDAGraphs`
- FLA warning like `Input tensor shape suggests potential format mismatch: seq_len < num_heads`

Interpretation:
- the `seq_len < num_heads` FLA warning is generally **benign** during normal inference with short prompts or chunked prefill; do not treat it as proof of model incompatibility
- the page-size / mamba alignment messages are tuning/engine messages, not immediate blockers
- `--enforce-eager` disables compile/cudagraph optimizations and is useful for compatibility debugging, but should not be assumed necessary in the final config

Recommended rollout order for Qwen3.6 on vLLM:
1. Start with a **conservative baseline**:
   - `Qwen/Qwen3.6-35B-A3B`
   - `--served-model-name <logical-name>`
   - `--trust-remote-code`
   - moderate `--gpu-memory-utilization` (for example `0.9`)
   - smoke-test `--max-model-len` such as `32768` first if bring-up risk is high
2. Do **not** copy Gemma-specific serving flags into Qwen deployments:
   - remove `--reasoning-parser gemma4`
   - remove `--tool-call-parser gemma4`
   - remove Gemma-specific chat templates
3. Validate in this order:
   - `/health`
   - `/v1/models`
   - `/v1/chat/completions` with a trivial deterministic prompt
4. Only after baseline generations are clean, add higher-level features:
   - `--enable-auto-tool-choice`
   - `--tool-call-parser qwen3_xml` for Qwen 3.x XML-style tool calling
   - `--reasoning-parser qwen3` if reasoning mode is actually needed

For Qwen3.5/3.6, treat tool calling, reasoning parsers, and non-default chat-template behaviour as **second-phase features**, not part of the initial compatibility proof.

### Qwen 3.x tool-calling compatibility check

If a Hermes-style client sends OpenAI-compatible requests with:
- `tools: [...]`
- `tool_choice: "auto"`

then vLLM must be started with both:
- `--enable-auto-tool-choice`
- `--tool-call-parser qwen3_xml`

If those flags are missing, vLLM returns an HTTP 400 of the form:
- `"auto" tool choice requires --enable-auto-tool-choice and --tool-call-parser to be set`

Treat that as a **serving configuration error**, not a client-side tool schema problem.

Verification pattern after rollout:
1. wait for `/health` to return `200`
2. confirm pod args or logs show auto tool choice enabled
3. send a direct `/v1/chat/completions` request with a tiny fake function tool and `tool_choice: "auto"`
4. expect `200 OK` and a response containing `tool_calls`

For Qwen 3.x on vLLM, prefer `qwen3_xml` over `hermes` unless you have model-specific evidence that a different parser is required.

### Single-GPU GitOps cutover pattern

When validating vLLM on a cluster where the target node has only **one GPU** and another inference deployment (for example SGLang) already owns it:

1. Expect `Pending` with scheduler messages like `Insufficient nvidia.com/gpu` and sometimes `Insufficient memory` until the competing workload is scaled to zero.
2. In GitOps setups, free the GPU in Git first, then reconcile both kustomizations. If you only patch live state, Flux may revert it.
3. On Theseus-style layouts this can mean scaling `tenant-sglang` to `0` before `tenant-vllm` can schedule on `gx10-d5e3`.
4. Do not treat the first cold start as a normal pod startup. The sequence can be:
   - multi-minute image pull (arm64 CUDA image)
   - long Hugging Face checkpoint download
   - safetensors shard load
   - `torch.compile` / warmup / KV-cache profiling
   - only then `/health` becomes green
5. During this phase the pod may be `Running` but still **not Ready**, and the Service endpoint may remain under `notReadyAddresses`; external/Tailscale probes can fail even though the container is progressing normally.
6. Read the logs before changing flags. If logs keep advancing through shard loading, compile, warmup, or profiling, the better action is usually to wait.

### Qwen 3.6 behaviour after successful bring-up

A successful vLLM bring-up does not guarantee terse instruction-following on the first prompt.

Observed pattern with `Qwen/Qwen3.6-35B-A3B` on vLLM:
- `/health` and `/v1/models` are healthy
- `/v1/chat/completions` returns `200`
- a trivial prompt like `Say only ok` may still answer with a reasoning preamble such as `Here's a thinking process:`
- vLLM logs may warn that the model's `generation_config.json` is overriding default sampling settings

Interpretation:
- this is better than a backend that emits garbage tokens or punctuation spam, but it still fails the stricter obedience smoke test
- treat it as a **second-phase prompt/template/generation-config issue**, not as proof that the engine failed to load
- after baseline bring-up, inspect model generation defaults and consider whether `--generation-config vllm` or tighter request parameters are needed for the intended agent workload

## 5. Compare Candidates

Build a comparison table:

| Model | Params | On-disk | Est. VRAM | Quant | Context | vLLM Support | Notes |
|-------|--------|---------|-----------|-------|---------|-------------|-------|
| ...   | ...    | ...     | ...       | ...   | ...     | Yes/No      | ...   |

## 6. Recommend

**Decision rules:**
- Prefer **FP8** or **GPTQ-Int4** for vLLM (best speed/quality tradeoff)
- Avoid GGUF with vLLM unless using llama.cpp backend
- MoE models: ALL expert weights must fit in memory even though only a subset activates
- Leave at least 20-30% memory headroom for KV cache
- Check vLLM release notes for newly supported architectures before declaring unsupported

## 7. Deploy

Update the vLLM deployment ConfigMap with the chosen model ID, then rollout restart:
```bash
kubectl set env deployment/vllm -n cognition VLLM_MODEL="<model_id>"
kubectl rollout restart deployment/vllm -n cognition
```

Or edit the `vllm-model-intent` ConfigMap if using the Foundry intent pattern.

## Pitfalls

- **MoE confusion**: Total params != active params. DeepSeek-V4-Flash has 284B total / 13B active but ALL 284B must be in memory. It won't fit on 128GB.
- **Context length**: 1M token context sounds great but the KV cache at that length can exceed model weights. Use `max_model_len` to cap it.
- **vLLM version lag**: A model released yesterday may not be supported by the vLLM image running in the cluster. Check the GitHub source tree before promising it will work.
- **Quantization availability**: Not all models get FP4/FP8/GPTQ variants. The original author (e.g. Qwen) is more likely to publish official quants than community repos.
- **ModelOpt NVFP4 vs vLLM**: ModelOpt's `hf_quant_config.json` is not universally supported. Always check the model card README for which serving engine the authors actually tested (SGLang, vLLM, TensorRT-LLM, etc.). If vLLM is not mentioned, assume it doesn't work.
- **Unified memory (GB10/Grace Blackwell)**: 128GB unified memory is shared between CPU and GPU. vLLM's `--gpu-memory-utilization` may need tuning (0.85-0.95) to leave room for system processes. The benefit is that CPU RAM and GPU VRAM are the same pool — no PCIe transfer bottleneck for offloading.
- **Linear attention / Mamba hybrids**: Models mixing full attention and linear attention (e.g. Qwen3.5 MoE) may have `conv1d` layers. Check `config.json` `layer_types` and `hf_quant_config.json` `exclude_modules` for `conv1d` exclusions — these can break vLLM loading if the quant config is not handled.
