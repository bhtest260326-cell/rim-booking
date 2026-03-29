#!/usr/bin/env python3
"""migrate_to_postgres.py — Migrate SQLite data to PostgreSQL (Upgrade 1).

Usage:
    DATABASE_URL=postgres://... SQLITE_DB_PATH=./data/bookings.db python scripts/migrate_to_postgres.py

This script copies all rows from the SQLite database into a PostgreSQL
database. It creates all required tables (matching the SQLite schema) and
bulk-inserts the data. Safe to re-run — uses INSERT OR IGNORE / ON CONFLICT DO NOTHING.

Tables migrated:
    bookings, clarifications, processed_emails, processed_sms, app_state,
    booking_events, failed_extractions, customer_service_history, waitlist,
    message_queue
"""

import os
import sys
import sqlite3
import logging

logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
logger = logging.getLogger(__name__)

SQLITE_PATH = os.environ.get('SQLITE_DB_PATH', './data/bookings.db')
PG_URL = os.environ.get('DATABASE_URL', '')

_TABLES_TO_MIGRATE = [
    'bookings',
    'clarifications',
    'processed_emails',
    'processed_sms',
    'app_state',
    'booking_events',
    'failed_extractions',
    'customer_service_history',
    'waitlist',
    'message_queue',
]

# PostgreSQL DDL — mirrors the SQLite schema using standard SQL types
_PG_DDL = """
CREATE TABLE IF NOT EXISTS bookings (
    id TEXT PRIMARY KEY,
    status TEXT NOT NULL DEFAULT 'awaiting_owner',
    booking_data TEXT,
    customer_email TEXT,
    source TEXT,
    created_at TEXT,
    confirmed_at TEXT,
    declined_at TEXT,
    calendar_event_id TEXT,
    reminders_sent TEXT NOT NULL DEFAULT '[]'
);
CREATE TABLE IF NOT EXISTS clarifications (
    id TEXT PRIMARY KEY,
    customer_email TEXT NOT NULL,
    booking_data TEXT,
    missing_fields TEXT,
    thread_id TEXT UNIQUE,
    created_at TEXT,
    attempt_count INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS processed_emails (
    msg_id TEXT PRIMARY KEY,
    processed_at TEXT
);
CREATE TABLE IF NOT EXISTS processed_sms (
    sms_sid TEXT PRIMARY KEY,
    processed_at TEXT
);
CREATE TABLE IF NOT EXISTS app_state (
    key TEXT PRIMARY KEY,
    value TEXT
);
CREATE TABLE IF NOT EXISTS booking_events (
    id SERIAL PRIMARY KEY,
    booking_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    actor TEXT,
    details TEXT,
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS failed_extractions (
    id SERIAL PRIMARY KEY,
    gmail_msg_id TEXT UNIQUE NOT NULL,
    thread_id TEXT,
    customer_email TEXT,
    subject TEXT,
    error_type TEXT,
    error_message TEXT,
    failure_count INTEGER DEFAULT 1,
    first_failed_at TEXT,
    last_failed_at TEXT,
    owner_notified INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS customer_service_history (
    id SERIAL PRIMARY KEY,
    booking_id TEXT NOT NULL UNIQUE,
    customer_phone TEXT,
    customer_email TEXT,
    vehicle_key TEXT,
    service_type TEXT,
    completed_date TEXT,
    next_reminder_6m TEXT,
    next_reminder_12m TEXT,
    reminder_6m_sent INTEGER DEFAULT 0,
    reminder_12m_sent INTEGER DEFAULT 0,
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS waitlist (
    id TEXT PRIMARY KEY,
    customer_email TEXT NOT NULL,
    customer_name TEXT,
    customer_phone TEXT,
    requested_date TEXT NOT NULL,
    booking_data TEXT NOT NULL,
    gmail_msg_id TEXT,
    thread_id TEXT,
    created_at TEXT NOT NULL,
    notified INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS message_queue (
    id SERIAL PRIMARY KEY,
    channel TEXT NOT NULL,
    recipient TEXT NOT NULL,
    subject TEXT,
    body TEXT NOT NULL,
    booking_id TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    created_at TEXT NOT NULL,
    sent_at TEXT
);
"""


def main():
    if not PG_URL:
        logger.error("DATABASE_URL env var is required")
        sys.exit(1)
    if not os.path.exists(SQLITE_PATH):
        logger.error("SQLite database not found: %s", SQLITE_PATH)
        sys.exit(1)

    try:
        import psycopg2
        import psycopg2.extras
    except ImportError:
        logger.error("psycopg2 not installed — run: pip install psycopg2-binary")
        sys.exit(1)

    sqlite_conn = sqlite3.connect(SQLITE_PATH)
    sqlite_conn.row_factory = sqlite3.Row
    pg_conn = psycopg2.connect(PG_URL)

    try:
        # Create tables in PostgreSQL
        with pg_conn.cursor() as cur:
            cur.execute(_PG_DDL)
        pg_conn.commit()
        logger.info("PostgreSQL schema created/verified")

        # Migrate each table
        for table in _TABLES_TO_MIGRATE:
            try:
                rows = sqlite_conn.execute(f"SELECT * FROM {table}").fetchall()
            except sqlite3.OperationalError:
                logger.warning("Table %s not found in SQLite — skipping", table)
                continue

            if not rows:
                logger.info("Table %s is empty — skipping", table)
                continue

            cols = rows[0].keys()
            placeholders = ','.join(['%s'] * len(cols))
            col_names = ','.join(cols)

            # Tables with SERIAL primary key need special handling
            serial_pk_tables = {'booking_events', 'failed_extractions', 'customer_service_history', 'message_queue'}
            if table in serial_pk_tables:
                insert_sql = (
                    f"INSERT INTO {table} ({col_names}) VALUES ({placeholders}) ON CONFLICT DO NOTHING"
                )
            else:
                insert_sql = (
                    f"INSERT INTO {table} ({col_names}) VALUES ({placeholders}) ON CONFLICT DO NOTHING"
                )

            inserted = 0
            with pg_conn.cursor() as cur:
                for row in rows:
                    try:
                        cur.execute(insert_sql, tuple(row))
                        inserted += 1
                    except Exception as exc:
                        logger.warning("Row insert failed in %s: %s", table, exc)
                        pg_conn.rollback()
            pg_conn.commit()
            logger.info("Migrated %d/%d rows from %s", inserted, len(rows), table)

        logger.info("Migration complete")

    finally:
        sqlite_conn.close()
        pg_conn.close()


if __name__ == '__main__':
    main()
