Environment: Running inside WSL (Windows Subsystem for Linux). Windows host filesystem is mounted under /mnt/c/ (C: drive). Windows user files are at /mnt/c/Users/<username>/. Convert Windows paths to /mnt/c/ equivalents.
§
The GitOps repository for the Theseus Kubernetes cluster (the 'boat') is located at /home/hugo/git/theseus-kubernetes.
§
Agent Memory Architecture ('Database Cortex'): 1) Domain-specific agents (Theseus for K8s, Apollo for work) filter noise, sending only high-level insights to the main Event Ledger. 2) Night Cycle: A 'Dreaming Agent' validates timeline events, updates Short-Term Memory, and generates randomized 'stories' (dreams/nightmares) to connect concepts. 3) GitOps Memory: Long-term context (Skills, Soul, Office metadata) is maintained by agents via Git commits and synced across the pantheon via GitHub Actions. 4) Dynamic Ontology: ~/office is a living knowledge graph where .md YAML frontmatter is autonomously updated by memory agents.
§
Novas tarefas e requisitos detalhados (como os derivados de ADRs) devem ser guardados na subpasta `~/office/backlog/requisites/` e não na raiz do backlog.
§
O Hugo tem o cliente de email Himalaya configurado com o seu Gmail (hugoalmeidamoreira@gmail.com) e com o email dos agentes (hermes@hugomoreira.eu) usando as credenciais IMAP e SMTP via WSL. A gestão de emails via terminal funciona bidirecionalmente.
§
Hermes officially uses 'hermes@hugomoreira.eu' for external communications. To send emails, ALWAYS use the custom wrapper script `~/.hermes/scripts/send_email.sh <to> <subject> <body_file>`. This script automatically handles MML multipart/alternative formatting and injects the official HTML signature. Do not use raw `himalaya template send` for outbound emails as it ignores the `signature-cmd` in non-interactive piped mode.
§
The 'workbench' directory (e.g., in ~/office-personal/workbench/) is a low-structure space used for early-stage development of projects or ideas, before requirements and the final solution are clear.