# Admin Pro Dashboard — HTML structural parts
# All SVG icons are inline 24x24 path-based icons (no external libraries)

HTML_SIDEBAR = """
<aside class="ap-sidebar" id="ap-sidebar">
  <div class="ap-sidebar-logo">
    <div class="ap-sidebar-logo-icon">
      <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" width="18" height="18">
        <path d="M3 17h1.5a2.5 2.5 0 0 0 5 0h6a2.5 2.5 0 0 0 5 0H22" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
        <path d="M2 9h14l3 5H2V9z" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
      </svg>
    </div>
    <div class="ap-sidebar-logo-text">Wheel Doctor</div>
  </div>
  <div class="ap-brand-strip">
    <span class="ap-brand-name">Control Pro</span>
    <span class="ap-brand-accent-line"></span>
  </div>

  <nav class="ap-nav">
    <div class="ap-nav-section-label">OVERVIEW</div>

    <button class="ap-nav-item active" data-section="dashboard" onclick="showSection('dashboard')">
      <svg class="ap-nav-icon" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <rect x="3" y="3" width="8" height="8" rx="1.5" stroke="currentColor" stroke-width="1.8"/>
        <rect x="13" y="3" width="8" height="8" rx="1.5" stroke="currentColor" stroke-width="1.8"/>
        <rect x="3" y="13" width="8" height="8" rx="1.5" stroke="currentColor" stroke-width="1.8"/>
        <rect x="13" y="13" width="8" height="8" rx="1.5" stroke="currentColor" stroke-width="1.8"/>
      </svg>
      <span>Dashboard</span>
    </button>

    <button class="ap-nav-item" data-section="activity" onclick="showSection('activity')">
      <svg class="ap-nav-icon" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <polyline points="22,12 18,12 15,21 9,3 6,12 2,12" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
      </svg>
      <span>Activity Feed</span>
    </button>

    <div class="ap-nav-section-label">BOOKINGS</div>

    <button class="ap-nav-item" data-section="bookings" onclick="showSection('bookings')">
      <svg class="ap-nav-icon" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
        <polyline points="14,2 14,8 20,8" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
        <line x1="8" y1="13" x2="16" y2="13" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>
        <line x1="8" y1="17" x2="13" y2="17" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>
      </svg>
      <span>Bookings</span>
    </button>

    <button class="ap-nav-item" data-section="calendar" onclick="showSection('calendar')">
      <svg class="ap-nav-icon" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <rect x="3" y="4" width="18" height="18" rx="2" stroke="currentColor" stroke-width="1.8"/>
        <line x1="16" y1="2" x2="16" y2="6" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>
        <line x1="8" y1="2" x2="8" y2="6" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>
        <line x1="3" y1="10" x2="21" y2="10" stroke="currentColor" stroke-width="1.8"/>
      </svg>
      <span>Calendar</span>
    </button>

    <button class="ap-nav-item" data-section="customers" onclick="showSection('customers')">
      <svg class="ap-nav-icon" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
        <circle cx="9" cy="7" r="4" stroke="currentColor" stroke-width="1.8"/>
        <path d="M23 21v-2a4 4 0 0 0-3-3.87" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
        <path d="M16 3.13a4 4 0 0 1 0 7.75" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
      </svg>
      <span>Customers</span>
    </button>

    <div class="ap-nav-section-label">ANALYTICS</div>

    <button class="ap-nav-item" data-section="analytics" onclick="showSection('analytics')">
      <svg class="ap-nav-icon" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <line x1="18" y1="20" x2="18" y2="10" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>
        <line x1="12" y1="20" x2="12" y2="4" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>
        <line x1="6" y1="20" x2="6" y2="14" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>
        <line x1="2" y1="20" x2="22" y2="20" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>
      </svg>
      <span>Analytics</span>
    </button>

    <div class="ap-nav-section-label">OPERATIONS</div>

    <button class="ap-nav-item" data-section="comms" onclick="showSection('comms')">
      <svg class="ap-nav-icon" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
        <polyline points="22,6 12,13 2,6" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
      </svg>
      <span>Communications</span>
    </button>

    <button class="ap-nav-item" data-section="system" onclick="showSection('system')">
      <svg class="ap-nav-icon" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <circle cx="12" cy="12" r="3" stroke="currentColor" stroke-width="1.8"/>
        <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" stroke="currentColor" stroke-width="1.8"/>
      </svg>
      <span>System</span>
    </button>
  </nav>

  <button class="ap-sidebar-toggle" id="ap-sidebar-toggle" onclick="toggleSidebar()" title="Toggle sidebar">
    <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" width="18" height="18">
      <polyline points="15,18 9,12 15,6" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
    </svg>
  </button>
</aside>
"""

HTML_TOPBAR = """
<div class="ap-topbar">
  <button class="ap-hamburger" id="ap-hamburger" onclick="toggleSidebar()" title="Toggle menu" aria-label="Toggle menu">
    <span></span><span></span><span></span>
  </button>
  <div class="ap-topbar-left">
    <h1 class="ap-page-title" id="ap-page-title">Dashboard</h1>
    <span class="ap-page-subtitle" id="ap-page-subtitle">Overview &amp; live metrics</span>
  </div>
  <div class="ap-topbar-center">
    <div class="ap-search-wrap">
      <svg class="ap-search-icon" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" width="16" height="16">
        <circle cx="11" cy="11" r="8" stroke="currentColor" stroke-width="2"/>
        <line x1="21" y1="21" x2="16.65" y2="16.65" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
      </svg>
      <input
        class="ap-search-input"
        id="ap-global-search"
        type="text"
        placeholder="Search bookings, customers..."
        oninput="globalSearch(this.value)"
        autocomplete="off"
      >
      <span class="ap-search-clear" id="ap-search-clear" onclick="clearSearch()" style="display:none">&#10005;</span>
    </div>
  </div>
  <div class="ap-topbar-right">
    <button class="ap-btn ap-btn-ghost ap-btn-sm" onclick="refreshCurrentSection()" id="ap-refresh-btn" title="Refresh">
      <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" width="15" height="15" style="margin-right:4px">
        <polyline points="23,4 23,10 17,10" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
        <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
      </svg>
      Refresh
    </button>
    <div class="ap-notification-bell" id="ap-notif-bell" onclick="toggleNotifications()" title="Notifications">
      <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" width="20" height="20">
        <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
        <path d="M13.73 21a2 2 0 0 1-3.46 0" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
      </svg>
      <span class="ap-notif-count" id="ap-notif-count" style="display:none">0</span>
    </div>
    <div class="ap-user-badge" id="ap-user-badge" onclick="toggleAdminDropdown(event)" title="Admin menu">
      <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" width="16" height="16">
        <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
        <circle cx="12" cy="7" r="4" stroke="currentColor" stroke-width="1.8"/>
      </svg>
      Admin
      <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" width="12" height="12" style="margin-left:2px;opacity:0.6">
        <polyline points="6,9 12,15 18,9" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
      </svg>
      <div class="ap-user-dropdown" id="ap-admin-dropdown" style="display:none" onclick="event.stopPropagation()">
        <button class="ap-user-dropdown-item" onclick="showChangePasswordModal()">
          <svg viewBox="0 0 24 24" fill="none" width="14" height="14"><rect x="3" y="11" width="18" height="11" rx="2" stroke="currentColor" stroke-width="1.8"/><path d="M7 11V7a5 5 0 0 1 10 0v4" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>
          Change Password
        </button>
        <button class="ap-user-dropdown-item" onclick="openDocumentation()">
          <svg viewBox="0 0 24 24" fill="none" width="14" height="14"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" stroke="currentColor" stroke-width="1.8"/><polyline points="14,2 14,8 20,8" stroke="currentColor" stroke-width="1.8"/></svg>
          Documentation
        </button>
        <hr class="ap-user-dropdown-divider">
        <button class="ap-user-dropdown-item danger" onclick="adminLogout()">
          <svg viewBox="0 0 24 24" fill="none" width="14" height="14"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/><polyline points="16,17 21,12 16,7" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/><line x1="21" y1="12" x2="9" y2="12" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>
          Logout
        </button>
      </div>
    </div>
  </div>
</div>
"""

HTML_SECTIONS = """
<!-- ═══════════════════════════════════════════════ DASHBOARD ══ -->
<section class="ap-section active" id="section-dashboard">
  <div class="ap-grid-4 ap-kpi-row">
    <div class="ap-card ap-kpi-card" id="kpi-pending">
      <div class="ap-kpi-label">Pending Bookings</div>
      <div class="ap-kpi-value" id="kpi-pending-val">—</div>
      <div class="ap-kpi-sub" id="kpi-pending-sub">awaiting confirmation</div>
    </div>
    <div class="ap-card ap-kpi-card ap-kpi-accent" id="kpi-today">
      <div class="ap-kpi-label">Today's Jobs</div>
      <div class="ap-kpi-value" id="kpi-today-val">—</div>
      <div class="ap-kpi-sub" id="kpi-today-sub">scheduled today</div>
    </div>
    <div class="ap-card ap-kpi-card" id="kpi-week">
      <div class="ap-kpi-label">This Week</div>
      <div class="ap-kpi-value" id="kpi-week-val">—</div>
      <div class="ap-kpi-sub" id="kpi-week-sub">bookings this week</div>
    </div>
    <div class="ap-card ap-kpi-card" id="kpi-total">
      <div class="ap-kpi-label">Total Bookings</div>
      <div class="ap-kpi-value" id="kpi-total-val">—</div>
      <div class="ap-kpi-sub" id="kpi-total-sub">all time</div>
    </div>
  </div>

  <div class="ap-card ap-pipeline-card">
    <div class="ap-card-header">
      <span class="ap-card-title">Booking Pipeline</span>
      <span class="ap-card-badge" id="pipeline-badge">Live</span>
    </div>
    <div class="ap-pipeline" id="ap-pipeline">
      <div class="ap-pipeline-loading">Loading pipeline…</div>
    </div>
  </div>

  <div class="ap-grid-2">
    <div class="ap-card">
      <div class="ap-card-header">
        <span class="ap-card-title">Recent Bookings</span>
        <button class="ap-btn ap-btn-ghost ap-btn-xs" onclick="showSection('bookings')">View all</button>
      </div>
      <div class="ap-table-wrap ap-recent-bookings-wrap">
        <table class="ap-table" id="recent-bookings-table">
          <thead>
            <tr>
              <th>Customer</th>
              <th>Date</th>
              <th>Service</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody id="recent-bookings-tbody">
            <tr><td colspan="4" class="ap-table-empty">Loading…</td></tr>
          </tbody>
        </table>
      </div>
    </div>

    <div class="ap-card">
      <div class="ap-card-header">
        <span class="ap-card-title">Today's Schedule</span>
        <span class="ap-card-sub" id="todays-date-label"></span>
      </div>
      <div class="ap-today-jobs" id="today-jobs-list">
        <div class="ap-today-empty">Loading today's jobs…</div>
      </div>
    </div>
  </div>

  <div class="ap-grid-3 ap-system-status-row">
    <div class="ap-card ap-status-card">
      <div class="ap-card-header"><span class="ap-card-title">Gmail</span></div>
      <div class="ap-status-indicator" id="status-gmail">
        <span class="ap-status-dot" id="status-gmail-dot"></span>
        <span id="status-gmail-text">Checking…</span>
      </div>
    </div>
    <div class="ap-card ap-status-card">
      <div class="ap-card-header"><span class="ap-card-title">AI (Anthropic)</span></div>
      <div class="ap-status-indicator" id="status-calendar">
        <span class="ap-status-dot" id="status-calendar-dot"></span>
        <span id="status-calendar-text">Checking…</span>
      </div>
    </div>
    <div class="ap-card ap-status-card">
      <div class="ap-card-header"><span class="ap-card-title">Database</span></div>
      <div class="ap-status-indicator" id="status-db">
        <span class="ap-status-dot" id="status-db-dot"></span>
        <span id="status-db-text">Checking…</span>
      </div>
    </div>
  </div>
</section>

<!-- ═══════════════════════════════════════════════ BOOKINGS ══ -->
<section class="ap-section" id="section-bookings">
  <div class="ap-card">
    <div class="ap-filter-bar">
      <div class="ap-status-pills" id="booking-status-pills">
        <button class="ap-pill active" data-status="all" onclick="filterBookings('all')">All</button>
        <button class="ap-pill" data-status="pending" onclick="filterBookings('pending')">Pending</button>
        <button class="ap-pill" data-status="confirmed" onclick="filterBookings('confirmed')">Confirmed</button>
        <button class="ap-pill" data-status="completed" onclick="filterBookings('completed')">Completed</button>
        <button class="ap-pill" data-status="cancelled" onclick="filterBookings('cancelled')">Cancelled</button>
        <button class="ap-pill" data-status="waitlist" onclick="filterBookings('waitlist')">Waitlist</button>
      </div>
      <div class="ap-filter-inputs">
        <input type="date" class="ap-input ap-input-sm" id="filter-date-from" placeholder="From" onchange="filterBookingsByDate()">
        <input type="date" class="ap-input ap-input-sm" id="filter-date-to" placeholder="To" onchange="filterBookingsByDate()">
        <input type="text" class="ap-input ap-input-sm" id="bookings-search" placeholder="Search name, email, phone…" oninput="searchBookings(this.value)">
      </div>
      <div class="ap-bulk-actions" id="bulk-actions" style="display:none">
        <span class="ap-bulk-count" id="bulk-count">0 selected</span>
        <button class="ap-btn ap-btn-sm ap-btn-danger" onclick="bulkDecline()">Cancel Selected</button>
        <button class="ap-btn ap-btn-sm ap-btn-ghost" onclick="clearBookingSelection()">Clear</button>
      </div>
    </div>

    <div class="ap-table-wrap" id="bookings-table-wrap">
      <table class="ap-table ap-table-hover" id="bookings-table">
        <thead>
          <tr>
            <th class="ap-th-check"><input type="checkbox" id="select-all-bookings" onchange="toggleSelectAll(this)"></th>
            <th class="ap-th-sortable" onclick="sortBookings('name')">Customer <span class="ap-sort-arrow">↕</span></th>
            <th class="ap-th-sortable" onclick="sortBookings('date')">Date <span class="ap-sort-arrow">↕</span></th>
            <th>Time</th>
            <th>Service</th>
            <th>Rims</th>
            <th>Suburb</th>
            <th class="ap-th-sortable" onclick="sortBookings('status')">Status <span class="ap-sort-arrow">↕</span></th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody id="bookings-tbody">
          <tr><td colspan="9" class="ap-table-empty">Loading bookings…</td></tr>
        </tbody>
      </table>
    </div>

    <div class="ap-pagination" id="bookings-pagination">
      <!-- JS replaces this with dynamic pagination controls -->
    </div>
  </div>
</section>

<!-- ═══════════════════════════════════════════════ ANALYTICS ══ -->
<section class="ap-section" id="section-analytics">
  <div class="ap-grid-4 ap-kpi-row">
    <div class="ap-card ap-kpi-card" id="ana-conversion">
      <div class="ap-kpi-label">Conversion Rate</div>
      <div class="ap-kpi-value" id="ana-conversion-val">—</div>
      <div class="ap-kpi-sub">enquiry → booking</div>
    </div>
    <div class="ap-card ap-kpi-card" id="ana-avg-confirm">
      <div class="ap-kpi-label">Avg. Confirm Time</div>
      <div class="ap-kpi-value" id="ana-avg-confirm-val">—</div>
      <div class="ap-kpi-sub">minutes to confirm</div>
    </div>
    <div class="ap-card ap-kpi-card ap-kpi-accent" id="ana-week">
      <div class="ap-kpi-label">Bookings This Week</div>
      <div class="ap-kpi-value" id="ana-week-val">—</div>
      <div class="ap-kpi-sub" id="ana-week-delta"></div>
    </div>
  </div>

  <div class="ap-grid-2">
    <div class="ap-card">
      <div class="ap-card-header">
        <span class="ap-card-title">Bookings Trend (30 days)</span>
        <div class="ap-chart-controls">
          <button class="ap-pill ap-pill-xs active" onclick="setTrendPeriod(30)">30d</button>
          <button class="ap-pill ap-pill-xs" onclick="setTrendPeriod(90)">90d</button>
        </div>
      </div>
      <div class="ap-chart-container" id="chart-trend">
        <canvas id="canvas-trend"></canvas>
        <div class="ap-chart-placeholder" id="trend-placeholder">Loading chart…</div>
      </div>
    </div>
    <div class="ap-card">
      <div class="ap-card-header">
        <span class="ap-card-title">Service Type Breakdown</span>
      </div>
      <div class="ap-chart-container" id="chart-service">
        <canvas id="canvas-service"></canvas>
        <div class="ap-chart-placeholder" id="service-placeholder">Loading chart…</div>
      </div>
    </div>
  </div>

  <div class="ap-grid-2">
    <div class="ap-card">
      <div class="ap-card-header">
        <span class="ap-card-title">Conversion Funnel</span>
      </div>
      <div class="ap-chart-container" id="chart-funnel">
        <div class="ap-funnel" id="funnel-chart">
          <div class="ap-funnel-step" id="funnel-enquiries">
            <div class="ap-funnel-bar" style="width:100%"></div>
            <div class="ap-funnel-label">Enquiries <span id="funnel-enquiries-n">—</span></div>
          </div>
          <div class="ap-funnel-step" id="funnel-pending">
            <div class="ap-funnel-bar" style="width:75%"></div>
            <div class="ap-funnel-label">Pending <span id="funnel-pending-n">—</span></div>
          </div>
          <div class="ap-funnel-step" id="funnel-confirmed">
            <div class="ap-funnel-bar" style="width:55%"></div>
            <div class="ap-funnel-label">Confirmed <span id="funnel-confirmed-n">—</span></div>
          </div>
          <div class="ap-funnel-step" id="funnel-completed">
            <div class="ap-funnel-bar" style="width:40%"></div>
            <div class="ap-funnel-label">Completed <span id="funnel-completed-n">—</span></div>
          </div>
        </div>
      </div>
    </div>
    <div class="ap-card ap-card-suburbs">
      <div class="ap-card-header">
        <span class="ap-card-title">Top Suburbs</span>
      </div>
      <div class="ap-suburbs-list" id="suburbs-list">
        <div class="ap-table-empty">Loading…</div>
      </div>
    </div>
  </div>

</section>

<!-- ═══════════════════════════════════════════════ CALENDAR ══ -->
<section class="ap-section" id="section-calendar">
  <div class="ap-calendar-layout">
    <div class="ap-calendar-main">
      <div class="ap-calendar-header">
        <button class="ap-btn ap-btn-ghost ap-btn-sm" onclick="calendarNav(-1)" id="cal-prev">
          <svg viewBox="0 0 24 24" fill="none" width="16" height="16"><polyline points="15,18 9,12 15,6" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>
        </button>
        <h2 class="ap-calendar-month-title" id="ap-calendar-title">Month Year</h2>
        <button class="ap-btn ap-btn-ghost ap-btn-sm" onclick="calendarNav(1)" id="cal-next">
          <svg viewBox="0 0 24 24" fill="none" width="16" height="16"><polyline points="9,18 15,12 9,6" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>
        </button>
        <div class="ap-calendar-view-toggle">
          <button class="ap-pill active" id="cal-view-month" onclick="setCalendarView('month')">Month</button>
          <button class="ap-pill" id="cal-view-week" onclick="setCalendarView('week')">Week</button>
        </div>
        <button class="ap-btn ap-btn-ghost ap-btn-sm" onclick="goToToday()">Today</button>
      </div>

      <div class="ap-calendar-weekdays">
        <div>Mon</div><div>Tue</div><div>Wed</div><div>Thu</div>
        <div>Fri</div><div>Sat</div><div>Sun</div>
      </div>

      <div class="ap-calendar" id="ap-calendar-grid">
        <div class="ap-calendar-loading">Loading calendar…</div>
      </div>
    </div>

    <div class="ap-day-detail-panel" id="ap-day-detail">
      <div class="ap-day-detail-header">
        <span class="ap-card-title" id="day-detail-title">Select a day</span>
        <span class="ap-card-badge" id="day-detail-count"></span>
      </div>
      <div class="ap-day-jobs-list" id="day-jobs-list">
        <div class="ap-today-empty">Click a calendar day to see jobs.</div>
      </div>
      <div class="ap-day-detail-actions" id="day-detail-actions" style="display:none">
        <button class="ap-btn ap-btn-sm ap-btn-danger" onclick="cancelDayPrompt()">Cancel All Jobs This Day</button>
      </div>
    </div>
  </div>
</section>

<!-- ═══════════════════════════════════════════════ COMMS ══ -->
<section class="ap-section" id="section-comms">
  <div class="ap-tabs" id="comms-tabs">
    <button class="ap-tab active" data-tab="gmail" onclick="switchCommsTab('gmail')">
      <svg viewBox="0 0 24 24" fill="none" width="15" height="15" style="margin-right:5px"><path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z" stroke="currentColor" stroke-width="1.8"/><polyline points="22,6 12,13 2,6" stroke="currentColor" stroke-width="1.8"/></svg>
      Gmail
      <span class="ap-tab-badge" id="tab-badge-gmail"></span>
    </button>
    <button class="ap-tab" data-tab="dlq" onclick="switchCommsTab('dlq')">
      Dead-Letter Queue
      <span class="ap-tab-badge" id="tab-badge-dlq"></span>
    </button>
    <button class="ap-tab" data-tab="clarifications" onclick="switchCommsTab('clarifications')">
      Clarifications
      <span class="ap-tab-badge" id="tab-badge-clarifications"></span>
    </button>
    <button class="ap-tab" data-tab="waitlist" onclick="switchCommsTab('waitlist')">
      Waitlist
      <span class="ap-tab-badge" id="tab-badge-waitlist"></span>
    </button>
    <button class="ap-tab" data-tab="sms" onclick="switchCommsTab('sms')">
      Send SMS
    </button>
  </div>

  <div class="ap-tab-content active" id="comms-gmail">
    <div class="ap-card">
      <div class="ap-card-header">
        <span class="ap-card-title">Inbox Queue</span>
        <button class="ap-btn ap-btn-ghost ap-btn-sm" onclick="loadGmailQueue()">↻ Refresh</button>
      </div>
      <div class="ap-table-wrap">
        <table class="ap-table" id="gmail-queue-table">
          <thead>
            <tr><th>From</th><th>Subject</th><th>Received</th><th>Classification</th><th>Actions</th></tr>
          </thead>
          <tbody id="gmail-queue-tbody">
            <tr><td colspan="5" class="ap-table-empty">Loading Gmail queue…</td></tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>

  <div class="ap-tab-content" id="comms-dlq">
    <div class="ap-card">
      <div class="ap-card-header">
        <span class="ap-card-title">Dead-Letter Queue</span>
        <span class="ap-card-sub">Emails that failed processing</span>
        <button class="ap-btn ap-btn-ghost ap-btn-sm" onclick="loadDlq()">↻ Refresh</button>
      </div>
      <div class="ap-table-wrap">
        <table class="ap-table" id="dlq-table">
          <thead>
            <tr><th>Email ID</th><th>From</th><th>Subject</th><th>Error</th><th>Attempts</th><th>Actions</th></tr>
          </thead>
          <tbody id="dlq-tbody">
            <tr><td colspan="6" class="ap-table-empty">Loading DLQ…</td></tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>

  <div class="ap-tab-content" id="comms-clarifications">
    <div class="ap-card">
      <div class="ap-card-header">
        <span class="ap-card-title">Pending Clarifications</span>
        <span class="ap-card-sub">Bookings awaiting more info from customer</span>
        <button class="ap-btn ap-btn-ghost ap-btn-sm" onclick="loadClarifications()">↻ Refresh</button>
      </div>
      <div class="ap-table-wrap">
        <table class="ap-table" id="clarifications-table">
          <thead>
            <tr><th>Customer</th><th>Missing Fields</th><th>Sent</th><th>Attempts</th><th>Actions</th></tr>
          </thead>
          <tbody id="clarifications-tbody">
            <tr><td colspan="5" class="ap-table-empty">Loading clarifications…</td></tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>

  <div class="ap-tab-content" id="comms-waitlist">
    <div class="ap-card">
      <div class="ap-card-header">
        <span class="ap-card-title">Waitlist</span>
        <span class="ap-card-sub">Customers waiting for a slot</span>
        <button class="ap-btn ap-btn-ghost ap-btn-sm" onclick="loadWaitlist()">↻ Refresh</button>
      </div>
      <div class="ap-table-wrap">
        <table class="ap-table" id="waitlist-table">
          <thead>
            <tr><th>Customer</th><th>Requested Date</th><th>Service</th><th>Rims</th><th>Added</th><th>Actions</th></tr>
          </thead>
          <tbody id="waitlist-tbody">
            <tr><td colspan="6" class="ap-table-empty">Loading waitlist…</td></tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>

  <div class="ap-tab-content" id="comms-sms">
    <div class="ap-card">
      <div class="ap-card-header">
        <span class="ap-card-title">Send Manual SMS</span>
      </div>
      <div class="ap-form-group">
        <label class="ap-label" for="sms-to">To (phone number)</label>
        <input class="ap-input" id="sms-to" type="tel" placeholder="+61400000000">
      </div>
      <div class="ap-form-group">
        <label class="ap-label" for="sms-booking-id">Booking ID (optional)</label>
        <input class="ap-input" id="sms-booking-id" type="text" placeholder="Leave blank for standalone SMS">
      </div>
      <div class="ap-form-group">
        <label class="ap-label" for="sms-message">Message</label>
        <textarea class="ap-input ap-textarea" id="sms-message" rows="4" placeholder="Type your message…" oninput="updateSmsCount(this)"></textarea>
        <span class="ap-input-hint" id="sms-char-count">0 / 160 characters</span>
      </div>
      <div class="ap-form-actions">
        <button class="ap-btn ap-btn-primary" onclick="sendManualSms()">Send SMS</button>
        <button class="ap-btn ap-btn-ghost" onclick="clearSmsForm()">Clear</button>
      </div>
      <div class="ap-sms-history-header">
        <span class="ap-card-title" style="font-size:0.95rem">Recent Outbound SMS</span>
      </div>
      <div class="ap-table-wrap">
        <table class="ap-table" id="sms-log-table">
          <thead>
            <tr><th>To</th><th>Message Preview</th><th>Sent</th><th>Status</th></tr>
          </thead>
          <tbody id="sms-log-tbody">
            <tr><td colspan="4" class="ap-table-empty">Loading SMS log…</td></tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</section>

<!-- ═══════════════════════════════════════════════ CUSTOMERS ══ -->
<section class="ap-section" id="section-customers">
  <div class="ap-grid-customers">
    <div class="ap-card ap-customers-list-card">
      <div class="ap-card-header">
        <span class="ap-card-title">Customers</span>
        <span class="ap-card-sub" id="customers-count"></span>
      </div>
      <div class="ap-search-wrap ap-search-inline">
        <svg class="ap-search-icon" viewBox="0 0 24 24" fill="none" width="15" height="15">
          <circle cx="11" cy="11" r="8" stroke="currentColor" stroke-width="2"/>
          <line x1="21" y1="21" x2="16.65" y2="16.65" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
        </svg>
        <input class="ap-input ap-input-sm" id="customer-search" type="text" placeholder="Search name, email, phone…" oninput="searchCustomers(this.value)">
      </div>
      <div class="ap-table-wrap">
        <table class="ap-table ap-table-hover" id="customers-table">
          <thead>
            <tr>
              <th>Name</th>
              <th>Email</th>
              <th>Phone</th>
              <th>Bookings</th>
              <th>Last Booking</th>
            </tr>
          </thead>
          <tbody id="customers-tbody">
            <tr><td colspan="5" class="ap-table-empty">Loading customers…</td></tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Customer detail side panel replaced by modal popup -->
    <div id="customer-detail" style="display:none"></div>
  </div>
</section>

<!-- ═══════════════════════════════════════════════ SYSTEM ══ -->
<section class="ap-section" id="section-system">
  <div class="ap-grid-4">
    <div class="ap-card ap-health-card" id="health-gmail">
      <div class="ap-health-icon">
        <svg viewBox="0 0 24 24" fill="none" width="28" height="28"><path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z" stroke="currentColor" stroke-width="1.8"/><polyline points="22,6 12,13 2,6" stroke="currentColor" stroke-width="1.8"/></svg>
      </div>
      <div class="ap-health-label">Gmail API</div>
      <div class="ap-health-status" id="health-gmail-status">—</div>
    </div>
    <div class="ap-card ap-health-card" id="health-calendar">
      <div class="ap-health-icon">
        <svg viewBox="0 0 24 24" fill="none" width="28" height="28"><rect x="3" y="4" width="18" height="18" rx="2" stroke="currentColor" stroke-width="1.8"/><line x1="16" y1="2" x2="16" y2="6" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/><line x1="8" y1="2" x2="8" y2="6" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/><line x1="3" y1="10" x2="21" y2="10" stroke="currentColor" stroke-width="1.8"/></svg>
      </div>
      <div class="ap-health-label">Calendar API</div>
      <div class="ap-health-status" id="health-calendar-status">—</div>
    </div>
    <div class="ap-card ap-health-card" id="health-twilio">
      <div class="ap-health-icon">
        <svg viewBox="0 0 24 24" fill="none" width="28" height="28"><path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07A19.5 19.5 0 0 1 4.69 12 19.79 19.79 0 0 1 1.58 3.44 2 2 0 0 1 3.56 2h3a2 2 0 0 1 2 1.72c.127.96.361 1.903.7 2.81a2 2 0 0 1-.45 2.11L7.91 9.91a16 16 0 0 0 6 6l.9-.9a2 2 0 0 1 2.11-.45c.907.339 1.85.573 2.81.7A2 2 0 0 1 22 16.92z" stroke="currentColor" stroke-width="1.8"/></svg>
      </div>
      <div class="ap-health-label">Twilio SMS</div>
      <div class="ap-health-status" id="health-twilio-status">—</div>
    </div>
    <div class="ap-card ap-health-card" id="health-db">
      <div class="ap-health-icon">
        <svg viewBox="0 0 24 24" fill="none" width="28" height="28"><ellipse cx="12" cy="5" rx="9" ry="3" stroke="currentColor" stroke-width="1.8"/><path d="M21 12c0 1.66-4.03 3-9 3S3 13.66 3 12" stroke="currentColor" stroke-width="1.8"/><path d="M3 5v14c0 1.66 4.03 3 9 3s9-1.34 9-3V5" stroke="currentColor" stroke-width="1.8"/></svg>
      </div>
      <div class="ap-health-label">Database</div>
      <div class="ap-health-status" id="health-db-status">—</div>
    </div>
  </div>

  <div class="ap-grid-2">
    <div class="ap-card">
      <div class="ap-card-header">
        <span class="ap-card-title">Feature Flags</span>
        <button class="ap-btn ap-btn-ghost ap-btn-sm" onclick="loadFeatureFlags()">↻ Refresh</button>
      </div>
      <div id="system-flags"><div class="ap-text-muted">Loading flags…</div></div>
    </div>

    <div class="ap-card">
      <div class="ap-card-header">
        <span class="ap-card-title">Database Stats</span>
        <button class="ap-btn ap-btn-ghost ap-btn-sm" onclick="loadDbStats()">↻ Refresh</button>
      </div>
      <div class="ap-db-stats" id="db-stats-grid">
        <div class="ap-stat-row"><span class="ap-stat-label">Total Bookings</span><span class="ap-stat-val" id="dbstat-bookings">—</span></div>
        <div class="ap-stat-row"><span class="ap-stat-label">Customers</span><span class="ap-stat-val" id="dbstat-customers">—</span></div>
        <div class="ap-stat-row"><span class="ap-stat-label">DLQ Entries</span><span class="ap-stat-val" id="dbstat-dlq">—</span></div>
        <div class="ap-stat-row"><span class="ap-stat-label">Waitlist Entries</span><span class="ap-stat-val" id="dbstat-waitlist">—</span></div>
        <div class="ap-stat-row"><span class="ap-stat-label">DB File Size</span><span class="ap-stat-val" id="dbstat-size">—</span></div>
        <div class="ap-stat-row"><span class="ap-stat-label">Last Vacuumed</span><span class="ap-stat-val" id="dbstat-vacuum">—</span></div>
      </div>
      <div class="ap-form-actions" style="margin-top:1rem">
        <button class="ap-btn ap-btn-ghost ap-btn-sm" onclick="vacuumDb()">Vacuum DB</button>
        <button class="ap-btn ap-btn-ghost ap-btn-sm" onclick="exportDb()">Export Backup</button>
      </div>
    </div>
  </div>

  <div class="ap-card">
    <div class="ap-card-header">
      <span class="ap-card-title">Cancel Entire Day</span>
      <span class="ap-card-sub ap-danger-text">Use with caution — notifies all affected customers</span>
    </div>
    <div class="ap-form-inline">
      <div class="ap-form-group">
        <label class="ap-label" for="cancel-day-date">Date to cancel</label>
        <input class="ap-input" id="cancel-day-date" type="date">
      </div>
      <div class="ap-form-group">
        <label class="ap-label" for="cancel-day-reason">Reason (sent to customers)</label>
        <input class="ap-input" id="cancel-day-reason" type="text" placeholder="e.g. Equipment maintenance" style="min-width:280px">
      </div>
      <button class="ap-btn ap-btn-danger ap-btn-sm" onclick="cancelDayPrompt()">Cancel Day</button>
    </div>
  </div>

  <div class="ap-card">
    <div class="ap-card-header">
      <span class="ap-card-title">App State Viewer</span>
      <button class="ap-btn ap-btn-ghost ap-btn-sm" onclick="loadAppState()">↻ Refresh</button>
      <button class="ap-btn ap-btn-ghost ap-btn-sm" onclick="toggleAppStateRaw()">Toggle Raw</button>
    </div>
    <div class="ap-app-state" id="app-state-viewer">
      <pre id="app-state-raw" style="display:none"></pre>
      <div id="app-state-formatted">
        <div class="ap-table-empty">Click Refresh to load app state.</div>
      </div>
    </div>
  </div>
</section>

<!-- ═══════════════════════════════════════════════ ACTIVITY ══ -->
<section class="ap-section" id="section-activity">
  <div class="ap-card">
    <div class="ap-card-header">
      <span class="ap-card-title">Activity Feed</span>
      <div class="ap-activity-controls">
        <select class="ap-input ap-input-sm" id="activity-type-filter" onchange="setActivityFilter(this.value)">
          <option value="all">All Events</option>
          <option value="created">Created</option>
          <option value="confirmed">Confirmed</option>
          <option value="declined">Declined</option>
          <option value="rescheduled">Rescheduled</option>
          <option value="cancellation_requested">Cancellations</option>
          <option value="note">Notes</option>
          <option value="cancelled">Cancelled</option>
        </select>
        <label class="ap-toggle-label">
          <input type="checkbox" id="activity-autorefresh" onchange="toggleActivityAutoRefresh(this.checked)">
          <span>Auto-refresh</span>
        </label>
        <button class="ap-btn ap-btn-ghost ap-btn-sm" onclick="loadActivity()">↻ Refresh</button>
      </div>
    </div>

    <div class="ap-activity-feed" id="activity-feed">
      <div class="ap-activity-loading">Loading activity feed…</div>
    </div>

    <div class="ap-activity-footer">
      <button class="ap-btn ap-btn-ghost ap-btn-sm" id="activity-load-more" onclick="loadMoreActivity()" style="display:none">Load more</button>
    </div>
  </div>
</section>
"""

HTML_MODALS = """
<div class="ap-modal-overlay" id="ap-modal-overlay" onclick="closeModal()">
  <div class="ap-modal" id="ap-modal" onclick="event.stopPropagation()">
    <div class="ap-modal-header">
      <h3 class="ap-modal-title" id="ap-modal-title">Title</h3>
      <button class="ap-modal-close" id="ap-modal-close" onclick="closeModal()" aria-label="Close modal">&#10005;</button>
    </div>
    <div class="ap-modal-body" id="ap-modal-body"></div>
    <div class="ap-modal-footer" id="ap-modal-footer"></div>
  </div>
</div>

<div class="ap-toast-container" id="ap-toast-container"></div>

<div class="ap-notification-panel" id="ap-notification-panel" style="display:none">
  <div class="ap-notif-panel-header">
    <span class="ap-card-title">Notifications</span>
    <button class="ap-btn ap-btn-ghost ap-btn-xs" onclick="clearAllNotifications()">Clear all</button>
    <button class="ap-btn ap-btn-ghost ap-btn-xs" onclick="toggleNotifications()">✕</button>
  </div>
  <div class="ap-notif-list" id="ap-notif-list">
    <div class="ap-notif-empty">No new notifications.</div>
  </div>
</div>
"""
