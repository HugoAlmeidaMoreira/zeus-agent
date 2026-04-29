---
name: k8s-pvc-model-downloader
description: Download a HuggingFace model to a shared PersistentVolumeClaim in Kubernetes without interrupting the inference workload that consumes it. Covers node affinity, taints, space checks, and monitoring.
triggers:
  - Need to download a HuggingFace model to a PVC used by vLLM, SGLang, or another inference engine
  - Need to pre-cache a model on disk before switching the inference deployment to it
  - Need to copy a model into a shared K8s volume without downtime on the consumer pod
---

# K8s PVC Model Downloader

Use this when you need to get a HuggingFace model onto disk inside a Kubernetes cluster so that an inference workload (vLLM, SGLang, etc.) can load it.

## Preconditions

- `kubectl` access to the cluster
- The target PVC already exists and is mounted by the inference workload
- Know the model ID (e.g. `vrfai/Qwen3.6-35B-A3B-NVFP4`)

## Workflow

### 1. Inspect the current state

```
kubectl get pvc <pvc-name> -n <namespace>
kubectl get pod -l <workload-label> -n <namespace> -o jsonpath='{.items[0].spec.nodeName}'
kubectl exec <running-pod> -n <namespace> -- sh -c 'du -sh <cache-path>/* && df -h <cache-path>'
```

Confirm there is enough free space for the new model. Models are often larger on disk than the repo size suggests due to blobs + symlinks.

### 2. Discover scheduling constraints

The downloader pod usually must land on the same node as the inference pod, especially if the PVC is backed by a local PV or has node affinity.

```
kubectl describe pod <running-pod> -n <namespace> | grep -i "tolerations\|node-selector\|node"
kubectl get node -o json | jq -r '.items[] | select(.spec.taints != null) | .metadata.name as $n | .spec.taints[] | "\($n): \(.key)=\(.value):\(.effect)"'
```

Note any `NoSchedule` taints and required node selectors.

### 3. Create a temporary downloader pod

Use a lightweight image with Python and the modern `hf` CLI. The pod must:
- Mount the same PVC at the same path used by the inference workload
- Include matching `nodeSelector` and `tolerations` so it schedules on the correct node
- Set `HF_HUB_ENABLE_HF_TRANSFER=1` for faster downloads
- Use `restartPolicy: Never` so it exits cleanly when done

Example manifest:

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: model-downloader
  namespace: <namespace>
spec:
  restartPolicy: Never
  nodeSelector:
    kubernetes.io/hostname: <target-node>
  tolerations:
    - key: <taint-key>
      operator: Equal
      value: <taint-value>
      effect: NoSchedule
  containers:
    - name: downloader
      image: python:3.11-slim
      command: ["sh", "-c"]
      args:
        - |
          pip install -q huggingface-hub
          export HF_HUB_ENABLE_HF_TRANSFER=1
          export HF_HUB_CACHE=<cache-mount-path>
          echo "Starting download of <model-id> ..."
          hf download <model-id> \
            --local-dir <cache-mount-path>/hub/<safe-model-dir-name>
          echo "Download complete."
      resources:
        requests:
          memory: "2Gi"
          cpu: "500m"
        limits:
          memory: "4Gi"
          cpu: "2"
      volumeMounts:
        - name: models
          mountPath: <cache-mount-path>
  volumes:
    - name: models
      persistentVolumeClaim:
        claimName: <pvc-name>
```

Apply with `kubectl apply -f`.

### 4. Monitor progress

```bash
kubectl logs model-downloader -n <namespace> -f
kubectl exec model-downloader -n <namespace> -- sh -c 'du -sh <cache-path>/hub/<dir>'
```

If the pod completes too quickly, verify the directory from the inference pod instead of execing into the completed downloader pod.

### 5. Verify completion and clean up

Once the pod reaches `Completed`, confirm the size looks correct:

```bash
kubectl get pod model-downloader -n <namespace>
kubectl exec <inference-pod> -n <namespace> -- sh -c 'du -sh <cache-path>/hub/<dir>'
kubectl delete pod model-downloader -n <namespace>
```

## Pitfalls

- **Outdated CLI:** The old `huggingface-cli download` command is deprecated and may no-op while still exiting successfully. Use `hf download` instead.
- **No auth:** Unauthenticated downloads work but hit lower rate limits. Set `HF_TOKEN` if the repo is gated or large.
- **Node scheduling:** Forgetting `nodeSelector` and `tolerations` causes `FailedScheduling` because the PVC may be bound to a specific node or the target node has taints.
- **Disk space:** HF Hub cache uses additional metadata files. Ensure at least 10-15% headroom above the advertised model size.
- **Symlink/path mismatch:** Downloading with `--local-dir` creates a plain directory such as `hub/vrfai_Qwen3.6-35B-A3B-NVFP4`, not the default `models--org--name` cache layout. That is fine for pre-staging on disk, but serving systems expecting the standard HF cache structure may need a direct model path or a re-download via the native cache layout.
- **Restart policy:** If `restartPolicy` is not `Never`, a failed or completed downloader may restart unexpectedly and re-download.

## Verification checklist

- [ ] PVC exists and has enough free space
- [ ] Downloader pod schedules on the correct node
- [ ] `hf download` is used, not the deprecated `huggingface-cli`
- [ ] Download completes without auth errors (or `HF_TOKEN` is provided)
- [ ] Model files are visible from the inference pod at the expected path
- [ ] Downloader pod is deleted after completion
