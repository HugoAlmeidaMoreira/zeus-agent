---
name: k8s-presigned-url-public-endpoint
description: >
  Why the "sign internally, rewrite hostname" presigned-URL 
  pattern fails inside Kubernetes (AWS-S4 signature invalidation 
  + internal DNS resolution). The correct alternative is proxy 
  streaming: the backend reads from MinIO via the internal 
  service endpoint and streams bytes to the browser. Also covers 
  the Docker build cache invalidation pitfall with Next.js 
  standalone builds on GitHub Actions.
---

# K8s Presigned URL Pitfalls → Proxy Streaming Pattern

## Problem
When a backend pod inside Kubernetes generates a presigned URL 
using an internal service DNS name (e.g. 
`minio.infrastructure.svc.cluster.local:9000`), the browser 
cannot resolve that hostname.

Two naive fixes both fail:

1. **Sign internally, rewrite hostname:** AWS-S4 signatures 
   include the `Host` header. Replacing the hostname in the 
   generated URL invalidates the signature → `403 Forbidden`.

2. **Use a public endpoint client inside the pod:** The pod may 
   not resolve the public DNS name (e.g. Tailscale) from inside 
   the cluster → `ENOTFOUND`.

## Correct Solution: Proxy Streaming

Instead of presigned URLs, have the backend read the object from 
MinIO via the internal endpoint and stream the bytes to the 
browser. No signature issues, no DNS issues.

### 1. Single internal endpoint env var
```bash
MINIO_ENDPOINT=http://minio.infrastructure.svc.cluster.local:9000
```

### 1.1 Local development fallback for shared MinIO clients
If the same codebase runs both inside Kubernetes and in local dev/WSL, a hard-coded `*.svc.cluster.local` endpoint breaks locally with `getaddrinfo ENOTFOUND ...svc.cluster.local`.

Use a shared MinIO client helper that:
- uses the internal service endpoint when `KUBERNETES_SERVICE_HOST` exists
- falls back to a public/Tailscale endpoint when running outside the cluster and `MINIO_ENDPOINT` points to `*.svc.cluster.local`

```typescript
const INTERNAL_ENDPOINT = process.env.MINIO_ENDPOINT!;
const PUBLIC_ENDPOINT = process.env.MINIO_PUBLIC_ENDPOINT || INTERNAL_ENDPOINT;
const isRunningInKubernetes = Boolean(process.env.KUBERNETES_SERVICE_HOST);

function resolveEndpoint() {
  const internalUrl = new URL(INTERNAL_ENDPOINT);

  if (!isRunningInKubernetes && internalUrl.hostname.endsWith(".svc.cluster.local")) {
    return PUBLIC_ENDPOINT;
  }

  return INTERNAL_ENDPOINT;
}
```

**You MUST set `MINIO_PUBLIC_ENDPOINT` in `.env.local`** — the fallback to `INTERNAL_ENDPOINT` still points to the internal hostname, which only resolves inside the cluster. Find the Tailscale public hostname with:

```bash
kubectl get svc -n infrastructure minio-tailscale -o jsonpath='{.status.loadBalancer.ingress[0].hostname}'
```

Then add to `.env.local`:

```bash
MINIO_PUBLIC_ENDPOINT=http://<hostname>.tail5ce214.ts.net:9000
```

This preserves production behaviour while making local proxy streaming work.

### 2. Stream endpoint
```typescript
// /api/documents/[id]/stream/route.ts
import { NextResponse } from "next/server";
import { minioClient, BUCKET_NAME } from "@/app/lib/minio";
import { Readable } from "stream";

export async function GET(req, { params }) {
  const { id } = await params;

  // 1. Lookup metadata from DB
  const doc = await db.query.documents.findFirst({ where: eq(documents.id, id) });
  if (!doc) return NextResponse.json({ error: "Not found" }, { status: 404 });

  // 2. Stat + get object via internal MinIO client
  const stat = await minioClient.statObject(BUCKET_NAME, doc.key);
  const nodeStream = await minioClient.getObject(BUCKET_NAME, doc.key);

  // 3. Return as streaming response
  const headers = new Headers();
  headers.set("Content-Type", doc.fileType || "application/octet-stream");
  headers.set("Content-Length", String(stat.size));
  headers.set("Content-Disposition", `inline; filename="${encodeURIComponent(doc.fileName)}"`);

  return new NextResponse(Readable.toWeb(nodeStream), { headers });
}
```

### 3. UI uses the stream URL directly
```tsx
<iframe src={`/api/documents/${doc.id}/stream`} />
<a href={`/api/documents/${doc.id}/stream?download=1`} download={doc.fileName}>
  Descarregar
</a>
```

### 4. Separate metadata endpoint
The UI no longer needs presigned URLs at all. Create a plain 
metadata route so components can fetch title, fileType, status, 
etc.:
```typescript
// /api/documents/[id]/route.ts
export async function GET(req, { params }) {
  const doc = await db.query.documents.findFirst({ where: eq(documents.id, id) });
  return NextResponse.json({ document: doc });
}
```

## When presigned URLs ARE okay
If the cluster can resolve the public MinIO endpoint AND you 
create a MinIO client configured with that public endpoint, 
presigned URLs work. But proxy streaming is simpler, more 
reliable, and avoids exposing the MinIO endpoint to browsers 
altogether.

## Pitfall: Docker Build Cache Invalidation
GitHub Actions with `docker/build-push-action` and 
`cache-from: type=gha` may reuse stale Next.js compiled server 
chunks even after source code changes. If the deployed pod still 
behaves like the old code:

1. Temporarily add `no-cache: true` to the action inputs.
2. Trigger a build — this forces full recompilation.
3. Remove `no-cache` afterward to restore fast incremental builds.
