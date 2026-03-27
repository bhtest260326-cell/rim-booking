import os
import base64
import logging
from google_auth import get_gmail_service
from googleapiclient.errors import HttpError
from ai_parser import extract_booking_details, merge_booking_data
from state_manager import StateManager
from twilio_handler import send_owner_confirmation_request
from label_manager import initialise_labels, label_pending_reply, label_awaiting_confirmation, label_processed
from email.mime.text import MIMEText

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
        if h['name'] in ('From', 'Subject', 'Reply-To'):
            headers[h['name']] = h['value']
    return headers

def extract_email_address(from_header):
    if '<' in from_header and '>' in from_header:
        return from_header.split('<')[1].split('>')[0].strip()
    return from_header.strip()

def poll_gmail():
    try:
        service = get_gmail_service()
        state = StateManager()

        try:
            initialise_labels(service)
        except Exception:
            pass

        results = service.users().messages().list(
            userId='me',
            q='in:inbox',
            maxResults=20
        ).execute()

        messages = results.get('messages', [])
        if not messages:
            return

        logger.info(f"Checking {len(messages)} inbox messages")

        for msg_ref in messages:
            msg_id = msg_ref['id']

            if state.is_email_processed(msg_id):
                continue

            message = service.users().messages().get(userId='me', id=msg_id, format='full').execute()
            headers = get_email_headers(message)
            from_header = headers.get('From', '')
            subject = headers.get('Subject', '(no subject)')
            customer_email = extract_email_address(from_header)
            body = get_email_body(message)
            thread_id = message.get('threadId')

            our_email = os.environ.get('GMAIL_ADDRESS', '')
            if our_email and customer_email.lower() == our_email.lower():
                state.mark_email_processed(msg_id)
                continue

            logger.info(f"Processing email from {customer_email}: {subject} (thread: {thread_id})")

            # Check if this thread already has a pending clarification booking
            existing_pending = state.get_pending_booking_by_thread(thread_id) if thread_id else None

            if existing_pending:
                handle_clarification_reply(
                    service, state, msg_id, thread_id,
                    existing_pending, body, subject, customer_email
                )
            else:
                handle_new_enquiry(
                    service, state, msg_id, thread_id,
                    body, subject, customer_email
                )

            state.mark_email_processed(msg_id)

    except HttpError as e:
        logger.error(f"Gmail API error: {e}")
    except Exception as e:
        logger.error(f"Gmail poll error: {e}", exc_info=True)


def handle_new_enquiry(service, state, msg_id, thread_id, body, subject, customer_email):
    """Process a brand new booking enquiry."""
    booking_data, missing_fields, needs_clarification = extract_booking_details(
        body, subject, customer_email
    )

    if needs_clarification:
        send_clarification_email(service, customer_email, subject, missing_fields)
        # Store partial booking data with thread_id so reply can merge into it
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


def handle_clarification_reply(service, state, msg_id, thread_id, existing_pending, body, subject, customer_email):
    """Customer replied with missing info — merge with existing partial booking."""
    original_data = existing_pending.get('booking_data', {})

    # Extract data from the reply only
    new_data, new_missing, _ = extract_booking_details(body, subject, customer_email)

    # Merge: original data takes precedence, new data fills in gaps
    merged_data = merge_booking_data(original_data, new_data)

    # Re-check what's still missing
    required = ['customer_name', 'preferred_date']
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
        # Still incomplete — ask again, reply in same thread
        send_clarification_email(service, customer_email, subject, still_missing)
        state.update_clarification_booking_data(existing_pending['id'], merged_data, still_missing)
        try:
            label_pending_reply(service, msg_id)
        except Exception:
            pass
        logger.info(f"Still missing fields for thread {thread_id}: {still_missing}")
    else:
        # All data collected — remove clarification record, create proper pending booking
        state.remove_pending_clarification(existing_pending['id'])
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


def send_clarification_email(service, to_email, original_subject, missing_fields):
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

    # Keep subject as Re: to stay in same thread
    if not original_subject.startswith('Re:'):
        subject = f"Re: {original_subject}"
    else:
        subject = original_subject

    message = MIMEText(body)
    message['to'] = to_email
    message['subject'] = subject

    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    service.users().messages().send(userId='me', body={'raw': raw}).execute()
