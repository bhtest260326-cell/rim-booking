import os
import logging
import requests
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

GOOGLE_MAPS_API_KEY = os.environ.get('GOOGLE_MAPS_API_KEY', '')
BUSINESS_ADDRESS = '76 Albert St, Osborne Park WA 6017'
BUSINESS_START_HOUR = 8    # 8:00 AM — first job of the day
BUSINESS_LATEST_START = 15  # 3:00 PM — last job must start by this to finish by ~5pm
TRAVEL_BUFFER_MINUTES = 10  # padding added on top of Maps estimate

# Job duration table (minutes) keyed by number of rims
_RIM_DURATION: dict[int, int] = {1: 120, 2: 180, 3: 240, 4: 300}
_DEFAULT_DURATION = 120  # fallback when rim count unknown


def get_job_duration_minutes(booking_data: dict) -> int:
    """Return estimated job duration in minutes based on rim count and service type."""
    service = (booking_data.get('service_type') or '').lower()

    # Paint touch-ups are quicker — not in the rim table
    if service == 'paint_touchup':
        return 60

    num_rims = booking_data.get('num_rims')
    try:
        n = int(num_rims)
    except (TypeError, ValueError):
        return _DEFAULT_DURATION

    if n <= 0:
        return _DEFAULT_DURATION
    if n in _RIM_DURATION:
        return _RIM_DURATION[n]
    # Extrapolate beyond 4 rims: base 300 min + 60 per extra rim
    return 300 + (n - 4) * 60


def get_travel_minutes(origin, destination):
    """Return driving time in minutes between two addresses.

    Appends ', Perth WA, Australia' to help Maps disambiguate suburb-only addresses.
    Falls back to 30 minutes if the API key is missing or the call fails.
    """
    if not GOOGLE_MAPS_API_KEY:
        logger.debug("GOOGLE_MAPS_API_KEY not set — using 30 min default travel time")
        return 30

    if not origin or not destination:
        return 30

    try:
        resp = requests.get(
            "https://maps.googleapis.com/maps/api/distancematrix/json",
            params={
                'origins': f"{origin}, Perth WA, Australia",
                'destinations': f"{destination}, Perth WA, Australia",
                'key': GOOGLE_MAPS_API_KEY,
                'mode': 'driving',
                'region': 'au',
            },
            timeout=10
        )
        data = resp.json()

        if data.get('status') != 'OK':
            logger.warning(f"Maps API status: {data.get('status')} for {origin} → {destination}")
            return 30

        rows = data.get('rows', [])
        if not rows:
            return 30

        elements = rows[0].get('elements', [])
        if not elements or elements[0].get('status') != 'OK':
            return 30

        travel_min = int(elements[0]['duration']['value'] / 60) + TRAVEL_BUFFER_MINUTES
        logger.info(f"Travel {origin} → {destination}: {travel_min} min")
        return travel_min

    except Exception as e:
        logger.error(f"Maps API error: {e}")
        return 30


def find_next_available_slot(target_date_str, new_address, day_bookings,
                             new_booking_data=None):
    """Find the earliest available start time on target_date for a new job.

    Args:
        target_date_str:  'YYYY-MM-DD' string for the desired date.
        new_address:      address/suburb string for the new job.
        day_bookings:     list of booking_data dicts already confirmed on that date.
        new_booking_data: full booking_data dict for the new job (used to calculate
                          its duration from rim count). Falls back to default if None.

    Returns:
        (date_str, time_str) — may advance to next business day if no room today.
    """
    try:
        target_date = datetime.strptime(target_date_str, "%Y-%m-%d")
    except ValueError:
        logger.warning(f"find_next_available_slot: invalid date '{target_date_str}', defaulting to today")
        target_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    # Advance past weekends
    while target_date.weekday() >= 5:
        target_date += timedelta(days=1)
    target_date_str = target_date.strftime("%Y-%m-%d")

    day_start = target_date.replace(hour=BUSINESS_START_HOUR, minute=0, second=0, microsecond=0)
    latest_start = target_date.replace(hour=BUSINESS_LATEST_START, minute=0, second=0, microsecond=0)

    # Duration of the new job being scheduled
    new_job_duration = get_job_duration_minutes(new_booking_data or {})

    if not day_bookings:
        # First job of the day — measure travel from the business address
        travel_from_base = get_travel_minutes(BUSINESS_ADDRESS, new_address)
        first_start = day_start + timedelta(minutes=travel_from_base)
        if first_start > day_start.replace(hour=BUSINESS_LATEST_START):
            first_start = day_start  # fallback if Maps gives a crazy result
        return target_date_str, first_start.strftime("%H:%M")

    # Build sorted list of (start, end, address) for existing jobs using their
    # own durations so longer multi-rim jobs block the right amount of time.
    existing = []
    for b in day_bookings:
        time_str = b.get('preferred_time') or '09:00'
        try:
            start = datetime.strptime(f"{target_date_str} {time_str}", "%Y-%m-%d %H:%M")
        except ValueError:
            continue
        duration = get_job_duration_minutes(b)
        end = start + timedelta(minutes=duration)
        addr = b.get('address') or b.get('suburb') or ''
        existing.append((start, end, addr))
    existing.sort(key=lambda x: x[0])

    if not existing:
        return target_date_str, day_start.strftime("%H:%M")

    # Walk through the day looking for a gap.
    # Always start from the business address so the first job accounts for travel from base.
    prev_end = day_start
    prev_addr = BUSINESS_ADDRESS

    for job_start, job_end, job_addr in existing:
        # Earliest we can start the new job (travel from previous position)
        travel_to_new = get_travel_minutes(prev_addr, new_address)
        earliest = prev_end + timedelta(minutes=travel_to_new)

        # Travel from new job to the upcoming existing job
        travel_new_to_next = get_travel_minutes(new_address, job_addr) if (new_address and job_addr) else 30

        new_job_end = earliest + timedelta(minutes=new_job_duration)

        # Fits before this existing job?
        if new_job_end + timedelta(minutes=travel_new_to_next) <= job_start and earliest <= latest_start:
            return target_date_str, earliest.strftime("%H:%M")

        # Skip past this existing job
        prev_end = job_end
        prev_addr = job_addr

    # Try slotting after the last existing job
    travel_from_last = get_travel_minutes(prev_addr, new_address)
    candidate = prev_end + timedelta(minutes=travel_from_last)

    if candidate <= latest_start:
        return target_date_str, candidate.strftime("%H:%M")

    # No room today — move to next business day
    next_day = target_date + timedelta(days=1)
    while next_day.weekday() >= 5:
        next_day += timedelta(days=1)
    logger.info(f"No slot available on {target_date_str}, advancing to {next_day.strftime('%Y-%m-%d')}")
    return next_day.strftime("%Y-%m-%d"), day_start.strftime("%H:%M")
