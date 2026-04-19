#!/usr/bin/env python3
import subprocess
import json
import psycopg2
import sys
import os

# Placeholder for the actual DB connection - we'll refine this based on the Mothership DB config
DB_HOST = "postgres.infrastructure.svc.cluster.local"
DB_PORT = 5432
DB_USER = "postgres"
DB_NAME = "mothership"

def get_unread_emails():
    try:
        result = subprocess.run(
            ["himalaya", "--account", "hermes", "envelope", "list", "--output", "json"],
            capture_output=True, text=True, check=True
        )
        
        # Parse output - sometimes himalaya mixes log warnings with JSON
        lines = result.stdout.strip().split('\n')
        json_str = next(line for line in lines if line.startswith('['))
        envelopes = json.loads(json_str)
        
        # Filter unseen (no 'Seen' flag)
        unseen = [e for e in envelopes if 'Seen' not in e.get('flags', [])]
        return unseen
    except Exception as e:
        print(f"Error fetching emails: {e}")
        return []

def main():
    unseen = get_unread_emails()
    if not unseen:
        print("No new emails.")
        return

    print(f"Found {len(unseen)} new emails.")
    for email in unseen:
        print(f"- From: {email['from']['name']} <{email['from']['addr']}> | Subject: {email['subject']}")
        
        # TODO: Read full message body
        # TODO: Insert into Mothership DB as a new Event/Task

if __name__ == "__main__":
    main()
