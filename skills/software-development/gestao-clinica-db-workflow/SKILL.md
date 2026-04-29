---
name: gestao-clinica-db-workflow
description: Workflow for exploring and manipulating the vectorized-gestao-clinica PostgreSQL database safely via psql.
trigger: When working with clinical data, patient records, documents, or any table in the gestao_clinica or administrativo schemas.
---

# Gestão Clínica Database Workflow

## 1. Access Pattern

The application database is **`gestao-clinica_db`** (not `mnemosyne`).
The main application schema is **`gestao_clinica`**.

PostgREST does **NOT** expose the `gestao_clinica` schema. You must use `psql` via port-forward.

### Port-forward
```bash
kubectl port-forward -n infrastructure svc/postgres 5433:5432
```

### Credentials
```bash
kubectl get secret -n infrastructure postgres-credentials -o json | jq -r '.data | map_values(@base64d)'
```

### psql connection string
```bash
PGPASSWORD=<password> psql -h 127.0.0.1 -p 5433 -U postgres -d gestao-clinica_db
```

## 2. Key Schemas and Tables

| Schema | Key Tables | Purpose |
|--------|-----------|---------|
| `gestao_clinica` | `documents`, `scripts`, `script_sections`, `script_fields`, `patient_events`, `patient_event_values`, `patient_event_indicators`, `clinical_notes` | Application data and clinical events |
| `administrativo` | `patients`, `patient_contacts`, `v_patient_summary` | Patient master data |
| `ontology` | `event_types`, `indicators`, `variables`, `classifications` | Taxonomy and metadata ONLY |

Patient process numbers live in `administrativo.patients.process_number`.

**Important:** Operational event data (`patient_events`, `patient_event_values`, `patient_event_indicators`) lives in `gestao_clinica`. The `ontology` schema is reserved for taxonomy/metadata (event types, indicator definitions, variable definitions). Do not place patient-specific event instances in `ontology`.

## 3. Safe Data Wrangling Pattern

When doing bulk updates derived from existing column values (e.g., parsing `title` into `year`/`description`), always validate first inside a transaction with `ROLLBACK`.

### Example: Extract and preview before committing
```sql
BEGIN;
UPDATE gestao_clinica.documents
SET
  year = (regexp_match(title, '[_ ]?data [0-9]{2}\s*-[0-9]{2}\s*-([0-9]{4})'))[1]::int,
  description = trim(regexp_replace(regexp_replace(title, '^[0-9]+ ', ''), '[_ ]?data .*', ''));

SELECT COUNT(*) FILTER (WHERE year IS NOT NULL) AS filled,
       MIN(year), MAX(year)
FROM gestao_clinica.documents;
ROLLBACK;
```

Only after confirming the preview is correct, run the `UPDATE` again without `ROLLBACK`.

## 4. Linking Documents to Clinical Events

The `documents.title` encodes a relationship to a real clinical event. Link to `gestao_clinica.patient_events` via `event_id`.

### Add the foreign key
```sql
ALTER TABLE gestao_clinica.documents
ADD COLUMN event_id uuid REFERENCES gestao_clinica.patient_events(id);
```

### Match documents to events
Match by `patient_id` + date from filename + consulta type.
```sql
WITH extracted AS (
  SELECT
    d.id AS doc_id,
    d.patient_id,
    (regexp_match(d.title, '[_ ]?data ([0-9]{2})\s*-([0-9]{2})\s*-([0-9]{4})'))[3] || '-' ||
    (regexp_match(d.title, '[_ ]?data ([0-9]{2})\s*-([0-9]{2})\s*-([0-9]{4})'))[2] || '-' ||
    (regexp_match(d.title, '[_ ]?data ([0-9]{2})\s*-([0-9]{2})\s*-([0-9]{4})'))[1] AS doc_date_iso,
    CASE
      WHEN d.title LIKE '%Consulta 1%' THEN 'consulta_1'
      WHEN d.title LIKE '%Consulta 2%' THEN 'consulta_2'
    END AS consulta_type
  FROM gestao_clinica.documents d
)
UPDATE gestao_clinica.documents doc
SET event_id = pe.id
FROM extracted e
JOIN gestao_clinica.patient_events pe ON pe.patient_id = e.patient_id
JOIN ontology.event_types et ON et.id = pe.event_type_id
WHERE doc.id = e.doc_id
  AND pe.date = e.doc_date_iso::date
  AND et.name = e.consulta_type;
```

### Find unmatched documents
```sql
SELECT d.id, d.title, p.process_number
FROM gestao_clinica.documents d
LEFT JOIN administrativo.patients p ON p.id = d.patient_id
WHERE d.event_id IS NULL;
```

Typo rate in manually-named files is ~1-2%. Common issues: wrong year, wrong month, swapped consulta number.

## 5. Common SQL Regex Snippets for Document Titles

The `documents.title` field often follows the pattern: `<process_number> <Consulta N>_data DD-MM-YYYY.pdf`

Tiago's naming is consistent but not strict. Expect variations: missing underscore (`1data`), double spaces, spaces inside dates (`17 -08-2023`). The regex must be forgiving.

- Extract process number: `trim(regexp_replace(title, '^([0-9]+).*', '\1'))`
- Extract year: `(regexp_match(title, '[_ ]?data [0-9]{2}\s*-[0-9]{2}\s*-([0-9]{4})'))[1]::int`
- Extract event type: `trim(regexp_replace(regexp_replace(title, '^[0-9]+ ', ''), '[_ ]?data .*', ''))`
- Validate format (strict): `title ~ '^[0-9]+ Consulta [12][_ ]?data [0-9]{2}-[0-9]{2}-[0-9]{4}\.pdf$'`
- Validate format (loose, handles double spaces): `title ~ '^[0-9]+\s+Consulta [12][_ ]?data [0-9]{2}\s*-[0-9]{2}\s*-[0-9]{4}\.pdf$'`

### Matching documents to events — full UPDATE

Use the forgiving regex for date extraction:

```sql
WITH extracted AS (
  SELECT
    d.id AS doc_id,
    d.patient_id,
    (regexp_match(d.title, '[_ ]?data ([0-9]{2})\s*-([0-9]{2})\s*-([0-9]{4})'))[3] || '-' ||
    (regexp_match(d.title, '[_ ]?data ([0-9]{2})\s*-([0-9]{2})\s*-([0-9]{4})'))[2] || '-' ||
    (regexp_match(d.title, '[_ ]?data ([0-9]{2})\s*-([0-9]{2})\s*-([0-9]{4})'))[1] AS doc_date_iso,
    CASE
      WHEN d.title LIKE '%Consulta 1%' THEN 'consulta_1'
      WHEN d.title LIKE '%Consulta 2%' THEN 'consulta_2'
    END AS consulta_type
  FROM gestao_clinica.documents d
)
UPDATE gestao_clinica.documents doc
SET event_id = pe.id
FROM extracted e
JOIN gestao_clinica.patient_events pe ON pe.patient_id = e.patient_id
JOIN ontology.event_types et ON et.id = pe.event_type_id
WHERE doc.id = e.doc_id
  AND pe.date = e.doc_date_iso::date
  AND et.name = e.consulta_type;
```

Typical match rate is ~98%. For unmatched docs, investigate nearby dates and common typos (wrong year, month, or consulta number).

## 6. Extracting Patient Names from Local .docx Files

The folder `db-management/Doentes CDC e avalições em word/` contains files named `<process_number> <Full Name>.docx`. This is a source-of-truth for patient names when `administrativo.patients.full_name` is empty.

### Workflow

1. List and parse filenames:
```bash
ls "Doentes CDC e avalições em word" | grep -E '^[0-9]+ ' | sed 's/^\([0-9]*\) \(.*\)\.docx$/\1|\2/' > /tmp/nomes.txt
```

2. Load into a temp table via `\copy` (not `COPY`, which requires server-side file access):
```sql
CREATE TEMP TABLE temp_nomes (
  process_number text,
  full_name text
);
```
```bash
PGPASSWORD=<pass> psql -h 127.0.0.1 -p 5433 -U postgres -d gestao-clinica_db -c "\copy temp_nomes FROM '/tmp/nomes.txt' WITH (FORMAT text, DELIMITER '|')"
```

3. Update existing patients and insert missing ones:
```sql
UPDATE administrativo.patients p
SET full_name = t.full_name
FROM temp_nomes t
WHERE p.process_number = t.process_number;

-- Insert patients present in files but not yet in DB
INSERT INTO administrativo.patients (id, process_number, full_name)
SELECT gen_random_uuid(), t.process_number, t.full_name
FROM temp_nomes t
LEFT JOIN administrativo.patients p ON p.process_number = t.process_number
WHERE p.id IS NULL;
```

## 7. Converting Clinical Evaluations (.docx) to Markdown

Install pandoc and batch-convert:
```bash
sudo apt-get install -y pandoc
mkdir -p doentes-md
for f in "Doentes CDC e avalições em word"/*.docx; do
  pandoc "$f" -t markdown -o "doentes-md/$(basename "${f%.docx}").md"
done
```

Pandoc preserves structure reasonably well. The output is plain markdown with `**bold**`, simple lists, and line breaks.

## 8. Extracting Missing Metadata from Markdown Content

Some converted files have generic names like `Consulta 01.06.2023.md` with no process number. The patient name and process number are usually in the first few lines of the markdown body.

### Common patterns in the markdown header

| Pattern | Example |
|---------|---------|
| `**[Nome Numero]{.mark}**` | `**[José Paulo Morgado 302152]{.mark}**` |
| `**Nome NP: Numero**` | `**Mª Paula Domingues NP: 395434**` |
| `[NOME MAIÚSCULO Numero]{.mark}` | `[FRANCISCO FELICIANO 48576]{.mark}` |
| `**Nome Numero**` (plain) | `**João Pedro Diniz 122811**` |

### Python extraction and rename script

```python
import re
from pathlib import Path

md_dir = Path("doentes-md")
for f in sorted(md_dir.glob("*.md")):
    if re.match(r'^[0-9]', f.name):
        continue  # Already has process number

    content = f.read_text()
    name = None
    process_number = None

    # Try patterns in order
    match = re.search(r'\*\*\[(.*?)\]\{', content)
    if match:
        line = match.group(1)
        np_match = re.search(r'(\d{3,})', line)
        if np_match:
            process_number = np_match.group(1)
            name = re.sub(r'\s*NP:\s*', ' ', line)
            name = re.sub(r'\s+' + process_number + r'\s*$', '', name).strip()

    if not name:
        match = re.search(r'\[([A-Z\s]+)\s+(\d{3,})\]\{', content)
        if match:
            name = match.group(1).strip().title()
            process_number = match.group(2)

    if not name:
        match = re.search(r'\*\*([^*]+?)\s*NP:\s*(\d{3,})\*\*', content)
        if match:
            name = match.group(1).strip()
            process_number = match.group(2)

    if not name:
        match = re.search(r'\*\*([A-Z][^*]+?)\s+(\d{3,})\*\*', content)
        if match:
            name = match.group(1).strip()
            process_number = match.group(2)

    if name and process_number:
        new_name = f"{process_number} {name}.md"
        # Handle collisions if patient already has a main file
        new_path = md_dir / new_name
        counter = 1
        while new_path.exists():
            new_name = f"{process_number} {name} ({counter}).md"
            new_path = md_dir / new_name
            counter += 1
        f.rename(new_path)
```

### Edge cases to handle
- Files named `Consulta DD.MM.YYYY.md` with multiple patient evaluations inside: check if a file for that patient already exists (e.g., `1075589 José Miguel Marques Sequeira.md` already covers `Consulta 12.01.2023.md`). Rename the duplicate to include the date suffix.
- Some files start with `**[Modelo de Consulta de 6 semanas]{.underline}**` followed by `**1075589**` on the next line. The name must be resolved from the existing patient record or another file for the same process number.

## 9. Storing Markdown Clinical Notes in the Database

After converting `.docx` evaluations to markdown (see section 7), store them in a dedicated table for structured querying and full-text search.

### Table definition
```sql
CREATE TABLE gestao_clinica.clinical_notes (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  patient_id uuid REFERENCES administrativo.patients(id),
  event_id uuid REFERENCES gestao_clinica.patient_events(id),
  source_file text NOT NULL,
  note_type text NOT NULL DEFAULT 'avaliacao_cdc',
  content text NOT NULL,
  extracted_fields jsonb DEFAULT '{}',
  created_at timestamptz DEFAULT now()
);

CREATE INDEX idx_clinical_notes_patient ON gestao_clinica.clinical_notes(patient_id);
CREATE INDEX idx_clinical_notes_event ON gestao_clinica.clinical_notes(event_id);
```

### Import from local markdown files
Generate a SQL script programmatically (Python or bash) that inserts each file, resolving `patient_id` from the process number embedded in the filename:

```python
import re
from pathlib import Path

md_dir = Path("doentes-md")
with open("/tmp/import_notes.sql", "w") as sql:
    sql.write("BEGIN;\n")
    for f in sorted(md_dir.glob("*.md")):
        match = re.match(r'^(\d+)\s+', f.name)
        if not match:
            continue
        process_number = match.group(1)
        content = f.read_text().replace("'", "''")
        source = f.name.replace("'", "''")
        sql.write(f"""
INSERT INTO gestao_clinica.clinical_notes (patient_id, source_file, note_type, content)
SELECT p.id, '{source}', 'avaliacao_cdc', '{content}'
FROM administrativo.patients p
WHERE p.process_number = '{process_number}'
  AND NOT EXISTS (
    SELECT 1 FROM gestao_clinica.clinical_notes cn
    WHERE cn.patient_id = p.id AND cn.source_file = '{source}'
  );
""")
    sql.write("COMMIT;\n")
```

Then execute:
```bash
PGPASSWORD=<pass> psql -h 127.0.0.1 -p 5433 -U postgres -d gestao-clinica_db -f /tmp/import_notes.sql
```

### Expected outcome
- 217 notes imported
- ~207 distinct patients
- 0 notes without patient_id (create missing patients first if needed)

### Adding canonical review status to `clinical_notes` and `documents`

Use the same canonical workflow states already used elsewhere in the app:
- `unreviewed`
- `ai_reviewed`
- `medical_review`

For `clinical_notes`, prefer a PostgreSQL enum in `gestao_clinica`.
For `documents`, inspect dependencies first before trying to convert the column type to that enum.

#### `clinical_notes`: preferred pattern
```sql
BEGIN;

DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM pg_type t
    JOIN pg_namespace n ON n.oid = t.typnamespace
    WHERE n.nspname = 'gestao_clinica'
      AND t.typname = 'clinical_note_status'
  ) AND NOT EXISTS (
    SELECT 1
    FROM pg_type t
    JOIN pg_namespace n ON n.oid = t.typnamespace
    WHERE n.nspname = 'gestao_clinica'
      AND t.typname = 'review_status'
  ) THEN
    ALTER TYPE gestao_clinica.clinical_note_status RENAME TO review_status;
  END IF;
END
$$;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_type t
    JOIN pg_namespace n ON n.oid = t.typnamespace
    WHERE n.nspname = 'gestao_clinica'
      AND t.typname = 'review_status'
  ) THEN
    CREATE TYPE gestao_clinica.review_status AS ENUM (
      'unreviewed',
      'ai_reviewed',
      'medical_review'
    );
  END IF;
END
$$;

ALTER TABLE gestao_clinica.clinical_notes
ADD COLUMN IF NOT EXISTS status gestao_clinica.review_status;

UPDATE gestao_clinica.clinical_notes
SET status = 'unreviewed'
WHERE status IS NULL;

ALTER TABLE gestao_clinica.clinical_notes
ALTER COLUMN status SET DEFAULT 'unreviewed';

ALTER TABLE gestao_clinica.clinical_notes
ALTER COLUMN status SET NOT NULL;

COMMIT;
```

If the old enum existed with Portuguese labels, rename the values in place:
```sql
ALTER TYPE gestao_clinica.review_status RENAME VALUE 'Não processado' TO 'unreviewed';
ALTER TYPE gestao_clinica.review_status RENAME VALUE 'Processado IA' TO 'ai_reviewed';
ALTER TYPE gestao_clinica.review_status RENAME VALUE 'Revisão médica' TO 'medical_review';
```

#### `documents`: normalise values first, then inspect view dependencies
If `gestao_clinica.documents.status` already exists as `text`, first normalise the values and default:
```sql
BEGIN;

ALTER TABLE gestao_clinica.documents
ALTER COLUMN status DROP DEFAULT;

UPDATE gestao_clinica.documents
SET status = CASE status
  WHEN 'unprocessed' THEN 'unreviewed'
  WHEN 'processing' THEN 'ai_reviewed'
  WHEN 'processed' THEN 'ai_reviewed'
  WHEN 'failed' THEN 'unreviewed'
  ELSE COALESCE(status, 'unreviewed')
END;

ALTER TABLE gestao_clinica.documents
ALTER COLUMN status SET DEFAULT 'unreviewed';

COMMIT;
```

Before changing `documents.status` from `text` to `gestao_clinica.review_status`, check for dependent views/rules.
In this project, `administrativo.v_patient_summary` blocked the type change with:
```text
ERROR: cannot alter type of a column used by a view or rule
DETAIL: rule _RETURN on view administrativo.v_patient_summary depends on column "status"
```

Pragmatic rule:
- `clinical_notes.status` -> enum `gestao_clinica.review_status`
- `documents.status` -> may need to remain `text` temporarily, but must still use the same canonical values and default

Verify with:
```sql
\dT+ gestao_clinica.*
\d+ gestao_clinica.documents
\d+ gestao_clinica.clinical_notes
SELECT 'documents' AS table_name, status::text AS status, COUNT(*)::int AS total
FROM gestao_clinica.documents
GROUP BY status
UNION ALL
SELECT 'clinical_notes' AS table_name, status::text AS status, COUNT(*)::int AS total
FROM gestao_clinica.clinical_notes
GROUP BY status
ORDER BY table_name, status;
```

Important: in `vectorized-gestao-clinica`, `clinical_notes` may exist in the live DB but be missing from `src/db/schema.ts`. After changing the DB directly with `psql`, sync the local Drizzle schema:
- add `clinicalNoteStatusEnum = pgEnum("review_status", [...])`
- add `clinicalNotes` to `src/db/schema.ts`
- set `documents.status` default to `unreviewed` in `src/db/schema.ts`

`src/db/schema.hcl` may lag behind the live DB and can be incomplete. Do not assume it is authoritative; inspect the real DB first and only patch HCL when you can do it safely and consistently.

## 10. Schema Migration: Moving Event Tables from ontology to gestao_clinica

If event tables were incorrectly placed in `ontology` (which should be taxonomy-only), migrate them to `gestao_clinica`.

### Why migrate
- `ontology` should contain only metadata: `event_types`, `indicators`, `variables`, `classifications`
- `patient_events`, `patient_event_values`, `patient_event_indicators` are operational data tied to specific patients
- Keeping them in `ontology` breaks schema boundaries and complicates backups/permissions

### Migration steps

1. **Create new tables in `gestao_clinica`** with identical structure
2. **Copy data** with `INSERT INTO ... SELECT * FROM ontology.table`
3. **Add PKs and FKs** in the new schema
4. **Update external FKs**:
   - `gestao_clinica.documents.event_id` → `gestao_clinica.patient_events(id)`
   - `gestao_clinica.clinical_notes.event_id` → `gestao_clinica.patient_events(id)`
5. **Drop FKs on old tables** that point to `ontology.patient_events`
6. **Drop old tables** (views depending on them must be dropped first or use CASCADE)
7. **Recreate views** in the correct schema (e.g., `gestao_clinica.v_patient_timeline`, `administrativo.v_patient_summary`)

### Critical: Check all view dependencies before dropping

```sql
-- Find all views that reference the old tables
SELECT 
  dependent_ns.nspname AS dependent_schema,
  dependent_view.relname AS dependent_view,
  source_ns.nspname AS source_schema,
  source_table.relname AS source_table
FROM pg_depend
JOIN pg_rewrite ON pg_depend.objid = pg_rewrite.oid
JOIN pg_class AS dependent_view ON pg_rewrite.ev_class = dependent_view.oid
JOIN pg_class AS source_table ON pg_depend.refobjid = source_table.oid
JOIN pg_namespace dependent_ns ON dependent_ns.oid = dependent_view.relnamespace
JOIN pg_namespace source_ns ON source_ns.oid = source_table.relnamespace
WHERE source_table.relname IN ('patient_events', 'patient_event_values', 'patient_event_indicators')
  AND source_ns.nspname = 'ontology';
```

In this project, dependent views included:
- `ontology.v_event_indicators`
- `ontology.v_patient_timeline`
- `administrativo.v_patient_summary`

All must be recreated pointing to `gestao_clinica` tables before or during the migration.

### CRITICAL: Update all raw SQL in the Next.js codebase

Drizzle schema definitions handle schema changes automatically, but **raw SQL queries (`db.execute(sql\`...\`)`) are hardcoded strings** and will NOT update when you move tables between schemas. The app will crash at runtime with `relation "ontology.patient_events" does not exist`.

After the DB migration, search and update ALL frontend/backend files:

```bash
cd ~/git/vectorized-gestao-clinica
grep -r "ontology\.patient_events\|ontology\.patient_event_values\|ontology\.patient_event_indicators" \
  --include="*.{ts,tsx}" -l
```

Files that typically need updating:
Files that typically need updating:
- `app/(protected)/patients/[id]/page.tsx` — server component queries for stats/timeline
- `app/api/patients/route.ts` — list patients with latest event review status per event type
- `app/api/patients/[id]/events/route.ts` — GET/POST/PUT for events and values (note: `patient_event_values` appears in GET SELECT, POST INSERT, PUT DELETE/INSERT)

Replace pattern: `ontology.patient_events` → `gestao_clinica.patient_events` and `ontology.patient_event_values` → `gestao_clinica.patient_event_values`.

Verify no stale references remain:
```bash
grep -r "ontology\.patient_events\|ontology\.patient_event_values" \
  --include="*.{ts,tsx}" -n
```
If the grep returns nothing, the frontend is clean.

## 11. Materializing Default Patient Events

Some event types may need to exist for every patient by default, even without uploaded documentation yet (for example `internamento` and `avaliacao_uci`). In that case, materialize them directly in `gestao_clinica.patient_events` instead of only faking the state in dashboard queries.

### Important: trust the live DB over the Drizzle schema
In this project there was schema drift between `src/db/schema.ts` and the real table:
- real table `gestao_clinica.patient_events.created_at` is `NOT NULL` and had no default
- real table default for `review_status` was `pending`
- app code/schema suggested `createdAt.defaultNow()` and `reviewStatus.default("unreviewed")`

Before bulk inserts, inspect the live table with:
```sql
\d+ gestao_clinica.patient_events
\d+ gestao_clinica.patient_event_values
```

### Write-path pitfall: `patient_events` and `patient_event_values` may require explicit IDs and timestamps
In this project, the live DB for event writes drifted from the assumptions in the app code:
- `gestao_clinica.patient_events.id` is `NOT NULL` with no default
- `gestao_clinica.patient_events.created_at` is `NOT NULL` with no default
- `gestao_clinica.patient_event_values.id` is `NOT NULL` with no default
- `gestao_clinica.patient_event_values.created_at` is `NOT NULL` with no default
- `gestao_clinica.patient_events.review_status` default was `pending` in the live DB

If the API inserts rows without explicitly sending `id` and `created_at`, writes fail at runtime with errors like:
```text
null value in column "id" of relation "patient_event_values" violates not-null constraint
```

Pragmatic rule for API writes in this repo:
- generate UUIDs in the application layer (`randomUUID()` or equivalent)
- send `created_at` explicitly on inserts
- do not assume DB defaults exist just because the local schema suggests they do

For `patient_event_values`, use the full insert shape:
```sql
INSERT INTO gestao_clinica.patient_event_values (
  id,
  patient_event_id,
  variable_id,
  value,
  created_at
)
VALUES (...);
```

For `patient_events`, prefer the full insert shape as well:
```sql
INSERT INTO gestao_clinica.patient_events (
  id,
  event_type_id,
  patient_id,
  date,
  notes,
  created_at
)
VALUES (...);
```

### PUT semantics for event APIs
When an event update endpoint supports both full edits and review-only toggles:
- update `date` only if `date` was actually sent
- update `notes` only if `notes` was actually sent
- update `review_status` only if `reviewStatus` was actually sent
- delete and re-insert `patient_event_values` only if `values` was actually sent

Do not let a review-only toggle overwrite `date`/`notes` or wipe values by omission.

Be careful with SQL templating when a field is optional. In this codebase, interpolating an undefined `reviewStatus` into:
```sql
CASE WHEN <bool> THEN ${reviewStatus} ELSE review_status END
```
produced invalid SQL (`THEN ELSE`). Guard the interpolation explicitly, for example by sending `${reviewStatus ?? null}` inside the `THEN` branch.

### Safe idempotent insert pattern
Use `NOT EXISTS` so you only create missing rows.
Use patient timestamps for the initial event timestamps so the new rows fit the existing chronology better than `now()`.

```sql
BEGIN;

WITH target_event_types AS (
  SELECT id, name
  FROM ontology.event_types
  WHERE name IN ('internamento', 'avaliacao_uci')
),
missing_events AS (
  SELECT
    gen_random_uuid() AS id,
    tet.id AS event_type_id,
    p.id AS patient_id,
    COALESCE(p.updated_at, p.created_at)::date AS date,
    'Evento inicial por defeito'::text AS notes,
    COALESCE(p.updated_at, p.created_at) AS created_at,
    'unreviewed'::text AS review_status
  FROM administrativo.patients p
  CROSS JOIN target_event_types tet
  WHERE NOT EXISTS (
    SELECT 1
    FROM gestao_clinica.patient_events pe
    WHERE pe.patient_id = p.id
      AND pe.event_type_id = tet.id
  )
)
INSERT INTO gestao_clinica.patient_events (
  id,
  event_type_id,
  patient_id,
  date,
  notes,
  created_at,
  review_status
)
SELECT id, event_type_id, patient_id, date, notes, created_at, review_status
FROM missing_events;

COMMIT;
```

### Verify after insert
```sql
WITH target_event_types AS (
  SELECT id, name
  FROM ontology.event_types
  WHERE name IN ('internamento', 'avaliacao_uci')
)
SELECT
  tet.name,
  COUNT(*)::int AS total,
  COUNT(*) FILTER (WHERE pe.review_status = 'unreviewed')::int AS unreviewed,
  COUNT(*) FILTER (WHERE pe.review_status = 'ai_reviewed')::int AS ai_reviewed,
  COUNT(*) FILTER (WHERE pe.review_status = 'medical_review')::int AS medical_review
FROM target_event_types tet
JOIN gestao_clinica.patient_events pe ON pe.event_type_id = tet.id
GROUP BY tet.name
ORDER BY tet.name;
```

## 12. Patient-level Administrative Review Status

If the UI needs review tracking for patient master-data (dados administrativos, not clinical events), first inspect the live table before adding any column.

In this project, the live DB already stores the administrative review state in:

```sql
administrativo.patients.demographics_review_status
```

Do not assume the column is called `review_status` just because the UI or TypeScript property uses that name.

### Live DB first, schema second
Before changing the Drizzle schema or generating a migration, confirm the real table:

```sql
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_schema = 'administrativo'
  AND table_name = 'patients'
ORDER BY ordinal_position;
```

If you see `demographics_review_status`, reuse it.
Do not generate a migration adding `review_status`, or the app will crash at runtime when Drizzle selects a non-existent column.

### Correct mapping pattern
Map the application field `reviewStatus` to the DB column `demographics_review_status`.

Drizzle schema:

```ts
reviewStatus: text("demographics_review_status").notNull().default("unreviewed")
```

Raw SQL reads should alias the DB column so the frontend can keep using `review_status` in JSON:

```sql
SELECT p.demographics_review_status AS review_status
FROM administrativo.patients p;
```

Raw SQL writes should target the real column:

```sql
UPDATE administrativo.patients
SET demographics_review_status = 'medical_review'
WHERE process_number = '1057141';
```

### Aggregation
Aggregate directly from the real DB column:

```sql
SELECT
  COUNT(*)::int AS total,
  COUNT(*) FILTER (WHERE demographics_review_status = 'unreviewed' OR demographics_review_status IS NULL)::int AS unreviewed,
  COUNT(*) FILTER (WHERE demographics_review_status = 'ai_reviewed')::int AS ai_reviewed,
  COUNT(*) FILTER (WHERE demographics_review_status = 'medical_review')::int AS medical_review
FROM administrativo.patients;
```

### API pattern
The patient update endpoint should support two modes:
1. full administrative data save
2. review-only toggle

Pattern used in `app/api/patients/[id]/route.ts`:
- parse the demographic fields plus `review_status` from the request body
- detect whether any actual demographic fields were sent
- if yes, update all demographic fields plus `demographics_review_status`
- if not, update only `demographics_review_status`
- return `demographics_review_status AS review_status`

This avoids forcing the client to resend the full form just to mark or unmark medical review, while keeping the frontend payload stable.

### UI pattern
On the patient page:
- keep fetched data in the server `page.tsx`
- pass the patient into a client layout component
- keep a local `currentPatient` state in the client layout
- render `Dados Administrativos` as its own tab
- let `PatientDemographicsForm` receive `onUpdate(updatedPatient)` and update `currentPatient`
- put the administrative review toggle inside the administrative form/card

This allows the administrative tab to update review state and patient fields immediately without a page refresh.

### Migration pitfall
If an incorrect migration was already generated to add `administrativo.patients.review_status`, convert it to a no-op or otherwise neutralize it before applying it. Keep the migration journal consistent with the files present.

### When editing patient administrative data
Saving the administrative form does not need to force `medical_review` automatically.
Persist whatever `review_status` the UI sends, but write it into `demographics_review_status`.

For a dedicated review button, toggle explicitly between:

```sql
demographics_review_status = 'medical_review'
```

and

```sql
demographics_review_status = 'unreviewed'
```

This keeps the semantics explicit and aligned with the event review workflow.

## 13. Patient list review-status debugging

When the `/patients` table shows unexpected status chips, separate three different concepts before changing the DB:

1. administrative review status (`administrativo.patients.demographics_review_status`)
2. field completeness (`full_name`, `date_of_birth`, `sex` present or not)
3. latest event review status per event type (`gestao_clinica.patient_events.review_status`)

### Known failure mode
In this project, the `Dados Adm.` column in `/patients` was showing a derived completeness badge (`Completo` / `Incompleto`) instead of the real administrative review status. That made many rows look "completed" even though the DB status was still `unreviewed`.

Rule:
- if the column is meant to show review workflow state, bind it to `demographics_review_status`
- do not reuse completeness booleans for review-state UI

### Missing event row vs missing status
If `consulta_1` or `consulta_2` appears with no status in the grid, inspect whether the problem is:
- a row exists with a bad `review_status`, or
- no `patient_events` row exists at all for that patient + event type

In this project the second case was the real cause for many blanks.
The table had no `NULL review_status` rows; instead many patients simply had no `consulta_2` row, so the app's `LEFT JOIN` produced `NULL` in the aggregated payload.

Audit pattern:
```sql
SELECT et.name,
       COUNT(*) FILTER (WHERE pe.id IS NULL)::int AS missing_event_rows,
       COUNT(*) FILTER (WHERE pe.id IS NOT NULL)::int AS existing_event_rows,
       COUNT(*) FILTER (WHERE pe.review_status IS NULL)::int AS null_status_rows
FROM administrativo.patients p
CROSS JOIN ontology.event_types et
LEFT JOIN gestao_clinica.patient_events pe
  ON pe.patient_id = p.id AND pe.event_type_id = et.id
GROUP BY et.name
ORDER BY et.name;
```

### List API behaviour for expected defaults
If the product expectation is that the `/patients` grid should always display the default workflow state even when the event row does not yet exist, make the fallback explicit in the list API:

```sql
jsonb_object_agg(
  et.id::text,
  COALESCE(le.review_status, 'unreviewed')
) FILTER (WHERE et.id IS NOT NULL) AS event_reviews
```

This is a presentation-layer fallback for the list view. It does not materialize missing event rows.

### Stable latest-event selection
When building the `latest_events` CTE for the list, do not sort only by `date DESC`. Use a stable tie-break:

```sql
ORDER BY patient_id, event_type_id, date DESC, created_at DESC, id DESC
```

Without this, two events on the same date can produce inconsistent list status.

### Schema drift warning
The live DB in this project had drift:
- `gestao_clinica.patient_events.review_status` default in the real DB was `pending`
- application code and product expectation were aligned around `unreviewed`
- existing rows inspected during debugging were all `unreviewed`

Rule:
- fix the list/UI bug first if that is what users are seeing
- then schedule a separate migration to align the live DB default with the canonical application value
- do not assume the live default matches Drizzle or UI labels

## 14. Auditing external annual CSV datasets before schema changes

When a new external dataset arrives (for example a yearly SMI export), do **not** create the final table immediately.
First compare the incoming columns against the live `ontology.variables` inventory and only then decide what belongs in:
- existing variables
- new ontology variables
- a raw staging table
- normalized child tables

### Recommended workflow

1. Inspect the CSV header and sample rows locally first.
   - confirm delimiter and encoding (`;`, often UTF-8 with BOM)
   - count columns and rows
   - infer rough data types: date / numeric / boolean / text
   - capture representative values for low-cardinality columns

2. Inspect the live DB, not just `src/db/schema.ts`.
   - inventory `ontology.variables`
   - include `name`, `name_display`, `section`, `subsection`, `variable_type`, `input_type`, `unit`
   - include `ontology.classifications` labels because many CSV categorical columns only match at the value level

3. Build a column-to-variable audit before proposing schema changes.
   Split findings into four buckets:
   - direct match
   - partial / ambiguous match
   - related but not equivalent
   - no current coverage

4. Prefer a raw-first ingestion strategy.
   If a CSV mixes demographics, episode data, procedures, microbiology, complications, and outcomes, create a raw import table first instead of forcing everything into `ontology.variables` or one wide canonical table.

5. Only after the audit, design the canonical model.
   Common outcome:
   - keep identifiers and dates mapped to existing variables
   - create new domain-specific tables for repeated child entities (`diagnoses`, `procedures`, `adverse_events`)
   - add new ontology variables only for fields that should be reused by the application UI, filters, or event forms

### Example mappings found in SMI annual CSV review

Direct reuse candidates:
- `Processo` -> `num_processo`
- `DN` -> `data_nascimento`
- `Sexo` -> `sexo`
- `Adm_HFF` -> `data_ad_hospital`
- `Adm_UCIP` -> `data_ad_smi`

Typical ambiguity examples:
- `Dias_Int` may mean total hospitalization length or SMI stay length
- `Data_Alta` may mean hospital discharge or SMI discharge
- `Ventilação` may or may not mean invasive mechanical ventilation
- `Motivo Admissão` may look close to `tipo_doente` but values may not align 1:1

Typical “related but not equivalent” examples:
- incoming numeric severity scores vs existing threshold/binary fields
  - `SAPS_II` is not the same thing as `apache_gt14`
  - `APACHE_II` numeric score is not the same thing as a boolean threshold field
  - `Dias_Vent` is not the same thing as `vmi_gt3d`

### Heuristic for deciding table shape

If the incoming dataset contains numbered repeating columns such as:
- `Diag1..Diag7`
- `Cirurgia 1..4`
- `Efeito Adverso 1..3`

that is usually a sign the canonical model should use child tables instead of fixed repeated columns.
Keep the numbered columns in raw staging, then normalize later.

### Practical rule

Do not treat approximate semantic similarity as a match.
If a field differs in unit, threshold, time horizon, or meaning, classify it as `related but not equivalent` and keep it out of automated mapping until a human decision is made.

### Recommended staging schema for annual SMI deliveries

When the immediate goal is “accept the yearly file now, normalize later”, use a two-table staging pattern in `gestao_clinica`.

#### 1. Import batch table

```sql
CREATE TABLE gestao_clinica.smi_import_batches (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  source_name text NOT NULL,
  source_year integer,
  source_file_name text,
  source_sha256 text,
  imported_at timestamptz NOT NULL DEFAULT now(),
  imported_by text,
  notes text,
  total_rows integer,
  raw_metadata jsonb NOT NULL DEFAULT '{}'::jsonb
);
```

Recommended extra constraint/index:
```sql
CREATE UNIQUE INDEX idx_smi_import_batches_source_sha256
  ON gestao_clinica.smi_import_batches (source_sha256)
  WHERE source_sha256 IS NOT NULL;
```

Important import pitfall:
- this is a partial unique index, not a plain table-level unique constraint
- in PostgreSQL, `INSERT ... ON CONFLICT (source_sha256)` may fail with:
  `there is no unique or exclusion constraint matching the ON CONFLICT specification`
- for this repo, the safe idempotent pattern was:
  1. compute `source_sha256`
  2. `SELECT id FROM gestao_clinica.smi_import_batches WHERE source_sha256 = ...`
  3. if found: `UPDATE` the batch metadata, `DELETE` existing `smi_episode_staging` rows for that `import_batch_id`, then re-insert the file rows
  4. if not found: `INSERT` a new batch, then insert staging rows

This avoids relying on conflict inference against the partial index and gives a clean re-import path when the same annual file is loaded again.

Purpose:
- one row per delivered file
- detect duplicate imports via `source_sha256`
- store provenance and batch-level notes

#### 2. Raw episode staging table

```sql
CREATE TABLE gestao_clinica.smi_episode_staging (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  import_batch_id uuid NOT NULL REFERENCES gestao_clinica.smi_import_batches(id) ON DELETE CASCADE,
  source_row_number integer NOT NULL,
  source_year integer,
  process_number text,
  patient_id uuid REFERENCES administrativo.patients(id) ON DELETE SET NULL,
  raw_payload jsonb NOT NULL,
  matched_event_id uuid REFERENCES gestao_clinica.patient_events(id) ON DELETE SET NULL,
  mapping_status text NOT NULL DEFAULT 'pending',
  mapping_notes text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT smi_episode_staging_mapping_status_check CHECK (
    mapping_status IN ('pending', 'matched_patient', 'matched_event', 'reviewed', 'ignored', 'error')
  ),
  CONSTRAINT smi_episode_staging_batch_row_unique UNIQUE (import_batch_id, source_row_number)
);
```

Recommended indexes:
```sql
CREATE INDEX idx_smi_episode_staging_import_batch
  ON gestao_clinica.smi_episode_staging(import_batch_id);
CREATE INDEX idx_smi_episode_staging_process_number
  ON gestao_clinica.smi_episode_staging(process_number);
CREATE INDEX idx_smi_episode_staging_patient_id
  ON gestao_clinica.smi_episode_staging(patient_id);
CREATE INDEX idx_smi_episode_staging_mapping_status
  ON gestao_clinica.smi_episode_staging(mapping_status);
CREATE INDEX idx_smi_episode_staging_source_year
  ON gestao_clinica.smi_episode_staging(source_year);
CREATE INDEX idx_smi_episode_staging_raw_payload_gin
  ON gestao_clinica.smi_episode_staging USING gin(raw_payload);
```

Purpose:
- one row per CSV line
- preserve the original source row intact in `raw_payload`
- store early linkage to patient/event when known, without forcing normalization yet

#### Why this worked well in this repo

It let the project move forward without prematurely deciding:
- whether `Data_Alta` means hospital discharge or SMI discharge
- whether `Dias_Int` means total stay or SMI stay
- whether approximate fields like `Ventilação` really map to existing binary ontology variables

It also kept the import path simple for future years (`smi 2023.csv`, `smi 2024.csv`, etc.) while leaving room for later normalization into child tables like diagnoses, procedures, microbiology, or adverse events.

### Repo-specific migration rule for this pattern

In this repo, the safe order was:
1. apply DDL directly with `psql`
2. verify live tables with `\d+`
3. sync `src/db/schema.ts`
4. sync `src/db/schema.hcl`

Reason:
- there may be no safe existing Drizzle migration history for incremental generation
- `drizzle-kit generate` can create an unsafe baseline when no prior migration chain exists
- live DB inspection is more reliable than assuming local schema files are authoritative

### Drizzle / Atlas sync note

For the staging tables, `src/db/schema.ts` can model the tables and btree indexes cleanly.
The raw GIN index on `jsonb` may need to stay documented in SQL/HCL even if application code never touches it directly.
If `schema.hcl` is only a partial model of the database, update it carefully and only if referenced tables already exist in that HCL model.

## 15. Pitfalls

- Do not try to use PostgREST for `gestao_clinica` tables. It will return `Invalid schema`.
- Do not assume the database is `mnemosyne`. The clinical app has its own DB (`gestao-clinica_db`).
- Patient data spans schemas: `gestao_clinica` (events, documents, notes), `administrativo` (patients).
- Operational event tables belong in `gestao_clinica`, not `ontology`.
- Tiago's filenames are **not machine-perfect**. Expect ~2% with typos (wrong year, month swapped, missing underscore, double spaces). The regex must use `\s*` generously.
- For bulk-loading local file data into Postgres, use `\copy` (client-side) not `COPY` (server-side). The server process cannot read your local `/tmp/`.
- When event-matching fails, check for off-by-one errors in day/month/year before concluding the event is missing.
- Pandoc produces clean markdown but the **filename** may not survive metadata. Some `.docx` files have generic Word titles like "Consulta 01.06.2023" as the document title, which becomes the filename after conversion. Always extract the real process number from the markdown body.
- Some `.docx` files contain **multiple patient evaluations** in a single document (separated by horizontal rules). The converted markdown keeps them together. When importing to a structured table, split on `---` or handle as a single multi-patient note.
- Always check view dependencies (`v_patient_timeline`, `v_patient_summary`, `v_event_indicators`) before dropping or moving event tables. They will block DROP TABLE if not handled.