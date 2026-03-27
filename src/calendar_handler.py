import os
import logging
from datetime import datetime, timedelta
from googleapiclient.errors import HttpError
from google_auth import get_calendar_service
from maps_handler import get_travel_minutes, BUSINESS_ADDRESS, get_job_duration_minutes

logger = logging.getLogger(__name__)

DEFAULT_JOB_DURATION_MINUTES = 120

TENTATIVE_EVENT_PREFIX = "[PENDING]"

def _get_previous_job_address(booking_data):
    """Return address of the last confirmed job before this one on the same day, or None."""
    try:
        from state_manager import StateManager
        state = StateManager()
        date_str = booking_data.get('preferred_date')
        time_str = booking_data.get('preferred_time') or '09:00'
        if not date_str:
            return None

        day_bookings = state.get_confirmed_bookings_for_date(date_str)
        new_start = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")

        candidates = []
        for bd in day_bookings:
            t = bd.get('preferred_time') or '09:00'
            try:
                s = datetime.strptime(f"{date_str} {t}", "%Y-%m-%d %H:%M")
            except ValueError:
                continue
            if s < new_start:
                addr = bd.get('address') or bd.get('suburb') or ''
                if addr:
                    candidates.append((s, addr))

        if not candidates:
            # First job of the day — travel is measured from the business address
            return BUSINESS_ADDRESS
        candidates.sort(key=lambda x: x[0], reverse=True)
        return candidates[0][1]
    except Exception:
        return BUSINESS_ADDRESS


def create_calendar_event(booking_data):
    """
    Create a Google Calendar event for a confirmed booking.
    Returns event ID or None on failure.
    """
    try:
        service = get_calendar_service()
        
        date_str = booking_data.get('preferred_date')
        time_str = booking_data.get('preferred_time') or '09:00'
        
        if not date_str:
            logger.error("No date in booking data, cannot create calendar event")
            return None
        
        # Parse start datetime — use rim-count-based duration
        job_duration = get_job_duration_minutes(booking_data)
        start_dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
        end_dt = start_dt + timedelta(minutes=job_duration)
        
        # Build event title
        customer_name = booking_data.get('customer_name', 'Customer')
        service_type = booking_data.get('service_type', 'rim_repair').replace('_', ' ').title()
        num_rims = booking_data.get('num_rims')
        title = f"{service_type} - {customer_name}"
        if num_rims:
            title += f" (x{num_rims} rims)"
        
        # Build description with all job details tech needs
        vehicle = ' '.join(filter(None, [
            booking_data.get('vehicle_colour'),
            booking_data.get('vehicle_make'),
            booking_data.get('vehicle_model')
        ])) or 'Not specified'
        
        customer_phone = booking_data.get('customer_phone', 'N/A')
        customer_email = booking_data.get('customer_email', 'N/A')
        address = booking_data.get('address') or booking_data.get('suburb', 'TBC')
        notes = booking_data.get('notes', '')
        
        # Travel time from previous job on the same day
        prev_address = _get_previous_job_address(booking_data)
        if prev_address and address and address != 'TBC':
            travel_min = get_travel_minutes(prev_address, address)
            travel_line = f"Travel from previous job: ~{travel_min} min  ({prev_address} → {address})"
        else:
            travel_line = ""

        description = f"""JOB DETAILS
===========
Customer: {customer_name}
Phone: {customer_phone}
Email: {customer_email}

Vehicle: {vehicle}
Service: {service_type}{f' x{num_rims} rims' if num_rims else ''}
Address: {address}
Duration: ~{job_duration // 60}h{f' {job_duration % 60}m' if job_duration % 60 else ''}
{travel_line}

Payment: EFTPOS on the day

{f'Notes: {notes}' if notes else ''}""".strip()
        
        event = {
            'summary': title,
            'location': address,
            'description': description,
            'start': {
                'dateTime': start_dt.isoformat(),
                'timeZone': 'Australia/Perth'
            },
            'end': {
                'dateTime': end_dt.isoformat(),
                'timeZone': 'Australia/Perth'
            },
            'reminders': {
                'useDefault': False,
                'overrides': [
                    {'method': 'popup', 'minutes': 60},
                    {'method': 'popup', 'minutes': 15}
                ]
            }
        }
        
        calendar_id = os.environ['GOOGLE_CALENDAR_ID']
        
        created_event = service.events().insert(
            calendarId=calendar_id,
            body=event
        ).execute()
        
        event_id = created_event.get('id')
        logger.info(f"Calendar event created: {event_id} for {title} on {date_str}")
        return event_id
        
    except HttpError as e:
        logger.error(f"Google Calendar API error: {e}")
        return None
    except Exception as e:
        logger.error(f"Calendar event creation error: {e}", exc_info=True)
        return None


def create_tentative_calendar_invite(booking_data, pending_id):
    """
    Create a tentative/pending Google Calendar event as a fallback when SMS fails.
    The event is prefixed with [PENDING] so it's clearly unconfirmed.
    Returns event ID or None on failure.
    """
    try:
        service = get_calendar_service()

        date_str = booking_data.get('preferred_date')
        time_str = booking_data.get('preferred_time') or '09:00'

        if not date_str:
            logger.error("No date in booking data, cannot create tentative calendar event")
            return None

        job_duration = get_job_duration_minutes(booking_data)
        start_dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
        end_dt = start_dt + timedelta(minutes=job_duration)

        customer_name = booking_data.get('customer_name', 'Customer')
        service_type = booking_data.get('service_type', 'rim_repair').replace('_', ' ').title()
        num_rims = booking_data.get('num_rims')
        title = f"{TENTATIVE_EVENT_PREFIX} {service_type} - {customer_name}"
        if num_rims:
            title += f" (x{num_rims} rims)"

        vehicle = ' '.join(filter(None, [
            booking_data.get('vehicle_colour'),
            booking_data.get('vehicle_make'),
            booking_data.get('vehicle_model')
        ])) or 'Not specified'

        customer_phone = booking_data.get('customer_phone', 'N/A')
        customer_email = booking_data.get('customer_email', 'N/A')
        address = booking_data.get('address') or booking_data.get('suburb', 'TBC')
        notes = booking_data.get('notes', '')

        prev_address = _get_previous_job_address(booking_data)
        if prev_address and address and address != 'TBC':
            travel_min = get_travel_minutes(prev_address, address)
            travel_line = f"Travel from previous job: ~{travel_min} min  ({prev_address} → {address})"
        else:
            travel_line = ""

        description = f"""⚠️ PENDING CONFIRMATION — SMS delivery failed. Reply YES/NO via SMS or edit/delete this event.
Booking ID: {pending_id}

JOB DETAILS
===========
Customer: {customer_name}
Phone: {customer_phone}
Email: {customer_email}

Vehicle: {vehicle}
Service: {service_type}{f' x{num_rims} rims' if num_rims else ''}
Address: {address}
Duration: ~{job_duration // 60}h{f' {job_duration % 60}m' if job_duration % 60 else ''}
{travel_line}

Payment: EFTPOS on the day

{f'Notes: {notes}' if notes else ''}""".strip()

        owner_email = os.environ.get('OWNER_EMAIL', '')
        attendees = [{'email': owner_email}] if owner_email else []

        event = {
            'summary': title,
            'location': address,
            'description': description,
            'status': 'tentative',
            'start': {
                'dateTime': start_dt.isoformat(),
                'timeZone': 'Australia/Perth'
            },
            'end': {
                'dateTime': end_dt.isoformat(),
                'timeZone': 'Australia/Perth'
            },
            'reminders': {
                'useDefault': False,
                'overrides': [
                    {'method': 'popup', 'minutes': 60},
                    {'method': 'popup', 'minutes': 15}
                ]
            }
        }
        if attendees:
            event['attendees'] = attendees

        calendar_id = os.environ['GOOGLE_CALENDAR_ID']

        created_event = service.events().insert(
            calendarId=calendar_id,
            body=event,
            sendUpdates='all' if attendees else 'none'
        ).execute()

        event_id = created_event.get('id')
        logger.info(f"Tentative calendar event created: {event_id} for {title} on {date_str} (booking {pending_id})")
        return event_id

    except HttpError as e:
        logger.error(f"Google Calendar API error creating tentative event: {e}")
        return None
    except Exception as e:
        logger.error(f"Tentative calendar event creation error: {e}", exc_info=True)
        return None


def delete_calendar_event(event_id):
    """Delete a calendar event by ID. Used to remove tentative events on decline."""
    try:
        service = get_calendar_service()
        calendar_id = os.environ['GOOGLE_CALENDAR_ID']
        service.events().delete(calendarId=calendar_id, eventId=event_id).execute()
        logger.info(f"Calendar event {event_id} deleted")
        return True
    except HttpError as e:
        logger.error(f"Error deleting calendar event {event_id}: {e}")
        return False
    except Exception as e:
        logger.error(f"Error deleting calendar event {event_id}: {e}")
        return False


def confirm_tentative_event(event_id, booking_data):
    """
    Convert a tentative [PENDING] event to a confirmed event.
    Strips the [PENDING] prefix, sets status to confirmed.
    Returns True on success.
    """
    try:
        service = get_calendar_service()
        calendar_id = os.environ['GOOGLE_CALENDAR_ID']

        event = service.events().get(calendarId=calendar_id, eventId=event_id).execute()

        summary = event.get('summary', '')
        if summary.startswith(TENTATIVE_EVENT_PREFIX):
            event['summary'] = summary[len(TENTATIVE_EVENT_PREFIX):].strip()

        description = event.get('description', '')
        # Remove the pending warning header
        if '⚠️ PENDING CONFIRMATION' in description:
            lines = description.split('\n')
            lines = [l for l in lines if not l.startswith('⚠️') and not l.startswith('Booking ID:')]
            # Remove leading blank line if any
            while lines and not lines[0].strip():
                lines.pop(0)
            event['description'] = '\n'.join(lines)

        event['status'] = 'confirmed'
        if 'attendees' in event:
            del event['attendees']

        service.events().update(
            calendarId=calendar_id,
            eventId=event_id,
            body=event,
            sendUpdates='none'
        ).execute()

        logger.info(f"Tentative event {event_id} confirmed and cleaned up")
        return True

    except Exception as e:
        logger.error(f"Error confirming tentative event {event_id}: {e}")
        return False
