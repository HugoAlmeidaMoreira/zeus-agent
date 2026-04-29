---
name: raw-source-ontology-field-mapping
description: Import raw yearly CSV sources with header drift into staging, build a canonical source-field catalogue, and create a protected UI/API to map source fields to ontology.variables in vectorized-gestao-clinica.
trigger: When a new raw data source arrives yearly as CSV/Excel with changing columns and you need a reviewable mapping layer before normalising into the clinical ontology.
---

# Raw source → ontology field mapping

Use this in `vectorized-gestao-clinica` when a source like SMI arrives as annual CSVs with schema drift and the team needs a manual mapping step to `ontology.variables`.

## Decision pattern

Do not jump straight to a final canonical clinical table that mirrors the CSV.

Use a 3-layer flow:
1. raw import batches
2. raw row staging
3. source-field catalogue + field→ontology mapping

This keeps the import faithful to the files received and lets clinicians map fields before normalisation.

## Data model

### Existing raw staging
- `gestao_clinica.smi_import_batches`
- `gestao_clinica.smi_episode_staging`

### Add source-field catalogue
Create a table like:
- `gestao_clinica.smi_source_fields`

Recommended columns:
- `id`
- `source_name`
- `field_key` — stable normalised key
- `canonical_label`
- `field_labels jsonb` — all label variants seen across years
- `years_present jsonb`
- `positions_by_year jsonb`
- `first_seen_year`
- `last_seen_year`
- `notes`
- timestamps
- unique `(source_name, field_key)`

### Add mapping table
Create a table like:
- `gestao_clinica.smi_field_variable_mappings`

Recommended columns:
- `id`
- `smi_source_field_id`
- `ontology_variable_id` nullable
- `mapping_status`
- `mapping_notes`
- `mapped_by`
- `mapped_at`
- timestamps
- unique `(smi_source_field_id)`

Recommended statuses:
- `pending`
- `mapped`
- `ignored`
- `needs_new_variable`

When using `mapped`, require `ontology_variable_id`.

## Importer behaviour

Update the importer so it does more than load rows.

### 1. Detect delimiter
Do not assume comma-separated files.

For the SMI files, the real delimiter was `;`. A naive `csv.DictReader` without delimiter detection treated the entire header line as a single column.

Use a helper that compares `;` vs `,` counts in the first line.

### 2. Normalise source field keys
Build a stable `field_key` from the raw label:
- strip accents with `unicodedata.normalize`
- lowercase
- replace non-alphanumerics with `_`
- collapse repeated `_`

Example:
- `Data Alta Clínica do SMI` → `data_alta_clinica_do_smi`

This key should be the durable join point for mappings, not the raw label.

### 3. Build catalogue across years
Before or during import, scan all yearly files and aggregate by normalised `field_key`:
- all labels observed
- years present
- position by year
- first and last year seen

### 4. Upsert source fields
For each aggregated field:
- insert/update `smi_source_fields`
- ensure there is a row in `smi_field_variable_mappings`
- default new mappings to `pending`

### 5. Keep row import idempotent
For batches, use the existing approach:
- find batch by checksum
- update existing batch or insert new batch
- delete and rehydrate staging rows for that batch

Do not depend on `ON CONFLICT (source_sha256)` when the DB uses a partial unique index that may not serve as a usable conflict target.

## UI pattern

Create a protected page like:
- `/smi/mappings`

Also add a sidebar link under the source group.

### Page should show
- summary cards: total, mapped, pending, ignored, needs new variable
- searchable table of source fields
- years present
- label variants
- current mapping status
- currently linked ontology variable, if any
- detail/editor panel for the selected field

### Editor controls
- status select
- ontology variable select
- notes textarea
- save button

### Good UX constraints
- if status is `mapped`, require ontology variable
- if status is not `mapped`, clear ontology variable on save
- keep labels and year-presence visible so the clinician understands drift across years

## API pattern

Create an endpoint like:
- `app/api/smi/mappings/route.ts`

### GET should return
- source fields joined with current mapping
- ontology variables available for selection
- summary counts by status

### POST should
- upsert the mapping row by `smi_source_field_id`
- set `mapped_at` when status is not `pending`
- update `updated_at`

## Testing pattern in this repo

This repo has no ready Jest/Vitest UI setup. For features like this:
1. write a `node:test` file that asserts the existence and source contracts of the new page/API/schema/importer changes
2. run it and watch it fail first
3. implement
4. run it again
5. run `tsx` import smoke tests for changed files

Useful checks:
- sidebar contains `/smi/mappings`
- page fetches `/api/smi/mappings`
- SQL/schema define `smi_source_fields` and `smi_field_variable_mappings`
- importer writes to both tables

## Verification checklist

- SQL applied successfully with `psql -f`
- importer runs successfully against the real DB
- source-field catalogue has the expected count
- mapping table has one row per source field
- status distribution is sensible, usually all `pending` at first load
- `node --test tests/<feature>.test.mjs` passes
- `npx tsx -e "import ..."` passes

## Pitfalls

1. SMI annual files used `;`, not `,`.
2. Header drift exists across years; map by normalised `field_key`, not by raw label only.
3. Preserve raw row staging even after introducing the field catalogue.
4. Keep the mapping layer separate from final ontology-normalised ingestion.
5. Sync `src/db/schema.ts` and `src/db/schema.hcl` when adding DB tables via raw SQL.
6. In this repo, source-level `node:test` plus `tsx` smoke tests is the practical validation path for navigation/API/page additions.
