---
name: cortex-postgrest-api
description: Architectural standard for Agent interaction with the Database Cortex via PostgREST
category: agents
---
# Database Cortex via PostgREST

The Database Cortex (`mnemosyne` PostgreSQL DB) is exposed to agents via a stateless PostgREST API running in the Theseus Kubernetes cluster. Agents use standard HTTP (`curl`) to interact with shared memory, ontologies, and cross-agent communications, avoiding heavy MCP servers or local Python DB scripts.

## Key Endpoints & Routing

PostgREST is accessible via two methods:

### Internal (from within the cluster — preferred)
- **URL:** `http://postgrest.infrastructure.svc.cluster.local`
- Use this when running queries from inside agent pods or any cluster-internal context
- Schemas exposed: `public`, `communications`, `ontology`, `contacts-and-relations`, `events`, `agent-zeus`, `agent-apollo`

### Tailscale (from external — legacy)
- **URL:** `http://infrastructure-postgrest-tailscale.tail5ce214.ts.net` (or IP `100.127.157.80`)
- Use this for external access (local terminal, non-cluster contexts)

When making requests, you MUST specify the target schema using the `Accept-Profile` (for GET) or `Content-Profile` (for POST/PATCH) headers.

### Reading Data (GET)
```bash
# Read a skill from the ontology
curl -s -H "Accept-Profile: ontology" "http://100.127.157.80/skills?name=eq.adr_template" | jq .

# Search for an ADR mentioning 'tailscale' in the tags array
curl -s -H "Accept-Profile: ontology" "http://100.127.157.80/adrs?tags=cs.{tailscale}" | jq .

# Check unread messages for a specific agent
curl -s -H "Accept-Profile: communications" "http://100.127.157.80/messages?receiver=eq.apollo&status=eq.unread" | jq .
```

### Writing Data (POST)
```bash
# Send an async message to another agent
curl -X POST -H "Content-Profile: communications" -H "Content-Type: application/json" \
  -d '{"sender":"zeus", "receiver":"apollo", "content":"Read ADR-080"}' \
  "http://100.127.157.80/messages"
```

## Application Databases vs. Cortex Database (IMPORTANT)

The PostgREST API is **strictly** for the global agent brain (`mnemosyne`). It does **not** expose application-specific databases (tenant DBs like `gestao-clinica_db`).

If a task requires querying or modifying **application data** (like a project's specific ontology, users, or business logic):
1. **DO NOT** use PostgREST.
2. Read the `DATABASE_URL` from the project's local `.env` or `.env.local`.
3. Use the raw `psql` CLI to connect directly to the Tailscale Postgres endpoint.

**Example (Querying an App DB):**
```bash
# Extract password via Doppler, then connect via psql using the host from the .env file
PGPASSWORD=$(doppler secrets get DB_PASSWORD --plain --project <project> --config <config>) psql -h infrastructure-postgres-tailscale.tail5ce214.ts.net -U <user> -d <db> -c "\dt"
```

**Schema Inspection Cheat Sheet**
Use these `psql` meta-commands when exploring an unfamiliar application database:
```bash
# List all schemas
PGPASSWORD=... psql -h <host> -U <user> -d <db> -c "\dn"

# List tables inside a specific schema
-c "\dt ontology.*"

# Describe columns, types, constraints and FKs of a table
-c "\d ontology.variables"

# Run a quick exploratory query
-c "SELECT * FROM ontology.event_types ORDER BY \"order\" LIMIT 10;"
```

## OpenBao Secret Injection & DB Connectivity (Troubleshooting)

If the PostgREST pod fails to connect to the database (e.g., `Name does not resolve`), ensure `PGRST_DB_URI` points to the **internal Kubernetes DNS** (e.g., `postgres.infrastructure.svc.cluster.local:5432`), NOT the Tailscale IP, to prevent resolution issues within the pod.

To update the URL in OpenBao dynamically without installing the CLI locally:
```bash
export BAO_TOKEN=$(doppler secrets get OPENBAO_ROOT_TOKEN --plain)

# Patch the secret directly inside the pod
kubectl exec -n infrastructure openbao-0 -- env BAO_ADDR=http://127.0.0.1:8200 BAO_TOKEN=$BAO_TOKEN bao kv patch secret/infrastructure/postgres url="postgres://postgres:<PASS>@postgres.infrastructure.svc.cluster.local:5432/mnemosyne"

# Force ExternalSecrets to sync immediately
kubectl annotate externalsecret -n infrastructure postgres-credentials force-sync=$(date +%s) --overwrite
```

## Schema Reloading and Permissions

When creating new tables via `psql` executed directly in the pod (e.g., `kubectl exec -n infrastructure postgres-0 -- psql -U postgres -d mnemosyne`), you must:
1. Grant permissions to the specific roles mapped to JWT claims, e.g., `mothership`, `theseus_user`, `blacksmith`. Wait, if those roles exist. PostgREST does not run as `web_anon` or `pgrst_role` in this cluster; check existing roles with `\du`.\n2. If exposing a **new schema**, you must patch the PostgREST deployment in Kubernetes to update the `PGRST_DB_SCHEMA` environment variable:\n```bash\nkubectl patch deployment postgrest -n infrastructure -p '{\"spec\":{\"template\":{\"spec\":{\"containers\":[{\"name\":\"postgrest\",\"env\":[{\"name\":\"PGRST_DB_SCHEMA\",\"value\":\"public,communications,ontology,contacts-and-relations,events\"}]}]}}}}'\n```\n3. Reload the schema for PostgREST:
```bash
kubectl exec -n infrastructure postgres-0 -- psql -U postgres -d mnemosyne -c "NOTIFY pgrst, 'reload schema';"
```

## Core Ontology Tables

Do not parse local markdown files for these documents anymore. Always query the Cortex API.
- `ontology.skills`: `name`, `description`, `content`
- `ontology.adrs`: `id`, `title`, `repository`, `tags`, `content`
- `ontology.journals`: `agent_id`, `entry_date`, `anomalies_blockers`, `voice_future`, `content` (Interventions and Implementations)
- `ontology.audits`: `findings_critical`, `remediation`
- `ontology.forensics`: Incident root-cause reports (`root_cause`, `damage_assessment`, `agent_accountability`)
- `contacts-and-relations.agents`: Information and addresses of other agents (`agent`, `tailscale`, `email`, `telegram`, `description`)
- `contacts-and-relations.people`: People context (`name`, `contact`, `relationship`)

**HTTP API Accept-Profile Header Required**
When calling the Cortex API, you must always provide the target PostgreSQL schema in the Accept-Profile header. If omitted, PostgREST will default to `public` and return a PGRST205 error ("Could not find the table").

Example: `curl -H "Accept-Profile: ontology" http://100.127.157.80/skills`
Example: `curl -H "Accept-Profile: communications" http://100.127.157.80/messages`