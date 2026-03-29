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

            # Sort
            _SORT_COLS = {
                'created_at':     'created_at',
                'preferred_date': 'preferred_date',
                'status':         'status',
                'customer_email': 'customer_email',
            }
            sort_by  = _SORT_COLS.get(request.args.get('sort_by', ''), 'created_at')
            sort_dir = 'ASC' if request.args.get('sort_dir', 'desc').lower() == 'asc' else 'DESC'

            count_sql = f"SELECT COUNT(*) AS cnt FROM bookings {where_clause}"
            list_sql = (
                f"SELECT * FROM bookings {where_clause} "
                f"ORDER BY {sort_by} {sort_dir} "
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

            # ── Google Calendar sync: create or convert event ──
            calendar_event_id = None
            try:
                with _get_conn() as conn:
                    eid_row = conn.execute(
                        "SELECT calendar_event_id FROM bookings WHERE id=?",
                        (booking_id,)
                    ).fetchone()
                existing_event_id = eid_row['calendar_event_id'] if eid_row else None

                if existing_event_id:
                    # Convert tentative [PENDING] event to confirmed
                    from calendar_handler import confirm_tentative_event
                    confirm_tentative_event(existing_event_id, booking_data)
                    calendar_event_id = existing_event_id
                    logger.info("Admin confirm: converted tentative calendar event %s", existing_event_id)
                else:
                    # Create a new confirmed calendar event
                    from calendar_handler import create_calendar_event
                    calendar_event_id = create_calendar_event(booking_data)
                    if calendar_event_id:
                        state.update_booking_calendar_event(booking_id, calendar_event_id)
                        logger.info("Admin confirm: created calendar event %s for booking %s", calendar_event_id, booking_id)
            except Exception:
                logger.exception("Admin confirm: calendar sync failed for booking %s (non-blocking)", booking_id)

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
                    'calendar_event_id': calendar_event_id,
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

            # ── Delete tentative calendar event before declining ──
            try:
                with _get_conn() as conn:
                    eid_row = conn.execute(
                        "SELECT calendar_event_id FROM bookings WHERE id=?",
                        (booking_id,)
                    ).fetchone()
                existing_event_id = eid_row['calendar_event_id'] if eid_row else None
                if existing_event_id:
                    from calendar_handler import delete_calendar_event
                    delete_calendar_event(existing_event_id)
                    logger.info("Admin decline: deleted calendar event %s for booking %s", existing_event_id, booking_id)
            except Exception:
                logger.exception("Admin decline: calendar delete failed for booking %s (non-blocking)", booking_id)

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

            # ── Google Calendar sync: update event if date/time changed ──
            date_or_time_changed = 'preferred_date' in body or 'preferred_time' in body
            if date_or_time_changed:
                try:
                    with _get_conn() as conn:
                        eid_row = conn.execute(
                            "SELECT calendar_event_id FROM bookings WHERE id=?",
                            (booking_id,)
                        ).fetchone()
                    event_id = eid_row['calendar_event_id'] if eid_row else None

                    new_date = merged.get('preferred_date', '')
                    new_time = merged.get('preferred_time', '')

                    if event_id and new_date and new_time:
                        from calendar_handler import update_calendar_event_time
                        from maps_handler import get_job_duration_minutes

                        # Parse new start time
                        time_str = new_time.strip().upper()
                        # Handle "HH:MM AM/PM" and "HH:MM" formats
                        for fmt in ('%Y-%m-%d %I:%M %p', '%Y-%m-%d %H:%M'):
                            try:
                                start_dt = datetime.strptime(
                                    new_date + ' ' + time_str, fmt
                                )
                                break
                            except ValueError:
                                continue
                        else:
                            # Fallback: try just the date with 9am default
                            start_dt = datetime.strptime(new_date, '%Y-%m-%d').replace(hour=9)

                        duration = get_job_duration_minutes(merged)
                        update_calendar_event_time(event_id, start_dt, duration)
                        logger.info("Admin edit: updated calendar event %s to %s %s", event_id, new_date, new_time)
                    elif event_id and not new_date:
                        # Date cleared (dragged back to pending) — leave calendar event as-is
                        logger.info("Admin edit: date cleared for booking %s, calendar event %s preserved", booking_id, event_id)
                except Exception:
                    logger.exception("Admin edit: calendar sync failed for booking %s (non-blocking)", booking_id)

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
                            "SELECT booking_data, status, customer_email, thread_id, calendar_event_id FROM bookings WHERE id=?",
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

                        # Delete tentative calendar event before declining
                        existing_event_id = row['calendar_event_id']
                        if existing_event_id:
                            try:
                                from calendar_handler import delete_calendar_event
                                delete_calendar_event(existing_event_id)
                                logger.info("Bulk decline: deleted calendar event %s for booking %s", existing_event_id, booking_id)
                            except Exception:
                                logger.exception("Bulk decline: calendar delete failed for booking %s (non-blocking)", booking_id)

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

    # ------------------------------------------------------------------
    # POST /api/bookings/<booking_id>/mark-moved
    # ------------------------------------------------------------------
    @bp.route('/api/bookings/<booking_id>/mark-moved', methods=['POST'])
    @require_auth
    def mark_booking_moved(booking_id):
        try:
            body = request.get_json(silent=True) or {}
            original_date = body.get('original_date')
            original_time = body.get('original_time')

            state = StateManager()

            with _get_conn() as conn:
                row = conn.execute(
                    "SELECT booking_data, status FROM bookings WHERE id=?",
                    (booking_id,)
                ).fetchone()

            if not row:
                return jsonify({'ok': False, 'error': 'Booking not found'}), 404

            try:
                booking_data = json.loads(row['booking_data']) if row['booking_data'] else {}
            except (ValueError, TypeError):
                booking_data = {}

            booking_data['moved_pending_notification'] = True
            booking_data['original_date'] = original_date
            booking_data['original_time'] = original_time

            status = row['status']
            if status == 'awaiting_owner':
                state.update_pending_booking_data(booking_id, booking_data)
            elif status == 'confirmed':
                state.update_confirmed_booking_data(booking_id, booking_data)
            else:
                with _get_conn() as conn:
                    conn.execute(
                        "UPDATE bookings SET booking_data=?, preferred_date=? WHERE id=?",
                        (
                            json.dumps(booking_data),
                            booking_data.get('preferred_date'),
                            booking_id,
                        )
                    )

            new_date = booking_data.get('preferred_date')
            new_time = booking_data.get('preferred_time')

            state.log_booking_event(
                booking_id, 'rescheduled', actor='owner_ui',
                details={
                    'old_date': original_date,
                    'new_date': new_date,
                    'old_time': original_time,
                    'new_time': new_time,
                }
            )
            logger.info("Admin marked booking %s as moved (old=%s/%s new=%s/%s)",
                         booking_id, original_date, original_time, new_date, new_time)
            return jsonify({'ok': True})

        except Exception:
            logger.exception("mark_booking_moved failed for %s", booking_id)
            return jsonify({'ok': False, 'error': 'Internal server error'}), 500

    # ------------------------------------------------------------------
    # POST /api/bookings/<booking_id>/send-change-notification
    # ------------------------------------------------------------------
    @bp.route('/api/bookings/<booking_id>/send-change-notification', methods=['POST'])
    @require_auth
    def send_change_notification(booking_id):
        try:
            state = StateManager()

            with _get_conn() as conn:
                row = conn.execute(
                    "SELECT booking_data, status, customer_email, thread_id FROM bookings WHERE id=?",
                    (booking_id,)
                ).fetchone()

            if not row:
                return jsonify({'ok': False, 'error': 'Booking not found'}), 404

            try:
                booking_data = json.loads(row['booking_data']) if row['booking_data'] else {}
            except (ValueError, TypeError):
                booking_data = {}

            if not booking_data.get('moved_pending_notification'):
                return jsonify({'ok': False, 'error': 'No pending move to notify'})

            customer_email = row['customer_email'] or booking_data.get('customer_email')
            thread_id = row['thread_id']
            email_sent = False

            if customer_email:
                try:
                    from twilio_handler import get_gmail_service, _fmt_date
                    from email_utils import send_customer_email, _h2, _p, _info_table, DARK, esc

                    service = get_gmail_service()
                    name = booking_data.get('customer_name', 'there')
                    first = esc(name.split()[0]) if name and name != 'there' else 'there'

                    new_date_raw = booking_data.get('preferred_date', 'TBC')
                    new_date = _fmt_date(new_date_raw)
                    new_time = booking_data.get('preferred_time', 'TBC')
                    original_date = _fmt_date(booking_data.get('original_date', 'TBC'))
                    original_time = booking_data.get('original_time', 'TBC')

                    address = esc(booking_data.get('address') or booking_data.get('suburb', 'your location'))

                    info_rows = [
                        ('New Date', new_date),
                        ('New Time', new_time),
                        ('Address', address),
                    ]

                    content = (
                        _p(f'Hi {first},')
                        + _p('We\'re writing to let you know that your booking has been rescheduled.')
                        + _h2('Updated Booking Details')
                        + _info_table(info_rows)
                        + _p(f'Your booking has been moved from <strong>{original_date}</strong> at '
                             f'<strong>{original_time}</strong> to <strong>{new_date}</strong> at '
                             f'<strong>{new_time}</strong>.')
                        + _p('If this new time doesn\'t work for you, simply reply to this email '
                             'and we\'ll find a better time.')
                        + f'<p style="margin:24px 0 0;color:{DARK};font-size:15px;">'
                          f'Kind regards,<br><strong style="color:#C41230;">Wheel Doctor Team</strong></p>'
                    )

                    ref = f' #{booking_id}'
                    send_customer_email(
                        service, customer_email,
                        f'Booking Rescheduled{ref} — Perth Swedish & European Auto Centre',
                        content, thread_id=thread_id
                    )
                    email_sent = True
                    logger.info("Change notification email sent to %s for booking %s", customer_email, booking_id)

                except Exception:
                    logger.exception("send_change_notification: email failed for booking %s", booking_id)

            # Clear the pending notification flags
            booking_data.pop('moved_pending_notification', None)
            booking_data.pop('original_date', None)
            booking_data.pop('original_time', None)

            status = row['status']
            if status == 'awaiting_owner':
                state.update_pending_booking_data(booking_id, booking_data)
            elif status == 'confirmed':
                state.update_confirmed_booking_data(booking_id, booking_data)
            else:
                with _get_conn() as conn:
                    conn.execute(
                        "UPDATE bookings SET booking_data=?, preferred_date=? WHERE id=?",
                        (
                            json.dumps(booking_data),
                            booking_data.get('preferred_date'),
                            booking_id,
                        )
                    )

            state.log_booking_event(
                booking_id, 'change_notification_sent', actor='owner_ui',
                details={'email_sent': email_sent}
            )
            logger.info("Change notification processed for booking %s (email_sent=%s)", booking_id, email_sent)
            return jsonify({'ok': True, 'email_sent': email_sent})

        except Exception:
            logger.exception("send_change_notification failed for %s", booking_id)
            return jsonify({'ok': False, 'error': 'Internal server error'}), 500


# ---------------------------------------------------------------------------
# Self-registration — executed when the module is imported by admin_pro/__init__.py
# ---------------------------------------------------------------------------
from admin_pro import admin_pro_bp, require_auth  # noqa: E402
register(admin_pro_bp, require_auth)
