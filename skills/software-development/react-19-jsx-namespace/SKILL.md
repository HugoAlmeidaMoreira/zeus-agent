---
name: react-19-jsx-namespace
description: React 19 removed the global JSX namespace. TypeScript code using JSX.Element must be updated to React.JSX.Element.
metadata:
  hermes:
    tags: [react, react-19, nextjs, typescript, jsx, build-errors]
    related_skills: [nextjs-15-async-params]
---

# React 19 — JSX Namespace Removed

## Problem

In React 19 (shipped with Next.js 15+), the global `JSX` namespace was removed. Code that references `JSX.Element` fails at build time with:

```
Type error: Cannot find namespace 'JSX'.
```

This typically appears after upgrading Next.js or adding `@types/react` v19.

## Fix

Replace all occurrences of the global `JSX` namespace with `React.JSX`:

```tsx
// ❌ Before (React 18 and earlier)
const elements: JSX.Element[] = [];

// ✅ After (React 19+)
const elements: React.JSX.Element[] = [];
```

Same for any JSX-related types:
- `JSX.Element` → `React.JSX.Element`
- `JSX.IntrinsicElements` → `React.JSX.IntrinsicElements`
- `JSX.Attributes` → `React.JSX.Attributes`

## Quick migration

Find all occurrences in a project:

```bash
grep -r "JSX\." --include="*.{ts,tsx}" -n
```

Bulk replace (review before committing):

```bash
sed -i 's/JSX\.Element/React.JSX.Element/g' $(grep -rl "JSX\.Element" --include="*.{ts,tsx}")
```

## Pitfalls

- The error appears during `next build` (TypeScript type-checking), not during `next dev`.
- It often surfaces in utility components or custom renderers (e.g., a hand-rolled markdown parser) rather than standard JSX syntax.
- Standard JSX syntax (`<div />`) still works; only explicit type annotations break.
