JS_CALENDAR = """
// ============================================================
// Admin Pro — Calendar Section JavaScript
// ============================================================

// ── Calendar State ───────────────────────────────────────────
const CAL_STATE = {
  year: new Date().getFullYear(),
  month: new Date().getMonth(), // 0-indexed
  view: 'month', // 'month' | 'week'
  selectedDate: null,
  bookingsByDate: {},
};

// ── Init ─────────────────────────────────────────────────────
async function initCalendar() {
  await loadCalendarData();
  renderCalendar();
}

async function loadCalendarData() {
  // Reset bookings — even if fetch fails the calendar still renders empty
  CAL_STATE.bookingsByDate = {};

  // Calculate date range for current month view
  const firstDay = new Date(CAL_STATE.year, CAL_STATE.month, 1);
  const lastDay  = new Date(CAL_STATE.year, CAL_STATE.month + 1, 0);
  const dateFrom = firstDay.toISOString().split('T')[0];
  const dateTo   = lastDay.toISOString().split('T')[0];

  try {
    // Load confirmed bookings
    const data = await apiFetch(
      `/v2/api/bookings?status=confirmed&date_from=${dateFrom}&date_to=${dateTo}&per_page=200`
    );

    // Group by preferred_date
    (data.bookings || []).forEach(b => {
      const d = (b.booking_data && b.booking_data.preferred_date) || b.preferred_date;
      if (d) {
        if (!CAL_STATE.bookingsByDate[d]) CAL_STATE.bookingsByDate[d] = [];
        CAL_STATE.bookingsByDate[d].push(b);
      }
    });
  } catch (err) {
    console.warn('Calendar: failed to load confirmed bookings:', err.message);
  }

  try {
    // Also load pending (awaiting_owner)
    const pendingData = await apiFetch(
      `/v2/api/bookings?status=awaiting_owner&date_from=${dateFrom}&date_to=${dateTo}&per_page=200`
    );
    (pendingData.bookings || []).forEach(b => {
      const d = (b.booking_data && b.booking_data.preferred_date) || b.preferred_date;
      if (d) {
        if (!CAL_STATE.bookingsByDate[d]) CAL_STATE.bookingsByDate[d] = [];
        CAL_STATE.bookingsByDate[d].push(b);
      }
    });
  } catch (err) {
    console.warn('Calendar: failed to load pending bookings:', err.message);
  }
}

// ── Calendar Header ──────────────────────────────────────────
function renderCalendarHeader() {
  const header = document.getElementById('ap-calendar-header');
  if (!header) return;
  const monthNames = [
    'January','February','March','April','May','June',
    'July','August','September','October','November','December'
  ];
  header.innerHTML = `
    <div class="ap-cal-header-inner">
      <button class="ap-btn ap-btn-ghost ap-btn-sm" onclick="calNavMonth(-1)">&#9664;</button>
      <h3 class="ap-cal-month-title">${monthNames[CAL_STATE.month]} ${CAL_STATE.year}</h3>
      <button class="ap-btn ap-btn-ghost ap-btn-sm" onclick="calNavMonth(1)">&#9654;</button>
      <button class="ap-btn ap-btn-ghost ap-btn-sm ap-ml-8" onclick="calGoToday()">Today</button>
    </div>
  `;
}

function calNavMonth(dir) {
  CAL_STATE.month += dir;
  if (CAL_STATE.month > 11) { CAL_STATE.month = 0; CAL_STATE.year++; }
  if (CAL_STATE.month < 0)  { CAL_STATE.month = 11; CAL_STATE.year--; }
  initCalendar();
}

// Alias used by HTML buttons
function calendarNav(dir) { calNavMonth(dir); }

function calGoToday() {
  CAL_STATE.year  = new Date().getFullYear();
  CAL_STATE.month = new Date().getMonth();
  initCalendar();
}

// Alias used by HTML
function goToToday() { calGoToday(); }

function setCalendarView(view) {
  CAL_STATE.view = view;
  // Update pill active state
  ['month', 'week'].forEach(v => {
    const btn = document.getElementById('cal-view-' + v);
    if (btn) btn.classList.toggle('active', v === view);
  });
  renderCalendar();
}

// ── Month Grid ───────────────────────────────────────────────
function renderCalendar() {
  const container = document.getElementById('ap-calendar-grid');
  if (!container) return;

  // Render the header (month/year + nav buttons)
  renderCalendarHeader();

  const today     = new Date().toISOString().split('T')[0];
  const firstDay  = new Date(CAL_STATE.year, CAL_STATE.month, 1);
  const startDow  = (firstDay.getDay() + 6) % 7; // Monday-first (0 = Mon)
  const daysInMonth = new Date(CAL_STATE.year, CAL_STATE.month + 1, 0).getDate();

  // Day-of-week header row
  let html = '<div class="ap-calendar-dow-row">';
  ['Mon','Tue','Wed','Thu','Fri','Sat','Sun'].forEach(d => {
    html += `<div class="ap-calendar-dow">${d}</div>`;
  });
  html += '</div>';

  // Grid cells
  html += '<div class="ap-calendar-grid-cells">';

  // Filler cells from previous month
  for (let i = 0; i < startDow; i++) {
    const prevDate = new Date(CAL_STATE.year, CAL_STATE.month, -startDow + i + 1);
    html += renderDayCell(prevDate, true);
  }

  // Current month cells
  for (let d = 1; d <= daysInMonth; d++) {
    const date = new Date(CAL_STATE.year, CAL_STATE.month, d);
    html += renderDayCell(date, false);
  }

  // Filler cells for next month to complete the last row
  const totalCells = startDow + daysInMonth;
  const remainder  = totalCells % 7;
  if (remainder !== 0) {
    const fillCount = 7 - remainder;
    for (let i = 1; i <= fillCount; i++) {
      const nextDate = new Date(CAL_STATE.year, CAL_STATE.month + 1, i);
      html += renderDayCell(nextDate, true);
    }
  }

  html += '</div>';
  container.innerHTML = html;

  // Re-render day detail panel if a date is already selected
  if (CAL_STATE.selectedDate) {
    renderDayDetail(CAL_STATE.selectedDate);
  }
}

function renderDayCell(date, otherMonth) {
  const dateStr  = date.toISOString().split('T')[0];
  const bookings = CAL_STATE.bookingsByDate[dateStr] || [];
  const today    = new Date().toISOString().split('T')[0];
  const isToday    = dateStr === today;
  const isSelected = dateStr === CAL_STATE.selectedDate;

  const confirmed = bookings.filter(b => b.status === 'confirmed').length;
  const pending   = bookings.filter(b => b.status === 'awaiting_owner').length;

  const classes = [
    'ap-calendar-day',
    otherMonth   ? 'other-month' : '',
    isToday      ? 'today'       : '',
    isSelected   ? 'selected'    : '',
    bookings.length > 0 ? 'has-jobs' : '',
  ].filter(Boolean).join(' ');

  return `
    <div class="${classes}" onclick="selectCalendarDay('${dateStr}')">
      <span class="ap-cal-day-num">${date.getDate()}</span>
      ${confirmed > 0 ? `<span class="ap-cal-dot confirmed" title="${confirmed} confirmed">${confirmed}</span>` : ''}
      ${pending   > 0 ? `<span class="ap-cal-dot pending"   title="${pending} pending">${pending}</span>`     : ''}
    </div>
  `;
}

// ── Day Selection & Detail Panel ─────────────────────────────
function selectCalendarDay(dateStr) {
  CAL_STATE.selectedDate = dateStr;
  renderCalendar();       // Re-render to show selected state
  renderDayDetail(dateStr);
}

function renderDayDetail(dateStr) {
  const panel = document.getElementById('ap-day-detail');
  if (!panel) return;

  const bookings = CAL_STATE.bookingsByDate[dateStr] || [];

  if (bookings.length === 0) {
    panel.innerHTML = `
      <div class="ap-text-muted">No jobs on ${formatDate(dateStr)}</div>
      <button class="ap-btn ap-btn-ghost ap-btn-sm ap-mt-16" onclick="showCancelDayForm('${dateStr}')">Cancel Day</button>
    `;
    return;
  }

  // Sort by preferred_time ascending
  bookings.sort((a, b) =>
    (a.booking_data?.preferred_time || '').localeCompare(b.booking_data?.preferred_time || '')
  );

  const jobWord = bookings.length > 1 ? 'jobs' : 'job';

  panel.innerHTML = `
    <h4 class="ap-day-detail-title">${formatDate(dateStr)} &mdash; ${bookings.length} ${jobWord}</h4>
    <button class="ap-btn ap-btn-danger ap-btn-sm ap-mt-8" onclick="showCancelDayForm('${dateStr}')">&#9888; Cancel Day</button>
    <div class="ap-mt-16">
      ${bookings.map(b => `
        <div class="ap-card ap-mt-8" style="padding:12px">
          <div class="ap-flex ap-flex-between" style="cursor:pointer" onclick="openBookingDetail('${b.id}')">
            <strong>${escapeHtml(b.booking_data?.customer_name || 'Unknown')}</strong>
            ${statusBadge(b.status)}
          </div>
          <div class="ap-text-muted" style="font-size:13px;margin-top:4px;cursor:pointer" onclick="openBookingDetail('${b.id}')">
            ${b.booking_data?.preferred_time || '?'} &middot;
            ${escapeHtml(b.booking_data?.address || b.booking_data?.suburb || '?')}
          </div>
          <div style="font-size:13px;cursor:pointer" onclick="openBookingDetail('${b.id}')">${serviceLabel(b.booking_data?.service_type)}</div>
          ${b.status === 'awaiting_owner' ? `
            <div style="margin-top:8px;display:flex;gap:6px">
              <button class="ap-btn ap-btn-success ap-btn-sm" onclick="calConfirmBooking('${b.id}','${dateStr}')">&#10003; Confirm</button>
              <button class="ap-btn ap-btn-danger ap-btn-sm" onclick="calDeclineBooking('${b.id}','${dateStr}')">&#10007; Decline</button>
            </div>
          ` : ''}
        </div>
      `).join('')}
    </div>
  `;
}

// ── Cancel Day Form ──────────────────────────────────────────
function showCancelDayForm(dateStr) {
  showModal(
    'Cancel Day',
    `
      <p>Cancel all bookings on <strong>${formatDate(dateStr)}</strong>?</p>
      <div class="ap-form-group ap-mt-16">
        <label>Reason</label>
        <textarea class="ap-textarea" id="cancel-day-reason" placeholder="Reason for cancellation..." rows="3"></textarea>
      </div>
    `,
    `<button class="ap-btn ap-btn-danger" onclick="submitCancelDay('${dateStr}')">Cancel All Jobs</button>`
  );
}

async function submitCancelDay(dateStr) {
  const reasonEl = document.getElementById('cancel-day-reason');
  const reason   = (reasonEl && reasonEl.value.trim()) ? reasonEl.value.trim() : 'No reason given';

  try {
    const data = await apiFetch('/v2/api/system/cancel-day', {
      method: 'POST',
      body: JSON.stringify({ date: dateStr, reason }),
    });
    closeModal();
    const cancelled = data.data?.cancelled ?? 0;
    showToast(`${cancelled} booking(s) cancelled`, 'info');
    // Clear the selected date and reload calendar
    CAL_STATE.selectedDate = null;
    initCalendar();
    // Clear the detail panel
    const panel = document.getElementById('ap-day-detail');
    if (panel) panel.innerHTML = '';
  } catch (err) {
    showToast('Failed to cancel day: ' + (err.message || 'Unknown error'), 'error');
  }
}

// ── Inline Confirm / Decline from Calendar Panel ────────────

async function calConfirmBooking(bookingId, dateStr) {
  try {
    await apiFetch('/v2/api/bookings/' + bookingId + '/confirm', { method: 'POST' });
    showToast('Booking confirmed.', 'success');
    await loadCalendarData();
    renderCalendar();
    renderDayDetail(dateStr);
  } catch (err) {
    showToast('Could not confirm: ' + (err.message || 'Unknown error'), 'error');
  }
}

async function calDeclineBooking(bookingId, dateStr) {
  if (!confirm('Decline this booking?')) return;
  try {
    await apiFetch('/v2/api/bookings/' + bookingId + '/decline', {
      method: 'POST',
      body: JSON.stringify({ reason: '' }),
    });
    showToast('Booking declined.', 'info');
    await loadCalendarData();
    renderCalendar();
    renderDayDetail(dateStr);
  } catch (err) {
    showToast('Could not decline: ' + (err.message || 'Unknown error'), 'error');
  }
}

// ── HTML for the Calendar Section ───────────────────────────
// Expected DOM structure injected by the section renderer:
//
//   <div id="ap-calendar-header"></div>
//   <div id="ap-calendar-grid"></div>
//   <div id="ap-day-detail"></div>
//
// The calendar section HTML string (rendered server-side or via
// renderSection()) must include those three anchor elements.
// initCalendar() is called automatically via SECTION_INIT.
"""
