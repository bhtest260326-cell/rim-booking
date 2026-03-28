import os
import re
import logging
from datetime import datetime
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException
from ai_parser import format_booking_for_owner, parse_owner_correction
from state_manager import StateManager
from calendar_handler import create_calendar_event, create_tentative_calendar_invite, confirm_tentative_event, delete_calendar_event
from google_auth import get_gmail_service
from label_manager import label_confirmed, label_declined
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import base64

from feature_flags import get_flag

logger = logging.getLogger(__name__)

def _fmt_date(date_str):
    """Format 'YYYY-MM-DD' as 'Monday, 31 March 2026'. Returns original string on failure."""
    try:
        dt = datetime.strptime(date_str, '%Y-%m-%d')
        return dt.strftime('%A, %d %B %Y').replace(' 0', ' ')
    except Exception:
        return date_str


def get_twilio_client():
    return Client(os.environ['TWILIO_ACCOUNT_SID'], os.environ['TWILIO_AUTH_TOKEN'])

def normalise_phone(number):
    if not number:
        return number
    digits = re.sub(r'[^\d+]', '', number)
    if digits.startswith('+'):
        return digits
    if digits.startswith('61') and len(digits) == 11:
        return f'+{digits}'
    if digits.startswith('0') and len(digits) == 10:
        return f'+61{digits[1:]}'
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
        if e.code == 63038 or getattr(e, 'status', None) == 429:
            logger.warning(f"Twilio daily SMS limit reached (429) — SMS to {to} not sent. Will retry next day.")
        else:
            logger.error(f"Twilio error sending to {to}: {e}")
        return None

def send_owner_confirmation_request(pending_id, booking_data):
    if not get_flag('flag_auto_sms_owner'):
        logger.info(f"Auto SMS to owner disabled — skipping confirmation request for {pending_id}")
        _send_calendar_invite_fallback(pending_id, booking_data, reason="SMS disabled")
        return
    msg = format_booking_for_owner(booking_data)
    msg += f"\n\n[ID:{pending_id}]"
    result = send_sms(os.environ['OWNER_MOBILE'], msg)
    if result is None:
        logger.warning(f"Owner SMS failed for booking {pending_id} — triggering calendar invite fallback")
        _send_calendar_invite_fallback(pending_id, booking_data, reason="SMS delivery failed")


def _send_calendar_invite_fallback(pending_id, booking_data, reason="SMS unavailable"):
    """
    Fallback when owner SMS cannot be sent.
    Creates a Google Calendar event with OWNER_EMAIL as attendee — Google sends
    a native accept/decline/amend invite email. RSVP is detected by the scheduler.
    """
    state = StateManager()
    owner_email = os.environ.get('OWNER_EMAIL', '')
    if not owner_email:
        logger.warning(f"OWNER_EMAIL not set — cannot send calendar invite fallback for {pending_id}")
        return

    event_id = create_tentative_calendar_invite(booking_data, pending_id)
    if event_id:
        state.update_booking_calendar_event(pending_id, event_id)
        logger.info(f"Calendar invite sent to {owner_email} for booking {pending_id} (event {event_id})")
    else:
        logger.error(f"Could not create calendar invite for booking {pending_id}")

def _handle_customer_sms(from_number, body_text, message_sid, state):
    """Handle an inbound SMS from a customer (not the owner).

    Looks up the customer by phone number in confirmed bookings.
    If found, forwards the message to the owner with booking context.
    Sends a brief auto-acknowledgement to the customer.
    """
    if not get_flag('flag_auto_sms_customer'):
        return  # only respond if customer SMS feature is enabled

    try:
        from state_manager import _get_conn
        import json

        normalised = normalise_phone(from_number)

        # Search confirmed and pending bookings for this phone number
        matched_booking_id = None
        matched_name = None
        matched_date = None

        with _get_conn() as conn:
            rows = conn.execute(
                "SELECT id, booking_data, status FROM bookings WHERE status IN ('confirmed', 'awaiting_owner') ORDER BY created_at DESC LIMIT 50"
            ).fetchall()

        for row in rows:
            try:
                bd = json.loads(row['booking_data'])
                stored_phone = normalise_phone(bd.get('customer_phone', '') or '')
                if stored_phone and stored_phone == normalised:
                    matched_booking_id = row['id']
                    matched_name = bd.get('customer_name', 'Customer')
                    matched_date = bd.get('preferred_date', '')
                    matched_status = row['status']
                    break
            except Exception:
                pass

        if matched_booking_id:
            # Forward to owner with context
            owner_msg = (
                f"📱 Customer SMS — {matched_name} (booking {matched_booking_id}, {matched_date}):\n"
                f"\"{body_text[:160]}\""
            )
            send_sms(os.environ['OWNER_MOBILE'], owner_msg)

            # Auto-acknowledge to customer
            ack_msg = (
                f"Hi {matched_name}, thanks for your message — we've received it and will be in touch shortly. "
                f"- Rim Repair Team"
            )
            send_sms(from_number, ack_msg)

            # Log the event
            try:
                state.log_booking_event(matched_booking_id, 'customer_sms_received', actor='customer',
                    details={'message_snippet': body_text[:200], 'from': normalised})
            except Exception:
                pass

            logger.info(f"Customer SMS from {normalised} forwarded to owner (booking {matched_booking_id})")
        else:
            # Unknown sender — just log, don't respond
            logger.info(f"SMS from unknown number {normalised} — not in any active booking")

    except Exception as e:
        logger.error(f"Customer SMS handling error: {e}", exc_info=True)


def process_single_sms_webhook(from_number, body_text, message_sid):
    state = StateManager()
    if state.is_sms_processed(message_sid):
        return
    owner_mobile = normalise_phone(os.environ.get('OWNER_MOBILE', ''))
    if normalise_phone(from_number) != owner_mobile:
        # This is NOT from the owner — check if it's from a known customer
        _handle_customer_sms(from_number, body_text, message_sid, state)
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
            # Only use fallback if booking was created within the last 2 hours
            created_at = latest.get('created_at', '')
            try:
                from datetime import timezone
                age = datetime.now(timezone.utc) - datetime.fromisoformat(created_at)
                if age.total_seconds() < 7200:
                    pending_id = latest['id']
                else:
                    logger.warning(f"Latest pending booking {latest['id']} is too old for ID-less SMS fallback ({int(age.total_seconds()//3600)}h old)")
            except Exception:
                pending_id = latest['id']  # fallback if date parse fails
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
    elif upper.startswith('CANCEL DATE '):
        # Format: CANCEL DATE YYYY-MM-DD <reason>
        rest = body_clean[len('CANCEL DATE '):].strip()
        parts = rest.split(None, 1)  # split on first whitespace
        if parts:
            cancel_date = parts[0].strip()
            cancel_reason = parts[1].strip() if len(parts) > 1 else 'unforeseen circumstances'
            # Validate date format
            try:
                from datetime import datetime as _dv
                _dv.strptime(cancel_date, '%Y-%m-%d')
                handle_owner_day_cancellation(cancel_date, cancel_reason)
            except ValueError:
                try:
                    send_sms(os.environ['OWNER_MOBILE'],
                        f"Invalid date format. Use: CANCEL DATE YYYY-MM-DD reason")
                except Exception as e:
                    logger.error(f"Could not send format error reply: {e}")
        else:
            try:
                send_sms(os.environ['OWNER_MOBILE'],
                    "Usage: CANCEL DATE YYYY-MM-DD reason (e.g. CANCEL DATE 2026-04-15 sick day)")
            except Exception as e:
                logger.error(f"Could not send usage error reply: {e}")
    else:
        handle_owner_correction(pending_id, pending, body_clean)
    state.mark_sms_processed(message_sid)

def poll_sms_replies():
    try:
        client = get_twilio_client()
        state = StateManager()
        messages = client.messages.list(to=os.environ['TWILIO_FROM_NUMBER'], limit=20)
        owner_mobile = normalise_phone(os.environ.get('OWNER_MOBILE', ''))
        for msg in messages:
            if msg.direction != 'inbound':
                continue
            if state.is_sms_processed(msg.sid):
                continue
            if normalise_phone(msg.from_) != owner_mobile:
                # This is NOT from the owner — check if it's from a known customer
                _handle_customer_sms(msg.from_, msg.body, msg.sid, state)
                state.mark_sms_processed(msg.sid)
                continue
            body = msg.body.strip()
            logger.info(f"Owner SMS received: {body}")
            pending_id = None
            if '[ID:' in body:
                try:
                    pending_id = body.split('[ID:')[1].split(']')[0].strip()
                    body_clean = body.split('[ID:')[0].strip()
                except (ValueError, IndexError):
                    body_clean = body
            else:
                body_clean = body
                latest = state.get_latest_pending_booking()
                if latest:
                    # Only use fallback if booking was created within the last 2 hours
                    created_at = latest.get('created_at', '')
                    try:
                        from datetime import timezone
                        age = datetime.now(timezone.utc) - datetime.fromisoformat(created_at)
                        if age.total_seconds() < 7200:
                            pending_id = latest['id']
                        else:
                            logger.warning(f"Latest pending booking {latest['id']} is too old for ID-less SMS fallback ({int(age.total_seconds()//3600)}h old)")
                    except Exception:
                        pending_id = latest['id']  # fallback if date parse fails
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
            elif upper.startswith('CANCEL DATE '):
                rest = body_clean[len('CANCEL DATE '):].strip()
                parts = rest.split(None, 1)
                if parts:
                    cancel_date = parts[0].strip()
                    cancel_reason = parts[1].strip() if len(parts) > 1 else 'unforeseen circumstances'
                    try:
                        from datetime import datetime as _dv
                        _dv.strptime(cancel_date, '%Y-%m-%d')
                        handle_owner_day_cancellation(cancel_date, cancel_reason)
                    except ValueError:
                        try:
                            send_sms(os.environ['OWNER_MOBILE'],
                                "Invalid date format. Use: CANCEL DATE YYYY-MM-DD reason")
                        except Exception as e:
                            logger.error(f"Could not send format error reply: {e}")
            else:
                handle_owner_correction(pending_id, pending, body_clean)
            state.mark_sms_processed(msg.sid)
    except Exception as e:
        logger.error(f"SMS poll error: {e}", exc_info=True)

def handle_owner_confirm(pending_id, pending):
    state = StateManager()
    booking_data = pending['booking_data']
    # Idempotency guard — if already confirmed, skip silently
    if pending.get('status') == 'confirmed':
        logger.info(f"Booking {pending_id} already confirmed — ignoring duplicate YES")
        return
    # Confirm in DB first — atomic BEGIN IMMEDIATE prevents race conditions.
    # Only proceed to calendar/notifications if DB actually recorded the change.
    confirmed = state.confirm_booking(pending_id, booking_data)
    if not confirmed:
        logger.error(f"confirm_booking returned False for {pending_id} — aborting confirmation (already processed or DB error)")
        try:
            send_sms(os.environ['OWNER_MOBILE'],
                f"Booking {pending_id} could not be confirmed (already processed or DB error). Check /admin.")
        except Exception:
            pass
        return
    # DB confirm succeeded — now handle calendar (failure is non-fatal)
    existing_event_id = pending.get('calendar_event_id')
    event_id = None
    if existing_event_id:
        try:
            confirm_tentative_event(existing_event_id, booking_data)
            event_id = existing_event_id
        except Exception as e:
            logger.error(f"Could not upgrade tentative calendar event {existing_event_id}: {e}")
    else:
        try:
            event_id = create_calendar_event(booking_data)
        except Exception as e:
            logger.error(f"Could not create calendar event for {pending_id}: {e}")
    if event_id:
        state.update_booking_calendar_event(pending_id, event_id)
    customer_phone = booking_data.get('customer_phone')
    customer_email = pending.get('customer_email') or booking_data.get('customer_email')
    confirmation_msg = build_customer_confirmation_sms(booking_data)
    if customer_phone and get_flag('flag_auto_sms_customer'):
        send_sms(customer_phone, confirmation_msg)
    if customer_email and get_flag('flag_auto_email_customer'):
        send_confirmation_email(customer_email, booking_data, booking_id=pending_id)
    gmail_msg_id = pending.get('gmail_msg_id')
    if gmail_msg_id:
        try:
            gmail = get_gmail_service()
            label_confirmed(gmail, gmail_msg_id)
        except Exception as e:
            logger.error(f"Label update error on confirm: {e}")
    try:
        send_sms(os.environ['OWNER_MOBILE'], f"Booking {pending_id} confirmed. Calendar event created. Customer notified.")
    except Exception as e:
        logger.error(f"Could not send owner confirm ACK for {pending_id}: {e}")
    logger.info(f"Booking {pending_id} fully confirmed")

    # Record service history for future maintenance reminders
    try:
        state.record_completed_service(pending_id, booking_data)
    except Exception as e:
        logger.warning(f"Could not record service history for {pending_id}: {e}")

    # Sync to Google Sheets
    if get_flag('flag_google_sheets_sync'):
        try:
            from google_sheets import append_booking_row
            # Re-fetch the booking after confirm so confirmed_at is populated
            confirmed = state.get_confirmed_bookings()
            confirmed_booking = confirmed.get(pending_id, {})
            if not confirmed_booking:
                # Fallback: build from what we have
                confirmed_booking = dict(pending)
                confirmed_booking['status'] = 'confirmed'
            append_booking_row(pending_id, confirmed_booking)
        except Exception as e:
            logger.error(f"Google Sheets sync error for booking {pending_id}: {e}")

    try:
        state.log_booking_event(pending_id, 'confirmed', actor='owner_sms',
            details={'customer_notified_sms': bool(customer_phone and get_flag('flag_auto_sms_customer')),
                     'customer_notified_email': bool(customer_email and get_flag('flag_auto_email_customer'))})
    except Exception:
        pass

def handle_owner_decline(pending_id, pending):
    state = StateManager()
    booking_data = pending['booking_data']
    # Remove any tentative calendar event created via fallback
    existing_event_id = pending.get('calendar_event_id')
    if existing_event_id:
        delete_calendar_event(existing_event_id)
    state.decline_booking(pending_id)
    customer_phone = booking_data.get('customer_phone')
    customer_email = pending.get('customer_email') or booking_data.get('customer_email')
    if customer_phone and get_flag('flag_auto_sms_customer'):
        send_sms(customer_phone,
            f"Hi {booking_data.get('customer_name', 'there')}, thank you for getting in touch with Rim Repair. "
            f"Unfortunately, we're unable to accommodate your requested time. "
            f"Please reply and we'll do our best to find a suitable time for you.")
    if customer_email and get_flag('flag_auto_email_customer'):
        send_decline_email(customer_email, booking_data)
    gmail_msg_id = pending.get('gmail_msg_id')
    if gmail_msg_id:
        try:
            gmail = get_gmail_service()
            label_declined(gmail, gmail_msg_id)
        except Exception as e:
            logger.error(f"Label update error on decline: {e}")
    try:
        send_sms(os.environ['OWNER_MOBILE'], f"Booking {pending_id} declined. Customer notified.")
    except Exception as e:
        logger.error(f"Could not send owner decline ACK for {pending_id}: {e}")

    try:
        state.log_booking_event(pending_id, 'declined', actor='owner_sms',
            details={'customer_notified': bool(customer_phone or customer_email)})
    except Exception:
        pass

def handle_owner_day_cancellation(date_str: str, reason: str) -> None:
    """Cancel all confirmed bookings for a date and notify customers to rebook.

    Triggered by owner SMS: CANCEL DATE 2026-04-15 sick
    """
    from state_manager import StateManager
    import json as _json
    from feature_flags import get_flag

    state = StateManager()
    cancelled = state.cancel_all_bookings_for_date(date_str, reason, 'owner_sms')

    if not cancelled:
        send_sms(os.environ['OWNER_MOBILE'], f"No confirmed bookings found for {_fmt_date(date_str)}.")
        return

    auto_notify = get_flag('flag_day_cancellation_auto_notify')
    notified = 0
    for b in cancelled:
        try:
            bd = _json.loads(b['booking_data']) if isinstance(b['booking_data'], str) else b['booking_data']
        except Exception:
            bd = {}
        customer_name = (bd.get('customer_name') or 'there').split()[0]
        customer_phone = bd.get('customer_phone')
        customer_email = b.get('customer_email') or bd.get('customer_email')

        # Delete calendar event if one exists
        event_id = b.get('calendar_event_id')
        if event_id:
            try:
                from calendar_handler import delete_calendar_event
                delete_calendar_event(event_id)
            except Exception as e:
                logger.warning(f"Could not delete calendar event {event_id}: {e}")

        if not auto_notify:
            continue

        # SMS customer
        if customer_phone and get_flag('flag_auto_sms_customer'):
            try:
                msg = (
                    f"Hi {customer_name}, unfortunately we need to cancel your Rim Repair "
                    f"appointment on {_fmt_date(date_str)} due to {reason}. We sincerely apologise. "
                    f"Please reply or email us to rebook at your convenience. - Rim Repair Team"
                )
                send_sms(customer_phone, msg)
                notified += 1
            except Exception as e:
                logger.error(f"Could not SMS customer for cancelled booking {b['id']}: {e}")

        # Email customer
        if customer_email and get_flag('flag_auto_email_replies'):
            try:
                from google_auth import get_gmail_service
                from email_utils import send_customer_email, _p, _h2, DARK, RED
                service = get_gmail_service()
                content = (
                    _p(f'Hi {customer_name},')
                    + _p(f'We regret to inform you that your Rim Repair appointment on '
                         f'<strong>{_fmt_date(date_str)}</strong> has been cancelled due to {reason}.')
                    + _p('We sincerely apologise for the inconvenience. '
                         'Please reply to this email or call us and we\'ll get you rebooked as soon as possible.')
                    + _p('We\'ll do our best to prioritise your rebooking.')
                    + f'<p style="margin:24px 0 0;color:{DARK};font-size:15px;">'
                    f'Kind regards,<br><strong style="color:{RED};">Rim Repair Team</strong></p>'
                )
                send_customer_email(service, customer_email,
                    f'Appointment Cancelled — {_fmt_date(date_str)}', content)
            except Exception as e:
                logger.error(f"Could not email customer for cancelled booking {b['id']}: {e}")

    try:
        send_sms(
            os.environ['OWNER_MOBILE'],
            f"Day cancellation complete: {len(cancelled)} booking(s) cancelled for {date_str}. "
            f"{notified} customer(s) notified via SMS. - Rim Repair System"
        )
    except Exception as e:
        logger.error(f"Could not send day cancellation summary to owner: {e}")
    logger.info(f"Day cancellation: {len(cancelled)} bookings cancelled for {date_str} (reason: {reason})")


def _extract_date_from_correction(text):
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
    state.update_pending_booking_data(pending_id, updated_booking)
    msg = f"Updated booking:\n\n{format_booking_for_owner(updated_booking)}\n\n[ID:{pending_id}]"
    try:
        send_sms(os.environ['OWNER_MOBILE'], msg)
    except Exception as e:
        logger.error(f"Could not send updated booking to owner for {pending_id}: {e}")
    logger.info(f"Booking {pending_id} updated with correction, re-sent for confirmation")

    try:
        state.log_booking_event(pending_id, 'data_updated', actor='owner_sms',
            details={'correction_text': correction_text[:200]})
    except Exception:
        pass

def build_customer_confirmation_sms(booking_data):
    date = _fmt_date(booking_data.get('preferred_date', 'TBC'))
    address = booking_data.get('address') or booking_data.get('suburb', 'your location')
    return (
        f"Hi {booking_data.get('customer_name', 'there')}, your Rim Repair booking is confirmed for "
        f"{date} at {address}. Our technician will come to you — you'll receive a reminder on the morning of your appointment with your time window. "
        f"Payment is by EFTPOS on the day. Any questions, just reply. - Rim Repair"
    )

def send_confirmation_email(to_email, booking_data, booking_id=None):
    try:
        from email_utils import send_customer_email, _h2, _p, _info_table, _ul, RED, DARK, esc
        service = get_gmail_service()
        name = booking_data.get('customer_name', 'there')
        first = esc(name.split()[0]) if name and name != 'there' else 'there'
        date = _fmt_date(booking_data.get('preferred_date', 'TBC'))
        address = esc(booking_data.get('address') or booking_data.get('suburb', 'your location'))
        vehicle = esc(' '.join(filter(None, [
            booking_data.get('vehicle_year'),
            booking_data.get('vehicle_colour'),
            booking_data.get('vehicle_make'),
            booking_data.get('vehicle_model'),
        ])) or 'your vehicle')
        service_type = booking_data.get('service_type', 'rim repair').replace('_', ' ').title()
        num_rims = booking_data.get('num_rims')
        if num_rims:
            service_type += f' \u00d7{num_rims} rims'

        info_rows = [
            ('Date', date),
            ('Address', address),
            ('Vehicle', vehicle),
            ('Service', service_type),
        ]

        # Generate reschedule link
        try:
            from email_utils import generate_reschedule_token
            base_url = os.environ.get('APP_BASE_URL', '').rstrip('/')
            if base_url and booking_id:
                reschedule_token = generate_reschedule_token(booking_id)
                reschedule_url = f"{base_url}/reschedule/{reschedule_token}"
                reschedule_para = _p(
                    f'Need to reschedule? <a href="{reschedule_url}" style="color:#C41230;">Click here</a> '
                    f'to choose a new date — no need to email us.',
                    f'color:{DARK};'
                )
            else:
                reschedule_para = ''
        except Exception:
            reschedule_para = ''

        content = (
            _p(f'Hi {first},')
            + _p('Thank you for choosing Perth Swedish &amp; European Auto Centre. '
                 'We\'re pleased to confirm your booking — the details are below.')
            + _h2('Booking Confirmation')
            + _info_table(info_rows)
            + _p('Our technician will come directly to you at the address provided. '
                 'You\'ll receive a reminder on the morning of your appointment with your specific arrival window.')
            + _p('If you need to make any changes or have questions before your appointment, '
                 'simply reply to this email.')
            + _p(f'We look forward to seeing you on <strong>{date}</strong>.',
                 f'color:{DARK};')
            + reschedule_para
            + f'<p style="margin:24px 0 0;color:{DARK};font-size:15px;">'
              f'Kind regards,<br><strong style="color:#C41230;">Rim Repair Team</strong></p>'
        )

        send_customer_email(service, to_email, 'Booking Confirmed — Perth Swedish & European Auto Centre', content)
        logger.info(f"Confirmation email sent to {to_email}")
    except Exception as e:
        logger.error(f"Email send error: {e}")

def send_decline_email(to_email, booking_data):
    try:
        from email_utils import send_customer_email, _p, _h2, DARK, esc
        service = get_gmail_service()
        name = booking_data.get('customer_name', 'there')
        first = esc(name.split()[0]) if name and name != 'there' else 'there'

        content = (
            _p(f'Hi {first},')
            + _p('Thank you for reaching out to Perth Swedish &amp; European Auto Centre.')
            + _p('Unfortunately we\'re unable to accommodate your requested time slot. '
                 'We\'d love to find a time that works for you — please reply to this email '
                 'with your availability and we\'ll do our best to get you booked in as soon as possible.')
            + _p('We apologise for any inconvenience and look forward to hearing from you.')
            + f'<p style="margin:24px 0 0;color:{DARK};font-size:15px;">'
              f'Kind regards,<br><strong style="color:#C41230;">Rim Repair Team</strong></p>'
        )

        send_customer_email(service, to_email, 'Re: Your Rim Repair Enquiry', content)
    except Exception as e:
        logger.error(f"Decline email send error: {e}")


def send_reschedule_change_email(to_email, booking_data, booking_id, old_date):
    """Send a 'Booking Change Confirmed' email after a customer self-service reschedule.

    Includes a fresh reschedule link so the customer can amend again if needed.
    """
    try:
        from email_utils import send_customer_email, generate_reschedule_token, _h2, _p, _info_table, RED, DARK
        from html import escape as esc
        service = get_gmail_service()

        name = booking_data.get('customer_name', 'there')
        first = esc(name.split()[0]) if name and name != 'there' else 'there'

        new_date_fmt = _fmt_date(booking_data.get('preferred_date', 'TBC'))
        old_date_fmt = _fmt_date(old_date) if old_date and old_date != 'Unknown' else old_date

        address = esc(booking_data.get('address') or booking_data.get('suburb', 'your location'))
        vehicle = esc(' '.join(filter(None, [
            booking_data.get('vehicle_year'),
            booking_data.get('vehicle_colour'),
            booking_data.get('vehicle_make'),
            booking_data.get('vehicle_model'),
        ])) or 'your vehicle')
        service_type = booking_data.get('service_type', 'rim repair').replace('_', ' ').title()
        num_rims = booking_data.get('num_rims')
        if num_rims:
            service_type += f' \u00d7{num_rims} rims'

        info_rows = [
            ('New Date', new_date_fmt),
            ('Address', address),
            ('Vehicle', vehicle),
            ('Service', service_type),
        ]

        # Generate a fresh reschedule link for further amendments
        reschedule_para = ''
        try:
            base_url = os.environ.get('APP_BASE_URL', '').rstrip('/')
            if base_url and booking_id:
                reschedule_token = generate_reschedule_token(booking_id)
                reschedule_url = f"{base_url}/reschedule/{reschedule_token}"
                reschedule_para = _p(
                    f'Need to change this again? <a href="{reschedule_url}" style="color:{RED};">Click here</a> '
                    f'to pick a different date — no need to email us.',
                    f'color:{DARK};'
                )
        except Exception:
            pass

        content = (
            _p(f'Hi {first},')
            + _p(
                f'Your booking has been successfully moved to <strong>{new_date_fmt}</strong>.'
                + (f' (Previously: {old_date_fmt}.)' if old_date_fmt and old_date_fmt != 'Unknown' else '')
            )
            + _h2('Updated Booking Details')
            + _info_table(info_rows)
            + _p('Our technician will come directly to you at the address provided. '
                 'You\'ll receive a reminder on the morning of your appointment with your specific arrival window.')
            + reschedule_para
            + _p('If you have any questions, simply reply to this email.')
            + f'<p style="margin:24px 0 0;color:{DARK};font-size:15px;">'
              f'Kind regards,<br><strong style="color:{RED};">Rim Repair Team</strong></p>'
        )

        send_customer_email(
            service, to_email,
            f'Booking Change Confirmed — Perth Swedish & European Auto Centre',
            content,
        )
        logger.info(f"Reschedule change email sent to {to_email} (booking {booking_id})")
    except Exception as e:
        logger.error(f"Reschedule change email send error: {e}")
