import os
import logging
import math
import time
import datetime as _dt_mod
import requests
from datetime import datetime, timedelta
from itertools import permutations as _perms

logger = logging.getLogger(__name__)

# WA Public Holidays — update annually
_WA_PUBLIC_HOLIDAYS: set = {
    # 2026
    _dt_mod.date(2026, 1, 1),   # New Year's Day
    _dt_mod.date(2026, 1, 26),  # Australia Day
    _dt_mod.date(2026, 3, 2),   # Labour Day (WA)
    _dt_mod.date(2026, 4, 3),   # Good Friday
    _dt_mod.date(2026, 4, 4),   # Easter Saturday
    _dt_mod.date(2026, 4, 6),   # Easter Monday
    _dt_mod.date(2026, 4, 25),  # Anzac Day
    _dt_mod.date(2026, 6, 1),   # WA Day
    _dt_mod.date(2026, 9, 28),  # Queen's Birthday (WA)
    _dt_mod.date(2026, 12, 25), # Christmas Day
    _dt_mod.date(2026, 12, 26), # Boxing Day
    # 2027
    _dt_mod.date(2027, 1, 1),   # New Year's Day
    _dt_mod.date(2027, 1, 26),  # Australia Day
    _dt_mod.date(2027, 3, 1),   # Labour Day (WA)
    _dt_mod.date(2027, 3, 26),  # Good Friday
    _dt_mod.date(2027, 3, 27),  # Easter Saturday
    _dt_mod.date(2027, 3, 29),  # Easter Monday
    _dt_mod.date(2027, 4, 26),  # Anzac Day (observed)
    _dt_mod.date(2027, 6, 7),   # WA Day
    _dt_mod.date(2027, 9, 27),  # Queen's Birthday (WA)
    _dt_mod.date(2027, 12, 25), # Christmas Day
    _dt_mod.date(2027, 12, 27), # Boxing Day (observed)
    # 2028
    _dt_mod.date(2028, 1, 3),   # New Year's Day (observed, 1st is Saturday)
    _dt_mod.date(2028, 1, 26),  # Australia Day
    _dt_mod.date(2028, 4, 14),  # Good Friday
    _dt_mod.date(2028, 4, 15),  # Easter Saturday
    _dt_mod.date(2028, 4, 17),  # Easter Monday
    _dt_mod.date(2028, 4, 25),  # Anzac Day
    _dt_mod.date(2028, 6, 5),   # WA Day
    _dt_mod.date(2028, 9, 25),  # King's Birthday (WA)
    _dt_mod.date(2028, 12, 25), # Christmas Day
    _dt_mod.date(2028, 12, 26), # Boxing Day
    # 2029
    _dt_mod.date(2029, 1, 1),   # New Year's Day
    _dt_mod.date(2029, 1, 28),  # Australia Day (observed, 26th is Saturday)
    _dt_mod.date(2029, 3, 30),  # Good Friday
    _dt_mod.date(2029, 3, 31),  # Easter Saturday
    _dt_mod.date(2029, 4, 2),   # Easter Monday
    _dt_mod.date(2029, 4, 25),  # Anzac Day
    _dt_mod.date(2029, 6, 4),   # WA Day
    _dt_mod.date(2029, 9, 24),  # King's Birthday (WA)
    _dt_mod.date(2029, 12, 25), # Christmas Day
    _dt_mod.date(2029, 12, 26), # Boxing Day
    # 2030
    _dt_mod.date(2030, 1, 1),   # New Year's Day
    _dt_mod.date(2030, 1, 28),  # Australia Day (observed, 26th is Saturday)
    _dt_mod.date(2030, 4, 19),  # Good Friday
    _dt_mod.date(2030, 4, 20),  # Easter Saturday
    _dt_mod.date(2030, 4, 22),  # Easter Monday
    _dt_mod.date(2030, 4, 25),  # Anzac Day
    _dt_mod.date(2030, 6, 3),   # WA Day
    _dt_mod.date(2030, 9, 23),  # King's Birthday (WA)
    _dt_mod.date(2030, 12, 25), # Christmas Day
    _dt_mod.date(2030, 12, 26), # Boxing Day
}


def _is_business_day(d: _dt_mod.date) -> bool:
    """Return True if d is a weekday that is not a WA public holiday."""
    return d.weekday() < 5 and d not in _WA_PUBLIC_HOLIDAYS


def _ceil_15(dt):
    """Round a datetime UP to the next 15-minute boundary (e.g. 11:44 → 11:45, 11:46 → 12:00).
    If already on a 15-minute boundary with no seconds, returns unchanged."""
    remainder = dt.minute % 15
    if remainder == 0 and dt.second == 0 and dt.microsecond == 0:
        return dt
    if remainder == 0:
        # On boundary but has sub-minute time — just clear seconds, don't advance
        return dt.replace(second=0, microsecond=0)
    add_minutes = 15 - remainder
    return (dt + timedelta(minutes=add_minutes)).replace(second=0, microsecond=0)

GOOGLE_MAPS_API_KEY = os.environ.get('GOOGLE_MAPS_API_KEY', '')
BUSINESS_ADDRESS = os.environ.get('BUSINESS_ADDRESS', '76 Albert St, Osborne Park WA 6017')
BUSINESS_START_HOUR = int(os.environ.get('WORK_START_HOUR', '8'))   # default 8:00 AM
BUSINESS_END_HOUR   = int(os.environ.get('WORK_END_HOUR',   '17'))  # default 5:00 PM
TRAVEL_BUFFER_MINUTES = 10  # padding added on top of Maps estimate

# Job duration table (minutes) keyed by number of rims
_RIM_DURATION: dict[int, int] = {1: 120, 2: 180, 3: 240, 4: 300}
_DEFAULT_DURATION = 120  # fallback when rim count unknown

# Distance matrix in-memory cache
_matrix_cache: dict = {}       # key -> matrix
_matrix_cache_ts: dict = {}    # key -> float timestamp
_MATRIX_CACHE_TTL = 1800       # 30 minutes

# Week availability in-memory cache
_avail_cache: dict = {}
_avail_cache_ts: dict = {}
_AVAIL_CACHE_TTL = 300  # 5 minutes

# Known out-of-area Western Australian locations (outside Perth metro)
_OUT_OF_AREA_KEYWORDS = [
    'mandurah', 'bunbury', 'busselton', 'margaret river', 'geraldton',
    'albany', 'kalgoorlie', 'boulder', 'broome', 'port hedland',
    'karratha', 'newman', 'esperance', 'merredin', 'northam',
    'york', 'narrogin', 'collie', 'harvey', 'waroona',
    'pinjarra', 'dwellingup', 'mundaring', 'toodyay',
]


def is_within_service_area(address: str) -> bool:
    """Return True if address appears to be within Perth metropolitan area.

    Returns True by default (accept bookings) — only rejects clearly regional WA addresses.
    """
    if not address:
        return True
    lower = address.lower()
    for kw in _OUT_OF_AREA_KEYWORDS:
        if kw in lower:
            logger.info(f"Service area check: '{address}' matches out-of-area keyword '{kw}'")
            return False
    return True


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


def get_travel_minutes(origin: str, destination: str, departure_dt=None) -> int:
    """Return driving time in minutes between two addresses.

    Appends ', Perth WA, Australia' to help Maps disambiguate suburb-only addresses.
    Falls back to 30 minutes if the API key is missing or the call fails.

    Args:
        origin:       origin address string.
        destination:  destination address string.
        departure_dt: optional timezone-naive datetime (Perth local time) representing
                      when travel begins.  When provided, the Distance Matrix API is
                      queried with departure_time and traffic_model='best_guess' so
                      that real traffic conditions are reflected in the estimate.
                      The cache key is bucketed to the nearest 15-minute interval to
                      avoid a cache miss on every call while still being traffic-aware.
    """
    if not GOOGLE_MAPS_API_KEY:
        logger.debug("GOOGLE_MAPS_API_KEY not set — using 30 min default travel time")
        return 30

    if not origin or not destination:
        return 30

    # Round departure to nearest 15-min bucket for cache key
    if departure_dt is not None:
        rounded_min = (departure_dt.minute // 15) * 15
        dep_key = departure_dt.strftime(f'%Y%m%d%H') + f'{rounded_min:02d}'
    else:
        dep_key = 'nodep'
    cache_key = (origin.lower().strip(), destination.lower().strip(), dep_key)

    try:
        params = {
            'origins': f"{origin}, Perth WA, Australia",
            'destinations': f"{destination}, Perth WA, Australia",
            'key': GOOGLE_MAPS_API_KEY,
            'mode': 'driving',
            'region': 'au',
        }
        if departure_dt is not None:
            try:
                import calendar as _cal
                # departure_dt is Perth local time (UTC+8, naive).
                # timegm() interprets its input as UTC, so subtract 8h first.
                utc_dt = departure_dt - timedelta(hours=8)
                params['departure_time'] = str(int(_cal.timegm(utc_dt.timetuple())))
                params['traffic_model'] = 'best_guess'
            except Exception:
                pass  # fall back to no traffic data
        try:
            resp = requests.get(
                "https://maps.googleapis.com/maps/api/distancematrix/json",
                params=params,
                timeout=10
            )
        except requests.exceptions.Timeout:
            logger.warning("Google Maps API timeout after 10s — using fallback travel time of 30 min")
            return 30
        except requests.exceptions.RequestException as e:
            logger.warning(f"Google Maps API request error: {e} — using fallback")
            return 30
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

        element = elements[0]
        # Prefer traffic-aware duration when departure_time was supplied
        duration_field = (
            element.get('duration_in_traffic') or element.get('duration')
        )
        travel_min = int(duration_field['value'] / 60) + TRAVEL_BUFFER_MINUTES
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

    # Cache key must preserve address order — the returned matrix is position-indexed.
    # sorted() was wrong: ['A','B'] and ['B','A'] would share a cache entry but need different matrices.
    key = tuple(addresses)
    if key in _matrix_cache and time.time() - _matrix_cache_ts.get(key, 0) < _MATRIX_CACHE_TTL:
        logger.info(f"Distance matrix cache hit ({n} locations)")
        return _matrix_cache[key]

    try:
        addrs_ctx = [f"{a}, Perth WA, Australia" for a in addresses]
        try:
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
        except requests.exceptions.Timeout:
            logger.warning("Google Maps API timeout after 15s — using fallback travel time of 30 min")
            return fallback
        except requests.exceptions.RequestException as e:
            logger.warning(f"Google Maps API request error: {e} — using fallback")
            return fallback
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

        _matrix_cache[key] = matrix
        _matrix_cache_ts[key] = time.time()
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


def _perth_now_local():
    """Return current datetime in Perth time (UTC+8) without pytz dependency."""
    return datetime.utcnow() + timedelta(hours=8)


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

    # Advance past weekends and WA public holidays
    while not _is_business_day(target_date.date()):
        target_date += timedelta(days=1)
    target_date_str = target_date.strftime("%Y-%m-%d")

    day_start = target_date.replace(hour=BUSINESS_START_HOUR, minute=0, second=0, microsecond=0)
    day_end = target_date.replace(hour=BUSINESS_END_HOUR, minute=0, second=0, microsecond=0)

    # Duration of the new job being scheduled
    new_job_duration = get_job_duration_minutes(new_booking_data or {})

    if not day_bookings:
        # First job of the day — measure travel from the business address
        travel_from_base = get_travel_minutes(BUSINESS_ADDRESS, new_address,
                                              departure_dt=day_start)
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
            travel_to_new = get_travel_minutes(prev_addr, new_address,
                                               departure_dt=prev_end)
            earliest = _ceil_15(prev_end + timedelta(minutes=travel_to_new))
            new_job_end = earliest + timedelta(minutes=new_job_duration)

            # Travel from new job to the upcoming existing job
            travel_new_to_next = (
                get_travel_minutes(new_address, job_addr, departure_dt=new_job_end)
                if (new_address and job_addr) else 30
            )

            # Fits before this existing job AND ends by 5pm?
            if (new_job_end + timedelta(minutes=travel_new_to_next) <= job_start
                    and new_job_end <= day_end):
                return target_date_str, earliest.strftime("%H:%M")

            # Skip past this existing job
            prev_end = job_end
            prev_addr = job_addr

        # Try slotting after the last existing job
        travel_from_last = get_travel_minutes(prev_addr, new_address,
                                              departure_dt=prev_end)
        candidate = _ceil_15(prev_end + timedelta(minutes=travel_from_last))
        candidate_end = candidate + timedelta(minutes=new_job_duration)

        if candidate_end <= day_end:
            return target_date_str, candidate.strftime("%H:%M")

    # No room today — move to next business day (skipping weekends and WA public holidays)
    next_day = target_date + timedelta(days=1)
    while not _is_business_day(next_day.date()):
        next_day += timedelta(days=1)
    logger.info(f"No slot available on {target_date_str}, advancing to {next_day.strftime('%Y-%m-%d')}")
    return next_day.strftime("%Y-%m-%d"), day_start.strftime("%H:%M")


def get_week_availability(duration_minutes: int, from_date_str: str = None,
                          assumed_travel_minutes: int = 25, num_days: int = 10) -> list:
    """Check availability for the next 5 business days.

    For each day, determines whether a contiguous block of `duration_minutes`
    can be fitted within business hours (8am–5pm) given existing confirmed bookings.
    An assumed travel time is added to each gap's required size to avoid offering
    slots that would not survive real routing:

    - Empty day:              duration + assumed_travel_minutes * 2
                              (travel to job from base, then back to base)
    - Gap before first job:   duration + assumed_travel_minutes
                              (travel from base to new job)
    - Gap between two jobs:   duration + assumed_travel_minutes * 2
                              (travel from prev job to new job, then new job to next job)
    - Gap after last job:     duration + assumed_travel_minutes
                              (travel from last job to new job)

    Args:
        duration_minutes:       required job duration in minutes.
        from_date_str:          'YYYY-MM-DD' to start from (defaults to today Perth time).
        assumed_travel_minutes: assumed one-way travel time in minutes (default 25).

    Returns:
        List of dicts, one per business day:
            {'date': 'YYYY-MM-DD', 'day_name': 'Monday', 'available': True/False}
    """
    import time as _t
    _avail_key = (duration_minutes, from_date_str or 'today')
    if _avail_key in _avail_cache:
        if _t.time() - _avail_cache_ts.get(_avail_key, 0) < _AVAIL_CACHE_TTL:
            logger.debug(f"Availability cache hit for {_avail_key}")
            return _avail_cache[_avail_key]

    from state_manager import StateManager

    if from_date_str:
        try:
            start = datetime.strptime(from_date_str, '%Y-%m-%d')
        except ValueError:
            start = _perth_now_local().replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        start = _perth_now_local().replace(hour=0, minute=0, second=0, microsecond=0)

    # Collect next N business days (Mon–Fri, excluding WA public holidays)
    business_days = []
    cursor = start
    while len(business_days) < num_days:
        if _is_business_day(cursor.date()):
            business_days.append(cursor)
        cursor += timedelta(days=1)

    state = StateManager()

    day_start_hour = BUSINESS_START_HOUR   # 8
    day_end_hour   = BUSINESS_END_HOUR     # 17

    def _check_days(days_list):
        """Compute availability for a list of day datetimes, return list of result dicts."""
        out = []
        for day in days_list:
            date_str  = day.strftime('%Y-%m-%d')
            day_name  = day.strftime('%A')
            day_start = day.replace(hour=day_start_hour, minute=0, second=0, microsecond=0)
            day_end   = day.replace(hour=day_end_hour,   minute=0, second=0, microsecond=0)

            existing_bookings = state.get_confirmed_bookings_for_date(date_str)

            if not existing_bookings:
                # Empty day — must account for travel to job and back to base
                required = duration_minutes + assumed_travel_minutes * 2
                available = required <= (day_end_hour - day_start_hour) * 60
            else:
                # Build sorted (start, end) intervals for confirmed jobs
                intervals = []
                for bd in existing_bookings:
                    t = bd.get('preferred_time') or '09:00'
                    try:
                        job_start = datetime.strptime(f"{date_str} {t}", "%Y-%m-%d %H:%M")
                    except ValueError:
                        continue
                    job_end = job_start + timedelta(minutes=get_job_duration_minutes(bd))
                    intervals.append((job_start, job_end))
                intervals.sort(key=lambda x: x[0])

                # Walk gaps: tag each with its position so travel overhead is applied correctly.
                # gap type: 'before_first' | 'between' | 'after_last'
                available = False
                gaps = []  # list of (gap_start, gap_end, gap_type)
                prev_end = day_start

                for i, (job_start, job_end) in enumerate(intervals):
                    if job_start > prev_end:
                        gap_type = 'before_first' if i == 0 else 'between'
                        gaps.append((prev_end, job_start, gap_type))
                    prev_end = max(prev_end, job_end)

                # Gap after last job
                if day_end > prev_end:
                    gaps.append((prev_end, day_end, 'after_last'))

                for gap_start, gap_end, gap_type in gaps:
                    gap_minutes = (gap_end - gap_start).total_seconds() / 60

                    # Travel overhead depends on position in the day
                    if gap_type == 'before_first':
                        # Travel from base to new job only (next job follows immediately after)
                        travel_overhead = assumed_travel_minutes
                    elif gap_type == 'between':
                        # Travel from previous job to new job, then from new job to next job
                        travel_overhead = assumed_travel_minutes * 2
                    else:  # after_last
                        # Travel from last job to new job (no following job to travel to)
                        travel_overhead = assumed_travel_minutes

                    required = duration_minutes + travel_overhead
                    if gap_minutes >= required:
                        available = True
                        break

            out.append({'date': date_str, 'day_name': day_name, 'available': available})
        return out

    result = _check_days(business_days)

    # If none of the 10 days are available, also check the following 5 business days
    if not any(s['available'] for s in result):
        next_business_days = []
        while len(next_business_days) < 5:
            if _is_business_day(cursor.date()):
                next_business_days.append(cursor)
            cursor += timedelta(days=1)
        result.extend(_check_days(next_business_days))

    _avail_cache[_avail_key] = result
    _avail_cache_ts[_avail_key] = _t.time()

    return result
