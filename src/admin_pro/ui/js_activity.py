"""
admin_pro/ui/js_activity.py
Activity feed section JavaScript for the Admin Pro dashboard.
Provides a live audit log of booking lifecycle events with client-side
filtering, auto-refresh, and timeline-style rendering.
"""

JS_ACTIVITY = """
// ============================================================
// Admin Pro — Activity Feed Section
// ============================================================

// ── Activity State ───────────────────────────────────────────
// Tracks the current filter, auto-refresh preference and the
// setInterval handle so it can be cleared when toggled off.
const ACTIVITY_STATE = {
  filter: 'all',
  autoRefresh: true,
  refreshInterval: null,
  limit: 50,
};

// ── Init ─────────────────────────────────────────────────────
// Called by the section router whenever the activity section
// is navigated to.  Injects styles once, renders controls,
// performs the first data load, then arms the auto-refresh
// timer if enabled.
async function initActivity() {
  injectActivityStyles();
  renderActivityControls();
  await loadActivity();
  if (ACTIVITY_STATE.autoRefresh) {
    ACTIVITY_STATE.refreshInterval = setInterval(loadActivity, 30000);
  }
}

// ── Controls ─────────────────────────────────────────────────
// Renders the filter pill-buttons and the auto-refresh checkbox
// into #activity-controls.  Re-called after any state change so
// the active filter button highlights correctly.
function renderActivityControls() {
  const controls = document.getElementById('activity-controls');
  if (!controls) return;

  const filters = [
    'all',
    'created',
    'confirmed',
    'declined',
    'note',
    'rescheduled',
    'cancellation_requested',
  ];

  const filterLabels = {
    all:                    'All Events',
    created:                'Created',
    confirmed:              'Confirmed',
    declined:               'Declined',
    note:                   'Notes',
    rescheduled:            'Rescheduled',
    cancellation_requested: 'Cancellations',
  };

  controls.innerHTML = `
    <div class="ap-flex ap-gap-8" style="flex-wrap:wrap">
      ${filters.map(f => `
        <button class="ap-btn ap-btn-sm ${f === ACTIVITY_STATE.filter ? 'ap-btn-primary' : 'ap-btn-ghost'}"
                onclick="setActivityFilter('${f}')">${filterLabels[f] || f}</button>
      `).join('')}
      <div style="margin-left:auto;display:flex;align-items:center;gap:8px">
        <label class="ap-text-muted" style="font-size:13px">
          <input type="checkbox" ${ACTIVITY_STATE.autoRefresh ? 'checked' : ''} onchange="toggleActivityAutoRefresh(this.checked)">
          Auto-refresh (30s)
        </label>
        <button class="ap-btn ap-btn-ghost ap-btn-sm" onclick="loadActivity()">↻ Refresh</button>
      </div>
    </div>
  `;
}

// Set a new filter value, re-render controls to reflect the
// active state, and immediately reload the feed.
function setActivityFilter(filter) {
  ACTIVITY_STATE.filter = filter;
  renderActivityControls();
  loadActivity();
}

// Enable or disable the 30-second auto-refresh interval.
// Always clears any existing interval first to avoid duplicates.
function toggleActivityAutoRefresh(enabled) {
  ACTIVITY_STATE.autoRefresh = enabled;
  if (ACTIVITY_STATE.refreshInterval) clearInterval(ACTIVITY_STATE.refreshInterval);
  if (enabled) ACTIVITY_STATE.refreshInterval = setInterval(loadActivity, 30000);
}

// ── Load & Render ─────────────────────────────────────────────
// Fetches events from the API, applies the client-side filter,
// and renders the timeline into #activity-feed.
// Updates #activity-last-updated with the current time.
async function loadActivity() {
  const feed = document.getElementById('activity-feed');
  if (!feed) return;

  try {
    let url = `/v2/api/comms/activity?limit=${ACTIVITY_STATE.limit}`;
    const data = await apiFetch(url);
    const events = data.events || [];

    // Filter client-side so switching filters is instant with no
    // extra network round-trips.
    const filtered = ACTIVITY_STATE.filter === 'all' ? events :
      events.filter(e => e.event_type === ACTIVITY_STATE.filter);

    if (filtered.length === 0) {
      feed.innerHTML = '<div class="ap-text-muted" style="padding:24px;text-align:center">No events found</div>';
      return;
    }

    feed.innerHTML = filtered.map((event, idx) => `
      <div class="ap-activity-item ap-animate-in" style="animation-delay:${idx * 30}ms">
        <div class="ap-activity-timeline">
          <div class="ap-activity-dot ${getEventColor(event.event_type)}">${getEventIcon(event.event_type)}</div>
          ${idx < filtered.length - 1 ? '<div class="ap-activity-line"></div>' : ''}
        </div>
        <div class="ap-activity-content">
          <div class="ap-activity-header">
            <strong class="ap-activity-type">${formatEventType(event.event_type)}</strong>
            <span class="ap-text-muted" style="font-size:12px">${relativeTime(event.created_at)}</span>
          </div>
          <div class="ap-activity-meta">
            ${event.customer_email ? `<span class="ap-text-dim">${escapeHtml(event.customer_email)}</span>` : ''}
            <span class="ap-badge ap-badge-blue" style="font-size:11px;cursor:pointer"
                  onclick="openBookingDetail('${event.booking_id}')">${event.booking_id?.substring(0,8)}…</span>
            ${event.actor !== 'system' ? `<span class="ap-badge ap-badge-purple" style="font-size:11px">${escapeHtml(event.actor)}</span>` : ''}
          </div>
          ${formatEventDetails(event.details) || ''}
        </div>
      </div>
    `).join('');

    // Update last-refreshed timestamp shown in the section header.
    const ts = document.getElementById('activity-last-updated');
    if (ts) ts.textContent = 'Updated ' + new Date().toLocaleTimeString();
  } catch (err) {
    console.error('loadActivity error:', err);
    feed.innerHTML = '<div class="ap-text-muted" style="padding:24px;text-align:center">Failed to load activity feed.</div>';
  }
}

// ── Event Formatting Helpers ──────────────────────────────────

// Returns an emoji icon for the given event type.
// Falls back to a plain bullet for unknown types.
function getEventIcon(type) {
  const icons = {
    created:                '🆕',
    confirmed:              '✅',
    declined:               '❌',
    note:                   '📝',
    rescheduled:            '📅',
    cancellation_requested: '⚠',
    reschedule_requested:   '🔄',
    cancelled:              '🚫',
    'morning_notification': '☀',
    'day_prior_reminder':   '🔔',
    default:                '●',
  };
  return icons[type] || icons.default;
}

// Returns a colour key used as a CSS class on the timeline dot.
function getEventColor(type) {
  const colors = {
    confirmed:              'green',
    declined:               'red',
    cancellation_requested: 'amber',
    cancelled:              'red',
    created:                'blue',
    note:                   'purple',
    rescheduled:            'teal',
  };
  return colors[type] || 'muted';
}

// Converts snake_case event type names to Title Case for display.
function formatEventType(type) {
  return type.replace(/_/g, ' ').replace(/\\b\\w/g, c => c.toUpperCase());
}

// Renders a compact detail line from the event's details object.
// Handles: text excerpts, reason, confidence score, date changes.
// Returns an empty string when there is nothing meaningful to show.
function formatEventDetails(details) {
  if (!details) return '';
  try {
    const d = typeof details === 'string' ? JSON.parse(details) : details;
    const parts = [];
    if (d.text)
      parts.push(`<em>"${escapeHtml(d.text.substring(0, 100))}"</em>`);
    if (d.reason)
      parts.push(`Reason: ${escapeHtml(d.reason.substring(0, 100))}`);
    if (d.confidence)
      parts.push(`Confidence: ${d.confidence}`);
    if (d.old_date && d.new_date)
      parts.push(`${formatDate(d.old_date)} → ${formatDate(d.new_date)}`);
    return parts.length
      ? `<div class="ap-activity-details">${parts.join(' · ')}</div>`
      : '';
  } catch { return ''; }
}

// ── Styles ────────────────────────────────────────────────────
// Injected once into <head> on first initActivity() call.
// The guard on #ap-activity-styles prevents duplicate injection
// when navigating away and back to the activity section.
function injectActivityStyles() {
  if (document.getElementById('ap-activity-styles')) return;
  const style = document.createElement('style');
  style.id = 'ap-activity-styles';
  style.textContent = `
    #activity-feed { max-width: 800px; }
    .ap-activity-item {
      display: flex;
      gap: 16px;
      margin-bottom: 4px;
    }
    .ap-activity-timeline {
      display: flex;
      flex-direction: column;
      align-items: center;
      flex-shrink: 0;
      width: 32px;
    }
    .ap-activity-dot {
      width: 32px;
      height: 32px;
      border-radius: 50%;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 14px;
      flex-shrink: 0;
    }
    .ap-activity-dot.green  { background: rgba(34,197,94,0.15); }
    .ap-activity-dot.red    { background: rgba(239,68,68,0.15); }
    .ap-activity-dot.amber  { background: rgba(245,158,11,0.15); }
    .ap-activity-dot.blue   { background: rgba(59,130,246,0.15); }
    .ap-activity-dot.purple { background: rgba(139,92,246,0.15); }
    .ap-activity-dot.teal   { background: rgba(20,184,166,0.15); }
    .ap-activity-dot.muted  { background: rgba(100,116,139,0.15); }
    .ap-activity-line {
      flex: 1;
      width: 2px;
      background: var(--ap-border);
      min-height: 16px;
    }
    .ap-activity-content { padding: 4px 0 20px; flex: 1; }
    .ap-activity-header {
      display: flex;
      align-items: center;
      gap: 10px;
      margin-bottom: 4px;
    }
    .ap-activity-type { font-size: 14px; }
    .ap-activity-meta {
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
      font-size: 13px;
    }
    .ap-activity-details {
      font-size: 13px;
      color: var(--ap-text-dim);
      margin-top: 4px;
      font-style: italic;
    }
    .ap-ml-8  { margin-left: 8px; }
    .ap-mb-16 { margin-bottom: 16px; }
  `;
  document.head.appendChild(style);
}
"""
