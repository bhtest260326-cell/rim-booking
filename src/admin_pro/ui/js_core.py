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

  const method = (options.method || 'GET').toUpperCase();

  const headers = Object.assign({}, options.headers || {});
  if ((method === 'POST' || method === 'PUT') && !headers['Content-Type']) {
    headers['Content-Type'] = 'application/json';
  }
  // Include CSRF token for state-changing requests (read from ap_csrf cookie)
  if (method === 'POST' || method === 'PUT' || method === 'DELETE') {
    const csrfMatch = document.cookie.match(/(?:^|;\\s*)ap_csrf=([^;]+)/);
    if (csrfMatch) headers['X-CSRF-Token'] = decodeURIComponent(csrfMatch[1]);
  }

  let response;
  try {
    // credentials:'same-origin' ensures the ap_session cookie is sent with every request
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

// ── HTML Sanitizer (H5 — prevent XSS in modal innerHTML) ────
function sanitizeHtml(html) {
  if (!html) return '';
  const div = document.createElement('div');
  div.innerHTML = html;
  // Remove dangerous elements
  div.querySelectorAll('script,style,iframe,object,embed,link,meta,base').forEach(el => el.remove());
  // Strip event handlers and javascript: hrefs from all elements
  div.querySelectorAll('*').forEach(el => {
    Array.from(el.attributes).forEach(attr => {
      if (attr.name.startsWith('on')) { el.removeAttribute(attr.name); return; }
      const val = (attr.value || '').trim().toLowerCase().replace(/\\s/g, '');
      if ((attr.name === 'href' || attr.name === 'src' || attr.name === 'action') &&
          (val.startsWith('javascript:') || val.startsWith('vbscript:'))) {
        el.removeAttribute(attr.name);
      }
    });
  });
  return div.innerHTML;
}

// ── Modal Management ─────────────────────────────────────────
function showModal(title, bodyHtml, footerHtml = '') {
  const overlay = document.getElementById('ap-modal-overlay');
  if (!overlay) return;

  document.getElementById('ap-modal-title').textContent = title;
  document.getElementById('ap-modal-body').innerHTML  = bodyHtml;
  document.getElementById('ap-modal-footer').innerHTML = footerHtml;

  overlay.style.display = 'flex';
  // Force reflow before adding .open so the CSS opacity transition fires
  void overlay.offsetWidth;
  overlay.classList.add('open');
}

function closeModal() {
  const overlay = document.getElementById('ap-modal-overlay');
  if (!overlay) return;
  overlay.classList.remove('open');
  // Hide after transition completes (200ms matches CSS transition)
  setTimeout(() => { if (!overlay.classList.contains('open')) overlay.style.display = 'none'; }, 210);
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
  if (diffMs < 0) return formatDateShort(str);
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
    rim_repair:    'Wheel Doctor Service',
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

// Toggle sidebar — desktop collapses to icon-only; mobile slides in as overlay
function toggleSidebar() {
  const sidebar  = document.querySelector('.ap-sidebar');
  const main     = document.getElementById('ap-main');
  const overlay  = document.getElementById('ap-sidebar-overlay');
  if (!sidebar) return;

  const isMobile = window.innerWidth <= 768;

  if (isMobile) {
    // Mobile: slide sidebar in/out as an overlay
    const isOpen = sidebar.classList.contains('mobile-open');
    if (isOpen) {
      sidebar.classList.remove('mobile-open');
      if (overlay) overlay.classList.remove('active');
    } else {
      sidebar.classList.add('mobile-open');
      if (overlay) overlay.classList.add('active');
    }
  } else {
    // Desktop: collapse sidebar to icon-only width
    APP.sidebarCollapsed = !APP.sidebarCollapsed;
    if (APP.sidebarCollapsed) {
      sidebar.classList.add('collapsed');
      if (main) main.classList.add('sidebar-collapsed');
    } else {
      sidebar.classList.remove('collapsed');
      if (main) main.classList.remove('sidebar-collapsed');
    }
  }
}

function closeSidebarMobile() {
  const sidebar = document.querySelector('.ap-sidebar');
  const overlay = document.getElementById('ap-sidebar-overlay');
  if (sidebar) sidebar.classList.remove('mobile-open');
  if (overlay) overlay.classList.remove('active');
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
  const clearBtn = document.getElementById('ap-search-clear');
  if (clearBtn) clearBtn.style.display = query ? 'inline' : 'none';

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

function clearSearch() {
  const searchInput = document.getElementById('ap-global-search');
  const clearBtn    = document.getElementById('ap-search-clear');
  if (searchInput) {
    searchInput.value = '';
    searchInput.dispatchEvent(new Event('input'));
  }
  if (clearBtn) clearBtn.style.display = 'none';
}

// ── Notifications Bell ───────────────────────────────────────
function toggleNotifications() {
  // Placeholder — a notifications panel can be injected here
  const panel = document.getElementById('ap-notification-panel');
  if (panel) {
    const isVisible = panel.style.display !== 'none' && panel.style.display !== '';
    panel.style.display = isVisible ? 'none' : 'block';
  } else {
    showToast('No new notifications.', 'info', 3000);
  }
}

function clearAllNotifications() {
  const panel = document.getElementById('ap-notification-panel');
  if (panel) {
    const list = document.getElementById('ap-notif-list');
    if (list) list.innerHTML = '<div class="ap-notif-empty">No new notifications.</div>';
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

// ── Admin Dropdown ───────────────────────────────────────────
function toggleAdminDropdown(e) {
  e.stopPropagation();
  const dropdown = document.getElementById('ap-admin-dropdown');
  if (!dropdown) return;
  const isOpen = dropdown.style.display !== 'none';
  dropdown.style.display = isOpen ? 'none' : 'block';
}

function closeAdminDropdown() {
  const dropdown = document.getElementById('ap-admin-dropdown');
  if (dropdown) dropdown.style.display = 'none';
}

function showChangePasswordModal() {
  closeAdminDropdown();
  showModal(
    'Change Password',
    '<div class="ap-form-group">' +
      '<label class="ap-label" for="cp-current">Current Password</label>' +
      '<input class="ap-input" id="cp-current" type="password" placeholder="Current password" autocomplete="current-password">' +
    '</div>' +
    '<div class="ap-form-group ap-mt-16">' +
      '<label class="ap-label" for="cp-new">New Password</label>' +
      '<input class="ap-input" id="cp-new" type="password" placeholder="New password" autocomplete="new-password">' +
    '</div>' +
    '<div class="ap-form-group ap-mt-16">' +
      '<label class="ap-label" for="cp-confirm">Confirm New Password</label>' +
      '<input class="ap-input" id="cp-confirm" type="password" placeholder="Confirm new password" autocomplete="new-password">' +
    '</div>',
    '<button class="ap-btn ap-btn-primary" onclick="submitChangePassword()">Update Password</button>' +
    '<button class="ap-btn ap-btn-ghost" onclick="closeModal()">Cancel</button>'
  );
}

async function submitChangePassword() {
  const current = (document.getElementById('cp-current') || {}).value || '';
  const newPw   = (document.getElementById('cp-new')     || {}).value || '';
  const confirm = (document.getElementById('cp-confirm') || {}).value || '';

  if (!current || !newPw) {
    showToast('Please fill in all fields.', 'warning');
    return;
  }
  if (newPw !== confirm) {
    showToast('New passwords do not match.', 'warning');
    return;
  }
  if (newPw.length < 8) {
    showToast('Password must be at least 8 characters.', 'warning');
    return;
  }

  try {
    await apiFetch('/api/admin/change-password', {
      method: 'POST',
      body: JSON.stringify({ current_password: current, new_password: newPw }),
    });
    closeModal();
    showToast('Password updated successfully.', 'success');
  } catch (err) {
    showToast('Failed to update password: ' + (err.message || 'Unknown error'), 'error');
  }
}

function openDocumentation() {
  closeAdminDropdown();
  showModal('Quick Reference', `
    <div style="line-height:1.8;font-size:14px">
      <p style="margin-bottom:12px"><strong>Booking flow:</strong> Customer emails → AI extracts details → Owner gets SMS → reply YES to confirm → customer notified.</p>
      <p style="margin-bottom:12px"><strong>Calendar:</strong> Click a day to see jobs. Use "Cancel Day" to notify all customers of a cancellation.</p>
      <p style="margin-bottom:12px"><strong>Feature Flags:</strong> Toggle automation on/off in System → Feature Flags. Hover the <em>i</em> icon for descriptions.</p>
      <p style="margin-bottom:12px"><strong>Customers:</strong> Click any customer row to view their full booking history.</p>
      <p style="margin-bottom:12px"><strong>Communications:</strong> View incoming emails, SMS queue, and activity log. Gmail requires OAuth to be active.</p>
      <p><strong>Support:</strong> Check Railway logs for errors. The Activity Feed shows all system events in real-time.</p>
    </div>
  `, '');
}

function adminLogout() {
  closeAdminDropdown();
  // Clear the session cookie and reload
  document.cookie = 'ap_session=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/';
  document.cookie = 'session=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/';
  window.location.reload();
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
      closeAdminDropdown();
    }
  });

  // Close admin dropdown when clicking anywhere outside
  document.addEventListener('click', function(e) {
    const badge = document.getElementById('ap-user-badge');
    if (badge && !badge.contains(e.target)) {
      closeAdminDropdown();
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
