import os
import base64
import logging
from google_auth import get_gmail_service
from googleapiclient.errors import HttpError
from ai_parser import extract_booking_details
from state_manager import StateManager
from twilio_handler import send_owner_confirmation_request
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)

PROCESSED_LABEL = "RimBookingProcessed"

def get_or_create_label(service, label_name):
    """Get or create a Gmail label for tracking processed emails."""
    try:
        labels = service.users().labels().list(userId='me').execute()
        for label in labels.get('labels', []):
            if label['name'] == label_name:
                return label['id']
        
        # Create label
        label = service.users().labels().create(
            userId='me',
            body={'name': label_name, 'labelListVisibility': 'labelHide', 'messageListVisibility': 'hide'}
        ).execute()
        return label['id']
    except Exception as e:
        logger.error(f"Label error: {e}")
        return None

def get_email_body(message):
    """Extract plain text body from Gmail message."""
    payload = message.get('payload', {})
    
    # Direct body
    body_data = payload.get('body', {}).get('data')
    if body_data:
        return base64.urlsafe_b64decode(body_data).decode('utf-8', errors='ignore')
    
    # Multipart
    for part in payload.get('parts', []):
        if part.get('mimeType') == 'text/plain':
            data = part.get('body', {}).get('data')
            if data:
                return base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')
        # Nested multipart
        for subpart in part.get('parts', []):
            if subpart.get('mimeType') == 'text/plain':
                data = subpart.get('body', {}).get('data')
                if data:
                    return base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')
    
    return ""

def get_email_headers(message):
    """Extract From, Subject headers."""
    headers = {}
    for h in message.get('payload', {}).get('headers', []):
        if h['name'] in ('From', 'Subject', 'Reply-To'):
            headers[h['name']] = h['value']
    return headers

def extract_email_address(from_header):
    """Extract raw email from 'Name <email>' format."""
    if '<' in from_header and '>' in from_header:
        return from_header.split('<')[1].split('>')[0].strip()
    return from_header.strip()

def poll_gmail():
    """Check Gmail for unprocessed customer booking emails."""
    try:
        service = get_gmail_service()
        state = StateManager()
        
        processed_label_id = get_or_create_label(service, PROCESSED_LABEL)
        
        # Search for unprocessed emails in inbox (exclude our own processed label, exclude sent)
        query = f'in:inbox -label:{PROCESSED_LABEL}'
        
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
            
            # Skip if already handled in state
            if state.is_email_processed(msg_id):
                # Apply label if not already done
                try:
                    service.users().messages().modify(
                        userId='me',
                        id=msg_id,
                        body={'addLabelIds': [processed_label_id]}
                    ).execute()
                except:
                    pass
                continue
            
            # Fetch full message
            message = service.users().messages().get(
                userId='me', id=msg_id, format='full'
            ).execute()
            
            headers = get_email_headers(message)
            from_header = headers.get('From', '')
            subject = headers.get('Subject', '(no subject)')
            customer_email = extract_email_address(from_header)
            body = get_email_body(message)
            
            # Skip emails from ourselves
            our_email = os.environ.get('GMAIL_ADDRESS', '')
            if our_email and customer_email.lower() == our_email.lower():
                state.mark_email_processed(msg_id)
                continue
            
            logger.info(f"Processing email from {customer_email}: {subject}")
            
            # Parse with AI
            booking_data, missing_fields, needs_clarification = extract_booking_details(
                body, subject, customer_email
            )
            
            if needs_clarification:
                # Auto-reply asking for missing info
                send_clarification_email(service, customer_email, subject, missing_fields)
                logger.info(f"Sent clarification request to {customer_email}")
            else:
                # Send to owner for confirmation
                pending_id = state.create_pending_booking(
                    booking_data=booking_data,
                    source='email',
                    customer_email=customer_email,
                    raw_message=body
                )
                send_owner_confirmation_request(pending_id, booking_data)
                logger.info(f"Sent owner confirmation request for booking {pending_id}")
            
            # Mark as processed
            state.mark_email_processed(msg_id)
            if processed_label_id:
                service.users().messages().modify(
                    userId='me',
                    id=msg_id,
                    body={'addLabelIds': [processed_label_id]}
                ).execute()
                
    except HttpError as e:
        logger.error(f"Gmail API error: {e}")
    except Exception as e:
        logger.error(f"Gmail poll error: {e}", exc_info=True)

def send_clarification_email(service, to_email, original_subject, missing_fields):
    """Send auto-reply requesting missing booking info."""
    fields_text = '\n'.join(f"- {f}" for f in missing_fields)
    
    body = f"""Hi,

Thanks for getting in touch with us about a rim repair booking.

To complete your booking, we just need a few more details:

{fields_text}

Please reply with this information and we'll get you booked in right away.

Thanks,
The Rim Repair Team"""

    subject = f"Re: {original_subject}" if not original_subject.startswith('Re:') else original_subject
    
    message = MIMEText(body)
    message['to'] = to_email
    message['subject'] = subject
    
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    
    service.users().messages().send(
        userId='me',
        body={'raw': raw}
    ).execute()
