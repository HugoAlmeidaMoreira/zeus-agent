Environment: Running inside WSL (Windows Subsystem for Linux). Windows host filesystem is mounted under /mnt/c/ (C: drive). Windows user files are at /mnt/c/Users/<username>/. Convert Windows paths to /mnt/c/ equivalents.
§
The GitOps repository for the Theseus Kubernetes cluster (the 'boat') is located at /home/hugo/git/theseus-kubernetes.
§
Agent Memory Architecture ('Database Cortex'): Memory consolidation is continuous (only dreaming/stories are nocturnal). Raw session data, failed commands, and trajectories in ~/.hermes/state.db are FUNDAMENTAL for learning/RL, not just noise. They are synced to PostgreSQL via ~/.hermes/scripts/postgres-sync/sync_state_to_pg.py (requires POSTGRES_URL). GitOps memory (Skills, Soul, ~/office) stores the distilled, structured knowledge.
§
Novas tarefas e requisitos detalhados (como os derivados de ADRs) devem ser guardados na subpasta `~/office/backlog/requisites/` e não na raiz do backlog.
§
O Hugo tem o cliente de email Himalaya configurado com o seu Gmail (hugoalmeidamoreira@gmail.com) e com o email dos agentes (hermes@hugomoreira.eu) usando as credenciais IMAP e SMTP via WSL. A gestão de emails via terminal funciona bidirecionalmente.
§
Hermes officially uses 'hermes@hugomoreira.eu' for external communications. To send emails, ALWAYS use the custom wrapper script `~/.hermes/scripts/send_email.sh <to> <subject> <body_file>`. This script automatically handles MML multipart/alternative formatting and injects the official HTML signature. Do not use raw `himalaya template send` for outbound emails as it ignores the `signature-cmd` in non-interactive piped mode.
§
The 'workbench' directory (e.g., in ~/office-personal/workbench/) is a low-structure space used for early-stage development of projects or ideas, before requirements and the final solution are clear.
§
No ambiente WSL, o Doppler está configurado de forma global no scope do utilizador (/home/hugo) para usar por defeito o projeto 'talos-cluster' e a config 'prd'. Os agentes devem assumir este contexto e usar diretamente 'doppler run' ou 'doppler secrets get <CHAVE>' sem especificar flags de projeto ou iterar sobre outros projetos.