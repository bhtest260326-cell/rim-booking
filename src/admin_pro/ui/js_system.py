JS_SYSTEM = """
// ── System Section ────────────────────────────────────────────────────────────

async function initSystem() {
  injectFlagStyles();
  renderCancelDayForm();
  await Promise.all([
    loadSystemHealth(),
    loadFeatureFlags(),
    loadDbStats(),
  ]);
}

// ── System Health ─────────────────────────────────────────────────────────────

async function loadSystemHealth() {
  const container = document.getElementById('system-health');
  if (!container) return;
  try {
    const h = await apiFetch('/v2/api/system/health');

    function healthDot(status) {
      const color = status === 'ok' || status === 'configured' ? 'var(--ap-green)' :
                    status === 'unconfigured' ? 'var(--ap-amber)' : 'var(--ap-red)';
      return `<span class="ap-status-dot" style="background:${color}"></span>`;
    }

    container.innerHTML = `
      <div class="ap-grid-4">
        <div class="ap-card">
          ${healthDot(h.db?.status)}
          <div class="ap-kpi-value" style="font-size:1.4rem">${h.db?.size_mb?.toFixed(2) || '?'} MB</div>
          <div class="ap-text-muted">Database</div>
          <div style="font-size:12px;margin-top:4px">${h.db?.bookings_count || 0} bookings</div>
        </div>
        <div class="ap-card">
          ${healthDot(h.gmail?.status)}
          <div class="ap-kpi-value" style="font-size:1.2rem">${h.gmail?.status || 'unknown'}</div>
          <div class="ap-text-muted">Gmail API</div>
          ${h.gmail?.last_poll ? `<div style="font-size:12px;margin-top:4px">Last poll: ${relativeTime(h.gmail.last_poll)}</div>` : ''}
        </div>
        <div class="ap-card">
          ${healthDot(h.anthropic?.status)}
          <div class="ap-kpi-value" style="font-size:1.2rem">${h.anthropic?.status || 'unknown'}</div>
          <div class="ap-text-muted">Anthropic AI</div>
        </div>
        <div class="ap-card">
          ${healthDot(h.twilio?.status)}
          <div class="ap-kpi-value" style="font-size:1.2rem">${h.twilio?.status || 'unknown'}</div>
          <div class="ap-text-muted">Twilio SMS</div>
          <div style="font-size:12px;margin-top:4px">${h.uptime_info?.pubsub_mode ? 'Pub/Sub mode' : 'Polling mode'}</div>
        </div>
      </div>
    `;
  } catch (err) {
    console.error('loadSystemHealth error:', err);
    container.innerHTML = '<div class="ap-text-muted">Failed to load system health.</div>';
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
              <div class="ap-flag-label">${escapeHtml(flag.label)}</div>
              <div class="ap-flag-desc">${escapeHtml(flag.description)}</div>
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
  const container = document.getElementById('system-db-stats');
  if (!container) return;
  try {
    const stats = await apiFetch('/v2/api/system/db-stats');

    container.innerHTML = `
      <h3 class="ap-card-title ap-mb-16">Database Tables</h3>
      <div class="ap-table-wrap">
        <table class="ap-table">
          <thead><tr><th>Table</th><th>Rows</th></tr></thead>
          <tbody>
            ${(stats?.tables || []).map(t => `
              <tr>
                <td>${escapeHtml(t.name)}</td>
                <td>${t.count.toLocaleString()}</td>
              </tr>
            `).join('')}
            <tr style="font-weight:600;border-top:2px solid var(--ap-border)">
              <td>Total</td><td>${(stats?.total_rows || 0).toLocaleString()}</td>
            </tr>
          </tbody>
        </table>
      </div>
    `;
  } catch (err) {
    console.error('loadDbStats error:', err);
    container.innerHTML = '<div class="ap-text-muted">Failed to load database stats.</div>';
  }
}

// ── Cancel Day Form ───────────────────────────────────────────────────────────

function renderCancelDayForm() {
  const container = document.getElementById('system-cancel-day');
  if (!container) return;
  container.innerHTML = `
    <h3 class="ap-card-title ap-mb-16">Cancel Day of Bookings</h3>
    <div class="ap-form-group">
      <label>Date to Cancel</label>
      <input type="date" class="ap-input" id="system-cancel-date" style="max-width:200px">
    </div>
    <div class="ap-form-group">
      <label>Reason (sent to customers)</label>
      <textarea class="ap-textarea" id="system-cancel-reason" rows="3" placeholder="e.g. Equipment maintenance, public holiday..."></textarea>
    </div>
    <button class="ap-btn ap-btn-danger" onclick="submitSystemCancelDay()">&#9888; Cancel All Jobs on This Day</button>
  `;
}

async function submitSystemCancelDay() {
  const date = document.getElementById('system-cancel-date').value;
  const reason = document.getElementById('system-cancel-reason').value.trim();
  if (!date) { showToast('Please select a date', 'warning'); return; }
  if (!reason) { showToast('Please provide a reason', 'warning'); return; }
  if (!confirm(`Cancel ALL bookings on ${formatDate(date)}? This will notify all customers.`)) return;
  try {
    const data = await apiFetch('/v2/api/system/cancel-day', {method:'POST', body: JSON.stringify({date, reason})});
    showToast(`${data.cancelled} booking(s) cancelled and customers notified`, 'success');
    document.getElementById('system-cancel-date').value = '';
    document.getElementById('system-cancel-reason').value = '';
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
    .ap-flag-label { font-weight:600; font-size:14px; }
    .ap-flag-desc { font-size:12px; color:var(--ap-text-muted); margin-top:3px; }
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
