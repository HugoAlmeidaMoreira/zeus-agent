#!/bin/bash

DB_FILE="$HOME/.hermes/state.db"
SYNC_SCRIPT="$HOME/.hermes/scripts/postgres-sync/sync_state_to_pg.py"
LOG_FILE="$HOME/.hermes/scripts/postgres-sync/watchtower.log"
COOLDOWN=5 # Wait 5 seconds after a change before syncing, to batch rapid changes

echo "Starting Watchtower for $DB_FILE..." >> "$LOG_FILE"

while true; do
  # Wait for a modification event on the SQLite database
  inotifywait -e modify,close_write "$DB_FILE" > /dev/null 2>&1
  
  echo "$(date): Change detected. Waiting $COOLDOWN seconds before sync..." >> "$LOG_FILE"
  sleep "$COOLDOWN"
  
  # Export the POSTGRES_URL from Doppler and run the sync script
  echo "$(date): Running sync..." >> "$LOG_FILE"
  POSTGRES_URL="$(doppler secrets get POSTGRES_URL --plain)" "$SYNC_SCRIPT" >> "$LOG_FILE" 2>&1
  echo "$(date): Sync completed." >> "$LOG_FILE"
  
  # Prevent CPU spinning if inotifywait fails for some reason
  sleep 1
done
