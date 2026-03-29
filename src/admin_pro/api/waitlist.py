"""
admin_pro/api/waitlist.py
Waitlist CRUD and auto-offer API endpoints.
"""

import json
import logging
from datetime import datetime, timezone

from flask import request, jsonify

from state_manager import StateManager, _get_conn

logger = logging.getLogger(__name__)


def register(bp, require_auth):
    """Register all waitlist API routes on *bp* using *require_auth* decorator."""

    # ------------------------------------------------------------------
    # GET /api/waitlist — list all waitlist entries (with filtering)
    # ------------------------------------------------------------------
    @bp.route('/api/waitlist', methods=['GET'])
    @require_auth
    def list_waitlist():
        try:
            status = request.args.get('status', 'all')
            search = request.args.get('search', '').strip()

            state = StateManager()
            entries = state.get_waitlist(status=status)

            # Apply search filter if provided
            if search:
                search_lower = search.lower()
                entries = [
                    e for e in entries
                    if search_lower in (e.get('customer_name') or '').lower()
                    or search_lower in (e.get('customer_email') or '').lower()
                    or search_lower in (e.get('customer_phone') or '').lower()
                    or search_lower in (e.get('preferred_suburb') or '').lower()
                ]

            # Parse preferred_dates JSON for the response
            for entry in entries:
                raw = entry.get('preferred_dates')
                if raw and isinstance(raw, str):
                    try:
                        entry['preferred_dates'] = json.loads(raw)
                    except (ValueError, TypeError):
                        entry['preferred_dates'] = []

            return jsonify({'ok': True, 'data': entries, 'total': len(entries)})

        except Exception:
            logger.exception("list_waitlist error")
            return jsonify({'ok': False, 'error': 'Failed to fetch waitlist'}), 500

    # ------------------------------------------------------------------
    # POST /api/waitlist — add customer to waitlist
    # ------------------------------------------------------------------
    @bp.route('/api/waitlist', methods=['POST'])
    @require_auth
    def add_to_waitlist():
        try:
            body = request.get_json(force=True, silent=True) or {}

            customer_name = (body.get('customer_name') or '').strip()
            if not customer_name:
                return jsonify({'ok': False, 'error': 'customer_name is required'}), 400

            state = StateManager()
            wid = state.add_to_waitlist(
                customer_name=customer_name,
                customer_email=body.get('customer_email'),
                customer_phone=body.get('customer_phone'),
                service_type=body.get('service_type'),
                preferred_dates=body.get('preferred_dates'),
                preferred_suburb=body.get('preferred_suburb'),
                rim_count=body.get('rim_count', 1),
                notes=body.get('notes'),
            )

            logger.info("Admin added waitlist entry %s for %s", wid, customer_name)
            return jsonify({'ok': True, 'data': {'id': wid}})

        except Exception:
            logger.exception("add_to_waitlist error")
            return jsonify({'ok': False, 'error': 'Failed to add to waitlist'}), 500

    # ------------------------------------------------------------------
    # PUT /api/waitlist/<id> — update waitlist entry
    # ------------------------------------------------------------------
    @bp.route('/api/waitlist/<int:waitlist_id>', methods=['PUT'])
    @require_auth
    def update_waitlist(waitlist_id):
        try:
            body = request.get_json(force=True, silent=True) or {}
            if not body:
                return jsonify({'ok': False, 'error': 'Request body is required'}), 400

            state = StateManager()
            entry = state.get_waitlist_entry(waitlist_id)
            if not entry:
                return jsonify({'ok': False, 'error': 'Waitlist entry not found'}), 404

            state.update_waitlist_entry(waitlist_id, **body)
            logger.info("Admin updated waitlist entry %s", waitlist_id)
            return jsonify({'ok': True})

        except Exception:
            logger.exception("update_waitlist error for id %s", waitlist_id)
            return jsonify({'ok': False, 'error': 'Failed to update waitlist entry'}), 500

    # ------------------------------------------------------------------
    # DELETE /api/waitlist/<id> — remove from waitlist
    # ------------------------------------------------------------------
    @bp.route('/api/waitlist/<int:waitlist_id>', methods=['DELETE'])
    @require_auth
    def delete_waitlist(waitlist_id):
        try:
            state = StateManager()
            entry = state.get_waitlist_entry(waitlist_id)
            if not entry:
                return jsonify({'ok': False, 'error': 'Waitlist entry not found'}), 404

            state.delete_waitlist_entry(waitlist_id)
            logger.info("Admin deleted waitlist entry %s", waitlist_id)
            return jsonify({'ok': True})

        except Exception:
            logger.exception("delete_waitlist error for id %s", waitlist_id)
            return jsonify({'ok': False, 'error': 'Failed to delete waitlist entry'}), 500

    # ------------------------------------------------------------------
    # POST /api/waitlist/<id>/offer — manually offer a slot
    # ------------------------------------------------------------------
    @bp.route('/api/waitlist/<int:waitlist_id>/offer', methods=['POST'])
    @require_auth
    def offer_waitlist_slot(waitlist_id):
        try:
            body = request.get_json(force=True, silent=True) or {}
            offered_date = body.get('date')

            state = StateManager()
            entry = state.get_waitlist_entry(waitlist_id)
            if not entry:
                return jsonify({'ok': False, 'error': 'Waitlist entry not found'}), 404

            if entry.get('status') != 'waiting':
                return jsonify({
                    'ok': False,
                    'error': f"Entry is '{entry['status']}', not waiting"
                }), 409

            # Send SMS/email offer
            sms_sent = False
            email_sent = False
            customer_name = (entry.get('customer_name') or 'there').split()[0]

            date_display = offered_date or 'your preferred date'
            try:
                if offered_date:
                    dt = datetime.strptime(offered_date, '%Y-%m-%d')
                    date_display = dt.strftime('%A, %d %B %Y').replace(' 0', ' ')
            except Exception:
                pass

            customer_phone = entry.get('customer_phone')
            if customer_phone:
                try:
                    from feature_flags import get_flag
                    if get_flag('flag_auto_sms_customer'):
                        from twilio_handler import send_sms
                        msg = (
                            f"Hi {customer_name}, great news! A spot has opened up on "
                            f"{date_display} for your rim repair. "
                            f"Reply YES to confirm or NO to stay on the waitlist. "
                            f"This offer expires in 24 hours. - Wheel Doctor"
                        )
                        send_sms(customer_phone, msg)
                        sms_sent = True
                except Exception:
                    logger.exception("Waitlist offer SMS failed for entry %s", waitlist_id)

            customer_email = entry.get('customer_email')
            if customer_email:
                try:
                    from feature_flags import get_flag
                    if get_flag('flag_auto_email_customer'):
                        from google_auth import get_gmail_service
                        from email_utils import send_customer_email, _p, RED, DARK

                        service = get_gmail_service()
                        content = (
                            _p(f'Hi {customer_name},')
                            + _p(f'Great news! A spot has become available on '
                                 f'<strong>{date_display}</strong> for your rim repair.')
                            + _p('If you\'d like to book this slot, simply reply to this email '
                                 'or text <strong>YES</strong> to confirm.')
                            + _p('This offer is valid for <strong>24 hours</strong>. '
                                 'After that, the slot may be offered to someone else.')
                            + f'<p style="margin:24px 0 0;color:{DARK};font-size:15px;">'
                              f'Kind regards,<br><strong style="color:{RED};">Wheel Doctor Team</strong></p>'
                        )
                        send_customer_email(
                            service, customer_email,
                            f'Slot Available - {date_display}', content
                        )
                        email_sent = True
                except Exception:
                    logger.exception("Waitlist offer email failed for entry %s", waitlist_id)

            # Update status to 'offered'
            state.update_waitlist_status(waitlist_id, 'offered')

            logger.info(
                "Waitlist offer sent for entry %s (sms=%s, email=%s)",
                waitlist_id, sms_sent, email_sent
            )
            return jsonify({
                'ok': True,
                'sms_sent': sms_sent,
                'email_sent': email_sent
            })

        except Exception:
            logger.exception("offer_waitlist_slot error for id %s", waitlist_id)
            return jsonify({'ok': False, 'error': 'Failed to offer slot'}), 500


# ---------------------------------------------------------------------------
# Self-registration
# ---------------------------------------------------------------------------
from admin_pro import admin_pro_bp, require_auth  # noqa: E402
register(admin_pro_bp, require_auth)
