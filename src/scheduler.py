import os
import time as _time
import logging
from datetime import datetime, timedelta, timezone
from state_manager import StateManager, DB_PATH

try:
    from zoneinfo import ZoneInfo
    _PERTH_TZ = ZoneInfo('Australia/Perth')
except ImportError:
    from datetime import timezone, timedelta
    _PERTH_TZ = timezone(timedelta(hours=8))

from twilio_handler import send_sms
from feature_flags import get_flag

logger = logging.getLogger(__name__)


def _fmt_date(date_str):
    """Format 'YYYY-MM-DD' as 'Monday, 31 March 2026'. Returns original string on failure."""
    try:
        dt = datetime.strptime(date_str, '%Y-%m-%d')
        return dt.strftime('%A, %d %B %Y').replace(' 0', ' ')
    except Exception as e:
        logger.warning('Could not format date %r: %s', date_str, e)
        return date_str


GOOGLE_REVIEW_LINK = os.environ.get('GOOGLE_REVIEW_LINK', '')
PERTH_UTC_OFFSET = 8  # UTC+8

_last_route_opt = 0.0
_ROUTE_OPT_INTERVAL = 300  # 5 minutes

# Task intervals in seconds
_TASK_INTERVALS = {
    'optimize_daily_routes':        300,   # every 5 min
    'check_calendar_rsvps':         120,   # every 2 min
    'send_morning_job_notifications': 300,  # every 5 min (idempotent)
    'send_day_prior_reminders':     600,   # every 10 min
    'send_post_job_review_requests': 600,  # every 10 min
    'send_maintenance_reminders':   3600,  # every hour
    'check_dlq_for_escalation':     1800,  # every 30 min
    'send_preflight_schedule_report': 300, # every 5 min (idempotent via date key)
    'send_owner_daily_briefing':    300,   # every 5 min (idempotent via date key)
    'check_pending_booking_expiry': 600,   # every 10 min
    'backup_database_to_email':     86400, # daily (also gated by date key)
    'backup_database_to_drive':     86400, # daily (also gated by hour)
    'run_db_cleanup':               604800, # weekly (7 days)
    'check_waitlist_opportunities': 3600,  # every hour
    'drain_message_queue':          60,    # every minute (Upgrade 5)
    'run_daily_health_check':       300,   # every 5 min (idempotent via date key, Upgrade 10)
}

_KNOWN_TASKS = frozenset(_TASK_INTERVALS.keys())
_task_last_run: dict = {k: 0.0 for k in _KNOWN_TASKS}

def _should_run(task_name: str) -> bool:
    """Return True if enough time has elapsed since this task last ran."""
    if task_name not in _KNOWN_TASKS:
        logger.warning('_should_run called with unknown task name %r — skipping', task_name)
        return False
    interval = _TASK_INTERVALS.get(task_name, 60)
    last = _task_last_run.get(task_name, 0)
    return (_time.monotonic() - last) >= interval

def _mark_ran(task_name: str) -> None:
    if task_name not in _KNOWN_TASKS:
        logger.warning('_mark_ran called with unknown task name %r — ignoring', task_name)
        return
    _task_last_run[task_name] = _time.monotonic()

def _perth_now():
    """Return current naive datetime in Perth local time (UTC+8, no DST)."""
    from datetime import timezone as _tz
    return datetime.now(_tz.utc).astimezone(_PERTH_TZ).replace(tzinfo=None)

def run_scheduled_tasks():
    """Run all scheduled tasks - call once per main loop iteration."""
    if _should_run('check_dlq_for_escalation'):
        try:
            check_dlq_for_escalation()
        except Exception as e:
            logger.error(f"check_dlq_for_escalation error: {e}", exc_info=True)
        _mark_ran('check_dlq_for_escalation')

    if _should_run('check_calendar_rsvps'):
        try:
            check_calendar_rsvps()
        except Exception as e:
            logger.error(f"check_calendar_rsvps error: {e}", exc_info=True)
        _mark_ran('check_calendar_rsvps')

    if _should_run('send_preflight_schedule_report'):
        try:
            send_preflight_schedule_report()
        except Exception as e:
            logger.error(f"send_preflight_schedule_report error: {e}", exc_info=True)
        _mark_ran('send_preflight_schedule_report')

    if _should_run('send_morning_job_notifications'):
        try:
            send_morning_job_notifications()
        except Exception as e:
            logger.error(f"send_morning_job_notifications error: {e}", exc_info=True)
        _mark_ran('send_morning_job_notifications')

    if _should_run('send_day_prior_reminders'):
        try:
            send_day_prior_reminders()
        except Exception as e:
            logger.error(f"send_day_prior_reminders error: {e}", exc_info=True)
        _mark_ran('send_day_prior_reminders')

    if _should_run('send_post_job_review_requests'):
        try:
            send_post_job_review_requests()
        except Exception as e:
            logger.error(f"send_post_job_review_requests error: {e}", exc_info=True)
        _mark_ran('send_post_job_review_requests')

    if _should_run('optimize_daily_routes'):
        try:
            optimize_daily_routes()
        except Exception as e:
            logger.error(f"optimize_daily_routes error: {e}", exc_info=True)
        _mark_ran('optimize_daily_routes')

    if _should_run('check_pending_booking_expiry'):
        try:
            check_pending_booking_expiry()
        except Exception as e:
            logger.error(f"check_pending_booking_expiry error: {e}", exc_info=True)
        _mark_ran('check_pending_booking_expiry')

    if _should_run('send_owner_daily_briefing'):
        try:
            send_owner_daily_briefing()
        except Exception as e:
            logger.error(f"send_owner_daily_briefing error: {e}", exc_info=True)
        _mark_ran('send_owner_daily_briefing')

    if _should_run('send_maintenance_reminders'):
        try:
            send_maintenance_reminders()
        except Exception as e:
            logger.error(f"send_maintenance_reminders error: {e}", exc_info=True)
        _mark_ran('send_maintenance_reminders')

    if _should_run('backup_database_to_email'):
        try:
            backup_database_to_email()
        except Exception as e:
            logger.error(f"backup_database_to_email error: {e}", exc_info=True)
        _mark_ran('backup_database_to_email')

    if _should_run('backup_database_to_drive'):
        try:
            now = _perth_now()
            if now.hour == 3:  # 3am Perth time — after email backup at 2am
                from backup_handler import backup_database_to_drive
                result = backup_database_to_drive()
                if result.get('ok'):
                    logger.info("Drive backup completed: %s bytes, %s backups retained",
                               result.get('size_bytes'), result.get('backups_retained'))
                else:
                    logger.warning("Drive backup failed: %s", result.get('error'))
        except Exception as e:
            logger.error("backup_database_to_drive error: %s", e, exc_info=True)
        _mark_ran('backup_database_to_drive')

    if _should_run('run_db_cleanup'):
        try:
            run_db_cleanup()
        except Exception as e:
            logger.error(f"run_db_cleanup error: {e}", exc_info=True)
        _mark_ran('run_db_cleanup')

    if _should_run('check_waitlist_opportunities'):
        try:
            check_waitlist_opportunities()
        except Exception as e:
            logger.error(f"check_waitlist_opportunities error: {e}", exc_info=True)
        _mark_ran('check_waitlist_opportunities')

    if _should_run('drain_message_queue'):
        try:
            from message_queue import drain_queue
            sent = drain_queue()
            if sent:
                logger.info("Message queue: %d message(s) sent", sent)
        except Exception as e:
            logger.error(f"drain_message_queue error: {e}", exc_info=True)
        _mark_ran('drain_message_queue')

    if _should_run('run_daily_health_check'):
        try:
            from health_monitor import run_daily_health_check
            run_daily_health_check()
        except Exception as e:
            logger.error(f"run_daily_health_check error: {e}", exc_info=True)
        _mark_ran('run_daily_health_check')


def _alert_owner_overrun(date_str, overrun_jobs):
    """Send an SMS to the owner when the optimised schedule for a day exceeds 5pm.

    Deduplicates: only sends once per calendar date. Subsequent 5-minute optimiser
    runs for the same overrun are silently skipped until the next day.
    """
    owner_phone = os.environ.get('OWNER_MOBILE', '')
    if not owner_phone:
        return

    # Cooldown: skip if we already alerted for this date today
    try:
        state = StateManager()
        cooldown_key = f'overrun_alert_sent_{date_str}'
        if state.get_app_state(cooldown_key):
            return  # already alerted for this date
    except Exception as e:
        logger.warning('Overrun alert cooldown state check failed: %s — proceeding to send', e)

    names = ', '.join(
        bd.get('customer_name') or bid
        for bid, bd in overrun_jobs
    )
    last_bid, last_bd = overrun_jobs[-1]
    last_time = last_bd.get('preferred_time', '?')
    msg = (
        f"SCHEDULE OVERRUN on {date_str}: {len(overrun_jobs)} job(s) "
        f"({names}) — last job starts {last_time}, may finish after 5pm. "
        f"Please review and reschedule. - Wheel Doctor System"
    )
    try:
        result = send_sms(owner_phone, msg)
        if result:
            logger.warning(f"Owner alerted: schedule overrun on {date_str}")
            try:
                state.set_app_state(cooldown_key, _perth_now().isoformat())
            except Exception as e:
                logger.warning('Could not persist overrun alert cooldown key: %s', e)
        else:
            logger.warning(f"Overrun SMS to owner failed (send_sms returned None) — cooldown not set, will retry")
    except Exception as e:
        logger.error(f"Could not send overrun alert: {e}")


def optimize_daily_routes():
    """Every 5 minutes: reorder each day's confirmed bookings for optimal Maps route.

    Fetches a full NxN distance matrix in one API call per day, solves TSP, then
    updates SQLite and Google Calendar for any bookings whose times changed.
    Only reorders bookings within the same day — never moves them between days.
    Route always departs from and returns to the business address.
    For single-job days, validates the job fits within business hours and alerts
    the owner if the schedule overruns 5pm.
    """
    global _last_route_opt
    now_ts = _time.time()
    if now_ts - _last_route_opt < _ROUTE_OPT_INTERVAL:
        return
    _last_route_opt = now_ts

    try:
        from maps_handler import find_optimal_route, get_job_duration_minutes, BUSINESS_START_HOUR, BUSINESS_END_HOUR, get_travel_minutes, BUSINESS_ADDRESS, _ceil_15
        from calendar_handler import update_calendar_event_time

        state = StateManager()
        today = _perth_now().strftime('%Y-%m-%d')
        confirmed = state.get_confirmed_bookings()

        # Group confirmed bookings by date (today + future only)
        by_date = {}
        for bid, booking in confirmed.items():
            if booking.get('status') != 'confirmed':
                continue
            bd = booking.get('booking_data', {})
            date = bd.get('preferred_date', '')
            if not date or date < today:
                continue
            by_date.setdefault(date, []).append((bid, bd, booking))

        for date_str, day_jobs in sorted(by_date.items()):
            target_date = datetime.strptime(date_str, '%Y-%m-%d')
            day_start = target_date.replace(hour=BUSINESS_START_HOUR, minute=0, second=0, microsecond=0)
            day_end = target_date.replace(hour=BUSINESS_END_HOUR, minute=0, second=0, microsecond=0)
            booking_lookup = {bid: booking for bid, _, booking in day_jobs}

            if len(day_jobs) == 1:
                # Single-job day: ensure the job starts from business hours, not a customer-requested time
                bid, bd, booking = day_jobs[0]
                duration = get_job_duration_minutes(bd)
                address = bd.get('address') or bd.get('suburb') or BUSINESS_ADDRESS
                travel = get_travel_minutes(BUSINESS_ADDRESS, address)
                correct_start = _ceil_15(day_start + timedelta(minutes=travel))
                correct_end = correct_start + timedelta(minutes=duration)

                current_time = bd.get('preferred_time', '')
                new_time = correct_start.strftime('%H:%M')

                if current_time != new_time:
                    new_bd = dict(bd)
                    new_bd['preferred_time'] = new_time
                    state.update_confirmed_booking_data(bid, new_bd)
                    event_id = booking.get('calendar_event_id')
                    if event_id:
                        try:
                            update_calendar_event_time(event_id, correct_start, duration)
                        except Exception as e:
                            logger.error(f"Calendar update failed for {bid}: {e}")
                    logger.info(f"Single-job {bid} on {date_str} rescheduled from {current_time} → {new_time}")

                if correct_end > day_end:
                    logger.warning(f"Single-job {bid} on {date_str} ends at {correct_end.strftime('%H:%M')} — exceeds 5pm")
                    _alert_owner_overrun(date_str, [(bid, bd)])
                continue

            # Multi-job day: run TSP route optimiser
            jobs_input = [(bid, bd) for bid, bd, _ in day_jobs]
            optimal = find_optimal_route(jobs_input, date_str)
            if not optimal:
                # Maps API unavailable — fall back to sequential scheduling from 8am
                logger.warning(f"Route optimiser unavailable for {date_str}, applying sequential fallback")
                current_dt = day_start
                prev_addr = BUSINESS_ADDRESS
                optimal = []
                for bid, bd, _ in day_jobs:
                    addr = bd.get('address') or bd.get('suburb') or BUSINESS_ADDRESS
                    travel = get_travel_minutes(prev_addr, addr)
                    start_dt = _ceil_15(current_dt + timedelta(minutes=travel))
                    new_bd = dict(bd)
                    new_bd['preferred_time'] = start_dt.strftime('%H:%M')
                    optimal.append((bid, new_bd))
                    current_dt = start_dt + timedelta(minutes=get_job_duration_minutes(bd))
                    prev_addr = addr

            # Apply updated times and detect overruns
            current_times = {bid: bd.get('preferred_time', '') for bid, bd, _ in day_jobs}
            overrun_jobs = []

            for bid, new_bd in optimal:
                new_time = new_bd.get('preferred_time', '09:00')
                duration = get_job_duration_minutes(new_bd)
                try:
                    job_start = datetime.strptime(f"{date_str} {new_time}", "%Y-%m-%d %H:%M")
                    job_end = job_start + timedelta(minutes=duration)
                    if job_end > day_end:
                        overrun_jobs.append((bid, new_bd))
                except Exception as e:
                    logger.warning('Could not compute overrun for booking %s time %r: %s', bid, new_time, e)

                if new_time != current_times.get(bid, ''):
                    state.update_confirmed_booking_data(bid, new_bd)
                    event_id = booking_lookup[bid].get('calendar_event_id')
                    if event_id:
                        try:
                            new_dt = datetime.strptime(f"{date_str} {new_time}", "%Y-%m-%d %H:%M")
                            update_calendar_event_time(event_id, new_dt, duration)
                        except Exception as e:
                            logger.error(f"Calendar update failed for {bid}: {e}")
                    else:
                        logger.warning(f"Booking {bid} has no calendar_event_id — calendar not updated")

            if overrun_jobs:
                logger.warning(f"Schedule overrun on {date_str}: {[bid for bid, _ in overrun_jobs]} exceed 5pm")
                _alert_owner_overrun(date_str, overrun_jobs)

            changed = [bid for bid, new_bd in optimal if new_bd.get('preferred_time', '') != current_times.get(bid, '')]
            if changed:
                logger.info(
                    f"Route optimised for {date_str}: "
                    + ", ".join(
                        f"{bid}@{new_bd.get('preferred_time')}"
                        for bid, new_bd in optimal
                    )
                )

    except Exception as e:
        logger.error(f"Route optimisation error: {e}", exc_info=True)


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

    from calendar_handler import get_event_attendee_status, get_event_datetime
    from twilio_handler import handle_owner_confirm, handle_owner_decline

    for booking in pending:
        booking_id = booking['id']
        event_id = booking.get('calendar_event_id')
        if not event_id:
            continue

        status = get_event_attendee_status(event_id, owner_email)
        if status == 'accepted':
            # Read the event's current date/time — owner may have dragged it to a new slot
            event_dt = get_event_datetime(event_id)
            if event_dt:
                bd = dict(booking.get('booking_data', {}))
                old_date = bd.get('preferred_date')
                old_time = bd.get('preferred_time')
                bd['preferred_date'] = event_dt['date']
                bd['preferred_time'] = event_dt['time']
                booking = dict(booking)
                booking['booking_data'] = bd
                state.update_pending_booking_data(booking_id, bd)
                if event_dt['date'] != old_date or event_dt['time'] != old_time:
                    logger.info(f"Booking {booking_id} rescheduled by calendar drag: {old_date} {old_time} → {event_dt['date']} {event_dt['time']}")
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

        _send_morning_email(customer_email, booking_data, thread_id=booking.get('thread_id'))
        state.mark_reminder_sent(booking_id, 'morning_notification')
        logger.info(f"Morning notification sent for booking {booking_id}")

def _time_window(time_str, duration_minutes=120):
    """Convert HH:MM + duration to a friendly arrival window string, e.g. '10:00am – 12:00pm'."""
    try:
        start = datetime.strptime(time_str, "%H:%M")
        end = start + timedelta(minutes=duration_minutes)
        def fmt(dt):
            return dt.strftime("%I:%M%p").lstrip('0').lower().replace(':00', '')
        return f"{fmt(start)} – {fmt(end)}"
    except Exception as e:
        logger.warning('Could not format time window for %r: %s', time_str, e)
        return time_str

def _send_morning_email(to_email, booking_data, thread_id=None):
    """Send the day-of morning notification email to a customer."""
    try:
        import html as _html
        from google_auth import get_gmail_service
        from email_utils import send_customer_email, _p, _h2, _info_table, _ul, DARK

        service = get_gmail_service()

        name = booking_data.get('customer_name', 'there')
        first = _html.escape(name.split()[0]) if name and name != 'there' else 'there'
        from maps_handler import get_job_duration_minutes
        time_str = booking_data.get('preferred_time') or '09:00'
        window = _time_window(time_str, get_job_duration_minutes(booking_data))
        address = _html.escape(booking_data.get('address') or booking_data.get('suburb', 'your location'))
        vehicle = _html.escape(' '.join(filter(None, [
            booking_data.get('vehicle_year'),
            booking_data.get('vehicle_colour'),
            booking_data.get('vehicle_make'),
            booking_data.get('vehicle_model'),
        ])) or 'your vehicle')

        content = (
            _p(f'Hi {first},')
            + _p('We hope you\'re having a great start to your day!')
            + _h2('Your Technician is on the Way')
            + _info_table([
                ('Arrival window', window),
                ('Location', address),
                ('Vehicle', vehicle),
            ])
            + _p('To make sure we can get started straight away, please ensure:')
            + _ul([
                f'Sufficient clear working space around <strong>{vehicle}</strong>',
                'The vehicle is accessible and parked in a flat, open area',
                'You, or someone authorised on your behalf, is available to approve the work '
                'and process payment by EFTPOS on the day',
            ])
            + _p('If anything has changed or you need to reach us before the visit, '
                 'simply reply to this email.')
            + f'<p style="margin:24px 0 0;color:{DARK};font-size:15px;">'
              f'We look forward to seeing you today!<br><br>'
              f'Kind regards,<br><strong style="color:#C41230;">Wheel Doctor Team</strong></p>'
        )

        send_customer_email(
            service, to_email,
            'Your Wheel Doctor Technician is on the Way Today',
            content,
            thread_id=thread_id,
        )
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
            f"Hi {name}, just a reminder that your Wheel Doctor booking is scheduled for tomorrow "
            f"at {time_str} at {address}. "
            f"Payment is by EFTPOS on the day. "
            f"For any changes, please reply to this message. - Wheel Doctor Team"
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
        except Exception as e:
            logger.warning('Could not parse review send time for booking %s (%r %r): %s', booking_id, booking_date, time_str, e)
            continue

        customer_phone = booking_data.get('customer_phone')
        if not customer_phone:
            state.mark_reminder_sent(booking_id, 'review_request')
            continue

        name = booking_data.get('customer_name', 'there')

        if GOOGLE_REVIEW_LINK:
            msg = (
                f"Hi {name}, thanks for choosing Wheel Doctor today! "
                f"We hope you're happy with the result. "
                f"If you have a moment, a Google review would mean a lot to us: {GOOGLE_REVIEW_LINK} "
                f"- Wheel Doctor Team"
            )
        else:
            msg = (
                f"Hi {name}, thanks for choosing Wheel Doctor today! "
                f"We hope you're happy with the result. "
                f"Feel free to refer us to anyone who needs wheel repairs. - Wheel Doctor Team"
            )

        send_sms(customer_phone, msg)
        state.mark_reminder_sent(booking_id, 'review_request')
        logger.info(f"Review request sent for booking {booking_id}")


def check_pending_booking_expiry():
    """Nudge the owner for pending bookings >48h, then expire them after 72h.

    Two-stage process:
    1. At 48h: send an SMS nudge to the owner (existing behaviour).
    2. At 72h: expire the booking and notify the owner via SMS.
    """
    state = StateManager()
    with state._conn() as conn:
        rows = conn.execute(
            "SELECT * FROM bookings WHERE status='awaiting_owner' ORDER BY created_at ASC"
        ).fetchall()
    pending = [state._booking_row_to_dict(r) for r in rows]
    if not pending:
        return

    now_utc = datetime.now(timezone.utc)
    owner_mobile = os.environ.get('OWNER_MOBILE', '')

    for booking in pending:
        booking_id = booking['id']

        created_at_str = booking.get('created_at')
        if not created_at_str:
            continue

        try:
            created_at = datetime.fromisoformat(created_at_str)
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
        except Exception as e:
            logger.warning('Could not parse created_at %r for booking %s: %s', created_at_str, booking_id, e)
            continue

        age = now_utc - created_at
        booking_data = booking.get('booking_data', {})
        customer_name = booking_data.get('customer_name', 'Unknown')
        preferred_date = booking_data.get('preferred_date', 'unknown date')

        # Stage 2: expire bookings older than 72h that already received a nudge
        if age >= timedelta(hours=72) and state.has_reminder_been_sent(booking_id, 'expiry_nudge'):
            try:
                expired = state.expire_booking(booking_id)
                if expired and owner_mobile:
                    msg = (
                        f"Booking {booking_id} for {customer_name} on {_fmt_date(preferred_date)} "
                        f"has EXPIRED (no response after 72h). "
                        f"The customer has not been notified. - Wheel Doctor System"
                    )
                    send_sms(owner_mobile, msg)
                    logger.info("Booking %s expired and owner notified", booking_id)
            except Exception as e:
                logger.error("Failed to expire booking %s: %s", booking_id, e)
            continue

        # Stage 1: nudge at 48h
        if age >= timedelta(hours=48) and not state.has_reminder_been_sent(booking_id, 'expiry_nudge'):
            if not owner_mobile:
                logger.warning("OWNER_MOBILE not configured, skipping expiry nudge SMS")
                return

            msg = (
                f"Reminder: Booking {booking_id} for {customer_name} on {_fmt_date(preferred_date)} "
                f"still needs your YES or NO. "
                f"Reply YES {booking_id} or NO {booking_id}"
            )

            try:
                send_sms(owner_mobile, msg)
                state.mark_reminder_sent(booking_id, 'expiry_nudge')
                logger.info("Expiry nudge sent for booking %s (age: %s)", booking_id, age)
            except Exception as e:
                logger.error("Failed to send expiry nudge for %s: %s", booking_id, e)


def send_owner_daily_briefing():
    """At 07:30 Perth time, send the owner an SMS summary of today's jobs."""
    now = _perth_now()
    if not (now.hour == 7 and now.minute >= 30 and now.minute < 35):
        return

    state = StateManager()
    today = now.strftime('%Y-%m-%d')

    last_sent = state.get_app_state('last_daily_briefing_date')
    if last_sent == today:
        return

    from maps_handler import get_job_duration_minutes

    confirmed = state.get_confirmed_bookings()

    jobs = []
    for booking_id, booking in confirmed.items():
        if booking.get('status') != 'confirmed':
            continue
        booking_data = booking.get('booking_data', {})
        if booking_data.get('preferred_date') != today:
            continue
        jobs.append((booking_id, booking_data))

    if not jobs:
        return

    # Sort by preferred_time
    def _sort_key(item):
        return item[1].get('preferred_time', '00:00')

    jobs.sort(key=_sort_key)

    first_bd = jobs[0][1]
    first_time = first_bd.get('preferred_time', '?')
    first_suburb = first_bd.get('suburb') or first_bd.get('address', '?')

    last_bd = jobs[-1][1]
    last_time_str = last_bd.get('preferred_time', '09:00')
    try:
        last_start = datetime.strptime(f"{today} {last_time_str}", "%Y-%m-%d %H:%M")
        duration = get_job_duration_minutes(last_bd)
        finish_dt = last_start + timedelta(minutes=duration)
        finish_time = finish_dt.strftime('%H:%M')
    except Exception as e:
        logger.warning('Could not compute finish time for daily briefing (%r %r): %s', today, last_time_str, e)
        finish_time = '?'

    msg = (
        f"Today: {len(jobs)} job(s). "
        f"First at {first_time} ({first_suburb}). "
        f"Est. finish ~{finish_time}. - Wheel Doctor"
    )

    owner_mobile = os.environ.get('OWNER_MOBILE', '')
    if not owner_mobile:
        logger.warning("OWNER_MOBILE not configured, skipping daily briefing SMS")
        return

    try:
        send_sms(owner_mobile, msg)
        state.set_app_state('last_daily_briefing_date', today)
        logger.info(f"Daily briefing sent for {today}: {len(jobs)} job(s)")
    except Exception as e:
        logger.error(f"Failed to send daily briefing: {e}")


def check_dlq_for_escalation():
    """Email owner when booking extractions have failed 3+ times (DLQ entries)."""
    if not get_flag('flag_dlq_escalation'):
        return
    try:
        from state_manager import StateManager
        state = StateManager()
        unnotified = state.get_unnotified_dlq_entries()
        if not unnotified:
            return

        owner_email = os.environ.get('OWNER_EMAIL', '')
        if not owner_email:
            logger.warning("DLQ: OWNER_EMAIL not set — cannot escalate")
            return

        dlq_lines = '\n'.join([
            f"  - {r['customer_email']} (failed {r['failure_count']}x, last: {r['last_failed_at'][:16]}, type: {r['error_type']})"
            for r in unnotified
        ])
        body = (
            f"ALERT: {len(unnotified)} booking enquiry(ies) failed AI extraction 3+ times "
            f"and were NOT sent to customers:\n\n{dlq_lines}\n\n"
            f"These customers' emails need manual follow-up. Check Railway logs for details.\n"
            f"- Wheel Doctor System"
        )
        from email.mime.text import MIMEText
        import base64
        from google_auth import get_gmail_service
        msg = MIMEText(body)
        msg['to'] = owner_email
        msg['subject'] = f"[ACTION REQUIRED] {len(unnotified)} Failed Booking Extraction(s)"
        service = get_gmail_service()
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        service.users().messages().send(userId='me', body={'raw': raw}).execute()
        for r in unnotified:
            state.mark_dlq_notified(r['gmail_msg_id'])
        logger.info(f"DLQ escalation email sent — {len(unnotified)} entries")
    except Exception as e:
        logger.error(f"check_dlq_for_escalation failed: {e}", exc_info=True)


def send_preflight_schedule_report():
    """At 06:30 Perth time, SMS owner a pre-flight daily schedule report."""
    if not get_flag('flag_preflight_report'):
        return
    now = _perth_now()
    if not (now.hour == 6 and 30 <= now.minute < 35):
        return

    try:
        from state_manager import StateManager
        from maps_handler import get_job_duration_minutes, BUSINESS_END_HOUR
        state = StateManager()
        today = now.strftime('%Y-%m-%d')

        owner_mobile = os.environ.get('OWNER_MOBILE', '')
        if not owner_mobile:
            logger.warning("OWNER_MOBILE not configured, skipping preflight schedule report SMS")
            return

        last = state.get_app_state('last_preflight_report_date')
        if last == today:
            return

        confirmed = state.get_confirmed_bookings()
        today_jobs = []
        for bid, booking in confirmed.items():
            if booking.get('status') != 'confirmed':
                continue
            bd = booking.get('booking_data', {})
            if bd.get('preferred_date') != today:
                continue
            today_jobs.append((bid, bd))

        state.set_app_state('last_preflight_report_date', today)

        if not today_jobs:
            send_sms(owner_mobile, f"Pre-flight {today}: No jobs scheduled today.")
            return

        today_jobs.sort(key=lambda x: x[1].get('preferred_time', '09:00'))

        issues = []
        lines = []
        from datetime import datetime as _dt, timedelta as _td
        day_end = _dt.strptime(f"{today} {BUSINESS_END_HOUR:02d}:00", "%Y-%m-%d %H:%M")
        prev_end = _dt.strptime(f"{today} 08:00", "%Y-%m-%d %H:%M")

        for i, (bid, bd) in enumerate(today_jobs):
            t = bd.get('preferred_time', '09:00')
            duration = get_job_duration_minutes(bd)
            customer = (bd.get('customer_name') or '?').split()[0]
            suburb = bd.get('suburb') or (bd.get('address') or '?').split(',')[0]
            try:
                job_start = _dt.strptime(f"{today} {t}", "%Y-%m-%d %H:%M")
                job_end = job_start + _td(minutes=duration)
            except Exception as e:
                logger.warning('Could not parse job time for preflight report, booking %s time %r: %s', bid, t, e)
                continue
            if i > 0 and job_start < prev_end:
                issues.append(f"CONFLICT job {i+1} ({customer}) overlaps previous")
            if job_end > day_end:
                issues.append(f"OVERRUN job {i+1} ({customer}) ends {job_end.strftime('%H:%M')}")
            lines.append(f"{t} {customer} @{suburb} ({duration}m)")
            prev_end = max(prev_end, job_end)

        header = f"Pre-flight {today} — {len(today_jobs)} job(s)"
        if issues:
            header += f" ⚠ {len(issues)} issue(s)"
        report = header + ":\n" + "\n".join(lines[:5])
        if issues:
            report += "\nISSUES:\n" + "\n".join(issues)
        if len(today_jobs) > 5:
            report += f"\n...+{len(today_jobs)-5} more"

        send_sms(owner_mobile, report)
        logger.info(f"Pre-flight report sent for {today}")
    except Exception as e:
        logger.error(f"send_preflight_schedule_report failed: {e}", exc_info=True)


def send_maintenance_reminders():
    """Daily: send 6-month and 12-month maintenance reminder SMS to past customers."""
    from feature_flags import get_flag
    if not get_flag('flag_maintenance_reminders'):
        return
    try:
        from state_manager import StateManager
        state = StateManager()
        today = _perth_now().strftime('%Y-%m-%d')

        for interval, months in [('6m', 6), ('12m', 12)]:
            due = state.get_maintenance_reminders_due(today, interval)
            for row in due:
                phone = row.get('customer_phone')
                if not phone:
                    state.mark_maintenance_reminder_sent(row['id'], interval)
                    continue
                vehicle = row.get('vehicle_key', '').replace('_', ' ').title() or 'your vehicle'
                service = (row.get('service_type') or 'wheel repair').replace('_', ' ')
                if interval == '6m':
                    msg = (
                        f"Hi, it's been 6 months since your {service} on {vehicle}. "
                        f"Time for a check-up? We're here when you need us. - Wheel Doctor Team"
                    )
                else:
                    msg = (
                        f"Hi, it's been a year since your {service} on {vehicle}. "
                        f"Keep it looking its best — reply to book your next service. - Wheel Doctor Team"
                    )
                try:
                    # Mark BEFORE sending so a crash between send and mark never causes a duplicate SMS
                    state.mark_maintenance_reminder_sent(row['id'], interval)
                    send_sms(phone, msg)
                    logger.info(f"Maintenance reminder ({interval}) sent to {phone} for booking {row['booking_id']}")
                except Exception as e:
                    logger.error(f"Maintenance reminder SMS failed: {e}")
    except Exception as e:
        logger.error(f"send_maintenance_reminders failed: {e}", exc_info=True)


_BACKUP_MAX_BYTES = 25 * 1024 * 1024  # 25 MB — Gmail attachment limit

def backup_database_to_email():
    """At 02:00 Perth time, email the SQLite database as an attachment to the owner.

    WARNING: This backup contains PII (customer names, phones, addresses) and is
    sent unencrypted as a standard email attachment.  Ensure the owner's inbox
    is adequately secured.  For encrypted backups, consider GPG before attaching.
    """
    now = _perth_now()
    if not (now.hour == 2 and now.minute < 5):
        return

    state = StateManager()
    today = now.strftime('%Y-%m-%d')

    last_backup = state.get_app_state('last_backup_date')
    if last_backup == today:
        return

    owner_email = os.environ.get('OWNER_EMAIL', '')
    if owner_email:
        logger.warning(
            'backup_database_to_email: sending database to %s — file contains PII '
            '(customer names, phones, addresses) and is transmitted unencrypted.',
            owner_email,
        )

    try:
        from google_auth import get_gmail_service
        from email.mime.multipart import MIMEMultipart
        from email.mime.base import MIMEBase
        from email import encoders
        import base64

        # Safety: refuse to send if the DB file exceeds the email attachment limit
        try:
            db_size = os.path.getsize(DB_PATH)
        except OSError as e:
            logger.error('backup_database_to_email: cannot stat DB file %s: %s', DB_PATH, e)
            return

        if db_size > _BACKUP_MAX_BYTES:
            logger.warning(
                'backup_database_to_email: DB file is %.1f MB — exceeds 25 MB email limit; '
                'skipping attachment send.  Use an alternative backup method.',
                db_size / (1024 * 1024),
            )
            state.set_app_state('last_backup_date', today)
            return

        service = get_gmail_service()
        msg = MIMEMultipart()
        msg['to'] = owner_email
        msg['subject'] = f"Wheel Doctor DB Backup — {today}"

        with open(DB_PATH, 'rb') as f:
            part = MIMEBase('application', 'octet-stream')
            part.set_payload(f.read())
            encoders.encode_base64(part)
            part.add_header('Content-Disposition', f'attachment; filename="booking_state_{today}.db"')
            msg.attach(part)

        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        service.users().messages().send(userId='me', body={'raw': raw}).execute()

        state.set_app_state('last_backup_date', today)
        logger.info(f"Database backup emailed for {today}")
    except Exception as e:
        logger.error(f"Database backup failed: {e}", exc_info=True)


def check_waitlist_opportunities():
    """Check if any cancelled bookings create openings for waitlisted customers.

    Runs hourly. For each date that has waitlisted customers, checks if the date
    now has available capacity. If so, sends a notification email to waitlisted customers.
    """
    try:
        from state_manager import StateManager, _get_conn
        from feature_flags import get_flag
        import json as _json

        if not get_flag('flag_auto_email_replies'):
            return

        state = StateManager()

        # Find dates with unnotified waitlist entries
        with _get_conn() as conn:
            waitlist_dates = conn.execute(
                """SELECT DISTINCT requested_date FROM waitlist
                   WHERE notified=0 AND requested_date >= date('now')"""
            ).fetchall()

        for row in waitlist_dates:
            date_str = row[0]

            # Check current availability for this date
            confirmed = state.get_confirmed_bookings_for_date(date_str)
            # Simple heuristic: if fewer than 4 confirmed bookings, there's space
            if len(confirmed) >= 4:
                continue

            # Notify all unnotified waitlisted customers for this date
            waitlist_entries = state.get_waitlist_for_date(date_str)
            for entry in waitlist_entries:
                try:
                    from google_auth import get_gmail_service
                    from email_utils import send_customer_email, _p, _h2, RED, DARK

                    service = get_gmail_service()
                    cust_name = (entry.get('customer_name') or 'there').split()[0]

                    content = (
                        _p(f'Hi {cust_name},')
                        + _p(f'Great news! A spot has become available on '
                             f'<strong>{_fmt_date(date_str)}</strong> — a date you previously enquired about.')
                        + _p('If you\'re still interested in booking, simply reply to this email '
                             'and we\'ll get you confirmed as soon as possible.')
                        + _p('Availability is limited, so please reply promptly to secure your spot.')
                        + f'<p style="margin:24px 0 0;color:{DARK};font-size:15px;">'
                          f'Kind regards,<br><strong style="color:{RED};">Wheel Doctor Team</strong></p>'
                    )

                    send_customer_email(
                        service, entry['customer_email'],
                        f'Availability Update — {_fmt_date(date_str)}', content
                    )
                    state.mark_waitlist_notified(entry['id'])
                    logger.info(f"Waitlist notification sent to {entry['customer_email']} for {date_str}")

                except Exception as e:
                    logger.error(f"Waitlist notification failed for {entry.get('id')}: {e}")

    except Exception as e:
        logger.error(f"check_waitlist_opportunities error: {e}", exc_info=True)


def run_db_cleanup():
    """Weekly housekeeping: prune unbounded-growth tables."""
    try:
        from state_manager import _get_conn
        import sqlite3 as _sqlite3

        with _get_conn() as conn:
            # Keep only last 10,000 processed_emails entries (prune oldest)
            try:
                conn.execute("""
                    DELETE FROM processed_emails
                    WHERE msg_id NOT IN (
                        SELECT msg_id FROM processed_emails
                        ORDER BY rowid DESC LIMIT 10000
                    )
                """)
                logger.info("DB cleanup: pruned old processed_emails entries")
            except Exception as e:
                logger.warning(f"DB cleanup processed_emails error: {e}")

            # Prune overrun alert cooldown keys older than 60 days
            try:
                from datetime import datetime as _dt, timedelta as _td
                cutoff = (_dt.utcnow() - _td(days=60)).strftime('%Y-%m-%d')
                conn.execute("""
                    DELETE FROM app_state
                    WHERE key LIKE 'overrun_alert_sent_%'
                    AND SUBSTR(key, LENGTH('overrun_alert_sent_') + 1) < ?
                """, (cutoff,))
                logger.info("DB cleanup: pruned old overrun alert cooldown keys")
            except Exception as e:
                logger.warning(f"DB cleanup app_state error: {e}")

            # Prune failed_extractions that are owner_notified and older than 90 days
            try:
                from datetime import datetime as _dt2, timedelta as _td2
                cutoff2 = (_dt2.utcnow() - _td2(days=90)).isoformat()
                conn.execute("""
                    DELETE FROM failed_extractions
                    WHERE owner_notified = 1 AND last_failed_at < ?
                """, (cutoff2,))
                logger.info("DB cleanup: pruned old notified DLQ entries")
            except Exception as e:
                logger.warning(f"DB cleanup failed_extractions error: {e}")

    except Exception as e:
        logger.error(f"DB cleanup error: {e}", exc_info=True)
