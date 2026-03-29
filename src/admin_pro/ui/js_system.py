JS_SYSTEM = """
// ── System Section ────────────────────────────────────────────────────────────

async function initSystem() {
  injectFlagStyles();
  await Promise.all([
    loadSystemHealth(),
    loadFeatureFlags(),
    loadDbStats(),
  ]);
}

// ── System Health ─────────────────────────────────────────────────────────────

async function loadSystemHealth() {
  try {
    const h = await apiFetch('/v2/api/system/health');

    function setStatus(id, status, detail) {
      const el = document.getElementById(id);
      if (!el) return;
      const color = (status === 'ok' || status === 'configured') ? 'var(--ap-green)'
                  : (status === 'unconfigured') ? 'var(--ap-amber)' : 'var(--ap-red)';
      el.innerHTML = `<span style="color:${color};font-weight:600">${status || '—'}</span>${detail ? '<br><small style="color:var(--ap-text-muted)">' + detail + '</small>' : ''}`;
    }

    setStatus('health-gmail-status',    h.gmail?.status,     h.gmail?.last_poll ? 'Last poll: ' + relativeTime(h.gmail.last_poll) : null);
    setStatus('health-calendar-status', h.anthropic?.status, null);
    setStatus('health-twilio-status',   h.twilio?.status,    h.uptime_info?.pubsub_mode ? 'Pub/Sub mode' : 'Polling mode');
    setStatus('health-db-status',       h.db?.status,        h.db ? (h.db.size_mb?.toFixed(2) + ' MB · ' + (h.db.bookings_count || 0) + ' bookings') : null);
  } catch (err) {
    console.error('loadSystemHealth error:', err);
  }
}

// ── Feature Flags ─────────────────────────────────────────────────────────────

async function loadFeatureFlags() {
  const container = document.getElementById('system-flags');
  if (!container) return;
  try {
    const data = await apiFetch('/v2/api/system/flags');
    const flags = data.flags || {};

    container.innerHTML = `
      <h3 class="ap-card-title ap-mb-16">Feature Flags</h3>
      <div class="ap-flags-grid">
        ${Object.entries(flags).map(([key, flag]) => `
          <div class="ap-flag-card ${flag.enabled ? 'enabled' : 'disabled'}" id="flag-card-${key}">
            <div class="ap-flag-info">
              <div class="ap-flag-label-row">
                <span class="ap-flag-label">${escapeHtml(flag.label)}</span>
                <span class="ap-flag-info-icon" tabindex="0" aria-label="${escapeHtml(flag.description)}">
                  &#x24D8;
                  <span class="ap-flag-tooltip">${escapeHtml(flag.description)}</span>
                </span>
              </div>
            </div>
            <label class="ap-toggle" title="${flag.enabled ? 'Enabled — click to disable' : 'Disabled — click to enable'}">
              <input type="checkbox" ${flag.enabled ? 'checked' : ''} onchange="toggleFlag('${key}', this.checked)">
              <span class="ap-toggle-slider"></span>
            </label>
          </div>
        `).join('')}
      </div>
    `;
  } catch (err) {
    console.error('loadFeatureFlags error:', err);
    if (container) container.innerHTML = '<div class="ap-text-muted">Failed to load feature flags.</div>';
  }
}

async function toggleFlag(key, enabled) {
  try {
    const data = await apiFetch(`/v2/api/system/flags/${key}`, {
      method: 'POST',
      body: JSON.stringify({ enabled })
    });
    const card = document.getElementById(`flag-card-${key}`);
    if (card) {
      card.classList.toggle('enabled', enabled);
      card.classList.toggle('disabled', !enabled);
    }
    showToast(`${key.replace('flag_','').replace(/_/g,' ')} ${enabled ? 'enabled' : 'disabled'}`, 'success');
  } catch(e) {
    showToast('Failed to update flag: ' + e.message, 'error');
    loadFeatureFlags(); // Reset to server state
  }
}

// ── Database Stats ────────────────────────────────────────────────────────────

async function loadDbStats() {
  try {
    const stats = await apiFetch('/v2/api/system/db-stats');
    const tables = stats?.tables || [];

    // Update individual stat spans in the existing HTML
    const bookings = tables.find(t => t.name === 'bookings');
    const customers = tables.find(t => t.name === 'customers');
    const dlq       = tables.find(t => t.name === 'dlq' || t.name === 'dead_letter_queue');
    const waitlist  = tables.find(t => t.name === 'waitlist');

    function setVal(id, val) { const el = document.getElementById(id); if (el) el.textContent = val; }
    setVal('dbstat-bookings', bookings ? bookings.count.toLocaleString() : '—');
    setVal('dbstat-customers', customers ? customers.count.toLocaleString() : '—');
    setVal('dbstat-dlq',      dlq       ? dlq.count.toLocaleString()      : '—');
    setVal('dbstat-waitlist', waitlist   ? waitlist.count.toLocaleString() : '—');
    setVal('dbstat-size',     '—');   // not returned separately
    setVal('dbstat-vacuum',   '—');

    // Also inject a compact table below for all tables
    const grid = document.getElementById('db-stats-grid');
    if (grid && tables.length > 0) {
      const extra = document.getElementById('db-stats-table');
      if (!extra) {
        const div = document.createElement('div');
        div.id = 'db-stats-table';
        div.style.cssText = 'margin-top:12px;border-top:1px solid var(--ap-border);padding-top:12px';
        div.innerHTML = '<div class="ap-text-muted" style="font-size:12px;margin-bottom:6px">All tables</div>' +
          tables.map(t => `<div class="ap-stat-row"><span class="ap-stat-label">${escapeHtml(t.name)}</span><span class="ap-stat-val">${t.count.toLocaleString()}</span></div>`).join('') +
          `<div class="ap-stat-row" style="font-weight:600;border-top:1px solid var(--ap-border);margin-top:4px;padding-top:4px"><span class="ap-stat-label">Total rows</span><span class="ap-stat-val">${(stats.total_rows||0).toLocaleString()}</span></div>`;
        grid.parentElement.appendChild(div);
      }
    }
  } catch (err) {
    console.error('loadDbStats error:', err);
  }
}

// ── Cancel Day (uses IDs from static HTML: cancel-day-date, cancel-day-reason) ──

function cancelDayPrompt() { submitSystemCancelDay(); }

async function submitSystemCancelDay() {
  // Support both the static HTML IDs and the dynamically-injected IDs
  const dateEl   = document.getElementById('cancel-day-date')   || document.getElementById('system-cancel-date');
  const reasonEl = document.getElementById('cancel-day-reason') || document.getElementById('system-cancel-reason');
  const date   = dateEl   ? dateEl.value.trim()   : '';
  const reason = reasonEl ? reasonEl.value.trim() : '';
  if (!date)   { showToast('Please select a date', 'warning');    return; }
  if (!reason) { showToast('Please provide a reason', 'warning'); return; }
  if (!confirm(`Cancel ALL bookings on ${formatDate(date)}? This will notify all customers.`)) return;
  try {
    const data = await apiFetch('/v2/api/system/cancel-day', {method: 'POST', body: JSON.stringify({date, reason})});
    showToast(`${data.cancelled || 0} booking(s) cancelled and customers notified`, 'success');
    if (dateEl)   dateEl.value   = '';
    if (reasonEl) reasonEl.value = '';
  } catch (err) {
    showToast('Failed to cancel day: ' + err.message, 'error');
  }
}

// ── Flag & Toggle Styles ──────────────────────────────────────────────────────

function injectFlagStyles() {
  const style = document.createElement('style');
  style.textContent = `
    .ap-flags-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 12px; }
    .ap-flag-card { display:flex; justify-content:space-between; align-items:center; padding:16px; background:var(--ap-card); border:1px solid var(--ap-border); border-radius:var(--ap-radius-sm); transition:.2s; }
    .ap-flag-card.enabled { border-color: rgba(34,197,94,0.3); }
    .ap-flag-card.disabled { opacity:.7; }
    .ap-flag-label-row { display:flex; align-items:center; gap:6px; }
    .ap-flag-label { font-weight:600; font-size:14px; }
    .ap-flag-info-icon { position:relative; display:inline-flex; align-items:center; justify-content:center; width:16px; height:16px; font-size:14px; color:var(--ap-text-muted); cursor:default; flex-shrink:0; line-height:1; }
    .ap-flag-info-icon:hover { color:var(--ap-primary); }
    .ap-flag-tooltip { visibility:hidden; opacity:0; position:absolute; bottom:calc(100% + 8px); left:50%; transform:translateX(-50%); background:#1e1e1e; color:var(--ap-text); font-size:12px; font-weight:400; line-height:1.5; padding:8px 12px; border-radius:8px; border:1px solid var(--ap-border-light); box-shadow:0 4px 16px rgba(0,0,0,0.5); white-space:normal; width:240px; text-align:left; pointer-events:none; transition:opacity .15s, visibility .15s; z-index:999; }
    .ap-flag-tooltip::after { content:''; position:absolute; top:100%; left:50%; transform:translateX(-50%); border:6px solid transparent; border-top-color:#1e1e1e; }
    .ap-flag-info-icon:hover .ap-flag-tooltip,
    .ap-flag-info-icon:focus .ap-flag-tooltip { visibility:visible; opacity:1; }
    .ap-toggle { position:relative; width:44px; height:24px; flex-shrink:0; margin-left:12px; }
    .ap-toggle input { opacity:0; width:0; height:0; }
    .ap-toggle-slider { position:absolute; inset:0; background:#334155; border-radius:24px; cursor:pointer; transition:.2s; }
    .ap-toggle-slider:before { content:''; position:absolute; height:18px; width:18px; left:3px; top:3px; background:white; border-radius:50%; transition:.2s; }
    .ap-toggle input:checked + .ap-toggle-slider { background:var(--ap-green); }
    .ap-toggle input:checked + .ap-toggle-slider:before { transform:translateX(20px); }
  `;
  document.head.appendChild(style);
}
"""
