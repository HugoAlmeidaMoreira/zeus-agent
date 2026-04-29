---
name: csv-to-normalized-db-migration
description: Migrate flat/wide CSV data (especially medical/clinical) into a normalized PostgreSQL EAV + event-sourcing schema using Drizzle/Postgres. Handles column mapping, ontology alignment, value normalization, and SQL generation.
category: data-science
---

# CSV to Normalized DB Migration

## When to Use
- You have a flat/wide CSV where each row represents a patient + multiple events + repeated measurements (e.g., `_Cons1`, `_Cons2` suffixes).
- The target database uses a normalized model: `patients` master table + `patient_events` timeline + `patient_event_values` EAV values.
- You need to reconcile CSV columns with an existing ontology (`variables`, `classifications`, `indicators`, `event_types`).

## Workflow

### 1. Extract CSV Columns
```python
import csv
with open('data.csv', 'r', encoding='utf-8-sig') as f:
    reader = csv.DictReader(f)
    headers = reader.fieldnames
    sample_rows = [next(reader) for _ in range(3)]
```
Always use `utf-8-sig` to strip the BOM (`\ufeff`) that Excel exports add.

### 2. Query Target Ontology
Connect via `psql` or the app's `DATABASE_URL` to inspect:
```sql
SELECT name, id, variable_type, input_type FROM ontology.variables ORDER BY name;
SELECT name, id FROM ontology.event_types ORDER BY name;
SELECT v.name, c.code, c.label_pt FROM ontology.classifications c JOIN ontology.variables v ON v.id = c.variable_id;
```

### 3. Build COLUMN_MAP
Map each CSV column to `(variable_name, target_event)`:
- `"patient"` for master data fields
- `"internamento"`, `"consulta_1"`, `"consulta_2"` for event-scoped fields
- Suffix stripping: `Disfagia_Cons1` and `Disfagia_Cons2` both map to `disfagia` but different events.

```python
COLUMN_MAP = {
    "Num_Processo": ("num_processo", "patient"),
    "Disfagia_Cons1": ("disfagia", "consulta_1"),
    "Disfagia_Cons2": ("disfagia", "consulta_2"),
    # ...
}
```

### 4. Identify Missing Variables
Compare CSV columns against ontology. Create missing entries with deterministic UUIDs or `gen_random_uuid()`.

### 5. Normalize Values
```python
def normalize_value(val, variable_name):
    if val is None: return None
    val = str(val).strip()
    if val in ("", "nan", "NaT", "None"): return None
    # Dates exported as 0 or "0.0" mean NULL
    if val in ("0", "0.0"):
        if variable_name.startswith("data_"): return None
        if variable_name == "status": return None
        if variable_name in ("justificacao", "nao_psiquiatria_motivo"): return None
    # Strip Excel float artifacts
    if re.match(r"^-?\d+\.0$", val): val = val[:-2]
    # Normalize date values to ISO YYYY-MM-DD
    if variable_name.startswith("data_"):
        m = re.match(r"(\d{4}-\d{2}-\d{2})", val)
        return m.group(1) if m else None
    return val
```

### 6. Handle Special Aggregations
- **Binary columns → multiselect**: If the CSV has boolean columns (`Neurologia`, `Psiquiatria`, etc.) that map to a single `multiselect` variable, aggregate them:
```python
refs = []
for col, ref_code in REF_COLS.items():
    if normalize_value(row.get(col), "referenciacoes") == "1":
        refs.append(ref_code)
if refs:
    event_values[target_evt].append(("referenciacoes", ",".join(refs)))
```
- **Follow-up variables routing**: Variables like `pics_motor`, `total_follow_up` should attach to the *most recent* event available (`consulta_2` > `consulta_1` > `internamento`).
- **Fallback fields**: If `altura`/`peso_admissao` are tied to `internamento` but no hospitalization event exists, fallback to `consulta_1`.

### 7. Generate SQL
Use PL/pgSQL `DO $$` blocks to handle idempotent inserts.

**Important — generate UUIDs in SQL, not Python:**
Generating event IDs in Python (`uuid.uuid4()`) and embedding them in the SQL makes re-runs unsafe if a previous execution partially succeeded. Instead, use deterministic IDs or `gen_random_uuid()` inside the SQL:

```sql
-- Prefer deterministic event IDs (hash of natural key)
INSERT INTO ontology.patient_events (id, event_type_id, patient_id, date, notes, created_at)
VALUES (
  uuid_generate_v5(uuid_ns_oid(), 'event|' || patient_process_number || '|consulta_1|' || event_date),
  'a0c6f437-...', v_pid, '2024-03-14', NULL, NOW()
)
ON CONFLICT (id) DO NOTHING;

-- Or use gen_random_uuid() directly in SQL for one-off migrations
INSERT INTO ontology.patient_events (id, event_type_id, patient_id, date, notes, created_at)
VALUES (gen_random_uuid(), 'a0c6f437-...', v_pid, '2024-03-14', NULL, NOW());
```

Full pattern:
```sql
INSERT INTO administrativo.patients (...) VALUES (...) ON CONFLICT (process_number) DO NOTHING;
DO $$ DECLARE v_pid uuid := (SELECT id FROM administrativo.patients WHERE process_number = '...');
BEGIN
  INSERT INTO ontology.patient_events (id, ...) VALUES (gen_random_uuid(), ...);
  INSERT INTO ontology.patient_event_values (id, patient_event_id, variable_id, value, created_at)
    SELECT gen_random_uuid(), event_id, v.id, value, NOW()
    FROM ontology.variables v WHERE v.name = '...';
END $$;
```

### 8. Validation Checks
Before running the migration:
```bash
# Count rows in CSV
wc -l data.csv

# Check for rows with hospitalization data
grep -c "Data_Ad_SMI" data.csv

# Verify generated SQL syntax
psql ... -f migrate.sql --dry-run  # or run inside a transaction and ROLLBACK first
```

## Pre-Migration: Identify Calculated Columns
Flat clinical exports often contain **derived/calculated columns** alongside raw measurements. Before mapping, scan for columns that are computable from other fields (e.g., `Idade`, `IMC_*`, `Dias_*`, `Desvio_time_*`).

Do NOT import these as `patient_event_values` — they belong in `ontology.indicators` and should be recalculated by views or triggers:

```python
CALCULATED_PATTERNS = {
    "Idade": "idade",
    r"IMC_[A-Za-z_]+": "imc",
    r"Dias_[A-Za-z_]+": "dias_internamento",
    r"Desvio_time_[A-Za-z_]+": "desvio_tempo",
}
```

After migration, create indicator views that compute them dynamically:
```sql
CREATE OR REPLACE VIEW ontology.v_event_indicators AS
SELECT
  pe.id AS event_id,
  p.process_number,
  pe.event_type_id,
  et.name AS event_type,
  p.data_nascimento,
  pe.date AS event_date,
  DATE_PART('year', AGE(pe.date, p.data_nascimento))::int AS idade,
  -- pull raw values via subqueries or LATERAL joins
  ...
FROM ontology.patient_events pe
JOIN ontology.event_types et ON et.id = pe.event_type_id
JOIN administrativo.patients p ON p.id = pe.patient_id;
```

## Post-Migration: Link External Documents (MinIO/S3)
Clinical workflows often have documents already stored in object storage. After patient migration, link them by extracting the foreign key from filenames:

```python
import boto3, re, csv
from collections import defaultdict

s3 = boto3.client('s3', endpoint_url='http://minio:9000', ...)
paginator = s3.get_paginator('list_objects_v2')
files = []
for page in paginator.paginate(Bucket='gestao-clinica-assets'):
    files.extend(page.get('Contents', []))

# Extract process number from filename: "12345_consulta.pdf"
proc_re = re.compile(r"(\d+)")
rows = []
existing_keys = set()  # SELECT key FROM gestao_clinica.documents
for obj in files:
    key = obj['Key']
    m = proc_re.search(key)
    if not m: continue
    proc = m.group(1)
    if key in existing_keys: continue
    rows.append((proc, key, 'unprocessed', 'consulta_1'))

# Bulk insert via COPY or executemany
```

Pitfall: `documents.key` may lack a UNIQUE constraint. If `ON CONFLICT (key)` fails, do a pre-flight `SELECT key FROM gestao_clinica.documents WHERE key = ANY(...)` and filter the insert set instead.

## Post-Migration: Schema Documentation (DB Wiki)
Instead of local markdown files, document the schema directly in PostgreSQL using `COMMENT ON`. This lives with the database (backup/restore carry comments) and is accessible via `psql \d+` or any GUI client.

```sql
COMMENT ON SCHEMA ontology IS 'Catalogo de variaveis, classificacoes, tipos de evento e indicadores calculados.';
COMMENT ON TABLE ontology.patient_events IS 'Timeline do doente. Cada linha e um momento clinico concreto.';
COMMENT ON COLUMN ontology.patient_events.event_type_id IS 'FK para event_types. Define o tipo de momento.';
```

Query comments programmatically:
```sql
SELECT n.nspname AS schema, c.relname AS table, obj_description(c.oid) AS description
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind = 'r' AND n.nspname IN ('ontology', 'administrativo')
ORDER BY n.nspname, c.relname;
```

## Post-Migration: Views as API Layer
Instead of querying normalized EAV tables directly from the frontend, create **read-only views** that denormalize the data the UI needs. This keeps the app database-centric and avoids heavy client-side joins.

Examples:

**Patient summary card** (counts + latest event):
```sql
CREATE OR REPLACE VIEW administrativo.v_patient_summary AS
SELECT
  p.id, p.process_number, p.nome, p.genero, p.data_nascimento,
  COUNT(DISTINCT pe.id) AS total_events,
  COUNT(DISTINCT d.id) AS total_documents,
  COUNT(DISTINCT CASE WHEN d.status = 'unprocessed' THEN d.id END) AS pending_documents,
  MAX(pe.date) AS last_event_date
FROM administrativo.patients p
LEFT JOIN ontology.patient_events pe ON pe.patient_id = p.id
LEFT JOIN gestao_clinica.documents d ON d.patient_id = p.id
GROUP BY p.id, p.process_number, p.nome, p.genero, p.data_nascimento;
```

**Timeline view** (events with values as JSON):
```sql
CREATE OR REPLACE VIEW ontology.v_patient_timeline AS
SELECT
  pe.id AS event_id,
  pe.patient_id,
  pe.date AS event_date,
  et.name AS event_type,
  jsonb_object_agg(v.name, pev.value) FILTER (WHERE v.name IS NOT NULL) AS values
FROM ontology.patient_events pe
JOIN ontology.event_types et ON et.id = pe.event_type_id
LEFT JOIN ontology.patient_event_values pev ON pev.patient_event_id = pe.id
LEFT JOIN ontology.variables v ON v.id = pev.variable_id
GROUP BY pe.id, pe.patient_id, pe.date, et.name;
```

The app queries these views exactly like tables — Drizzle and PostgREST treat them as first-class relations.

## Pitfalls
- **BOM**: Excel CSVs start with `\ufeff`. Use `utf-8-sig` or strip the first bytes.
- **Dates as floats**: Excel exports dates as `1955-12-25 00:00:00` or serial numbers. Always regex-extract `YYYY-MM-DD`.
- **Zero ambiguity**: `0` can mean "no" (binary), NULL (dates), or a valid classification code. Inspect per-variable semantics.
- **Missing events**: A flat CSV row may only have `consulta_1` data and no `internamento`. The script must skip event creation if all mapped fields are NULL.
- **Permission**: `patient_events` and child tables may require higher privileges than read-only. Use `psql` with the admin user (`postgres` or an app user with `INSERT` on all schemas). `gestao-clinica_user` may lack write access to `administrativo` or `ontology` depending on RLS/grants.
- **Partial runs / duplicate IDs**: If the SQL fails mid-transaction with `duplicate key`, the whole transaction rolls back but a previous run may already exist. Always check counts before running:
  ```bash
  psql ... -c "SELECT count(*) FROM administrativo.patients;"
  psql ... -c "SELECT count(*) FROM ontology.patient_events;"
  ```
  If counts already match the CSV row count, do not re-run blindly.

## Example Files
- `migrate_csv.py` — Python generator script
- `migrate_csv.sql` — Generated SQL for `psql -f`

## Related Skills
- `drizzle-schema-management` — For updating the Drizzle schema.ts after adding new ontology variables.
- `postgres-workbench-bootstrap` — For direct DB interaction patterns.
