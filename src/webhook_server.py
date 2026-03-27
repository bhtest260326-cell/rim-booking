"""
webhook_server.py — Flask HTTP server for real-time event delivery.

Endpoints:
  POST /webhook/gmail          — Google Pub/Sub push for new Gmail messages
  POST /webhook/twilio/sms     — Twilio inbound SMS from the owner
  GET  /health                 — Railway health check
  GET  /health/detailed        — Per-component health check
"""

import os
import hmac
import json
import base64
import logging
from flask import Flask, request, jsonify

logger = logging.getLogger(__name__)

_PUBSUB_TOKEN = os.environ.get('PUBSUB_WEBHOOK_TOKEN', '')


def create_app():
    app = Flask(__name__)

    from admin_ui import admin_bp
    app.register_blueprint(admin_bp)

    # ------------------------------------------------------------------
    # Static assets (banner image etc.)
    # ------------------------------------------------------------------

    @app.route('/static/<path:filename>')
    def static_files(filename):
        import os
        from flask import send_from_directory
        static_dir = os.path.join(os.path.dirname(__file__), 'static')
        return send_from_directory(static_dir, filename)

    # ------------------------------------------------------------------
    # Gmail / Pub/Sub webhook
    # ------------------------------------------------------------------

    @app.route('/webhook/gmail', methods=['POST'])
    def gmail_webhook():
        # Optional token check — set PUBSUB_WEBHOOK_TOKEN in Railway to enable
        if _PUBSUB_TOKEN:
            token = request.args.get('token', '')
            if not hmac.compare_digest(token.encode(), _PUBSUB_TOKEN.encode()):
                logger.warning("Gmail webhook: invalid or missing token")
                return 'Unauthorized', 403

        envelope = request.get_json(silent=True)
        if not envelope:
            return 'Bad Request: expected JSON', 400

        pubsub_audience = os.environ.get('PUBSUB_AUDIENCE', '')
        if pubsub_audience:
            auth_header = request.headers.get('Authorization', '')
            if auth_header.startswith('Bearer '):
                token = auth_header[7:]
                try:
                    from google.oauth2 import id_token
                    from google.auth.transport import requests as grequests
                    id_token.verify_oauth2_token(token, grequests.Request(), pubsub_audience)
                except Exception as e:
                    logger.warning(f"Gmail Pub/Sub JWT verification failed: {e}")
                    return jsonify({'error': 'Invalid token'}), 403
            else:
                logger.warning("Gmail webhook received without Authorization header (PUBSUB_AUDIENCE set but no token)")
                # Still process — don't block if token missing (gradual rollout)

        pubsub_message = envelope.get('message', {})
        data_b64 = pubsub_message.get('data', '')
        if not data_b64:
            # Pub/Sub sometimes sends an empty keepalive — acknowledge and ignore
            return 'OK', 200

        try:
            notification = json.loads(base64.b64decode(data_b64).decode('utf-8'))
        except Exception as e:
            logger.error(f"Gmail webhook: failed to decode Pub/Sub message: {e}")
            return 'Bad Request: decode failed', 400

        history_id = notification.get('historyId')
        if not history_id:
            return 'OK', 200

        logger.info(f"Gmail webhook: historyId={history_id}")

        try:
            from gmail_poller import process_history_notification
            process_history_notification(history_id)
            try:
                from state_manager import StateManager
                from datetime import datetime, timezone
                StateManager().set_app_state('last_gmail_poll_at', datetime.now(timezone.utc).isoformat())
            except Exception:
                pass
        except Exception as e:
            logger.error(f"Gmail webhook processing error: {e}", exc_info=True)
            # Return 200 anyway — returning 4xx/5xx causes Pub/Sub to retry

        return 'OK', 200

    # ------------------------------------------------------------------
    # Twilio inbound SMS webhook
    # ------------------------------------------------------------------

    @app.route('/webhook/twilio/sms', methods=['POST'])
    def twilio_sms_webhook():
        # Validate Twilio signature to reject spoofed requests
        auth_token = os.environ.get('TWILIO_AUTH_TOKEN', '')
        if auth_token and not os.environ.get('TWILIO_SKIP_VALIDATION'):
            from twilio.request_validator import RequestValidator
            validator = RequestValidator(auth_token)
            url = request.url
            post_data = request.form.to_dict()
            signature = request.headers.get('X-Twilio-Signature', '')
            if not validator.validate(url, post_data, signature):
                logger.warning("Twilio webhook signature validation failed")
                return jsonify({'error': 'Invalid signature'}), 403

        from_number = request.form.get('From', '')
        body_text = request.form.get('Body', '')
        message_sid = request.form.get('MessageSid', '')

        if not message_sid:
            return 'Bad Request', 400

        logger.info(f"Twilio webhook: SMS from {from_number} SID={message_sid}")

        try:
            from twilio_handler import process_single_sms_webhook
            process_single_sms_webhook(from_number, body_text, message_sid)
        except Exception as e:
            logger.error(f"Twilio webhook processing error: {e}", exc_info=True)

        # Return empty TwiML — Twilio requires a valid XML response
        return (
            '<?xml version="1.0" encoding="UTF-8"?><Response></Response>',
            200,
            {'Content-Type': 'text/xml'}
        )

    # ------------------------------------------------------------------
    # Customer self-service reschedule
    # ------------------------------------------------------------------

    @app.route('/reschedule/<token>', methods=['GET'])
    def reschedule_page(token):
        """Customer-facing reschedule page. Shows available days for their booking."""
        from email_utils import verify_reschedule_token
        from state_manager import StateManager
        from maps_handler import get_week_availability, get_job_duration_minutes
        import json

        booking_id = verify_reschedule_token(token)
        if not booking_id:
            return "<h2>This reschedule link has expired or is invalid.</h2><p>Please reply to your confirmation email to reschedule.</p>", 400

        state = StateManager()
        # Check confirmed bookings
        confirmed = state.get_confirmed_bookings()
        booking = confirmed.get(booking_id)
        if not booking:
            return "<h2>Booking not found.</h2><p>It may have already been cancelled or rescheduled.</p>", 404

        bd = booking.get('booking_data', {})
        if isinstance(bd, str):
            bd = json.loads(bd)

        # Get available days
        duration = get_job_duration_minutes(bd)
        availability = get_week_availability(duration)
        available_days = [slot for slot in availability if slot['available']]

        customer_name = (bd.get('customer_name') or 'there').split()[0]
        current_date = bd.get('preferred_date', 'Unknown')

        # Build simple HTML page
        options_html = ''
        for slot in available_days:
            options_html += f'<li><a href="/reschedule/{token}/confirm/{slot["date"]}">{slot["day_name"]} {slot["date"]}</a></li>'

        if not options_html:
            options_html = '<li>No available dates found in the next two weeks. Please reply to your email to reschedule.</li>'

        html = f"""<!DOCTYPE html>
<html><head><title>Reschedule Your Booking</title>
<style>body{{font-family:sans-serif;max-width:500px;margin:40px auto;padding:20px;}}
h1{{color:#C41230;}}a{{color:#C41230;}}ul{{line-height:2;}}</style></head>
<body>
<h1>Reschedule Your Booking</h1>
<p>Hi {customer_name}, your current booking is for <strong>{current_date}</strong>.</p>
<p>Please choose a new date from the available options below:</p>
<ul>{options_html}</ul>
<p><small>This link expires 7 days after your original confirmation.</small></p>
</body></html>"""
        return html

    @app.route('/reschedule/<token>/confirm/<new_date>', methods=['GET'])
    def reschedule_confirm(token, new_date):
        """Confirm the reschedule to the selected date."""
        import re, json
        from email_utils import verify_reschedule_token
        from state_manager import StateManager
        from feature_flags import get_flag

        # Validate date format
        if not re.match(r'^\d{4}-\d{2}-\d{2}$', new_date):
            return "<h2>Invalid date.</h2>", 400

        booking_id = verify_reschedule_token(token)
        if not booking_id:
            return "<h2>This reschedule link has expired or is invalid.</h2>", 400

        state = StateManager()
        confirmed = state.get_confirmed_bookings()
        booking = confirmed.get(booking_id)
        if not booking:
            return "<h2>Booking not found.</h2>", 404

        bd = booking.get('booking_data', {})
        if isinstance(bd, str):
            bd = json.loads(bd)

        old_date = bd.get('preferred_date', 'Unknown')
        bd['preferred_date'] = new_date
        bd['preferred_time'] = None  # Will be reassigned by route optimizer

        # Update DB
        state.update_confirmed_booking_data(booking_id, bd)

        try:
            state.log_booking_event(booking_id, 'rescheduled', actor='customer_self_service',
                details={'old_date': old_date, 'new_date': new_date})
        except Exception:
            pass

        # Notify owner via SMS
        if get_flag('flag_auto_sms_owner'):
            try:
                from twilio_handler import send_sms
                owner_mobile = os.environ.get('OWNER_MOBILE', '')
                if owner_mobile:
                    cust_name = (bd.get('customer_name') or 'Customer')
                    send_sms(owner_mobile,
                        f"Booking {booking_id} rescheduled by customer from {old_date} to {new_date} ({cust_name}). - Rim Repair System")
            except Exception as e:
                logger.warning(f"Owner reschedule SMS failed: {e}")

        customer_name = (bd.get('customer_name') or 'there').split()[0]
        html = f"""<!DOCTYPE html>
<html><head><title>Booking Rescheduled</title>
<style>body{{font-family:sans-serif;max-width:500px;margin:40px auto;padding:20px;}}
h1{{color:#C41230;}}</style></head>
<body>
<h1>Booking Rescheduled</h1>
<p>Hi {customer_name}, your booking has been rescheduled to <strong>{new_date}</strong>.</p>
<p>You'll receive a confirmation shortly. If you have any questions, please reply to your original email.</p>
<p><strong>Rim Repair Team</strong></p>
</body></html>"""
        return html

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------

    @app.route('/health', methods=['GET'])
    def health():
        return jsonify({'status': 'ok'})

    @app.route('/health/ai', methods=['GET'])
    def health_ai():
        """Diagnostic endpoint — tests whether the Anthropic API is reachable."""
        try:
            from ai_parser import client
            resp = client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=10,
                messages=[{"role": "user", "content": "Reply with the single word OK"}]
            )
            return jsonify({'status': 'ok', 'response': resp.content[0].text.strip()})
        except Exception as e:
            return jsonify({
                'status': 'error',
                'error_type': type(e).__name__,
                'error': str(e)
            }), 500

    @app.route('/health/detailed', methods=['GET'])
    def health_detailed():
        """Detailed system health check with per-component status."""
        import time
        import os
        from datetime import datetime, timezone, timedelta

        checks = {}
        overall = 'healthy'

        # --- Database ---
        try:
            from state_manager import StateManager, DB_PATH
            state = StateManager()
            db_size_mb = round(os.path.getsize(DB_PATH) / 1024 / 1024, 2) if os.path.exists(DB_PATH) else 0
            confirmed = state.get_confirmed_bookings()
            pending_bookings_with_cal = state.get_pending_bookings_with_calendar_events()
            checks['database'] = {
                'status': 'ok',
                'size_mb': db_size_mb,
                'confirmed_count': len(confirmed),
            }
        except Exception as e:
            checks['database'] = {'status': 'critical', 'error': str(e)}
            overall = 'critical'

        # --- Gmail last poll ---
        try:
            from state_manager import StateManager
            state = StateManager()
            last_poll = state.get_app_state('last_gmail_poll_at')
            if last_poll:
                last_dt = datetime.fromisoformat(last_poll)
                minutes_ago = round((datetime.now(timezone.utc) - last_dt).total_seconds() / 60, 1)
                poll_status = 'ok' if minutes_ago < 10 else ('warning' if minutes_ago < 30 else 'stale')
                if poll_status != 'ok' and overall == 'healthy':
                    overall = 'degraded'
                checks['gmail_last_poll'] = {
                    'status': poll_status,
                    'last_poll_at': last_poll,
                    'minutes_ago': minutes_ago,
                }
            else:
                checks['gmail_last_poll'] = {'status': 'unknown', 'note': 'No poll recorded yet'}
        except Exception as e:
            checks['gmail_last_poll'] = {'status': 'error', 'error': str(e)}

        # --- Pending bookings age ---
        try:
            from state_manager import StateManager
            state = StateManager()
            import sqlite3
            from state_manager import _get_conn
            with _get_conn() as conn:
                rows = conn.execute(
                    "SELECT id, created_at FROM bookings WHERE status='awaiting_owner' ORDER BY created_at ASC"
                ).fetchall()
            if rows:
                oldest = rows[0]
                oldest_dt = datetime.fromisoformat(oldest['created_at'])
                hours_old = round((datetime.now(timezone.utc) - oldest_dt).total_seconds() / 3600, 1)
                age_status = 'ok' if hours_old < 12 else ('warning' if hours_old < 48 else 'stale')
                if age_status == 'stale' and overall == 'healthy':
                    overall = 'degraded'
                checks['pending_bookings'] = {
                    'status': age_status,
                    'count': len(rows),
                    'oldest_booking_id': oldest['id'],
                    'oldest_hours_old': hours_old,
                }
            else:
                checks['pending_bookings'] = {'status': 'ok', 'count': 0}
        except Exception as e:
            checks['pending_bookings'] = {'status': 'error', 'error': str(e)}

        # --- Twilio ---
        twilio_ok = all([
            os.environ.get('TWILIO_ACCOUNT_SID'),
            os.environ.get('TWILIO_AUTH_TOKEN'),
            os.environ.get('TWILIO_FROM_NUMBER'),
            os.environ.get('OWNER_MOBILE'),
        ])
        checks['twilio'] = {'status': 'ok' if twilio_ok else 'misconfigured'}
        if not twilio_ok and overall == 'healthy':
            overall = 'degraded'

        # --- Google Maps ---
        maps_ok = bool(os.environ.get('GOOGLE_MAPS_API_KEY'))
        checks['google_maps'] = {'status': 'ok' if maps_ok else 'no_api_key (using 30min fallback)'}

        # --- Calendar ---
        cal_ok = bool(os.environ.get('GOOGLE_CALENDAR_ID'))
        checks['google_calendar'] = {'status': 'ok' if cal_ok else 'misconfigured'}

        return jsonify({
            'status': overall,
            'checks': checks,
            'timestamp': datetime.now(timezone.utc).isoformat(),
        }), 200 if overall != 'critical' else 503

    return app
