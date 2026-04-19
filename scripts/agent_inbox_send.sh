#!/bin/bash
# A simple bash wrapper to send messages to the agent_inbox table using psql
# Usage: ./agent_inbox_send.sh <sender_handle> <receiver_handle> '<json_payload>'

if [ "$#" -ne 3 ]; then
    echo "Usage: $0 <sender_handle> <receiver_handle> '<json_payload>'"
    echo "Example: $0 @apollo @zeus '{\"task\": \"review\", \"data\": \"...\"}'"
    exit 1
fi

SENDER=$1
RECEIVER=$2
PAYLOAD=$3

# Simple JSON validation (ensure it parses with jq)
if ! echo "$PAYLOAD" | jq . > /dev/null 2>&1; then
    echo "Error: Payload must be valid JSON"
    exit 1
fi

PG_URL=$(doppler secrets get POSTGRES_ADMIN_URL_INTERNAL --plain)
if [[ "$PG_URL" != *"mnemosyne"* ]]; then
    # Append database name if missing
    if [[ "$PG_URL" == */ ]]; then
        PG_URL="${PG_URL}mnemosyne"
    else
        PG_URL="${PG_URL}/mnemosyne"
    fi
fi

# Create table if it doesn't exist (run once)
psql "$PG_URL" -c "
CREATE TABLE IF NOT EXISTS \"contacts-and-relations\".agent_inbox (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    sender VARCHAR(255) NOT NULL,
    receiver VARCHAR(255) NOT NULL,
    payload JSONB NOT NULL,
    status VARCHAR(50) DEFAULT 'pending',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);" > /dev/null 2>&1

# Insert the message
psql "$PG_URL" -c "
INSERT INTO \"contacts-and-relations\".agent_inbox (sender, receiver, payload)
VALUES ('$SENDER', '$RECEIVER', '$PAYLOAD'::jsonb)
RETURNING id;
"
