"""health_monitor.py — Daily system health checks with owner alerts (Upgrade 10).

Runs a suite of checks once per day and alerts the owner by SMS + email if any
critical component is degraded. Designed to be called from the scheduler loop.

Checks performed:
  1. Database connectivity and size
  2. Gmail OAuth token validity
  3. Twilio credential validity
  4. Anthropic API reachability
  5. Dead-letter queue depth (alert if > threshold)
  6. Pending booking expiry (alert if bookings stuck > 24h)
"""

import os
import logging
from datetime import date, datetime, timezone

logger = logging.getLogger(__name__)

_LAST_RUN_KEY = 'health_monitor_last_run'
_DLQ_ALERT_THRESHOLD = 5   # alert if more than this many unnotified DLQ entries
_PENDING_STALE_HOURS = 24  # alert if a pending booking is older than this


def run_daily_health_check() -> dict:
    """Run all health checks. Returns a dict of {check_name: status_str}.

    Idempotent — skips if already run today (stored in app_state).
    """
    from state_manager import StateManager
    state = StateManager()

    today = date.today().isoformat()
    last_run = state.get_app_state(_LAST_RUN_KEY)
    if last_run == today:
        return {}  # already ran today

    results = {}
    alerts = []

    # 1. Database
    try:
        from state_manager import _get_conn
        with _get_conn() as conn:
            count = conn.execute("SELECT COUNT(*) FROM bookings").fetchone()[0]
        results['database'] = f'ok ({count} bookings)'
    except Exception as exc:
        results['database'] = f'FAIL: {exc}'
        alerts.append(f"Database error: {exc}")

    # 2. Gmail OAuth
    try:
        from google_auth import get_gmail_service
        svc = get_gmail_service()
        svc.users().getProfile(userId='me').execute()
        results['gmail'] = 'ok'
    except Exception as exc:
        results['gmail'] = f'FAIL: {exc}'
        alerts.append(f"Gmail auth error: {exc}")

    # 3. Twilio
    try:
        from twilio_handler import get_twilio_client
        client = get_twilio_client()
        client.api.accounts(os.environ.get('TWILIO_ACCOUNT_SID', '')).fetch()
        results['twilio'] = 'ok'
    except Exception as exc:
        results['twilio'] = f'FAIL: {exc}'
        alerts.append(f"Twilio error: {exc}")

    # 4. Anthropic API
    try:
        import anthropic
        c = anthropic.Anthropic(api_key=os.environ.get('ANTHROPIC_API_KEY', ''), timeout=10)
        c.messages.create(model='claude-haiku-4-5-20251001', max_tokens=1,
                          messages=[{'role': 'user', 'content': 'ping'}])
        results['anthropic'] = 'ok'
    except Exception as exc:
        results['anthropic'] = f'FAIL: {exc}'
        alerts.append(f"Anthropic API error: {exc}")

    # 5. DLQ depth
    try:
        from state_manager import _get_conn
        with _get_conn() as conn:
            dlq_count = conn.execute(
                "SELECT COUNT(*) FROM failed_extractions WHERE owner_notified=0"
            ).fetchone()[0]
        results['dlq'] = f'{dlq_count} unnotified'
        if dlq_count > _DLQ_ALERT_THRESHOLD:
            alerts.append(f"DLQ has {dlq_count} unnotified entries — check admin panel")
    except Exception as exc:
        results['dlq'] = f'FAIL: {exc}'

    # 6. Stale pending bookings
    try:
        from state_manager import _get_conn
        import json
        with _get_conn() as conn:
            rows = conn.execute(
                "SELECT id, created_at FROM bookings WHERE status='awaiting_owner'"
            ).fetchall()
        stale = []
        now = datetime.now(timezone.utc)
        for row in rows:
            try:
                age_h = (now - datetime.fromisoformat(row['created_at'])).total_seconds() / 3600
                if age_h > _PENDING_STALE_HOURS:
                    stale.append(row['id'])
            except Exception:
                pass
        results['stale_pending'] = f'{len(stale)} stale'
        if stale:
            alerts.append(f"{len(stale)} pending booking(s) stuck > {_PENDING_STALE_HOURS}h: {', '.join(stale[:3])}")
    except Exception as exc:
        results['stale_pending'] = f'FAIL: {exc}'

    # Mark as run
    state.set_app_state(_LAST_RUN_KEY, today)

    # Send alerts if any issues found
    if alerts:
        _send_health_alert(alerts, results)

    logger.info("Daily health check complete: %s", results)
    return results


def _send_health_alert(alerts: list, results: dict) -> None:
    summary = '\n'.join(f'• {a}' for a in alerts)
    full_text = (
        f"Daily health check — {date.today().isoformat()}\n\n"
        f"ISSUES DETECTED:\n{summary}\n\n"
        f"Full results:\n" +
        '\n'.join(f"  {k}: {v}" for k, v in results.items())
    )

    # SMS alert (brief)
    try:
        owner_phone = os.environ.get('OWNER_PHONE', '') or os.environ.get('OWNER_MOBILE', '')
        if owner_phone:
            from twilio_handler import send_sms
            brief = f"[Wheel Doctor Health] {len(alerts)} issue(s) detected: {alerts[0][:100]}"
            send_sms(owner_phone, brief)
    except Exception as exc:
        logger.error("Health alert SMS failed: %s", exc)

    # Email alert (detailed)
    try:
        owner_email = os.environ.get('OWNER_EMAIL', '')
        if not owner_email:
            return
        from google_auth import get_gmail_service
        from email.mime.text import MIMEText
        import base64
        msg = MIMEText(full_text)
        msg['to'] = owner_email
        msg['subject'] = f'[Wheel Doctor] Health alert — {len(alerts)} issue(s)'
        svc = get_gmail_service()
        svc.users().messages().send(
            userId='me',
            body={'raw': base64.urlsafe_b64encode(msg.as_bytes()).decode()}
        ).execute()
        logger.info("Health alert email sent to %s", owner_email)
    except Exception as exc:
        logger.error("Health alert email failed: %s", exc)
