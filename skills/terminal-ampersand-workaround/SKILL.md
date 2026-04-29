---
name: terminal-ampersand-workaround
description: Workaround for terminal tool rejecting commands with ampersands (&) inside JSON payloads or heredocs.
trigger: terminal tool errors with "Foreground command uses '&' backgrounding"
category: software-development
---

# Terminal Ampersand (&) Bug Workaround

## Problem
The `terminal` tool has an aggressive heuristic that blocks foreground commands containing the `&` character, assuming you are trying to background a process (e.g., `command &`). It throws this error:
`Foreground command uses '&' backgrounding. Use terminal(background=true)...`

This heuristic is flawed and will trigger even if the `&` is completely safe and inside quotes, such as:
- Inside a JSON payload for a `curl` request (e.g., `"title": "R&D"` or `"Context & Problem Statement"`).
- Inside a URL query string (e.g., `?foo=bar&baz=qux`) if not carefully quoted, though sometimes even quoting fails.
- Inside a `cat << 'EOF'` heredoc block.

## Solution
Do **NOT** try to escape the `&` or use different quoting mechanisms in the terminal tool, as the regex will likely still catch it.

Instead, use the **`write_file`** tool to safely write the content to disk, and then reference the file in the terminal command.

### Example: Complex Curl POST (PostgREST or APIs)

**❌ Fails:**
```json
// terminal tool
{
  "command": "curl -X POST -d '{\"text\": \"Research & Development\"}' http://api/..."
}
```

**✅ Works:**
1. Call `write_file` to save the payload:
```json
// write_file tool
{
  "path": "/tmp/payload.json",
  "content": "{\"text\": \"Research & Development\"}"
}
```

2. Call `terminal` to send it:
```json
// terminal tool
{
  "command": "curl -s -X POST -H \"Content-Type: application/json\" -d @/tmp/payload.json http://api/..."
}
```

### Example: Writing a script or markdown file with `cat << EOF`

**❌ Fails:**
```json
// terminal tool
{
  "command": "cat << 'EOF' > file.md\n# Context & Problem\nEOF"
}
```

**✅ Works:**
Use the `write_file` tool directly to write `file.md`. Do not use `cat` in the terminal to write files.