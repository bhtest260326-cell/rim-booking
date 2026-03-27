import os
import re
import logging
from datetime import datetime
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException
from ai_parser import format_booking_for_owner, parse_owner_correction
from state_manager import StateManager
from calendar_handler import create_calendar_event
from google_auth import get_gmail_service
from label_manager import label_confirmed, label_declined
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import base64

logger = logging.getLogger(__name__)

def get_twilio_client():
    return Client(os.environ['TWILIO_ACCOUNT_SID'], os.environ['TWILIO_AUTH_TOKEN'])

def normalise_phone(number):
    """Convert an Australian phone number to E.164 format (+61XXXXXXXXX).

    Handles formats like: 0452 728 291, 0452728291, +61452728291, 61452728291.
    Returns the original string unchanged if it doesn't look like an AU mobile/landline.
    """
    if not number:
        return number
    # Strip everything except digits and leading +
    digits = re.sub(r'[^\d+]', '', number)
    # Already E.164
    if digits.startswith('+'):
        return digits
    # Strip country code prefix without +
    if digits.startswith('61') and len(digits) == 11:
        return f'+{digits}'
    # Local format: 04XXXXXXXX or 02/03/07/08 XXXXXXXX
    if digits.startswith('0') and len(digits) == 10:
        return f'+61{digits[1:]}'
    # Return as-is — Twilio will surface the error if still invalid
    return number


def send_sms(to, body):
    try:
        to = normalise_phone(to)
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
    msg = format_booking_for_owner(booking_data)
    msg += f"\n\n[ID:{pending_id}]"
    send_sms(os.environ['OWNER_MOBILE'], msg)

def process_single_sms_webhook(from_number, body_text, message_sid):
    """Process one inbound SMS delivered via Twilio webhook (replaces polling for that message)."""
    state = StateManager()

    if state.is_sms_processed(message_sid):
        return

    owner_mobile = normalise_phone(os.environ.get('OWNER_MOBILE', ''))
    if normalise_phone(from_number) != owner_mobile:
        state.mark_sms_processed(message_sid)
        return

    body = body_text.strip()
    logger.info(f"Owner SMS (webhook): {body}")

    pending_id = None
    if '[ID:' in body:
        try:
            pending_id = body.split('[ID:')[1].split(']')[0].strip()
            body_clean = body.split('[ID:')[0].strip()
        except Exception:
            body_clean = body
    else:
        body_clean = body
        latest = state.get_latest_pending_booking()
        if latest:
            pending_id = latest['id']

    if not pending_id:
        logger.warning("Owner webhook SMS received but no pending booking found")
        state.mark_sms_processed(message_sid)
        return

    pending = state.get_pending_booking(pending_id)
    if not pending:
        logger.warning(f"No pending booking for ID {pending_id}")
        state.mark_sms_processed(message_sid)
        return

    upper = body_clean.upper().strip()
    if upper == 'YES':
        handle_owner_confirm(pending_id, pending)
    elif upper == 'NO':
        handle_owner_decline(pending_id, pending)
    else:
        handle_owner_correction(pending_id, pending, body_clean)

    state.mark_sms_processed(message_sid)


def poll_sms_replies():
    try:
        client = get_twilio_client()
        state = StateManager()

        messages = client.messages.list(
            to=os.environ['TWILIO_FROM_NUMBER'],
            limit=20
        )

        for msg in messages:
            if msg.direction != 'inbound':
                continue
            if state.is_sms_processed(msg.sid):
                continue
            if msg.from_ != os.environ['OWNER_MOBILE']:
                state.mark_sms_processed(msg.sid)
                continue

            body = msg.body.strip()
            logger.info(f"Owner SMS received: {body}")

            pending_id = None
            if '[ID:' in body:
                try:
                    pending_id = body.split('[ID:')[1].split(']')[0].strip()
                    body_clean = body.split('[ID:')[0].strip()
                except:
                    body_clean = body
            else:
                body_clean = body
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
                handle_owner_correction(pending_id, pending, body_clean)

            state.mark_sms_processed(msg.sid)

    except Exception as e:
        logger.error(f"SMS poll error: {e}", exc_info=True)

def handle_owner_confirm(pending_id, pending):
    state = StateManager()
    booking_data = pending['booking_data']

    event_id = create_calendar_event(booking_data)
    state.confirm_booking(pending_id, booking_data)
    if event_id:
        state.update_booking_calendar_event(pending_id, event_id)

    customer_phone = booking_data.get('customer_phone')
    customer_email = pending.get('customer_email') or booking_data.get('customer_email')

    confirmation_msg = build_customer_confirmation_sms(booking_data)

    if customer_phone:
        send_sms(customer_phone, confirmation_msg)
    if customer_email:
        send_confirmation_email(customer_email, booking_data)

    # Update Gmail label to Confirmed
    gmail_msg_id = pending.get('gmail_msg_id')
    if gmail_msg_id:
        try:
            gmail = get_gmail_service()
            label_confirmed(gmail, gmail_msg_id)
        except Exception as e:
            logger.error(f"Label update error on confirm: {e}")

    send_sms(os.environ['OWNER_MOBILE'], f"Booking {pending_id} confirmed. Calendar event created. Customer notified.")
    logger.info(f"Booking {pending_id} fully confirmed")

def handle_owner_decline(pending_id, pending):
    state = StateManager()
    booking_data = pending['booking_data']
    state.decline_booking(pending_id)

    customer_phone = booking_data.get('customer_phone')
    customer_email = pending.get('customer_email') or booking_data.get('customer_email')

    if customer_phone:
        send_sms(customer_phone,
            f"Hi {booking_data.get('customer_name', 'there')}, thank you for getting in touch with Rim Repair. "
            f"Unfortunately we're unable to accommodate your requested time. "
            f"Please reply and we'll find a suitable time for you.")

    if customer_email:
        send_decline_email(customer_email, booking_data)

    # Update Gmail label to Declined
    gmail_msg_id = pending.get('gmail_msg_id')
    if gmail_msg_id:
        try:
            gmail = get_gmail_service()
            label_declined(gmail, gmail_msg_id)
        except Exception as e:
            logger.error(f"Label update error on decline: {e}")

    send_sms(os.environ['OWNER_MOBILE'], f"Booking {pending_id} declined. Customer notified.")

def _extract_date_from_correction(text):
    """Parse a DD/MM date from a correction message. Returns YYYY-MM-DD or None."""
    match = re.search(r'\b(\d{1,2})/(\d{1,2})\b', text)
    if match:
        day, month = int(match.group(1)), int(match.group(2))
        year = datetime.now().year
        try:
            d = datetime(year, month, day)
            if d.date() < datetime.now().date():
                d = datetime(year + 1, month, day)
            return d.strftime('%Y-%m-%d')
        except ValueError:
            pass
    return None


def handle_owner_correction(pending_id, pending, correction_text):
    state = StateManager()
    original = pending['booking_data']

    # If the owner is asking to find a free slot, compute one using Maps travel time
    slot_hint = None
    lower = correction_text.lower()
    if any(kw in lower for kw in ['find', 'slot', 'free', 'available', 'schedule']):
        try:
            from maps_handler import find_next_available_slot
            target_date = (
                _extract_date_from_correction(correction_text)
                or original.get('preferred_date')
                or datetime.now().strftime('%Y-%m-%d')
            )
            job_address = original.get('address') or original.get('suburb') or ''
            day_bookings = state.get_confirmed_bookings_for_date(target_date)
            found_date, found_time = find_next_available_slot(
                target_date, job_address, day_bookings, new_booking_data=original
            )
            slot_hint = f"{found_date} at {found_time}"
            logger.info(f"Maps slot computed for correction: {slot_hint}")
        except Exception as e:
            logger.warning(f"Slot computation failed: {e}")

    updated_booking = parse_owner_correction(original, correction_text, slot_hint=slot_hint)

    s = state._read_state()
    if pending_id in s['pending_bookings']:
        s['pending_bookings'][pending_id]['booking_data'] = updated_booking
        state._write_state(s)

    msg = f"Updated booking:\n\n{format_booking_for_owner(updated_booking)}\n\n[ID:{pending_id}]"
    send_sms(os.environ['OWNER_MOBILE'], msg)
    logger.info(f"Booking {pending_id} updated with correction, re-sent for confirmation")

def build_customer_confirmation_sms(booking_data):
    date = booking_data.get('preferred_date', 'TBC')
    time = booking_data.get('preferred_time', 'TBC')
    address = booking_data.get('address') or booking_data.get('suburb', 'your location')
    return (
        f"Hi {booking_data.get('customer_name', 'there')}, your rim repair booking is confirmed for "
        f"{date} at {time} at {address}. Our technician will come to you — payment by EFTPOS on the day. "
        f"Any questions, just reply. - Rim Repair"
    )

def send_confirmation_email(to_email, booking_data):
    try:
        service = get_gmail_service()

        name = booking_data.get('customer_name', 'there')
        date = booking_data.get('preferred_date', 'TBC')
        time = booking_data.get('preferred_time', 'TBC')
        address = booking_data.get('address') or booking_data.get('suburb', 'your location')
        vehicle = ' '.join(filter(None, [
            booking_data.get('vehicle_colour'),
            booking_data.get('vehicle_make'),
            booking_data.get('vehicle_model')
        ])) or 'your vehicle'
        service_type = booking_data.get('service_type', 'rim repair').replace('_', ' ')

        body = f"""Hi {name},

Thank you for choosing Rim Repair. We're pleased to confirm your booking — the details are outlined below.

Booking Confirmation
--------------------
Date:     {date}
Time:     {time}
Address:  {address}
Vehicle:  {vehicle}
Service:  {service_type.title()}

Our technician will come directly to you at the address provided. Payment is by EFTPOS on the day of the appointment.

If you need to make any changes or have any questions prior to your appointment, please don't hesitate to reply to this email.

We look forward to seeing you.

Kind regards,
Rim Repair Team"""

        message = MIMEText(body)
        message['to'] = to_email
        message['subject'] = "Booking Confirmation — Rim Repair"

        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        service.users().messages().send(userId='me', body={'raw': raw}).execute()
        logger.info(f"Confirmation email sent to {to_email}")
    except Exception as e:
        logger.error(f"Email send error: {e}")

def send_decline_email(to_email, booking_data):
    try:
        service = get_gmail_service()

        name = booking_data.get('customer_name', 'there')

        body = f"""Hi {name},

Thank you for reaching out to Rim Repair.

Unfortunately we're unable to accommodate your requested time. We'd love to find a time that works for you — please reply to this email with your availability and we'll do our best to get you booked in as soon as possible.

We apologise for any inconvenience and look forward to hearing from you.

Kind regards,
Rim Repair Team"""

        message = MIMEText(body)
        message['to'] = to_email
        message['subject'] = "Re: Your Rim Repair Enquiry"

        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        service.users().messages().send(userId='me', body={'raw': raw}).execute()
    except Exception as e:
        logger.error(f"Decline email send error: {e}")
