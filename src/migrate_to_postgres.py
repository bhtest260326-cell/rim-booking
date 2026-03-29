#!/usr/bin/env python3
"""Migrate data from SQLite to PostgreSQL.

Usage:
    python migrate_to_postgres.py                      # full migration
    python migrate_to_postgres.py --dry-run            # preview only
    python migrate_to_postgres.py --database-url URL   # override DATABASE_URL

Requires:
    - psycopg2-binary
    - An existing SQLite database (path derived from STATE_FILE env var)
    - A PostgreSQL connection string via DATABASE_URL or --database-url
"""

import argparse
import json
import logging
import os
import sqlite3
import sys

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Schema — must match state_manager._ensure_schema() exactly
# ---------------------------------------------------------------------------
PG_SCHEMA = """
CREATE TABLE IF NOT EXISTS bookings (
    id              TEXT PRIMARY KEY,
    status          TEXT NOT NULL DEFAULT 'awaiting_owner',
    booking_data    TEXT NOT NULL,
    source          TEXT,
    customer_email  TEXT,
    raw_message     TEXT,
    gmail_msg_id    TEXT,
    thread_id       TEXT,
    preferred_date  TEXT,
    calendar_event_id TEXT,
    reminders_sent  TEXT NOT NULL DEFAULT '[]',
    created_at      TEXT,
    confirmed_at    TEXT,
    declined_at     TEXT
);

CREATE TABLE IF NOT EXISTS clarifications (
    id              TEXT PRIMARY KEY,
    booking_data    TEXT NOT NULL,
    customer_email  TEXT,
    thread_id       TEXT,
    gmail_msg_id    TEXT,
    missing_fields  TEXT NOT NULL DEFAULT '[]',
    attempt_count   INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT
);

CREATE TABLE IF NOT EXISTS processed_emails (
    msg_id TEXT PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS processed_sms (
    sms_sid TEXT PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS app_state (
    key   TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS booking_events (
    id          SERIAL PRIMARY KEY,
    booking_id  TEXT NOT NULL,
    event_type  TEXT NOT NULL,
    actor       TEXT,
    details     TEXT,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS failed_extractions (
    id              TEXT PRIMARY KEY,
    gmail_msg_id    TEXT NOT NULL UNIQUE,
    thread_id       TEXT,
    customer_email  TEXT NOT NULL,
    raw_body        TEXT,
    error_type      TEXT,
    error_message   TEXT,
    failure_count   INTEGER DEFAULT 1,
    first_failed_at TEXT NOT NULL,
    last_failed_at  TEXT NOT NULL,
    owner_notified  INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS customer_service_history (
    id                  SERIAL PRIMARY KEY,
    booking_id          TEXT NOT NULL,
    customer_phone      TEXT,
    customer_email      TEXT,
    vehicle_key         TEXT,
    service_type        TEXT,
    completed_date      TEXT,
    next_reminder_6m    TEXT,
    next_reminder_12m   TEXT,
    reminder_6m_sent    INTEGER DEFAULT 0,
    reminder_12m_sent   INTEGER DEFAULT 0,
    created_at          TEXT
);

CREATE TABLE IF NOT EXISTS waitlist (
    id          TEXT PRIMARY KEY,
    customer_email TEXT NOT NULL,
    customer_name  TEXT,
    customer_phone TEXT,
    requested_date TEXT NOT NULL,
    booking_data   TEXT NOT NULL,
    gmail_msg_id   TEXT,
    thread_id      TEXT,
    created_at     TEXT NOT NULL,
    notified       INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS message_queue (
    id          SERIAL PRIMARY KEY,
    channel     TEXT NOT NULL,
    recipient   TEXT NOT NULL,
    subject     TEXT,
    body        TEXT NOT NULL,
    booking_id  TEXT,
    status      TEXT NOT NULL DEFAULT 'pending',
    attempts    INTEGER NOT NULL DEFAULT 0,
    last_error  TEXT,
    created_at  TEXT NOT NULL,
    sent_at     TEXT
);
"""

PG_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_bookings_thread        ON bookings(thread_id);
CREATE INDEX IF NOT EXISTS idx_bookings_date          ON bookings(preferred_date);
CREATE INDEX IF NOT EXISTS idx_bookings_status        ON bookings(status);
CREATE INDEX IF NOT EXISTS idx_bookings_status_date   ON bookings(status, preferred_date);
CREATE INDEX IF NOT EXISTS idx_bookings_status_event  ON bookings(status, calendar_event_id);
CREATE INDEX IF NOT EXISTS idx_clarifications_thread  ON clarifications(thread_id);
CREATE INDEX IF NOT EXISTS idx_events_booking         ON booking_events(booking_id);
CREATE INDEX IF NOT EXISTS idx_dlq_notified           ON failed_extractions(owner_notified);
CREATE INDEX IF NOT EXISTS idx_svc_history_6m         ON customer_service_history(next_reminder_6m, reminder_6m_sent);
CREATE INDEX IF NOT EXISTS idx_svc_history_12m        ON customer_service_history(next_reminder_12m, reminder_12m_sent);
CREATE INDEX IF NOT EXISTS idx_svc_history_booking    ON customer_service_history(booking_id);
CREATE INDEX IF NOT EXISTS idx_waitlist_date          ON waitlist(requested_date, notified);
CREATE INDEX IF NOT EXISTS idx_msgqueue_status        ON message_queue(status, created_at);
CREATE UNIQUE INDEX IF NOT EXISTS idx_clarifications_thread_unique ON clarifications(thread_id);
"""

# ---------------------------------------------------------------------------
# Table migration definitions
# ---------------------------------------------------------------------------
# Each entry: (table_name, list_of_columns, has_serial_id)
# has_serial_id=True means the 'id' column is SERIAL and we need to
# reset the sequence after inserting rows with explicit IDs.

TABLES = [
    ("bookings", [
        "id", "status", "booking_data", "source", "customer_email",
        "raw_message", "gmail_msg_id", "thread_id", "preferred_date",
        "calendar_event_id", "reminders_sent", "created_at", "confirmed_at",
        "declined_at",
    ], False),
    ("clarifications", [
        "id", "booking_data", "customer_email", "thread_id", "gmail_msg_id",
        "missing_fields", "attempt_count", "created_at",
    ], False),
    ("processed_emails", ["msg_id"], False),
    ("processed_sms", ["sms_sid"], False),
    ("app_state", ["key", "value"], False),
    ("booking_events", [
        "id", "booking_id", "event_type", "actor", "details", "created_at",
    ], True),
    ("failed_extractions", [
        "id", "gmail_msg_id", "thread_id", "customer_email", "raw_body",
        "error_type", "error_message", "failure_count", "first_failed_at",
        "last_failed_at", "owner_notified",
    ], False),
    ("customer_service_history", [
        "id", "booking_id", "customer_phone", "customer_email", "vehicle_key",
        "service_type", "completed_date", "next_reminder_6m",
        "next_reminder_12m", "reminder_6m_sent", "reminder_12m_sent",
        "created_at",
    ], True),
    ("waitlist", [
        "id", "customer_email", "customer_name", "customer_phone",
        "requested_date", "booking_data", "gmail_msg_id", "thread_id",
        "created_at", "notified",
    ], False),
    ("message_queue", [
        "id", "channel", "recipient", "subject", "body", "booking_id",
        "status", "attempts", "last_error", "created_at", "sent_at",
    ], True),
]


def get_sqlite_path():
    state_file = os.environ.get('STATE_FILE', '/data/booking_state.json')
    return os.path.splitext(state_file)[0] + '.db'


def open_sqlite(path):
    if not os.path.exists(path):
        logger.error("SQLite database not found at %s", path)
        sys.exit(1)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def open_postgres(database_url):
    import psycopg2
    conn = psycopg2.connect(database_url)
    return conn


def create_pg_schema(pg_conn):
    """Create all tables and indexes in PostgreSQL."""
    cur = pg_conn.cursor()
    for stmt in PG_SCHEMA.split(';'):
        stmt = stmt.strip()
        if stmt:
            cur.execute(stmt)
    for stmt in PG_INDEXES.split(';'):
        stmt = stmt.strip()
        if stmt:
            try:
                cur.execute(stmt)
            except Exception as e:
                if 'already exists' in str(e).lower():
                    pg_conn.rollback()
                    continue
                raise
    pg_conn.commit()
    logger.info("PostgreSQL schema created successfully")


def migrate_table(sqlite_conn, pg_conn, table_name, columns, has_serial_id, dry_run=False):
    """Migrate a single table from SQLite to PostgreSQL."""
    # Read all rows from SQLite
    col_list = ', '.join(columns)
    try:
        rows = sqlite_conn.execute(f"SELECT {col_list} FROM {table_name}").fetchall()
    except sqlite3.OperationalError as e:
        logger.warning("Skipping table %s (not found in SQLite): %s", table_name, e)
        return 0

    if not rows:
        logger.info("  %s: 0 rows (empty)", table_name)
        return 0

    if dry_run:
        logger.info("  %s: %d rows (would migrate)", table_name, len(rows))
        return len(rows)

    placeholders = ', '.join(['%s'] * len(columns))
    insert_sql = f"INSERT INTO {table_name} ({col_list}) VALUES ({placeholders}) ON CONFLICT DO NOTHING"

    cur = pg_conn.cursor()
    migrated = 0
    for row in rows:
        values = tuple(row[col] for col in columns)
        try:
            cur.execute(insert_sql, values)
            migrated += 1
        except Exception as e:
            logger.warning("  %s: skipping row %s: %s", table_name, values[:1], e)
            pg_conn.rollback()

    # Reset SERIAL sequence if needed
    if has_serial_id and migrated > 0:
        try:
            cur.execute(
                f"SELECT setval(pg_get_serial_sequence('{table_name}', 'id'), "
                f"COALESCE((SELECT MAX(id) FROM {table_name}), 1))"
            )
        except Exception as e:
            logger.warning("  %s: could not reset sequence: %s", table_name, e)

    pg_conn.commit()
    logger.info("  %s: %d / %d rows migrated", table_name, migrated, len(rows))
    return migrated


def main():
    parser = argparse.ArgumentParser(description="Migrate SQLite data to PostgreSQL")
    parser.add_argument('--dry-run', action='store_true',
                        help="Show what would be migrated without making changes")
    parser.add_argument('--database-url', default=None,
                        help="PostgreSQL connection string (overrides DATABASE_URL env var)")
    parser.add_argument('--sqlite-path', default=None,
                        help="Path to SQLite database (overrides STATE_FILE-based path)")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)s %(message)s',
    )

    database_url = args.database_url or os.environ.get('DATABASE_URL')
    if not database_url:
        logger.error("No PostgreSQL connection string. Set DATABASE_URL or use --database-url")
        sys.exit(1)

    sqlite_path = args.sqlite_path or get_sqlite_path()
    logger.info("SQLite source: %s", sqlite_path)
    logger.info("PostgreSQL target: %s", database_url.split('@')[-1] if '@' in database_url else '(connection string)')

    if args.dry_run:
        logger.info("=== DRY RUN — no changes will be made ===")

    sqlite_conn = open_sqlite(sqlite_path)

    if not args.dry_run:
        pg_conn = open_postgres(database_url)
        create_pg_schema(pg_conn)
    else:
        pg_conn = None

    total = 0
    for table_name, columns, has_serial_id in TABLES:
        count = migrate_table(sqlite_conn, pg_conn, table_name, columns,
                              has_serial_id, dry_run=args.dry_run)
        total += count

    sqlite_conn.close()
    if pg_conn:
        pg_conn.close()

    logger.info("Migration complete: %d total rows %s",
                total, "would be migrated" if args.dry_run else "migrated")


if __name__ == '__main__':
    main()
