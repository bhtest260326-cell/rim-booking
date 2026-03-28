import os
import base64
import logging
from datetime import datetime
from google_auth import get_gmail_service
from googleapiclient.errors import HttpError
from ai_parser import extract_booking_details, merge_booking_data, is_booking_request
from state_manager import StateManager
from twilio_handler import send_owner_confirmation_request
from label_manager import initialise_labels, label_pending_reply, label_awaiting_confirmation, label_processed
from email.mime.text import MIMEText

from feature_flags import get_flag

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Cancellation / reschedule keyword detection
# ---------------------------------------------------------------------------

_CANCEL_KEYWORDS = [
    'cancel', 'cancellation', 'no longer need', "don't need", "dont need",
    'called off', 'not going ahead',
]

_RESCHEDULE_KEYWORDS = [
    'reschedule', 'change date', 'change time', 'different day',
    'move my booking', 'postpone',
]


def _detect_cancel_intent(text: str) -> bool:
    lower = text.lower()
    return any(kw in lower for kw in _CANCEL_KEYWORDS)


def _detect_reschedule_intent(text: str) -> bool:
    lower = text.lower()
    return any(kw in lower for kw in _RESCHEDULE_KEYWORDS)


# ---------------------------------------------------------------------------
# Duplicate / repeat customer detection
# ---------------------------------------------------------------------------

def _check_duplicate_booking(state, customer_email, booking_data):
    """Return existing booking info if same customer+vehicle seen in last 30 days, else None."""
    if not customer_email:
        return None
    from datetime import datetime, timezone, timedelta
    import json
    from state_manager import _get_conn
    cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    with _get_conn() as conn:
        rows = conn.execute(
            """SELECT id, booking_data, status, created_at FROM bookings
               WHERE customer_email = ? AND created_at > ?
               ORDER BY created_at DESC LIMIT 5""",
            (customer_email, cutoff)
        ).fetchall()
    vehicle_make = (booking_data.get('vehicle_make') or '').lower().strip()
    vehicle_model = (booking_data.get('vehicle_model') or '').lower().strip()
    for row in rows:
        try:
            bd = json.loads(row['booking_data'])
            if (bd.get('vehicle_make', '').lower().strip() == vehicle_make and
                    bd.get('vehicle_model', '').lower().strip() == vehicle_model and
                    vehicle_make):
                return {'id': row['id'], 'status': row['status'], 'created_at': row['created_at']}
        except Exception:
            pass
    return None


def get_email_body(message):
    payload = message.get('payload', {})
    body_data = payload.get('body', {}).get('data')
    if body_data:
        return base64.urlsafe_b64decode(body_data).decode('utf-8', errors='ignore')
    for part in payload.get('parts', []):
        if part.get('mimeType') == 'text/plain':
            data = part.get('body', {}).get('data')
            if data:
                return base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')
        for subpart in part.get('parts', []):
            if subpart.get('mimeType') == 'text/plain':
                data = subpart.get('body', {}).get('data')
                if data:
                    return base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')
    return ""

def get_email_headers(message):
    headers = {}
    for h in message.get('payload', {}).get('headers', []):
        if h['name'] in ('From', 'Subject', 'Reply-To', 'Message-ID', 'Auto-Submitted', 'X-Autoreply'):
            headers[h['name']] = h['value']
    return headers


# Sender addresses and subject patterns that indicate automated/system mail
_BOUNCE_SENDERS = ('mailer-daemon@', 'postmaster@', 'noreply@', 'no-reply@', 'donotreply@')
_BOUNCE_SUBJECTS = (
    'delivery status notification',
    'mail delivery failed',
    'mail delivery failure',
    'undeliverable',
    'returned mail',
    'delivery failure',
    'failure notice',
    'auto-reply',
    'automatic reply',
    'out of office',
)

def is_automated_email(customer_email, subject, headers):
    """Return True if this looks like a bounce, DSN, or auto-reply that should be skipped."""
    email_lower = customer_email.lower()
    subject_lower = subject.lower()

    if any(email_lower.startswith(prefix) for prefix in _BOUNCE_SENDERS):
        return True
    if any(pat in subject_lower for pat in _BOUNCE_SUBJECTS):
        return True
    if headers.get('Auto-Submitted', '').lower() not in ('', 'no'):
        return True
    return False

def extract_email_address(from_header):
    if '<' in from_header and '>' in from_header:
        return from_header.split('<')[1].split('>')[0].strip()
    return from_header.strip()

def _process_single_message(service, state, msg_id):
    """Fetch and process one Gmail message by ID. Used by both poll and webhook paths."""
    if state.is_email_processed(msg_id):
        return

    try:
        message = service.users().messages().get(
            userId='me', id=msg_id, format='full'
        ).execute()
    except HttpError as e:
        logger.error(f"Failed to fetch message {msg_id}: {e}")
        return

    # Only process inbox messages
    label_ids = message.get('labelIds', [])
    if 'INBOX' not in label_ids:
        state.mark_email_processed(msg_id)
        return

    headers = get_email_headers(message)
    from_header = headers.get('From', '')
    subject = headers.get('Subject', '(no subject)')
    message_id_header = headers.get('Message-ID', '')
    customer_email = extract_email_address(from_header)
    body = get_email_body(message)
    thread_id = message.get('threadId')

    our_email = os.environ.get('GMAIL_ADDRESS', '')
    if our_email and customer_email.lower() == our_email.lower():
        state.mark_email_processed(msg_id)
        return

    if is_automated_email(customer_email, subject, headers):
        logger.info(f"Skipping automated/bounce email from {customer_email}: {subject}")
        state.mark_email_processed(msg_id)
        return

    logger.info(f"Processing email from {customer_email}: {subject} (thread: {thread_id})")

    existing_pending = state.get_pending_booking_by_thread(thread_id) if thread_id else None

    if existing_pending:
        # Reply to an ongoing clarification — always process, no need to re-classify
        handle_clarification_reply(
            service, state, msg_id, thread_id,
            existing_pending, body, subject, customer_email,
            message_id_header=message_id_header
        )
    elif thread_id and state.thread_has_active_booking(thread_id):
        # Reply on a thread that already has an active/confirmed booking —
        # check for cancellation or reschedule intent
        _handle_active_booking_reply(state, thread_id, body, customer_email, msg_id)
    else:
        # New thread — classify before running any booking workflow
        if not is_booking_request(body, subject):
            logger.info(f"Email from {customer_email} is not a booking request — leaving untouched")
            state.mark_email_processed(msg_id)
            return
        try:
            from ai_parser import is_availability_inquiry
            if is_availability_inquiry(subject, body):
                logger.info(f"Availability inquiry detected from {customer_email} — sending availability table")
                handle_availability_inquiry(msg_id, thread_id, subject, body, customer_email)
                return
        except Exception as e:
            logger.error(f"Availability inquiry check failed for {customer_email}: {e}")
        handle_new_enquiry(
            service, state, msg_id, thread_id,
            body, subject, customer_email, message_id_header
        )

    state.mark_email_processed(msg_id)


def _handle_active_booking_reply(state, thread_id, body_text, customer_email, msg_id):
    """Handle a customer reply on a thread that already has a confirmed/pending booking.

    Detects cancellation and reschedule intent and forwards to the owner via SMS.
    """
    try:
        from state_manager import _get_conn
        import json as _json
        with _get_conn() as conn:
            row = conn.execute(
                """SELECT id, booking_data, status FROM bookings
                   WHERE thread_id = ? AND status IN ('awaiting_owner', 'confirmed')
                   ORDER BY created_at DESC LIMIT 1""",
                (thread_id,)
            ).fetchone()

        if not row:
            logger.info(f"Thread {thread_id} active booking not found — skipping reply")
            return

        booking_id = row['id']
        booking = _json.loads(row['booking_data'])
        status = row['status']
        customer_name = booking.get('customer_name', 'Customer')

        if _detect_cancel_intent(body_text):
            logger.info(f"Cancellation intent detected on thread {thread_id} (booking {booking_id})")
            try:
                from twilio_handler import send_sms
                send_sms(
                    os.environ['OWNER_MOBILE'],
                    f"CANCELLATION REQUEST: {customer_name} (booking {booking_id}) wants to cancel."
                    f" Reply to manage manually."
                )
            except Exception as e:
                logger.error(f"Could not send cancellation SMS to owner: {e}")
            try:
                state.log_booking_event(
                    booking_id, 'cancellation_requested', actor='customer',
                    details={'message_snippet': body_text[:200]}
                )
            except Exception as e:
                logger.error(f"Could not log cancellation event: {e}")

        elif _detect_reschedule_intent(body_text):
            logger.info(f"Reschedule intent detected on thread {thread_id} (booking {booking_id})")
            try:
                from twilio_handler import send_sms
                send_sms(
                    os.environ['OWNER_MOBILE'],
                    f"RESCHEDULE REQUEST: {customer_name} (booking {booking_id}) wants to reschedule."
                    f" Reply to manage manually."
                )
            except Exception as e:
                logger.error(f"Could not send reschedule SMS to owner: {e}")
            try:
                state.log_booking_event(
                    booking_id, 'reschedule_requested', actor='customer',
                    details={'message_snippet': body_text[:200]}
                )
            except Exception as e:
                logger.error(f"Could not log reschedule event: {e}")

        else:
            logger.info(f"Thread {thread_id} has active booking {booking_id} — reply has no actionable intent, skipping")

    except Exception as e:
        logger.error(f"Error handling active booking reply on thread {thread_id}: {e}", exc_info=True)


def poll_gmail():
    """Fallback full-inbox scan used when Pub/Sub webhooks are not configured."""
    try:
        service = get_gmail_service()
        state = StateManager()

        try:
            initialise_labels(service)
        except Exception as e:
            logger.warning(f"Label init skipped: {e}")

        try:
            results = service.users().messages().list(
                userId='me', q='in:inbox', maxResults=20
            ).execute()
        except Exception as e:
            logger.error(f"Gmail list error: {e}")
            return

        messages = results.get('messages', [])
        if not messages:
            return

        logger.info(f"Checking {len(messages)} inbox messages")
        for msg_ref in messages:
            _process_single_message(service, state, msg_ref['id'])

    except HttpError as e:
        logger.error(f"Gmail API error: {e}")
    except Exception as e:
        logger.error(f"Gmail poll error: {e}", exc_info=True)


def register_gmail_watch():
    """Register (or renew) a Gmail push notification watch via Pub/Sub.

    Requires PUBSUB_TOPIC_NAME env var.  Stores the returned historyId so
    process_history_notification() knows where to start.
    """
    topic = os.environ.get('PUBSUB_TOPIC_NAME', '')
    if not topic:
        logger.info("PUBSUB_TOPIC_NAME not set — Gmail push notifications disabled")
        return None

    try:
        service = get_gmail_service()
        result = service.users().watch(
            userId='me',
            body={'labelIds': ['INBOX'], 'topicName': topic}
        ).execute()

        history_id = str(result.get('historyId', ''))
        expiry_ms = result.get('expiration', 0)
        expiry_dt = datetime.fromtimestamp(int(expiry_ms) / 1000).strftime('%Y-%m-%d %H:%M UTC') if expiry_ms else 'unknown'

        state = StateManager()
        if not state.get_app_state('gmail_history_id'):
            state.set_app_state('gmail_history_id', history_id)

        logger.info(f"Gmail watch registered — historyId {history_id}, expires {expiry_dt}")
        return result
    except Exception as e:
        logger.error(f"Gmail watch registration failed: {e}")
        return None


def _process_sent_message(service, state, msg_id):
    """Detect when the owner sends a mixed-intent draft and auto-confirm the booking.

    When the owner sends the draft answer (instead of replying YES to the SMS),
    this creates the calendar event and confirms the booking automatically.
    Only acts on bookings that were created from a mixed-intent draft (have draft_id set).
    """
    sent_key = f'sent_{msg_id}'
    if state.is_email_processed(sent_key):
        return
    try:
        message = service.users().messages().get(
            userId='me', id=msg_id, format='metadata',
            metadataHeaders=['From', 'Subject']
        ).execute()

        if 'SENT' not in message.get('labelIds', []):
            return

        thread_id = message.get('threadId')
        if not thread_id:
            return

        from state_manager import _get_conn
        import json as _json
        with _get_conn() as conn:
            row = conn.execute(
                """SELECT id, booking_data FROM bookings
                   WHERE thread_id = ? AND status = 'awaiting_owner'
                   ORDER BY created_at DESC LIMIT 1""",
                (thread_id,)
            ).fetchone()

        if not row:
            return

        booking_id = row['id']
        booking_data = _json.loads(row['booking_data'])

        # Only auto-confirm bookings that originated from a mixed-intent draft
        if not booking_data.get('draft_id'):
            return

        pending = state.get_pending_booking(booking_id)
        if not pending:
            return

        logger.info(f"Owner sent draft reply for booking {booking_id} (thread {thread_id}) — auto-confirming")
        from twilio_handler import handle_owner_confirm
        handle_owner_confirm(booking_id, pending)

    except Exception as e:
        logger.error(f"_process_sent_message error for msg {msg_id}: {e}", exc_info=True)
    finally:
        state.mark_email_processed(sent_key)


def process_history_notification(new_history_id):
    """Process new Gmail messages since the last stored historyId.

    Called by the /webhook/gmail endpoint when Pub/Sub delivers a notification.
    """
    try:
        service = get_gmail_service()
        state = StateManager()

        last_id = state.get_app_state('gmail_history_id')

        # Always advance the stored historyId
        state.set_app_state('gmail_history_id', str(new_history_id))

        if not last_id:
            logger.warning("No stored historyId — skipping history fetch (will catch up on next notification)")
            return

        try:
            history_resp = service.users().history().list(
                userId='me',
                startHistoryId=last_id,
                historyTypes=['messageAdded'],
                labelId='INBOX'
            ).execute()
        except HttpError as e:
            if 'historyId' in str(e):
                # History expired — fall back to full scan
                logger.warning("History expired, falling back to full inbox scan")
                poll_gmail()
                return
            raise

        try:
            initialise_labels(service)
        except Exception:
            pass

        for record in history_resp.get('history', []):
            for msg_added in record.get('messagesAdded', []):
                msg_id = msg_added['message']['id']
                _process_single_message(service, state, msg_id)

        # Also watch SENT label so we can auto-confirm when the owner sends a draft reply
        try:
            sent_history_resp = service.users().history().list(
                userId='me',
                startHistoryId=last_id,
                historyTypes=['messageAdded'],
                labelId='SENT'
            ).execute()
            for record in sent_history_resp.get('history', []):
                for msg_added in record.get('messagesAdded', []):
                    _process_sent_message(service, state, msg_added['message']['id'])
        except Exception as _se:
            logger.warning(f"Sent history processing error (non-fatal): {_se}")

    except Exception as e:
        logger.error(f"History notification processing error: {e}", exc_info=True)


def _assign_best_slot(booking_data, state):
    """Compute the next available slot on the requested date and update booking_data in place.

    Tries preferred_date first, then alternative_dates in order (customer's stated options),
    then falls back to next business day only if none of the preferred dates have room.
    The customer's original preference is preserved in notes if the date changes.
    """
    target_date = booking_data.get('preferred_date')
    if not target_date:
        return

    try:
        from maps_handler import find_next_available_slot
        job_address = booking_data.get('address') or booking_data.get('suburb') or ''
        original_time = booking_data.get('preferred_time')

        # Build the ordered list of dates the customer is happy with
        alternative_dates = booking_data.get('alternative_dates') or []
        preferred_dates = [target_date] + [d for d in alternative_dates if d and d != target_date]

        found_date = None
        found_time = None

        for candidate_date in preferred_dates:
            day_bookings = state.get_confirmed_bookings_for_date(candidate_date)
            slot_date, slot_time = find_next_available_slot(
                candidate_date, job_address, day_bookings, new_booking_data=booking_data
            )
            # find_next_available_slot advances to next business day if no room —
            # only accept the result if it actually landed on the candidate date
            if slot_date == candidate_date:
                found_date = slot_date
                found_time = slot_time
                break

        # None of the preferred dates had room — fall back to next business day
        if not found_date:
            day_bookings = state.get_confirmed_bookings_for_date(target_date)
            found_date, found_time = find_next_available_slot(
                target_date, job_address, day_bookings, new_booking_data=booking_data
            )

        if found_date != target_date or found_time != original_time:
            pref_days = ', '.join(preferred_dates) if len(preferred_dates) > 1 else target_date
            pref_note = f"Customer requested {pref_days} around {original_time or 'any time'}"
            existing_notes = booking_data.get('notes') or ''
            booking_data['notes'] = f"{pref_note}. {existing_notes}".strip('. ') if existing_notes else pref_note

        # If the slot was advanced to a different date, add a clear waitlist note
        if found_date != target_date:
            logger.info(f"Booking slot advanced: customer wanted {target_date}, assigned {found_date}")
            existing_notes = booking_data.get('notes', '') or ''
            waitlist_note = f"Requested {target_date} — assigned {found_date} (original date was full)."
            booking_data['notes'] = f"{waitlist_note} {existing_notes}".strip() if existing_notes else waitlist_note
            # preferred_date updated below

        booking_data['preferred_date'] = found_date
        booking_data['preferred_time'] = found_time
        logger.info(f"Slot assigned: {found_date} {found_time} (preferred {preferred_dates}, original time {original_time})")
    except Exception as e:
        logger.warning(f"Slot computation skipped, keeping AI-extracted time: {e}")


def _is_date_available(date_str: str, booking_data: dict, state) -> bool:
    """Return True if there is at least one slot available on date_str for this booking.

    Fails open (returns True) so a check error never silently rejects a valid booking.
    """
    try:
        from maps_handler import find_next_available_slot
        job_address = booking_data.get('address') or booking_data.get('suburb') or ''
        day_bookings = state.get_confirmed_bookings_for_date(date_str)
        slot_date, _ = find_next_available_slot(
            date_str, job_address, day_bookings, new_booking_data=booking_data
        )
        return slot_date == date_str
    except Exception as e:
        logger.warning(f"Date availability check failed for {date_str}: {e}")
        return True  # fail open


def _send_date_full_email(service, to_email: str, subject: str, requested_date: str,
                          first_name: str, booking_data: dict, thread_id: str, state,
                          missing_fields: list = None) -> None:
    """Email the customer that their requested date is full, show fresh availability,
    and ask them to pick an available day (including all required details if still needed).
    """
    from maps_handler import get_week_availability, get_job_duration_minutes
    from email_utils import send_customer_email, _h2, _ul
    try:
        from datetime import datetime as _dt
        try:
            day_name = _dt.strptime(requested_date, '%Y-%m-%d').strftime('%A %-d %b')
        except Exception:
            day_name = requested_date

        duration = get_job_duration_minutes(booking_data)
        availability = get_week_availability(duration, assumed_travel_minutes=25)

        table_rows = ''
        for idx, slot in enumerate(availability):
            # Insert a separator row before the 6th item when next-week days were appended
            if idx == 5 and len(availability) > 5:
                table_rows += (
                    '<tr><td colspan="2" style="padding:6px 14px;font-size:12px;font-weight:700;'
                    'color:#64748b;background:#f8fafc;text-transform:uppercase;'
                    'letter-spacing:0.05em;">Following week</td></tr>'
                )

            if slot['available']:
                badge = '<span style="color:#16a34a;font-weight:600;">Yes</span>'
            else:
                badge = '<span style="color:#dc2626;font-weight:600;">No</span>'

            # Format date as "30 Mar" (no leading zero, cross-platform)
            try:
                slot_dt = _dt.strptime(slot['date'], '%Y-%m-%d')
                short_date = slot_dt.strftime('%d %b').lstrip('0')
            except Exception:
                short_date = ''

            day_with_date = f'{slot["day_name"]} {short_date}' if short_date else slot["day_name"]

            table_rows += (
                f'<tr>'
                f'<td style="padding:10px 16px;border-bottom:1px solid #e2e8f0;">{day_with_date}</td>'
                f'<td style="padding:10px 16px;border-bottom:1px solid #e2e8f0;">{badge}</td>'
                f'</tr>'
            )

        fields_section = ''
        if missing_fields:
            fields_section = (
                f'<p style="margin:16px 0 4px;"><strong>To confirm your booking in one reply,</strong> '
                f'please also include:</p>'
                + _ul(missing_fields)
            )

        content_html = (
            f'<p>Hi {first_name},</p>'
            f'<p>Thank you for your reply! Unfortunately <strong>{day_name}</strong> is '
            f'fully booked and we\'re unable to take any further appointments that day.</p>'
            f'<p>Here is our current availability — please choose one of the available days'
            f'{" and include your details below" if missing_fields else ""}:</p>'
            + _h2('Availability')
            + '<table style="border-collapse:collapse;width:100%;max-width:340px;'
            'border:1px solid #e2e8f0;margin:8px 0 16px;">'
            '<thead><tr style="background:#C41230;">'
            '<th style="padding:10px 16px;text-align:left;font-size:13px;font-weight:700;'
            'text-transform:uppercase;letter-spacing:0.05em;color:#ffffff;'
            'border-bottom:2px solid #C41230;">Day</th>'
            '<th style="padding:10px 16px;text-align:left;font-size:13px;font-weight:700;'
            'text-transform:uppercase;letter-spacing:0.05em;color:#ffffff;'
            'border-bottom:2px solid #C41230;">Available</th>'
            '</tr></thead>'
            f'<tbody>{table_rows}</tbody>'
            '</table>'
            + fields_section
            + '<p>Payment is by EFTPOS on the day of the appointment. '
            'We look forward to hearing from you!</p>'
            '<p>Kind regards,<br><strong>Rim Repair Team</strong></p>'
        )

        reply_subject = subject if subject.lower().startswith('re:') else f'Re: {subject}'
        send_customer_email(service, to_email, reply_subject, content_html, thread_id=thread_id)
        logger.info(f"Date-full rejection email sent to {to_email} (requested {requested_date})")
    except Exception as e:
        logger.error(f"Could not send date-full email to {to_email}: {e}")


def handle_availability_inquiry(msg_id, thread_id, subject, body, customer_email):
    """Respond to a customer asking about availability.

    Attempts to extract service details (rim count, service type) to calculate
    the required duration. Falls back to the default 2-rim duration if unclear.
    Checks the next 5 business days and replies with a formatted availability table.
    """
    from ai_parser import extract_booking_details, format_availability_response, is_booking_request
    from maps_handler import get_week_availability, get_job_duration_minutes
    from state_manager import StateManager
    from feature_flags import get_flag

    state = StateManager()

    if not get_flag('flag_auto_email_replies'):
        logger.info(f"Auto email replies disabled — skipping availability response for {customer_email}")
        state.mark_email_processed(msg_id)
        return

    # Extract whatever details the customer already provided in their first email.
    # This fixes two bugs: (a) we were assigning the raw tuple to booking_data instead
    # of unpacking it, and (b) we need the missing_fields list to show only what's
    # still needed, and to store a pending clarification so the customer's reply
    # correctly merges with what was already extracted.
    booking_data = {}
    missing_fields = []
    try:
        booking_data, missing_fields, _ = extract_booking_details(body, subject, customer_email)
        if not booking_data:
            booking_data = {}
        duration = get_job_duration_minutes(booking_data)

        # Build service description for the email
        num_rims = booking_data.get('num_rims')
        service_type = (booking_data.get('service_type') or '').lower()
        if service_type == 'paint_touchup':
            service_description = 'paint touch-up'
        elif num_rims:
            try:
                n = int(num_rims)
                service_description = f"{n}-rim repair"
            except (ValueError, TypeError):
                service_description = 'rim repair'
        else:
            service_description = 'rim repair'
            duration = 120  # default: 1 rim / 2 hours

        customer_name = booking_data.get('customer_name') or 'there'
        first_name = customer_name.split()[0].title() if customer_name != 'there' else 'there'

    except Exception as e:
        logger.error(f"extract_booking_details raised an exception for availability inquiry msg {msg_id}: {e}")
        state.add_to_dlq(msg_id, thread_id, customer_email, body, 'api_error', str(e))
        state.mark_email_processed(msg_id)
        return

    # Get week availability
    try:
        availability = get_week_availability(duration, assumed_travel_minutes=25)
    except Exception as e:
        logger.error(f"get_week_availability failed: {e}")
        state.mark_email_processed(msg_id)
        return

    # Format and send the response.
    # ORDERING: create the pending clarification BEFORE sending the email so that
    # if the email succeeds but clarification creation fails, the customer's reply
    # can still be retried (the email will already be in their inbox). The inverse
    # (email fails, clarification exists) is harmless — the clarification record
    # will be reused when the next polling cycle retries.
    from email_utils import send_customer_email

    requested_date = booking_data.get('preferred_date')
    inner_html = format_availability_response(
        first_name, availability, service_description,
        missing_fields=missing_fields if missing_fields else None,
        requested_date=requested_date,
    )

    service = get_gmail_service()
    reply_subject = subject if subject.lower().startswith('re:') else f"Re: {subject}"

    still_needed = missing_fields + ['your preferred available day'] if missing_fields else ['your preferred available day']

    # Step 1: persist clarification record first
    try:
        state.create_pending_clarification(
            booking_data=booking_data,
            customer_email=customer_email,
            thread_id=thread_id,
            msg_id=msg_id,
            missing_fields=still_needed,
        )
    except Exception as e:
        logger.error(f"Could not create pending clarification for {customer_email}: {e}")

    # Step 2: send the availability email
    try:
        send_customer_email(service, customer_email, reply_subject, inner_html, thread_id=thread_id)
        logger.info(f"Availability response sent to {customer_email} ({service_description}, {duration} min)")
    except Exception as e:
        logger.error(f"Could not send availability response to {customer_email}: {e}")

    # Step 3: apply Gmail label regardless of email send outcome
    try:
        label_processed(service, msg_id)
    except Exception as e:
        logger.warning(f"Could not label availability reply: {e}")

    state.mark_email_processed(msg_id)


def handle_new_enquiry(service, state, msg_id, thread_id, body, subject, customer_email, message_id_header=None):
    """Process a brand new booking enquiry."""
    try:
        booking_data, missing_fields, needs_clarification = extract_booking_details(
            body, subject, customer_email
        )
    except Exception as e:
        logger.error(f"extract_booking_details raised an exception for msg {msg_id}: {e}")
        state.add_to_dlq(msg_id, thread_id, customer_email, body, 'api_error', str(e))
        state.mark_email_processed(msg_id)
        return

    # If extraction returned an empty booking (system/API error), do not email the customer.
    # Add to DLQ and mark processed to stop the infinite retry loop.
    if not booking_data:
        logger.error(f"Extraction returned no data for msg {msg_id} — adding to DLQ")
        state.add_to_dlq(msg_id, thread_id, customer_email, body, 'extraction_empty', 'AI extraction returned no data')
        state.mark_email_processed(msg_id)
        return

    # --- AI Confidence Gating ---
    try:
        confidence = booking_data.get('confidence', 'medium')
        if booking_data.get('low_confidence'):
            logger.warning(f"Low confidence extraction for {msg_id} — adding to DLQ for owner review")
            try:
                state.add_to_dlq(msg_id, thread_id, customer_email, body[:2000],
                                 'low_confidence', 'AI confidence was low on extraction')
            except Exception as e:
                logger.error(f"Could not add low-confidence booking to DLQ: {e}")
            # Continue processing — don't skip, just flag it
            existing_notes = booking_data.get('notes', '') or ''
            booking_data['notes'] = f"LOW AI CONFIDENCE — please verify details. {existing_notes}".strip()
    except Exception as e:
        logger.error(f"Confidence gating error: {e}")
        confidence = 'medium'

    # --- Service Area Validation ---
    try:
        from maps_handler import is_within_service_area
        address_to_check = booking_data.get('address') or booking_data.get('suburb') or ''
        if address_to_check and not is_within_service_area(address_to_check):
            logger.info(f"Booking rejected: address '{address_to_check}' outside service area")
            try:
                from email_utils import send_customer_email, _p, DARK
                name = booking_data.get('customer_name', 'there')
                first = name.split()[0] if name and name != 'there' else 'there'
                content = (
                    _p(f'Hi {first},')
                    + _p('Thank you for getting in touch with Perth Swedish &amp; European Auto Centre.')
                    + _p('Unfortunately, your location appears to be outside our current service area '
                         '(Perth metropolitan area). We\'re unable to accommodate your booking at this time.')
                    + _p('We appreciate your interest and apologise for the inconvenience.')
                    + f'<p style="margin:24px 0 0;color:{DARK};font-size:15px;">'
                      f'Kind regards,<br><strong style="color:#C41230;">Rim Repair Team</strong></p>'
                )
                send_customer_email(service, customer_email, 'Re: Your Rim Repair Enquiry', content,
                                    thread_id=thread_id, message_id_header=message_id_header)
            except Exception as e:
                logger.error(f"Could not send out-of-area decline email: {e}")
            state.mark_email_processed(msg_id)
            return
    except Exception as e:
        logger.error(f"Service area check error: {e}")

    if needs_clarification:
        if get_flag('flag_auto_email_replies'):
            send_clarification_email(service, customer_email, subject, missing_fields,
                                      thread_id=thread_id, message_id_header=message_id_header,
                                      booking_data=booking_data)
        else:
            logger.info(f"Auto email replies disabled — clarification not sent to {customer_email}")
        state.create_pending_clarification(
            booking_data=booking_data,
            customer_email=customer_email,
            thread_id=thread_id,
            msg_id=msg_id,
            missing_fields=missing_fields
        )
        try:
            label_pending_reply(service, msg_id)
        except Exception:
            pass
        logger.info(f"Clarification sent to {customer_email}, thread {thread_id}")
    else:
        # --- Duplicate / Repeat Customer Detection ---
        try:
            duplicate = _check_duplicate_booking(state, customer_email, booking_data)
            if duplicate:
                logger.warning(
                    f"Duplicate booking detected: same customer+vehicle as booking "
                    f"{duplicate['id']} ({duplicate['status']}) created {duplicate['created_at']}"
                )
                existing_notes = booking_data.get('notes', '') or ''
                booking_data['notes'] = (
                    f"POSSIBLE DUPLICATE: Same vehicle as booking {duplicate['id']} "
                    f"({duplicate['status']}). {existing_notes}"
                ).strip()
        except Exception as e:
            logger.error(f"Duplicate check error: {e}")

        # --- Date Availability Check ---
        # If the customer has specified a date, verify it actually has room.
        # If full, send a polite rejection with updated availability rather than
        # silently rebooking them on a different day.
        preferred_date = booking_data.get('preferred_date')
        if preferred_date and not _is_date_available(preferred_date, booking_data, state):
            first_name = (booking_data.get('customer_name') or 'there').split()[0]
            logger.info(f"Requested date {preferred_date} is full for {customer_email} — sending date-full reply")
            _send_date_full_email(
                service, customer_email, subject, preferred_date,
                first_name, booking_data, thread_id, state
            )
            # Auto-enroll in waitlist for the requested but unavailable date
            if preferred_date:
                try:
                    wid = state.add_to_waitlist(
                        customer_email=customer_email,
                        customer_name=booking_data.get('customer_name'),
                        customer_phone=booking_data.get('customer_phone'),
                        requested_date=preferred_date,
                        booking_data_dict=booking_data,
                        gmail_msg_id=msg_id,
                        thread_id=thread_id
                    )
                    logger.info(f"Customer {customer_email} added to waitlist for {preferred_date} (waitlist ID: {wid})")
                except Exception as e:
                    logger.warning(f"Waitlist enroll failed (non-fatal): {e}")
            # Keep as a pending clarification so the next reply is handled correctly
            state.create_pending_clarification(
                booking_data=booking_data,
                customer_email=customer_email,
                thread_id=thread_id,
                msg_id=msg_id,
                missing_fields=['your preferred available day']
            )
            try:
                label_pending_reply(service, msg_id)
            except Exception:
                pass
            state.mark_email_processed(msg_id)
            return

        # Check for returning customer
        try:
            from state_manager import _get_conn
            import json as _json
            with _get_conn() as _conn:
                _hist = _conn.execute(
                    """SELECT csh.completed_date, csh.service_type
                       FROM customer_service_history csh
                       WHERE csh.customer_email = ?
                       ORDER BY csh.completed_date DESC LIMIT 1""",
                    (customer_email,)
                ).fetchone()
            if _hist:
                last_date = _hist['completed_date']
                last_svc = (_hist['service_type'] or 'rim repair').replace('_', ' ')
                returning_note = f"Returning customer — last service: {last_date} ({last_svc})"
                existing_notes = booking_data.get('notes') or ''
                booking_data['notes'] = (existing_notes + '\n' + returning_note).strip()
                logger.info(f"Returning customer detected: {customer_email}, last service {last_date}")
        except Exception as _e:
            logger.debug(f"Returning customer check failed (non-fatal): {_e}")

        _assign_best_slot(booking_data, state)
        pending_id = state.create_pending_booking(
            booking_data=booking_data,
            source='email',
            customer_email=customer_email,
            raw_message=body,
            msg_id=msg_id,
            thread_id=thread_id
        )

        # Log creation event with confidence level
        try:
            state.log_booking_event(
                pending_id, 'created', actor='ai',
                details={'confidence': confidence, 'customer_email': customer_email}
            )
        except Exception as e:
            logger.error(f"Could not log booking creation event: {e}")

        send_owner_confirmation_request(pending_id, booking_data)
        try:
            label_awaiting_confirmation(service, msg_id)
        except Exception:
            pass
        logger.info(f"Owner confirmation sent for booking {pending_id}")


def handle_clarification_reply(service, state, msg_id, thread_id, existing_pending, body, subject, customer_email, message_id_header=None):
    """Customer replied with missing info — merge with existing partial booking."""
    original_data = existing_pending.get('booking_data', {})
    _mixed_draft_id = None      # set in mixed block; used after slot assignment
    _mixed_question_body = None

    # --- Intent Classification ---
    # Before extracting booking details, classify whether this reply is a question
    # rather than booking information. Questions must not consume clarification
    # attempts or trigger another booking-details request.
    existing_missing = existing_pending.get('missing_fields', [])
    first_name = (original_data.get('customer_name') or 'there').split()[0]
    reply_subject = subject if subject.lower().startswith('re:') else f'Re: {subject}'

    try:
        from ai_parser import classify_clarification_reply, generate_faq_response, draft_off_scope_reply
        intent = classify_clarification_reply(body, subject)
    except Exception as _ie:
        logger.error(f"Intent classification failed: {_ie} — proceeding as booking_detail")
        intent = 'booking_detail'

    if intent == 'faq_question':
        # Customer asked a FAQ-type question (pricing, area, hours, payment, etc.)
        # Auto-answer it and re-ask missing fields, but do NOT consume an attempt.
        logger.info(f"FAQ question detected from {customer_email} on thread {thread_id} — auto-answering")
        try:
            faq_html = generate_faq_response(body, first_name, existing_missing, original_data)
            if get_flag('flag_auto_email_replies'):
                from email_utils import send_customer_email
                send_customer_email(service, customer_email, reply_subject, faq_html, thread_id=thread_id)
                logger.info(f"FAQ auto-reply sent to {customer_email}")
            else:
                logger.info(f"Auto email replies disabled — FAQ reply not sent to {customer_email}")
        except Exception as _fe:
            logger.error(f"FAQ response error for {customer_email}: {_fe}")
        try:
            label_pending_reply(service, msg_id)
        except Exception:
            pass
        state.mark_email_processed(msg_id)
        return

    elif intent == 'off_scope':
        # Customer asked something outside our FAQ scope.
        # Create a draft reply for owner review, label the email blue, do NOT send.
        logger.info(f"Off-scope message from {customer_email} on thread {thread_id} — creating draft for owner review")
        try:
            draft_html = draft_off_scope_reply(body, first_name, existing_missing, original_data)
            from email_utils import create_gmail_draft
            draft_id = create_gmail_draft(service, customer_email, reply_subject, draft_html, thread_id=thread_id)
            if draft_id:
                logger.info(f"Off-scope draft {draft_id} created for {customer_email}")
            else:
                logger.warning(f"Draft creation returned None for {customer_email}")
        except Exception as _de:
            logger.error(f"Off-scope draft creation error for {customer_email}: {_de}")
        try:
            from label_manager import label_assistance_required
            label_assistance_required(service, msg_id)
        except Exception as _le:
            logger.warning(f"Could not apply Assistance Required label: {_le}")
        try:
            state.log_booking_event(
                existing_pending['id'], 'off_scope_question', actor='customer',
                details={'message_snippet': body[:200], 'thread_id': thread_id}
            )
        except Exception:
            pass
        state.mark_email_processed(msg_id)
        return

    elif intent == 'mixed':
        # Customer provided booking details AND asked a question in the same message.
        # Draft a reply answering their question and label blue for owner review,
        # then fall through so the booking details are still extracted and processed.
        logger.info(f"Mixed intent (booking + question) from {customer_email} on thread {thread_id} — drafting answer and continuing booking flow")
        try:
            # Pass empty missing_fields — the current message is providing booking details
            # so we don't know yet what's still missing. The booking flow below will handle
            # any remaining fields. The draft should only answer the embedded question.
            draft_html = draft_off_scope_reply(body, first_name, [], original_data)
            from email_utils import create_gmail_draft
            draft_id = create_gmail_draft(service, customer_email, reply_subject, draft_html, thread_id=thread_id)
            if draft_id:
                _mixed_draft_id = draft_id
                _mixed_question_body = body
                logger.info(f"Mixed-intent draft {draft_id} created for {customer_email}")
            else:
                logger.warning(f"Mixed-intent draft creation returned None for {customer_email}")
        except Exception as _de:
            logger.error(f"Mixed-intent draft creation error for {customer_email}: {_de}")
        try:
            from label_manager import label_assistance_required
            label_assistance_required(service, msg_id)
        except Exception as _le:
            logger.warning(f"Could not apply Assistance Required label for mixed intent: {_le}")
        try:
            state.log_booking_event(
                existing_pending['id'], 'mixed_intent_question', actor='customer',
                details={'message_snippet': body[:200], 'thread_id': thread_id}
            )
        except Exception:
            pass
        # DO NOT return — fall through to extract booking details from this message

    # --- intent == 'booking_detail' or 'mixed' — proceed with normal extraction ---

    # Extract data from the reply only
    new_data, new_missing, _ = extract_booking_details(body, subject, customer_email)

    # If extraction failed (API/system error), skip silently — allow retry on next poll
    if new_data is None or (not new_data and new_missing and 'system issue' in ' '.join(new_missing).lower()):
        logger.error(f"Extraction error on clarification reply for thread {thread_id} — skipping to allow retry")
        return

    # Merge: original data takes precedence, new data fills in gaps
    merged_data = merge_booking_data(original_data, new_data)

    # Re-check what's still missing
    address_present = merged_data.get('address') or merged_data.get('suburb')

    still_missing = []
    if not merged_data.get('customer_name'):
        still_missing.append('Your full name')
    if not merged_data.get('customer_phone') and not customer_email:
        still_missing.append('Your phone number')
    if not address_present:
        still_missing.append('Your suburb or service address')
    if not merged_data.get('preferred_date'):
        still_missing.append('Your preferred date')

    if still_missing:
        # Before looping with another clarification, check if the customer is
        # actually requesting availability for a different week (e.g. "what about
        # next week?").  If so, re-send the availability table for that week and
        # do NOT increment the attempt counter.
        try:
            from ai_parser import is_availability_inquiry as _is_avail
            if _is_avail(subject, body):
                import re
                from datetime import date, timedelta
                from maps_handler import get_week_availability, get_job_duration_minutes
                from ai_parser import format_availability_response
                from email_utils import send_customer_email as _send_avail

                # Detect "next week", "following week", "week after", "further out",
                # "later date", "2 weeks", "fortnight", "in [month name]", etc.
                _next_week_re = re.compile(
                    r'\b(next|following)\s+week\b'
                    r'|\bweek\s+after\b'
                    r'|\bfortnight\b'
                    r'|\b\d+\s+weeks?\s+(away|out|time|later)\b'
                    r'|\bfurther\s+(out|ahead|away|date)\b'
                    r'|\blater\s+(date|time|in\s+the\s+(month|year))?\b'
                    r'|\banother\s+(week|time)\b'
                    r'|\b(january|february|march|april|may|june|july|august|september|october|november|december)\b',
                    re.I
                )
                wants_next_week = bool(_next_week_re.search(body))

                from_date_str = None
                if wants_next_week:
                    _today = date.today()
                    _days_ahead = (7 - _today.weekday()) % 7 or 7
                    from_date_str = (_today + timedelta(days=_days_ahead)).strftime('%Y-%m-%d')

                _duration = get_job_duration_minutes(merged_data)
                _availability = get_week_availability(_duration, from_date_str=from_date_str)
                _first_name = (merged_data.get('customer_name') or 'there').split()[0]
                # Exclude date-related items from the missing list shown in the table footer
                # since the customer will pick a date from the availability table itself.
                _non_date_missing = [
                    f for f in still_missing
                    if 'date' not in f.lower() and 'day' not in f.lower()
                ]
                _inner_html = format_availability_response(
                    _first_name, _availability,
                    missing_fields=_non_date_missing if _non_date_missing else None
                )
                _reply_subj = subject if subject.lower().startswith('re:') else f'Re: {subject}'
                _send_avail(service, customer_email, _reply_subj, _inner_html, thread_id=thread_id)
                logger.info(
                    f"Availability re-sent ({'next week' if wants_next_week else 'current week'}) "
                    f"to {customer_email} in clarification loop"
                )
                state.update_clarification_booking_data(existing_pending['id'], merged_data, still_missing)
                try:
                    label_pending_reply(service, msg_id)
                except Exception:
                    pass
                state.mark_email_processed(msg_id)
                return
        except Exception as _e:
            logger.warning(f"Availability re-send check failed in clarification loop: {_e}")

        # Check how many times we've already asked — bail out after 3 attempts
        attempts = state.increment_clarification_attempts(existing_pending['id'])
        if attempts >= 3:
            logger.warning(f"Clarification loop for thread {thread_id} exceeded 3 attempts — flagging for manual review")
            owner_email = os.environ.get('OWNER_EMAIL', '')
            if owner_email:
                try:
                    from google_auth import get_gmail_service as _gs
                    from email.mime.text import MIMEText
                    import base64
                    _svc = _gs()
                    _body = (
                        f"A customer ({customer_email}) has not provided complete booking details after "
                        f"{attempts} clarification emails.\n\nStill missing: {', '.join(still_missing)}\n\n"
                        f"Thread: {thread_id}\n\nPlease follow up manually."
                    )
                    _msg = MIMEText(_body)
                    _msg['to'] = owner_email
                    _msg['subject'] = f"[Manual Review] Incomplete booking from {customer_email}"
                    _raw = base64.urlsafe_b64encode(_msg.as_bytes()).decode()
                    _svc.users().messages().send(userId='me', body={'raw': _raw}).execute()
                    logger.info(f"Manual review email sent to owner for thread {thread_id}")
                except Exception as _e:
                    logger.error(f"Could not send manual review email: {_e}")
            state.mark_email_processed(msg_id)
            return
        # Still within attempt limit — send another clarification
        if get_flag('flag_auto_email_replies'):
            send_clarification_email(service, customer_email, subject, still_missing,
                                      thread_id=thread_id, message_id_header=message_id_header,
                                      booking_data=merged_data)
        else:
            logger.info(f"Auto email replies disabled — follow-up clarification not sent to {customer_email}")
        state.update_clarification_booking_data(existing_pending['id'], merged_data, still_missing)
        try:
            label_pending_reply(service, msg_id)
        except Exception:
            pass
        logger.info(f"Still missing fields for thread {thread_id}: {still_missing}")
    else:
        # All data collected — check the requested date is actually available before booking
        preferred_date = merged_data.get('preferred_date')
        if preferred_date and not _is_date_available(preferred_date, merged_data, state):
            first_name = (merged_data.get('customer_name') or 'there').split()[0]
            logger.info(f"Clarification complete but requested date {preferred_date} is full for {customer_email}")
            _send_date_full_email(
                service, customer_email, subject, preferred_date,
                first_name, merged_data, thread_id, state
            )
            # Reset the clarification so the customer can pick a new date
            state.update_clarification_booking_data(
                existing_pending['id'], merged_data, ['your preferred available day']
            )
            try:
                label_pending_reply(service, msg_id)
            except Exception:
                pass
            state.mark_email_processed(msg_id)
            return

        # Remove clarification record, create proper pending booking
        state.remove_pending_clarification(existing_pending['id'])
        _assign_best_slot(merged_data, state)
        pending_id = state.create_pending_booking(
            booking_data=merged_data,
            source='email',
            customer_email=customer_email,
            raw_message=body,
            msg_id=msg_id,
            thread_id=thread_id
        )
        send_owner_confirmation_request(pending_id, merged_data)
        try:
            label_awaiting_confirmation(service, msg_id)
        except Exception:
            pass
        logger.info(f"Clarification complete, owner confirmation sent for booking {pending_id}")

        # Mixed-intent: update draft with assigned slot and store metadata so the booking
        # can be auto-confirmed when the owner sends the draft, and the draft can be
        # refreshed if the owner reschedules via SMS before sending.
        if _mixed_draft_id:
            try:
                from email_utils import update_gmail_draft
                from ai_parser import draft_off_scope_reply as _dor
                _draft_meta = dict(merged_data)
                _draft_meta['draft_id'] = _mixed_draft_id
                _draft_meta['draft_question_body'] = _mixed_question_body or ''
                _draft_meta['draft_to_email'] = customer_email
                _draft_meta['draft_thread_id'] = thread_id
                _draft_meta['draft_subject'] = reply_subject
                state.update_pending_booking_data(pending_id, _draft_meta)
                refreshed_html = _dor(_mixed_question_body or '', first_name, [], _draft_meta)
                update_gmail_draft(service, _mixed_draft_id, customer_email, reply_subject,
                                   refreshed_html, thread_id=thread_id)
                logger.info(
                    f"Mixed-intent draft {_mixed_draft_id} refreshed with slot "
                    f"{merged_data.get('preferred_date')} {merged_data.get('preferred_time')} "
                    f"for booking {pending_id}"
                )
            except Exception as _dre:
                logger.error(f"Could not refresh mixed-intent draft for booking {pending_id}: {_dre}")


def send_clarification_email(service, to_email, original_subject, missing_fields,
                              thread_id=None, message_id_header=None, booking_data=None):
    from email_utils import send_customer_email, _p, _h2, _ul, _info_table, DARK

    name = 'there'
    try:
        if booking_data and booking_data.get('customer_name'):
            name = booking_data['customer_name'].split()[0]
    except Exception:
        pass

    # Build a summary of what was already captured
    captured_parts = []
    try:
        if booking_data:
            if booking_data.get('vehicle_make') and booking_data.get('vehicle_model'):
                vehicle_str = ' '.join(filter(None, [
                    booking_data.get('vehicle_year', ''),
                    booking_data['vehicle_make'],
                    booking_data['vehicle_model'],
                ])).strip()
                captured_parts.append(('Vehicle', vehicle_str))
            elif booking_data.get('vehicle_make'):
                captured_parts.append(('Vehicle', booking_data['vehicle_make']))
            location = booking_data.get('address') or booking_data.get('suburb')
            if location:
                captured_parts.append(('Location', location))
            if booking_data.get('preferred_date'):
                captured_parts.append(('Preferred date', booking_data['preferred_date']))
    except Exception:
        captured_parts = []

    captured_block = _info_table(captured_parts) if captured_parts else ''
    captured_intro = (
        '<p style="color:#1e293b;font-size:15px;line-height:1.65;margin:0 0 14px;">'
        'We\'ve noted the following details so far:</p>'
        + captured_block
    ) if captured_parts else ''

    subject = original_subject if original_subject.startswith('Re:') else f'Re: {original_subject}'

    content = (
        _p(f'Hi {name},')
        + _p('Thank you for getting in touch with Perth Swedish &amp; European Auto Centre!')
        + captured_intro
        + _h2('Just a Few More Details')
        + _p('To complete your booking we just need:')
        + _ul(missing_fields)
        + _p('Once we have this, we\'ll get your booking confirmed right away.')
        + f'<p style="margin:24px 0 0;color:{DARK};font-size:15px;">'
          f'Kind regards,<br><strong style="color:#C41230;">Rim Repair Team</strong></p>'
    )

    send_customer_email(service, to_email, subject, content,
                        thread_id=thread_id, message_id_header=message_id_header)
