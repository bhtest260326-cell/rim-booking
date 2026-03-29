JS_BOOKINGS = """
// ============================================================
// Admin Pro — Bookings Section JavaScript
// ============================================================

// ── Bookings State ───────────────────────────────────────────
const BOOKINGS_STATE = {
  page:    1,
  perPage: 25,
  status:  \'all\',
  dateFrom: \'\',
  dateTo:   \'\',
  search:   \'\',
  sortBy:   \'created_at\',
  sortDir:  \'desc\',
  selected: new Set(),
  total:    0,
};

// ── Status pill config ───────────────────────────────────────
const BOOKING_STATUS_PILLS = [
  { key: \'all\',           label: \'All\'       },
  { key: \'awaiting_owner\', label: \'Pending\'  },
  { key: \'confirmed\',     label: \'Confirmed\' },
  { key: \'declined\',      label: \'Declined\'  },
];

// ── Main init ────────────────────────────────────────────────
async function initBookings() {
  renderBookingsFilters();
  await loadBookings();
}

// ── Filter bar ───────────────────────────────────────────────
function renderBookingsFilters() {
  const container = document.getElementById(\'bookings-filters\');
  if (!container) return;

  // Build status pills HTML
  const pillsHtml = BOOKING_STATUS_PILLS.map(function(p) {
    const active = BOOKINGS_STATE.status === p.key ? \' ap-pill--active\' : \'\';
    return (
      \'<button class="ap-pill\' + active + \'" \' +
      \'onclick="setBookingStatus(\\'\' + p.key + \'\\')">\' +
      escapeHtml(p.label) +
      \'</button>\'
    );
  }).join(\'\');

  // Build per-page options
  const perPageOptions = [10, 25, 50, 100].map(function(n) {
    const sel = BOOKINGS_STATE.perPage === n ? \' selected\' : \'\';
    return \'<option value="\' + n + \'"\' + sel + \'>\' + n + \' / page</option>\';
  }).join(\'\');

  container.innerHTML = [
    \'<div class="ap-filter-row">\',
    \'  <div class="ap-filter-pills">\' + pillsHtml + \'</div>\',
    \'  <div class="ap-filter-controls">\',
    \'    <label class="ap-filter-label">From\',
    \'      <input type="date" class="ap-input ap-input--sm" id="bookings-date-from"\',
    \'        value="\' + escapeHtml(BOOKINGS_STATE.dateFrom) + \'"\',
    \'        onchange="onBookingDateFrom(this.value)">\',
    \'    </label>\',
    \'    <label class="ap-filter-label">To\',
    \'      <input type="date" class="ap-input ap-input--sm" id="bookings-date-to"\',
    \'        value="\' + escapeHtml(BOOKINGS_STATE.dateTo) + \'"\',
    \'        onchange="onBookingDateTo(this.value)">\',
    \'    </label>\',
    \'    <input type="search" class="ap-input ap-input--sm" id="bookings-search"\',
    \'      placeholder="Search name / email / suburb…"\',
    \'      value="\' + escapeHtml(BOOKINGS_STATE.search) + \'"\',
    \'      oninput="_bookingsSearchDebounced(this.value)">\',
    \'    <select class="ap-select ap-select--sm" onchange="onBookingPerPage(this.value)">\',
    \'      \' + perPageOptions,
    \'    </select>\',
    \'  </div>\',
    \'</div>\',
    \'<div class="ap-bulk-bar" id="bookings-bulk-bar" style="display:none;">\',
    \'  <span id="bookings-selected-count">0 selected</span>\',
    \'  <button class="ap-btn ap-btn-success ap-btn--sm" onclick="bulkConfirm()">&#10003; Confirm Selected</button>\',
    \'  <button class="ap-btn ap-btn-danger ap-btn--sm" onclick="bulkDecline()">&#10007; Decline Selected</button>\',
    \'  <button class="ap-btn ap-btn-ghost ap-btn--sm" onclick="clearBookingSelection()">Clear</button>\',
    \'</div>\',
  ].join(\'\');
}

// Debounced search handler (created once, referenced by oninput)
const _bookingsSearchDebounced = debounce(function(val) {
  BOOKINGS_STATE.search = val;
  BOOKINGS_STATE.page   = 1;
  loadBookings();
}, 350);

function setBookingStatus(status) {
  BOOKINGS_STATE.status = status;
  BOOKINGS_STATE.page   = 1;
  renderBookingsFilters();
  loadBookings();
}

function onBookingDateFrom(val) {
  BOOKINGS_STATE.dateFrom = val;
  BOOKINGS_STATE.page = 1;
  loadBookings();
}

function onBookingDateTo(val) {
  BOOKINGS_STATE.dateTo = val;
  BOOKINGS_STATE.page = 1;
  loadBookings();
}

function onBookingPerPage(val) {
  BOOKINGS_STATE.perPage = Number(val) || 25;
  BOOKINGS_STATE.page    = 1;
  loadBookings();
}

// ── Load and render bookings table ───────────────────────────
async function loadBookings() {
  const tableContainer = document.getElementById(\'bookings-table\');
  if (tableContainer) {
    tableContainer.innerHTML = \'<div class="ap-loading">Loading bookings…</div>\';
  }

  const params = new URLSearchParams();
  if (BOOKINGS_STATE.status && BOOKINGS_STATE.status !== \'all\') {
    params.set(\'status\', BOOKINGS_STATE.status);
  }
  if (BOOKINGS_STATE.dateFrom) params.set(\'date_from\', BOOKINGS_STATE.dateFrom);
  if (BOOKINGS_STATE.dateTo)   params.set(\'date_to\',   BOOKINGS_STATE.dateTo);
  if (BOOKINGS_STATE.search)   params.set(\'search\',    BOOKINGS_STATE.search);
  params.set(\'page\',     String(BOOKINGS_STATE.page));
  params.set(\'per_page\', String(BOOKINGS_STATE.perPage));
  params.set(\'sort_by\',  BOOKINGS_STATE.sortBy);
  params.set(\'sort_dir\', BOOKINGS_STATE.sortDir);

  try {
    const data = await apiFetch(\'/api/bookings?\' + params.toString());
    renderBookingsTable(data.bookings || []);
    renderPagination(data.total || 0, data.page || 1, data.pages || 1);
    BOOKINGS_STATE.total = data.total || 0;
  } catch (err) {
    if (tableContainer) {
      tableContainer.innerHTML = (
        \'<div class="ap-empty-state ap-empty-state--error">\' +
        \'<p>Failed to load bookings: \' + escapeHtml(err.message) + \'</p>\' +
        \'<button class="ap-btn ap-btn-ghost" onclick="loadBookings()">Retry</button>\' +
        \'</div>\'
      );
    }
  }
}

function renderBookingsTable(bookings) {
  const container = document.getElementById(\'bookings-table\');
  if (!container) return;

  if (!bookings || bookings.length === 0) {
    container.innerHTML = (
      \'<div class="ap-empty-state">\' +
      \'<div class="ap-empty-state__icon">&#128197;</div>\' +
      \'<p class="ap-empty-state__text">No bookings found.</p>\' +
      \'</div>\'
    );
    return;
  }

  function _sortTh(label, col) {
    var active  = BOOKINGS_STATE.sortBy === col;
    var dir     = active ? BOOKINGS_STATE.sortDir : \'\';
    var arrow   = dir === \'asc\' ? \' ↑\' : dir === \'desc\' ? \' ↓\' : \' ↕\';
    var cls     = \'ap-th ap-th--sort\' + (active ? \' ap-th--sort-active\' : \'\');
    return \'<th class="\' + cls + \'" onclick="sortBookings(\\'\' + col + \'\\')">\' + label + \'<span class="ap-sort-icon">\' + arrow + \'</span></th>\';
  }

  const headerCols = [
    \'<th class="ap-th ap-th--check"><input type="checkbox" title="Select all" onchange="toggleSelectAllBookings(this.checked)"></th>\',
    \'<th class="ap-th">#</th>\',
    \'<th class="ap-th">Customer</th>\',
    \'<th class="ap-th">Contact</th>\',
    \'<th class="ap-th">Service</th>\',
    _sortTh(\'Date / Time\', \'preferred_date\'),
    \'<th class="ap-th">Address</th>\',
    _sortTh(\'Status\', \'status\'),
    _sortTh(\'Created\', \'created_at\'),
    \'<th class="ap-th ap-th--actions">Actions</th>\',
  ].join(\'\');

  const rows = bookings.map(function(b) {
    const bd  = b.booking_data || {};
    const id  = b.id || \'\';
    const shortId = id.substring(0, 8) + \'…\';

    const name     = escapeHtml(bd.name || bd.customer_name || \'—\');
    const email    = escapeHtml(b.customer_email || bd.email || \'—\');
    const phone    = escapeHtml(bd.phone || bd.mobile || \'—\');
    const service  = escapeHtml(serviceLabel(bd.service_type || bd.service || \'\'));
    const rims     = bd.num_rims || bd.rims ? escapeHtml(String(bd.num_rims || bd.rims)) + \' rim(s)\' : \'\';
    const vehicle  = escapeHtml([bd.vehicle_make, bd.vehicle_model, bd.vehicle_year].filter(Boolean).join(\' \') || bd.vehicle || \'\');
    const serviceCell = [service, rims, vehicle].filter(Boolean).join(\'<br><small class="ap-muted">\') +
                        (rims || vehicle ? \'</small>\' : \'\');

    const dateStr  = b.preferred_date ? formatDate(b.preferred_date) : \'—\';
    const timeStr  = escapeHtml(bd.preferred_time || bd.time_slot || bd.time || \'\');
    const dateCell = timeStr ? dateStr + \'<br><small class="ap-muted">\' + timeStr + \'</small>\' : dateStr;

    const suburb   = escapeHtml(bd.suburb || bd.address_suburb || \'\');
    const postcode = escapeHtml(bd.postcode || bd.address_postcode || \'\');
    const addrCell = [suburb, postcode].filter(Boolean).join(\', \') || \'—\';

    const createdAt = b.created_at ? relativeTime(b.created_at) : \'—\';
    const isSelected = BOOKINGS_STATE.selected.has(id);

    // Action buttons
    const confirmBtn = (b.status === \'awaiting_owner\')
      ? \'<button class="ap-btn ap-btn-success ap-btn--xs" title="Confirm" onclick="confirmBooking(\\'\' + id + \'\\')">&#10003;</button>\'
      : \'\';
    const declineBtn = (b.status === \'awaiting_owner\')
      ? \'<button class="ap-btn ap-btn-danger ap-btn--xs" title="Decline" onclick="openDeclineModal(\\'\' + id + \'\\')">&#10007;</button>\'
      : \'\';
    const editBtn    = \'<button class="ap-btn ap-btn-ghost ap-btn--xs" title="Edit" onclick="openEditModal(\\'\' + id + \'\\')">&#9998;</button>\';
    const eventsBtn  = \'<button class="ap-btn ap-btn-ghost ap-btn--xs" title="Events / Audit" onclick="openBookingDetail(\\'\' + id + \'\\')">&#128203;</button>\';

    return [
      \'<tr class="ap-tr\' + (isSelected ? \' ap-tr--selected\' : \'\') + \'" data-id="\' + id + \'">\',
      \'  <td class="ap-td ap-td--check"><input type="checkbox" \' + (isSelected ? \'checked\' : \'\') + \' onchange="toggleBookingSelect(\\'\' + id + \'\\', this.checked)"></td>\',
      \'  <td class="ap-td ap-td--id"><span class="ap-monospace ap-link" onclick="openBookingDetail(\\'\' + id + \'\\')" title="\' + escapeHtml(id) + \'">\' + shortId + \'</span></td>\',
      \'  <td class="ap-td"><span class="ap-link" onclick="openBookingDetail(\\'\' + id + \'\\')">\' + name + \'</span></td>\',
      \'  <td class="ap-td ap-td--contact"><small>\' + email + \'<br>\' + phone + \'</small></td>\',
      \'  <td class="ap-td">\' + serviceCell + \'</td>\',
      \'  <td class="ap-td ap-td--date">\' + dateCell + \'</td>\',
      \'  <td class="ap-td ap-td--addr">\' + addrCell + \'</td>\',
      \'  <td class="ap-td">\' + statusBadge(b.status) + \'</td>\',
      \'  <td class="ap-td ap-td--created"><small>\' + createdAt + \'</small></td>\',
      \'  <td class="ap-td ap-td--actions">\' + confirmBtn + declineBtn + editBtn + eventsBtn + \'</td>\',
      \'</tr>\',
    ].join(\'\');
  }).join(\'\');

  container.innerHTML = (
    \'<table class="ap-table ap-table--bookings">\' +
    \'<thead><tr>\' + headerCols + \'</tr></thead>\' +
    \'<tbody>\' + rows + \'</tbody>\' +
    \'</table>\'
  );
}

// ── Pagination ───────────────────────────────────────────────
function renderPagination(total, page, pages) {
  const container = document.getElementById(\'bookings-pagination\');
  if (!container) return;

  if (pages <= 1) {
    container.innerHTML = (
      \'<span class="ap-pagination__info">\' + total + \' booking\' + (total === 1 ? \'\' : \'s\') + \'</span>\'
    );
    return;
  }

  const parts = [];

  // Summary
  const from = (page - 1) * BOOKINGS_STATE.perPage + 1;
  const to   = Math.min(page * BOOKINGS_STATE.perPage, total);
  parts.push(\'<span class="ap-pagination__info">\' + from + \'–\' + to + \' of \' + total + \'</span>\');

  // Prev button
  parts.push(
    \'<button class="ap-btn ap-btn-ghost ap-btn--sm ap-pagination__prev" \' +
    (page <= 1 ? \'disabled\' : \'onclick="goToPage(\' + (page - 1) + \')"\') +
    \'>&#8249; Prev</button>\'
  );

  // Page number buttons — show up to 7 around current page
  const windowSize = 2;
  const firstPage  = Math.max(1, page - windowSize);
  const lastPage   = Math.min(pages, page + windowSize);

  if (firstPage > 1) {
    parts.push(\'<button class="ap-btn ap-btn-ghost ap-btn--sm ap-pagination__page" onclick="goToPage(1)">1</button>\');
    if (firstPage > 2) {
      parts.push(\'<span class="ap-pagination__ellipsis">…</span>\');
    }
  }

  for (var p = firstPage; p <= lastPage; p++) {
    const active = p === page ? \' ap-btn--active\' : \'\';
    parts.push(
      \'<button class="ap-btn ap-btn-ghost ap-btn--sm ap-pagination__page\' + active + \'" \' +
      \'onclick="goToPage(\' + p + \')">\' + p + \'</button>\'
    );
  }

  if (lastPage < pages) {
    if (lastPage < pages - 1) {
      parts.push(\'<span class="ap-pagination__ellipsis">…</span>\');
    }
    parts.push(\'<button class="ap-btn ap-btn-ghost ap-btn--sm ap-pagination__page" onclick="goToPage(\' + pages + \')">\' + pages + \'</button>\');
  }

  // Next button
  parts.push(
    \'<button class="ap-btn ap-btn-ghost ap-btn--sm ap-pagination__next" \' +
    (page >= pages ? \'disabled\' : \'onclick="goToPage(\' + (page + 1) + \')"\') +
    \'>Next &#8250;</button>\'
  );

  container.innerHTML = \'<div class="ap-pagination">\' + parts.join(\'\') + \'</div>\';
}

function goToPage(p) {
  BOOKINGS_STATE.page = p;
  loadBookings();
  // Scroll table back to top
  const table = document.getElementById(\'bookings-table\');
  if (table) table.scrollIntoView({ behavior: \'smooth\', block: \'start\' });
}

// ── Selection helpers ────────────────────────────────────────
function toggleBookingSelect(id, checked) {
  if (checked) {
    BOOKINGS_STATE.selected.add(id);
  } else {
    BOOKINGS_STATE.selected.delete(id);
  }
  _updateBulkBar();
}

function toggleSelectAllBookings(checked) {
  const checkboxes = document.querySelectorAll(\'#bookings-table tbody input[type="checkbox"]\');
  checkboxes.forEach(function(cb) {
    const row = cb.closest(\'tr\');
    const id  = row ? row.dataset.id : null;
    if (!id) return;
    cb.checked = checked;
    if (checked) {
      BOOKINGS_STATE.selected.add(id);
      row.classList.add(\'ap-tr--selected\');
    } else {
      BOOKINGS_STATE.selected.delete(id);
      row.classList.remove(\'ap-tr--selected\');
    }
  });
  _updateBulkBar();
}

function clearBookingSelection() {
  BOOKINGS_STATE.selected.clear();
  _updateBulkBar();
  // Un-check all row checkboxes
  document.querySelectorAll(\'#bookings-table tbody input[type="checkbox"]\').forEach(function(cb) {
    cb.checked = false;
    const row = cb.closest(\'tr\');
    if (row) row.classList.remove(\'ap-tr--selected\');
  });
}

function _updateBulkBar() {
  const bar = document.getElementById(\'bookings-bulk-bar\');
  const countEl = document.getElementById(\'bookings-selected-count\');
  if (!bar) return;
  const n = BOOKINGS_STATE.selected.size;
  if (n > 0) {
    bar.style.display = \'flex\';
    if (countEl) countEl.textContent = n + \' selected\';
  } else {
    bar.style.display = \'none\';
  }
}

// ── Bulk actions ─────────────────────────────────────────────
async function bulkConfirm() {
  const ids = [...BOOKINGS_STATE.selected];
  if (!ids.length) return;
  if (!confirm(\'Confirm \' + ids.length + \' booking(s)?\')) return;
  try {
    const result = await apiFetch(\'/api/bookings/bulk\', {
      method: \'POST\',
      body: JSON.stringify({ action: \'confirm\', ids }),
    });
    const processed = result.processed || 0;
    const errors    = (result.errors || []).length;
    if (errors > 0) {
      showToast(processed + \' confirmed, \' + errors + \' failed.\', \'warning\');
    } else {
      showToast(processed + \' booking\' + (processed === 1 ? \'\' : \'s\') + \' confirmed.\', \'success\');
    }
  } catch (err) {
    showToast(\'Bulk confirm failed: \' + err.message, \'error\');
  }
  BOOKINGS_STATE.selected.clear();
  loadBookings();
}

async function bulkDecline() {
  const ids = [...BOOKINGS_STATE.selected];
  if (!ids.length) return;
  if (!confirm(\'Decline \' + ids.length + \' booking(s)?\')) return;
  try {
    const result = await apiFetch(\'/api/bookings/bulk\', {
      method: \'POST\',
      body: JSON.stringify({ action: \'decline\', ids }),
    });
    const processed = result.processed || 0;
    const errors    = (result.errors || []).length;
    if (errors > 0) {
      showToast(processed + \' declined, \' + errors + \' failed.\', \'warning\');
    } else {
      showToast(processed + \' booking\' + (processed === 1 ? \'\' : \'s\') + \' declined.\', \'info\');
    }
  } catch (err) {
    showToast(\'Bulk decline failed: \' + err.message, \'error\');
  }
  BOOKINGS_STATE.selected.clear();
  loadBookings();
}

// ── Booking detail modal ─────────────────────────────────────
async function openBookingDetail(bookingId) {
  showModal(\'Loading…\', \'<div class="ap-loading">Fetching booking details…</div>\', \'\');
  try {
    const data    = await apiFetch(\'/api/bookings/\' + bookingId);
    const booking = data.booking;
    const bd      = booking.booking_data || {};

    // Customer info
    const name    = escapeHtml(bd.name || bd.customer_name || \'—\');
    const email   = escapeHtml(booking.customer_email || bd.email || \'—\');
    const phone   = escapeHtml(bd.phone || bd.mobile || \'—\');

    // Service info
    const service = escapeHtml(serviceLabel(bd.service_type || bd.service || \'\'));
    const rims    = bd.num_rims || bd.rims ? escapeHtml(String(bd.num_rims || bd.rims)) + \' rim(s)\' : \'—\';
    const vehicle = escapeHtml(
      [bd.vehicle_make, bd.vehicle_model, bd.vehicle_year].filter(Boolean).join(\' \') ||
      bd.vehicle || \'—\'
    );

    // Schedule
    const dateStr  = booking.preferred_date ? formatDate(booking.preferred_date) : \'—\';
    const timeStr  = escapeHtml(bd.preferred_time || bd.time_slot || bd.time || \'—\');
    const suburb   = escapeHtml(bd.suburb || bd.address_suburb || \'\');
    const postcode = escapeHtml(bd.postcode || bd.address_postcode || \'\');
    const address  = [bd.address, suburb, postcode].filter(Boolean).map(escapeHtml).join(\', \') || \'—\';

    // Notes
    const notes = escapeHtml(bd.notes || booking.notes || \'\');

    // Build audit trail
    const events  = booking.events || [];
    const eventsHtml = events.length === 0
      ? \'<p class="ap-muted">No events recorded.</p>\'
      : events.map(function(ev) {
          const when   = ev.created_at ? formatDateTime(ev.created_at) : \'\';
          const actor  = escapeHtml(ev.actor || \'system\');
          const evType = escapeHtml((ev.event_type || \'\').replace(/_/g, \' \'));
          let detail   = \'\';
          if (ev.details && typeof ev.details === \'object\') {
            if (ev.details.text) {
              detail = \'<em>\' + escapeHtml(ev.details.text) + \'</em>\';
            } else if (ev.details.reason) {
              detail = \'Reason: <em>\' + escapeHtml(ev.details.reason) + \'</em>\';
            } else if (ev.details.updated_fields) {
              detail = \'Fields: \' + escapeHtml(ev.details.updated_fields.join(\', \'));
            }
          }
          return (
            \'<div class="ap-timeline-item">\' +
            \'  <div class="ap-timeline-dot"></div>\' +
            \'  <div class="ap-timeline-content">\' +
            \'    <div class="ap-timeline-header">\' +
            \'      <span class="ap-timeline-type">\' + evType + \'</span>\' +
            \'      <span class="ap-muted ap-timeline-actor">by \' + actor + \'</span>\' +
            \'    </div>\' +
            (detail ? \'<div class="ap-timeline-detail">\' + detail + \'</div>\' : \'\') +
            \'    <div class="ap-timeline-time ap-muted">\' + when + \'</div>\' +
            \'  </div>\' +
            \'</div>\'
          );
        }).join(\'\');

    const body = [
      \'<div class="ap-booking-detail">\',

      // ── Customer + Schedule (2 col) ──
      \'<div class="ap-bd-cols">\',
        \'<div>\',
          \'<div class="ap-detail-heading">Customer</div>\',
          \'<dl class="ap-dl">\',
            \'<dt>Name</dt>  <dd>\' + name  + \'</dd>\',
            \'<dt>Email</dt> <dd><a href="mailto:\' + email + \'" class="ap-link">\' + email + \'</a></dd>\',
            \'<dt>Phone</dt> <dd>\' + phone + \'</dd>\',
          \'</dl>\',
        \'</div>\',
        \'<div>\',
          \'<div class="ap-detail-heading">Schedule</div>\',
          \'<dl class="ap-dl">\',
            \'<dt>Date</dt>    <dd>\' + dateStr + \'</dd>\',
            \'<dt>Time</dt>    <dd>\' + timeStr + \'</dd>\',
            \'<dt>Address</dt><dd>\' + address + \'</dd>\',
          \'</dl>\',
        \'</div>\',
      \'</div>\',

      // ── Service ──
      \'<div class="ap-bd-sep"></div>\',
      \'<div class="ap-detail-heading">Service</div>\',
      \'<dl class="ap-dl">\',
        \'<dt>Type</dt>    <dd>\' + service + \'</dd>\',
        \'<dt>Rims</dt>   <dd>\' + rims    + \'</dd>\',
        \'<dt>Vehicle</dt><dd>\' + vehicle + \'</dd>\',
      \'</dl>\',

      // ── Notes ──
      \'<div class="ap-bd-sep"></div>\',
      \'<div class="ap-detail-heading">Notes</div>\',
      \'<div class="ap-notes-text">\' + (notes || \'<span style="opacity:.5">None</span>\') + \'</div>\',
      \'<button class="ap-btn ap-btn-ghost ap-btn-sm" style="margin-top:4px" onclick="addNote(\\'\' + bookingId + \'\\')">+ Add note</button>\',

      renderImageAssessment(bd.image_assessment),

      // ── Pending Change Notification ──
      (bd.moved_pending_notification ? [
        \'<div class="ap-bd-sep"></div>\',
        \'<div style="background:rgba(249,115,22,0.12);border:1px solid rgba(249,115,22,0.3);border-radius:8px;padding:12px 14px;">\',
        \'  <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px;">\',
        \'    <span style="font-size:16px">⚠️</span>\',
        \'    <strong style="color:#f97316">Booking Moved — Customer Not Yet Notified</strong>\',
        \'  </div>\',
        (bd.original_date ? \'  <div class="ap-text-muted" style="font-size:13px;margin-bottom:8px">Original: \' + escapeHtml(bd.original_date) + (bd.original_time ? \' at \' + escapeHtml(bd.original_time) : \'\') + \' → Now: \' + dateStr + \' at \' + timeStr + \'</div>\' : \'\'),
        \'  <button class="ap-notify-btn-lg" onclick="calNotifyCustomer(\\'\' + bookingId + \'\\')">📧 Send Change Notification</button>\',
        \'</div>\',
      ].join(\'\') : \'\'),

      // ── Activity ──
      \'<div class="ap-bd-sep"></div>\',
      \'<div class="ap-detail-heading">Activity</div>\',
      \'<div class="ap-timeline">\' + eventsHtml + \'</div>\',

      \'</div>\',
    ].join(\'\');

    const notifyBtn = bd.moved_pending_notification
      ? \'<button class="ap-notify-btn-lg" onclick="calNotifyCustomer(\\'\' + bookingId + \'\\')">📧 Notify Customer of Change</button>\'
      : \'\';

    const footer = (booking.status === \'awaiting_owner\')
      ? [
          \'<button class="ap-btn ap-btn-success" onclick="confirmBookingFromModal(\\'\' + bookingId + \'\\')">&#10003; Confirm</button>\',
          \'<button class="ap-btn ap-btn-danger" onclick="openDeclineModal(\\'\' + bookingId + \'\\')">&#10007; Decline</button>\',
          \'<button class="ap-btn ap-btn-ghost" onclick="openEditModal(\\'\' + bookingId + \'\\')">&#9998; Edit</button>\',
          notifyBtn,
        ].join(\'\')
      : \'<button class="ap-btn ap-btn-ghost" onclick="openEditModal(\\'\' + bookingId + \'\\')">&#9998; Edit</button>\' + notifyBtn;

    const shortId = bookingId.substring(0, 8).toUpperCase();
    showModal(
      \'#\' + shortId + \' <span style="margin-left:6px">\' + statusBadge(booking.status) + \'</span>\',
      body,
      footer
    );

  } catch (err) {
    showModal(\'Error\', \'<p class="ap-text--error">Failed to load booking: \' + escapeHtml(err.message) + \'</p>\', \'\');
  }
}

// ── Confirm booking (from table or modal) ────────────────────
async function confirmBooking(bookingId) {
  try {
    await apiFetch(\'/api/bookings/\' + bookingId + \'/confirm\', { method: \'POST\' });
    showToast(\'Booking confirmed.\', \'success\');
    loadBookings();
  } catch (err) {
    showToast(\'Could not confirm: \' + err.message, \'error\');
  }
}

async function confirmBookingFromModal(bookingId) {
  try {
    await apiFetch(\'/api/bookings/\' + bookingId + \'/confirm\', { method: \'POST\' });
    closeModal();
    showToast(\'Booking confirmed.\', \'success\');
    loadBookings();
  } catch (err) {
    showToast(\'Could not confirm: \' + err.message, \'error\');
  }
}

// ── Decline modal ────────────────────────────────────────────
function openDeclineModal(bookingId) {
  showModal(
    \'Decline Booking\',
    [
      \'<div class="ap-form-group">\',
      \'  <label class="ap-label">Reason (sent to customer)</label>\',
      \'  <textarea class="ap-textarea" id="decline-reason" rows="4"\',
      \'    placeholder="Optional — explain why you are unable to accept this booking…"></textarea>\',
      \'</div>\',
    ].join(\'\'),
    \'<button class="ap-btn ap-btn-danger" onclick="submitDecline(\\'\' + bookingId + \'\\')">Confirm Decline</button>\' +
    \'<button class="ap-btn ap-btn-ghost" onclick="closeModal()">Cancel</button>\'
  );
}

async function submitDecline(bookingId) {
  const reasonEl = document.getElementById(\'decline-reason\');
  const reason   = reasonEl ? reasonEl.value.trim() : \'\';
  try {
    await apiFetch(\'/api/bookings/\' + bookingId + \'/decline\', {
      method: \'POST\',
      body: JSON.stringify({ reason }),
    });
    closeModal();
    showToast(\'Booking declined.\', \'info\');
    loadBookings();
  } catch (err) {
    showToast(\'Could not decline: \' + err.message, \'error\');
  }
}

// ── Edit booking modal ───────────────────────────────────────
async function openEditModal(bookingId) {
  showModal(\'Loading…\', \'<div class="ap-loading">Fetching booking…</div>\', \'\');
  try {
    const data    = await apiFetch(\'/api/bookings/\' + bookingId);
    const booking = data.booking;
    const bd      = booking.booking_data || {};

    function field(label, id, value, type) {
      type = type || \'text\';
      return (
        \'<div class="ap-form-group">\' +
        \'  <label class="ap-label">\' + escapeHtml(label) + \'</label>\' +
        \'  <input type="\' + type + \'" class="ap-input" id="edit-\' + id + \'" value="\' + escapeHtml(value || \'\') + \'">\' +
        \'</div>\'
      );
    }

    function textarea(label, id, value) {
      return (
        \'<div class="ap-form-group">\' +
        \'  <label class="ap-label">\' + escapeHtml(label) + \'</label>\' +
        \'  <textarea class="ap-textarea" id="edit-\' + id + \'" rows="2">\' + escapeHtml(value || \'\') + \'</textarea>\' +
        \'</div>\'
      );
    }

    const body = [
      \'<div class="ap-edit-booking-form ap-grid-2">\',
      \'  <div>\',
      field(\'Name\',         \'name\',         bd.name || bd.customer_name || \'\'),
      field(\'Phone\',        \'phone\',        bd.phone || bd.mobile || \'\'),
      field(\'Email\',        \'email\',        booking.customer_email || bd.email || \'\'),
      field(\'Service Type\', \'service_type\', bd.service_type || bd.service || \'\'),
      field(\'No. of Rims\',  \'num_rims\',     bd.num_rims || bd.rims || \'\', \'number\'),
      \'  </div>\',
      \'  <div>\',
      field(\'Date\',          \'preferred_date\', booking.preferred_date || bd.preferred_date || \'\', \'date\'),
      field(\'Time\',          \'preferred_time\', bd.preferred_time || bd.time_slot || bd.time || \'\'),
      field(\'Address\',       \'address\',         bd.address || \'\'),
      field(\'Suburb\',        \'suburb\',           bd.suburb || bd.address_suburb || \'\'),
      field(\'Postcode\',      \'postcode\',         bd.postcode || bd.address_postcode || \'\'),
      \'  </div>\',
      \'</div>\',
      \'<div class="ap-grid-2">\',
      \'  <div>\',
      field(\'Vehicle Make\',  \'vehicle_make\',  bd.vehicle_make || \'\'),
      field(\'Vehicle Model\', \'vehicle_model\', bd.vehicle_model || \'\'),
      field(\'Vehicle Year\',  \'vehicle_year\',  bd.vehicle_year || \'\', \'number\'),
      \'  </div>\',
      \'  <div>\',
      textarea(\'Notes\', \'notes\', bd.notes || booking.notes || \'\'),
      \'  </div>\',
      \'</div>\',
    ].join(\'\');

    const footer = (
      \'<button class="ap-btn ap-btn-primary" onclick="submitEditBooking(\\'\' + bookingId + \'\\')">Save Changes</button>\' +
      \'<button class="ap-btn ap-btn-ghost" onclick="closeModal()">Cancel</button>\'
    );

    showModal(\'Edit Booking \' + bookingId.substring(0, 8) + \'…\', body, footer);

  } catch (err) {
    showModal(\'Error\', \'<p class="ap-text--error">Failed to load booking: \' + escapeHtml(err.message) + \'</p>\', \'\');
  }
}

async function submitEditBooking(bookingId) {
  function val(id) {
    const el = document.getElementById(\'edit-\' + id);
    return el ? el.value.trim() : \'\';
  }

  const payload = {
    name:           val(\'name\'),
    phone:          val(\'phone\'),
    email:          val(\'email\'),
    service_type:   val(\'service_type\'),
    num_rims:       val(\'num_rims\') ? Number(val(\'num_rims\')) : undefined,
    preferred_date: val(\'preferred_date\'),
    preferred_time: val(\'preferred_time\'),
    address:        val(\'address\'),
    suburb:         val(\'suburb\'),
    postcode:       val(\'postcode\'),
    vehicle_make:   val(\'vehicle_make\'),
    vehicle_model:  val(\'vehicle_model\'),
    vehicle_year:   val(\'vehicle_year\') ? Number(val(\'vehicle_year\')) : undefined,
    notes:          val(\'notes\'),
  };

  // Remove undefined / empty-string keys to avoid overwriting with blanks
  Object.keys(payload).forEach(function(k) {
    if (payload[k] === undefined || payload[k] === \'\') {
      delete payload[k];
    }
  });

  try {
    await apiFetch(\'/api/bookings/\' + bookingId + \'/edit\', {
      method: \'POST\',
      body: JSON.stringify(payload),
    });
    closeModal();
    showToast(\'Booking updated.\', \'success\');
    loadBookings();
  } catch (err) {
    showToast(\'Save failed: \' + err.message, \'error\');
  }
}

// ── HTML filter-bar compatibility shims ──────────────────────
// The static HTML filter tabs call filterBookings(status) with
// plain status names; map them to internal keys and delegate.
function filterBookings(status) {
  var statusMap = {
    \'all\':       \'all\',
    \'pending\':   \'awaiting_owner\',
    \'confirmed\': \'confirmed\',
    \'declined\':  \'declined\',
    \'completed\': \'completed\',
    \'cancelled\': \'cancelled\',
    \'waitlist\':  \'waitlist\',
  };
  var mapped = statusMap[status] !== undefined ? statusMap[status] : status;
  setBookingStatus(mapped);

  // Sync the active class on the static HTML pills
  var pills = document.querySelectorAll(\'#booking-status-pills .ap-pill\');
  pills.forEach(function(btn) {
    btn.classList.toggle(\'active\', btn.dataset.status === status);
  });
}

function filterBookingsByDate() {
  var from = document.getElementById(\'filter-date-from\');
  var to   = document.getElementById(\'filter-date-to\');
  BOOKINGS_STATE.dateFrom = from ? from.value : \'\';
  BOOKINGS_STATE.dateTo   = to   ? to.value   : \'\';
  BOOKINGS_STATE.page     = 1;
  loadBookings();
}

function searchBookings(val) {
  BOOKINGS_STATE.search = val || \'\';
  BOOKINGS_STATE.page   = 1;
  loadBookings();
}

function sortBookings(col) {
  if (BOOKINGS_STATE.sortBy === col) {
    BOOKINGS_STATE.sortDir = BOOKINGS_STATE.sortDir === \'asc\' ? \'desc\' : \'asc\';
  } else {
    BOOKINGS_STATE.sortBy  = col;
    BOOKINGS_STATE.sortDir = \'asc\';
  }
  BOOKINGS_STATE.page = 1;
  loadBookings();
}

function toggleSelectAll(checkbox) {
  toggleSelectAllBookings(checkbox.checked);
}

// ── Add note ─────────────────────────────────────────────────
async function addNote(bookingId) {
  const note = prompt(\'Add note to booking:\');
  if (!note || !note.trim()) return;
  try {
    await apiFetch(\'/api/bookings/\' + bookingId + \'/notes\', {
      method: \'POST\',
      body: JSON.stringify({ note: note.trim() }),
    });
    showToast(\'Note added.\', \'success\');
    // Refresh the detail modal if it is open
    openBookingDetail(bookingId);
  } catch (err) {
    showToast(\'Could not add note: \' + err.message, \'error\');
  }
}

// ── Image Assessment card ────────────────────────────────────
function renderImageAssessment(assessment) {
  if (!assessment || assessment.damage_level === 'not_visible') return '';

  const LEVEL_COLOUR = {
    minor:    { bg: '#f0fdf4', border: '#bbf7d0', text: '#166534' },
    moderate: { bg: '#fffbeb', border: '#fde68a', text: '#92400e' },
    severe:   { bg: '#fff1f2', border: '#fecaca', text: '#991b1b' },
  };
  const lvl   = (assessment.damage_level || '').toLowerCase();
  const theme = LEVEL_COLOUR[lvl] || { bg: '#f8fafc', border: '#e2e8f0', text: '#334155' };
  const label = escapeHtml((assessment.damage_level || '').replace(/_/g, ' '));
  const conf  = escapeHtml(assessment.confidence || '');
  const notes = escapeHtml(assessment.assessment_notes || '');
  const mins  = assessment.estimated_minutes ? escapeHtml(String(assessment.estimated_minutes)) + \' min\' : \'\';
  const price = (assessment.price_min && assessment.price_max)
    ? \'$\' + escapeHtml(String(assessment.price_min)) + \'–$\' + escapeHtml(String(assessment.price_max))
    : \'\';

  return [
    \'<h4 class="ap-detail-heading" style="margin-top:18px">📸 AI Image Assessment</h4>\',
    \'<div style="background:\' + theme.bg + \';border:1px solid \' + theme.border + \';\',
    \'border-radius:8px;padding:12px 14px;font-size:0.85rem;">\',
    \'  <div style="display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-bottom:6px;">\',
    \'    <span style="font-weight:700;color:\' + theme.text + \';text-transform:capitalize;">\' + label + \' damage</span>\',
    conf ? \'    <span style="color:var(--ap-text-muted);font-size:0.78rem;">(\' + conf + \' confidence)</span>\' : \'\',
    \'  </div>\',
    (price || mins) ? (
      \'  <div style="display:flex;gap:16px;margin-bottom:6px;">\' +
      (price ? \'<span><strong>Est. price:</strong> \' + price + \'</span>\' : \'\') +
      (mins  ? \'<span><strong>Est. time:</strong> \' + mins + \'</span>\' : \'\') +
      \'  </div>\'
    ) : \'\',
    notes ? \'  <div style="color:var(--ap-text-muted);">\' + notes + \'</div>\' : \'\',
    \'</div>\',
  ].join(\'\');
}

// ============================================================
// Waitlist Section
// ============================================================

const WAITLIST_STATE = {
  status: 'all',
  search: '',
};

async function initWaitlist() {
  await loadWaitlistEntries();
}

async function loadWaitlistEntries() {
  const container = document.getElementById('waitlist-container');
  if (!container) return;

  const params = new URLSearchParams();
  if (WAITLIST_STATE.status && WAITLIST_STATE.status !== 'all') {
    params.set('status', WAITLIST_STATE.status);
  }
  if (WAITLIST_STATE.search) params.set('search', WAITLIST_STATE.search);

  try {
    const data = await apiFetch('/api/waitlist?' + params.toString());
    const entries = data.data || [];
    renderWaitlistTable(entries);
  } catch (err) {
    container.innerHTML = '<div class="ap-alert ap-alert-error">Failed to load waitlist: ' + escapeHtml(err.message) + '</div>';
  }
}

function renderWaitlistTable(entries) {
  const container = document.getElementById('waitlist-container');
  if (!container) return;

  const STATUS_BADGE = {
    waiting: { bg: '#dbeafe', text: '#1e40af', label: 'Waiting' },
    offered: { bg: '#fef3c7', text: '#92400e', label: 'Offered' },
    booked:  { bg: '#d1fae5', text: '#065f46', label: 'Booked' },
    expired: { bg: '#f3f4f6', text: '#6b7280', label: 'Expired' },
  };

  const statusPills = ['all', 'waiting', 'offered', 'booked', 'expired'].map(function(s) {
    const active = WAITLIST_STATE.status === s ? ' ap-pill--active' : '';
    const label = s === 'all' ? 'All' : s.charAt(0).toUpperCase() + s.slice(1);
    return '<button class="ap-pill' + active + '" onclick="setWaitlistStatus(\\'' + s + '\\')">' + label + '</button>';
  }).join('');

  if (!entries.length) {
    container.innerHTML =
      '<div class="ap-filter-pills" style="margin-bottom:12px;">' + statusPills + '</div>' +
      '<div style="display:flex;justify-content:flex-end;margin-bottom:12px;">' +
        '<button class="ap-btn ap-btn-primary ap-btn-sm" onclick="openAddWaitlistModal()">+ Add to Waitlist</button>' +
      '</div>' +
      '<div class="ap-table-empty" style="padding:32px;text-align:center;">No waitlist entries found.</div>';
    return;
  }

  var rows = entries.map(function(e) {
    var badge = STATUS_BADGE[e.status] || STATUS_BADGE.waiting;
    var dates = Array.isArray(e.preferred_dates) ? e.preferred_dates.join(', ') : (e.preferred_dates || '—');
    var actions = '';
    if (e.status === 'waiting') {
      actions = '<button class="ap-btn ap-btn-primary ap-btn-xs" onclick="offerWaitlistSlot(' + e.id + ')">Offer Slot</button> ';
    }
    actions += '<button class="ap-btn ap-btn-ghost ap-btn-xs" onclick="editWaitlistEntry(' + e.id + ')">Edit</button> ';
    actions += '<button class="ap-btn ap-btn-ghost ap-btn-xs" style="color:var(--ap-danger);" onclick="deleteWaitlistEntry(' + e.id + ')">Remove</button>';

    return '<tr>' +
      '<td>' + escapeHtml(e.customer_name || '—') + '</td>' +
      '<td>' + escapeHtml(e.customer_email || '—') + '<br><span style="color:var(--ap-text-muted);font-size:0.8rem;">' + escapeHtml(e.customer_phone || '') + '</span></td>' +
      '<td>' + escapeHtml(e.service_type || '—') + '</td>' +
      '<td>' + escapeHtml(dates) + '</td>' +
      '<td>' + escapeHtml(e.preferred_suburb || '—') + '</td>' +
      '<td><span style="display:inline-block;padding:2px 8px;border-radius:10px;font-size:0.75rem;font-weight:600;background:' + badge.bg + ';color:' + badge.text + ';">' + badge.label + '</span></td>' +
      '<td>' + actions + '</td>' +
    '</tr>';
  }).join('');

  container.innerHTML =
    '<div class="ap-filter-pills" style="margin-bottom:12px;">' + statusPills + '</div>' +
    '<div style="display:flex;gap:12px;align-items:center;margin-bottom:12px;">' +
      '<input type="text" class="ap-input" placeholder="Search waitlist..." value="' + escapeHtml(WAITLIST_STATE.search) + '" oninput="searchWaitlist(this.value)" style="max-width:260px;">' +
      '<div style="flex:1;"></div>' +
      '<button class="ap-btn ap-btn-ghost ap-btn-sm" onclick="loadWaitlistEntries()">Refresh</button>' +
      '<button class="ap-btn ap-btn-primary ap-btn-sm" onclick="openAddWaitlistModal()">+ Add to Waitlist</button>' +
    '</div>' +
    '<table class="ap-table"><thead><tr>' +
      '<th>Name</th><th>Contact</th><th>Service</th><th>Preferred Dates</th><th>Suburb</th><th>Status</th><th>Actions</th>' +
    '</tr></thead><tbody>' + rows + '</tbody></table>';
}

function setWaitlistStatus(status) {
  WAITLIST_STATE.status = status;
  loadWaitlistEntries();
}

function searchWaitlist(val) {
  WAITLIST_STATE.search = val || '';
  loadWaitlistEntries();
}

async function offerWaitlistSlot(id) {
  var date = prompt('Enter the date to offer (YYYY-MM-DD), or leave blank for any preferred date:');
  if (date === null) return; // cancelled
  try {
    var body = {};
    if (date && date.trim()) body.date = date.trim();
    await apiFetch('/api/waitlist/' + id + '/offer', {
      method: 'POST',
      body: JSON.stringify(body),
    });
    showToast('Slot offered to customer.', 'success');
    loadWaitlistEntries();
  } catch (err) {
    showToast('Failed to offer slot: ' + err.message, 'error');
  }
}

async function deleteWaitlistEntry(id) {
  if (!confirm('Remove this customer from the waitlist?')) return;
  try {
    await apiFetch('/api/waitlist/' + id, { method: 'DELETE' });
    showToast('Removed from waitlist.', 'success');
    loadWaitlistEntries();
  } catch (err) {
    showToast('Failed to remove: ' + err.message, 'error');
  }
}

async function editWaitlistEntry(id) {
  // Fetch current entry data
  try {
    var data = await apiFetch('/api/waitlist?status=all');
    var entry = (data.data || []).find(function(e) { return e.id === id; });
    if (!entry) { showToast('Entry not found', 'error'); return; }
    openEditWaitlistModal(entry);
  } catch (err) {
    showToast('Failed to load entry: ' + err.message, 'error');
  }
}

function openAddWaitlistModal() {
  openEditWaitlistModal(null);
}

function openEditWaitlistModal(entry) {
  var isNew = !entry;
  var title = isNew ? 'Add to Waitlist' : 'Edit Waitlist Entry';
  var e = entry || {};
  var dates = Array.isArray(e.preferred_dates) ? e.preferred_dates.join(', ') : (e.preferred_dates || '');

  var html = [
    '<h3 style="margin:0 0 16px;">' + title + '</h3>',
    '<div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;">',
    '  <label class="ap-label">Name *<input class="ap-input" id="wl-name" value="' + escapeHtml(e.customer_name || '') + '"></label>',
    '  <label class="ap-label">Email<input class="ap-input" id="wl-email" value="' + escapeHtml(e.customer_email || '') + '"></label>',
    '  <label class="ap-label">Phone<input class="ap-input" id="wl-phone" value="' + escapeHtml(e.customer_phone || '') + '"></label>',
    '  <label class="ap-label">Service Type<input class="ap-input" id="wl-service" value="' + escapeHtml(e.service_type || '') + '"></label>',
    '  <label class="ap-label">Preferred Dates (comma-separated)<input class="ap-input" id="wl-dates" value="' + escapeHtml(dates) + '"></label>',
    '  <label class="ap-label">Suburb<input class="ap-input" id="wl-suburb" value="' + escapeHtml(e.preferred_suburb || '') + '"></label>',
    '  <label class="ap-label">Rim Count<input class="ap-input" type="number" id="wl-rims" value="' + (e.rim_count || 1) + '" min="1" max="10"></label>',
    '</div>',
    '<label class="ap-label" style="margin-top:10px;">Notes<textarea class="ap-input" id="wl-notes" rows="2">' + escapeHtml(e.notes || '') + '</textarea></label>',
    '<div style="display:flex;gap:8px;justify-content:flex-end;margin-top:16px;">',
    '  <button class="ap-btn ap-btn-ghost" onclick="closeModal()">Cancel</button>',
    '  <button class="ap-btn ap-btn-primary" onclick="saveWaitlistEntry(' + (isNew ? 'null' : e.id) + ')">Save</button>',
    '</div>',
  ].join('\\n');

  openModal(html);
}

async function saveWaitlistEntry(id) {
  var name = document.getElementById('wl-name').value.trim();
  if (!name) { showToast('Name is required.', 'error'); return; }

  var datesStr = document.getElementById('wl-dates').value.trim();
  var dates = datesStr ? datesStr.split(',').map(function(d) { return d.trim(); }).filter(Boolean) : [];

  var payload = {
    customer_name:    name,
    customer_email:   document.getElementById('wl-email').value.trim() || null,
    customer_phone:   document.getElementById('wl-phone').value.trim() || null,
    service_type:     document.getElementById('wl-service').value.trim() || null,
    preferred_dates:  dates.length ? dates : null,
    preferred_suburb: document.getElementById('wl-suburb').value.trim() || null,
    rim_count:        parseInt(document.getElementById('wl-rims').value, 10) || 1,
    notes:            document.getElementById('wl-notes').value.trim() || null,
  };

  try {
    if (id) {
      await apiFetch('/api/waitlist/' + id, { method: 'PUT', body: JSON.stringify(payload) });
      showToast('Waitlist entry updated.', 'success');
    } else {
      await apiFetch('/api/waitlist', { method: 'POST', body: JSON.stringify(payload) });
      showToast('Added to waitlist.', 'success');
    }
    closeModal();
    loadWaitlistEntries();
  } catch (err) {
    showToast('Save failed: ' + err.message, 'error');
  }
}

// ── Notify customer of booking change ────────────────────────
async function calNotifyCustomer(bookingId) {
  if (!confirm('Send change notification email to customer?')) return;
  try {
    await apiFetch('/api/bookings/' + bookingId + '/send-change-notification', { method: 'POST' });
    showToast('Change notification sent to customer.', 'success');
    // Remove from changed set if calendar tracks it
    if (typeof CAL_STATE !== 'undefined' && CAL_STATE.changedBookings) {
      CAL_STATE.changedBookings.delete(bookingId);
    }
    // Refresh the detail modal
    openBookingDetail(bookingId);
    // Refresh calendar if visible
    if (typeof initCalendar === 'function' && document.getElementById('section-calendar')?.style.display !== 'none') {
      initCalendar();
    }
  } catch (err) {
    showToast('Failed to send notification: ' + err.message, 'error');
  }
}
"""
