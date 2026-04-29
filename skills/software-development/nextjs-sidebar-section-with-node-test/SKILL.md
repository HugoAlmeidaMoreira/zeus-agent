---
name: nextjs-sidebar-section-with-node-test
description: Add a new protected sidebar section in vectorized-gestao-clinica and validate it without Jest/Vitest by using node:test source assertions plus tsx import smoke tests.
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [nextjs, sidebar, navigation, node-test, smoke-test, vectorized-gestao-clinica]
---

# Next.js sidebar section with node:test

Use this when adding a new group to `app/components/app-sidebar.tsx` in `vectorized-gestao-clinica`, especially when the change also needs new protected pages and API routes.

## When this applies
- A new sidebar group or link has to be added
- The repo has no configured Jest/Vitest test setup
- You still want a RED/GREEN check before and after the implementation

## What was learned
This repo does not currently expose a ready unit-test setup for React components. For small navigation features, the fastest reliable validation path is:
1. write a lightweight `node:test` file that asserts source-level presence of the expected links/pages/routes;
2. run it and watch it fail first;
3. implement the files;
4. run the same test again;
5. run `tsx` import smoke tests to catch syntax/module issues.

## Steps

### 1. Inspect the existing navigation structure
Read:
- `app/components/app-sidebar.tsx`
- `app/(protected)/layout.tsx`
- any similar pages under `app/(protected)/...`
- any similar API routes under `app/api/...`

Confirm whether the new section belongs under `(protected)` and what icon names already exist in `@phosphor-icons/react`.

### 2. Write the failing test first
Create a small test file under `tests/`, for example:
- `tests/<feature>.test.mjs`

Use `node:test` + `assert` + `fs.readFileSync` to verify:
- the new `SidebarGroup` exists;
- the expected `href`s and labels exist in `app-sidebar.tsx`;
- the expected protected page files exist and contain the correct `fetch("/api/... ")` calls;
- the expected API route files exist and contain the expected SQL/table references.

This is not a component rendering test. It is a source-contract test for repos without a proper UI test harness.

Run:
- `node --test tests/<feature>.test.mjs`

The first run should fail.

### 3. Implement the sidebar group
Edit `app/components/app-sidebar.tsx` and add:
- a new `SidebarGroup`
- one `NavLink` per destination
- `isActive` and `weight` logic based on `pathname`

Prefer existing icons already used in the repo when they fit.

### 4. Add protected pages
Create pages under:
- `app/(protected)/<section>/<page>/page.tsx`

Pattern used successfully:
- client component
- local `loading` / `error` state
- `useEffect` calling `fetch("/api/... ")`
- summary cards + table output
- `PageHeader` for consistent top section

### 5. Add API routes
Create routes under:
- `app/api/<section>/<page>/route.ts`

Pattern used successfully:
- `export const dynamic = "force-dynamic"`
- query with `db.execute(sql`...`)`
- return `NextResponse.json(...)`
- catch errors and log a clear prefix like `[SECTION/PAGE]`

### 6. Re-run the source-level test
Run again:
- `node --test tests/<feature>.test.mjs`

It should now pass.

### 7. Run import smoke tests
Because the repo has no dedicated UI/unit harness, also run a `tsx` import check covering the changed files:
- `npx tsx -e "import './app/components/app-sidebar.tsx'; import './app/api/.../route.ts'; import './app/(protected)/.../page.tsx'; console.log('ok')"`

This catches syntax/module issues in newly added files.

## Pitfalls
- `git diff -- <files>` will not show newly created untracked files. Use `git status` if you need to confirm they exist.
- Do not assume Jest/Vitest exists in this repo.
- For small navigation work, source-level assertions are enough to enforce RED/GREEN without setting up a whole test stack.
- Check Phosphor icon export names before changing imports.

## Verification checklist
- Sidebar group exists with the intended links
- Protected pages exist and fetch from the correct API routes
- API routes query the intended tables/views
- `node --test tests/<feature>.test.mjs` passes
- `npx tsx -e "import ..."` passes
