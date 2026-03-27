import os
import logging
from datetime import datetime, timedelta, timezone
from state_manager import StateManager
from twilio_handler import send_sms
from feature_flags import get_flag

logger = logging.getLogger(__name__)

GOOGLE_REVIEW_LINK = os.environ.get('GOOGLE_REVIEW_LINK', '')
PERTH_UTC_OFFSET = 8  # UTC+8

def _perth_now():
    """Return current datetime in Perth time (UTC+8)."""
    return datetime.utcnow() + timedelta(hours=PERTH_UTC_OFFSET)

def run_scheduled_tasks():
    """Run all scheduled tasks - call once per main loop iteration."""
    try:
        check_calendar_rsvps()
        send_morning_job_notifications()
        send_day_prior_reminders()
        send_post_job_review_requests()
    except Exception as e:
        logger.error(f"Scheduler error: {e}", exc_info=True)


def check_calendar_rsvps():
    """
    Poll pending bookings that were sent as calendar invites (fallback path).
    When the owner accepts or declines via Google Calendar, trigger the full
    confirm/decline workflow including customer notification.
    """
    owner_email = os.environ.get('OWNER_EMAIL', '')
    if not owner_email:
        return

    state = StateManager()
    pending = state.get_pending_bookings_with_calendar_events()
    if not pending:
        return

    from calendar_handler import get_event_attendee_status
    from twilio_handler import handle_owner_confirm, handle_owner_decline

    for booking in pending:
        booking_id = booking['id']
        event_id = booking.get('calendar_event_id')
        if not event_id:
            continue

        status = get_event_attendee_status(event_id, owner_email)
        if status == 'accepted':
            logger.info(f"Calendar RSVP accepted for booking {booking_id} — confirming")
            handle_owner_confirm(booking_id, booking)
        elif status == 'declined':
            logger.info(f"Calendar RSVP declined for booking {booking_id} — declining")
            handle_owner_decline(booking_id, booking)

def send_morning_job_notifications():
    """At 8am Perth time, email all customers booked for today."""
    now = _perth_now()
    # Only fire between 08:00 and 08:05 Perth time
    if not (now.hour == 8 and now.minute < 5):
        return

    state = StateManager()
    today = now.strftime('%Y-%m-%d')
    confirmed = state.get_confirmed_bookings()

    for booking_id, booking in confirmed.items():
        if booking.get('status') != 'confirmed':
            continue
        if state.has_reminder_been_sent(booking_id, 'morning_notification'):
            continue

        booking_data = booking.get('booking_data', {})
        if booking_data.get('preferred_date') != today:
            continue

        customer_email = booking.get('customer_email') or booking_data.get('customer_email')
        if not customer_email:
            state.mark_reminder_sent(booking_id, 'morning_notification')
            continue

        _send_morning_email(customer_email, booking_data)
        state.mark_reminder_sent(booking_id, 'morning_notification')
        logger.info(f"Morning notification sent for booking {booking_id}")

def _time_window(time_str):
    """Convert HH:MM to a friendly 2-hour window string, e.g. '10:00am – 12:00pm'."""
    try:
        start = datetime.strptime(time_str, "%H:%M")
        end = start + timedelta(hours=2)
        def fmt(dt):
            return dt.strftime("%-I:%M%p").lower().replace(':00', '')
        return f"{fmt(start)} – {fmt(end)}"
    except Exception:
        return time_str

def _send_morning_email(to_email, booking_data):
    """Send the day-of morning notification email to a customer."""
    try:
        from google_auth import get_gmail_service
        from email.mime.text import MIMEText
        import base64

        service = get_gmail_service()

        name = booking_data.get('customer_name', 'there')
        time_str = booking_data.get('preferred_time') or '09:00'
        window = _time_window(time_str)
        address = booking_data.get('address') or booking_data.get('suburb', 'your location')
        vehicle = ' '.join(filter(None, [
            booking_data.get('vehicle_colour'),
            booking_data.get('vehicle_make'),
            booking_data.get('vehicle_model')
        ])) or 'your vehicle'

        body = f"""Hi {name},

We hope you're having a great start to your day!

Just a friendly heads-up — your rim repair technician will be visiting you today at {address} between {window}.

To make sure we can get started straight away, could you please ensure:

  - There is sufficient clear working space around {vehicle}
  - The vehicle is accessible and ideally parked in a flat, open area
  - You or someone authorised is available to approve the work and process payment by EFTPOS on the day

If anything has changed or you need to reach us before the visit, simply reply to this email.

We're looking forward to seeing you today!

Kind regards,
Rim Repair Team"""

        message = MIMEText(body)
        message['to'] = to_email
        message['subject'] = "Your Rim Repair Technician is Visiting Today"

        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        service.users().messages().send(userId='me', body={'raw': raw}).execute()
        logger.info(f"Morning notification email sent to {to_email}")
    except Exception as e:
        logger.error(f"Morning notification email error: {e}")

def send_day_prior_reminders():
    """Send reminder SMS to customers the day before their booking."""
    if not get_flag('flag_day_prior_reminders'):
        return
    state = StateManager()
    confirmed = state.get_confirmed_bookings()

    tomorrow = (_perth_now() + timedelta(days=1)).strftime('%Y-%m-%d')

    for booking_id, booking in confirmed.items():
        if booking.get('status') != 'confirmed':
            continue
        if state.has_reminder_been_sent(booking_id, 'day_prior'):
            continue

        booking_data = booking.get('booking_data', {})
        booking_date = booking_data.get('preferred_date')

        if booking_date != tomorrow:
            continue

        customer_phone = booking_data.get('customer_phone')
        if not customer_phone:
            logger.info(f"No phone for booking {booking_id}, skipping day-prior reminder")
            state.mark_reminder_sent(booking_id, 'day_prior')
            continue

        time_str = booking_data.get('preferred_time', 'the scheduled time')
        name = booking_data.get('customer_name', 'there')
        address = booking_data.get('address') or booking_data.get('suburb', 'your location')

        msg = (
            f"Hi {name}, just a reminder that your rim repair is booked for tomorrow "
            f"at {time_str} at {address}. "
            f"Payment by EFTPOS on the day. "
            f"Any changes, please reply to this message. - Rim Repair Team"
        )

        send_sms(customer_phone, msg)
        state.mark_reminder_sent(booking_id, 'day_prior')
        logger.info(f"Day-prior reminder sent for booking {booking_id}")

def send_post_job_review_requests():
    """Send Google review request SMS ~2 hours after job end time."""
    if not get_flag('flag_post_job_reviews'):
        return
    state = StateManager()
    confirmed = state.get_confirmed_bookings()

    now = _perth_now()
    today = now.strftime('%Y-%m-%d')

    for booking_id, booking in confirmed.items():
        if booking.get('status') != 'confirmed':
            continue
        if state.has_reminder_been_sent(booking_id, 'review_request'):
            continue

        booking_data = booking.get('booking_data', {})
        booking_date = booking_data.get('preferred_date')

        if booking_date != today:
            continue

        time_str = booking_data.get('preferred_time', '09:00')
        try:
            job_start = datetime.strptime(f"{booking_date} {time_str}", "%Y-%m-%d %H:%M")
            review_send_time = job_start + timedelta(hours=3)
            if now < review_send_time:
                continue
        except Exception:
            continue

        customer_phone = booking_data.get('customer_phone')
        if not customer_phone:
            state.mark_reminder_sent(booking_id, 'review_request')
            continue

        name = booking_data.get('customer_name', 'there')

        if GOOGLE_REVIEW_LINK:
            msg = (
                f"Hi {name}, thanks for choosing Rim Repair Team today! "
                f"We hope you're happy with the result. "
                f"If you have a moment, a Google review would mean a lot to us: {GOOGLE_REVIEW_LINK} "
                f"- Rim Repair Team"
            )
        else:
            msg = (
                f"Hi {name}, thanks for choosing Rim Repair Team today! "
                f"We hope you're happy with the result. "
                f"Feel free to refer us to anyone who needs rim repairs. - Rim Repair Team"
            )

        send_sms(customer_phone, msg)
        state.mark_reminder_sent(booking_id, 'review_request')
        logger.info(f"Review request sent for booking {booking_id}")
