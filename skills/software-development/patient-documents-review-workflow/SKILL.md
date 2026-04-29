---
name: patient-documents-review-workflow
description: Update the patient documents section in vectorized-gestao-clinica to show one item per row and toggle medical review status for documents and clinical notes.
trigger: When changing the patient page documents UI, adding review toggles, or wiring status updates for gestao_clinica.documents and gestao_clinica.clinical_notes.
---

# Patient Documents Review Workflow

## Goal

On the patient page, render documents and clinical notes as vertical lists (one item per row), hide any aggregate “pending” indicator, and allow each item to toggle between `unreviewed` and `medical_review`.

## Files normally involved

- `app/(protected)/patients/[id]/page.tsx`
- `app/components/patient-page-layout.tsx`
- `app/components/patient-documents.tsx`
- `app/api/documents/[id]/route.ts`
- `app/api/clinical-notes/[id]/route.ts`

## Data requirements

### Documents
The Drizzle table already exposes `documents.status`.

### Clinical notes
The patient page SQL must explicitly select `status` from `gestao_clinica.clinical_notes`.
Without that, the UI cannot show the badge or toggle state.

Pattern used:

```sql
SELECT id, source_file, note_type, content, status, created_at
FROM gestao_clinica.clinical_notes
WHERE patient_id = ...
ORDER BY created_at DESC
```

## UI pattern

### 1. Use one row per item
In `app/components/patient-documents.tsx`, prefer:
- outer `space-y-2` list
- each item as one bordered row
- left side clickable for preview/open
- right side action button for review toggle

Avoid the old card grid if the requirement is “1 por linha”.

### 2. Remove aggregate pending info
Do not render a summary like `X pendentes` in this section when the requirement is to remove pending information.
Also do not rely on legacy status values like `unprocessed` for the patient page documents view.

### 3. Reuse the existing review status vocabulary
Use the same three values already used elsewhere in the app:
- `unreviewed`
- `ai_reviewed`
- `medical_review`

Portuguese labels used in the UI:
- `unreviewed` → `Não revisto`
- `ai_reviewed` → `Revisto por IA`
- `medical_review` → `Revisão médica`

## API pattern

### Documents endpoint
Extend `app/api/documents/[id]/route.ts` with `PATCH`.
Validate status against:

```ts
const allowedStatuses = new Set(["unreviewed", "ai_reviewed", "medical_review"]);
```

Then update `documents.status` and return the updated row.

### Clinical notes endpoint
Create `app/api/clinical-notes/[id]/route.ts` with `PATCH`.
Use the same allowed status set and update `clinical_notes.status`.
Return the updated row as `clinicalNote`.

## State-management pattern

Keep the source-of-truth arrays in `app/components/patient-page-layout.tsx`, not inside `patient-documents.tsx`.

Recommended approach:
- `currentDocs` state in the parent layout
- `currentClinicalNotes` state in the parent layout
- pass both arrays down to `PatientDocuments`
- pass callbacks back up:
  - `onDocStatusChange(docId, status)`
  - `onClinicalNoteStatusChange(noteId, status)`

When a status changes:
- update the list item in the parent state
- also update `selectedDoc` / `selectedNote` if that item is open in the side viewer

This avoids stale UI in the side panel.

## Sync pitfall

If `docs` or `clinicalNotes` come from the server page and can change after navigation/re-render, add:

```ts
useEffect(() => setCurrentDocs(docs), [docs]);
useEffect(() => setCurrentClinicalNotes(clinicalNotes), [clinicalNotes]);
```

Without this, local state can drift from refreshed server props.

## Toggle behaviour

For this workflow, the button toggles only:
- `medical_review` → `unreviewed`
- any other value → `medical_review`

This preserves `ai_reviewed` as a readable state in the badge system but the manual button still promotes to medical review.

## Verification

After changes, run at least:

```bash
npx eslint 'app/(protected)/patients/[id]/page.tsx' 'app/components/patient-documents.tsx' 'app/components/patient-page-layout.tsx' 'app/api/documents/[id]/route.ts' 'app/api/clinical-notes/[id]/route.ts'
npx tsc --noEmit
```

## Common pitfalls

- Forgetting to select `clinical_notes.status` in the patient page query
- Updating child-local state instead of parent layout state
- Updating the list but not the currently selected preview item
- Leaving old `unprocessed` / pending-summary logic in the documents section
- Returning inconsistent JSON shapes from the PATCH endpoints (`document` vs `clinicalNote`)
- Using grid cards when the requirement is explicitly one row per item
