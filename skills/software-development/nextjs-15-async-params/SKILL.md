---
name: nextjs-15-async-params
description: Next.js 15+ changed dynamic route params and searchParams from plain objects to Promises. Server Components must await them before use.
version: 1.0.0
metadata:
  hermes:
    tags: [nextjs, react, app-router, async-params, debugging]
    related_skills: [systematic-debugging, react-19-jsx-namespace]
---

# Next.js 15+ Async Params & SearchParams

## Problem
In Next.js 15+ (App Router), `params` and `searchParams` props in page components are **Promises**, not plain objects.

Accessing them synchronously throws:
```
Error: Route "/path/[id]" used `params.id`. `params` is a Promise and must be unwrapped with `await` or `React.use()` before accessing its properties.
```

## Fix — Server Components

Change the type signature and await the Promise:

```tsx
// ❌ Before (Next.js 14 and earlier)
export default async function Page({ params }: { params: { id: string } }) {
  const id = params.id; // throws in v15+
}

// ✅ After (Next.js 15+)
export default async function Page({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
}
```

Same for `searchParams`:

```tsx
export default async function Page({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>;
}) {
  const { id } = await params;
  const { q } = await searchParams;
}
```

## Fix — Client Components

Use `React.use()`:

```tsx
"use client";
import { use } from "react";

export default function Page({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
}
```

## Pitfall — "Still not working" after another fix

Users often report "still not working" after an unrelated fix (e.g. a database lookup change). The real error may have shifted to the async-params issue, but they describe it the same way. Always check server logs for the exact stack trace instead of assuming the original bug persists.

## Key Points
- `params` is always a Promise in v15+, even for static routes.
- `searchParams` is also a Promise.
- The component must remain `async` for Server Components.
- `React.use()` is the client-side equivalent of `await`.