---
name: postgres-workbench-bootstrap
description: Bootstrap a dedicated Postgres workbench repo with catalog-based routing, Atlas schema placeholders, SQL wrappers, and agent guardrails for mixed Cortex/app-database environments.
---

# Postgres Workbench Bootstrap

Use this when the user wants a dedicated repository for database work instead of a generic MCP or universal PostgREST layer.

## When to use

Use this skill when:
- a repo should become the canonical database workbench
- the user wants SQL-over-Tailscale as the primary operating model
- agents need routing + schema discovery + SQL execution guardrails
- Atlas is desired as schema-as-code, but SQL remains the canonical execution layer

## Target model

For the workbench itself, use this split:
- workbench operations -> Atlas + raw `psql`
- no PostgREST in the workbench operating path
- no MCP unless there is a real need for a separate productised tool boundary

The workbench should treat both Cortex DBs and application DBs as SQL targets when operating from this repo.

## Repository shape

Create this structure:

- `README.md`
- `AGENTS.md`
- `.gitignore`
- `atlas.hcl`
- `catalog/databases.yaml`
- `catalog/policies.yaml`
- `schemas/<db>/schema.hcl`
- `scripts/db-resolve.sh`
- `scripts/db-query.sh`
- `scripts/db-describe.sh`
- `scripts/atlas-inspect.sh`
- `scripts/atlas-diff.sh`
- `scripts/atlas-apply.sh`
- `skills/postgres-workbench.md`
- `docs/architecture.md`
- `docs/onboarding.md`
- `docs/decisions/0001-operating-model.md`

## Canonical operating order

Agents should work in this order:
1. Read `catalog/databases.yaml`
2. Read `catalog/policies.yaml`
3. Read `schemas/<db>/schema.hcl`
4. Resolve connection data with `scripts/db-resolve.sh`
5. Execute SQL with `scripts/db-query.sh` or `scripts/db-describe.sh`
6. Use Atlas scripts only for schema inspection/diff/apply workflows

## Catalog design

`catalog/databases.yaml` should capture at least:
- `id`
- `owner`
- `purpose`
- `environment`
- `host`
- `port`
- `database`
- `schemas`
- `access_mode`
- `preferred_interface`
- `credential_source`
- `atlas_schema_path`
- optional `env_file`
- `notes`

For this pattern:
- set `access_mode: psql`
- set `preferred_interface: sql`
- avoid carrying `postgrest_url` inside the workbench catalog unless there is a separate reason outside the workbench flow

`catalog/policies.yaml` should define:
- read-only by default
- explicit write mode required
- destructive SQL requires explicit approval
- Atlas review required before DDL
- Tailscale should be checked first on connectivity failures

## Script design rules

### `db-resolve.sh`
- Read `catalog/databases.yaml`
- Return the DB metadata as JSON
- Prefer Python + PyYAML for parsing if `yq` is absent

### `db-query.sh`
- Default to read-only mode
- Accept `--write` explicitly for writes
- Accept `--sql` or `--file`
- Load local repo `.env` first if present
- Use `POSTGRES_URL` from `.env` as the base server credential source
- Allow database-specific overrides from project `.env.local` if configured
- Read credentials from explicit `PG*` env vars first, then project `.env.local`, then parse user/password from `POSTGRES_URL`
- If `tailscale` exists locally, run a connectivity check before database access
- Block keywords like `INSERT`, `UPDATE`, `DELETE`, `CREATE`, `ALTER`, `DROP`, `TRUNCATE`, `GRANT`, `REVOKE`, `COMMENT` unless `--write` is set
- Use `psql -v ON_ERROR_STOP=1 -P pager=off`

### `db-describe.sh`
- Use `db-query.sh`
- Query `information_schema.tables` for quick introspection

### Atlas scripts
- `atlas-inspect.sh` writes into `schemas/<db>/schema.hcl`
- both Atlas scripts should load local `.env` if present
- both scripts should check Tailscale first when the binary exists locally
- `atlas-apply.sh` should be conservative; first version can intentionally refuse automatic apply
- if Atlas is installed locally in the repo (for example `bin/atlas`), support `ATLAS_BIN=/abs/path/to/bin/atlas`
- for `atlas-diff.sh`, a pragmatic first implementation is:
  1. save the current local `schema.hcl`
  2. run `atlas-inspect.sh` again against live
  3. diff the before/after files with `diff -u`
  4. report "Schemas are synced, no changes to be made." when there is no diff
- this file-diff approach is acceptable when Atlas native diff is awkward in practice because of local driver/dev-url constraints or introspection quirks

### Atlas introspection quirks
- Atlas may emit invalid pseudo-table entries for some databases during inspect
- in this environment, `mnemosyne` produced bogus stubs for `event-ledger` and `timeline`
- if these appear as empty table blocks, filter them out in `atlas-inspect.sh` immediately after inspect before saving the final `schema.hcl`
- otherwise later diff/replay steps may fail on invalid SQL generation
- Atlas may also warn that triggers/functions/procedures are skipped without Pro; record that limitation rather than pretending full coverage exists

## Atlas handling

If the `atlas` binary is not installed:
- do not fake schema discovery
- create placeholder `schemas/<db>/schema.hcl` files that clearly say inspect is pending
- make the Atlas scripts fail clearly with exit 127 and a direct message
- note the limitation in `README.md`

This prevents pretending the repo already has schema-as-code when it does not.

## Documentation to write

### `README.md`
Explain:
- repo purpose
- SQL-over-Tailscale operating model
- expected flow: catalog -> Atlas -> SQL
- current tool availability (`psql`, `atlas`, optionally `tailscale`)
- local `.env` with `POSTGRES_URL` as the base connectivity source

### `AGENTS.md`
State:
- SQL is canonical for database work
- Atlas is canonical for schema discovery
- PostgREST is not part of the workbench operating model
- never guess the target DB
- never run destructive SQL without explicit approval
- read-only is default
- if access fails, check Tailscale first

### `skills/postgres-workbench.md`
Document the operating order and guardrails so Zeus can enter the repo and work without rediscovering the rules.

## Validation checklist

After bootstrapping, verify:
1. `db-resolve.sh <db-id>` returns correct JSON
2. `db-describe.sh <db-id> <name>` finds a known table
3. `db-query.sh <db-id> --sql "select ..."` succeeds in read-only mode
4. a blocked write keyword fails without `--write`
5. `atlas-inspect.sh <db-id>` fails clearly if Atlas is missing
6. the repo makes ownership boundaries visible between Cortex and app DBs

## Reusable lesson

The main failure mode was not only missing schema knowledge. It was mixing:
- routing
- ownership
- credentials
- schema discovery
- execution

This workbench pattern fixes that by making routing and policy explicit before any SQL runs.
