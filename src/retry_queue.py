"""retry_queue.py — DB-backed webhook retry queue with exponential backoff.

When webhook processing (Gmail Pub/Sub or Twilio SMS) fails, the payload is
enqueued here for automatic retry.  A scheduler task drains the queue every
60 seconds, retrying items with exponential backoff (1 min, 5 min, 25 min).

Table schema (created automatically):
    retry_queue(
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        payload_type    TEXT NOT NULL,       -- 'gmail' or 'twilio_sms'
        payload_json    TEXT NOT NULL,
        attempts        INTEGER NOT NULL DEFAULT 0,
        max_attempts    INTEGER NOT NULL DEFAULT 3,
        next_retry_at   TEXT NOT NULL,       -- ISO-8601 UTC
        created_at      TEXT NOT NULL,
        last_error      TEXT
    )
"""

import json
import logging
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

# Exponential backoff delays in seconds: attempt 1 -> 1 min, 2 -> 5 min, 3 -> 25 min
_BACKOFF_SECONDS = [60, 300, 1500]


def _get_conn():
    from state_manager import _get_conn as _sm_conn
    return _sm_conn()


def _ensure_table():
    """Create the retry_queue table if it does not already exist."""
    conn = _get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS retry_queue (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            payload_type    TEXT NOT NULL,
            payload_json    TEXT NOT NULL,
            attempts        INTEGER NOT NULL DEFAULT 0,
            max_attempts    INTEGER NOT NULL DEFAULT 3,
            next_retry_at   TEXT NOT NULL,
            created_at      TEXT NOT NULL,
            last_error      TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_retry_queue_next
            ON retry_queue(next_retry_at);
    """)
    conn.commit()


# Ensure table exists on module import
try:
    _ensure_table()
except Exception:
    # Module may be imported before DB is ready (e.g. during testing);
    # table will be created on first enqueue/process call.
    pass


def enqueue_retry(payload_type: str, payload: dict, max_attempts: int = 3) -> int:
    """Add a failed webhook payload to the retry queue.

    Args:
        payload_type: Identifier such as 'gmail' or 'twilio_sms'.
        payload:      Dict that will be JSON-serialised and replayed on retry.
        max_attempts: Maximum number of retry attempts (default 3).

    Returns:
        Row ID of the enqueued item.
    """
    _ensure_table()
    now = datetime.now(timezone.utc)
    next_retry = now + timedelta(seconds=_BACKOFF_SECONDS[0])
    conn = _get_conn()
    cursor = conn.execute(
        """INSERT INTO retry_queue
           (payload_type, payload_json, attempts, max_attempts, next_retry_at, created_at)
           VALUES (?, ?, 0, ?, ?, ?)""",
        (
            payload_type,
            json.dumps(payload),
            max_attempts,
            next_retry.isoformat(),
            now.isoformat(),
        ),
    )
    conn.commit()
    row_id = cursor.lastrowid
    logger.info("retry_queue: enqueued %s item id=%s (max_attempts=%d)",
                payload_type, row_id, max_attempts)
    return row_id


def process_retry_queue() -> int:
    """Process all due items in the retry queue. Returns count of items processed."""
    _ensure_table()
    now = datetime.now(timezone.utc)
    conn = _get_conn()

    rows = conn.execute(
        """SELECT id, payload_type, payload_json, attempts, max_attempts
           FROM retry_queue
           WHERE next_retry_at <= ?
           ORDER BY next_retry_at ASC
           LIMIT 20""",
        (now.isoformat(),),
    ).fetchall()

    processed = 0
    for row in rows:
        row_id = row['id']
        payload_type = row['payload_type']
        attempts = row['attempts'] + 1
        max_attempts = row['max_attempts']

        try:
            payload = json.loads(row['payload_json'])
        except (json.JSONDecodeError, TypeError) as e:
            logger.error("retry_queue: bad JSON for id=%s — removing: %s", row_id, e)
            conn.execute("DELETE FROM retry_queue WHERE id=?", (row_id,))
            conn.commit()
            continue

        try:
            _replay_payload(payload_type, payload)
            # Success — remove from queue
            conn.execute("DELETE FROM retry_queue WHERE id=?", (row_id,))
            conn.commit()
            logger.info("retry_queue: id=%s (%s) succeeded on attempt %d",
                        row_id, payload_type, attempts)
            processed += 1
        except Exception as exc:
            error_msg = str(exc)[:500]
            if attempts >= max_attempts:
                # Exhausted retries — remove and log
                conn.execute("DELETE FROM retry_queue WHERE id=?", (row_id,))
                conn.commit()
                logger.error(
                    "retry_queue: id=%s (%s) exhausted %d attempts — dropping. Last error: %s",
                    row_id, payload_type, max_attempts, error_msg,
                )
            else:
                # Schedule next retry with exponential backoff
                backoff_idx = min(attempts, len(_BACKOFF_SECONDS) - 1)
                next_retry = now + timedelta(seconds=_BACKOFF_SECONDS[backoff_idx])
                conn.execute(
                    """UPDATE retry_queue
                       SET attempts=?, next_retry_at=?, last_error=?
                       WHERE id=?""",
                    (attempts, next_retry.isoformat(), error_msg, row_id),
                )
                conn.commit()
                logger.warning(
                    "retry_queue: id=%s (%s) attempt %d/%d failed, next retry at %s: %s",
                    row_id, payload_type, attempts, max_attempts,
                    next_retry.isoformat(), error_msg,
                )
            processed += 1

    return processed


def _replay_payload(payload_type: str, payload: dict) -> None:
    """Re-execute a webhook payload. Raises on failure."""
    if payload_type == 'gmail':
        history_id = payload.get('history_id')
        if not history_id:
            raise ValueError("gmail retry payload missing history_id")
        from gmail_poller import process_history_notification
        process_history_notification(history_id)
        # Update last poll timestamp on success
        from state_manager import StateManager
        StateManager().set_app_state(
            'last_gmail_poll_at',
            datetime.now(timezone.utc).isoformat(),
        )

    elif payload_type == 'twilio_sms':
        from twilio_handler import process_single_sms_webhook
        process_single_sms_webhook(
            payload.get('from_number', ''),
            payload.get('body_text', ''),
            payload.get('message_sid', ''),
            media_items=payload.get('media_items'),
        )

    else:
        raise ValueError(f"Unknown payload_type: {payload_type}")


def get_queue_depth() -> int:
    """Return the number of items currently in the retry queue."""
    try:
        _ensure_table()
        conn = _get_conn()
        row = conn.execute("SELECT COUNT(*) FROM retry_queue").fetchone()
        return row[0] if row else 0
    except Exception:
        return 0
