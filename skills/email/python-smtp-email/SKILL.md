---
name: python-smtp-email
description: Fallback method to send emails using Python smtplib when himalaya or send_email.sh fails with IMAP errors.
category: email
---

# Python SMTP Email Fallback

## Context
The default `~/.hermes/scripts/send_email.sh` wrapper and `himalaya` CLI can sometimes fail with IMAP sync issues (e.g., `cannot add IMAP message`, `stream error`, `unexpected tag in command completion result`) or template parsing panics.

## Trigger
Use this fallback immediately when `send_email.sh` or `himalaya message send` fail to send an email due to system/IMAP errors.

## Implementation
Use a direct Python script via the `terminal` tool to send the email using the built-in `smtplib`.

```python
import smtplib
from email.message import EmailMessage

msg = EmailMessage()
msg.set_content("""Olá,

Corpo do email aqui.

Um abraço,
Hermes""")
msg["Subject"] = "Assunto do Email"
msg["From"] = "hermes@hugomoreira.eu"
msg["To"] = "destinatario@exemplo.com"

# Connect to the SMTP server
s = smtplib.SMTP("webdomain02.dnscpanel.com", 587)
s.starttls()

# Read password from the credentials file
password = open("/home/hugo/.hermes_email_pass").read().strip()
s.login("hermes@hugomoreira.eu", password)

s.send_message(msg)
s.quit()
```

## Pitfalls
- Ensure the password file `/home/hugo/.hermes_email_pass` exists and is read securely.
- Set the correct SMTP server and port (`webdomain02.dnscpanel.com` / `587`).
- The `smtplib` connection requires `starttls()` before `login()`.