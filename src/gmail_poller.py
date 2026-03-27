import os
import base64
import logging
from google_auth import get_gmail_service
from googleapiclient.errors import HttpError
from ai_parser import extract_booking_details
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

        # Initialise all labels on first run
        initialise_labels(service)

        query = 'in:inbox -label:Rim Repairs/Awaiting Confirmation -label:Rim Repairs/Pending Reply -label:Rim Repairs/Confirmed -label:Rim Repairs/Declined -label:Rim Repairs/Processed'

        results = service.users().messages().list(
            userId='me',
            q=query,
            maxResults=10
        ).execute()

        messages = results.get('messages', [])
        if not messages:
            return

        logger.info(f"Found {len(messages)} unprocessed emails")

        for msg_ref in messages:
            msg_id = msg_ref['id']

            if state.is_email_processed(msg_id):
                label_processed(service, msg_id)
                continue

            message = service.users().messages().get(userId='me', id=msg_id, format='full').execute()
            headers = get_email_headers(message)
            from_header = headers.get('From', '')
            subject = headers.get('Subject', '(no subject)')
            customer_email = extract_email_address(from_header)
            body = get_email_body(message)

            our_email = os.environ.get('GMAIL_ADDRESS', '')
            if our_email and customer_email.lower() == our_email.lower():
                state.mark_email_processed(msg_id)
                label_processed(service, msg_id)
                continue

            logger.info(f"Processing email from {customer_email}: {subject}")

            booking_data, missing_fields, needs_clarification = extract_booking_details(
                body, subject, customer_email
            )

            if needs_clarification:
                send_clarification_email(service, customer_email, subject, missing_fields)
                label_pending_reply(service, msg_id)
                logger.info(f"Sent clarification to {customer_email}, labelled Pending Reply")
            else:
                pending_id = state.create_pending_booking(
                    booking_data=booking_data,
                    source='email',
                    customer_email=customer_email,
                    raw_message=body,
                    msg_id=msg_id
                )
                send_owner_confirmation_request(pending_id, booking_data)
                label_awaiting_confirmation(service, msg_id)
                logger.info(f"Owner confirmation sent for {pending_id}, labelled Awaiting Confirmation")

            state.mark_email_processed(msg_id)

    except HttpError as e:
        logger.error(f"Gmail API error: {e}")
    except Exception as e:
        logger.error(f"Gmail poll error: {e}", exc_info=True)

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

    subject = f"Re: {original_subject}" if not original_subject.startswith('Re:') else original_subject

    message = MIMEText(body)
    message['to'] = to_email
    message['subject'] = subject

    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    service.users().messages().send(userId='me', body={'raw': raw}).execute()
