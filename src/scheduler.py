import os
import logging
from datetime import datetime, timedelta, timezone
from state_manager import StateManager
from twilio_handler import send_sms
from feature_flags import get_flag

logger = logging.getLogger(__name__)

GOOGLE_REVIEW_LINK = os.environ.get('GOOGLE_REVIEW_LINK', '')

def run_scheduled_tasks():
    """Run all scheduled tasks - call once per main loop iteration."""
    try:
        send_day_prior_reminders()
        send_post_job_review_requests()
    except Exception as e:
        logger.error(f"Scheduler error: {e}", exc_info=True)

def send_day_prior_reminders():
    """Send reminder SMS to customers the day before their booking."""
    if not get_flag('flag_day_prior_reminders'):
        return
    state = StateManager()
    confirmed = state.get_confirmed_bookings()
    
    tomorrow = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
    
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
    
    now = datetime.now()
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
        
        # Check if job end time has passed (start + 1hr + 2hr buffer = 3hrs after start)
        time_str = booking_data.get('preferred_time', '09:00')
        try:
            job_start = datetime.strptime(f"{booking_date} {time_str}", "%Y-%m-%d %H:%M")
            review_send_time = job_start + timedelta(hours=3)
            
            if now < review_send_time:
                continue
        except:
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
