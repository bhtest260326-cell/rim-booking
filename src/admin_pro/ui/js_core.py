JS_CORE = """
// ============================================================
// Admin Pro — Core JavaScript Framework
// ============================================================

// ── Global State ─────────────────────────────────────────────
const APP = {
  currentSection: 'dashboard',
  refreshTimers: {},
  charts: {},
  sidebarCollapsed: false,
};

// ── Section Title Map ────────────────────────────────────────
const SECTION_META = {
  dashboard: { title: 'Dashboard',       subtitle: 'Overview & live metrics' },
  bookings:  { title: 'Bookings',        subtitle: 'Manage and review all bookings' },
  analytics: { title: 'Analytics',       subtitle: 'Performance metrics and trends' },
  calendar:  { title: 'Calendar',        subtitle: 'Schedule view' },
  comms:     { title: 'Communications',  subtitle: 'Email, SMS and queue management' },
  customers: { title: 'Customers',       subtitle: 'Customer profiles and history' },
  system:    { title: 'System',          subtitle: 'Feature flags and system health' },
  activity:  { title: 'Activity Feed',   subtitle: 'Audit log and recent events' },
};

// ── Section Init Map ─────────────────────────────────────────
const SECTION_INIT = {
  dashboard: () => typeof initDashboard  === 'function' && initDashboard(),
  bookings:  () => typeof initBookings   === 'function' && initBookings(),
  analytics: () => typeof initAnalytics  === 'function' && initAnalytics(),
  calendar:  () => typeof initCalendar   === 'function' && initCalendar(),
  comms:     () => typeof initComms      === 'function' && initComms(),
  customers: () => typeof initCustomers  === 'function' && initCustomers(),
  system:    () => typeof initSystem     === 'function' && initSystem(),
  activity:  () => typeof initActivity   === 'function' && initActivity(),
};

// ── Section Navigation ───────────────────────────────────────
function showSection(name) {
  if (!SECTION_META[name]) {
    console.warn('showSection: unknown section', name);
    return;
  }

  // Hide all sections
  document.querySelectorAll('.ap-section').forEach(el => {
    el.style.display = 'none';
  });

  // Show target section
  const target = document.getElementById('section-' + name);
  if (target) {
    target.style.display = 'block';
  }

  // Update nav active state
  document.querySelectorAll('.ap-nav-item').forEach(el => {
    el.classList.remove('active');
    if (el.dataset.section === name) {
      el.classList.add('active');
    }
  });

  // Update page title and subtitle
  const meta = SECTION_META[name];
  const titleEl = document.getElementById('ap-page-title');
  const subtitleEl = document.getElementById('ap-page-subtitle');
  if (titleEl) titleEl.textContent = meta.title;
  if (subtitleEl) subtitleEl.textContent = meta.subtitle;

  // Clear auto-refresh timers for sections other than the new one
  Object.keys(APP.refreshTimers).forEach(section => {
    if (section !== name) {
      clearInterval(APP.refreshTimers[section]);
      delete APP.refreshTimers[section];
    }
  });

  // Update state
  APP.currentSection = name;

  // Call section-specific init
  if (SECTION_INIT[name]) {
    SECTION_INIT[name]();
  }
}

// ── API Client ───────────────────────────────────────────────
async function apiFetch(path, options = {}) {
  // Prepend /v2 if not already present
  if (!path.startsWith('/v2')) {
    path = '/v2' + (path.startsWith('/') ? path : '/' + path);
  }

  // Append auth token if available (injected by serve_spa into window.__AP_TOKEN)
  if (window.__AP_TOKEN) {
    path = path + (path.includes('?') ? '&' : '?') + 'token=' + encodeURIComponent(window.__AP_TOKEN);
  }

  const method = (options.method || 'GET').toUpperCase();

  const headers = Object.assign({}, options.headers || {});
  if ((method === 'POST' || method === 'PUT') && !headers['Content-Type']) {
    headers['Content-Type'] = 'application/json';
  }

  let response;
  try {
    response = await fetch(path, Object.assign({}, options, { method, headers, credentials: 'same-origin' }));
  } catch (networkErr) {
    showToast('Network error — could not reach the server.', 'error');
    throw networkErr;
  }

  if (response.status === 401) {
    showToast('Session expired. Please log in again.', 'error', 6000);
    throw new Error('Unauthorized');
  }

  if (!response.ok) {
    let message = 'Request failed (' + response.status + ')';
    try {
      const errData = await response.json();
      if (errData && (errData.message || errData.error)) {
        message = errData.message || errData.error;
      }
    } catch (_) {}
    throw new Error(message);
  }

  return response.json();
}

// ── Toast Notifications ──────────────────────────────────────
const TOAST_ICONS = {
  success: '✓',
  error:   '✕',
  info:    'ℹ',
  warning: '⚠',
};

function showToast(message, type = 'info', duration = 4000) {
  const container = document.getElementById('ap-toast-container');
  if (!container) return null;

  const toast = document.createElement('div');
  toast.className = 'ap-toast ap-toast--' + type;
  toast.style.cssText = [
    'display:flex',
    'align-items:center',
    'gap:10px',
    'padding:12px 16px',
    'border-radius:6px',
    'margin-bottom:8px',
    'box-shadow:0 4px 12px rgba(0,0,0,0.15)',
    'opacity:0',
    'transform:translateX(40px)',
    'transition:opacity 0.25s ease, transform 0.25s ease',
    'cursor:pointer',
    'max-width:360px',
    'word-break:break-word',
  ].join(';');

  const icon = document.createElement('span');
  icon.className = 'ap-toast__icon';
  icon.textContent = TOAST_ICONS[type] || TOAST_ICONS.info;
  icon.style.cssText = 'font-size:16px;flex-shrink:0;font-weight:bold;';

  const text = document.createElement('span');
  text.className = 'ap-toast__message';
  text.textContent = message;
  text.style.cssText = 'flex:1;font-size:14px;';

  const closeBtn = document.createElement('button');
  closeBtn.className = 'ap-toast__close';
  closeBtn.textContent = '×';
  closeBtn.style.cssText = [
    'background:none',
    'border:none',
    'cursor:pointer',
    'font-size:18px',
    'line-height:1',
    'padding:0',
    'opacity:0.7',
    'flex-shrink:0',
  ].join(';');

  toast.appendChild(icon);
  toast.appendChild(text);
  toast.appendChild(closeBtn);
  container.appendChild(toast);

  // Trigger slide-in animation
  requestAnimationFrame(() => {
    toast.style.opacity = '1';
    toast.style.transform = 'translateX(0)';
  });

  function removeToast() {
    toast.style.opacity = '0';
    toast.style.transform = 'translateX(40px)';
    setTimeout(() => {
      if (toast.parentNode) toast.parentNode.removeChild(toast);
    }, 280);
  }

  closeBtn.addEventListener('click', removeToast);
  toast.addEventListener('click', removeToast);

  if (duration > 0) {
    setTimeout(removeToast, duration);
  }

  return toast;
}

// ── Modal Management ─────────────────────────────────────────
function showModal(title, bodyHtml, footerHtml = '') {
  const overlay = document.getElementById('ap-modal-overlay');
  if (!overlay) return;

  document.getElementById('ap-modal-title').textContent = title;
  document.getElementById('ap-modal-body').innerHTML  = bodyHtml;
  document.getElementById('ap-modal-footer').innerHTML = footerHtml;

  overlay.style.display = 'flex';

  const dialog = overlay.querySelector('.ap-modal-dialog') || overlay.firstElementChild;
  if (dialog) {
    dialog.classList.remove('ap-modal--slide-up');
    void dialog.offsetWidth; // force reflow
    dialog.classList.add('ap-modal--slide-up');
  }
}

function closeModal() {
  const overlay = document.getElementById('ap-modal-overlay');
  if (overlay) overlay.style.display = 'none';
}

// ── Date / Time Utilities ────────────────────────────────────
const MONTH_SHORT = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
const DAY_SHORT   = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'];

function _parseDate(str) {
  // Accept "2026-04-09" or ISO strings
  if (!str) return null;
  const d = new Date(str);
  return isNaN(d.getTime()) ? null : d;
}

function _pad2(n) {
  return String(n).padStart(2, '0');
}

// "2026-04-09" → "Wed 09 Apr 2026"
function formatDate(str) {
  const d = _parseDate(str);
  if (!d) return str || '';
  return DAY_SHORT[d.getDay()] + ' ' + _pad2(d.getDate()) + ' ' + MONTH_SHORT[d.getMonth()] + ' ' + d.getFullYear();
}

// ISO string → "09 Apr 2026 14:32"
function formatDateTime(str) {
  const d = _parseDate(str);
  if (!d) return str || '';
  return (
    _pad2(d.getDate()) + ' ' +
    MONTH_SHORT[d.getMonth()] + ' ' +
    d.getFullYear() + ' ' +
    _pad2(d.getHours()) + ':' +
    _pad2(d.getMinutes())
  );
}

// ISO string → "2 hours ago", "yesterday", "3 days ago"
function relativeTime(str) {
  const d = _parseDate(str);
  if (!d) return str || '';
  const now   = Date.now();
  const diffMs = now - d.getTime();
  const diffSec = Math.floor(diffMs / 1000);
  const diffMin = Math.floor(diffSec / 60);
  const diffHr  = Math.floor(diffMin / 60);
  const diffDay = Math.floor(diffHr  / 24);

  if (diffSec < 60)       return 'just now';
  if (diffMin < 60)       return diffMin + ' minute' + (diffMin === 1 ? '' : 's') + ' ago';
  if (diffHr  < 24)       return diffHr  + ' hour'   + (diffHr  === 1 ? '' : 's') + ' ago';
  if (diffDay === 1)      return 'yesterday';
  if (diffDay < 30)       return diffDay + ' day'    + (diffDay === 1 ? '' : 's') + ' ago';
  const diffMo = Math.floor(diffDay / 30);
  if (diffMo  < 12)       return diffMo  + ' month'  + (diffMo  === 1 ? '' : 's') + ' ago';
  const diffYr = Math.floor(diffMo / 12);
  return diffYr + ' year' + (diffYr === 1 ? '' : 's') + ' ago';
}

// "2026-04-09" → "09 Apr"
function formatDateShort(str) {
  const d = _parseDate(str);
  if (!d) return str || '';
  return _pad2(d.getDate()) + ' ' + MONTH_SHORT[d.getMonth()];
}

// ── Utility Functions ────────────────────────────────────────
function debounce(fn, delay = 300) {
  let timer;
  return function(...args) {
    clearTimeout(timer);
    timer = setTimeout(() => fn.apply(this, args), delay);
  };
}

function escapeHtml(str) {
  if (str === null || str === undefined) return '';
  return String(str)
    .replace(/&/g,  '&amp;')
    .replace(/</g,  '&lt;')
    .replace(/>/g,  '&gt;')
    .replace(/"/g,  '&quot;')
    .replace(/'/g,  '&#39;');
}

function capitalize(str) {
  if (!str) return '';
  return str.charAt(0).toUpperCase() + str.slice(1);
}

// Status → styled badge HTML
function statusBadge(status) {
  const STATUS_MAP = {
    awaiting_owner: { label: 'Pending',   cls: 'ap-badge--amber'  },
    confirmed:      { label: 'Confirmed', cls: 'ap-badge--green'  },
    declined:       { label: 'Declined',  cls: 'ap-badge--red'    },
    completed:      { label: 'Completed', cls: 'ap-badge--blue'   },
    cancelled:      { label: 'Cancelled', cls: 'ap-badge--grey'   },
    pending:        { label: 'Pending',   cls: 'ap-badge--amber'  },
  };
  const s   = (status || '').toLowerCase();
  const map = STATUS_MAP[s] || { label: capitalize(s.replace(/_/g, ' ')), cls: 'ap-badge--grey' };
  return '<span class="ap-badge ' + map.cls + '">' + escapeHtml(map.label) + '</span>';
}

// Service type → human label
function serviceLabel(type) {
  const SERVICE_MAP = {
    rim_repair:    'Rim Repair',
    paint_touchup: 'Paint Touch-up',
    paint_touch_up: 'Paint Touch-up',
    powder_coat:   'Powder Coat',
    straightening: 'Straightening',
    refurb:        'Full Refurb',
    full_refurb:   'Full Refurb',
    other:         'Other',
  };
  if (!type) return 'Unknown';
  return SERVICE_MAP[type.toLowerCase()] || capitalize(type.replace(/_/g, ' '));
}

// Animate a counter from 0 → target
function animateCounter(el, target, duration = 800) {
  if (!el) return;
  const start     = performance.now();
  const startVal  = 0;
  const endVal    = Number(target) || 0;

  function step(now) {
    const elapsed  = now - start;
    const progress = Math.min(elapsed / duration, 1);
    // ease-out cubic
    const eased    = 1 - Math.pow(1 - progress, 3);
    el.textContent = Math.round(startVal + (endVal - startVal) * eased);
    if (progress < 1) requestAnimationFrame(step);
  }

  requestAnimationFrame(step);
}

// Toggle sidebar collapsed state
function toggleSidebar() {
  const sidebar = document.querySelector('.ap-sidebar');
  if (!sidebar) return;
  APP.sidebarCollapsed = !APP.sidebarCollapsed;
  if (APP.sidebarCollapsed) {
    sidebar.classList.add('collapsed');
  } else {
    sidebar.classList.remove('collapsed');
  }
}

// ── Refresh System ───────────────────────────────────────────
function refreshCurrentSection() {
  const section = APP.currentSection;

  // Show spinner on refresh button
  const refreshBtn = document.getElementById('ap-refresh-btn');
  if (refreshBtn) {
    refreshBtn.classList.add('spinning');
    setTimeout(() => refreshBtn.classList.remove('spinning'), 1000);
  }

  if (SECTION_INIT[section]) {
    SECTION_INIT[section]();
  }
}

function setAutoRefresh(section, intervalMs) {
  // Clear any existing timer for this section
  if (APP.refreshTimers[section]) {
    clearInterval(APP.refreshTimers[section]);
    delete APP.refreshTimers[section];
  }

  if (intervalMs > 0) {
    APP.refreshTimers[section] = setInterval(() => {
      // Only fire if this section is still active
      if (APP.currentSection === section && SECTION_INIT[section]) {
        SECTION_INIT[section]();
      }
    }, intervalMs);
  }
}

// ── Global Search ────────────────────────────────────────────
const globalSearch = debounce(function(query) {
  if (!query || query.length < 2) return;

  if (APP.currentSection !== 'bookings') {
    showSection('bookings');
  }

  const searchInput = document.getElementById('bookings-search');
  if (searchInput) {
    searchInput.value = query;
    searchInput.dispatchEvent(new Event('input'));
  }
}, 400);

// ── Notifications Bell ───────────────────────────────────────
function toggleNotifications() {
  // Placeholder — a notifications panel can be injected here
  const panel = document.getElementById('ap-notif-panel');
  if (panel) {
    const isVisible = panel.style.display !== 'none' && panel.style.display !== '';
    panel.style.display = isVisible ? 'none' : 'block';
  } else {
    showToast('No new notifications.', 'info', 3000);
  }
}

async function loadNotificationCount() {
  const badge = document.getElementById('ap-notif-count');
  if (!badge) return;

  try {
    const data = await apiFetch('/api/bookings/stats');
    const pending = (data && data.pending !== undefined) ? Number(data.pending) : 0;

    if (pending > 0) {
      badge.textContent = pending > 99 ? '99+' : String(pending);
      badge.style.display = 'inline-flex';
    } else {
      badge.textContent = '';
      badge.style.display = 'none';
    }
  } catch (err) {
    // Silent fail — notifications are non-critical
    console.debug('loadNotificationCount error:', err.message);
  }
}

// ── Initialization ───────────────────────────────────────────
document.addEventListener('DOMContentLoaded', function() {
  // Boot the default section
  showSection('dashboard');

  // Load notification badge immediately, then poll every minute
  loadNotificationCount();
  setInterval(loadNotificationCount, 60000);

  // Global keyboard shortcuts
  document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') {
      closeModal();
    }
  });

  // Wire up the sidebar toggle button if present
  const sidebarToggle = document.getElementById('ap-sidebar-toggle');
  if (sidebarToggle) {
    sidebarToggle.addEventListener('click', toggleSidebar);
  }

  // Wire up the refresh button if present
  const refreshBtn = document.getElementById('ap-refresh-btn');
  if (refreshBtn) {
    refreshBtn.addEventListener('click', refreshCurrentSection);
  }

  // Wire up modal close controls
  const modalOverlay = document.getElementById('ap-modal-overlay');
  if (modalOverlay) {
    // Close when clicking backdrop (outside dialog)
    modalOverlay.addEventListener('click', function(e) {
      if (e.target === modalOverlay) closeModal();
    });
  }
  const modalCloseBtn = document.getElementById('ap-modal-close');
  if (modalCloseBtn) {
    modalCloseBtn.addEventListener('click', closeModal);
  }

  // Wire up global search input
  const globalSearchInput = document.getElementById('ap-global-search');
  if (globalSearchInput) {
    globalSearchInput.addEventListener('input', function() {
      globalSearch(this.value.trim());
    });
    globalSearchInput.addEventListener('keydown', function(e) {
      if (e.key === 'Enter') {
        globalSearch(this.value.trim());
      }
    });
  }

  // Wire up nav items (data-section attribute routing)
  document.querySelectorAll('.ap-nav-item[data-section]').forEach(function(item) {
    item.addEventListener('click', function(e) {
      e.preventDefault();
      showSection(this.dataset.section);
    });
  });

  // Wire up notifications bell
  const notifBell = document.getElementById('ap-notif-bell');
  if (notifBell) {
    notifBell.addEventListener('click', toggleNotifications);
  }
});
"""
