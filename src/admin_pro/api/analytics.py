"""
admin_pro/api/analytics.py
Analytics endpoints for the Admin Pro dashboard.
"""

import json
import logging
from datetime import datetime, timedelta, timezone

from flask import request, jsonify

from state_manager import _get_conn

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Pricing table used by the revenue endpoint
# ---------------------------------------------------------------------------
PRICING = {
    "rim_repair": 180,
    "paint_touchup": 120,
    "multiple_rims": 320,
}

SERVICE_LABELS = {
    "rim_repair": "Wheel Doctor",
    "paint_touchup": "Paint Touch-up",
    "multiple_rims": "Multiple Rims",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_booking_data(raw):
    """Safely parse booking_data JSON; return empty dict on failure."""
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}


def _week_label(dt):
    """Return a human-readable 'Week of DD Mon' label for the Monday of the
    week that contains *dt*."""
    monday = dt - timedelta(days=dt.weekday())
    return monday.strftime("Week of %d %b")


# ---------------------------------------------------------------------------
# Endpoint implementations
# ---------------------------------------------------------------------------

def _overview():
    with _get_conn() as conn:
        # Total bookings and status breakdown
        rows = conn.execute(
            "SELECT status, COUNT(*) AS cnt FROM bookings GROUP BY status"
        ).fetchall()

        status_counts = {r["status"]: r["cnt"] for r in rows}
        total = sum(status_counts.values())
        confirmed = status_counts.get("confirmed", 0)
        declined = status_counts.get("declined", 0)
        # everything that is not confirmed or declined is considered pending
        pending = total - confirmed - declined

        conversion_rate = round((confirmed / total * 100), 2) if total else 0.0

        # Today's confirmed jobs (using preferred_date column)
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        today_jobs = conn.execute(
            "SELECT COUNT(*) FROM bookings WHERE status='confirmed' AND preferred_date=?",
            (today_str,),
        ).fetchone()[0]

        # This week's confirmed bookings (Mon–Sun of current UTC week)
        now = datetime.now(timezone.utc)
        week_start = (now - timedelta(days=now.weekday())).strftime("%Y-%m-%d")
        week_end = (now + timedelta(days=6 - now.weekday())).strftime("%Y-%m-%d")
        this_week_confirmed = conn.execute(
            """SELECT COUNT(*) FROM bookings
               WHERE status='confirmed'
               AND preferred_date >= ? AND preferred_date <= ?""",
            (week_start, week_end),
        ).fetchone()[0]

        # Average hours from created_at to confirmed_at
        time_rows = conn.execute(
            """SELECT created_at, confirmed_at FROM bookings
               WHERE status='confirmed'
               AND created_at IS NOT NULL AND confirmed_at IS NOT NULL"""
        ).fetchall()

        durations = []
        for r in time_rows:
            try:
                created = datetime.fromisoformat(r["created_at"].replace("Z", "+00:00"))
                confirmed_at = datetime.fromisoformat(r["confirmed_at"].replace("Z", "+00:00"))
                delta = (confirmed_at - created).total_seconds() / 3600
                if delta >= 0:
                    durations.append(delta)
            except (ValueError, AttributeError):
                pass

        avg_confirm_hours = round(sum(durations) / len(durations), 2) if durations else 0.0

        # Distinct customers by email
        total_customers = conn.execute(
            "SELECT COUNT(DISTINCT customer_email) FROM bookings WHERE customer_email IS NOT NULL"
        ).fetchone()[0]

    return jsonify({
        "total_bookings": total,
        "confirmed": confirmed,
        "declined": declined,
        "pending": pending,
        "conversion_rate": conversion_rate,
        "today_jobs": today_jobs,
        "this_week_confirmed": this_week_confirmed,
        "avg_confirm_hours": avg_confirm_hours,
        "total_customers": total_customers,
    })


def _trends():
    try:
        weeks = int(request.args.get("weeks", 8))
        if weeks < 1 or weeks > 52:
            weeks = 8
    except (ValueError, TypeError):
        weeks = 8

    now = datetime.now(timezone.utc)
    # Build bucket boundaries: [weeks] complete weeks, most recent last
    buckets = []
    for i in range(weeks - 1, -1, -1):
        # Monday of the week that was i weeks ago
        start_of_this_week = now - timedelta(days=now.weekday())
        bucket_monday = start_of_this_week - timedelta(weeks=i)
        bucket_monday = bucket_monday.replace(hour=0, minute=0, second=0, microsecond=0)
        bucket_sunday = bucket_monday + timedelta(days=6, hours=23, minutes=59, seconds=59)
        buckets.append((bucket_monday, bucket_sunday))

    with _get_conn() as conn:
        # Fetch all confirmed bookings with a preferred_date
        rows = conn.execute(
            """SELECT preferred_date FROM bookings
               WHERE status='confirmed' AND preferred_date IS NOT NULL"""
        ).fetchall()

    # Count per bucket
    counts = [0] * weeks
    for r in rows:
        try:
            bdate = datetime.strptime(r["preferred_date"], "%Y-%m-%d").replace(
                tzinfo=timezone.utc
            )
            for idx, (bstart, bend) in enumerate(buckets):
                if bstart <= bdate <= bend:
                    counts[idx] += 1
                    break
        except (ValueError, AttributeError):
            pass

    labels = [_week_label(start) for start, _ in buckets]

    return jsonify({"labels": labels, "counts": counts, "weeks": weeks})


def _funnel():
    with _get_conn() as conn:
        emails_received = conn.execute(
            "SELECT COUNT(*) FROM processed_emails"
        ).fetchone()[0]

        booking_extracted = conn.execute(
            "SELECT COUNT(*) FROM bookings"
        ).fetchone()[0]

        sent_to_owner = conn.execute(
            """SELECT COUNT(*) FROM bookings
               WHERE status IN ('awaiting_owner', 'confirmed', 'declined')"""
        ).fetchone()[0]

        confirmed = conn.execute(
            "SELECT COUNT(*) FROM bookings WHERE status='confirmed'"
        ).fetchone()[0]

    return jsonify({
        "stages": [
            {"label": "Emails Received", "count": emails_received},
            {"label": "Booking Extracted", "count": booking_extracted},
            {"label": "Sent to Owner", "count": sent_to_owner},
            {"label": "Confirmed", "count": confirmed},
        ]
    })


def _suburbs():
    with _get_conn() as conn:
        rows = conn.execute("SELECT booking_data FROM bookings").fetchall()

    suburb_counts = {}
    for r in rows:
        bd = _parse_booking_data(r["booking_data"])
        # Try several common field names for the location / suburb
        suburb = (
            bd.get("suburb")
            or bd.get("address_suburb")
            or bd.get("location_suburb")
            or ""
        )
        if not suburb:
            # Fall back to parsing suburb out of a full address string
            address = bd.get("address") or bd.get("location") or ""
            if address:
                # Use the last meaningful token before a postcode/state
                parts = [p.strip() for p in address.split(",") if p.strip()]
                suburb = parts[-1] if parts else ""

        if suburb:
            suburb = suburb.strip().title()
            suburb_counts[suburb] = suburb_counts.get(suburb, 0) + 1

    top10 = sorted(suburb_counts.items(), key=lambda x: x[1], reverse=True)[:10]
    return jsonify({"suburbs": [{"name": name, "count": cnt} for name, cnt in top10]})


def _services():
    with _get_conn() as conn:
        rows = conn.execute("SELECT booking_data FROM bookings").fetchall()

    service_counts = {}
    for r in rows:
        bd = _parse_booking_data(r["booking_data"])
        stype = bd.get("service_type") or "unknown"
        stype = stype.strip().lower()
        service_counts[stype] = service_counts.get(stype, 0) + 1

    services = [
        {
            "type": stype,
            "count": cnt,
            "label": SERVICE_LABELS.get(stype, stype.replace("_", " ").title()),
        }
        for stype, cnt in sorted(service_counts.items(), key=lambda x: x[1], reverse=True)
    ]

    return jsonify({"services": services})


def _revenue():
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT booking_data FROM bookings WHERE status='confirmed'"
        ).fetchall()

    by_service = {}
    for r in rows:
        bd = _parse_booking_data(r["booking_data"])
        stype = (bd.get("service_type") or "unknown").strip().lower()
        price = PRICING.get(stype, 0)
        if stype not in by_service:
            by_service[stype] = {"count": 0, "revenue": 0.0}
        by_service[stype]["count"] += 1
        by_service[stype]["revenue"] += price

    total_estimated = sum(v["revenue"] for v in by_service.values())

    by_service_list = [
        {
            "type": stype,
            "count": data["count"],
            "revenue": round(data["revenue"], 2),
        }
        for stype, data in sorted(
            by_service.items(), key=lambda x: x[1]["revenue"], reverse=True
        )
    ]

    return jsonify({
        "total_estimated": round(total_estimated, 2),
        "by_service": by_service_list,
        "currency": "AUD",
    })


def _heatmap():
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT booking_data, preferred_date FROM bookings"
        ).fetchall()

    # dow (0=Mon … 6=Sun), hour -> count
    freq = {}
    for r in rows:
        bd = _parse_booking_data(r["booking_data"])
        preferred_time = bd.get("preferred_time") or ""
        preferred_date = r["preferred_date"] or ""

        hour = None

        # Attempt to parse hour from preferred_time (e.g. "09:00", "9am", "14:30")
        if preferred_time:
            pt = preferred_time.strip()
            # Try HH:MM format
            try:
                hour = datetime.strptime(pt, "%H:%M").hour
            except ValueError:
                pass
            # Try H:MM
            if hour is None:
                try:
                    hour = datetime.strptime(pt, "%I:%M %p").hour
                except ValueError:
                    pass
            # Try am/pm shorthand: "9am", "2pm"
            if hour is None:
                pt_lower = pt.lower().replace(" ", "")
                try:
                    if pt_lower.endswith("am"):
                        hour = int(pt_lower[:-2]) % 12
                    elif pt_lower.endswith("pm"):
                        hour = (int(pt_lower[:-2]) % 12) + 12
                except (ValueError, AttributeError):
                    pass

        # Determine day-of-week from preferred_date
        dow = None
        if preferred_date:
            try:
                dow = datetime.strptime(preferred_date, "%Y-%m-%d").weekday()
            except ValueError:
                pass

        if dow is not None and hour is not None:
            key = (dow, hour)
            freq[key] = freq.get(key, 0) + 1

    data = [
        [dow, hour, count]
        for (dow, hour), count in sorted(freq.items())
    ]

    return jsonify({"data": data})


# ---------------------------------------------------------------------------
# Blueprint registration
# ---------------------------------------------------------------------------

def register(bp, require_auth):
    @bp.route("/api/analytics/overview", methods=["GET"])
    @require_auth
    def analytics_overview():
        try:
            return _overview()
        except Exception:
            logger.exception("analytics_overview error")
            return jsonify({"error": "Internal server error"}), 500

    @bp.route("/api/analytics/trends", methods=["GET"])
    @require_auth
    def analytics_trends():
        try:
            return _trends()
        except Exception:
            logger.exception("analytics_trends error")
            return jsonify({"error": "Internal server error"}), 500

    @bp.route("/api/analytics/funnel", methods=["GET"])
    @require_auth
    def analytics_funnel():
        try:
            return _funnel()
        except Exception:
            logger.exception("analytics_funnel error")
            return jsonify({"error": "Internal server error"}), 500

    @bp.route("/api/analytics/suburbs", methods=["GET"])
    @require_auth
    def analytics_suburbs():
        try:
            return _suburbs()
        except Exception:
            logger.exception("analytics_suburbs error")
            return jsonify({"error": "Internal server error"}), 500

    @bp.route("/api/analytics/services", methods=["GET"])
    @require_auth
    def analytics_services():
        try:
            return _services()
        except Exception:
            logger.exception("analytics_services error")
            return jsonify({"error": "Internal server error"}), 500

    @bp.route("/api/analytics/revenue", methods=["GET"])
    @require_auth
    def analytics_revenue():
        try:
            return _revenue()
        except Exception:
            logger.exception("analytics_revenue error")
            return jsonify({"error": "Internal server error"}), 500

    @bp.route("/api/analytics/heatmap", methods=["GET"])
    @require_auth
    def analytics_heatmap():
        try:
            return _heatmap()
        except Exception:
            logger.exception("analytics_heatmap error")
            return jsonify({"error": "Internal server error"}), 500


# Self-registration when imported by the admin_pro package
from admin_pro import admin_pro_bp, require_auth  # noqa: E402
register(admin_pro_bp, require_auth)
