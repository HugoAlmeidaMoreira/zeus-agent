---
name: nextjs-split-view-layout
description: Pattern for Next.js App Router pages that need a persistent side panel or split-view layout (e.g., document viewer alongside main content). Keeps data fetching in the Server Component while delegating layout state to a Client Component.
trigger: nextjs, app-router, split-view, side-panel, clinical-dashboard, document-viewer, layout-state
tags: [nextjs, react, architecture, ui-pattern]
---

# Next.js Split-View Layout Pattern

## Problem
In clinical/medical dashboards, the user often needs to view a document (PDF, markdown, form) in a persistent side panel while still seeing the main patient data. A modal (Sheet/Dialog) hides the underlying data. An inline viewer pushes content down. A true split-view is needed.

## Solution Architecture

### 1. Server Component (`page.tsx`)
- **Only responsibility**: fetch data
- **Never manages UI state** (no `useState`)
- Passes all data to a Client Layout Component

```tsx
// app/patients/[id]/page.tsx
export default async function PatientPage({ params }) {
  const patient = await db.select().from(patients).where(...);
  const docs = await db.select().from(documents).where(...);
  const notes = await db.execute(sql`SELECT ... FROM clinical_notes`);
  
  return (
    <PatientPageLayout
      patient={patient}
      docs={docs}
      clinicalNotes={notes}
    />
  );
}
```

### 2. Client Layout Component (`patient-page-layout.tsx`)
- **Manages all layout state**: `selectedDoc`, `selectedNote`, `viewerOpen`
- **Renders the split view**: main content (left) + side panel (right)
- **Provides callbacks** to children

```tsx
"use client";
export default function PatientPageLayout({ patient, docs, clinicalNotes }) {
  const [selectedDoc, setSelectedDoc] = useState(null);
  const [selectedNote, setSelectedNote] = useState(null);
  
  const viewerOpen = selectedDoc !== null || selectedNote !== null;
  
  return (
    <div className="flex h-screen">
      {/* Left: main content */}
      <div className="flex-1 overflow-y-auto">
        <PatientTabs 
          docs={docs} 
          clinicalNotes={clinicalNotes}
          onSelectDoc={setSelectedDoc}
          onSelectNote={setSelectedNote}
        />
      </div>
      
      {/* Right: side panel viewer */}
      {viewerOpen && (
        <div className="w-[45%] border-l bg-card">
          {selectedDoc && <PdfViewer doc={selectedDoc} />}
          {selectedNote && <MarkdownViewer note={selectedNote} />}
        </div>
      )}
    </div>
  );
}
```

### 3. Nested Components
- Receive callbacks as props
- Call them on user interaction (click)
- **Never** try to render the viewer themselves

```tsx
// patient-documents.tsx
export default function PatientDocuments({ docs, onSelectDoc }) {
  return (
    <button onClick={() => onSelectDoc(doc)}>
      {doc.fileName}
    </button>
  );
}
```

## Key Rules

1. **`page.tsx` stays a Server Component** — no `'use client'`, no hooks
2. **Lift viewer state to the layout component** — don't put it in tabs or child components
3. **Pass callbacks down, not viewer components up** — `onSelectDoc`, `onSelectNote`
4. **Use percentage width for the panel** — `w-[45%]` or `w-[40%]`, not fixed pixels
5. **Close button resets all selection state** — `setSelectedDoc(null); setSelectedNote(null)`

## Markdown Renderer (No Dependencies)

For clinical notes in markdown, implement a lightweight renderer without pulling in `react-markdown`:

```tsx
function MarkdownRenderer({ content }: { content: string }) {
  const lines = content.split("\n");
  const elements: React.ReactNode[] = [];
  let inList = false;
  let listItems: React.ReactNode[] = [];
  
  const flushList = () => {
    if (inList && listItems.length > 0) {
      elements.push(<ul key={...}>{listItems}</ul>);
      listItems = [];
      inList = false;
    }
  };
  
  lines.forEach((line, idx) => {
    const t = line.trim();
    if (t.startsWith("# ")) { flushList(); elements.push(<h1>{t.slice(2)}</h1>); }
    else if (t.startsWith("## ")) { flushList(); elements.push(<h2>{t.slice(3)}</h2>); }
    else if (t.startsWith("- ")) { inList = true; listItems.push(<li>{t.slice(2)}</li>); }
    else if (t === "" && inList) { flushList(); }
    else if (t !== "") {
      flushList();
      const html = t.replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>");
      elements.push(<p dangerouslySetInnerHTML={{ __html: html }} />);
    }
  });
  flushList();
  return <div>{elements}</div>;
}
```

## Pitfalls

- **Don't** use a Sheet/Dialog for the viewer if the user needs to cross-reference with main data
- **Don't** put `'use client'` in `page.tsx` just to manage layout state — split it
- **Don't** render the viewer inside the tab component — it will be constrained by the tab container width
- **Don't** forget to handle the close button properly — reset all selection state

## When to Use This vs. Other Patterns

| Pattern | When to use |
|---------|-------------|
| **Modal/Sheet** | Quick preview, no need to see underlying data |
| **Inline viewer** | Only one document type, always visible |
| **Split-view (this)** | Need to reference patient data while viewing documents |
| **Full-page viewer** | Document is the main focus, no patient context needed |
