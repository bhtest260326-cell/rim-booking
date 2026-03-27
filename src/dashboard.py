"""
Local Rim Repair Dashboard — double-click 'Start Dashboard.bat' to open.
Reads from the local SQLite database by default.
Set railway_url in dashboard_config.json to pull live data from Railway instead.
"""
import os
import sys
import json
import threading
import webbrowser
import time
import logging
from datetime import datetime, timedelta

# ── On Windows, redirect the default Linux DB path to a local folder ───────
if sys.platform == 'win32':
    _DEFAULT_SF = '/data/booking_state.json'
    if os.environ.get('STATE_FILE', _DEFAULT_SF) == _DEFAULT_SF:
        _PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        os.environ['STATE_FILE'] = os.path.join(_PROJ, 'data', 'booking_state.json')

from flask import Flask, request, jsonify, redirect

logging.basicConfig(level=logging.WARNING)

# ── Paths ───────────────────────────────────────────────────────────────────
_PROJ_ROOT  = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(_PROJ_ROOT, 'dashboard_config.json')
PORT        = 5001

app = Flask(__name__)


# ── Config helpers ──────────────────────────────────────────────────────────
def _load_cfg():
    try:
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH) as f:
                return json.load(f)
    except Exception:
        pass
    return {'railway_url': '', 'admin_token': ''}


def _save_cfg(d):
    with open(CONFIG_PATH, 'w') as f:
        json.dump(d, f, indent=2)


# ── Data layer ──────────────────────────────────────────────────────────────
def _booking_card(row_dict, bd):
    return {
        'id':         row_dict.get('id', '?'),
        'name':       bd.get('customer_name', '—'),
        'date':       bd.get('preferred_date', '?'),
        'time':       bd.get('preferred_time', '?'),
        'address':    bd.get('address') or bd.get('suburb', '?'),
        'service':    (bd.get('service_type') or 'rim_repair').replace('_', ' ').title(),
        'rims':       bd.get('rim_count') or '?',
        'phone':      bd.get('customer_phone', ''),
        'email':      row_dict.get('customer_email', ''),
        'created':    (row_dict.get('created_at') or '')[:10],
    }


def _local_data():
    from feature_flags import get_all_flags
    from state_manager import StateManager

    state = StateManager()
    flags = get_all_flags()

    with state._conn() as conn:
        pending_rows = conn.execute(
            "SELECT * FROM bookings WHERE status='awaiting_owner' ORDER BY created_at DESC"
        ).fetchall()

    pending = [_booking_card(dict(r), json.loads(dict(r).get('booking_data', '{}')))
               for r in pending_rows]

    today   = datetime.now().strftime('%Y-%m-%d')
    confirmed = state.get_confirmed_bookings()

    upcoming = []
    for bid, b in confirmed.items():
        bd   = b.get('booking_data', {})
        date = bd.get('preferred_date', '')
        if date >= today:
            row = dict(b)
            row['id'] = bid
            upcoming.append(_booking_card(row, bd))
    upcoming.sort(key=lambda x: (x['date'], x['time']))

    today_jobs = [u for u in upcoming if u['date'] == today]

    return {
        'flags':      flags,
        'pending':    pending,
        'upcoming':   upcoming,
        'today_jobs': today_jobs,
        'stats':      {'pending': len(pending), 'today': len(today_jobs), 'upcoming': len(upcoming)},
        'mode':       'Local Database',
        'error':      None,
    }


def _railway_data(url, token):
    try:
        import requests
        qs = f'?token={token}' if token else ''
        r  = requests.get(f'{url}/admin/api/data{qs}', timeout=8)
        if r.status_code == 200:
            d = r.json()
            d['mode']  = 'Railway (live)'
            d['error'] = None
            return d
        return _err_data('Railway', f'Server returned {r.status_code}')
    except Exception as e:
        return _err_data('Railway', str(e))


def _err_data(mode, msg):
    return {
        'flags': {}, 'pending': [], 'upcoming': [], 'today_jobs': [],
        'stats': {'pending': 0, 'today': 0, 'upcoming': 0},
        'mode': mode, 'error': msg,
    }


def get_data():
    cfg   = _load_cfg()
    url   = cfg.get('railway_url', '').strip().rstrip('/')
    token = cfg.get('admin_token', '').strip()
    if url:
        return _railway_data(url, token)
    try:
        return _local_data()
    except Exception as e:
        return _err_data('Local Database', str(e))


# ── HTML template ───────────────────────────────────────────────────────────
_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Rim Repair — Control Centre</title>
<style>
:root {
  --bg:#07111f; --surface:#0d1f35; --card:#112240; --border:#1a3a5c;
  --accent:#3b82f6; --green:#22c55e; --red:#ef4444; --amber:#f59e0b;
  --purple:#8b5cf6; --teal:#14b8a6; --orange:#f97316;
  --text:#f1f5f9; --muted:#64748b; --subtle:#1e3a5c;
  --radius:14px;
}
*{box-sizing:border-box;margin:0;padding:0;}
body{background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;min-height:100vh;}

/* ─ Header ─ */
.header{background:linear-gradient(135deg,#0d1f35,#0a1628);border-bottom:1px solid var(--border);padding:12px 24px;display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;position:sticky;top:0;z-index:100;}
.header-left{display:flex;align-items:center;gap:12px;}
.logo{width:38px;height:38px;background:linear-gradient(135deg,var(--accent),#6366f1);border-radius:10px;display:flex;align-items:center;justify-content:center;font-size:18px;flex-shrink:0;}
.title{font-size:1.1rem;font-weight:700;}
.subtitle{font-size:0.7rem;color:var(--muted);margin-top:1px;}
.header-right{display:flex;align-items:center;gap:8px;}
.badge{display:inline-flex;align-items:center;gap:5px;padding:4px 10px;border-radius:20px;font-size:0.72rem;font-weight:600;}
.badge-green{background:rgba(34,197,94,.15);color:var(--green);border:1px solid rgba(34,197,94,.3);}
.badge-red{background:rgba(239,68,68,.15);color:var(--red);border:1px solid rgba(239,68,68,.3);}
.dot{width:7px;height:7px;border-radius:50%;}
.dot-green{background:var(--green);animation:pulse-dot 2s infinite;}
.dot-red{background:var(--red);}
@keyframes pulse-dot{0%,100%{opacity:1}50%{opacity:.3}}
.btn-hdr{background:var(--subtle);border:1px solid var(--border);color:var(--muted);padding:6px 12px;border-radius:8px;font-size:0.78rem;cursor:pointer;transition:.15s;display:flex;align-items:center;gap:5px;}
.btn-hdr:hover{color:var(--text);border-color:var(--accent);}
.btn-hdr.loading{color:var(--accent);}

/* ─ Container ─ */
.container{max-width:1400px;margin:0 auto;padding:20px 20px 60px;}

/* ─ Error ─ */
.error-banner{background:rgba(239,68,68,.1);border:1px solid rgba(239,68,68,.3);color:#fca5a5;border-radius:10px;padding:12px 16px;margin-bottom:18px;font-size:0.82rem;}

/* ─ Setup ─ */
.setup-panel{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);padding:20px;margin-bottom:18px;}
.setup-title{font-size:0.85rem;font-weight:700;margin-bottom:4px;}
.setup-sub{font-size:0.72rem;color:var(--muted);margin-bottom:16px;line-height:1.5;}
.form-label{font-size:0.7rem;font-weight:600;color:var(--muted);text-transform:uppercase;letter-spacing:.05em;margin-bottom:4px;display:block;}
.form-input{width:100%;background:var(--surface);border:1px solid var(--border);color:var(--text);padding:9px 12px;border-radius:8px;font-size:0.85rem;outline:none;}
.form-input:focus{border-color:var(--accent);}
.form-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:14px;}
@media(max-width:600px){.form-grid{grid-template-columns:1fr;}}
.btn-save{background:var(--accent);color:#fff;border:none;padding:9px 20px;border-radius:8px;font-weight:600;font-size:0.83rem;cursor:pointer;width:100%;transition:.15s;}
.btn-save:hover{opacity:.85;}
.btn-clear{background:transparent;color:var(--red);border:1px solid rgba(239,68,68,.4);padding:9px 20px;border-radius:8px;font-size:0.83rem;cursor:pointer;width:100%;margin-top:6px;transition:.15s;}
.btn-clear:hover{background:rgba(239,68,68,.1);}

/* ─ Stats ─ */
.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:18px;}
@media(max-width:900px){.stats{grid-template-columns:repeat(2,1fr);}}
@media(max-width:500px){.stats{grid-template-columns:1fr 1fr;}}
.stat{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);padding:16px 18px;display:flex;align-items:center;gap:14px;}
.stat-icon{width:42px;height:42px;border-radius:10px;display:flex;align-items:center;justify-content:center;font-size:18px;flex-shrink:0;}
.si-amber{background:rgba(245,158,11,.15);}
.si-green{background:rgba(34,197,94,.15);}
.si-blue{background:rgba(59,130,246,.15);}
.si-purple{background:rgba(139,92,246,.15);}
.stat-num{font-size:1.9rem;font-weight:800;line-height:1;}
.stat-lbl{font-size:0.68rem;color:var(--muted);text-transform:uppercase;letter-spacing:.05em;margin-top:2px;}
.c-amber{color:var(--amber);}
.c-green{color:var(--green);}
.c-blue{color:var(--accent);}
.c-purple{color:var(--purple);}

/* ─ Pipeline ─ */
.pipeline{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);padding:20px;margin-bottom:18px;}
.pipeline-head{display:flex;align-items:center;justify-content:space-between;margin-bottom:18px;}
.pipeline-title{font-size:0.82rem;font-weight:700;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);}
.pipeline-sub{font-size:0.68rem;color:var(--muted);margin-top:2px;}
.stages{display:flex;align-items:stretch;gap:0;overflow-x:auto;padding-bottom:4px;}
.stages::-webkit-scrollbar{height:4px;}
.stages::-webkit-scrollbar-track{background:var(--surface);border-radius:2px;}
.stages::-webkit-scrollbar-thumb{background:var(--border);border-radius:2px;}
.stage{flex:1;min-width:110px;background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:14px 10px;text-align:center;transition:.2s;cursor:default;}
.stage:hover{border-color:var(--accent);transform:translateY(-2px);}
.stage.active{border-color:var(--amber);background:rgba(245,158,11,.06);animation:stage-pulse 3s infinite;}
@keyframes stage-pulse{0%,100%{box-shadow:0 0 0 0 rgba(245,158,11,0)}50%{box-shadow:0 0 0 4px rgba(245,158,11,.15)}}
.stage-ico{font-size:1.4rem;margin-bottom:8px;display:block;}
.stage-num{font-size:1.5rem;font-weight:800;line-height:1;margin-bottom:4px;display:block;}
.stage-name{font-size:0.7rem;font-weight:700;color:var(--text);margin-bottom:2px;display:block;}
.stage-sub{font-size:0.6rem;color:var(--muted);display:block;}
.sarrow{display:flex;align-items:center;padding:0 5px;color:var(--border);font-size:1.1rem;flex-shrink:0;align-self:center;}
.pipeline-bar{margin-top:16px;height:3px;border-radius:2px;background:linear-gradient(90deg,var(--accent),var(--purple),var(--amber),var(--orange),var(--green),var(--teal));opacity:.35;}

/* ─ Layout ─ */
.main-grid{display:grid;grid-template-columns:300px 1fr;gap:18px;margin-bottom:18px;align-items:start;}
@media(max-width:900px){.main-grid{grid-template-columns:1fr;}}
.right-col{display:flex;flex-direction:column;gap:16px;}

/* ─ Panels ─ */
.panel{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);overflow:hidden;}
.panel-header{padding:13px 18px;border-bottom:1px solid var(--border);display:flex;align-items:center;justify-content:space-between;gap:8px;}
.panel-title{font-size:0.8rem;font-weight:700;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);}
.panel-count{background:var(--subtle);color:var(--accent);font-size:0.7rem;font-weight:700;padding:2px 8px;border-radius:10px;}

/* ─ Flags ─ */
.flag-row{display:flex;align-items:center;justify-content:space-between;padding:13px 18px;border-bottom:1px solid var(--border);gap:12px;cursor:pointer;transition:.1s;}
.flag-row:last-child{border-bottom:none;}
.flag-row:hover{background:rgba(255,255,255,.03);}
.flag-label{font-size:0.87rem;font-weight:600;margin-bottom:2px;}
.flag-desc{font-size:0.7rem;color:var(--muted);line-height:1.4;}
.switch{position:relative;display:inline-block;width:46px;height:25px;flex-shrink:0;}
.switch input{opacity:0;width:0;height:0;pointer-events:none;}
.slider{position:absolute;cursor:pointer;inset:0;background:var(--red);border-radius:26px;transition:.25s;}
.slider:before{position:absolute;content:"";height:19px;width:19px;left:3px;bottom:3px;background:#fff;border-radius:50%;transition:.25s;}
input:checked+.slider{background:var(--green);}
input:checked+.slider:before{transform:translateX(21px);}

/* ─ Booking cards ─ */
.booking-list{padding:8px;}
.bcard{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:13px;margin-bottom:8px;transition:.15s;}
.bcard:last-child{margin-bottom:0;}
.bcard:hover{border-color:var(--accent);}
.bcard-top{display:flex;align-items:center;justify-content:space-between;margin-bottom:7px;}
.bcard-name{font-size:0.93rem;font-weight:700;}
.bcard-id{font-size:0.63rem;color:var(--muted);background:var(--subtle);padding:2px 6px;border-radius:6px;}
.bcard-row{display:flex;gap:14px;flex-wrap:wrap;margin-bottom:3px;}
.bcard-item{font-size:0.73rem;color:var(--muted);display:flex;align-items:center;gap:4px;}
.bcard-item span{color:var(--text);}
.empty{text-align:center;padding:30px 20px;color:var(--muted);font-size:0.8rem;line-height:1.6;}

/* ─ Gmail ─ */
.gmail-panel{margin-bottom:20px;}
.panel-hdr-right{display:flex;align-items:center;gap:8px;}
.btn-sm{background:var(--subtle);border:1px solid var(--border);color:var(--muted);padding:4px 10px;border-radius:6px;font-size:0.7rem;cursor:pointer;transition:.15s;}
.btn-sm:hover{color:var(--text);border-color:var(--accent);}
.gmail-row{display:flex;align-items:center;gap:12px;padding:11px 18px;border-bottom:1px solid var(--border);transition:.1s;}
.gmail-row:last-child{border-bottom:none;}
.gmail-row:hover{background:rgba(255,255,255,.02);}
.gmail-row.unread .gmail-from,.gmail-row.unread .gmail-subject{font-weight:700;color:var(--text);}
.gmail-avatar{width:34px;height:34px;border-radius:50%;background:var(--subtle);display:flex;align-items:center;justify-content:center;font-size:0.78rem;font-weight:700;color:var(--accent);flex-shrink:0;text-transform:uppercase;}
.gmail-main{flex:1;min-width:0;}
.gmail-from{font-size:0.8rem;color:var(--muted);margin-bottom:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
.gmail-subject{font-size:0.84rem;color:var(--muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin-bottom:2px;}
.gmail-snippet{font-size:0.72rem;color:var(--muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;opacity:.65;}
.gmail-right{display:flex;flex-direction:column;align-items:flex-end;gap:5px;flex-shrink:0;min-width:80px;}
.gmail-time{font-size:0.68rem;color:var(--muted);}
.spill{padding:2px 8px;border-radius:20px;font-size:0.6rem;font-weight:700;white-space:nowrap;}
.spill-confirmed{background:rgba(22,167,102,.2);color:#4ade80;border:1px solid rgba(22,167,102,.3);}
.spill-awaiting{background:rgba(255,173,71,.2);color:var(--amber);border:1px solid rgba(255,173,71,.3);}
.spill-pending{background:rgba(239,68,68,.2);color:#f87171;border:1px solid rgba(239,68,68,.3);}
.spill-declined{background:rgba(139,92,246,.2);color:#a78bfa;border:1px solid rgba(139,92,246,.3);}
.spill-processed{background:rgba(100,116,139,.2);color:var(--muted);border:1px solid rgba(100,116,139,.3);}

/* ─ Misc ─ */
.refresh-bar{text-align:right;font-size:0.67rem;color:var(--muted);margin-bottom:14px;}
@keyframes spin{to{transform:rotate(360deg)}}
.spin{display:inline-block;animation:spin .7s linear infinite;}
</style>
</head>
<body>

<div class="header">
  <div class="header-left">
    <div class="logo">&#9881;</div>
    <div>
      <div class="title">Rim Repair Control Centre</div>
      <div class="subtitle" id="mode-label">Loading…</div>
    </div>
  </div>
  <div class="header-right">
    <span class="badge badge-red" id="conn-badge">
      <span class="dot dot-red" id="conn-dot"></span>
      <span id="conn-text">…</span>
    </span>
    <button class="btn-hdr" id="refresh-btn" onclick="refreshAll()">&#8635; Refresh</button>
    <button class="btn-hdr" onclick="toggleSetup()">&#9965; Setup</button>
  </div>
</div>

<div class="container">

  <div class="error-banner" id="error-banner" style="display:none"></div>

  <!-- Setup -->
  <div class="setup-panel" id="setup-panel" style="display:none">
    <div class="setup-title">Railway Connection</div>
    <div class="setup-sub">Connect to your live Railway deployment for real-time bookings, Gmail inbox, and remote controls. Leave blank to use the local database only.</div>
    <div class="form-grid">
      <div><label class="form-label">Railway URL</label>
        <input class="form-input" id="inp-url" placeholder="https://your-app.railway.app" type="url"></div>
      <div><label class="form-label">Admin Token</label>
        <input class="form-input" id="inp-token" placeholder="ADMIN_TOKEN value" type="password"></div>
    </div>
    <button class="btn-save" onclick="saveSetup()">Save &amp; Connect</button>
    <button class="btn-clear" onclick="clearSetup()">Clear (use local database)</button>
  </div>

  <!-- Stats -->
  <div class="stats">
    <div class="stat">
      <div class="stat-icon si-amber">&#9203;</div>
      <div><div class="stat-num c-amber" id="s-pending">—</div><div class="stat-lbl">Pending Approval</div></div>
    </div>
    <div class="stat">
      <div class="stat-icon si-green">&#128295;</div>
      <div><div class="stat-num c-green" id="s-today">—</div><div class="stat-lbl">Jobs Today</div></div>
    </div>
    <div class="stat">
      <div class="stat-icon si-blue">&#128197;</div>
      <div><div class="stat-num c-blue" id="s-upcoming">—</div><div class="stat-lbl">Upcoming Jobs</div></div>
    </div>
    <div class="stat">
      <div class="stat-icon si-purple">&#9989;</div>
      <div><div class="stat-num c-purple" id="s-confirmed">—</div><div class="stat-lbl">Total Confirmed</div></div>
    </div>
  </div>

  <div class="refresh-bar">Last updated: <span id="last-updated">—</span></div>

  <!-- AI Pipeline -->
  <div class="pipeline">
    <div class="pipeline-head">
      <div>
        <div class="pipeline-title">&#9654; AI Booking Pipeline</div>
        <div class="pipeline-sub">Live flow of enquiries through the automated system</div>
      </div>
    </div>
    <div class="stages">

      <div class="stage" title="Total emails received and deduped by the system">
        <span class="stage-ico">&#128140;</span>
        <span class="stage-num c-blue" id="pipe-received">—</span>
        <span class="stage-name">Email In</span>
        <span class="stage-sub">Total received</span>
      </div>
      <div class="sarrow">&#8250;</div>

      <div class="stage" title="Emails sent through Claude AI for booking extraction">
        <span class="stage-ico">&#129302;</span>
        <span class="stage-num" style="color:var(--purple)" id="pipe-ai">—</span>
        <span class="stage-name">AI Extract</span>
        <span class="stage-sub">Claude parsed</span>
      </div>
      <div class="sarrow">&#8250;</div>

      <div class="stage" id="stage-clarify" title="Customers awaiting reply with missing info">
        <span class="stage-ico">&#10067;</span>
        <span class="stage-num c-amber" id="pipe-clarify">—</span>
        <span class="stage-name">Clarify</span>
        <span class="stage-sub">Awaiting reply</span>
      </div>
      <div class="sarrow">&#8250;</div>

      <div class="stage" id="stage-owner" title="Complete bookings sent to owner for YES/NO">
        <span class="stage-ico">&#128241;</span>
        <span class="stage-num" style="color:var(--orange)" id="pipe-owner">—</span>
        <span class="stage-name">Owner SMS</span>
        <span class="stage-sub">Awaiting decision</span>
      </div>
      <div class="sarrow">&#8250;</div>

      <div class="stage" title="Bookings confirmed by owner">
        <span class="stage-ico">&#9989;</span>
        <span class="stage-num c-green" id="pipe-confirmed">—</span>
        <span class="stage-name">Confirmed</span>
        <span class="stage-sub">All time</span>
      </div>
      <div class="sarrow">&#8250;</div>

      <div class="stage" title="Google Calendar events created">
        <span class="stage-ico">&#128197;</span>
        <span class="stage-num" style="color:var(--teal)" id="pipe-calendar">—</span>
        <span class="stage-name">Calendared</span>
        <span class="stage-sub">Events created</span>
      </div>

    </div>
    <div class="pipeline-bar"></div>
  </div>

  <!-- Main grid: Controls + Bookings -->
  <div class="main-grid">

    <div class="panel" id="flags-panel">
      <div class="panel-header">
        <span class="panel-title">&#9878; Automation Controls</span>
      </div>
      <div id="flags-body"><div class="empty">Loading…</div></div>
    </div>

    <div class="right-col">

      <div class="panel">
        <div class="panel-header">
          <span class="panel-title">&#9203; Pending Approval</span>
          <span class="panel-count" id="pending-count">0</span>
        </div>
        <div class="booking-list" id="pending-list"><div class="empty">Loading…</div></div>
      </div>

      <div class="panel">
        <div class="panel-header">
          <span class="panel-title">&#128295; Upcoming Jobs</span>
          <span class="panel-count" id="upcoming-count">0</span>
        </div>
        <div class="booking-list" id="upcoming-list"><div class="empty">Loading…</div></div>
      </div>

    </div>
  </div>

  <!-- Gmail Inbox -->
  <div class="panel gmail-panel">
    <div class="panel-header">
      <span class="panel-title">&#128140; Gmail Inbox</span>
      <div class="panel-hdr-right">
        <span class="panel-count" id="gmail-count">—</span>
        <button class="btn-sm" onclick="loadGmail()">&#8635; Refresh</button>
      </div>
    </div>
    <div id="gmail-list">
      <div class="empty">Connect to Railway to view Gmail inbox&#10;<br>Set your Railway URL in Setup above</div>
    </div>
  </div>

</div><!-- /container -->

<script>
/* ─ State ─ */
let _setupVisible = false;

/* ─ Helpers ─ */
function fmtDate(d) {
  if (!d || d === '?') return '?';
  try {
    const [,m,dd] = d.split('-');
    return `${parseInt(dd)} ${['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'][m-1]}`;
  } catch { return d; }
}

function fmtGmailDate(s) {
  if (!s) return '';
  try {
    const d = new Date(s), now = new Date();
    const diffH = (now - d) / 3.6e6;
    if (diffH < 20 && d.getDate() === now.getDate())
      return d.toLocaleTimeString('en-AU', {hour:'2-digit', minute:'2-digit'});
    if (diffH < 168)
      return d.toLocaleDateString('en-AU', {weekday:'short'});
    return d.toLocaleDateString('en-AU', {day:'numeric', month:'short'});
  } catch { return s.substring(0, 11); }
}

function senderName(from) {
  if (!from) return '?';
  const m = from.match(/^"?([^"<]+)"?\s*</);
  if (m) return m[1].trim();
  const em = from.match(/([^@\s<]+)@/);
  return em ? em[1] : from.substring(0, 18);
}

/* ─ Setup ─ */
function toggleSetup() {
  _setupVisible = !_setupVisible;
  document.getElementById('setup-panel').style.display = _setupVisible ? '' : 'none';
  if (_setupVisible) {
    fetch('/config').then(r => r.json()).then(cfg => {
      document.getElementById('inp-url').value   = cfg.railway_url  || '';
      document.getElementById('inp-token').value = cfg.admin_token  || '';
    });
  }
}

async function saveSetup() {
  const body = {
    railway_url: document.getElementById('inp-url').value.trim().replace(/\/+$/,''),
    admin_token: document.getElementById('inp-token').value.trim(),
  };
  await fetch('/config', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)});
  toggleSetup();
  refreshAll();
}

async function clearSetup() {
  await fetch('/config', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({railway_url:'',admin_token:''})});
  toggleSetup();
  refreshAll();
}

/* ─ Refresh ─ */
async function refreshAll() {
  const btn = document.getElementById('refresh-btn');
  btn.innerHTML = '<span class="spin">&#8635;</span> Refreshing';
  btn.classList.add('loading');
  await Promise.allSettled([loadData(), loadGmail()]);
  btn.innerHTML = '&#8635; Refresh';
  btn.classList.remove('loading');
}

/* ─ Flags ─ */
async function toggleFlag(key) {
  const r = await fetch('/toggle', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({key})});
  if (r.ok) {
    const j = await r.json();
    const inp = document.getElementById('inp-' + key);
    if (inp) inp.checked = j.enabled;
  }
}

function renderFlags(flags) {
  if (!flags || !Object.keys(flags).length) {
    document.getElementById('flags-body').innerHTML = '<div class="empty">No settings available</div>';
    return;
  }
  document.getElementById('flags-body').innerHTML = Object.entries(flags).map(([key, data]) => `
    <div class="flag-row" onclick="toggleFlag('${key}')">
      <div>
        <div class="flag-label">${data.label}</div>
        <div class="flag-desc">${data.description}</div>
      </div>
      <label class="switch" onclick="event.stopPropagation()">
        <input type="checkbox" id="inp-${key}" ${data.enabled ? 'checked' : ''} onchange="toggleFlag('${key}')">
        <span class="slider"></span>
      </label>
    </div>`).join('');
}

/* ─ Booking cards ─ */
function bookingCard(b) {
  const rims = b.rims && b.rims !== '?' ? ` &bull; ${b.rims} rim${b.rims != 1 ? 's' : ''}` : '';
  return `<div class="bcard">
    <div class="bcard-top"><div class="bcard-name">${b.name}</div><div class="bcard-id">${b.id}</div></div>
    <div class="bcard-row">
      <div class="bcard-item">&#128197; <span>${fmtDate(b.date)} at ${b.time}</span></div>
      <div class="bcard-item">&#128205; <span>${b.address}</span></div>
    </div>
    <div class="bcard-row">
      <div class="bcard-item">&#128295; <span>${b.service}${rims}</span></div>
      ${b.phone ? `<div class="bcard-item">&#128222; <span>${b.phone}</span></div>` : ''}
    </div>
  </div>`;
}

function renderBookings(pending, upcoming) {
  document.getElementById('pending-count').textContent  = pending.length;
  document.getElementById('upcoming-count').textContent = upcoming.length;
  document.getElementById('pending-list').innerHTML  = pending.length  ? pending.map(bookingCard).join('')  : '<div class="empty">No bookings awaiting approval</div>';
  document.getElementById('upcoming-list').innerHTML = upcoming.length ? upcoming.map(bookingCard).join('') : '<div class="empty">No upcoming bookings</div>';
}

/* ─ Pipeline ─ */
function renderPipeline(w, s) {
  if (!w) return;
  const set = (id, v) => { const el = document.getElementById(id); if (el) el.textContent = v ?? '—'; };
  set('pipe-received',  w.emails_received);
  set('pipe-ai',        w.ai_extracted);
  set('pipe-clarify',   w.clarifications_pending);
  set('pipe-owner',     w.awaiting_owner ?? s?.pending);
  set('pipe-confirmed', w.confirmed);
  set('pipe-calendar',  w.calendar_events ?? w.confirmed);
  const toggle = (id, on) => { const el = document.getElementById(id); if (el) el.classList.toggle('active', on > 0); };
  toggle('stage-clarify', w.clarifications_pending);
  toggle('stage-owner',   w.awaiting_owner ?? s?.pending);
}

/* ─ Main data ─ */
async function loadData() {
  try {
    const d = await fetch('/api/data').then(r => r.json());
    const ok = !d.error;
    document.getElementById('conn-badge').className   = 'badge ' + (ok ? 'badge-green' : 'badge-red');
    document.getElementById('conn-dot').className     = 'dot '   + (ok ? 'dot-green'  : 'dot-red');
    document.getElementById('conn-text').textContent  = d.mode || 'Unknown';
    document.getElementById('mode-label').textContent = d.mode || '';
    const err = document.getElementById('error-banner');
    if (d.error) { err.style.display = ''; err.textContent = 'Error: ' + d.error; }
    else err.style.display = 'none';
    const s = d.stats || {}, w = d.workflow || {};
    document.getElementById('s-pending').textContent   = s.pending  ?? '—';
    document.getElementById('s-today').textContent     = s.today    ?? '—';
    document.getElementById('s-upcoming').textContent  = s.upcoming ?? '—';
    document.getElementById('s-confirmed').textContent = w.confirmed ?? '—';
    renderFlags(d.flags);
    renderBookings(d.pending || [], d.upcoming || []);
    renderPipeline(w, s);
    document.getElementById('last-updated').textContent = new Date().toLocaleTimeString();
  } catch (e) {
    document.getElementById('conn-badge').className  = 'badge badge-red';
    document.getElementById('conn-text').textContent = 'Offline';
    const err = document.getElementById('error-banner');
    err.style.display = '';
    err.textContent = 'Dashboard server not responding: ' + e;
  }
}

/* ─ Gmail ─ */
const PILL_MAP = {
  'Confirmed':             ['spill-confirmed',  'Confirmed'],
  'Awaiting Confirmation': ['spill-awaiting',   'Awaiting'],
  'Pending Reply':         ['spill-pending',    'Needs Info'],
  'Declined':              ['spill-declined',   'Declined'],
  'Processed':             ['spill-processed',  'Processed'],
};

function gmailRow(m) {
  const name = senderName(m.from);
  const pill = m.booking_status && PILL_MAP[m.booking_status]
    ? `<span class="spill ${PILL_MAP[m.booking_status][0]}">${PILL_MAP[m.booking_status][1]}</span>` : '';
  return `<div class="gmail-row${m.is_unread ? ' unread' : ''}">
    <div class="gmail-avatar">${name.charAt(0).toUpperCase()}</div>
    <div class="gmail-main">
      <div class="gmail-from">${name}</div>
      <div class="gmail-subject">${m.subject || '(no subject)'}</div>
      <div class="gmail-snippet">${m.snippet || ''}</div>
    </div>
    <div class="gmail-right">
      <div class="gmail-time">${fmtGmailDate(m.date)}</div>
      ${pill}
    </div>
  </div>`;
}

async function loadGmail() {
  const list = document.getElementById('gmail-list');
  try {
    const r = await fetch('/api/gmail');
    if (!r.ok) { list.innerHTML = '<div class="empty">Gmail unavailable — connect to Railway first</div>'; return; }
    const d = await r.json();
    if (d.error) { list.innerHTML = `<div class="empty">Gmail: ${d.error}</div>`; return; }
    const msgs = d.messages || [];
    document.getElementById('gmail-count').textContent = msgs.length;
    list.innerHTML = msgs.length ? msgs.map(gmailRow).join('') : '<div class="empty">Inbox is empty</div>';
  } catch {
    list.innerHTML = '<div class="empty">Gmail unavailable — connect to Railway to view inbox</div>';
  }
}

/* ─ Init ─ */
loadData();
loadGmail();
setInterval(loadData,  60000);
setInterval(loadGmail, 120000);
</script>
</body>
</html>"""


# ── Flask routes ────────────────────────────────────────────────────────────
@app.route('/')
def index():
    return _HTML, 200, {'Content-Type': 'text/html; charset=utf-8'}


@app.route('/api/data')
def api_data():
    return jsonify(get_data())


@app.route('/api/gmail')
def api_gmail():
    cfg   = _load_cfg()
    url   = cfg.get('railway_url', '').strip().rstrip('/')
    token = cfg.get('admin_token', '').strip()
    if not url:
        return jsonify({'messages': [], 'error': 'No Railway URL configured'})
    try:
        import requests as _req
        qs = f'?token={token}' if token else ''
        r  = _req.get(f'{url}/admin/api/gmail{qs}', timeout=12)
        if r.status_code == 200:
            return jsonify(r.json())
        return jsonify({'messages': [], 'error': f'Railway returned {r.status_code}'})
    except Exception as e:
        return jsonify({'messages': [], 'error': str(e)})


@app.route('/toggle', methods=['POST'])
def toggle():
    body = request.get_json(silent=True) or {}
    key  = body.get('key', '')

    cfg   = _load_cfg()
    url   = cfg.get('railway_url', '').strip().rstrip('/')
    token = cfg.get('admin_token', '').strip()

    if url:
        # Forward toggle to Railway
        try:
            import requests as _req
            qs = f'?token={token}' if token else ''
            # Use the JSON toggle API on Railway
            r = _req.post(f'{url}/admin/api/toggle{qs}',
                          json={'key': key}, timeout=8)
            if r.status_code == 200:
                return jsonify(r.json())
            return jsonify({'success': False, 'error': f'Railway {r.status_code}'}), 502
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 502
    else:
        # Local toggle
        from feature_flags import FLAGS, get_flag, set_flag
        if key not in FLAGS:
            return jsonify({'success': False, 'error': 'Unknown flag'}), 400
        new_state = not get_flag(key)
        set_flag(key, new_state)
        return jsonify({'success': True, 'enabled': new_state})


@app.route('/config', methods=['GET', 'POST'])
def config():
    if request.method == 'POST':
        body = request.get_json(silent=True) or {}
        _save_cfg({
            'railway_url':  body.get('railway_url', ''),
            'admin_token':  body.get('admin_token', ''),
        })
        return jsonify({'ok': True})
    return jsonify(_load_cfg())


# ── Launch ──────────────────────────────────────────────────────────────────
def _open_browser():
    time.sleep(1.4)
    webbrowser.open(f'http://localhost:{PORT}')


if __name__ == '__main__':
    print(f'\n  Rim Repair Dashboard starting on http://localhost:{PORT}')
    print('  Close this window to stop the dashboard.\n')
    threading.Thread(target=_open_browser, daemon=True).start()
    app.run(host='127.0.0.1', port=PORT, debug=False)
