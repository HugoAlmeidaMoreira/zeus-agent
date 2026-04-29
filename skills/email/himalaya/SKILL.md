---
name: himalaya
description: CLI to manage emails via IMAP/SMTP. Use himalaya to list, read, write, reply, forward, search, and organize emails from the terminal. Supports multiple accounts and message composition with MML (MIME Meta Language).
version: 1.0.0
author: community
license: MIT
metadata:
  hermes:
    tags: [Email, IMAP, SMTP, CLI, Communication]
    homepage: https://github.com/pimalaya/himalaya
prerequisites:
  commands: [himalaya]
---

# Himalaya Email CLI

Himalaya is a CLI email client that lets you manage emails from the terminal using IMAP, SMTP, Notmuch, or Sendmail backends.

**IMPORTANT CLI SYNTAX:** The `--account` flag MUST come *after* the subcommand (e.g., `himalaya envelope list --account hermes`, NOT `himalaya --account hermes envelope list`). Global flags placed before the subcommand will cause an `unexpected argument` error.

## References

- `references/configuration.md` (config file setup + IMAP/SMTP authentication)
- `references/message-composition.md` (MML syntax for composing emails)

## Prerequisites

1. Himalaya CLI installed (`himalaya --version` to verify)
2. A configuration file at `~/.config/himalaya/config.toml`
3. IMAP/SMTP credentials configured (password stored securely)

### Installation

```bash
# Pre-built binary (Linux/macOS — recommended)
curl -sSL https://raw.githubusercontent.com/pimalaya/himalaya/master/install.sh | PREFIX=~/.local sh

# macOS via Homebrew
brew install himalaya

# Or via cargo (any platform with Rust)
cargo install himalaya --locked
```

## Configuration Setup

Run the interactive wizard to set up an account:

```bash
himalaya account configure
```

Or create `~/.config/himalaya/config.toml` manually:

```toml
[accounts.personal]
email = "you@example.com"
display-name = "Your Name"
default = true

backend.type = "imap"
backend.host = "imap.example.com"
backend.port = 993
backend.encryption.type = "tls"
backend.login = "you@example.com"
backend.auth.type = "password"
backend.auth.cmd = "pass show email/imap"  # or use keyring

message.send.backend.type = "smtp"
message.send.backend.host = "smtp.example.com"
message.send.backend.port = 587
message.send.backend.encryption.type = "start-tls"
message.send.backend.login = "you@example.com"
message.send.backend.auth.type = "password"
message.send.backend.auth.cmd = "pass show email/smtp"
```

## Hermes Integration Notes

- **Reading, listing, searching, moving, deleting** all work directly through the terminal tool
- **Composing/replying/forwarding** — piped input (`cat << EOF | himalaya template send`) is recommended for reliability. Interactive `$EDITOR` mode works with `pty=true` + background + process tool, but requires knowing the editor and its commands
- Use `--output json` for structured output that's easier to parse programmatically
- The `himalaya account configure` wizard requires interactive input — use PTY mode: `terminal(command="himalaya account configure", pty=true)`

## Common Operations

### List Folders

```bash
himalaya folder list
```

### List Emails

List emails in INBOX (default):

```bash
himalaya envelope list --account hermes --output json
```

List emails in a specific folder:

```bash
himalaya envelope list --folder "Sent"
```

List with pagination:

```bash
himalaya envelope list --page 1 --page-size 20
```

### Search Emails

```bash
himalaya envelope list from john@example.com subject meeting
```

### Read an Email

Read email by ID (shows plain text):

```bash
himalaya message read 42 --account hermes
```

**Avoid Marking as Seen:** Use `--preview` when reading automated/sync scripts if you don't want to flag the message as read on the IMAP server.
```bash
himalaya message read 42 --account hermes --preview
```

**Remove Headers:** Use `--no-headers` to retrieve just the body content.
```bash
himalaya message read 42 --account hermes --no-headers
```

Add or remove flags (e.g., Mark as Seen):
```bash
himalaya flag add 42 Seen --account hermes
```

Export raw MIME:

```bash
himalaya message export 42 --full --account hermes
```

### Reply to an Email

To reply non-interactively from Hermes, read the original message, compose a reply, and pipe it:

```bash
# Get the reply template, edit it, and send
himalaya template reply 42 | sed 's/^$/\nYour reply text here\n/' | himalaya template send
```

Or build the reply manually:

```bash
cat << 'EOF' | himalaya template send
From: you@example.com
To: sender@example.com
Subject: Re: Original Subject
In-Reply-To: <original-message-id>

Your reply here.
EOF
```

Reply-all (interactive — needs $EDITOR, use template approach above instead):

```bash
himalaya message reply 42 --all
```

### Forward an Email

```bash
# Get forward template and pipe with modifications
himalaya template forward 42 | sed 's/^To:.*/To: newrecipient@example.com/' | himalaya template send
```

### Write a New Email

**Non-interactive (use this from Hermes)** — pipe the message via stdin:

```bash
cat << 'EOF' | himalaya template send
From: you@example.com
To: recipient@example.com
Subject: Test Message

Hello from Himalaya!

-- 
Hermes Agent
EOF
```

> **⚠️ Pitfalls for Non-interactive Sending:**
> - **Signatures:** Piping input bypasses the `signature-cmd` configured in `config.toml`. You MUST manually append the signature text to the bottom of your piped body (or use a wrapper script).
> - **False Failure (IMAP append):** When using `himalaya template send`, you may receive an error like `cannot add IMAP message ... stream error ... unexpected tag in command completion result`. This usually means the email **WAS successfully sent** via SMTP, but Himalaya failed to save a copy to the IMAP `Sent` folder. Do not assume the send failed; verify receipt before retrying.

**Save as Draft (Do not send)** — use `template save` and specify the drafts folder (e.g., `[Gmail]/Drafts` for Gmail). Note that the `--account` and `--folder` flags must come *after* `template save` and not before `template`:

```bash
# First, verify the drafts folder name: himalaya folder list --account personal
cat << 'EOF' | himalaya template save --account personal --folder "[Gmail]/Drafts"
To: recipient@example.com
Subject: Draft Subject

This is a draft message.
EOF
```

```bash
himalaya message write -H "To:recipient@example.com" -H "Subject:Test" "Message body here"
```

Note: `himalaya message write` without piped input opens `$EDITOR`. This works with `pty=true` + background mode, but piping is simpler and more reliable.

### Move/Copy Emails

Move to folder:

```bash
himalaya message move 42 "Archive"
```

Copy to folder:

```bash
himalaya message copy 42 "Important"
```

### Delete an Email

```bash
himalaya message delete 42
```

### Manage Flags

Add flag:

```bash
himalaya flag add 42 --flag seen
```

Remove flag:

```bash
himalaya flag remove 42 --flag seen
```

## Multiple Accounts

List accounts:

```bash
himalaya account list
```

Use a specific account:

```bash
himalaya folder list --account personal
himalaya template save --account personal --folder "Drafts"
```

Note: The `--account` flag must be placed *after* the specific subcommand (e.g. `himalaya folder list --account personal` or `himalaya template save --account personal --folder "Drafts"`), not immediately after `himalaya`. The CLI throws `unexpected argument '--account' found` if placed incorrectly.

## Attachments

Save attachments from a message:

```bash
himalaya attachment download 42
```

Save to specific directory:

```bash
himalaya attachment download 42 --dir ~/Downloads
```

## Output Formats

Most commands support `--output` for structured output:

```bash
himalaya envelope list --output json
himalaya envelope list --output plain
```

## Pitfalls & Troubleshooting

- **False Positive on Send (IMAP Append Error):** When using `himalaya template send` or `himalaya message send`, you may encounter this error:
  ```text
  Error: 
     0: cannot add IMAP message
     1: stream error
     2: unexpected tag in command completion result
  ```
  **Do not assume the email failed to send.** This error typically occurs *after* successful SMTP transmission, when Himalaya attempts to `APPEND` a copy of the message to the IMAP `Sent` folder. Verify the sent status by checking the recipient's inbox. If SMTP succeeds, the email was delivered despite this error.
- **TOML Table Ordering:** When editing `config.toml` manually, ensure plain key-value pairs (like `folder.sent = "INBOX.Sent"`) are defined *before* any nested tables (like `backend.type = "imap"` or `message.send.backend.type = "smtp"`). Placing plain keys after tables will cause TOML parsing errors.

## Debugging

Enable debug logging:

```bash
RUST_LOG=debug himalaya envelope list
```

Full trace with backtrace:

```bash
RUST_LOG=trace RUST_BACKTRACE=1 himalaya envelope list
```

## Troubleshooting

- **`cannot add IMAP message` (stream error / unexpected tag) during send:** This often happens on cPanel/custom host IMAP servers where the default folder names do not match. The server expects folders prefixed with `INBOX.` (e.g., `INBOX.Sent`). Fix this by explicitly defining folders in your `config.toml` account section:
  ```toml
  folder.sent = "INBOX.Sent"
  folder.drafts = "INBOX.Drafts"
  folder.trash = "INBOX.Trash"
  ```
- **Emails bounced by Gmail (550-5.7.26 Unauthenticated):** If `himalaya template send` succeeds but you receive an "Undelivered Mail Returned to Sender" in your INBOX stating Gmail blocked it, the sender domain is missing SPF or DKIM DNS records.

### Common Errors
- **`cannot add IMAP message / unexpected tag` on send**: This usually happens because Himalaya tries to save the sent message to a "Sent" folder that doesn't exist or is named differently on the server (very common on cPanel servers). Fix this by explicitly mapping the folders in `config.toml` under your account configuration:
  ```toml
  folder.sent = "INBOX.Sent"
  folder.drafts = "INBOX.Drafts"
  folder.trash = "INBOX.Trash"
  ```
- **`invalid value: map, expected map with a single key`**: TOML formatting error. This happens when mixing table declarations incorrectly (e.g. using `backend.encryption = "tls"` instead of `backend.encryption.type = "tls"`). Avoid using `sed` to edit `config.toml`; rewrite the file or block completely using `cat << EOF` to prevent breaking the strict TOML map validation.

## Tips

- Use `himalaya --help` or `himalaya <command> --help` for detailed usage.
- Message IDs are relative to the current folder; re-list after folder changes.
- For composing rich emails with attachments, use MML syntax (see `references/message-composition.md`).
- Store passwords securely using `pass`, system keyring, or a command that outputs the password.
