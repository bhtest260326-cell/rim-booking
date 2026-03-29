import json
import os
import uuid
import sqlite3
import logging
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

_STATE_FILE_JSON = os.environ.get('STATE_FILE', '/data/booking_state.json')
DB_PATH = os.path.splitext(_STATE_FILE_JSON)[0] + '.db'


def _get_conn():
    db_dir = os.path.dirname(DB_PATH)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
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

        CREATE TABLE IF NOT EXISTS booking_events (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            booking_id  TEXT NOT NULL,
            event_type  TEXT NOT NULL,
            actor       TEXT,
            details     TEXT,
            created_at  TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_events_booking ON booking_events(booking_id);

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
        CREATE INDEX IF NOT EXISTS idx_dlq_notified ON failed_extractions(owner_notified);

        CREATE TABLE IF NOT EXISTS customer_service_history (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
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
        CREATE INDEX IF NOT EXISTS idx_svc_history_6m  ON customer_service_history(next_reminder_6m, reminder_6m_sent);
        CREATE INDEX IF NOT EXISTS idx_svc_history_12m ON customer_service_history(next_reminder_12m, reminder_12m_sent);

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
        CREATE INDEX IF NOT EXISTS idx_waitlist_date ON waitlist(requested_date, notified);

        CREATE TABLE IF NOT EXISTS message_queue (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
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
        CREATE INDEX IF NOT EXISTS idx_msgqueue_status ON message_queue(status, created_at);
    """)
    conn.commit()

    # Column migrations — handle tables created before new columns were added.
    # ALTER TABLE ADD COLUMN is idempotent via the try/except below.
    _migrations = [
        "ALTER TABLE clarifications ADD COLUMN attempt_count INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE bookings ADD COLUMN calendar_event_id TEXT",
        "ALTER TABLE bookings ADD COLUMN reminders_sent TEXT NOT NULL DEFAULT '[]'",
        "ALTER TABLE bookings ADD COLUMN confirmed_at TEXT",
        "ALTER TABLE bookings ADD COLUMN declined_at TEXT",
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_svc_history_booking ON customer_service_history(booking_id)",
    ]
    for sql in _migrations:
        try:
            conn.execute(sql)
            conn.commit()
        except sqlite3.OperationalError as e:
            if 'duplicate column name' not in str(e) and 'already exists' not in str(e):
                raise

    # Migration: UNIQUE index on clarifications.thread_id
    try:
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_clarifications_thread_unique ON clarifications(thread_id)")
    except Exception as _e:
        logger.debug("idx_clarifications_thread_unique not created (may already exist): %s", _e)


def _migrate_from_json(conn):
    """One-time migration from the legacy JSON state file, if it exists."""
    already = conn.execute(
        "SELECT value FROM app_state WHERE key='json_migration_done'"
    ).fetchone()
    if already:
        return
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
        except Exception as e:
            logger.warning("Migration: could not insert processed_email %s: %s", mid, e)

    for sid in old.get('processed_sms', []):
        try:
            conn.execute("INSERT OR IGNORE INTO processed_sms(sms_sid) VALUES (?)", (sid,))
        except Exception as e:
            logger.warning("Migration: could not insert processed_sms %s: %s", sid, e)

    conn.execute("INSERT OR REPLACE INTO app_state(key,value) VALUES ('json_migration_done','1')")
    conn.commit()

    if migrated:
        logger.info(f"Migrated {migrated} records from JSON to SQLite")
        backup = _STATE_FILE_JSON + '.migrated'
        try:
            os.rename(_STATE_FILE_JSON, backup)
            logger.info(f"Legacy JSON renamed to {backup}")
        except Exception as e:
            logger.warning("Could not rename legacy JSON to %s: %s", backup, e)


def _check_time_conflict(conn, preferred_date: str, preferred_time: str,
                          new_job_duration: int, exclude_booking_id: str = None) -> tuple[bool, str | None]:
    """Return (has_conflict, conflicting_booking_id) for a proposed time slot."""
    try:
        proposed_start = datetime.strptime(f"{preferred_date} {preferred_time}", "%Y-%m-%d %H:%M")
        proposed_end = proposed_start + timedelta(minutes=new_job_duration)

        rows = conn.execute(
            "SELECT id, booking_data FROM bookings WHERE status='confirmed' AND preferred_date=?",
            (preferred_date,)
        ).fetchall()

        for row in rows:
            if exclude_booking_id and row['id'] == exclude_booking_id:
                continue
            bd = json.loads(row['booking_data'])
            existing_time = bd.get('preferred_time')
            if not existing_time:
                logger.warning(f"Booking {row['id']} has no preferred_time; skipping in conflict check")
                continue
            from maps_handler import get_job_duration_minutes
            existing_duration = get_job_duration_minutes(bd)
            existing_start = datetime.strptime(f"{preferred_date} {existing_time}", "%Y-%m-%d %H:%M")
            existing_end = existing_start + timedelta(minutes=existing_duration)
            buffer = timedelta(minutes=5)
            if proposed_start < existing_end + buffer and proposed_end + buffer > existing_start:
                return (True, row['id'])

        return (False, None)
    except Exception as e:
        logger.warning(f"Time conflict check error (failing open): {e}")
        return (False, None)


VALID_TRANSITIONS = {
    'awaiting_owner': {'confirmed', 'declined'},
    'confirmed': {'cancelled'},
    'declined': set(),
    'cancelled': set(),
}


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

    def _assert_transition(self, current_status: str, new_status: str) -> None:
        """Raise ValueError if the status transition is not permitted."""
        allowed = VALID_TRANSITIONS.get(current_status, set())
        if new_status not in allowed:
            raise ValueError(f'Invalid transition: {current_status!r} → {new_status!r}')

    # ------------------------------------------------------------------
    # Pending bookings
    # ------------------------------------------------------------------

    def _next_booking_number(self) -> str:
        """Return the next sequential booking number (100001, 100002, …) atomically."""
        with _get_conn() as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                row = conn.execute(
                    "SELECT value FROM app_state WHERE key='booking_counter'"
                ).fetchone()
                val = row['value'] if row else None
                current = int(val) if val is not None else 100000
                nxt = current + 1
                conn.execute(
                    "INSERT OR REPLACE INTO app_state(key, value) VALUES ('booking_counter', ?)",
                    (str(nxt),)
                )
                conn.execute("COMMIT")
            except Exception:
                try:
                    conn.execute("ROLLBACK")
                except Exception:
                    pass
                raise
        return str(nxt)

    def create_pending_booking(self, booking_data, source, customer_email=None,
                                raw_message=None, msg_id=None, thread_id=None):
        pending_id = self._next_booking_number()
        raw_message_stored = (raw_message or '')[:2000]
        with self._conn() as conn:
            conn.execute("""
                INSERT INTO bookings
                (id, status, booking_data, source, customer_email, raw_message,
                 gmail_msg_id, thread_id, preferred_date, created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?)
            """, (
                pending_id, 'awaiting_owner', json.dumps(booking_data),
                source, customer_email, raw_message_stored, msg_id, thread_id,
                booking_data.get('preferred_date'),
                datetime.now(timezone.utc).isoformat()
            ))
        self.log_booking_event(pending_id, 'created', actor='ai')
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
            try:
                conn.execute("BEGIN IMMEDIATE")
                row = conn.execute(
                    "SELECT id, status FROM bookings WHERE id=?",
                    (pending_id,)
                ).fetchone()
                if not row:
                    conn.execute("ROLLBACK")
                    return False
                self._assert_transition(row['status'], 'confirmed')
                if booking_data:
                    preferred_date = booking_data.get('preferred_date')
                    preferred_time = booking_data.get('preferred_time')
                    if preferred_date and preferred_time:
                        from maps_handler import get_job_duration_minutes
                        duration = get_job_duration_minutes(booking_data)
                        has_conflict, conflicting_id = _check_time_conflict(
                            conn, preferred_date, preferred_time, duration,
                            exclude_booking_id=pending_id
                        )
                        if has_conflict:
                            logger.warning(
                                f"confirm_booking: time conflict for {pending_id} "
                                f"with existing booking {conflicting_id}"
                            )
                            conn.execute("ROLLBACK")
                            self.log_booking_event(pending_id, 'confirm_failed', actor='system',
                                                   details={'reason': 'time_conflict',
                                                            'conflicting_booking_id': conflicting_id})
                            return False
                now_iso = datetime.now(timezone.utc).isoformat()
                if booking_data:
                    result = conn.execute("""
                        UPDATE bookings
                        SET status='confirmed', confirmed_at=?, booking_data=?,
                            preferred_date=?
                        WHERE id=?
                    """, (now_iso, json.dumps(booking_data),
                          booking_data.get('preferred_date'), pending_id))
                    if result.rowcount == 0:
                        logger.warning(f"confirm_booking: no rows updated for {pending_id}")
                        conn.execute("ROLLBACK")
                        return False
                else:
                    result = conn.execute("""
                        UPDATE bookings SET status='confirmed', confirmed_at=? WHERE id=?
                    """, (now_iso, pending_id))
                    if result.rowcount == 0:
                        logger.warning(f"confirm_booking: no rows updated for {pending_id}")
                        conn.execute("ROLLBACK")
                        return False
                conn.execute("COMMIT")
            except Exception:
                try:
                    conn.execute("ROLLBACK")
                except Exception:
                    pass
                raise
        self.log_booking_event(pending_id, 'confirmed', actor='system')
        logger.info(f"Confirmed booking {pending_id}")
        return True

    def decline_booking(self, pending_id):
        with self._conn() as conn:
            result = conn.execute("""
                UPDATE bookings SET status='declined', declined_at=?
                WHERE id=? AND status='awaiting_owner'
            """, (datetime.now(timezone.utc).isoformat(), pending_id))
            if result.rowcount == 0:
                logger.warning(f"decline_booking: {pending_id} not in awaiting_owner state")
                return False
        self.log_booking_event(pending_id, 'declined', actor='system')
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
    # Audit trail
    # ------------------------------------------------------------------

    def log_booking_event(self, booking_id: str, event_type: str,
                          actor: str = 'system', details: dict = None):
        """Record a state transition or notable action on a booking.

        event_type examples: 'created', 'confirmed', 'declined', 'rescheduled',
                             'cancelled', 'data_updated', 'reminder_sent',
                             'customer_notified', 'expiry_nudge_sent',
                             'duplicate_detected', 'sheets_synced'
        actor examples: 'owner_sms', 'owner_calendar', 'scheduler', 'ai',
                        'customer', 'system', 'dashboard'
        """
        import json as _json
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO booking_events
                   (booking_id, event_type, actor, details, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    booking_id,
                    event_type,
                    actor,
                    _json.dumps(details) if details else None,
                    datetime.now(timezone.utc).isoformat(),
                )
            )

    def get_booking_events(self, booking_id: str) -> list:
        """Return all audit events for a booking, oldest first."""
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT id, booking_id, event_type, actor, details, created_at
                   FROM booking_events WHERE booking_id = ?
                   ORDER BY created_at ASC""",
                (booking_id,)
            ).fetchall()
        result = []
        for row in rows:
            d = dict(row)
            if d.get('details'):
                try:
                    d['details'] = json.loads(d['details'])
                except Exception as e:
                    logger.debug("Could not parse booking event details JSON for event %s: %s", d.get('id'), e)
            result.append(d)
        return result

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

    def get_pending_bookings_for_date(self, date_str):
        """Return booking_data dicts for awaiting_owner bookings on a given date.

        Used by _assign_best_slot so that pending-but-not-yet-confirmed bookings
        are treated as capacity-consuming, preventing overbooking on the same day.
        """
        with self._conn() as conn:
            rows = conn.execute("""
                SELECT booking_data FROM bookings
                WHERE status='awaiting_owner' AND preferred_date=?
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
        """Create a pending clarification record.

        If a clarification already exists for this thread_id (e.g. due to a
        duplicate webhook delivery), the existing record is updated in-place
        rather than creating a second orphaned record.
        """
        with self._conn() as conn:
            existing = conn.execute(
                "SELECT id FROM clarifications WHERE thread_id=?", (thread_id,)
            ).fetchone()
            if existing:
                # Update the existing record rather than creating a duplicate
                conn.execute("""
                    UPDATE clarifications
                    SET booking_data=?, customer_email=?, gmail_msg_id=?,
                        missing_fields=?
                    WHERE thread_id=?
                """, (
                    json.dumps(booking_data), customer_email, msg_id,
                    json.dumps(missing_fields), thread_id
                ))
                return existing['id']

            cid = str(uuid.uuid4())[:8].upper()
            try:
                conn.execute("""
                    INSERT INTO clarifications
                    (id, booking_data, customer_email, thread_id, gmail_msg_id,
                     missing_fields, created_at)
                    VALUES (?,?,?,?,?,?,?)
                """, (
                    cid, json.dumps(booking_data), customer_email, thread_id, msg_id,
                    json.dumps(missing_fields), datetime.now(timezone.utc).isoformat()
                ))
            except sqlite3.IntegrityError:
                logger.warning(f"create_pending_clarification: IntegrityError for thread_id={thread_id!r} — duplicate insert skipped")
                existing2 = conn.execute(
                    "SELECT id FROM clarifications WHERE thread_id=?", (thread_id,)
                ).fetchone()
                return existing2['id'] if existing2 else cid
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
    # Reschedule token replay-attack prevention
    # ------------------------------------------------------------------

    def mark_reschedule_token_used(self, token_hash: str) -> None:
        """Store token hash so it cannot be replayed.

        Uses the app_state table with key 'used_token_<hash[:32]>'.
        Entries are automatically cleaned up after 8 days by
        is_reschedule_token_used() which trims on each write.
        """
        key = f'used_token_{token_hash[:32]}'
        value = datetime.now(timezone.utc).isoformat()
        with self._conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO app_state(key, value) VALUES (?,?)",
                (key, value)
            )
            # Purge entries older than 8 days while we have the connection open
            cutoff = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()
            conn.execute(
                "DELETE FROM app_state WHERE key LIKE 'used_token_%' AND value < ?",
                (cutoff,)
            )

    def is_reschedule_token_used(self, token_hash: str) -> bool:
        """Return True if token was already used."""
        key = f'used_token_{token_hash[:32]}'
        with self._conn() as conn:
            row = conn.execute(
                "SELECT 1 FROM app_state WHERE key=?", (key,)
            ).fetchone()
        return row is not None

    # ------------------------------------------------------------------
    # Dead-Letter Queue (Feature 3)
    # ------------------------------------------------------------------

    def add_to_dlq(self, msg_id: str, thread_id: str, customer_email: str,
                   raw_body: str, error_type: str, error_message: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._conn() as conn:
            conn.execute("""
                INSERT INTO failed_extractions
                (id, gmail_msg_id, thread_id, customer_email, raw_body,
                 error_type, error_message, failure_count, first_failed_at, last_failed_at)
                VALUES (?,?,?,?,?,?,?,1,?,?)
                ON CONFLICT(gmail_msg_id) DO UPDATE SET
                    failure_count  = failure_count + 1,
                    last_failed_at = excluded.last_failed_at,
                    error_type     = excluded.error_type,
                    error_message  = excluded.error_message
            """, (str(uuid.uuid4()), msg_id, thread_id, customer_email,
                  (raw_body or '')[:2000], error_type, error_message, now, now))

    def get_unnotified_dlq_entries(self) -> list:
        with self._conn() as conn:
            rows = conn.execute("""
                SELECT * FROM failed_extractions
                WHERE failure_count >= 3 AND owner_notified = 0
                ORDER BY last_failed_at DESC
            """).fetchall()
        return [dict(r) for r in rows]

    def mark_dlq_notified(self, msg_id: str) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE failed_extractions SET owner_notified = 1 WHERE gmail_msg_id = ?",
                (msg_id,)
            )

    # ------------------------------------------------------------------
    # Customer Service History / Maintenance Reminders (Feature 9)
    # ------------------------------------------------------------------

    def record_completed_service(self, booking_id: str, booking_data: dict) -> None:
        """Record service for future 6m/12m maintenance reminders."""
        try:
            now = datetime.now(timezone.utc)
            vehicle_key = '_'.join(filter(None, [
                str(booking_data.get('vehicle_year', '')),
                str(booking_data.get('vehicle_make', '')),
                str(booking_data.get('vehicle_model', '')),
            ])).lower().strip('_') or 'unknown'
            reminder_6m  = (now + timedelta(days=182)).strftime('%Y-%m-%d')
            reminder_12m = (now + timedelta(days=365)).strftime('%Y-%m-%d')
            with self._conn() as conn:
                conn.execute("""
                    INSERT OR IGNORE INTO customer_service_history
                    (booking_id, customer_phone, customer_email, vehicle_key,
                     service_type, completed_date, next_reminder_6m, next_reminder_12m, created_at)
                    VALUES (?,?,?,?,?,?,?,?,?)
                """, (
                    booking_id,
                    booking_data.get('customer_phone'),
                    booking_data.get('customer_email'),
                    vehicle_key,
                    booking_data.get('service_type', 'rim_repair'),
                    now.strftime('%Y-%m-%d'),
                    reminder_6m,
                    reminder_12m,
                    now.isoformat(),
                ))
        except Exception as e:
            logger.warning(f"record_completed_service failed: {e}")

    def get_maintenance_reminders_due(self, today_str: str, interval: str) -> list:
        """Return service history rows with reminders due on or before today. interval: '6m' or '12m'."""
        if interval not in ('6m', '12m'):
            raise ValueError(f"Invalid interval: {interval!r}")
        col_date = f'next_reminder_{interval}'
        col_sent = f'reminder_{interval}_sent'
        with self._conn() as conn:
            rows = conn.execute(f"""
                SELECT * FROM customer_service_history
                WHERE {col_date} <= ? AND {col_sent} = 0
            """, (today_str,)).fetchall()
        return [dict(r) for r in rows]

    def mark_maintenance_reminder_sent(self, history_id: int, interval: str) -> None:
        if interval not in ('6m', '12m'):
            raise ValueError(f"Invalid interval: {interval!r}")
        col_sent = f'reminder_{interval}_sent'
        with self._conn() as conn:
            conn.execute(f"UPDATE customer_service_history SET {col_sent} = 1 WHERE id = ?", (history_id,))

    # ------------------------------------------------------------------
    # Bulk date cancellation (Feature 9 support)
    # ------------------------------------------------------------------

    def cancel_all_bookings_for_date(self, date_str: str, reason: str, cancelled_by: str = 'owner') -> list:
        """Bulk cancel all confirmed and awaiting-owner bookings for a date.

        Includes calendar_event_id so callers can delete orphaned calendar events.
        Returns list of cancelled booking dicts.
        """
        with self._conn() as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                rows = conn.execute("""
                    SELECT id, booking_data, customer_email, thread_id, calendar_event_id
                    FROM bookings
                    WHERE preferred_date = ? AND status IN ('confirmed', 'awaiting_owner')
                """, (date_str,)).fetchall()
                bookings = [dict(r) for r in rows]
                conn.execute("""
                    UPDATE bookings SET status = 'owner_cancelled'
                    WHERE preferred_date = ? AND status IN ('confirmed', 'awaiting_owner')
                """, (date_str,))
                conn.execute("COMMIT")
            except Exception:
                try:
                    conn.execute("ROLLBACK")
                except Exception:
                    pass
                raise
        for b in bookings:
            self.log_booking_event(b['id'], 'owner_day_cancelled', actor=cancelled_by,
                                   details={'reason': reason, 'date': date_str})
        return bookings

    # ------------------------------------------------------------------
    # Waitlist
    # ------------------------------------------------------------------

    def add_to_waitlist(self, customer_email, customer_name, customer_phone,
                        requested_date, booking_data_dict, gmail_msg_id=None, thread_id=None):
        """Add a customer to the waitlist for a specific date."""
        import uuid, json as _j
        wid = str(uuid.uuid4())[:8]
        now = datetime.utcnow().isoformat()
        with self._conn() as conn:
            conn.execute("""
                INSERT OR IGNORE INTO waitlist
                (id, customer_email, customer_name, customer_phone,
                 requested_date, booking_data, gmail_msg_id, thread_id, created_at)
                VALUES (?,?,?,?,?,?,?,?,?)
            """, (wid, customer_email, customer_name, customer_phone,
                  requested_date, _j.dumps(booking_data_dict),
                  gmail_msg_id, thread_id, now))
        return wid

    def get_waitlist_for_date(self, date_str):
        """Return all unnotified waitlist entries for a date."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM waitlist WHERE requested_date=? AND notified=0 ORDER BY created_at",
                (date_str,)
            ).fetchall()
        return [dict(r) for r in rows]

    def mark_waitlist_notified(self, waitlist_id):
        """Mark a waitlist entry as notified."""
        with self._conn() as conn:
            conn.execute("UPDATE waitlist SET notified=1 WHERE id=?", (waitlist_id,))

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

    # ------------------------------------------------------------------
    # Message Queue (Upgrade 5)
    # ------------------------------------------------------------------

    def enqueue_message(self, channel: str, recipient: str, body: str,
                        subject: str = None, booking_id: str = None) -> int:
        """Add a message to the outbound queue. Returns the new row id."""
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        with _get_conn() as conn:
            cur = conn.execute(
                """INSERT INTO message_queue(channel, recipient, subject, body, booking_id, status, created_at)
                   VALUES (?, ?, ?, ?, ?, 'pending', ?)""",
                (channel, recipient, subject, body, booking_id, now)
            )
            conn.commit()
            return cur.lastrowid

    def get_pending_messages(self, limit: int = 50) -> list:
        """Return pending messages that have been attempted fewer than 3 times."""
        with _get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM message_queue WHERE status='pending' AND attempts < 3 ORDER BY created_at LIMIT ?",
                (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    def mark_message_sent(self, msg_id: int) -> None:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        with _get_conn() as conn:
            conn.execute(
                "UPDATE message_queue SET status='sent', sent_at=? WHERE id=?",
                (now, msg_id)
            )
            conn.commit()

    def mark_message_failed(self, msg_id: int, error: str = None) -> None:
        with _get_conn() as conn:
            conn.execute(
                "UPDATE message_queue SET attempts=attempts+1, last_error=?, status=CASE WHEN attempts+1>=3 THEN 'dead' ELSE 'pending' END WHERE id=?",
                (error, msg_id)
            )
            conn.commit()

    # ------------------------------------------------------------------
    # GDPR helpers (Upgrade 9)
    # ------------------------------------------------------------------

    def get_customer_data(self, email: str) -> dict:
        """Return all data held for a customer (GDPR right of access)."""
        from datetime import datetime, timezone
        import json as _json
        with _get_conn() as conn:
            bookings = [dict(r) for r in conn.execute(
                "SELECT id, status, booking_data, created_at, confirmed_at FROM bookings WHERE customer_email=?",
                (email,)
            ).fetchall()]
            clarifications = [dict(r) for r in conn.execute(
                "SELECT id, missing_fields, attempt_count, created_at FROM clarifications WHERE customer_email=?",
                (email,)
            ).fetchall()]
        return {
            'email': email,
            'exported_at': datetime.now(timezone.utc).isoformat(),
            'bookings': bookings,
            'clarifications': clarifications,
        }

    def anonymise_old_bookings(self, before_date: str) -> int:
        """Anonymise PII for bookings completed before *before_date* (YYYY-MM-DD).

        Returns the number of records anonymised.
        """
        import uuid as _uuid, json as _json
        anon_marker = '[GDPR_PURGED]'
        with _get_conn() as conn:
            rows = conn.execute(
                "SELECT id, booking_data FROM bookings WHERE status='confirmed' AND (confirmed_at < ? OR created_at < ?)",
                (before_date, before_date)
            ).fetchall()
            count = 0
            for row in rows:
                try:
                    bd = _json.loads(row['booking_data']) if row['booking_data'] else {}
                except Exception:
                    bd = {}
                for field in ('customer_name', 'customer_phone', 'address', 'customer_email'):
                    if field in bd:
                        bd[field] = anon_marker
                anon_email = f"purged_{_uuid.uuid4().hex[:8]}@gdpr.deleted"
                conn.execute(
                    "UPDATE bookings SET customer_email=?, booking_data=? WHERE id=?",
                    (anon_email, _json.dumps(bd), row['id'])
                )
                count += 1
            conn.commit()
        return count
