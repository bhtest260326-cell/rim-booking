"""
admin_pro/api/route.py
Route optimization API endpoint for the admin pro dashboard.
"""

import json
import logging
import os
from datetime import datetime, timedelta

from flask import jsonify

from state_manager import StateManager, _get_conn

logger = logging.getLogger(__name__)

BUSINESS_ADDRESS = os.environ.get('BUSINESS_ADDRESS', '76 Albert St, Osborne Park WA 6017')
GOOGLE_MAPS_API_KEY = os.environ.get('GOOGLE_MAPS_API_KEY', '')


def register(bp, require_auth):
    """Register route optimization API endpoints on *bp*."""

    @bp.route('/api/route/<date>', methods=['GET'])
    @require_auth
    def get_route(date):
        """Return optimized route data for a given date.

        Response: {
            "date": "YYYY-MM-DD",
            "stops": [
                {
                    "booking_id": "...",
                    "address": "...",
                    "lat": N,
                    "lng": N,
                    "arrival_time": "HH:MM",
                    "service_type": "...",
                    "customer_name": "...",
                    "num_rims": N
                }
            ],
            "total_travel_minutes": N,
            "total_distance_km": N,
            "base_address": "...",
            "maps_api_key": "..."
        }
        """
        try:
            # Validate date format
            try:
                target_date = datetime.strptime(date, "%Y-%m-%d")
            except ValueError:
                return jsonify({'ok': False, 'error': 'Invalid date format. Use YYYY-MM-DD'}), 400

            # Get confirmed bookings for the date (with IDs)
            with _get_conn() as conn:
                rows = conn.execute(
                    "SELECT id, booking_data, customer_email FROM bookings "
                    "WHERE status='confirmed' AND preferred_date=?",
                    (date,)
                ).fetchall()

            if not rows:
                return jsonify({
                    'ok': True,
                    'date': date,
                    'stops': [],
                    'total_travel_minutes': 0,
                    'total_distance_km': 0,
                    'base_address': BUSINESS_ADDRESS,
                    'maps_api_key': GOOGLE_MAPS_API_KEY,
                })

            # Build booking list for route optimizer
            bookings_for_day = []
            for row in rows:
                try:
                    bd = json.loads(row['booking_data']) if row['booking_data'] else {}
                except (ValueError, TypeError):
                    bd = {}
                bookings_for_day.append((row['id'], bd))

            # Use the existing route optimizer from maps_handler
            from maps_handler import (
                find_optimal_route,
                get_distance_matrix,
                get_job_duration_minutes,
                BUSINESS_START_HOUR,
            )

            # Try to get optimized order
            optimized = find_optimal_route(bookings_for_day, date)

            if optimized:
                ordered = optimized
            else:
                # Single booking or no API key - use original order sorted by time
                ordered = sorted(
                    bookings_for_day,
                    key=lambda x: x[1].get('preferred_time', '09:00')
                )

            # Build the addresses list for distance calculation
            addresses = [BUSINESS_ADDRESS]
            for bid, bd in ordered:
                addresses.append(bd.get('address') or bd.get('suburb') or BUSINESS_ADDRESS)

            # Get distance matrix for travel time calculation
            matrix = get_distance_matrix(addresses)

            # Build stops list with travel times
            stops = []
            total_travel = 0
            prev_idx = 0

            for i, (bid, bd) in enumerate(ordered):
                addr_idx = i + 1
                travel_min = matrix[prev_idx][addr_idx]
                total_travel += travel_min

                address = bd.get('address') or bd.get('suburb') or ''
                stops.append({
                    'booking_id': bid,
                    'address': address,
                    'lat': bd.get('lat', 0),
                    'lng': bd.get('lng', 0),
                    'arrival_time': bd.get('preferred_time', ''),
                    'service_type': bd.get('service_type', ''),
                    'customer_name': bd.get('customer_name') or bd.get('name', ''),
                    'num_rims': bd.get('num_rims', ''),
                    'travel_from_prev': travel_min,
                    'job_duration': get_job_duration_minutes(bd),
                })

                prev_idx = addr_idx

            # Add return travel to base
            if ordered:
                return_travel = matrix[prev_idx][0]
                total_travel += return_travel

            # Estimate total distance (rough: 1 km per minute of driving in metro)
            total_distance_km = round(total_travel * 0.9, 1)

            return jsonify({
                'ok': True,
                'date': date,
                'stops': stops,
                'total_travel_minutes': total_travel,
                'total_distance_km': total_distance_km,
                'base_address': BUSINESS_ADDRESS,
                'maps_api_key': GOOGLE_MAPS_API_KEY,
            })

        except Exception:
            logger.exception("get_route failed for date %s", date)
            return jsonify({'ok': False, 'error': 'Internal server error'}), 500


# ---------------------------------------------------------------------------
# Self-registration
# ---------------------------------------------------------------------------
from admin_pro import admin_pro_bp, require_auth  # noqa: E402
register(admin_pro_bp, require_auth)
