---
title: Clinical Script Database Mapping
name: clinical-script-database-mapping
description: |
  Workflow end-to-end para converter guiões de entrevista clínica (ficheiros .docx)
  numa estrutura configurável na base de dados PostgreSQL do projeto
  vectorized-gestao-clinica e apresentá-los na UI. Mapeia campos do guião para
  variables da ontology, cria scripts/sections/fields em gestao_clinica, constrói
  API route e componente React dinâmico, e mantém o modelo EAV para os dados dos
  doentes.
trigger: |
  Quando for necessário converter um guião clínico (ex: .docx de consulta,
  checklist de follow-up) para tabelas na DB do gestao-clinica e/ou criar a
  UI/API dinâmica para o renderizar.
---

# Clinical Script Database Mapping

## 1. Contexto do Schema

A base de dados `gestao-clinica_db` usa um modelo EAV (Entity-Attribute-Value)
para dados clínicos:

- `ontology.variables` — dicionário central de campos (nome técnico, label PT,
  tipo, input widget, secção)
- `ontology.classifications` — opções para variables do tipo `classification`
- `ontology.event_types` — tipos de evento: `internamento`, `consulta_1`,
  `consulta_2`
- `ontology.patient_events` — cada consulta/internamento concreto de um doente
- `ontology.patient_event_values` — respostas EAV (FK evento + FK variable +
  valor em texto)
- `gestao_clinica.scripts` — definição do guião/template
- `gestao_clinica.script_sections` — secções dentro do guião
- `gestao_clinica.script_fields` — campos/perguntas, ligados a `variables`

## 2. Extrair Texto de .docx (Sem Dependências)

Se `python-docx` não estiver disponível, usar fallback nativo:

```python
import zipfile
import xml.etree.ElementTree as ET

def get_text_from_docx(docx_path):
    with zipfile.ZipFile(docx_path, 'r') as z:
        xml_content = z.read('word/document.xml')
    tree = ET.fromstring(xml_content)
    ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
    text_parts = []
    for paragraph in tree.findall('.//w:p', ns):
        para_text = [node.text for node in paragraph.findall('.//w:t', ns) if node.text]
        if para_text:
            text_parts.append(''.join(para_text))
    return '\n'.join(text_parts)
```

## 3. Aceder ao PostgreSQL no Cluster

O serviço `postgres` corre no namespace `infrastructure`. Fazer port-forward
para o host local:

```bash
kubectl port-forward -n infrastructure svc/postgres 5433:5432 --address 0.0.0.0
```

**Pitfall:** O nome da base de dados é `gestao-clinica_db`, não `mnemosyne`.

**Pitfall:** O utilizador da app é `gestao-clinica_user` (com hífen). Usar
aspas no SQL: `"gestao-clinica_user"`.

**Pitfall:** O schema `gestao_clinica` requer permissões `GRANT USAGE` e
`GRANT SELECT/INSERT/UPDATE/DELETE` para o utilizador da app aceder via
PostgREST.

## 4. Workflow de Mapeamento

### Passo 1 — Criar Variables em Falta

Mapear cada campo do guião para `ontology.variables`. Usar `ON CONFLICT (name)
DO NOTHING` porque `name` tem UNIQUE constraint.

```sql
INSERT INTO ontology.variables (id, name, name_display, section, variable_type, input_type, created_at)
VALUES (gen_random_uuid(), 'nome_campo', 'Label PT', 'Secção', 'binary', 'radio', now())
ON CONFLICT (name) DO NOTHING;
```

Tipos de `variable_type`: `text`, `date`, `binary`, `quantitative`,
`classification`.

Tipos de `input_type`: `text`, `textarea`, `number`, `date`, `radio`, `select`,
`multiselect`.

### Passo 2 — Criar Classifications

Para variables do tipo `classification`, inserir as opções em
`ontology.classifications`:

```sql
INSERT INTO ontology.classifications (id, variable_id, code, label_pt, created_at)
SELECT gen_random_uuid(), v.id, 'opcao_a', 'Opção A', now()
FROM ontology.variables v WHERE v.name = 'nome_campo'
ON CONFLICT DO NOTHING;
```

### Passo 3 — Criar o Script

```sql
INSERT INTO gestao_clinica.scripts (id, name, name_display, description, event_type_id, version, is_active, created_at, updated_at)
VALUES (gen_random_uuid(), 'nome_guiao', 'Nome Display', 'Descrição', <event_type_id>, 1, true, now(), now())
ON CONFLICT (name) DO NOTHING;
```

### Passo 4 — Criar Sections

```sql
INSERT INTO gestao_clinica.script_sections (id, script_id, name, name_display, "order", created_at, updated_at)
VALUES (gen_random_uuid(), <script_id>, 'identificacao', 'Identificação', 1, now(), now())
ON CONFLICT DO NOTHING RETURNING id;
```

### Passo 5 — Criar Fields

```sql
INSERT INTO gestao_clinica.script_fields (id, section_id, variable_id, "order", is_required, created_at, updated_at)
VALUES (gen_random_uuid(), <section_id>, <variable_id>, 1, false, now(), now())
ON CONFLICT DO NOTHING;
```

## 5. Verificar a Estrutura

Usar a vista `gestao_clinica.v_script_structure` para validar:

```sql
SELECT s.name_display AS script, sec.name_display AS section,
       v.name_display AS campo, v.variable_type AS tipo, v.input_type AS input
FROM gestao_clinica.v_script_structure vss
JOIN gestao_clinica.scripts s ON s.id = vss.script_id
JOIN gestao_clinica.script_sections sec ON sec.id = vss.section_id
JOIN ontology.variables v ON v.id = vss.variable_id
WHERE s.name = 'nome_guiao'
ORDER BY sec."order", vss.field_order;
```

## 6. Sincronizar Schema Drizzle (TypeScript)

Depois de criar as tabelas via SQL direto no PostgreSQL, sincronizar o
`src/db/schema.ts` do Drizzle. Verificar os nomes reais das colunas na DB
antes de declarar no schema (o Drizzle não infere automaticamente).

```typescript
// Exemplo: tabelas de guião em gestao_clinica
export const scripts = gestaoClinicaSchema.table("scripts", {
  id: uuid("id").defaultRandom().primaryKey(),
  name: text("name").notNull().unique(),
  nameDisplay: text("name_display"),
  description: text("description"),
  eventTypeId: uuid("event_type_id").references(() => eventTypes.id),
  version: integer("version").default(1),
  isActive: boolean("is_active").default(true),
  createdAt: timestamp("created_at", { withTimezone: true }).defaultNow(),
  updatedAt: timestamp("updated_at", { withTimezone: true }).defaultNow(),
});

export const scriptSections = gestaoClinicaSchema.table("script_sections", {
  id: uuid("id").defaultRandom().primaryKey(),
  scriptId: uuid("script_id").references(() => scripts.id).notNull(),
  name: text("name").notNull(),
  nameDisplay: text("name_display"),
  sortOrder: integer("sort_order").default(0),
  createdAt: timestamp("created_at", { withTimezone: true }).defaultNow(),
  updatedAt: timestamp("updated_at", { withTimezone: true }).defaultNow(),
});

export const scriptFields = gestaoClinicaSchema.table("script_fields", {
  id: uuid("id").defaultRandom().primaryKey(),
  sectionId: uuid("section_id").references(() => scriptSections.id).notNull(),
  variableId: uuid("variable_id").references(() => variables.id),
  sortOrder: integer("sort_order").default(0),
  isRequired: boolean("is_required").default(false),
  createdAt: timestamp("created_at", { withTimezone: true }).defaultNow(),
  updatedAt: timestamp("updated_at", { withTimezone: true }).defaultNow(),
});
```

**Pitfall:** Nomes de colunas na DB usam snake_case; no Drizzle usamos camelCase
com o nome real da coluna como primeiro argumento (ex: `nameDisplay: text("name_display")`).

## 7. API Route para Buscar Guião

Criar uma API route Next.js que devolve a estrutura completa do guião (com
sections, fields, variables e classifications):

```typescript
// app/api/scripts/route.ts
import { NextRequest } from "next/server";
import { db } from "@/db";
import { scripts, scriptSections, scriptFields } from "@/db/schema";
import { variables, classifications } from "@/db/schema";
import { eq, and } from "drizzle-orm";

export async function GET(request: NextRequest) {
  const slug = request.nextUrl.searchParams.get("slug");
  if (!slug) return Response.json({ error: "Missing slug" }, { status: 400 });

  const script = await db.query.scripts.findFirst({
    where: eq(scripts.name, slug),
    with: {
      sections: {
        with: {
          fields: {
            with: {
              variable: {
                with: { classifications: true },
              },
            },
          },
        },
      },
    },
  });

  if (!script) return Response.json({ error: "Not found" }, { status: 404 });
  return Response.json({ script });
}
```

**Nota:** O Drizzle relational queries requerem que o schema declare as
relações via `relations()`. Se não estiverem definidas, fazer JOINs manuais
com `db.select().from(...).innerJoin(...).where(...)`.

## 8. Componente UI — Documento de Referência (NÃO Formulário)

Os guiões clínicos são **documentos técnicos de apoio às consultas**, destinados a
serem impressos e usados pelos colegas durante a consulta. NÃO são formulários
digitais de input.

### 8.1. Apresentação como Documento

Cada campo deve aparecer como um card de referência com:
- Nome da variável (título)
- Descrição do que avaliar
- Badge com o tipo de resposta esperada (Sim/Não, Numérico, Texto, Data, Seleção)
- Unidade (se aplicável)
- Lista de opções possíveis (para campos de seleção)
- Intervalo permitido (min/max)
- Exemplo de registo (placeholder)
- Notas técnicas (help_text)

### 8.2. Estrutura do Componente

```tsx
// app/components/script-form.tsx (estrutura chave)
function ScriptForm({ script }: { script: ScriptWithSections }) {
  return (
    <div className="space-y-6">
      {script.sections.map((section) => (
        <details key={section.id} className="border rounded-lg" open>
          <summary className="p-4 font-medium cursor-pointer">
            {section.nameDisplay || section.name}
          </summary>
          <div className="p-4 grid grid-cols-1 md:grid-cols-2 gap-4">
            {section.fields.map((field) => (
              <FieldCard key={field.id} field={field} />
            ))}
          </div>
        </details>
      ))}
      <button onClick={() => window.print()}>Imprimir / PDF</button>
    </div>
  );
}

function FieldCard({ field }: { field: ScriptField }) {
  const v = field.variable;
  return (
    <div className="break-inside-avoid rounded-lg border p-4 shadow-sm">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h4 className="text-sm font-semibold">{v.nameDisplay}</h4>
          {v.description && <p className="mt-1 text-sm text-muted-foreground">{v.description}</p>}
        </div>
        <FieldTypeBadge type={v.variableType} inputType={v.inputType} />
      </div>
      {v.classifications.length > 0 && (
        <div className="mt-3">
          <p className="text-xs font-medium text-muted-foreground uppercase">Opções de registo</p>
          <div className="flex flex-wrap gap-1.5">
            {v.classifications.map((c) => (
              <span key={c.code} className="rounded border px-2 py-1 text-xs">{c.labelPt}</span>
            ))}
          </div>
        </div>
      )}
      {v.helpText && (
        <div className="mt-3 rounded-md bg-muted/50 px-3 py-2 text-xs">
          <span className="font-medium">Nota:</span> {v.helpText}
        </div>
      )}
    </div>
  );
}
```

### 8.3. CSS para Impressão

Adicionar `@media print` ao `globals.css`:

```css
@media print {
  @page { margin: 1.5cm; size: A4; }
  nav, aside, [role="navigation"] { display: none !important; }
  .break-inside-avoid { break-inside: avoid; }
}
```

**Padrões de UI usados:**
- Secções collapsíveis para navegação no ecrã; todas abertas no print
- Grid responsivo: 1 coluna em mobile, 2 em desktop/print
- Ícones Phosphor (`CaretDown`, `FileText`, `Printer`)
- Botão `window.print()` para PDF via browser
- Cards com `break-inside-avoid` para evitar quebras de página no meio de um campo
- `print:hidden` nos controlos interativos; `print:block` para forçar conteúdo visível

## 9. Página Dinâmica [slug]

Em vez de páginas estáticas por guião, usar uma rota dinâmica:

```tsx
// app/(protected)/scripts/[slug]/page.tsx
export default async function ScriptPage({ params }: { params: { slug: string } }) {
  const res = await fetch(`${process.env.NEXT_PUBLIC_APP_URL}/api/scripts?slug=${params.slug}`,
    { cache: "no-store" }
  );
  if (!res.ok) return notFound();
  const { script } = await res.json();
  return <ScriptForm script={script} />;
}
```

## 10. Extrair Subsecções do Guião para Agrupar Variables

Além das secções principais, os guiões clínicos têm subsecções lógicas
(ex: "Avaliação Cognitiva", "Avaliação Emocional/Psicológica",
"Avaliação Motora/Física", "Scores", etc.). Em vez de criar tabelas
`script_sections`, podemos adicionar um campo `subsection` diretamente em
`ontology.variables` e agrupar a UI por esse campo.

### 10.1. Adicionar Coluna `subsection`

```sql
ALTER TABLE ontology.variables ADD COLUMN IF NOT EXISTS subsection text;
```

Sincronizar no Drizzle schema:

```typescript
export const variables = ontSchema.table("variables", {
  // ... campos existentes ...
  subsection: text("subsection"),
});
```

### 10.2. Mapear Variables para Subsecções via Script

Ler o guião .docx (ver secção 2), identificar as subsecções, e fazer UPDATE
programático:

```python
import psycopg2

subsection_map = {
    "gcs": "Avaliação Cognitiva",
    "memoria_internamento": "Avaliação Cognitiva",
    "barulho": "Avaliação Emocional/Psicológica",
    "luz": "Avaliação Emocional/Psicológica",
    "avd_higiene": "Avaliação Motora/Física",
    "barthel": "Scores",
    # ... etc
}

conn = psycopg2.connect(host="localhost", port=5433,
                        database="gestao-clinica_db",
                        user="postgres", password="postgres")
cur = conn.cursor()
for name, sub in subsection_map.items():
    cur.execute("UPDATE ontology.variables SET subsection = %s WHERE name = %s;", (sub, name))
conn.commit()
```

### 10.3. Agrupar Variables na API

A API `/api/ontology/event-types` deve devolver `subsection` juntamente com
cada variable:

```typescript
.select({
  id: variables.id,
  name: variables.name,
  name_display: variables.nameDisplay,
  section: variables.section,
  subsection: variables.subsection,  // <- incluir
  is_required: eventTypeVariables.isRequired,
  display_order: eventTypeVariables.displayOrder,
})
```

### 10.4. UI Colapsável por Subsecção

No componente React, agrupar as variables por `subsection` (fallback para
`section`):

```typescript
function groupBySubsection(variables: Variable[]): Record<string, Variable[]> {
  const groups: Record<string, Variable[]> = {};
  for (const v of variables) {
    const key = v.subsection || v.section || "Outros";
    if (!groups[key]) groups[key] = [];
    groups[key].push(v);
  }
  return groups;
}
```

Renderizar cada grupo como um accordion colapsável com `<details>` ou com
estado React + botões `ChevronDown`/`ChevronRight`.

**Padrão visual usado:**
- Cada subsecção é um card com header clicável
- Header mostra o nome da subsecção + contagem de variables
- Ao expandir, mostra uma tabela com as variables (nome, obrigatória, ordem)
- Ícone de lixo para desassociar a variable do evento

## 11. Query para UI / PDF (dados do doente)

Para renderizar o guião preenchido na UI ou gerar PDF:

```sql
-- Estrutura do guião com valores do doente num evento concreto
SELECT
  sec."order" AS section_order,
  sec.name_display AS section,
  v.name_display AS campo,
  v.input_type,
  pev.value AS resposta
FROM gestao_clinica.scripts s
JOIN gestao_clinica.script_sections sec ON sec.script_id = s.id
JOIN gestao_clinica.script_fields f ON f.section_id = sec.id
JOIN ontology.variables v ON v.id = f.variable_id
LEFT JOIN ontology.patient_event_values pev ON pev.variable_id = v.id
  AND pev.patient_event_id = '<event_id>'
WHERE s.name = 'nome_guiao'
ORDER BY sec."order", f."order";
```

## 10.5. Junction Table `event_type_variables`

Para ligar tipos de evento (`event_types`) às variáveis (`variables`) sem
hardcoding, usar uma tabela de junção:

```sql
CREATE TABLE ontology.event_type_variables (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  event_type_id uuid NOT NULL REFERENCES ontology.event_types(id) ON DELETE CASCADE,
  variable_id uuid NOT NULL REFERENCES ontology.variables(id) ON DELETE CASCADE,
  is_required boolean DEFAULT false,
  display_order integer DEFAULT 0,
  created_at timestamp DEFAULT now(),
  UNIQUE (event_type_id, variable_id)
);
```

Sincronizar no Drizzle schema:

```typescript
export const eventTypeVariables = ontSchema.table("event_type_variables", {
  id: uuid("id").defaultRandom().primaryKey(),
  eventTypeId: uuid("event_type_id").notNull().references(() => eventTypes.id, { onDelete: "cascade" }),
  variableId: uuid("variable_id").notNull().references(() => variables.id, { onDelete: "cascade" }),
  isRequired: boolean("is_required").default(false).notNull(),
  displayOrder: integer("display_order").default(0).notNull(),
  createdAt: timestamp("created_at").defaultNow().notNull(),
});
```

**Padrão de preenchimento automático:** mapear o campo `section` de cada
variable para os event types correspondentes:

```python
section_to_events = {
    "Demográficos": ["internamento"],
    "Internamento": ["internamento"],
    "Avaliação UCI": ["avaliacao_uci"],
    "Consulta": ["consulta_1", "consulta_2"],
}
```

Inserir via script Python/psycopg2 com `ON CONFLICT DO NOTHING`.

## 10.6. Mostrar Tipo e Valores na UI

Em vez de colunas "Obrigatória" e "Ordem", a tabela de variables pode mostrar:
- **Tipo** — badge com `variable_type` (traduzido: Texto, Número, Sim/Não, etc.)
- **Valores** — chips com os códigos das `classifications` associadas

### Batch fetch de Classifications

Em vez de N pedidos, fazer um único pedido batch com todos os IDs visíveis:

```typescript
// No componente React, após carregar event types
const allVarIds = eventTypes.flatMap(et => et.variables.map(v => v.id));
fetch(`/api/ontology/classifications?variables=${[...new Set(allVarIds)].join(",")}`)
```

A API `/api/ontology/classifications` deve aceitar o query param `variables`
(com IDs separados por vírgula) e devolver um mapa `variable_id → classifications[]`.

### Renderização

```tsx
function formatType(type: string): string {
  const map: Record<string, string> = {
    string: "Texto", number: "Número", boolean: "Sim/Não",
    date: "Data", enum: "Enumeração", score: "Score",
  };
  return map[type] || type;
}

// Na tabela
<td>
  <span className="text-xs px-1.5 py-0.5 rounded bg-primary/10 text-primary font-medium">
    {formatType(v.variable_type)}
  </span>
</td>
<td>
  {classifications[v.id]?.map(c => (
    <span key={c.id} className="text-xs px-1.5 py-0.5 rounded bg-muted" title={c.label_pt}>
      {c.code}
    </span>
  ))}
</td>
```

## 12. Pitfalls Summary

1. **DB name:** `gestao-clinica_db`, não `mnemosyne`.
2. **Schema access:** `gestao_clinica` precisa de grants para o app user.
3. **PostgREST:** O schema `gestao_clinica` não é exposto no PostgREST por
default (só `ontology` o é); verificar `db-schema` no config do PostgREST se
for necessário API access.
4. **DOCX parsing:** `python-docx` pode não estar instalado; usar fallback com
`zipfile` + `xml.etree`.
5. **psql quoting:** Ao passar SQL via `bash -c`, cuidado com aspas simples e
backslashes. Usar ficheiro `.sql` e `psql -f` quando possível.
6. **Variable naming:** `name` em `ontology.variables` é UNIQUE; verificar
variáveis existentes antes de criar novas para evitar duplicados com nomes
ligeiramente diferentes.
7. **Drizzle sync:** DDL direto na DB não atualiza o schema TypeScript. Sempre
que criar/alterar tabelas, sincronizar `src/db/schema.ts` manualmente.
8. **Drizzle column names:** A coluna na DB é snake_case; no schema Drizzle
usar `camelCase: sqlType("snake_case")`.
9. **Dynamic routes vs estático:** Preferir `[slug]/page.tsx` a criar uma página
nova por guião. Isto evita rebuilds quando se adicionam guiões na DB.
10. **API route:** Quando usar Drizzle relational queries, certificar que as
relações estão declaradas via `relations()`. Senão, fallback para joins
manuais.
11. **`drizzle-kit push` sem TTY:** `drizzle-kit push` falha em ambientes
non-interativos (CI, pipes) quando aparecem prompts (ex: "truncar tabela?").
Workaround: para ALTERs simples, usar `psql` diretamente com
`ALTER TABLE ... ADD COLUMN IF NOT EXISTS`.
12. **Phosphor vs Lucide icons:** `@phosphor-icons/react` não tem `AlertCircle`
(existe em lucide-react mas não em phosphor). Usar `Warning` ou `WarningCircle`.
