"""
admin_pro/api/bookings.py
Booking CRUD API endpoints for the admin pro dashboard.
"""

import json
import logging
from datetime import datetime, timezone, timedelta

from flask import request, jsonify

from state_manager import StateManager, _get_conn

logger = logging.getLogger(__name__)

# Allowlist of valid booking data field names
_ALLOWED_BOOKING_FIELDS = {
    'customer_name', 'customer_email', 'customer_phone', 'vehicle_make',
    'vehicle_model', 'vehicle_colour', 'service_type', 'num_rims',
    'preferred_date', 'preferred_time', 'address', 'suburb', 'notes',
    'confidence', 'address_notes', 'missing_fields', 'name', 'phone',
    '_confirmation_pin',
}


def _validate_booking_data(data: dict) -> str | None:
    """Validate booking data fields. Returns error message or None if valid."""
    if not isinstance(data, dict):
        return "booking_data must be an object"
    invalid_keys = set(data.keys()) - _ALLOWED_BOOKING_FIELDS
    if invalid_keys:
        return f"Invalid fields: {sorted(invalid_keys)}"
    for k, v in data.items():
        if isinstance(v, str) and len(v) > 500:
            return f"Field '{k}' exceeds maximum length of 500 characters"
    return None


# ---------------------------------------------------------------------------
# Customer notification helper
# ---------------------------------------------------------------------------

def _notify_customer_confirmed(booking_id, booking_data, customer_email, thread_id):
    """Send SMS and/or email confirmation to the customer after admin confirms.

    Mirrors the notification logic in twilio_handler.handle_owner_confirm so
    that every confirmation path notifies the customer consistently.
    Returns a dict with keys 'sms_sent' and 'email_sent' for logging.
    """
    from feature_flags import get_flag

    sms_sent = False
    email_sent = False

    customer_phone = booking_data.get('customer_phone')

    if customer_phone and get_flag('flag_auto_sms_customer'):
        try:
            from twilio_handler import send_sms, build_customer_confirmation_sms
            msg = build_customer_confirmation_sms(booking_data)
            send_sms(customer_phone, msg)
            sms_sent = True
        except Exception:
            logger.exception("_notify_customer_confirmed: SMS failed for booking %s", booking_id)

    if customer_email and get_flag('flag_auto_email_customer'):
        try:
            from twilio_handler import send_confirmation_email
            send_confirmation_email(customer_email, booking_data, booking_id=booking_id, thread_id=thread_id)
            email_sent = True
        except Exception:
            logger.exception("_notify_customer_confirmed: email failed for booking %s", booking_id)

    return {'sms_sent': sms_sent, 'email_sent': email_sent}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _row_to_dict(row):
    """Convert a sqlite3.Row to a plain dict with booking_data parsed."""
    d = dict(row)
    raw = d.get('booking_data')
    if raw:
        try:
            d['booking_data'] = json.loads(raw)
        except (ValueError, TypeError):
            d['booking_data'] = {}
    else:
        d['booking_data'] = {}
    return d


def _event_row_to_dict(row):
    """Convert a booking_events sqlite3.Row to a plain dict."""
    d = dict(row)
    raw = d.get('details')
    if raw:
        try:
            d['details'] = json.loads(raw)
        except (ValueError, TypeError):
            d['details'] = {}
    else:
        d['details'] = None
    return d


def _week_bounds():
    """Return ISO strings for start and end of the current calendar week (Mon–Sun)."""
    today = datetime.now(timezone.utc).date()
    start = today - timedelta(days=today.weekday())          # Monday
    end = start + timedelta(days=6)                          # Sunday
    return start.isoformat(), end.isoformat()


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def register(bp, require_auth):
    """Register all booking API routes on *bp* using *require_auth* decorator."""

    # ------------------------------------------------------------------
    # GET /api/bookings — paginated list with optional filters
    # ------------------------------------------------------------------
    @bp.route('/api/bookings', methods=['GET'])
    @require_auth
    def list_bookings():
        try:
            status = request.args.get('status', 'all')
            date_from = request.args.get('date_from')
            date_to = request.args.get('date_to')
            search = request.args.get('search', '').strip()

            try:
                page = max(1, int(request.args.get('page', 1)))
            except (ValueError, TypeError):
                page = 1

            try:
                per_page = min(100, max(1, int(request.args.get('per_page', 25))))
            except (ValueError, TypeError):
                per_page = 25

            conditions = []
            params = []

            if status and status != 'all':
                conditions.append("status = ?")
                params.append(status)

            if date_from:
                conditions.append("preferred_date >= ?")
                params.append(date_from)

            if date_to:
                conditions.append("preferred_date <= ?")
                params.append(date_to)

            if search:
                like = f"%{search}%"
                conditions.append(
                    "(customer_email LIKE ? "
                    " OR JSON_EXTRACT(booking_data, '$.name') LIKE ?"
                    " OR JSON_EXTRACT(booking_data, '$.suburb') LIKE ?"
                    " OR JSON_EXTRACT(booking_data, '$.customer_name') LIKE ?)"
                )
                params.extend([like, like, like, like])

            where_clause = ("WHERE " + " AND ".join(conditions)) if conditions else ""

            count_sql = f"SELECT COUNT(*) AS cnt FROM bookings {where_clause}"
            list_sql = (
                f"SELECT * FROM bookings {where_clause} "
                f"ORDER BY created_at DESC "
                f"LIMIT ? OFFSET ?"
            )

            offset = (page - 1) * per_page

            with _get_conn() as conn:
                total = conn.execute(count_sql, params).fetchone()['cnt']
                rows = conn.execute(list_sql, params + [per_page, offset]).fetchall()

            bookings = [_row_to_dict(r) for r in rows]
            pages = max(1, (total + per_page - 1) // per_page)

            return jsonify({
                'bookings': bookings,
                'total': total,
                'page': page,
                'pages': pages,
            })

        except Exception:
            logger.exception("list_bookings failed")
            return jsonify({'ok': False, 'error': 'Internal server error'}), 500

    # ------------------------------------------------------------------
    # GET /api/bookings/stats
    # ------------------------------------------------------------------
    @bp.route('/api/bookings/stats', methods=['GET'])
    @require_auth
    def booking_stats():
        try:
            today = datetime.now(timezone.utc).date().isoformat()
            week_start, week_end = _week_bounds()

            with _get_conn() as conn:
                def count(sql, p=()):
                    row = conn.execute(sql, p).fetchone()
                    return row[0] if row else 0

                awaiting = count(
                    "SELECT COUNT(*) FROM bookings WHERE status='awaiting_owner'"
                )
                confirmed = count(
                    "SELECT COUNT(*) FROM bookings WHERE status='confirmed'"
                )
                declined = count(
                    "SELECT COUNT(*) FROM bookings WHERE status='declined'"
                )
                total = count("SELECT COUNT(*) FROM bookings")
                today_count = count(
                    "SELECT COUNT(*) FROM bookings "
                    "WHERE substr(preferred_date,1,10)=? "
                    "AND status IN ('confirmed','awaiting_owner')",
                    (today,)
                )
                week_count = count(
                    "SELECT COUNT(*) FROM bookings "
                    "WHERE substr(preferred_date,1,10) >= ? "
                    "AND substr(preferred_date,1,10) <= ? "
                    "AND status IN ('confirmed','awaiting_owner')",
                    (week_start, week_end)
                )

            return jsonify({
                'awaiting_owner': awaiting,
                'confirmed': confirmed,
                'declined': declined,
                'total': total,
                'today': today_count,
                'this_week': week_count,
            })

        except Exception:
            logger.exception("booking_stats failed")
            return jsonify({'ok': False, 'error': 'Internal server error'}), 500

    # ------------------------------------------------------------------
    # GET /api/bookings/<booking_id> — single booking with events
    # ------------------------------------------------------------------
    @bp.route('/api/bookings/<booking_id>', methods=['GET'])
    @require_auth
    def get_booking(booking_id):
        try:
            with _get_conn() as conn:
                row = conn.execute(
                    "SELECT * FROM bookings WHERE id=?", (booking_id,)
                ).fetchone()

                if not row:
                    return jsonify({'ok': False, 'error': 'Booking not found'}), 404

                booking = _row_to_dict(row)

                event_rows = conn.execute(
                    "SELECT * FROM booking_events WHERE booking_id=? ORDER BY created_at ASC",
                    (booking_id,)
                ).fetchall()

            booking['events'] = [_event_row_to_dict(e) for e in event_rows]
            return jsonify({'ok': True, 'booking': booking})

        except Exception:
            logger.exception("get_booking failed for %s", booking_id)
            return jsonify({'ok': False, 'error': 'Internal server error'}), 500

    # ------------------------------------------------------------------
    # GET /api/bookings/<booking_id>/events — audit trail only
    # ------------------------------------------------------------------
    @bp.route('/api/bookings/<booking_id>/events', methods=['GET'])
    @require_auth
    def get_booking_events(booking_id):
        try:
            with _get_conn() as conn:
                # Verify the booking exists first
                exists = conn.execute(
                    "SELECT 1 FROM bookings WHERE id=?", (booking_id,)
                ).fetchone()
                if not exists:
                    return jsonify({'ok': False, 'error': 'Booking not found'}), 404

                event_rows = conn.execute(
                    "SELECT id, event_type, actor, details, created_at "
                    "FROM booking_events WHERE booking_id=? ORDER BY created_at ASC",
                    (booking_id,)
                ).fetchall()

            events = [_event_row_to_dict(e) for e in event_rows]
            return jsonify({'events': events})

        except Exception:
            logger.exception("get_booking_events failed for %s", booking_id)
            return jsonify({'ok': False, 'error': 'Internal server error'}), 500

    # ------------------------------------------------------------------
    # POST /api/bookings/<booking_id>/confirm
    # ------------------------------------------------------------------
    @bp.route('/api/bookings/<booking_id>/confirm', methods=['POST'])
    @require_auth
    def confirm_booking(booking_id):
        try:
            state = StateManager()

            # Fetch current booking_data so we can pass it through
            with _get_conn() as conn:
                row = conn.execute(
                    "SELECT booking_data, status, customer_email, thread_id FROM bookings WHERE id=?",
                    (booking_id,)
                ).fetchone()

            if not row:
                return jsonify({'ok': False, 'error': 'Booking not found'}), 404

            if row['status'] != 'awaiting_owner':
                return jsonify({
                    'ok': False,
                    'error': f"Booking is in '{row['status']}' state, not awaiting_owner"
                }), 409

            try:
                booking_data = json.loads(row['booking_data']) if row['booking_data'] else {}
            except (ValueError, TypeError):
                booking_data = {}

            # Allow caller to supply updated booking_data in the request body
            body = request.get_json(silent=True) or {}
            if body.get('booking_data'):
                err = _validate_booking_data(body['booking_data'])
                if err:
                    return jsonify({'ok': False, 'error': err}), 400
                booking_data.update(body['booking_data'])

            success = state.confirm_booking(booking_id, booking_data)
            if not success:
                return jsonify({'ok': False, 'error': 'Could not confirm booking (possible time conflict or state error)'}), 409

            # Notify customer (SMS and/or email) now that the booking is confirmed
            customer_email = row['customer_email'] or booking_data.get('customer_email')
            thread_id = row['thread_id']

            notif = _notify_customer_confirmed(booking_id, booking_data, customer_email, thread_id)

            state.log_booking_event(
                booking_id, 'confirmed', actor='owner_ui',
                details={
                    'triggered_by': 'admin_dashboard',
                    'customer_notified_sms': notif['sms_sent'],
                    'customer_notified_email': notif['email_sent'],
                }
            )
            logger.info("Admin confirmed booking %s (sms=%s email=%s)", booking_id, notif['sms_sent'], notif['email_sent'])
            return jsonify({'ok': True})

        except Exception:
            logger.exception("confirm_booking failed for %s", booking_id)
            return jsonify({'ok': False, 'error': 'Internal server error'}), 500

    # ------------------------------------------------------------------
    # POST /api/bookings/<booking_id>/decline
    # ------------------------------------------------------------------
    @bp.route('/api/bookings/<booking_id>/decline', methods=['POST'])
    @require_auth
    def decline_booking(booking_id):
        try:
            body = request.get_json(silent=True) or {}
            reason = body.get('reason', '')

            state = StateManager()

            with _get_conn() as conn:
                row = conn.execute(
                    "SELECT status FROM bookings WHERE id=?", (booking_id,)
                ).fetchone()

            if not row:
                return jsonify({'ok': False, 'error': 'Booking not found'}), 404

            if row['status'] != 'awaiting_owner':
                return jsonify({
                    'ok': False,
                    'error': f"Booking is in '{row['status']}' state, not awaiting_owner"
                }), 409

            success = state.decline_booking(booking_id)
            if not success:
                return jsonify({'ok': False, 'error': 'Could not decline booking'}), 409

            details = {'triggered_by': 'admin_dashboard'}
            if reason:
                details['reason'] = reason

            state.log_booking_event(
                booking_id, 'declined', actor='owner_ui', details=details
            )
            logger.info("Admin declined booking %s (reason: %s)", booking_id, reason or 'none')
            return jsonify({'ok': True})

        except Exception:
            logger.exception("decline_booking failed for %s", booking_id)
            return jsonify({'ok': False, 'error': 'Internal server error'}), 500

    # ------------------------------------------------------------------
    # POST /api/bookings/<booking_id>/edit
    # ------------------------------------------------------------------
    @bp.route('/api/bookings/<booking_id>/edit', methods=['POST'])
    @require_auth
    def edit_booking(booking_id):
        try:
            body = request.get_json(silent=True) or {}
            if not body:
                return jsonify({'ok': False, 'error': 'Request body is required'}), 400

            state = StateManager()

            with _get_conn() as conn:
                row = conn.execute(
                    "SELECT booking_data, status FROM bookings WHERE id=?",
                    (booking_id,)
                ).fetchone()

            if not row:
                return jsonify({'ok': False, 'error': 'Booking not found'}), 404

            status = row['status']

            try:
                existing_data = json.loads(row['booking_data']) if row['booking_data'] else {}
            except (ValueError, TypeError):
                existing_data = {}

            # Validate and merge incoming fields
            err = _validate_booking_data(body)
            if err:
                return jsonify({'ok': False, 'error': err}), 400
            merged = {**existing_data, **body}

            if status == 'awaiting_owner':
                state.update_pending_booking_data(booking_id, merged)
            elif status == 'confirmed':
                state.update_confirmed_booking_data(booking_id, merged)
            else:
                # For declined or other statuses, perform a raw update
                with _get_conn() as conn:
                    conn.execute(
                        "UPDATE bookings SET booking_data=?, preferred_date=? WHERE id=?",
                        (
                            json.dumps(merged),
                            merged.get('preferred_date'),
                            booking_id,
                        )
                    )

            state.log_booking_event(
                booking_id, 'data_updated', actor='owner_ui',
                details={'updated_fields': list(body.keys())}
            )
            logger.info("Admin edited booking %s fields: %s", booking_id, list(body.keys()))
            return jsonify({'ok': True, 'booking_data': merged})

        except Exception:
            logger.exception("edit_booking failed for %s", booking_id)
            return jsonify({'ok': False, 'error': 'Internal server error'}), 500

    # ------------------------------------------------------------------
    # POST /api/bookings/<booking_id>/notes
    # ------------------------------------------------------------------
    @bp.route('/api/bookings/<booking_id>/notes', methods=['POST'])
    @require_auth
    def add_booking_note(booking_id):
        try:
            body = request.get_json(silent=True) or {}
            note = (body.get('note') or '').strip()

            if not note:
                return jsonify({'ok': False, 'error': "'note' field is required"}), 400

            state = StateManager()

            with _get_conn() as conn:
                exists = conn.execute(
                    "SELECT 1 FROM bookings WHERE id=?", (booking_id,)
                ).fetchone()

            if not exists:
                return jsonify({'ok': False, 'error': 'Booking not found'}), 404

            state.log_booking_event(
                booking_id, 'note', actor='owner_ui',
                details={'text': note}
            )
            logger.info("Admin added note to booking %s", booking_id)
            return jsonify({'ok': True})

        except Exception:
            logger.exception("add_booking_note failed for %s", booking_id)
            return jsonify({'ok': False, 'error': 'Internal server error'}), 500

    # ------------------------------------------------------------------
    # POST /api/bookings/bulk — bulk confirm/decline
    # ------------------------------------------------------------------
    @bp.route('/api/bookings/bulk', methods=['POST'])
    @require_auth
    def bulk_action():
        try:
            body = request.get_json(silent=True) or {}
            action = body.get('action', '')
            ids = body.get('ids', [])

            if action not in ('confirm', 'decline'):
                return jsonify({
                    'ok': False,
                    'error': "action must be 'confirm' or 'decline'"
                }), 400

            if not isinstance(ids, list) or not ids:
                return jsonify({'ok': False, 'error': "'ids' must be a non-empty list"}), 400

            # Cap bulk operations to prevent runaway requests
            MAX_BULK = 200
            if len(ids) > MAX_BULK:
                return jsonify({
                    'ok': False,
                    'error': f"Cannot process more than {MAX_BULK} bookings at once"
                }), 400

            state = StateManager()
            processed = 0
            errors = []

            for booking_id in ids:
                try:
                    with _get_conn() as conn:
                        row = conn.execute(
                            "SELECT booking_data, status, customer_email, thread_id FROM bookings WHERE id=?",
                            (booking_id,)
                        ).fetchone()

                    if not row:
                        errors.append({'id': booking_id, 'error': 'not found'})
                        continue

                    current_status = row['status']

                    if action == 'confirm':
                        if current_status != 'awaiting_owner':
                            errors.append({
                                'id': booking_id,
                                'error': f"status is '{current_status}', expected 'awaiting_owner'"
                            })
                            continue

                        try:
                            booking_data = json.loads(row['booking_data']) if row['booking_data'] else {}
                        except (ValueError, TypeError):
                            booking_data = {}

                        success = state.confirm_booking(booking_id, booking_data)
                        if not success:
                            errors.append({'id': booking_id, 'error': 'confirm failed (possible conflict)'})
                            continue

                        # Notify customer after bulk confirm
                        bulk_customer_email = row.get('customer_email') or booking_data.get('customer_email')
                        bulk_thread_id = row.get('thread_id')
                        bulk_notif = _notify_customer_confirmed(booking_id, booking_data, bulk_customer_email, bulk_thread_id)

                        state.log_booking_event(
                            booking_id, 'confirmed', actor='owner_ui',
                            details={
                                'triggered_by': 'bulk_action',
                                'customer_notified_sms': bulk_notif['sms_sent'],
                                'customer_notified_email': bulk_notif['email_sent'],
                            }
                        )

                    elif action == 'decline':
                        if current_status != 'awaiting_owner':
                            errors.append({
                                'id': booking_id,
                                'error': f"status is '{current_status}', expected 'awaiting_owner'"
                            })
                            continue

                        success = state.decline_booking(booking_id)
                        if not success:
                            errors.append({'id': booking_id, 'error': 'decline failed'})
                            continue

                        state.log_booking_event(
                            booking_id, 'declined', actor='owner_ui',
                            details={'triggered_by': 'bulk_action'}
                        )

                    processed += 1

                except Exception as exc:
                    logger.exception("bulk_action: error processing booking %s", booking_id)
                    errors.append({'id': booking_id, 'error': str(exc)})

            logger.info(
                "Bulk %s: processed=%d errors=%d", action, processed, len(errors)
            )
            return jsonify({'ok': True, 'processed': processed, 'errors': errors})

        except Exception:
            logger.exception("bulk_action failed")
            return jsonify({'ok': False, 'error': 'Internal server error'}), 500


# ---------------------------------------------------------------------------
# Self-registration — executed when the module is imported by admin_pro/__init__.py
# ---------------------------------------------------------------------------
from admin_pro import admin_pro_bp, require_auth  # noqa: E402
register(admin_pro_bp, require_auth)
