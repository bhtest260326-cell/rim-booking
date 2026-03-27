import os
import base64
import logging
from datetime import datetime
from google_auth import get_gmail_service
from googleapiclient.errors import HttpError
from ai_parser import extract_booking_details, merge_booking_data
from state_manager import StateManager
from twilio_handler import send_owner_confirmation_request
from label_manager import initialise_labels, label_pending_reply, label_awaiting_confirmation, label_processed
from email.mime.text import MIMEText

from feature_flags import get_flag

logger = logging.getLogger(__name__)

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
        handle_clarification_reply(
            service, state, msg_id, thread_id,
            existing_pending, body, subject, customer_email,
            message_id_header=message_id_header
        )
    elif thread_id and state.thread_has_active_booking(thread_id):
        logger.info(f"Thread {thread_id} already has an active booking, skipping")
    else:
        handle_new_enquiry(
            service, state, msg_id, thread_id,
            body, subject, customer_email, message_id_header
        )

    state.mark_email_processed(msg_id)


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

        booking_data['preferred_date'] = found_date
        booking_data['preferred_time'] = found_time
        logger.info(f"Slot assigned: {found_date} {found_time} (preferred {preferred_dates}, original time {original_time})")
    except Exception as e:
        logger.warning(f"Slot computation skipped, keeping AI-extracted time: {e}")


def handle_new_enquiry(service, state, msg_id, thread_id, body, subject, customer_email, message_id_header=None):
    """Process a brand new booking enquiry."""
    booking_data, missing_fields, needs_clarification = extract_booking_details(
        body, subject, customer_email
    )

    if needs_clarification:
        if get_flag('flag_auto_email_replies'):
            send_clarification_email(service, customer_email, subject, missing_fields,
                                      thread_id=thread_id, message_id_header=message_id_header)
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
        _assign_best_slot(booking_data, state)
        pending_id = state.create_pending_booking(
            booking_data=booking_data,
            source='email',
            customer_email=customer_email,
            raw_message=body,
            msg_id=msg_id,
            thread_id=thread_id
        )
        send_owner_confirmation_request(pending_id, booking_data)
        try:
            label_awaiting_confirmation(service, msg_id)
        except Exception:
            pass
        logger.info(f"Owner confirmation sent for booking {pending_id}")


def handle_clarification_reply(service, state, msg_id, thread_id, existing_pending, body, subject, customer_email, message_id_header=None):
    """Customer replied with missing info — merge with existing partial booking."""
    original_data = existing_pending.get('booking_data', {})

    # Extract data from the reply only
    new_data, new_missing, _ = extract_booking_details(body, subject, customer_email)

    # Merge: original data takes precedence, new data fills in gaps
    merged_data = merge_booking_data(original_data, new_data)

    # Re-check what's still missing
    address_present = merged_data.get('address') or merged_data.get('suburb')
    service_present = merged_data.get('service_type') and merged_data.get('service_type') != 'unknown'

    still_missing = []
    if not merged_data.get('customer_name'):
        still_missing.append('your full name')
    if not address_present:
        still_missing.append('your service address')
    if not merged_data.get('preferred_date'):
        still_missing.append('your preferred date')
    if not service_present:
        still_missing.append('the type of service required (rim repair or paint touch-up)')

    if still_missing:
        # Still incomplete — ask again, keeping reply inside the same Gmail thread
        if get_flag('flag_auto_email_replies'):
            send_clarification_email(service, customer_email, subject, still_missing,
                                      thread_id=thread_id, message_id_header=message_id_header)
        else:
            logger.info(f"Auto email replies disabled — follow-up clarification not sent to {customer_email}")
        state.update_clarification_booking_data(existing_pending['id'], merged_data, still_missing)
        try:
            label_pending_reply(service, msg_id)
        except Exception:
            pass
        logger.info(f"Still missing fields for thread {thread_id}: {still_missing}")
    else:
        # All data collected — remove clarification record, create proper pending booking
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


def send_clarification_email(service, to_email, original_subject, missing_fields, thread_id=None, message_id_header=None):
    if len(missing_fields) == 1:
        fields_intro = "To complete your booking, we just need one more detail:"
    else:
        fields_intro = "To complete your booking, we just need a few more details:"

    fields_text = '\n'.join(f"  - {f}" for f in missing_fields)

    body = f"""Hi,

Thank you for getting in touch with Rim Repair.

{fields_intro}

{fields_text}

Once we have this information, we'll confirm your booking straight away.

If you have any questions in the meantime, please don't hesitate to reply to this email.

Kind regards,
Rim Repair Team"""

    if not original_subject.startswith('Re:'):
        subject = f"Re: {original_subject}"
    else:
        subject = original_subject

    message = MIMEText(body)
    message['to'] = to_email
    message['subject'] = subject

    if message_id_header:
        message['In-Reply-To'] = message_id_header
        message['References'] = message_id_header

    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    send_body = {'raw': raw}
    if thread_id:
        send_body['threadId'] = thread_id

    service.users().messages().send(userId='me', body=send_body).execute()
