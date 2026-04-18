---
name: varlock-bitwarden
description: How to use Varlock with Bitwarden Secrets Manager CLI (bws) to secure environment variables and prevent AI agents from leaking API keys.
version: 1.1.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [security, env, secrets, varlock, bitwarden, bws, credentials]
---

# Varlock + Bitwarden Secrets Manager CLI (bws) Workflow

This skill documents how to secure a project's `.env` file using Varlock combined with the Bitwarden Secrets Manager CLI (`bws`). This ensures that AI agents (like Hermes) do not have access to plaintext API keys on disk, while still knowing the schema of required variables, and allows fully automated secret injection without manual vault unlocking.

## Why `bws` over `bw`?
While the standard Bitwarden CLI (`bw`) requires manual login (`bw login`) and vault unlocking (`bw unlock`) to get a session key, the **Bitwarden Secrets Manager CLI (`bws`)** is designed for machine-to-machine authentication. It uses a long-lived `BWS_ACCESS_TOKEN`, making it ideal for automated wrapper scripts and AI agents, as it doesn't require human intervention at runtime to unlock the vault.

## 1. Prerequisites

1. **Varlock**: Installed via `npm install -g varlock` or downloaded from `https://varlock.dev/install.sh`
2. **Bitwarden Secrets Manager CLI (`bws`)**: Installed via the official releases (do not confuse with `bw`). 
   - Installation on Linux usually involves downloading the zip from the Bitwarden SDK releases or via a package manager if available.

Ensure both `varlock` and `bws` are in your `PATH`.

## 2. Authentication (BWS_ACCESS_TOKEN)

Instead of a master password and session key, `bws` uses an access token generated from the Bitwarden Secrets Manager web vault.

The human user must set this token in their root environment or pass it to the agent:
```bash
export BWS_ACCESS_TOKEN="<your_machine_account_token>"
```

## 3. Setting up Varlock Schema

Initialize Varlock in your project directory (e.g., `~/.hermes/`):

```bash
cd ~/.hermes
varlock init
```

This creates an `.env.schema` file. Edit this file to mark which variables are sensitive.

**Example `.env.schema`:**
```env
# @sensitive @required
OPENAI_API_KEY=

# @type=number @default=180
TERMINAL_TIMEOUT=
```

## 4. Integrating `bws` with the Environment

Create a wrapper script (e.g., `start_hermes.sh`) that loads the variables securely from the Secrets Manager:

```bash
#!/bin/bash

# Ensure the access token is set
if [ -z "$BWS_ACCESS_TOKEN" ]; then
    echo "Error: BWS_ACCESS_TOKEN is not set. Please export it first."
    exit 1
fi

# Fetch secrets and export them directly to the environment
# You need the specific Secret ID from the BWS vault
export OPENAI_API_KEY=$(bws secret get "00000000-0000-0000-0000-000000000000" | jq -r .value)
export ANTHROPIC_API_KEY=$(bws secret get "11111111-1111-1111-1111-111111111111" | jq -r .value)

# Load Varlock to validate the environment against the schema
# This ensures all required vars are present and types are correct
eval $(varlock load --export)

# Start the application
hermes
```

## 5. Security Rules for AI Agents

1. **Never commit the BWS_ACCESS_TOKEN.** It should be injected by the host or human user.
2. **NEVER log or print the output of `bws secret get`.** If you must verify a key exists, check its length or hash, not the value.
3. If an `.env` file contains plaintext secrets, advise the user to move them to Bitwarden Secrets Manager and delete the plaintext values.
4. Ensure `.env` (even if empty of secrets), `auth.json`, and `.env.schema` are evaluated for Git inclusion. Usually, `.env.schema` goes into Git, but `.env` does not.