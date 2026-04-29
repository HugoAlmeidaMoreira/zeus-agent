Environment: WSL (Windows Subsystem for Linux). Windows host filesystem mounted under /mnt/c/. Convert Windows paths to /mnt/c/ equivalents. When running K8s/GitOps tasks inside WSL, the 'wsl' CLI is absent — just use 'git push' directly despite AGENTS.md rules.
§
Agent Topology: 'diana', 'mnemosyne', 'athena'. opencode-go needs OPENCODE_GO_API_KEY. GitOps: ~/git/theseus-kubernetes holds all K8s manifests. App repos (e.g. vectorized-gestao-clinica) are decoupled: no local manifests, no local ADRs (use Cortex DB via PostgREST), no legacy skeleton code.
§
Preferred DB interaction split: narrow cortex/memory workflows (ADRs, journals, skills) use PostgREST at 100.127.157.80 (mnemosyne/cortex DB). Application-database reasoning (clinical schema, variables, patients, events) requires raw `psql` via `kubectl port-forward -n infrastructure svc/postgres 5433:5432` because PostgREST does NOT expose clinical tables. Doppler project for the app is `vectorized-gestao-clinica` (config `prd`), NOT `theseus`. Use temp SQL files with psql `-f` to avoid bash escaping hell.
§
Clinical scripts (guiões) are reference documents for printing during consultations, not digital forms. Present as document cards with print-friendly CSS, not interactive inputs.
§
Hermes officially uses 'hermes@hugomoreira.eu' for external communications. To send emails, ALWAYS use the custom wrapper script `~/.hermes/scripts/send_email.sh <to> <subject> <body_file>`. This script automatically handles MML multipart/alternative formatting and injects the official HTML signature. Do not use raw `himalaya template send` for outbound emails as it ignores the `signature-cmd` in non-interactive piped mode.
§
No ambiente WSL, o Doppler está configurado de forma global para usar 'talos-cluster/prd'. Para outros projetos (vectorized-gestao-clinica, planapp/apollo), os agentes usam 'doppler setup --project <name> --config <env>'.
§
Cluster Theseus has no cert-manager. TLS pattern: Cloudflare Flexible terminates TLS at edge, cluster serves HTTP only. All ingresses must have ssl-redirect: false. Never add TLS blocks or cert-manager annotations.
§
Our vllm is hosted on a ASUS Ascent GX10 with CPU ARM v9.2-A CPU (GB10), NVIDIA Blackwell GPU (GB10, integrated) and 128 GB LPDDR5x Coherent Unified System Memory