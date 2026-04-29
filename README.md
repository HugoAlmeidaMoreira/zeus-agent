# Hermes Core Context Files

Este diretório `~/.hermes/` contém o estado global, memórias, e identidade do agente. Quando uma nova sessão do Hermes é iniciada, o *harness* lê e agrega estes ficheiros para construir o *system prompt* dinâmico que governa a operação do agente em todas as tarefas.

Editar estes ficheiros altera diretamente a identidade base do agente e o contexto duradouro com o qual ele inicia cada conversa.

## Ficheiros do System Prompt Global

* **`SOUL.md`**: A *Persona* e voz do agente. Edita este ficheiro para alterar o tom (formal vs. informal), idioma preferido, restrições verbais (palavras proibidas, nível de otimismo), e preferências essenciais de formatação (ex: "não mostrar código a não ser que eu peça", "usar sistema métrico").
* **`memories/MEMORY.md`**: O *Database Cortex* da arquitetura local. Contém as memórias operacionais (OS, caminhos WSL, atalhos de ferramentas, convenções do repositório global, anomalias do terminal). Usa a ferramenta `memory` para atualizar isto dinamicamente durante as sessões, reduzindo a necessidade de o utilizador repetir factos contextuais do ambiente de trabalho (como caminhos GitOps, PostgREST ou Tailscale).
* **`memories/USER.md`**: O perfil do utilizador. Detalhes duradouros sobre quem o utilizador é (nome, família, profissão, papéis, domínios web detidos, infraestrutura sob a sua gestão). Separa-se da `MEMORY.md` para manter a distinção entre "quem é o utilizador" e "como a máquina funciona".
* **`skills/` (Diretório)**: A memória procedural. Contém pastas com os ficheiros `SKILL.md` que codificam fluxos de trabalho específicos (como `graphify`, `create-adr`, etc.). O cabeçalho de cada *skill* é injetado no *prompt*, mas o conteúdo só é lido via chamada de ferramenta.

## Configuração Técnica

* **`config.yaml`**: Define as fundações de execução (modelos, provedores como OpenRouter, servidores MCP injetados, chaves e ferramentas base). Alterar isto afeta a orquestração do LLM antes mesmo de o *prompt* ser lido.