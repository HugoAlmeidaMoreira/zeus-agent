#!/usr/bin/env python3
import sys
import json
import os
import psycopg2
import uuid
import subprocess

def get_pg_url():
    try:
        # Try to get it via Doppler directly
        result = subprocess.run(
            ['doppler', 'secrets', 'get', 'POSTGRES_ADMIN_URL_INTERNAL', '--plain'],
            capture_output=True, text=True, check=True
        )
        base_url = result.stdout.strip()
        if not base_url:
            raise ValueError("Empty output from doppler")
        # Ensure it points to mnemosyne DB
        if base_url.endswith('/'):
            return f"{base_url}mnemosyne"
        elif not base_url.endswith('mnemosyne'):
            return f"{base_url}/mnemosyne"
        return base_url
    except Exception as e:
        print(f"Error getting PG URL: {e}", file=sys.stderr)
        # Fallback to environment variable if set
        if 'POSTGRES_URL' in os.environ:
             url = os.environ['POSTGRES_URL']
             if 'mnemosyne' not in url:
                 print("Warning: POSTGRES_URL doesn't seem to point to mnemosyne database", file=sys.stderr)
             return url
        sys.exit(1)

def send_message(sender, receiver, payload):
    pg_url = get_pg_url()
    try:
        conn = psycopg2.connect(pg_url)
        with conn.cursor() as cur:
            # Create schema and table if they don't exist
            cur.execute('CREATE SCHEMA IF NOT EXISTS "contacts-and-relations";')
            cur.execute("""
                CREATE TABLE IF NOT EXISTS "contacts-and-relations".agent_inbox (
                    id UUID PRIMARY KEY,
                    sender VARCHAR(255) NOT NULL,
                    receiver VARCHAR(255) NOT NULL,
                    payload JSONB NOT NULL,
                    status VARCHAR(50) DEFAULT 'pending',
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
            """)
            
            # Insert the message
            message_id = str(uuid.uuid4())
            cur.execute("""
                INSERT INTO "contacts-and-relations".agent_inbox (id, sender, receiver, payload)
                VALUES (%s, %s, %s, %s)
                RETURNING id;
            """, (message_id, sender, receiver, json.dumps(payload)))
            
            inserted_id = cur.fetchone()[0]
            conn.commit()
            print(f"Success! Message sent with ID: {inserted_id}")
            
    except Exception as e:
        print(f"Database error: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        if 'conn' in locals() and conn:
            conn.close()

if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Usage: agent_inbox_send.py <sender_handle> <receiver_handle> '<json_payload>'", file=sys.stderr)
        print("Example: agent_inbox_send.py @apollo @zeus '{\"task\": \"review\", \"data\": \"...\"}'", file=sys.stderr)
        sys.exit(1)
        
    sender_handle = sys.argv[1]
    receiver_handle = sys.argv[2]
    
    try:
        payload_data = json.loads(sys.argv[3])
    except json.JSONDecodeError:
        print("Error: Payload must be valid JSON", file=sys.stderr)
        sys.exit(1)
        
    send_message(sender_handle, receiver_handle, payload_data)
