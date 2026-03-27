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
