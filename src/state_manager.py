import json
import os
import uuid
import sqlite3
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

_STATE_FILE_JSON = os.environ.get('STATE_FILE', '/data/booking_state.json')
DB_PATH = os.path.splitext(_STATE_FILE_JSON)[0] + '.db'


def _get_conn():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")   # safe concurrent reads/writes
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _ensure_schema(conn):
    conn.executescript("""
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

        CREATE INDEX IF NOT EXISTS idx_bookings_thread        ON bookings(thread_id);
        CREATE INDEX IF NOT EXISTS idx_bookings_date          ON bookings(preferred_date);
        CREATE INDEX IF NOT EXISTS idx_bookings_status        ON bookings(status);
        CREATE INDEX IF NOT EXISTS idx_bookings_status_date   ON bookings(status, preferred_date);
        CREATE INDEX IF NOT EXISTS idx_bookings_status_event  ON bookings(status, calendar_event_id);
        CREATE INDEX IF NOT EXISTS idx_clarifications_thread  ON clarifications(thread_id);
    """)
    conn.commit()


def _migrate_from_json(conn):
    """One-time migration from the legacy JSON state file, if it exists."""
    if not os.path.exists(_STATE_FILE_JSON):
        return
    try:
        with open(_STATE_FILE_JSON, 'r') as f:
            old = json.load(f)
    except Exception as e:
        logger.warning(f"Could not read legacy JSON for migration: {e}")
        return

    migrated = 0

    for bid, b in old.get('pending_bookings', {}).items():
        bd = b.get('booking_data', {})
        try:
            conn.execute("""
                INSERT OR IGNORE INTO bookings
                (id, status, booking_data, source, customer_email, raw_message,
                 gmail_msg_id, thread_id, preferred_date, reminders_sent, created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """, (
                bid, b.get('status', 'awaiting_owner'),
                json.dumps(bd), b.get('source'), b.get('customer_email'),
                b.get('raw_message'), b.get('gmail_msg_id'), b.get('thread_id'),
                bd.get('preferred_date'), json.dumps(b.get('reminders_sent', [])),
                b.get('created_at')
            ))
            migrated += 1
        except Exception as e:
            logger.warning(f"Migration skip pending {bid}: {e}")

    for bid, b in old.get('confirmed_bookings', {}).items():
        bd = b.get('booking_data', {})
        try:
            conn.execute("""
                INSERT OR IGNORE INTO bookings
                (id, status, booking_data, source, customer_email, raw_message,
                 gmail_msg_id, thread_id, preferred_date, calendar_event_id,
                 reminders_sent, created_at, confirmed_at, declined_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                bid, b.get('status', 'confirmed'),
                json.dumps(bd), b.get('source'), b.get('customer_email'),
                b.get('raw_message'), b.get('gmail_msg_id'), b.get('thread_id'),
                bd.get('preferred_date'), b.get('calendar_event_id'),
                json.dumps(b.get('reminders_sent', [])),
                b.get('created_at'), b.get('confirmed_at'), b.get('declined_at')
            ))
            migrated += 1
        except Exception as e:
            logger.warning(f"Migration skip confirmed {bid}: {e}")

    for cid, c in old.get('pending_clarifications', {}).items():
        try:
            conn.execute("""
                INSERT OR IGNORE INTO clarifications
                (id, booking_data, customer_email, thread_id, gmail_msg_id,
                 missing_fields, created_at)
                VALUES (?,?,?,?,?,?,?)
            """, (
                cid, json.dumps(c.get('booking_data', {})),
                c.get('customer_email'), c.get('thread_id'),
                c.get('gmail_msg_id'), json.dumps(c.get('missing_fields', [])),
                c.get('created_at')
            ))
            migrated += 1
        except Exception as e:
            logger.warning(f"Migration skip clarification {cid}: {e}")

    for mid in old.get('processed_emails', []):
        try:
            conn.execute("INSERT OR IGNORE INTO processed_emails(msg_id) VALUES (?)", (mid,))
        except Exception:
            pass

    for sid in old.get('processed_sms', []):
        try:
            conn.execute("INSERT OR IGNORE INTO processed_sms(sms_sid) VALUES (?)", (sid,))
        except Exception:
            pass

    conn.commit()

    if migrated:
        logger.info(f"Migrated {migrated} records from JSON to SQLite")
        backup = _STATE_FILE_JSON + '.migrated'
        try:
            os.rename(_STATE_FILE_JSON, backup)
            logger.info(f"Legacy JSON renamed to {backup}")
        except Exception:
            pass


class StateManager:
    def __init__(self):
        conn = _get_conn()
        _ensure_schema(conn)
        _migrate_from_json(conn)
        conn.close()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _conn(self):
        return _get_conn()

    # ------------------------------------------------------------------
    # Pending bookings
    # ------------------------------------------------------------------

    def create_pending_booking(self, booking_data, source, customer_email=None,
                                raw_message=None, msg_id=None, thread_id=None):
        pending_id = str(uuid.uuid4())[:8].upper()
        with self._conn() as conn:
            conn.execute("""
                INSERT INTO bookings
                (id, status, booking_data, source, customer_email, raw_message,
                 gmail_msg_id, thread_id, preferred_date, created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?)
            """, (
                pending_id, 'awaiting_owner', json.dumps(booking_data),
                source, customer_email, raw_message, msg_id, thread_id,
                booking_data.get('preferred_date'),
                datetime.now(timezone.utc).isoformat()
            ))
        logger.info(f"Created pending booking {pending_id}")
        return pending_id

    def get_pending_booking(self, pending_id):
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM bookings WHERE id=? AND status='awaiting_owner'",
                (pending_id,)
            ).fetchone()
        return self._booking_row_to_dict(row) if row else None

    def get_latest_pending_booking(self):
        with self._conn() as conn:
            row = conn.execute("""
                SELECT * FROM bookings
                WHERE status='awaiting_owner'
                ORDER BY created_at DESC LIMIT 1
            """).fetchone()
        return self._booking_row_to_dict(row) if row else None

    def confirm_booking(self, pending_id, booking_data=None):
        with self._conn() as conn:
            row = conn.execute(
                "SELECT id FROM bookings WHERE id=? AND status='awaiting_owner'",
                (pending_id,)
            ).fetchone()
            if not row:
                return False
            params = [datetime.now(timezone.utc).isoformat(), pending_id]
            if booking_data:
                result = conn.execute("""
                    UPDATE bookings
                    SET status='confirmed', confirmed_at=?, booking_data=?,
                        preferred_date=?
                    WHERE id=?
                """, (params[0], json.dumps(booking_data),
                      booking_data.get('preferred_date'), pending_id))
                if result.rowcount == 0:
                    logger.warning(f"confirm_booking: no rows updated for {pending_id}")
                    return False
            else:
                result = conn.execute("""
                    UPDATE bookings SET status='confirmed', confirmed_at=? WHERE id=?
                """, tuple(params))
                if result.rowcount == 0:
                    logger.warning(f"confirm_booking: no rows updated for {pending_id}")
                    return False
        logger.info(f"Confirmed booking {pending_id}")
        return True

    def decline_booking(self, pending_id):
        with self._conn() as conn:
            conn.execute("""
                UPDATE bookings SET status='declined', declined_at=? WHERE id=?
            """, (datetime.now(timezone.utc).isoformat(), pending_id))
        return True

    def update_confirmed_booking_data(self, booking_id, booking_data):
        """Update booking_data (e.g. preferred_time) on a confirmed booking."""
        with self._conn() as conn:
            conn.execute("""
                UPDATE bookings
                SET booking_data=?, preferred_date=?
                WHERE id=? AND status='confirmed'
            """, (json.dumps(booking_data), booking_data.get('preferred_date'), booking_id))

    def update_pending_booking_data(self, pending_id, booking_data):
        with self._conn() as conn:
            conn.execute("""
                UPDATE bookings
                SET booking_data=?, preferred_date=?
                WHERE id=? AND status='awaiting_owner'
            """, (json.dumps(booking_data), booking_data.get('preferred_date'), pending_id))

    def update_booking_calendar_event(self, pending_id, event_id):
        with self._conn() as conn:
            conn.execute(
                "UPDATE bookings SET calendar_event_id=? WHERE id=?",
                (event_id, pending_id)
            )

    def get_pending_bookings_with_calendar_events(self):
        """Return all awaiting_owner bookings that have a calendar_event_id set (invite fallback path)."""
        with self._conn() as conn:
            rows = conn.execute("""
                SELECT * FROM bookings
                WHERE status='awaiting_owner' AND calendar_event_id IS NOT NULL
            """).fetchall()
        return [self._booking_row_to_dict(row) for row in rows]

    # ------------------------------------------------------------------
    # Reminders
    # ------------------------------------------------------------------

    def mark_reminder_sent(self, booking_id, reminder_type):
        with self._conn() as conn:
            row = conn.execute(
                "SELECT reminders_sent FROM bookings WHERE id=?", (booking_id,)
            ).fetchone()
            if not row:
                return
            reminders = json.loads(row['reminders_sent'] or '[]')
            reminders.append({
                'type': reminder_type,
                'sent_at': datetime.now(timezone.utc).isoformat()
            })
            conn.execute(
                "UPDATE bookings SET reminders_sent=? WHERE id=?",
                (json.dumps(reminders), booking_id)
            )

    def has_reminder_been_sent(self, booking_id, reminder_type):
        with self._conn() as conn:
            row = conn.execute(
                "SELECT reminders_sent FROM bookings WHERE id=?", (booking_id,)
            ).fetchone()
        if not row:
            return False
        reminders = json.loads(row['reminders_sent'] or '[]')
        return any(r['type'] == reminder_type for r in reminders)

    # ------------------------------------------------------------------
    # Confirmed bookings queries
    # ------------------------------------------------------------------

    def get_confirmed_bookings(self):
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM bookings WHERE status='confirmed'"
            ).fetchall()
        return {row['id']: self._booking_row_to_dict(row) for row in rows}

    def get_confirmed_bookings_for_date(self, date_str):
        with self._conn() as conn:
            rows = conn.execute("""
                SELECT booking_data FROM bookings
                WHERE status='confirmed' AND preferred_date=?
            """, (date_str,)).fetchall()
        return [json.loads(r['booking_data']) for r in rows]

    # ------------------------------------------------------------------
    # Deduplication
    # ------------------------------------------------------------------

    def is_email_processed(self, msg_id):
        with self._conn() as conn:
            row = conn.execute(
                "SELECT 1 FROM processed_emails WHERE msg_id=?", (msg_id,)
            ).fetchone()
        return row is not None

    def mark_email_processed(self, msg_id):
        with self._conn() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO processed_emails(msg_id) VALUES (?)", (msg_id,)
            )

    def is_sms_processed(self, sms_sid):
        with self._conn() as conn:
            row = conn.execute(
                "SELECT 1 FROM processed_sms WHERE sms_sid=?", (sms_sid,)
            ).fetchone()
        return row is not None

    def mark_sms_processed(self, sms_sid):
        with self._conn() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO processed_sms(sms_sid) VALUES (?)", (sms_sid,)
            )

    # ------------------------------------------------------------------
    # Clarifications
    # ------------------------------------------------------------------

    def create_pending_clarification(self, booking_data, customer_email,
                                      thread_id, msg_id, missing_fields):
        cid = str(uuid.uuid4())[:8].upper()
        with self._conn() as conn:
            conn.execute("""
                INSERT INTO clarifications
                (id, booking_data, customer_email, thread_id, gmail_msg_id,
                 missing_fields, created_at)
                VALUES (?,?,?,?,?,?,?)
            """, (
                cid, json.dumps(booking_data), customer_email, thread_id, msg_id,
                json.dumps(missing_fields), datetime.now(timezone.utc).isoformat()
            ))
        return cid

    def get_pending_booking_by_thread(self, thread_id):
        """Return a pending clarification for this thread, or None."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM clarifications WHERE thread_id=?", (thread_id,)
            ).fetchone()
        if not row:
            return None
        return {
            'id': row['id'],
            'booking_data': json.loads(row['booking_data']),
            'customer_email': row['customer_email'],
            'thread_id': row['thread_id'],
            'gmail_msg_id': row['gmail_msg_id'],
            'missing_fields': json.loads(row['missing_fields'] or '[]'),
        }

    def thread_has_active_booking(self, thread_id):
        with self._conn() as conn:
            row = conn.execute("""
                SELECT 1 FROM bookings
                WHERE thread_id=? AND status IN ('awaiting_owner','confirmed')
            """, (thread_id,)).fetchone()
        return row is not None

    def update_clarification_booking_data(self, clarification_id, booking_data,
                                           missing_fields):
        with self._conn() as conn:
            conn.execute("""
                UPDATE clarifications
                SET booking_data=?, missing_fields=?
                WHERE id=?
            """, (json.dumps(booking_data), json.dumps(missing_fields),
                  clarification_id))

    def increment_clarification_attempts(self, clarification_id):
        """Increment attempt counter and return the new count."""
        with self._conn() as conn:
            conn.execute("""
                UPDATE clarifications SET attempt_count = attempt_count + 1 WHERE id=?
            """, (clarification_id,))
            row = conn.execute(
                "SELECT attempt_count FROM clarifications WHERE id=?", (clarification_id,)
            ).fetchone()
        return row['attempt_count'] if row else 0

    def remove_pending_clarification(self, clarification_id):
        with self._conn() as conn:
            conn.execute(
                "DELETE FROM clarifications WHERE id=?", (clarification_id,)
            )

    # ------------------------------------------------------------------
    # App state (key-value, used for Gmail historyId etc.)
    # ------------------------------------------------------------------

    def get_app_state(self, key):
        with self._conn() as conn:
            row = conn.execute(
                "SELECT value FROM app_state WHERE key=?", (key,)
            ).fetchone()
        return row['value'] if row else None

    def set_app_state(self, key, value):
        with self._conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO app_state(key, value) VALUES (?,?)",
                (key, str(value))
            )

    # ------------------------------------------------------------------
    # Internal conversion
    # ------------------------------------------------------------------

    def _booking_row_to_dict(self, row):
        if not row:
            return None
        d = dict(row)
        d['booking_data'] = json.loads(d.get('booking_data') or '{}')
        d['reminders_sent'] = json.loads(d.get('reminders_sent') or '[]')
        return d
