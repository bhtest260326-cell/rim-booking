"""
admin_pro/ui/js_dashboard.py
Dashboard section JavaScript for the Admin Pro UI.
"""

JS_DASHBOARD = """
// ---------------------------------------------------------------------------
// Dashboard — KPI cards, pipeline, recent bookings, today's jobs, system status
// ---------------------------------------------------------------------------

async function initDashboard() {
  showDashboardSkeletons();

  const today = new Date().toISOString().slice(0, 10);

  const [statsRes, overviewRes, funnelRes, pendingRes, todayRes, healthRes] =
    await Promise.allSettled([
      apiFetch('/v2/api/bookings/stats'),
      apiFetch('/v2/api/analytics/overview'),
      apiFetch('/v2/api/analytics/funnel'),
      apiFetch('/v2/api/bookings?status=awaiting_owner&per_page=5'),
      apiFetch('/v2/api/bookings?status=confirmed&date_from=' + today + '&date_to=' + today + '&per_page=50'),
      apiFetch('/v2/api/system/health'),
    ]);

  // KPI cards
  try {
    const stats    = statsRes.status === 'fulfilled'    ? statsRes.value    : null;
    const overview = overviewRes.status === 'fulfilled' ? overviewRes.value : null;

    const pendingCount  = stats   ? (stats.awaiting_owner ?? 0) : 0;
    const todayCount    = stats   ? (stats.today           ?? 0) : 0;
    const weekCount     = stats   ? (stats.this_week       ?? 0) : 0;
    const totalConfirmed = stats  ? (stats.confirmed       ?? 0) : 0;

    const convRate = overview ? (overview.conversion_rate ?? null) : null;

    renderKpiCard('kpi-pending', pendingCount, 'Awaiting Approval', 'amber',  '&#9203;', null);
    renderKpiCard('kpi-today',   todayCount,   "Today's Jobs",      'green',  '&#128336;', null);
    renderKpiCard('kpi-week',    weekCount,    'This Week',         'blue',   '&#128197;', null);
    renderKpiCard('kpi-total',   totalConfirmed,'Total Confirmed',  'purple', '&#10003;',
      convRate !== null ? Math.round(convRate) : null);

    // Floating action badge for pending bookings
    updatePendingBadge(pendingCount);
  } catch (err) {
    console.error('Dashboard KPI error:', err);
    showKpiError();
  }

  // Pipeline
  try {
    if (funnelRes.status === 'fulfilled' && funnelRes.value && funnelRes.value.stages) {
      renderPipeline(funnelRes.value.stages);
    } else {
      showPipelineError('Could not load pipeline data');
    }
  } catch (err) {
    console.error('Dashboard pipeline error:', err);
    showPipelineError(err.message);
  }

  // Recent bookings (awaiting owner)
  try {
    if (pendingRes.status === 'fulfilled' && pendingRes.value) {
      renderRecentBookings(pendingRes.value.bookings || []);
    } else {
      renderRecentBookings([]);
    }
  } catch (err) {
    console.error('Dashboard recent bookings error:', err);
    showSectionError('recent-bookings-tbody', 'Could not load pending bookings');
  }

  // Today's jobs
  try {
    if (todayRes.status === 'fulfilled' && todayRes.value) {
      renderTodayJobs(todayRes.value.bookings || []);
    } else {
      renderTodayJobs([]);
    }
  } catch (err) {
    console.error('Dashboard today jobs error:', err);
    showSectionError('today-jobs-list', "Could not load today's jobs");
  }

  // System status
  try {
    if (healthRes.status === 'fulfilled' && healthRes.value) {
      renderSystemStatus(healthRes.value);
    } else {
      renderSystemStatus(null);
    }
  } catch (err) {
    console.error('Dashboard system status error:', err);
    showSectionError('dashboard-system-status', 'Could not load system status');
  }

  // Auto-refresh every 30 seconds
  setAutoRefresh('dashboard', 30000);

  // Wire KPI card click navigation
  wireKpiClicks();
}

// ---------------------------------------------------------------------------
// Loading skeletons
// ---------------------------------------------------------------------------

function showDashboardSkeletons() {
  const kpiIds = ['kpi-pending', 'kpi-today', 'kpi-week', 'kpi-total'];
  const skeletonKpi = `
    <div class="ap-skeleton ap-skeleton-icon"></div>
    <div class="ap-skeleton ap-skeleton-value"></div>
    <div class="ap-skeleton ap-skeleton-label"></div>
  `;
  kpiIds.forEach(function(id) {
    const el = document.getElementById(id);
    if (el) el.innerHTML = skeletonKpi;
  });

  const pipeline = document.getElementById('ap-pipeline');
  if (pipeline) {
    pipeline.innerHTML = '<div class="ap-skeleton ap-skeleton-pipeline"></div>';
  }

  const skeletonRow = `
    <tr><td colspan="5"><div class="ap-skeleton ap-skeleton-row"></div></td></tr>
    <tr><td colspan="5"><div class="ap-skeleton ap-skeleton-row"></div></td></tr>
    <tr><td colspan="5"><div class="ap-skeleton ap-skeleton-row"></div></td></tr>
  `;
  const recentEl = document.getElementById('recent-bookings-tbody');
  if (recentEl) recentEl.innerHTML = skeletonRow;

  const todayEl = document.getElementById('today-jobs-list');
  if (todayEl) todayEl.innerHTML = '<div class="ap-skeleton ap-skeleton-row"></div><div class="ap-skeleton ap-skeleton-row"></div>';

  // System status dots — just leave as "Checking…" during skeleton state
}

// ---------------------------------------------------------------------------
// KPI Cards
// ---------------------------------------------------------------------------

function renderKpiCard(id, value, label, color, icon, trend) {
  const el = document.getElementById(id);
  if (!el) return;
  if (trend === undefined) trend = null;
  el.innerHTML = `
    <div class="ap-kpi-icon" style="color:var(--ap-${color})">${icon}</div>
    <div class="ap-kpi-value" style="color:var(--ap-${color})">${value}</div>
    <div class="ap-kpi-label">${label}</div>
    ${trend !== null ? `<div class="ap-kpi-trend ${trend >= 0 ? 'up' : 'down'}">${trend >= 0 ? '&#8593;' : '&#8595;'} ${Math.abs(trend)}%</div>` : ''}
  `;
  const valueEl = el.querySelector('.ap-kpi-value');
  if (valueEl) animateCounter(valueEl, value);
}

function showKpiError() {
  ['kpi-pending', 'kpi-today', 'kpi-week', 'kpi-total'].forEach(function(id) {
    const el = document.getElementById(id);
    if (el) el.innerHTML = '<div class="ap-error-state">&#9888; Error</div>';
  });
}

// ---------------------------------------------------------------------------
// Pipeline Visualization
// ---------------------------------------------------------------------------

function renderPipeline(stages) {
  const container = document.getElementById('ap-pipeline');
  if (!container) return;
  if (!stages || stages.length === 0) {
    container.innerHTML = '<div class="ap-empty-state">No pipeline data available</div>';
    return;
  }

  const icons   = ['&#128231;', '&#128269;', '&#128228;', '&#9989;'];
  const labels  = ['Email In', 'Extracted', 'Sent to Owner', 'Confirmed'];
  const firstCount = stages[0] ? (stages[0].count || 1) : 1;

  let html = '<div class="ap-pipeline-track">';

  stages.forEach(function(stage, idx) {
    const count   = stage.count || 0;
    const pct     = firstCount > 0 ? Math.round((count / firstCount) * 100) : 0;
    const icon    = icons[idx]  || '&#9679;';
    const label   = labels[idx] || stage.label || ('Stage ' + (idx + 1));
    const barW    = Math.max(pct, 4);

    html += `
      <div class="ap-pipeline-node">
        <div class="ap-pipeline-node-icon">${icon}</div>
        <div class="ap-pipeline-node-count">${count.toLocaleString()}</div>
        <div class="ap-pipeline-node-label">${label}</div>
        <div class="ap-pipeline-node-bar">
          <div class="ap-pipeline-node-bar-fill" style="width:${barW}%"></div>
        </div>
        <div class="ap-pipeline-node-pct">${pct}%</div>
      </div>
    `;

    if (idx < stages.length - 1) {
      html += '<div class="ap-pipeline-arrow"><span class="ap-pipeline-arrow-anim">&#10148;</span></div>';
    }
  });

  html += '</div>';
  container.innerHTML = html;
}

function showPipelineError(msg) {
  const container = document.getElementById('ap-pipeline');
  if (container) {
    container.innerHTML = `<div class="ap-error-state">&#9888; ${escapeHtml(msg || 'Pipeline unavailable')}</div>`;
  }
}

// ---------------------------------------------------------------------------
// Recent Bookings Table
// ---------------------------------------------------------------------------

function renderRecentBookings(bookings) {
  const tbody = document.getElementById('recent-bookings-tbody');
  if (!tbody) return;

  if (!bookings || bookings.length === 0) {
    tbody.innerHTML = '<tr><td colspan="5" class="ap-table-empty">&#10003; No bookings awaiting approval</td></tr>';
    return;
  }

  let rows = '';
  bookings.forEach(function(b) {
    const bd          = b.booking_data || {};
    const name        = escapeHtml(bd.name || bd.customer_name || b.customer_email || 'Unknown');
    const service     = escapeHtml(bd.service_type
      ? bd.service_type.replace(/_/g, ' ').replace(/\\b\\w/g, function(c) { return c.toUpperCase(); })
      : 'Wheel Doctor Service');
    const date        = escapeHtml(b.preferred_date || bd.preferred_date || '—');
    const statusBadge = '<span class="ap-badge ap-badge-amber">Pending</span>';
    const id          = escapeHtml(b.id || '');

    rows += `
      <tr style="cursor:pointer" onclick="openBookingDetail('${id}')">
        <td>${name}</td>
        <td>${service}</td>
        <td>${date}</td>
        <td>${statusBadge}</td>
        <td class="ap-table-actions" style="white-space:nowrap" onclick="event.stopPropagation()">
          <button class="ap-btn ap-btn-sm ap-btn-success"
                  onclick="confirmBooking('${id}')">Confirm</button>
          <button class="ap-btn ap-btn-sm ap-btn-danger"
                  onclick="declineBooking('${id}')">Decline</button>
        </td>
      </tr>
    `;
  });

  tbody.innerHTML = rows;
}

// ---------------------------------------------------------------------------
// Today's Jobs Timeline
// ---------------------------------------------------------------------------

function renderTodayJobs(bookings) {
  const container = document.getElementById('today-jobs-list');
  if (!container) return;

  if (!bookings || bookings.length === 0) {
    container.innerHTML = '<div class="ap-empty-state">No confirmed jobs today</div>';
    return;
  }

  // Sort by preferred_time ascending
  const sorted = bookings.slice().sort(function(a, b) {
    const ta = (a.booking_data || {}).preferred_time || '';
    const tb = (b.booking_data || {}).preferred_time || '';
    return ta.localeCompare(tb);
  });

  let html = '<div class="ap-timeline">';
  sorted.forEach(function(b) {
    const bd     = b.booking_data || {};
    const time   = escapeHtml(bd.preferred_time || '—');
    const name   = escapeHtml(bd.name || bd.customer_name || b.customer_email || 'Unknown');
    const suburb = escapeHtml(bd.suburb || bd.address_suburb || bd.location_suburb || '');
    const service = escapeHtml(bd.service_type
      ? bd.service_type.replace(/_/g, ' ').replace(/\\b\\w/g, function(c) { return c.toUpperCase(); })
      : 'Wheel Doctor Service');

    html += `
      <div class="ap-timeline-item">
        <div class="ap-timeline-dot"></div>
        <div class="ap-timeline-time">${time}</div>
        <div class="ap-timeline-content">
          <div class="ap-timeline-name">${name}</div>
          <div class="ap-timeline-meta">${service}${suburb ? ' &bull; ' + suburb : ''}</div>
        </div>
      </div>
    `;
  });
  html += '</div>';
  container.innerHTML = html;
}

// ---------------------------------------------------------------------------
// System Status
// ---------------------------------------------------------------------------

function renderSystemStatus(health) {
  // API returns {gmail:{status:'ok',...}, db:{status:'ok',...}, anthropic:{...}, twilio:{...}}
  // HTML has cards for Gmail, Calendar (repurposed to Anthropic AI), and Database
  const services = [
    { key: 'gmail',     dotId: 'status-gmail-dot',     textId: 'status-gmail-text' },
    { key: 'anthropic', dotId: 'status-calendar-dot',  textId: 'status-calendar-text' },
    { key: 'db',        dotId: 'status-db-dot',        textId: 'status-db-text' },
  ];

  services.forEach(function(svc) {
    const dot  = document.getElementById(svc.dotId);
    const text = document.getElementById(svc.textId);
    if (!dot && !text) return;

    let dotClass  = 'ap-status-dot';
    let labelText = 'Unknown';

    if (health) {
      const entry = health[svc.key];
      // entry is an object {status: 'ok'/'error'/'unconfigured'/'configured', ...}
      const statusVal = entry ? (entry.status || entry) : null;
      if (statusVal === 'ok' || statusVal === 'healthy' || statusVal === 'configured') {
        dotClass  += ' ap-status-ok';
        labelText  = statusVal === 'configured' ? 'Configured' : 'OK';
      } else if (statusVal === 'error' || statusVal === 'unhealthy') {
        dotClass  += ' ap-status-error';
        labelText  = 'Error';
      } else if (statusVal === 'unconfigured') {
        dotClass  += ' ap-status-warning';
        labelText  = 'Not set';
      } else if (statusVal) {
        dotClass  += ' ap-status-ok';
        labelText  = String(statusVal);
      }
    }

    if (dot)  dot.className  = dotClass;
    if (text) text.textContent = labelText;
  });
}

// ---------------------------------------------------------------------------
// Quick Actions — confirm / decline
// ---------------------------------------------------------------------------

async function confirmBooking(bookingId) {
  try {
    await apiFetch('/v2/api/bookings/' + bookingId + '/confirm', { method: 'POST' });
    showToast('Booking confirmed!', 'success');
    initDashboard();
  } catch (e) {
    showToast(e.message || 'Could not confirm booking', 'error');
  }
}

async function declineBooking(bookingId) {
  if (!confirm('Decline this booking?')) return;
  try {
    await apiFetch('/v2/api/bookings/' + bookingId + '/decline', { method: 'POST' });
    showToast('Booking declined', 'info');
    initDashboard();
  } catch (e) {
    showToast(e.message || 'Could not decline booking', 'error');
  }
}

// ---------------------------------------------------------------------------
// Pending badge
// ---------------------------------------------------------------------------

function updatePendingBadge(count) {
  let badge = document.getElementById('ap-pending-fab');
  if (count > 0) {
    if (!badge) {
      badge = document.createElement('div');
      badge.id = 'ap-pending-fab';
      badge.className = 'ap-fab';
      badge.title = 'Pending bookings';
      badge.setAttribute('onclick', "showSection('bookings')");
      document.body.appendChild(badge);
    }
    badge.innerHTML = `
      <span class="ap-fab-icon">&#9203;</span>
      <span class="ap-fab-badge">${count}</span>
    `;
    badge.style.display = 'flex';
  } else {
    if (badge) badge.style.display = 'none';
  }
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function showSectionError(containerId, message) {
  const el = document.getElementById(containerId);
  if (el) {
    el.innerHTML = `<div class="ap-error-state">&#9888; ${escapeHtml(message || 'An error occurred')}</div>`;
  }
}


// ---------------------------------------------------------------------------
// KPI Card click navigation
// ---------------------------------------------------------------------------

function wireKpiClicks() {
  const map = {
    'kpi-pending': function() { showSection('bookings'); setTimeout(function() { filterBookings('awaiting_owner'); }, 300); },
    'kpi-today':   function() { showSection('bookings'); setTimeout(function() { filterBookings('confirmed'); }, 300); },
    'kpi-week':    function() { showSection('bookings'); setTimeout(function() { filterBookings('confirmed'); }, 300); },
    'kpi-total':   function() { showSection('bookings'); setTimeout(function() { filterBookings('all'); }, 300); },
  };
  Object.entries(map).forEach(function(entry) {
    var id = entry[0], fn = entry[1];
    var el = document.getElementById(id);
    if (el) { el.style.cursor = 'pointer'; el.onclick = fn; el.title = 'Click to view'; }
  });
}
"""
