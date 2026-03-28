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
        """Customer-facing reschedule page — calendar UI with month navigation."""
        from email_utils import verify_reschedule_token
        from state_manager import StateManager
        from maps_handler import get_week_availability, get_job_duration_minutes, _is_business_day
        import json, calendar as _cal
        from datetime import datetime as _dt, timedelta as _td, date as _date

        booking_id = verify_reschedule_token(token)
        if not booking_id:
            return ("<h2 style='font-family:sans-serif;color:#C41230;'>Link expired or invalid.</h2>"
                    "<p style='font-family:sans-serif;'>Please reply to your confirmation email to reschedule.</p>"), 400

        state = StateManager()
        confirmed = state.get_confirmed_bookings()
        booking = confirmed.get(booking_id)
        if not booking:
            return ("<h2 style='font-family:sans-serif;'>Booking not found.</h2>"
                    "<p style='font-family:sans-serif;'>It may have already been rescheduled or cancelled.</p>"), 404

        bd = booking.get('booking_data', {})
        if isinstance(bd, str):
            bd = json.loads(bd)

        # Determine which month to display (default: current month, min: today)
        today = _date.today()
        month_param = request.args.get('month', today.strftime('%Y-%m'))
        try:
            view_year, view_month = int(month_param[:4]), int(month_param[5:7])
            view_first = _date(view_year, view_month, 1)
        except Exception:
            view_first = today.replace(day=1)
            view_year, view_month = view_first.year, view_first.month

        # Clamp: don't allow navigating before current month
        if view_first < today.replace(day=1):
            view_first = today.replace(day=1)
            view_year, view_month = view_first.year, view_first.month

        # Prev/next month navigation
        prev_month_dt = (view_first - _td(days=1)).replace(day=1)
        next_month_dt = (view_first + _td(days=32)).replace(day=1)
        prev_param = prev_month_dt.strftime('%Y-%m')
        next_param = next_month_dt.strftime('%Y-%m')
        can_go_prev = view_first > today.replace(day=1)

        # Fetch availability: enough days to cover entire view month + overflow
        days_in_month = _cal.monthrange(view_year, view_month)[1]
        # Start from the later of today or view_first
        fetch_start = max(today, view_first)
        duration = get_job_duration_minutes(bd)
        avail_data = get_week_availability(
            duration,
            from_date_str=fetch_start.strftime('%Y-%m-%d'),
            num_days=max(days_in_month, 30)
        )
        avail_map = {s['date']: s['available'] for s in avail_data}

        customer_name = (bd.get('customer_name') or 'there').split()[0]
        current_date = bd.get('preferred_date', 'Unknown')
        month_label = view_first.strftime('%B %Y')

        # Build calendar grid (Sunday-first, 7 columns)
        # weekday(): Mon=0 … Sun=6; calendar week starts Sunday so offset = (weekday+1)%7
        first_weekday = view_first.weekday()   # 0=Mon … 6=Sun
        start_offset = (first_weekday + 1) % 7  # cells to skip before day 1 (Sun-first grid)

        day_headers = ''.join(f'<div class="dh">{d}</div>' for d in ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'])
        cells = '<div class="dc empty"></div>' * start_offset

        for d in range(1, days_in_month + 1):
            day_date = _date(view_year, view_month, d)
            date_str = day_date.strftime('%Y-%m-%d')
            is_past = day_date < today
            is_weekend = day_date.weekday() >= 5

            if is_past or is_weekend:
                css = 'dc past'
                inner = f'<span class="dn">{d}</span>'
            elif not _is_business_day(day_date):
                css = 'dc holiday'
                inner = f'<span class="dn">{d}</span><span class="dl">Holiday</span>'
            elif avail_map.get(date_str) is True:
                css = 'dc available'
                inner = (f'<a href="/reschedule/{token}/confirm/{date_str}" class="day-link">'
                         f'<span class="dn">{d}</span><span class="dl">Available</span></a>')
            elif avail_map.get(date_str) is False:
                css = 'dc full'
                inner = f'<span class="dn">{d}</span><span class="dl">Full</span>'
            else:
                # Date not in fetched range (future beyond our window)
                css = 'dc future'
                inner = f'<span class="dn">{d}</span>'

            cells += f'<div class="{css}">{inner}</div>'

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Reschedule Your Booking</title>
<style>
  *{{box-sizing:border-box;margin:0;padding:0;}}
  body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#f8fafc;color:#1e293b;}}
  .wrap{{max-width:480px;margin:32px auto;padding:16px;}}
  .card{{background:#fff;border-radius:12px;box-shadow:0 2px 12px rgba(0,0,0,.08);padding:24px;}}
  h1{{color:#C41230;font-size:22px;margin-bottom:4px;}}
  .subtitle{{color:#64748b;font-size:14px;margin-bottom:20px;}}
  .current-booking{{background:#fef2f2;border:1px solid #fecaca;border-radius:8px;
    padding:12px 16px;margin-bottom:20px;font-size:14px;color:#991b1b;}}
  .cal-nav{{display:flex;align-items:center;justify-content:space-between;margin-bottom:12px;}}
  .cal-nav strong{{font-size:17px;}}
  .nav-btn{{background:none;border:1px solid #e2e8f0;border-radius:6px;
    padding:6px 14px;cursor:pointer;color:#1e293b;font-size:13px;text-decoration:none;
    display:inline-block;}}
  .nav-btn:hover{{background:#f1f5f9;}}
  .nav-btn.disabled{{color:#cbd5e1;cursor:default;pointer-events:none;}}
  .cal-grid{{display:grid;grid-template-columns:repeat(7,1fr);gap:4px;}}
  .dh{{text-align:center;font-size:11px;font-weight:600;color:#94a3b8;
    padding:6px 0;text-transform:uppercase;}}
  .dc{{border-radius:8px;min-height:52px;display:flex;flex-direction:column;
    align-items:center;justify-content:center;padding:4px;font-size:13px;}}
  .dc.empty{{background:none;}}
  .dc.past{{background:#f8fafc;opacity:.45;}}
  .dc.holiday{{background:#f8fafc;opacity:.55;}}
  .dc.future{{background:#f8fafc;}}
  .dc.full{{background:#fff1f2;}}
  .dc.available{{background:#f0fdf4;border:1px solid #bbf7d0;transition:transform .1s;}}
  .dc.available:hover{{transform:scale(1.04);border-color:#4ade80;}}
  .dn{{font-weight:700;font-size:15px;}}
  .dc.past .dn,.dc.holiday .dn,.dc.future .dn{{color:#94a3b8;font-weight:400;}}
  .dc.full .dn{{color:#f87171;}}
  .dc.available .dn{{color:#16a34a;}}
  .dl{{font-size:10px;margin-top:2px;}}
  .dc.full .dl{{color:#f87171;}}
  .dc.available .dl{{color:#16a34a;font-weight:600;}}
  .dc.holiday .dl{{color:#94a3b8;}}
  .day-link{{display:flex;flex-direction:column;align-items:center;
    text-decoration:none;width:100%;height:100%;}}
  .legend{{display:flex;gap:14px;margin-top:16px;flex-wrap:wrap;}}
  .leg{{display:flex;align-items:center;gap:5px;font-size:12px;color:#64748b;}}
  .leg-dot{{width:10px;height:10px;border-radius:3px;}}
  .footer{{margin-top:16px;font-size:12px;color:#94a3b8;text-align:center;}}
</style>
</head>
<body>
<div class="wrap">
  <div class="card">
    <h1>Reschedule Booking</h1>
    <p class="subtitle">Hi {customer_name}, select a new date below</p>
    <div class="current-booking">
      Current booking: <strong>{current_date}</strong>
    </div>

    <div class="cal-nav">
      {'<a href="?month=' + prev_param + '" class="nav-btn">&#8592; ' + prev_month_dt.strftime('%b') + '</a>' if can_go_prev else '<span class="nav-btn disabled">&#8592;</span>'}
      <strong>{month_label}</strong>
      <a href="?month={next_param}" class="nav-btn">{next_month_dt.strftime('%b')} &#8594;</a>
    </div>

    <div class="cal-grid">
      {day_headers}
      {cells}
    </div>

    <div class="legend">
      <div class="leg"><div class="leg-dot" style="background:#bbf7d0;border:1px solid #86efac;"></div>Available</div>
      <div class="leg"><div class="leg-dot" style="background:#fff1f2;border:1px solid #fecaca;"></div>Fully booked</div>
      <div class="leg"><div class="leg-dot" style="background:#f1f5f9;"></div>Unavailable</div>
    </div>
    <p class="footer">This link expires 7 days after your original confirmation.</p>
  </div>
</div>
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

        # Send booking change confirmation email to customer
        if get_flag('flag_auto_email_customer'):
            try:
                customer_email = booking.get('customer_email') or bd.get('customer_email')
                if customer_email:
                    from twilio_handler import send_reschedule_change_email
                    send_reschedule_change_email(customer_email, bd, booking_id, old_date)
            except Exception as e:
                logger.warning(f"Reschedule change email failed: {e}")

        # Build a branded success page with a fresh reschedule link
        from email_utils import build_email_html, generate_reschedule_token, _p, _h2, RED, DARK
        from datetime import datetime as _dt2

        try:
            new_date_fmt = _dt2.strptime(new_date, '%Y-%m-%d').strftime('%A, %d %B %Y').replace(' 0', ' ')
        except Exception:
            new_date_fmt = new_date

        customer_name = (bd.get('customer_name') or 'there').split()[0]

        reschedule_again_para = ''
        try:
            base_url = os.environ.get('APP_BASE_URL', '').rstrip('/')
            if base_url:
                new_token = generate_reschedule_token(booking_id)
                reschedule_again_url = f"{base_url}/reschedule/{new_token}"
                reschedule_again_para = (
                    f'<p style="margin:16px 0 0;font-size:15px;color:{DARK};">'
                    f'Changed your mind? <a href="{reschedule_again_url}" style="color:{RED};">Click here</a> '
                    f'to pick a different date.</p>'
                )
        except Exception:
            pass

        page_content = (
            f'<h1 style="color:{RED};font-size:22px;margin:0 0 16px;">Booking Updated</h1>'
            + _p(f'Hi {customer_name}, your booking has been successfully rescheduled to '
                 f'<strong>{new_date_fmt}</strong>.')
            + _p('A confirmation email has been sent to you with the updated details. '
                 'If you have any questions, please reply to your original booking email.')
            + reschedule_again_para
            + f'<p style="margin:24px 0 0;color:{DARK};font-size:15px;">'
              f'Kind regards,<br><strong style="color:{RED};">Rim Repair Team</strong></p>'
        )

        return build_email_html(page_content)

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
