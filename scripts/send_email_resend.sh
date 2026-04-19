#!/bin/bash
TO=$1
SUBJECT=$2
BODY_FILE=$3

# Extract the plain text body
PLAIN_BODY=$(cat "$BODY_FILE")

# Convert newlines to <br> for HTML version
HTML_BODY=$(cat "$BODY_FILE" | sed -z 's/\n/<br>\n/g')

# Escape quotes and backslashes for JSON payload
PLAIN_BODY_ESCAPED=$(jq -Rs . <<< "$PLAIN_BODY" | sed 's/^"\(.*\)"$/\1/')

# Build the complete HTML email including the signature
FULL_HTML=$(cat << HTML_EOF
<html><body>
<div style="font-family: sans-serif; font-size: 14px; color: #333;">
$HTML_BODY
<br><br>
<div style="margin-top: 15px;">
  <div style="font-weight: bold; color: #0056b3; font-size: 14px;">Hermes</div>
  <div style="color: #666; font-size: 12px; margin-bottom: 5px;">Agente Autónomo & Gestor de Contactos de Hugo Moreira</div>
  <div style="border-top: 3px solid #ccc; width: 350px;"></div>
</div>
</div>
</body></html>
HTML_EOF
)

# Escape the HTML for JSON payload
FULL_HTML_ESCAPED=$(jq -Rs . <<< "$FULL_HTML" | sed 's/^"\(.*\)"$/\1/')

# Fetch the Resend API key dynamically from Doppler
RESEND_API_KEY=$(doppler secrets get RESEND_API_KEY --plain)

# Execute the curl request to Resend API
curl -s -X POST https://api.resend.com/emails \
  -H "Authorization: Bearer $RESEND_API_KEY" \
  -H "Content-Type: application/json" \
  -d "{
    \"from\": \"Hermes Agent <hermes@hugomoreira.eu>\",
    \"to\": [\"$TO\"],
    \"subject\": \"$SUBJECT\",
    \"text\": \"$PLAIN_BODY_ESCAPED\",
    \"html\": \"$FULL_HTML_ESCAPED\"
  }"
