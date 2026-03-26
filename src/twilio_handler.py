import os
import logging
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException
from ai_parser import format_booking_for_owner, parse_owner_correction
from state_manager import StateManager
from calendar_handler import create_calendar_event
from google_auth import get_gmail_service
from email.mime.text import MIMEText
import base64

logger = logging.getLogger(__name__)

def get_twilio_client():
    return Client(os.environ['TWILIO_ACCOUNT_SID'], os.environ['TWILIO_AUTH_TOKEN'])

def send_sms(to, body):
    """Send an SMS via Twilio."""
    try:
        client = get_twilio_client()
        message = client.messages.create(
            body=body,
            from_=os.environ['TWILIO_FROM_NUMBER'],
            to=to
        )
        logger.info(f"SMS sent to {to}: SID {message.sid}")
        return message.sid
    except TwilioRestException as e:
        logger.error(f"Twilio error sending to {to}: {e}")
        return None

def send_owner_confirmation_request(pending_id, booking_data):
    """Send booking details to owner for YES/NO confirmation."""
    from ai_parser import format_booking_for_owner
    
    msg = format_booking_for_owner(booking_data)
    msg += f"\n\n[ID:{pending_id}]"
    
    send_sms(os.environ['OWNER_MOBILE'], msg)

def poll_sms_replies():
    """Check Twilio for incoming SMS replies from owner."""
    try:
        client = get_twilio_client()
        state = StateManager()
        
        # Fetch recent inbound messages to our number
        messages = client.messages.list(
            to=os.environ['TWILIO_FROM_NUMBER'],
            limit=20
        )
        
        for msg in messages:
            if msg.direction != 'inbound':
                continue
            
            if state.is_sms_processed(msg.sid):
                continue
            
            # Only process replies from owner
            if msg.from_ != os.environ['OWNER_MOBILE']:
                state.mark_sms_processed(msg.sid)
                continue
            
            body = msg.body.strip()
            logger.info(f"Owner SMS received: {body}")
            
            # Extract booking ID if present
            pending_id = None
            if '[ID:' in body:
                try:
                    pending_id = body.split('[ID:')[1].split(']')[0].strip()
                    body_clean = body.split('[ID:')[0].strip()
                except:
                    body_clean = body
            else:
                body_clean = body
                # Fall back to most recent pending booking
                latest = state.get_latest_pending_booking()
                if latest:
                    pending_id = latest['id']
            
            if not pending_id:
                logger.warning("Owner SMS received but no pending booking found")
                state.mark_sms_processed(msg.sid)
                continue
            
            pending = state.get_pending_booking(pending_id)
            if not pending:
                logger.warning(f"No pending booking found for ID {pending_id}")
                state.mark_sms_processed(msg.sid)
                continue
            
            upper = body_clean.upper().strip()
            
            if upper == 'YES':
                handle_owner_confirm(pending_id, pending)
            elif upper == 'NO':
                handle_owner_decline(pending_id, pending)
            else:
                # Treat as a correction
                handle_owner_correction(pending_id, pending, body_clean)
            
            state.mark_sms_processed(msg.sid)
            
    except Exception as e:
        logger.error(f"SMS poll error: {e}", exc_info=True)

def handle_owner_confirm(pending_id, pending):
    """Owner confirmed - create calendar event, notify customer."""
    state = StateManager()
    booking_data = pending['booking_data']
    
    # Create Google Calendar event
    event_id = create_calendar_event(booking_data)
    
    # Confirm in state
    state.confirm_booking(pending_id, booking_data)
    
    if event_id:
        state.update_booking_calendar_event(pending_id, event_id)
    
    # Notify customer
    customer_phone = booking_data.get('customer_phone')
    customer_email = pending.get('customer_email') or booking_data.get('customer_email')
    
    confirmation_msg = build_customer_confirmation(booking_data)
    
    if customer_phone:
        send_sms(customer_phone, confirmation_msg)
    
    if customer_email:
        send_confirmation_email(customer_email, booking_data, confirmation_msg)
    
    # Confirm to owner
    send_sms(
        os.environ['OWNER_MOBILE'],
        f"✓ Booking {pending_id} confirmed. Calendar event created. Customer notified."
    )
    
    logger.info(f"Booking {pending_id} fully confirmed and customer notified")

def handle_owner_decline(pending_id, pending):
    """Owner declined - notify customer."""
    state = StateManager()
    booking_data = pending['booking_data']
    
    state.decline_booking(pending_id)
    
    customer_phone = booking_data.get('customer_phone')
    customer_email = pending.get('customer_email') or booking_data.get('customer_email')
    
    decline_msg = (
        "Hi, thanks for your enquiry about a rim repair. "
        "Unfortunately we're unable to accommodate your requested time. "
        "Please reply to discuss alternative times. Thanks, Rim Repair Team"
    )
    
    if customer_phone:
        send_sms(customer_phone, decline_msg)
    
    if customer_email:
        send_decline_email(customer_email, booking_data, decline_msg)
    
    send_sms(os.environ['OWNER_MOBILE'], f"Booking {pending_id} declined. Customer notified.")
    logger.info(f"Booking {pending_id} declined")

def handle_owner_correction(pending_id, pending, correction_text):
    """Owner sent a correction - update booking and re-confirm."""
    state = StateManager()
    original = pending['booking_data']
    
    updated_booking = parse_owner_correction(original, correction_text)
    
    # Update pending state
    s = state._read_state()
    if pending_id in s['pending_bookings']:
        s['pending_bookings'][pending_id]['booking_data'] = updated_booking
        state._write_state(s)
    
    # Re-send confirmation request with updated details
    from ai_parser import format_booking_for_owner
    msg = f"Updated booking details:\n\n{format_booking_for_owner(updated_booking)}\n\n[ID:{pending_id}]"
    send_sms(os.environ['OWNER_MOBILE'], msg)
    
    logger.info(f"Booking {pending_id} updated with correction, re-sent for confirmation")

def build_customer_confirmation(booking_data):
    """Build confirmation SMS for customer."""
    date = booking_data.get('preferred_date', 'TBC')
    time = booking_data.get('preferred_time', 'TBC')
    address = booking_data.get('address') or booking_data.get('suburb', 'your location')
    service = booking_data.get('service_type', 'rim repair').replace('_', ' ')
    
    return (
        f"Hi {booking_data.get('customer_name', 'there')}! "
        f"Your rim repair booking is confirmed for {date} at {time} "
        f"at {address}. "
        f"Our technician will come to you. Payment by EFTPOS on the day. "
        f"Any questions, just reply to this message. - Rim Repair Team"
    )

def send_confirmation_email(to_email, booking_data, sms_text):
    """Send booking confirmation via email."""
    try:
        service = get_gmail_service()
        
        subject = "Your Rim Repair Booking Confirmation"
        body = f"""{sms_text}

---
This is an automated confirmation from Rim Repair Team.
"""
        
        message = MIMEText(body)
        message['to'] = to_email
        message['subject'] = subject
        
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        service.users().messages().send(userId='me', body={'raw': raw}).execute()
        logger.info(f"Confirmation email sent to {to_email}")
    except Exception as e:
        logger.error(f"Email send error: {e}")

def send_decline_email(to_email, booking_data, msg):
    """Send decline notification via email."""
    try:
        service = get_gmail_service()
        
        message = MIMEText(msg)
        message['to'] = to_email
        message['subject'] = "Re: Your Rim Repair Enquiry"
        
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        service.users().messages().send(userId='me', body={'raw': raw}).execute()
    except Exception as e:
        logger.error(f"Decline email send error: {e}")
