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
import time
import collections
from flask import Flask, request, jsonify

logger = logging.getLogger(__name__)

_PUBSUB_TOKEN = os.environ.get('PUBSUB_WEBHOOK_TOKEN', '')

# Fix 5 — Hardcoded Claude model name: use env var with sensible default
CLAUDE_MODEL = os.environ.get('CLAUDE_MODEL', 'claude-sonnet-4-6')

# Rate limiter for reschedule/booking public endpoints (per IP, 10 req/min)
_reschedule_rate_limit: dict = collections.defaultdict(list)
_RATE_LIMIT_MAX = 10
_RATE_LIMIT_WINDOW = 60  # seconds

# Separate rate limiter for webhook endpoints (per IP, 60 req/min)
_webhook_rate_limit: dict = collections.defaultdict(list)
_WEBHOOK_RATE_MAX = 60
_WEBHOOK_RATE_WINDOW = 60

# Periodic cleanup state for rate-limit dicts
_rate_limit_cleanup_counter = 0
_RATE_LIMIT_CLEANUP_EVERY = 100  # run cleanup every N calls


def _cleanup_rate_limit_dicts():
    """Remove IPs with empty or fully-expired timestamp lists to bound memory."""
    global _rate_limit_cleanup_counter
    _rate_limit_cleanup_counter += 1
    if _rate_limit_cleanup_counter < _RATE_LIMIT_CLEANUP_EVERY:
        return
    _rate_limit_cleanup_counter = 0
    now = time.monotonic()
    for store, window in ((_reschedule_rate_limit, _RATE_LIMIT_WINDOW),
                          (_webhook_rate_limit, _WEBHOOK_RATE_WINDOW)):
        cutoff = now - window
        stale_keys = [ip for ip, ts in store.items()
                      if not ts or all(t <= cutoff for t in ts)]
        for ip in stale_keys:
            del store[ip]


def _check_rate_limit(ip: str) -> bool:
    """Return True if the request is allowed, False if rate limit exceeded.
    Also cleans up old timestamps to avoid memory growth.
    """
    _cleanup_rate_limit_dicts()
    now = time.monotonic()
    window_start = now - _RATE_LIMIT_WINDOW
    timestamps = _reschedule_rate_limit[ip]
    # Drop timestamps outside the current window
    timestamps[:] = [t for t in timestamps if t > window_start]
    if len(timestamps) >= _RATE_LIMIT_MAX:
        return False
    timestamps.append(now)
    return True


def _check_webhook_rate_limit(ip: str) -> bool:
    """Rate limit for public webhook endpoints (60 req/min per IP)."""
    _cleanup_rate_limit_dicts()
    now = time.monotonic()
    window_start = now - _WEBHOOK_RATE_WINDOW
    timestamps = _webhook_rate_limit[ip]
    timestamps[:] = [t for t in timestamps if t > window_start]
    if len(timestamps) >= _WEBHOOK_RATE_MAX:
        return False
    timestamps.append(now)
    return True


def create_app():
    app = Flask(__name__)
    app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024  # 2MB max request size

    # Fix 1 — Log Pub/Sub verification mode at startup
    _pubsub_audience = os.environ.get('PUBSUB_AUDIENCE', '')
    if _pubsub_audience:
        logger.info("Pub/Sub JWT verification: ENABLED (PUBSUB_AUDIENCE=%s)", _pubsub_audience)
    else:
        logger.info("Pub/Sub JWT verification: DISABLED (PUBSUB_AUDIENCE not set — local dev mode)")

    from admin_ui import admin_bp
    app.register_blueprint(admin_bp)

    from admin_pro import admin_pro_bp
    app.register_blueprint(admin_pro_bp)

    # ------------------------------------------------------------------
    # Static assets (banner image etc.)
    # ------------------------------------------------------------------

    # Fix 3 — Whitelist of allowed extensions for static file serving
    _ALLOWED_STATIC_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.css', '.js', '.ico', '.svg', '.webp', '.json'}

    @app.route('/static/<path:filename>')
    def static_files(filename):
        import os as _os
        from flask import send_from_directory, abort
        # Strip any directory traversal attempts and check extension whitelist
        safe_name = _os.path.basename(filename)
        _, ext = _os.path.splitext(safe_name)
        if ext.lower() not in _ALLOWED_STATIC_EXTENSIONS:
            abort(404)
        static_dir = _os.path.join(_os.path.dirname(__file__), 'static')
        return send_from_directory(static_dir, safe_name)

    # ------------------------------------------------------------------
    # Gmail / Pub/Sub webhook
    # ------------------------------------------------------------------

    @app.route('/webhook/gmail', methods=['POST'])
    def gmail_webhook():
        # Webhook rate limit
        client_ip = request.headers.get('X-Forwarded-For', '').split(',')[0].strip() or request.remote_addr or 'unknown'
        if not _check_webhook_rate_limit(client_ip):
            return jsonify({'error': 'Rate limit exceeded'}), 429

        # Optional token check — accepts query param OR X-Webhook-Token header
        if _PUBSUB_TOKEN:
            token = request.args.get('token', '') or request.headers.get('X-Webhook-Token', '')
            if not hmac.compare_digest(token.encode(), _PUBSUB_TOKEN.encode()):
                logger.warning("Gmail webhook: invalid or missing token")
                return 'Unauthorized', 403

        envelope = request.get_json(silent=True)
        if not envelope:
            return 'Bad Request: expected JSON', 400

        # Fix 1 — JWT verification is mandatory when PUBSUB_AUDIENCE is set
        pubsub_audience = os.environ.get('PUBSUB_AUDIENCE', '')
        if pubsub_audience:
            auth_header = request.headers.get('Authorization', '')
            if not auth_header.startswith('Bearer '):
                logger.warning(
                    "Gmail webhook: missing Authorization header (PUBSUB_AUDIENCE is set — rejecting)"
                )
                return jsonify({'error': 'Missing token'}), 403
            token = auth_header[7:]
            try:
                from google.oauth2 import id_token
                from google.auth.transport import requests as grequests
                id_token.verify_oauth2_token(token, grequests.Request(), pubsub_audience)
            except Exception as e:
                logger.warning("Gmail Pub/Sub JWT verification failed: %s", e)
                return jsonify({'error': 'Invalid token'}), 403

        pubsub_message = envelope.get('message', {})
        data_b64 = pubsub_message.get('data', '')
        if not data_b64:
            # Pub/Sub sometimes sends an empty keepalive — acknowledge and ignore
            return 'OK', 200

        try:
            notification = json.loads(base64.b64decode(data_b64).decode('utf-8'))
        except Exception as e:
            logger.error("Gmail webhook: failed to decode Pub/Sub message: %s", e)
            return 'Bad Request: decode failed', 400

        history_id = notification.get('historyId')
        if not history_id:
            return 'OK', 200

        logger.info("Gmail webhook: historyId=%s", history_id)

        try:
            from gmail_poller import process_history_notification
            process_history_notification(history_id)
            try:
                from state_manager import StateManager
                from datetime import datetime, timezone
                StateManager().set_app_state('last_gmail_poll_at', datetime.now(timezone.utc).isoformat())
            except Exception as e:
                # Fix 6 — log instead of silently swallowing
                logger.warning("Failed to update last_gmail_poll_at: %s", e)
        except Exception as e:
            logger.error("Gmail webhook processing error: %s", e, exc_info=True)
            # Return 200 anyway — returning 4xx/5xx causes Pub/Sub to retry

        return 'OK', 200

    # ------------------------------------------------------------------
    # Twilio inbound SMS webhook
    # ------------------------------------------------------------------

    @app.route('/webhook/twilio/sms', methods=['POST'])
    def twilio_sms_webhook():
        # Rate limit on webhook endpoint
        twilio_ip = request.remote_addr or 'unknown'
        if not _check_webhook_rate_limit(twilio_ip):
            return jsonify({'error': 'Rate limit exceeded'}), 429

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

        # Extract MMS image attachments (if any)
        num_media = int(request.form.get('NumMedia', '0') or '0')
        media_items = []
        for i in range(min(num_media, 4)):
            media_url = request.form.get(f'MediaUrl{i}', '')
            media_type = request.form.get(f'MediaContentType{i}', 'image/jpeg')
            if media_url and media_type.startswith('image/'):
                media_items.append({'url': media_url, 'media_type': media_type})

        logger.info("Twilio webhook: SMS from %s SID=%s media=%d", from_number, message_sid, len(media_items))

        try:
            from twilio_handler import process_single_sms_webhook
            process_single_sms_webhook(from_number, body_text, message_sid, media_items=media_items or None)
        except Exception as e:
            logger.error("Twilio webhook processing error: %s", e, exc_info=True)

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
        # Fix 2 — Rate limit per IP
        client_ip = request.remote_addr or '0.0.0.0'
        if not _check_rate_limit(client_ip):
            return (
                "<h2 style='font-family:sans-serif;'>Too many requests.</h2>"
                "<p style='font-family:sans-serif;'>Please wait a moment and try again.</p>",
                429
            )

        from email_utils import verify_reschedule_token
        from state_manager import StateManager
        from maps_handler import get_week_availability, get_job_duration_minutes, _is_business_day
        import json, calendar as _cal
        from html import escape as _esc
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
        current_year = today.year
        month_param = request.args.get('month', today.strftime('%Y-%m'))

        # Fix 4 — Validate month parameter bounds; default to current month/year on error
        try:
            view_year = int(month_param[:4])
            view_month = int(month_param[5:7])
            # Bounds check: year within ±2 of current, month 1–12
            if not (current_year - 1 <= view_year <= current_year + 2) or not (1 <= view_month <= 12):
                raise ValueError("month parameter out of bounds")
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

        customer_name = _esc((bd.get('customer_name') or 'there').split()[0])
        current_date = _esc(bd.get('preferred_date', 'Unknown'))
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
        # Fix 2 — Rate limit per IP (shared counter with reschedule_page)
        client_ip = request.remote_addr or '0.0.0.0'
        if not _check_rate_limit(client_ip):
            return (
                "<h2 style='font-family:sans-serif;'>Too many requests.</h2>"
                "<p style='font-family:sans-serif;'>Please wait a moment and try again.</p>",
                429
            )

        import re, json
        from html import escape as _esc2
        from email_utils import verify_reschedule_token
        from state_manager import StateManager
        from feature_flags import get_flag

        # Validate date format
        if not re.match(r'^\d{4}-\d{2}-\d{2}$', new_date):
            return "<h2>Invalid date.</h2>", 400

        # Validate it's a real calendar date and not in the past
        from datetime import datetime as _dt_val, date as _date_val
        try:
            parsed_date = _dt_val.strptime(new_date, '%Y-%m-%d').date()
        except ValueError:
            return "<h2>Invalid date.</h2>", 400
        if parsed_date < _date_val.today():
            return ("<h2 style='font-family:sans-serif;'>This date is in the past.</h2>"
                    "<p style='font-family:sans-serif;'>Please choose a future date.</p>"), 400

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
        except Exception as e:
            # Fix 6 — log instead of silently swallowing
            logger.warning("Failed to log booking event: %s", e)

        # Notify owner via SMS
        if get_flag('flag_auto_sms_owner'):
            try:
                from twilio_handler import send_sms
                owner_mobile = os.environ.get('OWNER_MOBILE', '')
                if owner_mobile:
                    cust_name = (bd.get('customer_name') or 'Customer')
                    send_sms(owner_mobile,
                        f"Booking {booking_id} rescheduled by customer from {old_date} to {new_date} ({cust_name}). - Wheel Doctor System")
            except Exception as e:
                logger.warning("Owner reschedule SMS failed: %s", e)

        # Send booking change confirmation email to customer
        if get_flag('flag_auto_email_customer'):
            try:
                customer_email = booking.get('customer_email') or bd.get('customer_email')
                if customer_email:
                    from twilio_handler import send_reschedule_change_email
                    send_reschedule_change_email(customer_email, bd, booking_id, old_date, thread_id=booking.get('thread_id'))
            except Exception as e:
                logger.warning("Reschedule change email failed: %s", e)

        # Build a branded success page with a fresh reschedule link
        from email_utils import build_email_html, generate_reschedule_token, _p, _h2, RED, DARK
        from datetime import datetime as _dt2

        try:
            new_date_fmt = _esc2(_dt2.strptime(new_date, '%Y-%m-%d').strftime('%A, %d %B %Y').replace(' 0', ' '))
        except Exception as e:
            logger.warning("Failed to format new_date '%s': %s", new_date, e)
            new_date_fmt = _esc2(new_date)

        customer_name = _esc2((bd.get('customer_name') or 'there').split()[0])

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
        except Exception as e:
            logger.warning("Failed to build reschedule_again link: %s", e)

        page_content = (
            f'<h1 style="color:{RED};font-size:22px;margin:0 0 16px;">Booking Updated</h1>'
            + _p(f'Hi {customer_name}, your booking has been successfully rescheduled to '
                 f'<strong>{new_date_fmt}</strong>.')
            + _p('A confirmation email has been sent to you with the updated details. '
                 'If you have any questions, please reply to your original booking email.')
            + reschedule_again_para
            + f'<p style="margin:24px 0 0;color:{DARK};font-size:15px;">'
              f'Kind regards,<br><strong style="color:{RED};">Wheel Doctor Team</strong></p>'
        )

        return build_email_html(page_content)

    # ------------------------------------------------------------------
    # Customer self-service cancellation (Upgrade 2)
    # ------------------------------------------------------------------

    @app.route('/reschedule/<token>/cancel', methods=['GET'])
    def reschedule_cancel(token):
        """Customer self-service booking cancellation."""
        client_ip = request.remote_addr or '0.0.0.0'
        if not _check_rate_limit(client_ip):
            return "<h2 style='font-family:sans-serif;'>Too many requests.</h2>", 429

        from email_utils import verify_reschedule_token
        from state_manager import StateManager
        from html import escape as _esc
        import json as _json

        booking_id = verify_reschedule_token(token)
        if not booking_id:
            return ("<h2 style='font-family:sans-serif;color:#C41230;'>Link expired or invalid.</h2>"
                    "<p style='font-family:sans-serif;'>Please contact us directly to cancel.</p>"), 400

        state = StateManager()
        confirmed = state.get_confirmed_bookings()
        booking = confirmed.get(booking_id)
        if not booking:
            return ("<h2 style='font-family:sans-serif;'>Booking not found.</h2>"
                    "<p style='font-family:sans-serif;'>This booking may have already been cancelled.</p>"), 404

        bd = booking.get('booking_data', {})
        if isinstance(bd, str):
            bd = _json.loads(bd)

        try:
            state.decline_booking(booking_id)
            state.log_booking_event(booking_id, 'cancelled', actor='customer_self_service',
                                    details={'method': 'reschedule_link'})
        except Exception as e:
            logger.warning("Cancel booking %s failed: %s", booking_id, e)
            return "<h2 style='font-family:sans-serif;'>An error occurred. Please contact us to cancel.</h2>", 500

        # Notify owner
        try:
            from twilio_handler import send_sms
            from feature_flags import get_flag
            owner_mobile = os.environ.get('OWNER_MOBILE', '')
            if owner_mobile and get_flag('flag_auto_sms_owner'):
                cust_name = bd.get('customer_name', 'Customer')
                booked_date = bd.get('preferred_date', '')
                send_sms(owner_mobile,
                         f"CANCELLATION: {cust_name} cancelled booking {booking_id} for {booked_date}. - Wheel Doctor System")
        except Exception as e:
            logger.warning("Owner cancel SMS failed: %s", e)

        cust_name = _esc((bd.get('customer_name') or 'there').split()[0])
        booked_date = _esc(bd.get('preferred_date', ''))
        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Booking Cancelled</title>
<style>
  body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#f8fafc;color:#1e293b;}}
  .wrap{{max-width:480px;margin:64px auto;padding:16px;}}
  .card{{background:#fff;border-radius:12px;box-shadow:0 2px 12px rgba(0,0,0,.08);padding:32px;text-align:center;}}
  h1{{color:#64748b;font-size:22px;margin-bottom:16px;}}p{{color:#475569;line-height:1.6;}}
</style>
</head>
<body><div class="wrap"><div class="card">
  <h1>Booking Cancelled</h1>
  <p>Hi {cust_name}, your booking{' for <strong>' + booked_date + '</strong>' if booked_date else ''} has been cancelled.</p>
  <p style="margin-top:12px;">To rebook, please reply to your original confirmation email.</p>
  <p style="margin-top:24px;color:#94a3b8;font-size:13px;">— Wheel Doctor Team</p>
</div></div></body></html>"""

    # ------------------------------------------------------------------
    # Customer-facing booking form (Upgrade 7)
    # ------------------------------------------------------------------

    @app.route('/book', methods=['GET'])
    def booking_form():
        """Customer-facing booking form — structured input, no AI parsing needed."""
        return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Book a Wheel Repair — Wheel Doctor</title>
<style>
*{box-sizing:border-box;margin:0;padding:0;}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#f8fafc;color:#1e293b;}
.wrap{max-width:560px;margin:32px auto;padding:16px;}
.card{background:#fff;border-radius:12px;box-shadow:0 2px 12px rgba(0,0,0,.08);padding:28px;}
h1{color:#C41230;font-size:24px;margin-bottom:4px;}.subtitle{color:#64748b;font-size:14px;margin-bottom:24px;}
label{display:block;font-size:13px;font-weight:600;color:#374151;margin-bottom:4px;}
input,select,textarea{width:100%;padding:10px 12px;border:1px solid #e2e8f0;border-radius:8px;font-size:14px;
  color:#1e293b;background:#fff;outline:none;transition:border .15s;}
input:focus,select:focus,textarea:focus{border-color:#C41230;}
.row{margin-bottom:16px;}.row-2{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:16px;}
.btn{display:block;width:100%;padding:13px;background:#C41230;color:#fff;border:none;border-radius:8px;
  font-size:16px;font-weight:600;cursor:pointer;margin-top:24px;}
.btn:hover{background:#a31025;}
.section-label{font-size:11px;font-weight:700;color:#94a3b8;text-transform:uppercase;
  letter-spacing:.05em;margin:20px 0 12px;border-bottom:1px solid #f1f5f9;padding-bottom:6px;}
.success{background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;padding:20px;margin-top:16px;display:none;}
.error-msg{background:#fef2f2;border:1px solid #fecaca;border-radius:8px;padding:16px;margin-top:12px;
  color:#991b1b;font-size:14px;display:none;}
</style>
</head>
<body>
<div class="wrap"><div class="card">
<h1>Book a Wheel Repair</h1>
<p class="subtitle">Mobile service — we come to you across Perth metro</p>
<div id="form-error" class="error-msg"></div>
<div id="form-success" class="success">
  <strong style="color:#16a34a;">Booking received!</strong>
  <p style="margin-top:8px;color:#166534;font-size:14px;">We'll be in touch shortly to confirm your appointment.</p>
</div>
<form id="booking-form" onsubmit="submitBooking(event)">
<p class="section-label">Your Details</p>
<div class="row"><label>Full Name *</label><input type="text" name="customer_name" required maxlength="100"></div>
<div class="row-2">
  <div><label>Email *</label><input type="email" name="customer_email" required maxlength="200"></div>
  <div><label>Mobile</label><input type="tel" name="customer_phone" maxlength="20" placeholder="04XX XXX XXX"></div>
</div>
<p class="section-label">Vehicle</p>
<div class="row-2">
  <div><label>Make *</label><input type="text" name="vehicle_make" required maxlength="50" placeholder="e.g. Toyota"></div>
  <div><label>Model *</label><input type="text" name="vehicle_model" required maxlength="50" placeholder="e.g. Camry"></div>
</div>
<div class="row-2">
  <div><label>Colour</label><input type="text" name="vehicle_colour" maxlength="30"></div>
  <div><label>Rims to repair *</label>
    <select name="num_rims" required>
      <option value="">Select...</option>
      <option value="1">1 rim</option><option value="2">2 rims</option>
      <option value="3">3 rims</option><option value="4">4 rims</option>
    </select>
  </div>
</div>
<div class="row"><label>Service Type</label>
  <select name="service_type">
    <option value="Rim Repair">Rim Repair</option>
    <option value="Rim Respray">Rim Respray</option>
    <option value="Rim Repair &amp; Respray">Rim Repair &amp; Respray</option>
  </select>
</div>
<p class="section-label">Location &amp; Timing</p>
<div class="row"><label>Street Address *</label><input type="text" name="address" required maxlength="200" placeholder="e.g. 12 Smith St"></div>
<div class="row"><label>Suburb *</label><input type="text" name="suburb" required maxlength="100"></div>
<div class="row-2">
  <div><label>Preferred Date</label><input type="date" name="preferred_date"></div>
  <div><label>Preferred Time</label>
    <select name="preferred_time">
      <option value="">Flexible</option>
      <option value="08:00">8:00 AM</option><option value="09:00">9:00 AM</option>
      <option value="10:00">10:00 AM</option><option value="11:00">11:00 AM</option>
      <option value="12:00">12:00 PM</option><option value="13:00">1:00 PM</option>
      <option value="14:00">2:00 PM</option>
    </select>
  </div>
</div>
<div class="row"><label>Notes</label><textarea name="notes" rows="3" maxlength="500" placeholder="Details about the damage..."></textarea></div>
<button type="submit" class="btn" id="submit-btn">Request Booking</button>
<p style="font-size:12px;color:#94a3b8;margin-top:12px;text-align:center;">We'll confirm within a few hours via email or SMS.</p>
</form>
</div></div>
<script>
async function submitBooking(e) {
  e.preventDefault();
  const btn = document.getElementById('submit-btn');
  const errDiv = document.getElementById('form-error');
  const successDiv = document.getElementById('form-success');
  btn.disabled = true; btn.textContent = 'Sending...';
  errDiv.style.display = 'none';
  const data = {};
  new FormData(e.target).forEach((v, k) => { data[k] = v; });
  try {
    const resp = await fetch('/book/submit', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(data)});
    const result = await resp.json();
    if (result.ok) { e.target.style.display='none'; successDiv.style.display='block'; }
    else { errDiv.textContent = result.error || 'An error occurred.'; errDiv.style.display='block'; btn.disabled=false; btn.textContent='Request Booking'; }
  } catch(err) { errDiv.textContent='Network error. Please try again.'; errDiv.style.display='block'; btn.disabled=false; btn.textContent='Request Booking'; }
}
</script>
</body></html>"""

    @app.route('/book/submit', methods=['POST'])
    def booking_form_submit():
        """Process the customer booking form submission."""
        import re as _re
        client_ip = request.remote_addr or '0.0.0.0'
        if not _check_rate_limit(client_ip):
            return jsonify({'ok': False, 'error': 'Too many requests. Please wait and try again.'}), 429

        try:
            data = request.get_json(silent=True) or {}
        except Exception:
            return jsonify({'ok': False, 'error': 'Invalid request'}), 400

        # Validate required fields
        required = ['customer_name', 'customer_email', 'vehicle_make', 'vehicle_model', 'num_rims', 'address', 'suburb']
        for field in required:
            if not str(data.get(field, '') or '').strip():
                return jsonify({'ok': False, 'error': f'Please fill in: {field.replace("_", " ")}'}), 400

        # Validate and sanitise
        FIELD_MAX = {'customer_name': 100, 'customer_email': 200, 'customer_phone': 20,
                     'vehicle_make': 50, 'vehicle_model': 50, 'vehicle_colour': 30,
                     'service_type': 50, 'address': 200, 'suburb': 100,
                     'preferred_date': 10, 'preferred_time': 5, 'notes': 500}
        sanitized = {}
        for field, max_len in FIELD_MAX.items():
            val = str(data.get(field, '') or '').strip()
            if len(val) > max_len:
                return jsonify({'ok': False, 'error': f'Field {field} is too long'}), 400
            sanitized[field] = val

        num_rims_raw = str(data.get('num_rims', '') or '').strip()
        if num_rims_raw not in ('1', '2', '3', '4'):
            return jsonify({'ok': False, 'error': 'Invalid number of rims'}), 400

        if not _re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', sanitized['customer_email']):
            return jsonify({'ok': False, 'error': 'Please enter a valid email address'}), 400

        if sanitized['preferred_date'] and not _re.match(r'^\d{4}-\d{2}-\d{2}$', sanitized['preferred_date']):
            return jsonify({'ok': False, 'error': 'Invalid date format'}), 400

        booking_data = {
            **sanitized,
            'num_rims': int(num_rims_raw),
            'service_type': sanitized['service_type'] or 'Rim Repair',
            'preferred_date': sanitized['preferred_date'] or None,
            'preferred_time': sanitized['preferred_time'] or None,
            'confidence': 'high',
            'missing_fields': [],
            'source': 'web_form',
        }

        try:
            from state_manager import StateManager
            from twilio_handler import send_sms

            state = StateManager()
            booking_id = state.save_pending_booking(
                booking_data=booking_data,
                customer_email=sanitized['customer_email'],
                source='web_form'
            )

            # Try to find a slot
            try:
                from maps_handler import find_next_available_slot
                job_address = f"{sanitized['address']}, {sanitized['suburb']} WA"
                target_date = booking_data.get('preferred_date')
                if target_date:
                    day_bookings = (
                        state.get_confirmed_bookings_for_date(target_date)
                        + state.get_pending_bookings_for_date(target_date)
                    )
                    slot_date, slot_time = find_next_available_slot(
                        target_date, job_address, day_bookings,
                        new_booking_data=booking_data
                    )
                    if slot_date and slot_time:
                        booking_data['preferred_date'] = slot_date
                        booking_data['preferred_time'] = slot_time
                        state.update_pending_booking_data(booking_id, booking_data)
            except Exception as e:
                logger.warning("Web form: slot finding failed: %s", e)

            # Notify owner via SMS
            owner_mobile = os.environ.get('OWNER_MOBILE', '')
            if owner_mobile:
                try:
                    msg = (f"NEW WEB BOOKING: {booking_data['customer_name']}, "
                           f"{booking_data['num_rims']}x {booking_data['service_type']}, "
                           f"{sanitized['suburb']}, {booking_data.get('preferred_date', 'TBD')}. "
                           f"Reply YES or NO [ID:{booking_id}] - Wheel Doctor")
                    send_sms(owner_mobile, msg[:160])
                except Exception as e:
                    logger.warning("Web form: owner SMS failed: %s", e)

            logger.info("Web form booking created: %s", booking_id)
            return jsonify({'ok': True, 'booking_id': booking_id})

        except Exception:
            logger.exception("Web form booking creation failed")
            return jsonify({'ok': False, 'error': 'Failed to save booking. Please contact us directly.'}), 500

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
            # Fix 5 — use CLAUDE_MODEL env var instead of hardcoded string
            resp = client.messages.create(
                model=CLAUDE_MODEL,
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
