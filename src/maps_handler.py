import os
import logging
import math
import requests
from datetime import datetime, timedelta
from itertools import permutations as _perms

logger = logging.getLogger(__name__)


def _ceil_15(dt):
    """Round a datetime UP to the next 15-minute boundary (e.g. 11:44 → 11:45, 11:46 → 12:00)."""
    remainder = dt.minute % 15
    if remainder == 0 and dt.second == 0:
        return dt.replace(second=0, microsecond=0)
    add_minutes = 15 - remainder
    return (dt + timedelta(minutes=add_minutes)).replace(second=0, microsecond=0)

GOOGLE_MAPS_API_KEY = os.environ.get('GOOGLE_MAPS_API_KEY', '')
BUSINESS_ADDRESS = '76 Albert St, Osborne Park WA 6017'
BUSINESS_START_HOUR = 8    # 8:00 AM — depart Osborne Park, first job no earlier than this
BUSINESS_END_HOUR = 17     # 5:00 PM — all jobs must END by this time
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


def get_distance_matrix(addresses):
    """Fetch NxN travel-time matrix (minutes) for a list of addresses in one API call.

    addresses[0] should be the depot. Returns a 2-D list where matrix[i][j] is the
    driving time in minutes from addresses[i] to addresses[j], including TRAVEL_BUFFER_MINUTES.
    Falls back to 30-minute defaults on any failure.
    """
    n = len(addresses)
    fallback = [[0 if i == j else 30 for j in range(n)] for i in range(n)]

    if not GOOGLE_MAPS_API_KEY or n < 2:
        return fallback

    try:
        addrs_ctx = [f"{a}, Perth WA, Australia" for a in addresses]
        resp = requests.get(
            "https://maps.googleapis.com/maps/api/distancematrix/json",
            params={
                'origins':      '|'.join(addrs_ctx),
                'destinations': '|'.join(addrs_ctx),
                'key':          GOOGLE_MAPS_API_KEY,
                'mode':         'driving',
                'region':       'au',
            },
            timeout=15,
        )
        data = resp.json()

        if data.get('status') != 'OK':
            logger.warning(f"Distance matrix status: {data.get('status')}")
            return fallback

        matrix = []
        for i, row in enumerate(data.get('rows', [])):
            row_mins = []
            for j, elem in enumerate(row.get('elements', [])):
                if i == j:
                    row_mins.append(0)
                elif elem.get('status') == 'OK':
                    row_mins.append(int(elem['duration']['value'] / 60) + TRAVEL_BUFFER_MINUTES)
                else:
                    row_mins.append(30)
            matrix.append(row_mins)

        logger.info(f"Distance matrix fetched: {n}×{n} locations")
        return matrix

    except Exception as e:
        logger.error(f"Distance matrix error: {e}")
        return fallback


def find_optimal_route(bookings_for_day, date_str):
    """Find the optimal visit order for a list of same-day confirmed bookings.

    Uses a full NxN distance matrix fetched in one Maps API call.  Solves TSP
    with brute-force for N ≤ 8 jobs, nearest-neighbour heuristic for larger N.
    The route always departs from and returns to BUSINESS_ADDRESS.

    Args:
        bookings_for_day: list of (booking_id, booking_data_dict) — same day, any order.
        date_str:         'YYYY-MM-DD'

    Returns:
        Ordered list of (booking_id, updated_booking_data) with corrected
        preferred_time values, or None if optimisation is not applicable.
    """
    n = len(bookings_for_day)
    if n < 2 or not GOOGLE_MAPS_API_KEY:
        return None

    try:
        target_date = datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        return None

    # Index 0 = depot, 1..n = job addresses
    addresses = [BUSINESS_ADDRESS] + [
        bd.get('address') or bd.get('suburb') or BUSINESS_ADDRESS
        for _, bd in bookings_for_day
    ]

    matrix = get_distance_matrix(addresses)

    # ── TSP ──────────────────────────────────────────────────────────────────
    job_idxs = list(range(1, n + 1))
    best_order = None
    best_cost = float('inf')

    if n <= 8:
        for perm in _perms(job_idxs):
            cost = matrix[0][perm[0]]
            for k in range(len(perm) - 1):
                cost += matrix[perm[k]][perm[k + 1]]
            cost += matrix[perm[-1]][0]
            if cost < best_cost:
                best_cost = cost
                best_order = perm
    else:
        # Nearest-neighbour heuristic
        unvisited = set(job_idxs)
        current = 0
        order = []
        while unvisited:
            nearest = min(unvisited, key=lambda j: matrix[current][j])
            order.append(nearest)
            unvisited.remove(nearest)
            current = nearest
        best_order = tuple(order)
        best_cost = (matrix[0][best_order[0]]
                     + sum(matrix[best_order[k]][best_order[k + 1]] for k in range(n - 1))
                     + matrix[best_order[-1]][0])

    # ── Assign start times ───────────────────────────────────────────────────
    day_start = target_date.replace(
        hour=BUSINESS_START_HOUR, minute=0, second=0, microsecond=0
    )
    current_dt = day_start
    prev_idx = 0  # start at depot

    result = []
    for addr_idx in best_order:
        job_slot = addr_idx - 1
        booking_id, booking_data = bookings_for_day[job_slot]

        travel = matrix[prev_idx][addr_idx]
        start_dt = _ceil_15(current_dt + timedelta(minutes=travel))
        if start_dt < day_start:
            start_dt = day_start

        updated = dict(booking_data)
        updated['preferred_time'] = start_dt.strftime("%H:%M")
        result.append((booking_id, updated))

        current_dt = start_dt + timedelta(minutes=get_job_duration_minutes(booking_data))
        prev_idx = addr_idx

    # Warn if the optimised schedule runs past 5pm
    day_end = target_date.replace(hour=BUSINESS_END_HOUR, minute=0, second=0, microsecond=0)
    if result:
        last_bid, last_bd = result[-1]
        last_time_str = last_bd.get('preferred_time', '09:00')
        try:
            last_start = datetime.strptime(f"{date_str} {last_time_str}", "%Y-%m-%d %H:%M")
            last_end = last_start + timedelta(minutes=get_job_duration_minutes(last_bd))
            if last_end > day_end:
                logger.warning(
                    f"Route optimiser: last job on {date_str} ends at "
                    f"{last_end.strftime('%H:%M')} — exceeds 5pm boundary"
                )
        except Exception:
            pass

    route_desc = " → ".join(
        bd.get('address') or bd.get('suburb', '?') for _, bd in result
    )
    logger.info(
        f"Optimal route {date_str}: base → {route_desc} → base  (~{best_cost} min travel)"
    )
    return result


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
    day_end = target_date.replace(hour=BUSINESS_END_HOUR, minute=0, second=0, microsecond=0)

    # Duration of the new job being scheduled
    new_job_duration = get_job_duration_minutes(new_booking_data or {})

    if not day_bookings:
        # First job of the day — measure travel from the business address
        travel_from_base = get_travel_minutes(BUSINESS_ADDRESS, new_address)
        first_start = _ceil_15(day_start + timedelta(minutes=travel_from_base))
        first_end = first_start + timedelta(minutes=new_job_duration)
        if first_end <= day_end:
            return target_date_str, first_start.strftime("%H:%M")
        # Doesn't fit today — fall through to "no room today"
    else:
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

        # Walk through the day looking for a gap.
        # Always start from the business address so the first job accounts for travel from base.
        prev_end = day_start
        prev_addr = BUSINESS_ADDRESS

        for job_start, job_end, job_addr in existing:
            # Earliest we can start the new job (travel from previous position, rounded up to :00/:15/:30/:45)
            travel_to_new = get_travel_minutes(prev_addr, new_address)
            earliest = _ceil_15(prev_end + timedelta(minutes=travel_to_new))
            new_job_end = earliest + timedelta(minutes=new_job_duration)

            # Travel from new job to the upcoming existing job
            travel_new_to_next = get_travel_minutes(new_address, job_addr) if (new_address and job_addr) else 30

            # Fits before this existing job AND ends by 5pm?
            if (new_job_end + timedelta(minutes=travel_new_to_next) <= job_start
                    and new_job_end <= day_end):
                return target_date_str, earliest.strftime("%H:%M")

            # Skip past this existing job
            prev_end = job_end
            prev_addr = job_addr

        # Try slotting after the last existing job
        travel_from_last = get_travel_minutes(prev_addr, new_address)
        candidate = _ceil_15(prev_end + timedelta(minutes=travel_from_last))
        candidate_end = candidate + timedelta(minutes=new_job_duration)

        if candidate_end <= day_end:
            return target_date_str, candidate.strftime("%H:%M")

    # No room today — move to next business day
    next_day = target_date + timedelta(days=1)
    while next_day.weekday() >= 5:
        next_day += timedelta(days=1)
    logger.info(f"No slot available on {target_date_str}, advancing to {next_day.strftime('%Y-%m-%d')}")
    return next_day.strftime("%Y-%m-%d"), day_start.strftime("%H:%M")
