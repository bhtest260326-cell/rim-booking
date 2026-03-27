"""
admin_ui.py — Flask blueprint for the owner control panel.

Accessible at:  GET  /admin          — dashboard with toggle switches
                POST /admin/toggle   — flip a single flag

Protection: set ADMIN_TOKEN env var in Railway. Access the page at
            https://your-app.railway.app/admin?token=YOUR_TOKEN
            and bookmark that URL. If ADMIN_TOKEN is not set, no auth
            is required (fine for local dev).
"""

import os
import json
import logging
from datetime import datetime, timedelta
from flask import Blueprint, request, redirect, jsonify

from feature_flags import FLAGS, get_all_flags, set_flag, get_flag

logger = logging.getLogger(__name__)

ADMIN_TOKEN = os.environ.get('ADMIN_TOKEN', '')

admin_bp = Blueprint('admin', __name__)


# ---------------------------------------------------------------------------
# Auth helper
# ---------------------------------------------------------------------------

def _authorised() -> bool:
    if not ADMIN_TOKEN:
        return True
    tok = request.args.get('token') or request.form.get('token', '')
    return tok == ADMIN_TOKEN


def _qs() -> str:
    """Return ?token=… query string to preserve auth across page loads."""
    return f'?token={ADMIN_TOKEN}' if ADMIN_TOKEN else ''


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

def _render_dashboard(flags: dict) -> str:
    cards = ''
    for key, data in flags.items():
        on = data['enabled']
        btn_color = '#22c55e' if on else '#ef4444'
        btn_label = 'ON' if on else 'OFF'
        cards += f"""
      <div class="card">
        <div class="info">
          <div class="label">{data['label']}</div>
          <div class="desc">{data['description']}</div>
        </div>
        <form method="POST" action="/admin/toggle{_qs()}">
          <input type="hidden" name="key" value="{key}">
          <button type="submit" class="btn" style="background:{btn_color}">{btn_label}</button>
        </form>
      </div>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Rim Repair — Control Panel</title>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      background: #0f172a;
      color: #e2e8f0;
      min-height: 100vh;
      padding: 24px 16px 40px;
    }}
    h1 {{
      font-size: 1.25rem;
      font-weight: 700;
      color: #f8fafc;
      letter-spacing: -0.01em;
    }}
    .sub {{
      font-size: 0.78rem;
      color: #64748b;
      margin-top: 2px;
      margin-bottom: 28px;
    }}
    .section-label {{
      font-size: 0.65rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.1em;
      color: #475569;
      margin-bottom: 10px;
    }}
    .card {{
      background: #1e293b;
      border: 1px solid #1e3a5f;
      border-radius: 14px;
      padding: 16px;
      margin-bottom: 10px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 14px;
    }}
    .info {{ flex: 1; min-width: 0; }}
    .label {{
      font-size: 0.9rem;
      font-weight: 600;
      color: #f1f5f9;
      margin-bottom: 3px;
      line-height: 1.3;
    }}
    .desc {{
      font-size: 0.73rem;
      color: #94a3b8;
      line-height: 1.4;
    }}
    .btn {{
      border: none;
      border-radius: 10px;
      color: #fff;
      font-weight: 700;
      font-size: 0.82rem;
      padding: 10px 18px;
      cursor: pointer;
      white-space: nowrap;
      min-width: 52px;
      -webkit-tap-highlight-color: transparent;
    }}
    .btn:active {{ opacity: 0.75; transform: scale(0.97); }}
    .footer {{
      text-align: center;
      font-size: 0.68rem;
      color: #1e293b;
      margin-top: 32px;
    }}
  </style>
</head>
<body>
  <h1>&#9881; Rim Repair Control Panel</h1>
  <p class="sub">Tap a button to switch a feature on or off — takes effect immediately</p>
  <div class="section-label">Automation Settings</div>
  {cards}
  <p class="footer">rim-repair-booking &bull; changes are saved to database</p>
</body>
</html>"""


@admin_bp.route('/admin', methods=['GET'])
def admin_dashboard():
    if not _authorised():
        return (
            '<h2 style="font-family:sans-serif;padding:40px">Unauthorized</h2>'
            '<p style="font-family:sans-serif;padding:0 40px">Add <code>?token=YOUR_TOKEN</code> to the URL.</p>',
            403,
        )
    flags = get_all_flags()
    return _render_dashboard(flags), 200


# ---------------------------------------------------------------------------
# Toggle endpoint
# ---------------------------------------------------------------------------

@admin_bp.route('/admin/toggle', methods=['POST'])
def admin_toggle():
    if not _authorised():
        return 'Unauthorized', 403

    key = request.form.get('key', '')
    if key not in FLAGS:
        return 'Bad Request: unknown flag', 400

    new_state = not get_flag(key)
    set_flag(key, new_state)
    logger.info(f"Admin: flag '{key}' → {'ON' if new_state else 'OFF'}")

    return redirect(f'/admin{_qs()}')


# ---------------------------------------------------------------------------
# JSON API — consumed by the local dashboard app
# ---------------------------------------------------------------------------

@admin_bp.route('/admin/api/data', methods=['GET'])
def api_data():
    if not _authorised():
        return jsonify({'error': 'Unauthorized'}), 403

    from state_manager import StateManager

    state = StateManager()
    flags = get_all_flags()

    # Pending bookings
    with state._conn() as conn:
        pending_rows = conn.execute(
            "SELECT * FROM bookings WHERE status='awaiting_owner' ORDER BY created_at DESC"
        ).fetchall()

    def _card(row, bd):
        return {
            'id':      row['id'],
            'name':    bd.get('customer_name', '—'),
            'date':    bd.get('preferred_date', '?'),
            'time':    bd.get('preferred_time', '?'),
            'address': bd.get('address') or bd.get('suburb', '?'),
            'service': (bd.get('service_type') or 'rim_repair').replace('_', ' ').title(),
            'rims':    bd.get('rim_count') or '?',
            'phone':   bd.get('customer_phone', ''),
            'email':   row['customer_email'] or '',
        }

    pending = [_card(r, json.loads(r['booking_data'] or '{}')) for r in pending_rows]

    today     = datetime.now().strftime('%Y-%m-%d')
    confirmed = state.get_confirmed_bookings()
    upcoming  = []
    for bid, b in confirmed.items():
        bd   = b.get('booking_data', {})
        date = bd.get('preferred_date', '')
        if date >= today:
            row = {'id': bid, 'customer_email': b.get('customer_email', '')}
            upcoming.append(_card(row, bd))
    upcoming.sort(key=lambda x: (x['date'], x['time']))
    today_jobs = [u for u in upcoming if u['date'] == today]

    # Workflow pipeline counts
    with state._conn() as conn:
        emails_received      = conn.execute("SELECT COUNT(*) FROM processed_emails").fetchone()[0]
        clarifications_pending = conn.execute("SELECT COUNT(*) FROM clarifications").fetchone()[0]
        total_confirmed      = conn.execute("SELECT COUNT(*) FROM bookings WHERE status='confirmed'").fetchone()[0]
        total_declined       = conn.execute("SELECT COUNT(*) FROM bookings WHERE status='declined'").fetchone()[0]
        calendar_events      = conn.execute(
            "SELECT COUNT(*) FROM bookings WHERE status='confirmed' AND calendar_event_id IS NOT NULL AND calendar_event_id != ''"
        ).fetchone()[0]
        ai_extracted = conn.execute("SELECT COUNT(*) FROM bookings").fetchone()[0] + clarifications_pending

    return jsonify({
        'flags':      flags,
        'pending':    pending,
        'upcoming':   upcoming,
        'today_jobs': today_jobs,
        'stats': {
            'pending':  len(pending),
            'today':    len(today_jobs),
            'upcoming': len(upcoming),
        },
        'workflow': {
            'emails_received':       emails_received,
            'ai_extracted':          ai_extracted,
            'clarifications_pending': clarifications_pending,
            'awaiting_owner':        len(pending),
            'confirmed':             total_confirmed,
            'declined':              total_declined,
            'calendar_events':       calendar_events,
        },
    })


@admin_bp.route('/admin/api/gmail', methods=['GET'])
def api_gmail():
    """Return the last 25 Gmail inbox messages with booking status labels."""
    if not _authorised():
        return jsonify({'error': 'Unauthorized'}), 403
    try:
        from google_auth import get_gmail_service
        service = get_gmail_service()

        # Build label ID → name map (needed to resolve custom label IDs)
        labels_result = service.users().labels().list(userId='me').execute()
        label_map = {l['id']: l['name'] for l in labels_result.get('labels', [])}

        results = service.users().messages().list(
            userId='me', labelIds=['INBOX'], maxResults=25
        ).execute()
        raw_msgs = results.get('messages', [])

        inbox = []
        for msg in raw_msgs:
            m = service.users().messages().get(
                userId='me', id=msg['id'], format='metadata',
                metadataHeaders=['From', 'Subject', 'Date']
            ).execute()
            headers   = {h['name']: h['value'] for h in m.get('payload', {}).get('headers', [])}
            label_ids = m.get('labelIds', [])

            booking_status = None
            for lid in label_ids:
                name = label_map.get(lid, '')
                if name.startswith('Rim Repairs/'):
                    booking_status = name[len('Rim Repairs/'):]
                    break

            inbox.append({
                'id':             msg['id'],
                'thread_id':      m.get('threadId', ''),
                'from':           headers.get('From', ''),
                'subject':        headers.get('Subject', '(no subject)'),
                'date':           headers.get('Date', ''),
                'snippet':        m.get('snippet', ''),
                'is_unread':      'UNREAD' in label_ids,
                'booking_status': booking_status,
            })

        return jsonify({'messages': inbox, 'error': None})
    except Exception as e:
        logger.error(f"Gmail inbox API error: {e}")
        return jsonify({'messages': [], 'error': str(e)})


@admin_bp.route('/admin/api/toggle', methods=['POST'])
def api_toggle():
    """JSON toggle endpoint used by the local dashboard."""
    if not _authorised():
        return jsonify({'error': 'Unauthorized'}), 403

    body = request.get_json(silent=True) or {}
    key  = body.get('key', '')
    if key not in FLAGS:
        return jsonify({'error': 'Unknown flag'}), 400

    new_state = not get_flag(key)
    set_flag(key, new_state)
    logger.info(f"API toggle: '{key}' → {'ON' if new_state else 'OFF'}")
    return jsonify({'success': True, 'enabled': new_state})
