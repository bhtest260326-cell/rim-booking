"""message_queue.py — Reliable outbound message delivery with retry (Upgrade 5).

Provides a simple persistent queue backed by the SQLite message_queue table.
A background worker drains the queue, retrying failed messages up to 3 times
with exponential back-off before marking them dead.

Usage:
    from message_queue import enqueue, drain_queue

    enqueue('sms', '+61412345678', 'Your booking is confirmed!')
    enqueue('email', 'owner@example.com', 'New booking received', subject='New Booking')

    # Called by scheduler or startup hook:
    drain_queue()
"""

import logging
import time
from state_manager import StateManager

logger = logging.getLogger(__name__)

_RETRY_DELAYS = [0, 60, 300]  # seconds before each attempt (0, 1 min, 5 min)


def enqueue(channel: str, recipient: str, body: str,
            subject: str = None, booking_id: str = None) -> int:
    """Add a message to the persistent outbound queue.

    Args:
        channel:    'sms' or 'email'
        recipient:  Phone number (sms) or email address (email)
        body:       Message body text
        subject:    Email subject (ignored for SMS)
        booking_id: Optional booking reference for logging
    Returns:
        Row ID of the queued message
    """
    state = StateManager()
    msg_id = state.enqueue_message(
        channel=channel,
        recipient=recipient,
        body=body,
        subject=subject,
        booking_id=booking_id,
    )
    logger.info("Enqueued %s to %s (id=%s, booking=%s)", channel, recipient, msg_id, booking_id)
    return msg_id


def _send_sms(recipient: str, body: str) -> None:
    from twilio_handler import send_sms
    result = send_sms(recipient, body)
    if result is None:
        raise RuntimeError(f"send_sms returned None for {recipient}")


def _send_email(recipient: str, body: str, subject: str) -> None:
    from google_auth import get_gmail_service
    from email.mime.text import MIMEText
    import base64
    msg = MIMEText(body)
    msg['to'] = recipient
    msg['subject'] = subject or '(no subject)'
    svc = get_gmail_service()
    svc.users().messages().send(
        userId='me',
        body={'raw': base64.urlsafe_b64encode(msg.as_bytes()).decode()}
    ).execute()


def drain_queue(max_messages: int = 50) -> int:
    """Process pending messages in the queue. Returns number of messages sent."""
    state = StateManager()
    messages = state.get_pending_messages(limit=max_messages)
    sent = 0
    for msg in messages:
        msg_id = msg['id']
        channel = msg.get('channel', '')
        recipient = msg.get('recipient', '')
        body = msg.get('body', '')
        subject = msg.get('subject')
        attempts = msg.get('attempts', 0)

        # Respect back-off delay
        if attempts > 0:
            import datetime as _dt
            created = msg.get('created_at', '')
            try:
                from datetime import timezone
                age = (_dt.datetime.now(timezone.utc) - _dt.datetime.fromisoformat(created)).total_seconds()
                required_delay = _RETRY_DELAYS[min(attempts, len(_RETRY_DELAYS) - 1)]
                if age < required_delay:
                    continue
            except Exception:
                pass

        try:
            if channel == 'sms':
                _send_sms(recipient, body)
            elif channel == 'email':
                _send_email(recipient, body, subject)
            else:
                logger.warning("Unknown channel %r for message %s — skipping", channel, msg_id)
                state.mark_message_failed(msg_id, f"Unknown channel: {channel}")
                continue

            state.mark_message_sent(msg_id)
            sent += 1
            logger.info("Message %s sent via %s to %s", msg_id, channel, recipient)

        except Exception as exc:
            logger.warning("Message %s failed (attempt %d): %s", msg_id, attempts + 1, exc)
            state.mark_message_failed(msg_id, str(exc)[:200])

    return sent
