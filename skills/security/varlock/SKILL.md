---
name: varlock
description: Use Varlock to create AI-safe .env schemas and prevent secret leakage
---

# Varlock: AI-Safe Environment Variables

Varlock (by dmno-dev) is a tool designed to create "Schemas for agents, Secrets for humans." 

**Crucial Distinction:** Varlock is NOT an encrypted vault (like SOPS, git-crypt, or HashiCorp Vault). Instead, it uses the `@env-spec` standard to generate `.env.schema` files that explicitly annotate which environment variables are sensitive. This tells AI agents and tools exactly what is safe to read/log and what must be redacted, preventing accidental leaks of API keys or passwords by LLMs.

## Trigger Conditions
- The user asks to secure `.env` files against AI leaks.
- The user mentions `varlock`.
- You need to review or generate an environment schema.

## Installation

```bash
# Install via cURL
curl -sSfL https://varlock.dev/install.sh | sh -s

# Add to PATH (e.g., in ~/.bashrc or ~/.zshrc)
export PATH="${XDG_CONFIG_HOME:-~/.config}/varlock/bin:$PATH"
```

## Usage

1. **Initialize in a project:**
   Navigate to the project directory containing a `.env` file and run:
   ```bash
   varlock init
   ```
   This will read the existing `.env` (without exposing the real values) and generate a `.env.schema` file.

2. **Schema Annotations (`@env-spec`):**
   Open the `.env.schema` and ensure correct annotations:
   - `@sensitive`: Use this for API keys, passwords, and tokens. (e.g., `# @sensitive`)
   - `@required`: Marks the variable as mandatory.
   - `@type`: Defines data type (e.g., `# @type=number`, `# @type=boolean`).
   - `@example`: Provides a safe dummy value (e.g., `# @example="sk-12345..."`).

3. **Validation:**
   ```bash
   varlock load
   ```
   This validates the current `.env` against the `.env.schema` and pretty-prints the variables safely.

## Best Practices for Hermes / AI Agents
- Always commit `.env.schema` to version control.
- **NEVER** commit `.env`.
- When an AI agent (like Hermes) encounters a `.env.schema`, it should respect the `@sensitive` tags and refuse to read or output the raw values of those keys from the actual `.env` file unless explicitly overridden by the user for a secure operation.
