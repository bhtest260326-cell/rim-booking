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
<title>Rim Repair — Dashboard</title>
<style>
:root{
  --bg:#07111f;--surface:#0d1f35;--card:#112240;--border:#1a3a5c;
  --accent:#3b82f6;--green:#22c55e;--red:#ef4444;--amber:#f59e0b;
  --text:#f1f5f9;--muted:#64748b;--subtle:#1e3a5c;
  --radius:14px;--shadow:0 4px 24px rgba(0,0,0,.4);
}
*{box-sizing:border-box;margin:0;padding:0;}
body{background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;min-height:100vh;}

/* Header */
.header{background:linear-gradient(135deg,#0d1f35 0%,#0a1628 100%);border-bottom:1px solid var(--border);padding:16px 24px;display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;}
.header-left{display:flex;align-items:center;gap:12px;}
.logo{width:36px;height:36px;background:var(--accent);border-radius:10px;display:flex;align-items:center;justify-content:center;font-size:18px;}
.title{font-size:1.1rem;font-weight:700;color:var(--text);}
.subtitle{font-size:0.7rem;color:var(--muted);margin-top:1px;}
.header-right{display:flex;align-items:center;gap:10px;}
.badge{display:inline-flex;align-items:center;gap:5px;padding:4px 10px;border-radius:20px;font-size:0.72rem;font-weight:600;}
.badge-green{background:rgba(34,197,94,.15);color:var(--green);border:1px solid rgba(34,197,94,.3);}
.badge-red{background:rgba(239,68,68,.15);color:var(--red);border:1px solid rgba(239,68,68,.3);}
.badge-blue{background:rgba(59,130,246,.15);color:var(--accent);border:1px solid rgba(59,130,246,.3);}
.dot{width:7px;height:7px;border-radius:50%;}
.dot-green{background:var(--green);}
.dot-red{background:var(--red);}
.settings-btn{background:var(--subtle);border:1px solid var(--border);color:var(--muted);padding:6px 12px;border-radius:8px;font-size:0.78rem;cursor:pointer;transition:.15s;}
.settings-btn:hover{color:var(--text);border-color:var(--accent);}

/* Layout */
.container{max-width:1200px;margin:0 auto;padding:20px 20px 40px;}

/* Stats */
.stats{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-bottom:24px;}
.stat{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);padding:18px;text-align:center;}
.stat-num{font-size:2rem;font-weight:800;line-height:1;margin-bottom:4px;}
.stat-lbl{font-size:0.72rem;color:var(--muted);text-transform:uppercase;letter-spacing:.05em;}
.stat-num.amber{color:var(--amber);}
.stat-num.green{color:var(--green);}
.stat-num.blue{color:var(--accent);}

/* Main grid */
.main{display:grid;grid-template-columns:1fr 1.5fr;gap:20px;align-items:start;}
@media(max-width:760px){.main{grid-template-columns:1fr;} .stats{grid-template-columns:repeat(3,1fr);}}

/* Panels */
.panel{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);overflow:hidden;}
.panel-header{padding:14px 18px;border-bottom:1px solid var(--border);display:flex;align-items:center;justify-content:space-between;}
.panel-title{font-size:0.82rem;font-weight:700;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);}
.panel-count{background:var(--subtle);color:var(--accent);font-size:0.7rem;font-weight:700;padding:2px 8px;border-radius:10px;}

/* Toggle rows */
.flag-row{display:flex;align-items:center;justify-content:space-between;padding:14px 18px;border-bottom:1px solid var(--border);gap:12px;}
.flag-row:last-child{border-bottom:none;}
.flag-text{}
.flag-label{font-size:0.88rem;font-weight:600;color:var(--text);margin-bottom:2px;}
.flag-desc{font-size:0.72rem;color:var(--muted);line-height:1.4;}
/* CSS toggle switch */
.switch{position:relative;display:inline-block;width:48px;height:26px;flex-shrink:0;}
.switch input{opacity:0;width:0;height:0;}
.slider{position:absolute;cursor:pointer;inset:0;background:var(--red);border-radius:26px;transition:.25s;}
.slider:before{position:absolute;content:"";height:20px;width:20px;left:3px;bottom:3px;background:#fff;border-radius:50%;transition:.25s;}
input:checked+.slider{background:var(--green);}
input:checked+.slider:before{transform:translateX(22px);}
.switch input{pointer-events:none;}
.flag-row{cursor:pointer;}
.flag-row:hover{background:rgba(255,255,255,.03);}

/* Booking cards */
.booking-list{padding:8px;}
.bcard{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:14px;margin-bottom:8px;}
.bcard:last-child{margin-bottom:0;}
.bcard-top{display:flex;align-items:center;justify-content:space-between;margin-bottom:8px;}
.bcard-name{font-size:0.95rem;font-weight:700;color:var(--text);}
.bcard-id{font-size:0.65rem;color:var(--muted);background:var(--subtle);padding:2px 6px;border-radius:6px;}
.bcard-row{display:flex;gap:16px;flex-wrap:wrap;margin-bottom:4px;}
.bcard-item{font-size:0.75rem;color:var(--muted);display:flex;align-items:center;gap:4px;}
.bcard-item span{color:var(--text);}
.empty{text-align:center;padding:32px 20px;color:var(--muted);font-size:0.82rem;}

/* Error banner */
.error-banner{background:rgba(239,68,68,.1);border:1px solid rgba(239,68,68,.3);color:#fca5a5;border-radius:10px;padding:12px 16px;margin-bottom:20px;font-size:0.82rem;}

/* Setup panel */
.setup-panel{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);padding:20px;margin-bottom:20px;}
.setup-title{font-size:0.85rem;font-weight:700;color:var(--text);margin-bottom:4px;}
.setup-sub{font-size:0.72rem;color:var(--muted);margin-bottom:16px;}
.form-row{margin-bottom:12px;}
.form-label{font-size:0.72rem;font-weight:600;color:var(--muted);text-transform:uppercase;letter-spacing:.05em;margin-bottom:4px;display:block;}
.form-input{width:100%;background:var(--surface);border:1px solid var(--border);color:var(--text);padding:9px 12px;border-radius:8px;font-size:0.85rem;outline:none;}
.form-input:focus{border-color:var(--accent);}
.form-row-inline{display:grid;grid-template-columns:1fr 1fr;gap:12px;}
.btn-save{background:var(--accent);color:#fff;border:none;padding:9px 20px;border-radius:8px;font-weight:600;font-size:0.83rem;cursor:pointer;width:100%;transition:.15s;}
.btn-save:hover{opacity:.85;}
.btn-clear{background:transparent;color:var(--red);border:1px solid rgba(239,68,68,.4);padding:9px 20px;border-radius:8px;font-size:0.83rem;cursor:pointer;width:100%;margin-top:6px;transition:.15s;}
.btn-clear:hover{background:rgba(239,68,68,.1);}
.setup-toggle{font-size:0.75rem;color:var(--accent);cursor:pointer;background:none;border:none;padding:0;}

/* Refresh bar */
.refresh-bar{text-align:right;font-size:0.68rem;color:var(--muted);margin-bottom:12px;}
</style>
</head>
<body>

<div class="header">
  <div class="header-left">
    <div class="logo">&#9881;</div>
    <div>
      <div class="title">Rim Repair Dashboard</div>
      <div class="subtitle" id="mode-label">Loading...</div>
    </div>
  </div>
  <div class="header-right">
    <span class="badge" id="conn-badge"><span class="dot" id="conn-dot"></span><span id="conn-text">...</span></span>
    <button class="settings-btn" onclick="toggleSetup()">&#9965; Setup</button>
  </div>
</div>

<div class="container">

  <!-- Error -->
  <div class="error-banner" id="error-banner" style="display:none"></div>

  <!-- Setup panel (hidden by default) -->
  <div class="setup-panel" id="setup-panel" style="display:none">
    <div class="setup-title">Railway Connection</div>
    <div class="setup-sub">Connect to your live Railway deployment to see real-time bookings and control settings remotely. Leave blank to use the local database.</div>
    <div class="form-row-inline">
      <div class="form-row" style="margin-bottom:0">
        <label class="form-label">Railway URL</label>
        <input class="form-input" id="inp-url" placeholder="https://your-app.railway.app" type="url">
      </div>
      <div class="form-row" style="margin-bottom:0">
        <label class="form-label">Admin Token</label>
        <input class="form-input" id="inp-token" placeholder="ADMIN_TOKEN value" type="password">
      </div>
    </div>
    <br>
    <button class="btn-save" onclick="saveSetup()">Save &amp; Connect</button>
    <button class="btn-clear" onclick="clearSetup()">Clear (use local database)</button>
  </div>

  <!-- Stats -->
  <div class="stats">
    <div class="stat">
      <div class="stat-num amber" id="s-pending">—</div>
      <div class="stat-lbl">Pending</div>
    </div>
    <div class="stat">
      <div class="stat-num green" id="s-today">—</div>
      <div class="stat-lbl">Today</div>
    </div>
    <div class="stat">
      <div class="stat-num blue" id="s-upcoming">—</div>
      <div class="stat-lbl">Upcoming</div>
    </div>
  </div>

  <div class="refresh-bar">Last updated: <span id="last-updated">—</span></div>

  <div class="main">

    <!-- LEFT: Feature flags -->
    <div class="panel" id="flags-panel">
      <div class="panel-header">
        <span class="panel-title">Automation Settings</span>
      </div>
      <div id="flags-body">
        <div class="empty">Loading settings…</div>
      </div>
    </div>

    <!-- RIGHT: Bookings -->
    <div>
      <div class="panel" style="margin-bottom:16px">
        <div class="panel-header">
          <span class="panel-title">Pending Approval</span>
          <span class="panel-count" id="pending-count">0</span>
        </div>
        <div class="booking-list" id="pending-list">
          <div class="empty">Loading…</div>
        </div>
      </div>

      <div class="panel">
        <div class="panel-header">
          <span class="panel-title">Upcoming Jobs</span>
          <span class="panel-count" id="upcoming-count">0</span>
        </div>
        <div class="booking-list" id="upcoming-list">
          <div class="empty">Loading…</div>
        </div>
      </div>
    </div>

  </div>
</div>

<script>
const FLAG_LABELS = {
  flag_auto_email_replies:   'Auto email replies to customers',
  flag_auto_sms_owner:       'Auto SMS booking requests to owner',
  flag_auto_sms_customer:    'Auto SMS to customers',
  flag_auto_email_customer:  'Auto email to customers',
  flag_day_prior_reminders:  'Morning reminder SMS (day-prior)',
  flag_post_job_reviews:     'Post-job review request SMS',
};

let _data = null;
let _setupVisible = false;

function toggleSetup(){
  _setupVisible = !_setupVisible;
  document.getElementById('setup-panel').style.display = _setupVisible ? '' : 'none';
  if(_setupVisible) loadSetupInputs();
}

async function loadSetupInputs(){
  const r = await fetch('/config');
  const cfg = await r.json();
  document.getElementById('inp-url').value   = cfg.railway_url  || '';
  document.getElementById('inp-token').value = cfg.admin_token  || '';
}

async function saveSetup(){
  const body = {
    railway_url:  document.getElementById('inp-url').value.trim().replace(/\/+$/,''),
    admin_token:  document.getElementById('inp-token').value.trim(),
  };
  await fetch('/config', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)});
  toggleSetup();
  loadData();
}

async function clearSetup(){
  await fetch('/config', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({railway_url:'',admin_token:''})});
  document.getElementById('inp-url').value='';
  document.getElementById('inp-token').value='';
  toggleSetup();
  loadData();
}

async function toggleFlag(key, currentEnabled){
  const r = await fetch('/toggle', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({key})});
  if(r.ok){
    const j = await r.json();
    // Update just that toggle without full reload
    const inp = document.getElementById('inp-'+key);
    if(inp) inp.checked = j.enabled;
  }
}

function renderFlags(flags){
  if(!flags || Object.keys(flags).length===0){
    document.getElementById('flags-body').innerHTML='<div class="empty">No settings available</div>';
    return;
  }
  let html='';
  for(const [key,data] of Object.entries(flags)){
    const checked = data.enabled ? 'checked' : '';
    html += `
    <div class="flag-row" onclick="toggleFlag('${key}', ${data.enabled})">
      <div class="flag-text">
        <div class="flag-label">${data.label}</div>
        <div class="flag-desc">${data.description}</div>
      </div>
      <label class="switch" onclick="event.stopPropagation()">
        <input type="checkbox" id="inp-${key}" ${checked} onchange="toggleFlag('${key}', ${data.enabled})">
        <span class="slider"></span>
      </label>
    </div>`;
  }
  document.getElementById('flags-body').innerHTML = html;
}

function fmtDate(d){
  if(!d||d==='?') return '?';
  try{
    const [y,m,dd]=d.split('-');
    const months=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
    return `${parseInt(dd)} ${months[parseInt(m)-1]}`;
  }catch{return d;}
}

function bookingCard(b){
  const rimsStr = b.rims && b.rims!='?' ? ` &bull; ${b.rims} rim${b.rims!=1?'s':''}` : '';
  return `<div class="bcard">
    <div class="bcard-top">
      <div class="bcard-name">${b.name}</div>
      <div class="bcard-id">${b.id}</div>
    </div>
    <div class="bcard-row">
      <div class="bcard-item">&#128197; <span>${fmtDate(b.date)} at ${b.time}</span></div>
      <div class="bcard-item">&#128205; <span>${b.address}</span></div>
    </div>
    <div class="bcard-row">
      <div class="bcard-item">&#128295; <span>${b.service}${rimsStr}</span></div>
      ${b.phone ? `<div class="bcard-item">&#128222; <span>${b.phone}</span></div>` : ''}
    </div>
  </div>`;
}

function renderBookings(pending, upcoming){
  const pList = document.getElementById('pending-list');
  const uList = document.getElementById('upcoming-list');
  document.getElementById('pending-count').textContent  = pending.length;
  document.getElementById('upcoming-count').textContent = upcoming.length;

  pList.innerHTML = pending.length
    ? pending.map(bookingCard).join('')
    : '<div class="empty">No bookings awaiting approval</div>';

  uList.innerHTML = upcoming.length
    ? upcoming.map(bookingCard).join('')
    : '<div class="empty">No upcoming bookings</div>';
}

async function loadData(){
  try{
    const r = await fetch('/api/data');
    const d = await r.json();
    _data = d;

    // Connection badge
    const isOk = !d.error;
    document.getElementById('conn-badge').className = 'badge ' + (isOk ? 'badge-green' : 'badge-red');
    document.getElementById('conn-dot').className   = 'dot ' + (isOk ? 'dot-green' : 'dot-red');
    document.getElementById('conn-text').textContent = d.mode || 'Unknown';
    document.getElementById('mode-label').textContent = d.mode || '';

    // Error
    const errEl = document.getElementById('error-banner');
    if(d.error){errEl.style.display=''; errEl.textContent='Error: '+d.error;}
    else{errEl.style.display='none';}

    // Stats
    const s = d.stats || {};
    document.getElementById('s-pending').textContent  = s.pending  ?? '—';
    document.getElementById('s-today').textContent    = s.today    ?? '—';
    document.getElementById('s-upcoming').textContent = s.upcoming ?? '—';

    renderFlags(d.flags);
    renderBookings(d.pending || [], d.upcoming || []);

    document.getElementById('last-updated').textContent = new Date().toLocaleTimeString();
  }catch(e){
    document.getElementById('conn-badge').className  = 'badge badge-red';
    document.getElementById('conn-text').textContent = 'Offline';
    document.getElementById('error-banner').style.display = '';
    document.getElementById('error-banner').textContent   = 'Dashboard server not responding: '+e;
  }
}

// Initial load + auto-refresh every 60s
loadData();
setInterval(loadData, 60000);
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
