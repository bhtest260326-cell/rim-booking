"""
admin_ui.py — Flask blueprint for the owner control panel.

Accessible at:  GET  /admin          — dashboard with toggle switches
                POST /admin/toggle   — flip a single flag

Protection: set ADMIN_TOKEN env var in Railway. Pass the token via the
            X-Admin-Token request header. If ADMIN_TOKEN is not set, no
            auth is required (fine for local dev).
"""

import os
import json
import hmac
import html as _html
import logging
import functools
from datetime import datetime, timedelta
from flask import Blueprint, request, redirect, jsonify, make_response

from feature_flags import FLAGS, get_all_flags, set_flag, get_flag

logger = logging.getLogger(__name__)

ADMIN_TOKEN = os.environ.get('ADMIN_TOKEN', '')

admin_bp = Blueprint('admin', __name__)


# ---------------------------------------------------------------------------
# Basic Auth setup
# ---------------------------------------------------------------------------

_admin_pass = os.environ.get('ADMIN_PASSWORD', '')
_admin_user = os.environ.get('ADMIN_USERNAME', 'admin')

if not _admin_pass:
    logger.critical(
        "ADMIN_PASSWORD env var is not set — admin UI is running WITHOUT Basic Auth protection. "
        "Set ADMIN_PASSWORD in your environment to enable authentication."
    )


def _require_admin_auth(f):
    """Decorator that enforces HTTP Basic Auth on admin routes.

    Skips auth entirely when ADMIN_PASSWORD is not set (local dev convenience),
    but logs a critical warning at startup (see above).
    """
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if _admin_pass:
            auth = request.authorization
            if not (
                auth
                and hmac.compare_digest(auth.username.encode(), _admin_user.encode())
                and hmac.compare_digest(auth.password.encode(), _admin_pass.encode())
            ):
                response = make_response('Unauthorized', 401)
                response.headers['WWW-Authenticate'] = 'Basic realm="Admin"'
                return response
        return f(*args, **kwargs)
    return decorated


# ---------------------------------------------------------------------------
# Legacy token-based auth helper
# ---------------------------------------------------------------------------

def _authorised() -> bool:
    # If Basic Auth is active and the request passed _require_admin_auth, trust it
    if _admin_pass:
        auth = request.authorization
        if auth and hmac.compare_digest(auth.username.encode(), _admin_user.encode()) and hmac.compare_digest(auth.password.encode(), _admin_pass.encode()):
            return True
    if not ADMIN_TOKEN:
        return True
    # Accept token from header or POST body only — never from URL query params
    # (tokens in URLs appear in server logs and browser history)
    tok = (
        request.headers.get('X-Admin-Token') or
        request.form.get('token', '') or
        (request.get_json(silent=True) or {}).get('token', '')
    )
    return hmac.compare_digest(tok, ADMIN_TOKEN)


def _qs() -> str:
    """Kept for template compatibility — returns empty string (token no longer in URL)."""
    return ''


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

def _render_dashboard(flags: dict, pending: list = None) -> str:
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

    pending_cards = ''
    if pending:
        for b in pending:
            bid = b.get('id', '')
            name = _html.escape(str(b.get('name', '—')))
            date = _html.escape(str(b.get('date', '?')))
            time_val = _html.escape(str(b.get('time', '?')))
            address = _html.escape(str(b.get('address', '?')))
            service = _html.escape(str(b.get('service', '?')))
            rims = _html.escape(str(b.get('rims', '?')))
            phone = _html.escape(str(b.get('phone', '')))
            phone_html = f'<div class="desc">&#128222; {phone}</div>' if phone else ''
            pending_cards += f"""
      <div class="pending-card">
        <div class="info">
          <div class="label">{name} <span style="font-size:0.65rem;color:#475569;margin-left:6px;">{bid}</span></div>
          <div class="desc">&#128197; {date} at {time_val} &nbsp;&bull;&nbsp; &#128205; {address}</div>
          <div class="desc">&#128295; {service} &mdash; {rims} rims</div>
          {phone_html}
        </div>
        <div style="margin-top:10px;display:flex;gap:8px;flex-wrap:wrap;align-items:center;">
          <button onclick="confirmBooking('{bid}')" style="background:#22c55e;color:#fff;border:none;padding:6px 16px;border-radius:6px;cursor:pointer;font-weight:600;">&#10003; Confirm</button>
          <button onclick="declineBooking('{bid}')" style="background:#ef4444;color:#fff;border:none;padding:6px 16px;border-radius:6px;cursor:pointer;font-weight:600;">&#10007; Decline</button>
          <button onclick="toggleEditPanel('{bid}')" style="background:#334155;color:#94a3b8;border:1px solid #475569;padding:6px 14px;border-radius:6px;cursor:pointer;font-size:0.78rem;">&#9881; Edit / Notes</button>
        </div>
        <div id="edit-panel-{bid}" style="display:none;margin-top:14px;border-top:1px solid #1e3a5f;padding-top:14px;">
          <div style="font-size:0.65rem;font-weight:700;text-transform:uppercase;letter-spacing:0.1em;color:#475569;margin-bottom:8px;">Notes</div>
          <textarea id="note-text-{bid}" rows="2" placeholder="Add an internal note…" style="width:100%;background:#0f172a;border:1px solid #334155;border-radius:6px;color:#e2e8f0;padding:8px;font-size:0.8rem;resize:vertical;"></textarea>
          <button onclick="saveBookingNote('{bid}', token)" style="margin-top:6px;background:#3b82f6;color:#fff;border:none;padding:5px 14px;border-radius:6px;cursor:pointer;font-size:0.78rem;font-weight:600;">Save Note</button>

          <div style="font-size:0.65rem;font-weight:700;text-transform:uppercase;letter-spacing:0.1em;color:#475569;margin-top:14px;margin-bottom:8px;">Quick Edit</div>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;">
            <div>
              <label style="font-size:0.7rem;color:#64748b;display:block;margin-bottom:3px;">Date</label>
              <input type="date" id="edit-date-{bid}" value="{date}" style="width:100%;background:#0f172a;border:1px solid #334155;border-radius:6px;color:#e2e8f0;padding:6px 8px;font-size:0.8rem;">
            </div>
            <div>
              <label style="font-size:0.7rem;color:#64748b;display:block;margin-bottom:3px;">Time</label>
              <input type="time" id="edit-time-{bid}" value="{time_val}" style="width:100%;background:#0f172a;border:1px solid #334155;border-radius:6px;color:#e2e8f0;padding:6px 8px;font-size:0.8rem;">
            </div>
          </div>
          <div style="margin-top:8px;">
            <label style="font-size:0.7rem;color:#64748b;display:block;margin-bottom:3px;">Suburb / Address</label>
            <input type="text" id="edit-address-{bid}" value="{address}" placeholder="Suburb or full address" style="width:100%;background:#0f172a;border:1px solid #334155;border-radius:6px;color:#e2e8f0;padding:6px 8px;font-size:0.8rem;">
          </div>
          <button onclick="saveBookingEdit('{bid}', token)" style="margin-top:8px;background:#f59e0b;color:#000;border:none;padding:5px 14px;border-radius:6px;cursor:pointer;font-size:0.78rem;font-weight:600;">Save Changes</button>

          <div style="font-size:0.65rem;font-weight:700;text-transform:uppercase;letter-spacing:0.1em;color:#475569;margin-top:14px;margin-bottom:8px;">Decline with Reason</div>
          <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center;">
            <select id="decline-reason-{bid}" style="flex:1;min-width:180px;background:#0f172a;border:1px solid #334155;border-radius:6px;color:#e2e8f0;padding:6px 8px;font-size:0.8rem;">
              <option value="scheduling_conflict">Scheduling Conflict</option>
              <option value="location_too_far">Location Too Far</option>
              <option value="customer_request">Customer Request</option>
              <option value="other">Other</option>
            </select>
            <button onclick="declineWithReason('{bid}', token)" style="background:#7c3aed;color:#fff;border:none;padding:6px 14px;border-radius:6px;cursor:pointer;font-size:0.78rem;font-weight:600;">&#10007; Decline with Reason</button>
          </div>
        </div>
      </div>"""
    else:
        pending_cards = '<div style="color:#475569;font-size:0.8rem;padding:4px 0;">No bookings awaiting approval</div>'

    pending_section = f"""
  <div class="section-label" style="margin-top:24px;">Pending Approval ({len(pending) if pending else 0})</div>
  {pending_cards}"""

    qs = _qs()

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Wheel Doctor — Control Panel</title>
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
    .pending-card {{
      background: #1e293b;
      border: 1px solid #1e3a5f;
      border-radius: 14px;
      padding: 16px;
      margin-bottom: 10px;
    }}
    .pending-card .info {{ flex: 1; min-width: 0; margin-bottom: 6px; }}
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
    /* Analytics */
    .analytics-section {{
      margin-bottom: 28px;
    }}
    .analytics-grid {{
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 10px;
      margin-bottom: 14px;
    }}
    @media(max-width: 700px) {{ .analytics-grid {{ grid-template-columns: repeat(2, 1fr); }} }}
    .a-stat {{
      background: #1e293b;
      border: 1px solid #1e3a5f;
      border-radius: 12px;
      padding: 14px 16px;
    }}
    .a-stat-num {{
      font-size: 1.6rem;
      font-weight: 800;
      color: #3b82f6;
      line-height: 1;
      margin-bottom: 4px;
    }}
    .a-stat-lbl {{
      font-size: 0.65rem;
      color: #64748b;
      text-transform: uppercase;
      letter-spacing: 0.07em;
    }}
    .suburbs-panel {{
      background: #1e293b;
      border: 1px solid #1e3a5f;
      border-radius: 12px;
      padding: 14px 16px;
    }}
    .suburbs-title {{
      font-size: 0.65rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.1em;
      color: #475569;
      margin-bottom: 10px;
    }}
    .suburb-row {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 5px 0;
      border-bottom: 1px solid #1e3a5f;
      font-size: 0.8rem;
    }}
    .suburb-row:last-child {{ border-bottom: none; }}
    .suburb-badge {{
      background: #0f172a;
      color: #3b82f6;
      font-size: 0.7rem;
      font-weight: 700;
      padding: 2px 8px;
      border-radius: 8px;
      border: 1px solid #1e3a5f;
    }}
  </style>
</head>
<body>
  <h1>&#9881; Wheel Doctor Control Panel</h1>
  <p class="sub">Tap a button to switch a feature on or off — takes effect immediately</p>

  <div class="section-label">Analytics</div>
  <div class="analytics-section">
    <div class="analytics-grid">
      <div class="a-stat">
        <div class="a-stat-num" id="an-conversion">—</div>
        <div class="a-stat-lbl">Conversion Rate (%)</div>
      </div>
      <div class="a-stat">
        <div class="a-stat-num" id="an-confirm-time">—</div>
        <div class="a-stat-lbl">Avg Confirm Time (hrs)</div>
      </div>
      <div class="a-stat">
        <div class="a-stat-num" id="an-total-created">—</div>
        <div class="a-stat-lbl">Total Created</div>
      </div>
      <div class="a-stat">
        <div class="a-stat-num" id="an-total-declined">—</div>
        <div class="a-stat-lbl">Total Declined</div>
      </div>
    </div>
    <div class="suburbs-panel">
      <div class="suburbs-title">Top 5 Suburbs</div>
      <div id="an-suburbs"><em style="color:#475569;font-size:0.8rem;">Loading…</em></div>
    </div>
  </div>

  {pending_section}

  <div class="section-label" style="margin-top:24px;">Automation Settings</div>
  {cards}
  <p class="footer">rim-repair-booking &bull; changes are saved to database</p>

<script>
(function() {{
  var qs = '{qs}';
  var token = qs ? qs.replace('?token=', '') : '';

  function confirmBooking(id) {{
    if (!confirm('Confirm booking ' + id + '?')) return;
    fetch('/admin/api/booking/' + id + '/confirm?token=' + token, {{method: 'POST'}})
      .then(function(r) {{ return r.json(); }})
      .then(function(d) {{
        if (d.ok) {{ alert('Booking ' + id + ' confirmed!'); location.reload(); }}
        else {{ alert('Error: ' + d.error); }}
      }});
  }}

  function declineBooking(id) {{
    if (!confirm('Decline booking ' + id + '?')) return;
    fetch('/admin/api/booking/' + id + '/decline?token=' + token, {{method: 'POST'}})
      .then(function(r) {{ return r.json(); }})
      .then(function(d) {{
        if (d.ok) {{ alert('Booking ' + id + ' declined.'); location.reload(); }}
        else {{ alert('Error: ' + d.error); }}
      }});
  }}

  function toggleEditPanel(id) {{
    var panel = document.getElementById('edit-panel-' + id);
    if (panel) {{ panel.style.display = panel.style.display === 'none' ? 'block' : 'none'; }}
  }}

  function saveBookingNote(id, tok) {{
    var noteEl = document.getElementById('note-text-' + id);
    var note = noteEl ? noteEl.value.trim() : '';
    if (!note) {{ alert('Please enter a note.'); return; }}
    fetch('/admin/api/booking/' + id + '/notes?token=' + tok, {{
      method: 'POST',
      headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify({{note: note}})
    }})
      .then(function(r) {{ return r.json(); }})
      .then(function(d) {{
        if (d.ok) {{ alert('Note saved.'); if (noteEl) noteEl.value = ''; }}
        else {{ alert('Error: ' + d.error); }}
      }});
  }}

  function saveBookingEdit(id, tok) {{
    var dateEl    = document.getElementById('edit-date-' + id);
    var timeEl    = document.getElementById('edit-time-' + id);
    var addressEl = document.getElementById('edit-address-' + id);
    var payload = {{}};
    if (dateEl    && dateEl.value.trim())    {{ payload.preferred_date = dateEl.value.trim(); }}
    if (timeEl    && timeEl.value.trim())    {{ payload.preferred_time = timeEl.value.trim(); }}
    if (addressEl && addressEl.value.trim()) {{ payload.address = addressEl.value.trim(); }}
    if (!Object.keys(payload).length) {{ alert('No fields to update.'); return; }}
    fetch('/admin/api/booking/' + id + '/edit?token=' + tok, {{
      method: 'POST',
      headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify(payload)
    }})
      .then(function(r) {{ return r.json(); }})
      .then(function(d) {{
        if (d.ok) {{ alert('Booking updated.'); location.reload(); }}
        else {{ alert('Error: ' + d.error); }}
      }});
  }}

  function declineWithReason(id, tok) {{
    var reasonEl = document.getElementById('decline-reason-' + id);
    var reason = reasonEl ? reasonEl.value : 'other';
    if (!confirm('Decline booking ' + id + ' (' + reason + ')?')) return;
    fetch('/admin/api/booking/' + id + '/decline-with-reason?token=' + tok, {{
      method: 'POST',
      headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify({{reason: reason}})
    }})
      .then(function(r) {{ return r.json(); }})
      .then(function(d) {{
        if (d.ok) {{ alert('Booking declined.'); location.reload(); }}
        else {{ alert('Error: ' + d.error); }}
      }});
  }}

  // Expose to global scope for onclick handlers
  window.confirmBooking = confirmBooking;
  window.declineBooking = declineBooking;
  window.toggleEditPanel = toggleEditPanel;
  window.saveBookingNote = saveBookingNote;
  window.saveBookingEdit = saveBookingEdit;
  window.declineWithReason = declineWithReason;

  // Load analytics
  fetch('/admin/api/analytics' + (token ? '?token=' + token : ''))
    .then(function(r) {{ return r.json(); }})
    .then(function(d) {{
      if (d.error) return;
      document.getElementById('an-conversion').textContent    = d.conversion_rate_pct !== undefined ? d.conversion_rate_pct + '%' : '—';
      document.getElementById('an-confirm-time').textContent  = d.avg_confirm_hours !== null && d.avg_confirm_hours !== undefined ? d.avg_confirm_hours : '—';
      document.getElementById('an-total-created').textContent = d.total_created !== undefined ? d.total_created : '—';
      document.getElementById('an-total-declined').textContent= d.total_declined !== undefined ? d.total_declined : '—';
      var suburbs = d.top_suburbs || [];
      if (suburbs.length) {{
        document.getElementById('an-suburbs').innerHTML = suburbs.map(function(s) {{
          return '<div class="suburb-row"><span>' + s.suburb + '</span><span class="suburb-badge">' + s.count + '</span></div>';
        }}).join('');
      }} else {{
        document.getElementById('an-suburbs').innerHTML = '<div style="color:#475569;font-size:0.8rem;">No data yet</div>';
      }}
    }})
    .catch(function() {{}});
}})();
</script>
</body>
</html>"""


@admin_bp.route('/admin', methods=['GET'])
@_require_admin_auth
def admin_dashboard():
    if not _authorised():
        return (
            '<h2 style="font-family:sans-serif;padding:40px">Unauthorized</h2>'
            '<p style="font-family:sans-serif;padding:0 40px">Add <code>?token=YOUR_TOKEN</code> to the URL.</p>',
            403,
        )
    flags = get_all_flags()

    pending = []
    try:
        from state_manager import StateManager
        state = StateManager()
        with state._conn() as conn:
            pending_rows = conn.execute(
                "SELECT * FROM bookings WHERE status='awaiting_owner' ORDER BY created_at DESC"
            ).fetchall()
        for r in pending_rows:
            bd = json.loads(r['booking_data'] or '{}')
            pending.append({
                'id':      r['id'],
                'name':    bd.get('customer_name', '—'),
                'date':    bd.get('preferred_date', '?'),
                'time':    bd.get('preferred_time', '?'),
                'address': bd.get('address') or bd.get('suburb', '?'),
                'service': (bd.get('service_type') or 'rim_repair').replace('_', ' ').title(),
                'rims':    bd.get('rim_count') or '?',
                'phone':   bd.get('customer_phone', ''),
            })
    except Exception as e:
        logger.warning(f"Could not load pending bookings for dashboard: {e}")

    return _render_dashboard(flags, pending), 200


# ---------------------------------------------------------------------------
# Toggle endpoint
# ---------------------------------------------------------------------------

@admin_bp.route('/admin/toggle', methods=['POST'])
@_require_admin_auth
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
@_require_admin_auth
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
    upcoming.sort(key=lambda x: (x['date'] or '', x['time'] or ''))
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
@_require_admin_auth
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
                if name in ('Pending Reply', 'Awaiting Confirmation', 'Confirmed', 'Declined', 'Processed'):
                    booking_status = name
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
        return jsonify({'messages': [], 'error': 'Internal server error'})


@admin_bp.route('/admin/api/toggle', methods=['POST'])
@_require_admin_auth
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


@admin_bp.route('/admin/api/booking/<booking_id>/confirm', methods=['POST'])
@_require_admin_auth
def api_confirm_booking(booking_id):
    token = request.args.get('token') or request.json.get('token', '') if request.is_json else ''
    if not _authorised():
        return jsonify({'error': 'Unauthorized'}), 401
    try:
        from state_manager import StateManager
        from twilio_handler import handle_owner_confirm
        state = StateManager()
        pending = state.get_pending_booking(booking_id)
        if not pending:
            return jsonify({'error': f'No pending booking {booking_id}'}), 404
        handle_owner_confirm(booking_id, pending)
        return jsonify({'ok': True, 'booking_id': booking_id})
    except Exception as e:
        logger.error(f"Dashboard confirm error: {e}")
        return jsonify({'error': 'Internal server error'}), 500


@admin_bp.route('/admin/api/booking/<booking_id>/decline', methods=['POST'])
@_require_admin_auth
def api_decline_booking(booking_id):
    token = request.args.get('token') or (request.json.get('token', '') if request.is_json else '')
    if not _authorised():
        return jsonify({'error': 'Unauthorized'}), 401
    try:
        from state_manager import StateManager
        from twilio_handler import handle_owner_decline
        state = StateManager()
        pending = state.get_pending_booking(booking_id)
        if not pending:
            return jsonify({'error': f'No pending booking {booking_id}'}), 404
        handle_owner_decline(booking_id, pending)
        return jsonify({'ok': True, 'booking_id': booking_id})
    except Exception as e:
        logger.error(f"Dashboard decline error: {e}")
        return jsonify({'error': 'Internal server error'}), 500


@admin_bp.route('/admin/api/booking/<booking_id>/notes', methods=['POST'])
@_require_admin_auth
def api_booking_add_note(booking_id):
    """Add a timestamped note to a booking."""
    if not _authorised():
        return jsonify({'error': 'Unauthorized'}), 403
    try:
        from state_manager import StateManager
        data = request.get_json(silent=True) or {}
        note = (data.get('note') or '').strip()
        if not note:
            return jsonify({'error': 'Note text is required'}), 400
        state = StateManager()
        state.log_booking_event(booking_id, 'note', actor='owner_ui', details={'text': note})
        return jsonify({'ok': True}), 200
    except Exception as e:
        logger.error(f"api_booking_add_note error: {e}")
        return jsonify({'error': 'Internal server error'}), 500


@admin_bp.route('/admin/api/booking/<booking_id>/edit', methods=['POST'])
@_require_admin_auth
def api_booking_edit(booking_id):
    """Update booking fields (date, time, address, num_rims)."""
    if not _authorised():
        return jsonify({'error': 'Unauthorized'}), 403
    try:
        from state_manager import StateManager
        import json as _json
        data = request.get_json(silent=True) or {}

        state = StateManager()
        with state._conn() as conn:
            row = conn.execute(
                "SELECT booking_data, status FROM bookings WHERE id=?", (booking_id,)
            ).fetchone()
        if not row:
            return jsonify({'error': 'Booking not found'}), 404

        bd = _json.loads(row['booking_data'])
        changed = {}
        for field in ('preferred_date', 'preferred_time', 'address', 'suburb', 'num_rims'):
            if field in data and data[field] is not None and str(data[field]).strip():
                bd[field] = data[field]
                changed[field] = data[field]
        if not changed:
            return jsonify({'error': 'No valid fields provided'}), 400

        with state._conn() as conn:
            conn.execute(
                "UPDATE bookings SET booking_data=? WHERE id=?",
                (_json.dumps(bd), booking_id)
            )
        state.log_booking_event(booking_id, 'fields_edited', actor='owner_ui', details=changed)
        return jsonify({'ok': True, 'changed': changed}), 200
    except Exception as e:
        logger.error(f"api_booking_edit error: {e}")
        return jsonify({'error': 'Internal server error'}), 500


@admin_bp.route('/admin/api/booking/<booking_id>/decline-with-reason', methods=['POST'])
@_require_admin_auth
def api_booking_decline_with_reason(booking_id):
    """Decline a pending booking and record the reason."""
    if not _authorised():
        return jsonify({'error': 'Unauthorized'}), 403
    try:
        from state_manager import StateManager
        data = request.get_json(silent=True) or {}
        reason = (data.get('reason') or 'No reason specified').strip()

        state = StateManager()
        pending = state.get_pending_booking(booking_id)
        if not pending:
            return jsonify({'error': 'Pending booking not found'}), 404

        state.decline_booking(booking_id)
        state.log_booking_event(booking_id, 'declined_with_reason', actor='owner_ui',
                                details={'reason': reason})

        # Notify customer
        import json as _json
        bd = pending.get('booking_data', {})
        if isinstance(bd, str):
            bd = _json.loads(bd)
        customer_phone = bd.get('customer_phone')
        from feature_flags import get_flag
        if customer_phone and get_flag('flag_auto_sms_customer'):
            try:
                from twilio_handler import send_sms
                name = (bd.get('customer_name') or 'there').split()[0]
                send_sms(customer_phone,
                    f"Hi {name}, unfortunately we're unable to accommodate your booking request "
                    f"at this time. Please contact us if you'd like to discuss alternatives. - Wheel Doctor Team")
            except Exception as e:
                logger.warning(f"Could not SMS customer on decline: {e}")

        return jsonify({'ok': True}), 200
    except Exception as e:
        logger.error(f"api_booking_decline_with_reason error: {e}")
        return jsonify({'error': 'Internal server error'}), 500


@admin_bp.route('/admin/api/analytics', methods=['GET'])
@_require_admin_auth
def api_analytics():
    if not _authorised():
        return jsonify({'error': 'Unauthorized'}), 401
    try:
        from state_manager import StateManager, _get_conn
        from datetime import datetime, timezone, timedelta

        state = StateManager()
        now = datetime.now(timezone.utc)

        # Bookings per week (last 8 weeks)
        weeks = []
        for i in range(7, -1, -1):
            week_start = (now - timedelta(weeks=i+1)).strftime('%Y-%m-%d')
            week_end = (now - timedelta(weeks=i)).strftime('%Y-%m-%d')
            with _get_conn() as conn:
                count = conn.execute(
                    "SELECT COUNT(*) FROM bookings WHERE status='confirmed' AND confirmed_at >= ? AND confirmed_at < ?",
                    (week_start, week_end)
                ).fetchone()[0]
            weeks.append({'week_start': week_start, 'count': count})

        # Conversion rate
        with _get_conn() as conn:
            total_created = conn.execute("SELECT COUNT(*) FROM bookings").fetchone()[0]
            total_confirmed = conn.execute("SELECT COUNT(*) FROM bookings WHERE status='confirmed'").fetchone()[0]
            total_declined = conn.execute("SELECT COUNT(*) FROM bookings WHERE status='declined'").fetchone()[0]

        conversion_rate = round(total_confirmed / total_created * 100, 1) if total_created > 0 else 0

        # Top suburbs
        with _get_conn() as conn:
            rows = conn.execute(
                "SELECT booking_data FROM bookings WHERE status='confirmed'"
            ).fetchall()
        suburb_counts = {}
        for row in rows:
            try:
                bd = json.loads(row[0])
                suburb = bd.get('suburb') or bd.get('address', '').split(',')[0].strip()
                if suburb:
                    suburb_counts[suburb] = suburb_counts.get(suburb, 0) + 1
            except Exception:
                pass
        top_suburbs = sorted(suburb_counts.items(), key=lambda x: x[1], reverse=True)[:5]

        # Average time to confirm (hours)
        with _get_conn() as conn:
            rows = conn.execute(
                "SELECT created_at, confirmed_at FROM bookings WHERE status='confirmed' AND created_at IS NOT NULL AND confirmed_at IS NOT NULL LIMIT 50"
            ).fetchall()
        confirm_times = []
        for row in rows:
            try:
                created = datetime.fromisoformat(row[0])
                confirmed = datetime.fromisoformat(row[1])
                hours = (confirmed - created).total_seconds() / 3600
                if 0 < hours < 168:  # ignore outliers > 1 week
                    confirm_times.append(hours)
            except Exception:
                pass
        avg_confirm_hours = round(sum(confirm_times) / len(confirm_times), 1) if confirm_times else None

        return jsonify({
            'bookings_per_week': weeks,
            'conversion_rate_pct': conversion_rate,
            'total_created': total_created,
            'total_confirmed': total_confirmed,
            'total_declined': total_declined,
            'top_suburbs': [{'suburb': _html.escape(s), 'count': c} for s, c in top_suburbs],
            'avg_confirm_hours': avg_confirm_hours,
        })
    except Exception as e:
        logger.error(f"Analytics error: {e}", exc_info=True)
        return jsonify({'error': 'Internal server error'}), 500


@admin_bp.route('/admin/api/booking/<booking_id>/events', methods=['GET'])
@_require_admin_auth
def api_booking_events(booking_id):
    if not _authorised():
        return jsonify({'error': 'Unauthorized'}), 401
    try:
        from state_manager import StateManager
        state = StateManager()
        events = state.get_booking_events(booking_id)
        return jsonify({'booking_id': booking_id, 'events': events})
    except Exception as e:
        logger.exception(f"api_booking_events error for {booking_id}: {e}")
        return jsonify({'error': 'Internal server error'}), 500
