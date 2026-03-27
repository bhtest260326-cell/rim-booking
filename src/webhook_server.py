"""
webhook_server.py — Flask HTTP server for real-time event delivery.

Endpoints:
  POST /webhook/gmail          — Google Pub/Sub push for new Gmail messages
  POST /webhook/twilio/sms     — Twilio inbound SMS from the owner
  GET  /health                 — Railway health check
  GET  /health/detailed        — Per-component health check
"""

import os
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
            if request.args.get('token') != _PUBSUB_TOKEN:
                logger.warning("Gmail webhook: invalid or missing token")
                return 'Unauthorized', 403

        envelope = request.get_json(silent=True)
        if not envelope:
            return 'Bad Request: expected JSON', 400

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
        try:
            auth_token = os.environ['TWILIO_AUTH_TOKEN']
            from twilio.request_validator import RequestValidator
            validator = RequestValidator(auth_token)
            signature = request.headers.get('X-Twilio-Signature', '')
            # Use the public URL if behind a proxy (Railway sets X-Forwarded-Proto)
            url = request.url.replace('http://', 'https://', 1)
            if not validator.validate(url, request.form.to_dict(), signature):
                logger.warning("Twilio webhook: invalid signature")
                return 'Unauthorized', 403
        except KeyError:
            logger.error("TWILIO_AUTH_TOKEN not set — cannot validate Twilio signature, rejecting request")
            return 'Service Unavailable', 503
        except Exception as e:
            logger.error(f"Twilio signature validation error: {e}")
            return 'Internal Server Error', 500

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
