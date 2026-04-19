#!/usr/bin/env python3
import sqlite3
import psycopg2
import psycopg2.extras
import os
import sys
import time

SQLITE_DB = os.path.expanduser("~/.hermes/state.db")
PG_URL = os.environ.get("POSTGRES_URL")

if not PG_URL:
    print("Error: POSTGRES_URL environment variable is required.", file=sys.stderr)
    sys.exit(1)

def get_pg_connection():
    return psycopg2.connect(PG_URL)

def init_pg_schema(pg_conn):
    with pg_conn.cursor() as cur:
        cur.execute('CREATE SCHEMA IF NOT EXISTS "agent-zeus";')
        cur.execute('SET search_path TO "agent-zeus";')
        cur.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                source TEXT NOT NULL,
                user_id TEXT,
                model TEXT,
                model_config JSONB,
                system_prompt TEXT,
                parent_session_id TEXT,
                started_at DOUBLE PRECISION NOT NULL,
                ended_at DOUBLE PRECISION,
                end_reason TEXT,
                message_count INTEGER DEFAULT 0,
                tool_call_count INTEGER DEFAULT 0,
                input_tokens INTEGER DEFAULT 0,
                output_tokens INTEGER DEFAULT 0,
                cache_read_tokens INTEGER DEFAULT 0,
                cache_write_tokens INTEGER DEFAULT 0,
                reasoning_tokens INTEGER DEFAULT 0,
                billing_provider TEXT,
                billing_base_url TEXT,
                billing_mode TEXT,
                estimated_cost_usd DOUBLE PRECISION,
                actual_cost_usd DOUBLE PRECISION,
                cost_status TEXT,
                cost_source TEXT,
                pricing_version TEXT,
                title TEXT
            );

            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT,
                tool_call_id TEXT,
                tool_calls JSONB,
                tool_name TEXT,
                timestamp DOUBLE PRECISION NOT NULL,
                token_count INTEGER,
                finish_reason TEXT,
                reasoning TEXT,
                reasoning_details JSONB,
                codex_reasoning_items JSONB
            );
            
            CREATE TABLE IF NOT EXISTS sync_state (
                key TEXT PRIMARY KEY,
                value TEXT
            );
        """)
    pg_conn.commit()

def get_last_sync_timestamp(pg_conn):
    with pg_conn.cursor() as cur:
        cur.execute("SELECT value FROM sync_state WHERE key = 'last_sync_time'")
        result = cur.fetchone()
        if result:
            return float(result[0])
        return 0.0

def update_last_sync_timestamp(pg_conn, timestamp):
    with pg_conn.cursor() as cur:
        cur.execute("""
            INSERT INTO sync_state (key, value)
            VALUES ('last_sync_time', %s)
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
        """, (str(timestamp),))
    pg_conn.commit()

def sync_data():
    print("Starting SQLite to PostgreSQL sync...")
    try:
        pg_conn = get_pg_connection()
    except Exception as e:
        print(f"Failed to connect to Postgres: {e}", file=sys.stderr)
        sys.exit(1)
        
    init_pg_schema(pg_conn)
    sqlite_conn = sqlite3.connect(SQLITE_DB)
    sqlite_conn.row_factory = sqlite3.Row
    
    last_sync = get_last_sync_timestamp(pg_conn)
    current_sync = time.time()
    
    print(f"Syncing sessions since {last_sync}...")
    sqlite_cur = sqlite_conn.cursor()
    sqlite_cur.execute("SELECT * FROM sessions WHERE started_at >= ?", (last_sync - 86400,))
    sessions = sqlite_cur.fetchall()
        
    if sessions:
        with pg_conn.cursor() as pg_cur:
            insert_query = """
                INSERT INTO sessions (
                    id, source, user_id, model, model_config, system_prompt,
                    parent_session_id, started_at, ended_at, end_reason,
                    message_count, tool_call_count, input_tokens, output_tokens,
                    cache_read_tokens, cache_write_tokens, reasoning_tokens,
                    billing_provider, billing_base_url, billing_mode,
                    estimated_cost_usd, actual_cost_usd, cost_status, cost_source,
                    pricing_version, title
                ) VALUES (
                    %(id)s, %(source)s, %(user_id)s, %(model)s, %(model_config)s, %(system_prompt)s,
                    %(parent_session_id)s, %(started_at)s, %(ended_at)s, %(end_reason)s,
                    %(message_count)s, %(tool_call_count)s, %(input_tokens)s, %(output_tokens)s,
                    %(cache_read_tokens)s, %(cache_write_tokens)s, %(reasoning_tokens)s,
                    %(billing_provider)s, %(billing_base_url)s, %(billing_mode)s,
                    %(estimated_cost_usd)s, %(actual_cost_usd)s, %(cost_status)s, %(cost_source)s,
                    %(pricing_version)s, %(title)s
                ) ON CONFLICT (id) DO UPDATE SET
                    ended_at = EXCLUDED.ended_at,
                    end_reason = EXCLUDED.end_reason,
                    message_count = EXCLUDED.message_count,
                    tool_call_count = EXCLUDED.tool_call_count,
                    input_tokens = EXCLUDED.input_tokens,
                    output_tokens = EXCLUDED.output_tokens,
                    cache_read_tokens = EXCLUDED.cache_read_tokens,
                    cache_write_tokens = EXCLUDED.cache_write_tokens,
                    reasoning_tokens = EXCLUDED.reasoning_tokens,
                    estimated_cost_usd = EXCLUDED.estimated_cost_usd,
                    actual_cost_usd = EXCLUDED.actual_cost_usd,
                    cost_status = EXCLUDED.cost_status,
                    title = EXCLUDED.title;
            """
            psycopg2.extras.execute_batch(pg_cur, insert_query, [dict(s) for s in sessions])
        pg_conn.commit()
        print(f"Synced {len(sessions)} sessions.")

    print("Syncing messages...")
    sqlite_cur.execute("SELECT * FROM messages WHERE timestamp >= ?", (last_sync,))
    messages = sqlite_cur.fetchall()
        
    if messages:
        with pg_conn.cursor() as pg_cur:
            insert_query = """
                INSERT INTO messages (
                    id, session_id, role, content, tool_call_id,
                    tool_calls, tool_name, timestamp, token_count,
                    finish_reason, reasoning, reasoning_details, codex_reasoning_items
                ) VALUES (
                    %(id)s, %(session_id)s, %(role)s, %(content)s, %(tool_call_id)s,
                    %(tool_calls)s, %(tool_name)s, %(timestamp)s, %(token_count)s,
                    %(finish_reason)s, %(reasoning)s, %(reasoning_details)s, %(codex_reasoning_items)s
                ) ON CONFLICT (id) DO NOTHING;
            """
            psycopg2.extras.execute_batch(pg_cur, insert_query, [dict(m) for m in messages])
        pg_conn.commit()
        print(f"Synced {len(messages)} messages.")
        
    update_last_sync_timestamp(pg_conn, current_sync)
    print("Sync complete.")
    
    sqlite_conn.close()
    pg_conn.close()

if __name__ == "__main__":
    sync_data()