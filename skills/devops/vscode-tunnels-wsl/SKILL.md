---
name: vscode-tunnels-wsl
description: Set up VS Code Remote Tunnels for accessing WSL instances remotely, including troubleshooting stuck logins.
---

# Setting up VS Code Remote Tunnels for WSL

This skill outlines the reliable method for setting up VS Code Tunnels to access a remote WSL instance (e.g., a secondary machine like 'Apollo') from a primary machine, avoiding common pitfalls with integrated terminals.

## Trigger
Use this when you need to configure remote access to a WSL instance via VS Code without dealing with SSH keys, port forwarding, or firewall rules.

## Steps

**On the Target Machine (the WSL instance to be accessed):**

1. **Open a Standalone Terminal:** Open the WSL terminal directly from Windows (e.g., Windows Terminal, Ubuntu app). 
   *⚠️ CRITICAL: Do NOT run these commands inside the VS Code integrated terminal, as the authentication prompts may hang or be suppressed.*
2. **Clear Existing State:** Remove any phantom or stuck configurations:
   ```bash
   code tunnel unregister
   ```
3. **Download and Extract the Linux CLI (CRITICAL FOR WSL):** Do NOT use the built-in `code` command in WSL, as it will try to tunnel to the Windows host instead of the Linux environment. Download the standalone Linux CLI:
   ```bash
   curl -sL "https://vscode.download.prss.microsoft.com/dbazure/download/stable/560a9dba96f961efea7b1612916f89e5d5d4d679/vscode_cli_alpine_x64_cli.tar.gz" -o vscode_cli.tar.gz && tar -xzf vscode_cli.tar.gz
   ```
4. **Initiate the Tunnel using the extracted binary:**
   ```bash
   ./code tunnel
   ```
5. **Authenticate:** The terminal will output a device login URL (e.g., `https://github.com/login/device`) and an 8-character code. Open this link in any browser, enter the code, and authenticate via GitHub or Microsoft.
6. **Name the Machine:** When prompted in the terminal, provide a memorable name for the machine (e.g., `apollo`).
7. **Install as a Service (Optional but Recommended):** To ensure the tunnel survives terminal closures and machine reboots, stop the current process (Ctrl+C) and run:
   ```bash
   ./code tunnel service install
   ```

**On the Host Machine (where you are working):**

1. Open VS Code.
2. Navigate to the **Remote Explorer** extension.
3. In the dropdown at the top, select **Tunnels** (not WSL or SSH).
4. The newly named machine will appear in the list. Click the connect icon to access its WSL environment.

## Pitfalls & Troubleshooting
- **No authentication prompt appears:** You are likely running `code tunnel` inside an existing VS Code integrated terminal. Close it and use a standalone Windows/WSL terminal.
- **"Already registered" errors:** Run `code tunnel unregister` to clear the old state before attempting to create a new tunnel.
- **\"tar: This does not look like a tar archive\" or \"Not Found\" or \"gzip: stdin\":** The official Microsoft download links (`https://code.visualstudio.com/sha/download?build=stable&os=cli-linux-x64`) often redirect or fail with `curl`. Always use the direct Azure blob URL provided in step 3.
- **`code-server` not found:** Scripts like `https://aka.ms/install-vscode-server/setup.sh` install different components that require different CLI commands (`code-server tunnel` instead of `./code tunnel`). Stick to extracting the tar.gz manually as shown in step 3 to ensure predictability.