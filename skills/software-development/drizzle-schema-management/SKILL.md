---
name: drizzle-schema-management
description: Safely manage Postgres schema changes with Drizzle ORM in non-interactive and agentic contexts.
tags:
  - drizzle
  - postgres
  - nextjs
  - schema-migration
  - devops
---

# Drizzle Schema Management in Agentic Contexts

Use this when working with a Next.js / Node.js project that uses Drizzle ORM with PostgreSQL, especially when running commands from an automated or non-interactive shell.

## Prerequisites Check

Before attempting any schema operation, verify:
1. `drizzle-kit` is listed in `devDependencies` in `package.json`.
2. `drizzle.config.ts` exists at the project root and points to the correct schema file and database URL.
3. The `DATABASE_URL` env var is available and valid.

If any of the above are missing, fix them before proceeding.

## Critical Pitfall: `drizzle-kit push` requires a TTY

`drizzle-kit push` is interactive by design. When it detects a potentially destructive change (e.g., adding a unique constraint to a table that already contains data), it prompts for confirmation. **This prompt cannot be bypassed with `--force`** in all cases; the flag only auto-approves data-loss statements, not constraint-related warnings.

In a non-interactive shell (CI, agent, piped command), you will see:
```
Error: Interactive prompts require a TTY terminal
(process.stdin.isTTY or process.stdout.isTTY is false).
```

### Workarounds

1. **Prefer `generate` + `migrate`** ( safest )
   ```bash
   npx drizzle-kit generate   # creates SQL migration files
   npx drizzle-kit migrate    # applies them
   ```
   This avoids the interactive push flow entirely.

2. **Use raw SQL via `psql`** ( pragmatic fallback )
   If `drizzle-kit` is unavailable, misconfigured, or the migration flow is blocked, write the DDL in SQL and execute it directly:
   ```bash
   psql "$DATABASE_URL" -c "CREATE TABLE IF NOT EXISTS ..."
   ```
   Afterward, update the Drizzle TypeScript schema (`src/db/schema.ts`) and the Atlas HCL schema (if used) to match the live database.

   **Important:** Even if you are only adding *new* schemas or tables, `push` can still block because of constraint warnings on **existing unrelated tables** (e.g., a NextAuth `user` table). In that case, `psql` is the fastest unblocking path.

3. **Use Atlas** ( if the project maintains HCL schema-as-code )
   Projects that use Atlas (`.hcl` files) should prefer Atlas for schema changes:
   ```bash
   atlas schema apply --env local
   ```
   Then sync the Drizzle TS schema to match.

## Pitfall: `generate` creates a baseline migration when no history exists

If the project has never used Drizzle migrations before (no `drizzle/` folder with previous migration files), running `npx drizzle-kit generate` will produce a **single baseline migration that recreates every table from scratch** — not an incremental migration for your change. Applying this to a production database with existing data would be catastrophic.

**Check before generating:**
```bash
ls drizzle/
```
If the folder is empty or missing, `generate` is unsafe for incremental changes. In that case:
- Use the raw `psql` fallback below for the specific DDL change.
- Optionally, after the database is in sync, run `generate` once to establish a baseline, then delete the migration SQL before applying it, so future `generate` calls produce incremental migrations.

## Pragmatic `psql` Fallback Workflow

When `drizzle-kit push` or `migrate` is blocked and you need to move forward:

1. **Apply DDL directly:**
   ```bash
   psql "$DATABASE_URL" -c "CREATE SCHEMA IF NOT EXISTS new_schema;"
   psql "$DATABASE_URL" -c "CREATE TABLE new_schema.new_table (...);"
   ```
2. **Verify in the database:**
   ```bash
   psql "$DATABASE_URL" -c "\dt new_schema.*"
   ```
3. **Sync `src/db/schema.ts`** — add the new Drizzle table definitions to match the live schema.
4. **Sync Atlas `.hcl`** (if the project uses Atlas) — add the new schema objects there too.
5. **Test connectivity** with a throwaway TypeScript script:
   ```bash
   npx tsx scripts/test-db-insert.ts
   ```
   Example `scripts/test-db-insert.ts`:
   ```ts
   import { db } from '../src/db/index';
   import { newTable } from '../src/db/schema';
   await db.insert(newTable).values({ ... });
   console.log('Insert OK');
   ```

Do NOT leave the Drizzle TypeScript schema out of sync with the real database for long, or TypeScript builds and query type inference will break.

## Many-to-Many Junction Tables

For linking two catalog tables (e.g., `event_types` ↔ `variables`):

### Schema definition
```ts
export const eventTypeVariables = ontology.table(
  "event_type_variables",
  {
    id: uuid("id").defaultRandom().primaryKey(),
    eventTypeId: uuid("event_type_id")
      .notNull()
      .references(() => eventTypes.id, { onDelete: "cascade" }),
    variableId: uuid("variable_id")
      .notNull()
      .references(() => variables.id, { onDelete: "cascade" }),
    isRequired: boolean("is_required").default(false),
    displayOrder: integer("display_order").default(0),
    createdAt: timestamp("created_at", { withTimezone: true }).defaultNow(),
  },
  (t) => [unique("etv_unique").on(t.eventTypeId, t.variableId)]
);
```
Use a surrogate `id` PK plus a composite unique constraint on the two FKs. Add metadata columns (`is_required`, `display_order`) directly on the junction table.

### API — inline relations on GET
```ts
// /api/ontology/event-types/route.ts
const rows = await db
  .select({
    eventType: eventTypes,
    variable: variables,
    isRequired: eventTypeVariables.isRequired,
    displayOrder: eventTypeVariables.displayOrder,
  })
  .from(eventTypes)
  .leftJoin(eventTypeVariables, eq(eventTypeVariables.eventTypeId, eventTypes.id))
  .leftJoin(variables, eq(eventTypeVariables.variableId, variables.id));

// Group by parent
const grouped = rows.reduce((acc, row) => {
  const et = row.eventType;
  if (!acc[et.id]) acc[et.id] = { ...et, variables: [] };
  if (row.variable) acc[et.id].variables.push({ ...row.variable, isRequired: row.isRequired, displayOrder: row.displayOrder });
  return acc;
}, {});
return Response.json(Object.values(grouped));
```

### API — association management
```ts
// /api/ontology/event-type-variables/route.ts
// POST { eventTypeId, variableId, isRequired?, displayOrder? }
// DELETE { eventTypeId, variableId }
```

### UI pattern
- Display parent items as **cards** (not a flat table).
- Each card contains an inline **sub-table** of already-linked children.
- "+ Variável" button inside each card opens a **modal** to pick an existing child and set junction metadata (required, order).
- Trash icon on each child row calls DELETE on the junction endpoint.
- Keeps the UX scoped: user never leaves the parent list to manage links.

## Cross-Schema Queries: Use `db.execute`, Not the Query Builder

The Drizzle query builder (`.select().from()`) does **not** accept `sql\`schema.table\`` as a table reference. It expects a registered Drizzle table object and will fail at runtime (or produce invalid SQL) when given a raw SQL fragment for the `FROM` clause.

**Broken:**
```ts
const [patientCount] = await db
  .select({ count: sql<number>`count(*)::int` })
  .from(sql`gestao_clinica.patients`);
// ERROR: Failed query: select count(*)::int from gestao_clinica.patients params:
```

**Fixed:**
```ts
const patientResult = await db.execute(
  sql`SELECT count(*)::int AS count FROM gestao_clinica.patients`
);
const patientCount = Number((patientResult.rows[0] as any)?.count ?? 0);
```

Rule of thumb: if the query touches a schema or table that is **not** registered in `src/db/schema.ts` as a Drizzle table object, use `db.execute(sql\`...\`)` instead of the query builder.

## Reserved Keywords in Raw SQL (`db.execute`)

When using `db.execute(sql\`...\`)` with Drizzle, PostgreSQL reserved keywords used as column or table names must be double-quoted inside the template literal. Drizzle's tagged template does NOT auto-quote identifiers for you.

Common reserved keywords that break raw SQL:
- `order` (very common on `ontology.event_types`)
- `user`
- `primary`
- `default`
- `date`, `time`, `timestamp`

**Broken:**
```ts
await db.execute(sql`
  SELECT id, name_display, name, order
  FROM ontology.event_types
  ORDER BY order
`);
// ERROR: syntax error at or near "order"
```

**Fixed:**
```ts
await db.execute(sql`
  SELECT id, name_display, name, "order"
  FROM ontology.event_types
  ORDER BY "order"
`);
```

Always quote reserved keywords in raw SQL, even in column aliases and `ORDER BY` clauses.

## JSON Aggregation for Flattening One-to-Many

When you need one row per parent with nested child data (e.g., one patient row containing the latest review status per event type), use PostgreSQL's `jsonb_object_agg`:

```ts
const result = await db.execute(sql`
  WITH latest_events AS (
    SELECT DISTINCT ON (patient_id, event_type_id)
      patient_id, event_type_id, review_status
    FROM ontology.patient_events
    ORDER BY patient_id, event_type_id, date DESC
  )
  SELECT
    p.id,
    p.process_number,
    jsonb_object_agg(et.id::text, le.review_status)
      FILTER (WHERE et.id IS NOT NULL) as event_reviews
  FROM administrativo.patients p
  LEFT JOIN ontology.event_types et ON true
  LEFT JOIN latest_events le
    ON le.patient_id = p.id AND le.event_type_id = et.id
  GROUP BY p.id, p.process_number
`);
```

The resulting rows contain `event_reviews` as a `Record<string, string | null>` that the frontend can iterate over by event type ID.

## TypeScript Casting with `db.execute(sql\`...\`)`

`db.execute()` returns `Record<string, unknown>[]`. TypeScript rejects a direct `as MyType[]` cast because the types do not sufficiently overlap. Use `as unknown as MyType[]`:

```ts
const rows = result.rows as unknown as EventTypeStat[];
```

If you only need a single row, cast the element:
```ts
const row = result.rows[0] as unknown as Patient;
```

Some projects (e.g., `vectorized-gestao-clinica`) maintain schema in two places:
- `src/db/schema.ts` — Drizzle ORM TypeScript schema
- `schemas/<db>/schema.hcl` — Atlas HCL schema

When making schema changes:
1. Apply changes to the database using one canonical tool (prefer Atlas if available, otherwise Drizzle migrations).
2. Update the OTHER schema file to match the live state.
3. Never let the two schema definitions drift for long.

## Environment Isolation Quirk

The `execute_code` tool runs Python in an isolated sandbox. Installing packages via `pip` in a `terminal` session does NOT make them available inside `execute_code`. If you need pandas, openpyxl, or other Python packages for file conversion, either:
- Run the script via the `terminal` tool, or
- Ensure the packages are installed inside the sandbox environment (if possible).
