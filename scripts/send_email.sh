#!/bin/bash
TO=$1
SUBJECT=$2
BODY_FILE=$3

HTML_BODY=$(cat "$BODY_FILE" | sed -z 's/\n/<br>\n/g')

TEMPLATE=$(cat << INNER_EOF
From: Hermes Agent <hermes@hugomoreira.eu>
To: $TO
Subject: $SUBJECT

<#multipart type=alternative>
$(cat "$BODY_FILE")
<#part type=text/html>
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
<#/multipart>
INNER_EOF
)

echo "$TEMPLATE" | himalaya template send --account hermes
