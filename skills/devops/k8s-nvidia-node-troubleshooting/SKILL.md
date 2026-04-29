---
name: k8s-nvidia-node-troubleshooting
description: Diagnose whether a Kubernetes node's NVIDIA driver, GPU exposure, or device plugin state is causing inference or scheduling problems.
triggers:
  - GPU workloads in Kubernetes are failing to start, not seeing GPUs, or behaving oddly on a specific node
  - Need to verify whether an NVIDIA driver update or mismatch is a plausible root cause
  - Need to inspect GPU node health from kubectl access before touching the host directly
related_skills:
  - systematic-debugging
---

# K8s NVIDIA Node Troubleshooting

Use this when the question is not yet "how to fix it" but "is the GPU node healthy, and is the driver a plausible cause?"

## Goal

Establish, from Kubernetes first, whether:
- the node is Ready
- the GPU is exposed to the scheduler
- the NVIDIA device plugin is healthy
- the actual loaded driver version can be read
- host-level access is blocked by policy and needs a fallback path

## Workflow

### 1. Identify the target node and current workload placement

```bash
kubectl get nodes -o wide
kubectl get pods -A -o wide | grep -iE 'vllm|nvidia|gpu' || true
```

If the issue is tied to one machine, capture its node name first. Do not assume the "brain node" label from memory matches the live cluster.

### 2. Confirm the node exposes GPU capacity

```bash
kubectl describe node <node> | sed -n '/Capacity:/,/Events:/p'
kubectl get node <node> --show-labels
```

Check for:
- `nvidia.com/gpu` in Capacity/Allocatable
- product labels such as `gpu.nvidia.com/product=...`
- node status `Ready`
- absence of suspicious node events

If `nvidia.com/gpu` is missing, treat that as a stronger signal than "the driver might be old".

### 3. Inspect the NVIDIA device plugin

Find the plugin pod on that node and inspect logs:

```bash
kubectl get pods -A -o wide | grep -i nvidia
kubectl logs -n kube-system <nvidia-device-plugin-pod> --tail=200
```

Healthy signs:
- plugin starts normally
- registers `nvidia.com/gpu`
- no repeated init failures

This often tells you whether the node can hand GPUs to Kubernetes even before checking the host directly.

### 4. Read the loaded driver version from inside the device-plugin pod

This is the fastest low-friction path when host debugging is restricted:

```bash
kubectl exec -n kube-system <nvidia-device-plugin-pod> -- \
  nvidia-smi --query-gpu=driver_version,name --format=csv,noheader

kubectl exec -n kube-system <nvidia-device-plugin-pod> -- sh -lc \
  'cat /proc/driver/nvidia/version || true; echo ---; uname -a'
```

Notes:
- `nvidia-smi` query fields vary by version; `cuda_version` may be rejected, so start with `driver_version,name`
- `/proc/driver/nvidia/version` is a reliable fallback for the exact loaded kernel module version
- this gives the version actually running, which matters more than package assumptions

### 5. Expect `kubectl debug node/...` to fail under PodSecurity baseline

A common dead end:

```bash
kubectl debug node/<node> --image=ubuntu:24.04 -- chroot /host bash
```

In restricted clusters this may be forbidden because node debugging uses host namespaces and hostPath mounts. If blocked by PodSecurity, do not stall on that route. Use the device-plugin pod path above, or arrange approved host access separately.

## Interpretation rules

- **Node Ready + `nvidia.com/gpu` present + plugin registered + `nvidia-smi` works**: the driver stack is at least functioning at the Kubernetes exposure layer
- **Plugin healthy but workload still failing**: look next at workload image, CUDA compatibility, model server flags, resource requests, node selectors, and taints
- **GPU absent from node capacity**: focus on driver/runtime/plugin integration before blaming the application
- **One-month-old driver alone** is weak evidence; compare the exact running version against vendor release notes and known issues before recommending updates

## Evidence to collect before blaming the driver

- node name
- GPU product label
- `nvidia.com/gpu` capacity/allocatable
- plugin pod name and logs
- `nvidia-smi` output from plugin pod
- `/proc/driver/nvidia/version`
- kernel version

## Pitfalls

- Assuming host access is available; `kubectl debug node/...` may be blocked by policy
- Treating driver age as the cause without confirming whether Kubernetes still sees the GPU cleanly
- Querying unsupported `nvidia-smi` fields and mistaking that for a driver failure
- Looking only at workload logs and skipping node/plugin evidence

## Minimal conclusion template

1. State whether the node is Ready
2. State whether `nvidia.com/gpu` is exposed
3. State the loaded driver version and GPU model
4. State whether the device plugin is healthy
5. Say whether the driver is a plausible immediate cause, or whether online release-note comparison is still needed
