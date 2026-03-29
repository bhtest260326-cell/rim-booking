JS_CALENDAR = """
// ============================================================
// Admin Pro — Calendar Section JavaScript (Week View + Drag-and-Drop)
// ============================================================

// ── Calendar State ───────────────────────────────────────────
const CAL_STATE = {
  year: new Date().getFullYear(),
  month: new Date().getMonth(),
  weekStart: null,           // Monday of current week (Date object)
  changedBookings: new Set(),// booking IDs moved but not yet notified
  bookings: [],              // flat array of all bookings from API
  bookingsByDate: {},        // { 'YYYY-MM-DD': [booking, ...] }
  dragData: null,
};

// ── Constants ────────────────────────────────────────────────
const CAL_SLOT_HEIGHT = 28;
const CAL_HOUR_START = 7;
const CAL_HOUR_END = 18;
const CAL_TOTAL_SLOTS = (CAL_HOUR_END - CAL_HOUR_START) * 2;
const CAL_BIZ_START = 8;
const CAL_BIZ_END = 17;
const CAL_DEFAULT_DURATION_SLOTS = 4;

// Rim duration table (mirrors maps_handler._RIM_DURATION / _DEFAULT_DURATION)
const CAL_RIM_DURATION = { 1: 120, 2: 180, 3: 240, 4: 300 };
const CAL_DEFAULT_DURATION_MIN = 120;
const CAL_TRAVEL_BUFFER_MIN = 30;

function _calGetJobDurationSlots(bd) {
  var service = (bd.service_type || '').toLowerCase();
  if (service === 'paint_touchup') return Math.ceil(60 / 30);
  var numRims = parseInt(bd.num_rims || bd.rims, 10);
  var minutes = CAL_DEFAULT_DURATION_MIN;
  if (numRims > 0) {
    if (CAL_RIM_DURATION[numRims]) {
      minutes = CAL_RIM_DURATION[numRims];
    } else if (numRims > 4) {
      minutes = 300 + (numRims - 4) * 60;
    }
  }
  // Add travel buffer
  minutes += CAL_TRAVEL_BUFFER_MIN;
  return Math.ceil(minutes / 30);
}

// ── Init ─────────────────────────────────────────────────────
async function initCalendar() {
  if (!CAL_STATE.weekStart) {
    CAL_STATE.weekStart = _calGetMonday(new Date());
  }
  await loadCalendarData();
  renderCalendar();
}

// ── Helpers ──────────────────────────────────────────────────
function _calGetMonday(d) {
  var date = new Date(d);
  var day = date.getDay();
  var diff = (day === 0 ? -6 : 1) - day;
  date.setDate(date.getDate() + diff);
  date.setHours(0, 0, 0, 0);
  return date;
}

function _calDateStr(d) {
  var y = d.getFullYear();
  var m = String(d.getMonth() + 1).padStart(2, '0');
  var dd = String(d.getDate()).padStart(2, '0');
  return y + '-' + m + '-' + dd;
}

function _calWeekDays() {
  var days = [];
  for (var i = 0; i < 5; i++) {
    var d = new Date(CAL_STATE.weekStart);
    d.setDate(d.getDate() + i);
    days.push(d);
  }
  return days;
}

// ── Data Loading ─────────────────────────────────────────────
async function loadCalendarData() {
  CAL_STATE.bookings = [];
  CAL_STATE.bookingsByDate = {};

  var days = _calWeekDays();
  var dateFrom = _calDateStr(days[0]);
  var dateTo = _calDateStr(days[4]);

  var fetches = [
    apiFetch('/v2/api/bookings?status=confirmed&date_from=' + dateFrom + '&date_to=' + dateTo + '&per_page=200'),
    apiFetch('/v2/api/bookings?status=awaiting_owner&date_from=' + dateFrom + '&date_to=' + dateTo + '&per_page=200'),
    apiFetch('/v2/api/bookings?status=awaiting_owner&per_page=200'),
  ];

  var results = await Promise.allSettled(fetches);

  results.forEach(function(result) {
    if (result.status === 'fulfilled') {
      (result.value.bookings || []).forEach(function(b) {
        CAL_STATE.bookings.push(b);
        var d = (b.booking_data && b.booking_data.preferred_date) || b.preferred_date;
        if (d) {
          if (!CAL_STATE.bookingsByDate[d]) CAL_STATE.bookingsByDate[d] = [];
          CAL_STATE.bookingsByDate[d].push(b);
        }
        if (b.booking_data && b.booking_data.moved_pending_notification) {
          CAL_STATE.changedBookings.add(b.id);
        }
      });
    }
  });

  // Third fetch: all pending bookings (for the panel, may include ones outside this week)
  if (results[2] && results[2].status === 'fulfilled') {
    (results[2].value.bookings || []).forEach(function(b) {
      // Add to flat list if not already there
      var exists = CAL_STATE.bookings.some(function(existing) { return existing.id === b.id; });
      if (!exists) {
        CAL_STATE.bookings.push(b);
      }
    });
  }

  // Render pending panel with awaiting_owner bookings from all dates
  _calRenderPendingPanel();
}

// ── Pending Confirmation Panel ─────────────────────────────
function _calRenderPendingPanel() {
  var listEl = document.getElementById('ap-pending-list');
  var countEl = document.getElementById('pending-count');
  if (!listEl) return;

  // Collect all awaiting_owner bookings across all dates
  var pending = [];
  CAL_STATE.bookings.forEach(function(b) {
    if (b.status === 'awaiting_owner') pending.push(b);
  });

  if (countEl) countEl.textContent = pending.length;

  if (pending.length === 0) {
    listEl.innerHTML = '<div class="ap-text-muted" style="padding:16px;text-align:center;font-size:13px">No bookings awaiting confirmation</div>';
    return;
  }

  // Sort by preferred_date then time
  pending.sort(function(a, b) {
    var dA = a.preferred_date || '';
    var dB = b.preferred_date || '';
    if (dA !== dB) return dA.localeCompare(dB);
    var tA = (a.booking_data && a.booking_data.preferred_time) || '';
    var tB = (b.booking_data && b.booking_data.preferred_time) || '';
    return tA.localeCompare(tB);
  });

  var html = '';
  pending.forEach(function(b) {
    var bd = b.booking_data || {};
    var name = escapeHtml(bd.customer_name || bd.name || 'Unknown');
    var date = b.preferred_date ? formatDate(b.preferred_date) : 'No date';
    var time = escapeHtml(bd.preferred_time || 'TBD');
    var service = serviceLabel(bd.service_type);
    var suburb = escapeHtml(bd.suburb || bd.address_suburb || '');

    html += '<div class="ap-pending-card" draggable="true" tabindex="0" ';
    html += 'role="button" aria-label="Pending booking: ' + name + ', ' + date + '" ';
    html += 'data-booking-id="' + b.id + '" ';
    html += 'ondragstart="calPendingDragStart(event, \\'' + b.id + '\\')" ';
    html += 'ondragend="calPendingDragEnd(event)" ';
    html += 'onclick="openBookingDetail(\\'' + b.id + '\\')">';
    html += '<div class="pending-name">' + name + '</div>';
    html += '<div class="pending-meta">';
    html += '<span>' + date + ' at ' + time + '</span>';
    html += '<span>' + service + (suburb ? ' · ' + suburb : '') + '</span>';
    html += '</div>';
    html += '<div class="pending-actions" onclick="event.stopPropagation()">';
    html += '<button class="ap-btn ap-btn-success ap-btn-sm" onclick="event.stopPropagation();calConfirmBooking(\\'' + b.id + '\\')">Confirm</button>';
    html += '<button class="ap-btn ap-btn-danger ap-btn-sm" onclick="event.stopPropagation();calDeclineBooking(\\'' + b.id + '\\')">Decline</button>';
    html += '</div>';
    html += '</div>';
  });

  listEl.innerHTML = html;
}

function calPendingDragStart(event, bookingId) {
  // Find the booking to get its current date/time
  var booking = null;
  CAL_STATE.bookings.forEach(function(b) {
    if (b.id === bookingId) booking = b;
  });
  var origDate = booking ? (booking.preferred_date || '') : '';
  var origTime = (booking && booking.booking_data) ? (booking.booking_data.preferred_time || '') : '';

  CAL_STATE.dragData = {
    bookingId: bookingId,
    originalDate: origDate,
    originalTime: origTime,
    fromPending: true,
  };
  event.dataTransfer.effectAllowed = 'move';
  event.dataTransfer.setData('text/plain', bookingId);

  var card = event.target.closest('.ap-pending-card');
  if (card) {
    setTimeout(function() { card.classList.add('dragging'); }, 0);
  }
}

function calPendingDragEnd(event) {
  CAL_STATE.dragData = null;
  document.querySelectorAll('.ap-pending-card.dragging').forEach(function(el) {
    el.classList.remove('dragging');
  });
  document.querySelectorAll('.cal-drop-indicator').forEach(function(el) {
    el.remove();
  });
  document.querySelectorAll('.cal-day-body').forEach(function(el) {
    el.classList.remove('cal-drag-over');
  });
}

// ── Navigation ───────────────────────────────────────────────
function calNavWeek(dir) {
  var d = new Date(CAL_STATE.weekStart);
  d.setDate(d.getDate() + dir * 7);
  CAL_STATE.weekStart = d;
  CAL_STATE.year = d.getFullYear();
  CAL_STATE.month = d.getMonth();
  initCalendar();
}

function calGoToday() {
  CAL_STATE.weekStart = _calGetMonday(new Date());
  var now = new Date();
  CAL_STATE.year = now.getFullYear();
  CAL_STATE.month = now.getMonth();
  initCalendar();
}

// Aliases for backward compatibility
function calendarNav(dir) { calNavWeek(dir); }
function goToToday() { calGoToday(); }

function setCalendarView(view) {
  ['month', 'week'].forEach(function(v) {
    var btn = document.getElementById('cal-view-' + v);
    if (btn) btn.classList.toggle('active', v === 'week');
  });
  renderCalendar();
}

// ── Time Helpers ─────────────────────────────────────────────
function _calParseTime(timeStr) {
  if (!timeStr) return null;
  var s = timeStr.trim().toUpperCase();

  var m24 = s.match(/^(\\d{1,2}):(\\d{2})$/);
  if (m24) {
    return { hour: parseInt(m24[1], 10), minute: parseInt(m24[2], 10) };
  }

  var m12 = s.match(/^(\\d{1,2}):(\\d{2})\\s*(AM|PM)$/);
  if (m12) {
    var h = parseInt(m12[1], 10);
    var min = parseInt(m12[2], 10);
    if (m12[3] === 'PM' && h !== 12) h += 12;
    if (m12[3] === 'AM' && h === 12) h = 0;
    return { hour: h, minute: min };
  }

  var mh = s.match(/^(\\d{1,2})\\s*(AM|PM)?$/);
  if (mh) {
    var hr = parseInt(mh[1], 10);
    if (mh[2] === 'PM' && hr !== 12) hr += 12;
    if (mh[2] === 'AM' && hr === 12) hr = 0;
    return { hour: hr, minute: 0 };
  }

  return null;
}

function _calTimeToSlotIndex(hour, minute) {
  return (hour - CAL_HOUR_START) * 2 + Math.floor(minute / 30);
}

// ── Overlap layout (Google Calendar style) ──────────────────
function _calComputeOverlapLayout(bookings) {
  // For each booking compute start/end in pixels, then assign columns
  var items = bookings.map(function(b) {
    var bd = b.booking_data || {};
    var timeStr = bd.preferred_time || '';
    var parsed = _calParseTime(timeStr);
    var hour = parsed ? parsed.hour : 9;
    var minute = parsed ? parsed.minute : 0;
    if (hour < CAL_HOUR_START) { hour = CAL_HOUR_START; minute = 0; }
    if (hour >= CAL_HOUR_END) { hour = CAL_HOUR_END - 1; minute = 0; }
    var slotIndex = _calTimeToSlotIndex(hour, minute);
    var topPx = slotIndex * CAL_SLOT_HEIGHT + (minute % 30) / 30 * CAL_SLOT_HEIGHT;
    var durationSlots = _calGetJobDurationSlots(bd);
    var heightPx = durationSlots * CAL_SLOT_HEIGHT;
    var maxTop = CAL_TOTAL_SLOTS * CAL_SLOT_HEIGHT - heightPx;
    if (topPx > maxTop) topPx = maxTop;
    return { booking: b, top: topPx, bottom: topPx + heightPx, col: 0, totalCols: 1 };
  });

  // Sort by start time, then by duration (longer first)
  items.sort(function(a, b) { return a.top - b.top || (b.bottom - b.top) - (a.bottom - a.top); });

  // Greedy column assignment
  // columns[c] = end position of last event placed in column c
  var columns = [];
  items.forEach(function(item) {
    var placed = false;
    for (var c = 0; c < columns.length; c++) {
      if (item.top >= columns[c]) {
        item.col = c;
        columns[c] = item.bottom;
        placed = true;
        break;
      }
    }
    if (!placed) {
      item.col = columns.length;
      columns.push(item.bottom);
    }
  });

  // Find overlapping groups and set totalCols for each group
  // Two items overlap if their vertical ranges intersect
  for (var i = 0; i < items.length; i++) {
    // Find all items that transitively overlap with this one
    var group = [i];
    var maxCol = items[i].col;
    var groupBottom = items[i].bottom;
    for (var j = i + 1; j < items.length; j++) {
      if (items[j].top < groupBottom) {
        group.push(j);
        if (items[j].col > maxCol) maxCol = items[j].col;
        if (items[j].bottom > groupBottom) groupBottom = items[j].bottom;
      }
    }
    var totalCols = maxCol + 1;
    group.forEach(function(idx) {
      if (totalCols > items[idx].totalCols) items[idx].totalCols = totalCols;
    });
  }

  // Return map of bookingId -> { col, totalCols }
  var layoutMap = {};
  items.forEach(function(item) {
    layoutMap[item.booking.id] = { col: item.col, totalCols: item.totalCols };
  });
  return layoutMap;
}

function _calSlotToTimeStr(slotIndex) {
  var totalMinutes = (CAL_HOUR_START * 60) + (slotIndex * 30);
  var h = Math.floor(totalMinutes / 60);
  var m = totalMinutes % 60;
  return String(h).padStart(2, '0') + ':' + String(m).padStart(2, '0');
}

function _calSlotToTime12(slotIndex) {
  var totalMinutes = (CAL_HOUR_START * 60) + (slotIndex * 30);
  var h = Math.floor(totalMinutes / 60);
  var m = totalMinutes % 60;
  return _calFormatTime12(h, m);
}

function _calFormatTime12(hour, minute) {
  var ampm = hour >= 12 ? 'PM' : 'AM';
  var h = hour % 12;
  if (h === 0) h = 12;
  return h + ':' + String(minute).padStart(2, '0') + ' ' + ampm;
}

// ── Render ───────────────────────────────────────────────────
function renderCalendar() {
  var container = document.getElementById('ap-calendar-grid');
  if (!container) return;

  var staticWeekdays = document.querySelector('.ap-calendar-weekdays');
  if (staticWeekdays) staticWeekdays.style.display = 'none';

  var detailPanel = document.getElementById('ap-day-detail');
  if (detailPanel) detailPanel.style.display = 'none';

  var days = _calWeekDays();
  var todayStr = _calDateStr(new Date());
  var gridHeight = CAL_TOTAL_SLOTS * CAL_SLOT_HEIGHT;

  var monthNamesShort = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
  var dayNames = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'];

  var mon = days[0];
  var fri = days[4];
  var headerLabel = dayNames[mon.getDay()] + ' ' + mon.getDate() + ' ' + monthNamesShort[mon.getMonth()] +
    ' \\u2013 ' +
    dayNames[fri.getDay()] + ' ' + fri.getDate() + ' ' + monthNamesShort[fri.getMonth()] +
    ' ' + fri.getFullYear();

  var html = '';

  // Inject scoped styles
  html += '<style>' + _calGetStyles() + '</style>';

  // ── Header row with navigation
  html += '<div class="cal-nav-header" role="toolbar" aria-label="Calendar navigation">';
  html += '<button class="cal-nav-btn" onclick="calNavWeek(-1)" title="Previous week" aria-label="Previous week"><span aria-hidden="true">&#9664;</span></button>';
  html += '<span class="cal-nav-label" aria-live="polite">' + headerLabel + '</span>';
  html += '<button class="cal-nav-btn" onclick="calNavWeek(1)" title="Next week" aria-label="Next week"><span aria-hidden="true">&#9654;</span></button>';
  html += '<button class="cal-nav-today-btn" onclick="calGoToday()" aria-label="Go to current week">Today</button>';
  html += '</div>';

  // Update the static title element if it exists
  var titleEl = document.getElementById('ap-calendar-title');
  if (titleEl) titleEl.textContent = headerLabel;

  // Ensure week pill is active
  var weekBtn = document.getElementById('cal-view-week');
  var monthBtn = document.getElementById('cal-view-month');
  if (weekBtn) weekBtn.classList.add('active');
  if (monthBtn) monthBtn.classList.remove('active');

  // ── Week grid wrapper
  html += '<div class="cal-week-wrapper">';

  // ── Time gutter (left column)
  html += '<div class="cal-time-gutter">';
  html += '<div class="cal-gutter-header"></div>';
  html += '<div class="cal-gutter-body" style="height:' + gridHeight + 'px">';
  for (var h = CAL_HOUR_START; h < CAL_HOUR_END; h++) {
    var topPx = (h - CAL_HOUR_START) * 2 * CAL_SLOT_HEIGHT;
    var dimmed = (h < CAL_BIZ_START || h >= CAL_BIZ_END) ? ' cal-time-dimmed' : '';
    html += '<div class="cal-time-label' + dimmed + '" style="top:' + topPx + 'px">';
    html += _calFormatTime12(h, 0);
    html += '</div>';
  }
  html += '</div></div>';

  // ── Day columns (Mon-Fri)
  days.forEach(function(day) {
    var dateStr = _calDateStr(day);
    var isToday = dateStr === todayStr;
    var label = dayNames[day.getDay()] + ' ' + day.getDate();

    html += '<div class="cal-day-col' + (isToday ? ' cal-day-today' : '') + '">';

    // Day header — clickable to open day detail
    html += '<div class="cal-day-header' + (isToday ? ' cal-header-today' : '') + '" ';
    html += 'onclick="selectCalendarDay(\\'' + dateStr + '\\')">';
    html += '<span class="cal-day-label">' + label + '</span>';
    html += '</div>';

    // Day body (time slots)
    html += '<div class="cal-day-body" style="height:' + gridHeight + 'px" ';
    html += 'data-date="' + dateStr + '" ';
    html += 'ondragover="calDragOver(event)" ondrop="calDrop(event, \\'' + dateStr + '\\')" ';
    html += 'ondragleave="calDragLeave(event)">';

    // Background slot rows with data attributes for drop targeting
    for (var s = 0; s < CAL_TOTAL_SLOTS; s++) {
      var slotTop = s * CAL_SLOT_HEIGHT;
      var slotHour = CAL_HOUR_START + Math.floor(s / 2);
      var isBiz = (slotHour >= CAL_BIZ_START && slotHour < CAL_BIZ_END);
      html += '<div class="cal-slot-bg' + (isBiz ? '' : ' cal-slot-dimmed') + '" ';
      html += 'style="top:' + slotTop + 'px;height:' + CAL_SLOT_HEIGHT + 'px" ';
      html += 'data-slot="' + s + '" data-date="' + dateStr + '" ';
      html += 'data-time="' + _calSlotToTimeStr(s) + '"></div>';
    }

    // Hour grid lines
    for (var gl = CAL_HOUR_START; gl <= CAL_HOUR_END; gl++) {
      var lineTop = (gl - CAL_HOUR_START) * 2 * CAL_SLOT_HEIGHT;
      html += '<div class="cal-hour-line" style="top:' + lineTop + 'px"></div>';
    }

    // Half-hour grid lines
    for (var gl2 = CAL_HOUR_START; gl2 < CAL_HOUR_END; gl2++) {
      var halfTop = ((gl2 - CAL_HOUR_START) * 2 + 1) * CAL_SLOT_HEIGHT;
      html += '<div class="cal-half-line" style="top:' + halfTop + 'px"></div>';
    }

    // Current time indicator
    if (isToday) {
      var now = new Date();
      var nowSlot = _calTimeToSlotIndex(now.getHours(), now.getMinutes());
      var nowMinInSlot = now.getMinutes() % 30;
      var nowTop = nowSlot * CAL_SLOT_HEIGHT + (nowMinInSlot / 30) * CAL_SLOT_HEIGHT;
      if (nowTop >= 0 && nowTop <= gridHeight) {
        html += '<div class="cal-now-line" style="top:' + nowTop + 'px"></div>';
      }
    }

    // Booking cards with overlap layout
    var bookings = CAL_STATE.bookingsByDate[dateStr] || [];
    bookings.sort(function(a, b) {
      var tA = (a.booking_data && a.booking_data.preferred_time) || '';
      var tB = (b.booking_data && b.booking_data.preferred_time) || '';
      return tA.localeCompare(tB);
    });

    var layoutMap = _calComputeOverlapLayout(bookings);
    bookings.forEach(function(b) {
      var layout = layoutMap[b.id] || { col: 0, totalCols: 1 };
      html += _calRenderBookingCard(b, dateStr, layout);
    });

    html += '</div>'; // .cal-day-body
    html += '</div>'; // .cal-day-col
  });

  html += '</div>'; // .cal-week-wrapper

  container.innerHTML = html;
}

// ── Booking Card Renderer ────────────────────────────────────
function _calRenderBookingCard(b, dateStr, layout) {
  layout = layout || { col: 0, totalCols: 1 };
  var bd = b.booking_data || {};
  var timeStr = bd.preferred_time || '';
  var parsed = _calParseTime(timeStr);

  var hour = parsed ? parsed.hour : 9;
  var minute = parsed ? parsed.minute : 0;

  if (hour < CAL_HOUR_START) { hour = CAL_HOUR_START; minute = 0; }
  if (hour >= CAL_HOUR_END) { hour = CAL_HOUR_END - 1; minute = 0; }

  var slotIndex = _calTimeToSlotIndex(hour, minute);
  var topPx = slotIndex * CAL_SLOT_HEIGHT + (minute % 30) / 30 * CAL_SLOT_HEIGHT;
  var durationSlots = _calGetJobDurationSlots(bd);
  var heightPx = durationSlots * CAL_SLOT_HEIGHT;

  var maxTop = CAL_TOTAL_SLOTS * CAL_SLOT_HEIGHT - heightPx;
  if (topPx > maxTop) topPx = maxTop;

  // Overlap column positioning
  var colWidth = 100 / layout.totalCols;
  var leftPct = layout.col * colWidth;

  var isConfirmed = b.status === 'confirmed';
  var isPending = b.status === 'awaiting_owner';
  var colorClass = isConfirmed ? 'cal-card-confirmed' : 'cal-card-pending';

  var name = escapeHtml(bd.customer_name || bd.name || 'Unknown');
  var service = serviceLabel(bd.service_type);
  var displayTime = parsed ? _calFormatTime12(hour, minute) : (timeStr || 'TBD');
  var isChanged = CAL_STATE.changedBookings.has(b.id);
  var badge = statusBadge(b.status);

  var html = '';
  html += '<div class="cal-booking-card ' + colorClass + (isChanged ? ' cal-card-changed' : '') + '" ';
  html += 'style="top:' + topPx + 'px;height:' + heightPx + 'px;left:calc(' + leftPct + '% + 1px);width:calc(' + colWidth + '% - 2px)" ';
  html += 'draggable="true" tabindex="0" ';
  html += 'role="button" aria-label="' + name + ' at ' + displayTime + ', ' + service + '" ';
  html += 'data-booking-id="' + b.id + '" ';
  html += 'data-date="' + dateStr + '" ';
  html += 'data-time="' + escapeHtml(timeStr) + '" ';
  html += 'ondragstart="calDragStart(event, \\'' + b.id + '\\', \\'' + dateStr + '\\', \\'' + escapeHtml(timeStr) + '\\')" ';
  html += 'ondragend="calDragEnd(event)" ';
  html += 'onclick="openBookingDetail(\\'' + b.id + '\\')">';

  var rims = bd.num_rims || bd.rims;
  var rimsStr = rims ? ' · ' + rims + ' rim' + (parseInt(rims, 10) !== 1 ? 's' : '') : '';
  html += '<div class="cal-card-time">' + displayTime + ' ' + badge + '</div>';
  html += '<div class="cal-card-name">' + name + '</div>';
  html += '<div class="cal-card-info">' + service + rimsStr + '</div>';

  // Inline confirm/decline for pending bookings
  if (isPending) {
    html += '<div class="cal-card-actions" onclick="event.stopPropagation()">';
    html += '<button class="cal-action-btn cal-btn-confirm" onclick="event.stopPropagation();calConfirmBooking(\\'' + b.id + '\\',\\'' + dateStr + '\\')">Confirm</button>';
    html += '<button class="cal-action-btn cal-btn-decline" onclick="event.stopPropagation();calDeclineBooking(\\'' + b.id + '\\',\\'' + dateStr + '\\')">Decline</button>';
    html += '</div>';
  }

  // Notify button for changed bookings
  if (isChanged) {
    html += '<div class="cal-card-actions" onclick="event.stopPropagation()">';
    html += '<button class="cal-action-btn cal-btn-notify cal-pulse-notify" onclick="event.stopPropagation();calNotifyCustomer(\\'' + b.id + '\\')">\\ud83d\\udce7 Notify</button>';
    html += '</div>';
  }

  html += '</div>';
  return html;
}

// ── Drag and Drop ────────────────────────────────────────────
function calDragStart(event, bookingId, dateStr, timeStr) {
  // Look up booking status
  var booking = CAL_STATE.bookings.find(function(b) { return b.id === bookingId; });
  var status = booking ? booking.status : '';
  CAL_STATE.dragData = {
    bookingId: bookingId,
    originalDate: dateStr,
    originalTime: timeStr,
    status: status,
  };
  event.dataTransfer.effectAllowed = 'move';
  event.dataTransfer.setData('text/plain', bookingId);

  var card = event.target.closest('.cal-booking-card');
  if (card) {
    setTimeout(function() { card.classList.add('cal-card-dragging'); }, 0);
  }
}

function calDragEnd(event) {
  CAL_STATE.dragData = null;
  // Remove dragging class from all cards (calendar + pending panel)
  document.querySelectorAll('.cal-card-dragging').forEach(function(el) {
    el.classList.remove('cal-card-dragging');
  });
  document.querySelectorAll('.ap-pending-card.dragging').forEach(function(el) {
    el.classList.remove('dragging');
  });
  document.querySelectorAll('.cal-drop-indicator').forEach(function(el) {
    el.remove();
  });
  document.querySelectorAll('.cal-day-body').forEach(function(el) {
    el.classList.remove('cal-drag-over');
  });
  // Remove pending panel drop highlight
  var pendingList = document.getElementById('ap-pending-list');
  if (pendingList) pendingList.classList.remove('pending-drag-over');
}

// ── Pending Panel Drop Target ────────────────────────────────
// Allows dragging unconfirmed bookings from the calendar back to
// the pending panel (clears their date/time).
function calPendingPanelDragOver(event) {
  if (!CAL_STATE.dragData) return;
  // Only accept pending (awaiting_owner) bookings
  if (CAL_STATE.dragData.status !== 'awaiting_owner') return;
  event.preventDefault();
  event.dataTransfer.dropEffect = 'move';
  var list = document.getElementById('ap-pending-list');
  if (list) list.classList.add('pending-drag-over');
}

function calPendingPanelDragLeave(event) {
  var list = document.getElementById('ap-pending-list');
  if (!list) return;
  var related = event.relatedTarget;
  if (related && list.contains(related)) return;
  list.classList.remove('pending-drag-over');
}

async function calPendingPanelDrop(event) {
  event.preventDefault();
  var list = document.getElementById('ap-pending-list');
  if (list) list.classList.remove('pending-drag-over');

  if (!CAL_STATE.dragData) return;
  if (CAL_STATE.dragData.status !== 'awaiting_owner') {
    showToast('Only unconfirmed bookings can be moved back to pending.', 'warning');
    CAL_STATE.dragData = null;
    return;
  }

  var bookingId = CAL_STATE.dragData.bookingId;
  CAL_STATE.dragData = null;

  // Clear the date and time to "unschedule" the booking
  try {
    await apiFetch('/v2/api/bookings/' + bookingId + '/edit', {
      method: 'POST',
      body: JSON.stringify({ preferred_date: '', preferred_time: '' }),
    });
    showToast('Booking moved back to pending.', 'info');
    await loadCalendarData();
    renderCalendar();
  } catch (err) {
    showToast('Failed to unschedule booking: ' + (err.message || 'Unknown error'), 'error');
  }
}

function calDragOver(event) {
  event.preventDefault();
  event.dataTransfer.dropEffect = 'move';

  var body = event.target.closest('.cal-day-body');
  if (!body) return;
  body.classList.add('cal-drag-over');

  var rect = body.getBoundingClientRect();
  var y = event.clientY - rect.top;
  var slotIndex = Math.max(0, Math.min(CAL_TOTAL_SLOTS - 1, Math.floor(y / CAL_SLOT_HEIGHT)));
  var snappedTop = slotIndex * CAL_SLOT_HEIGHT;

  var indicator = body.querySelector('.cal-drop-indicator');
  if (!indicator) {
    indicator = document.createElement('div');
    indicator.className = 'cal-drop-indicator';
    body.appendChild(indicator);
  }
  indicator.style.top = snappedTop + 'px';
  indicator.style.height = (CAL_DEFAULT_DURATION_SLOTS * CAL_SLOT_HEIGHT) + 'px';
  indicator.textContent = _calSlotToTime12(slotIndex);
}

function calDragLeave(event) {
  var body = event.target.closest('.cal-day-body');
  if (!body) return;

  var related = event.relatedTarget;
  if (related && body.contains(related)) return;

  body.classList.remove('cal-drag-over');
  var indicator = body.querySelector('.cal-drop-indicator');
  if (indicator) indicator.remove();
}

async function calDrop(event, targetDate) {
  event.preventDefault();

  var body = event.target.closest('.cal-day-body');
  if (!body) return;

  body.classList.remove('cal-drag-over');
  var indicator = body.querySelector('.cal-drop-indicator');
  if (indicator) indicator.remove();

  if (!CAL_STATE.dragData) return;

  var bookingId = CAL_STATE.dragData.bookingId;
  var origDate = CAL_STATE.dragData.originalDate;
  var origTime = CAL_STATE.dragData.originalTime;

  var rect = body.getBoundingClientRect();
  var y = event.clientY - rect.top;
  var slotIndex = Math.max(0, Math.min(CAL_TOTAL_SLOTS - 1, Math.floor(y / CAL_SLOT_HEIGHT)));
  var newTime = _calSlotToTimeStr(slotIndex);

  if (targetDate === origDate && newTime === origTime) {
    CAL_STATE.dragData = null;
    return;
  }

  CAL_STATE.dragData = null;

  await calMoveBooking(bookingId, targetDate, newTime, origDate, origTime);
}

async function calMoveBooking(bookingId, newDate, newTime, oldDate, oldTime) {
  var payload = { preferred_date: newDate, preferred_time: newTime };

  try {
    await apiFetch('/v2/api/bookings/' + bookingId + '/edit', {
      method: 'POST',
      body: JSON.stringify(payload),
    });

    showToast('Booking moved to ' + newDate + ' at ' + newTime, 'success');

    // Mark moved server-side with original date/time for notification
    try {
      await apiFetch('/v2/api/bookings/' + bookingId + '/mark-moved', {
        method: 'POST',
        body: JSON.stringify({ original_date: oldDate || '', original_time: oldTime || '' }),
      });
    } catch (markErr) {
      console.warn('mark-moved endpoint not available:', markErr.message);
    }

    CAL_STATE.changedBookings.add(bookingId);

    await loadCalendarData();
    renderCalendar();
  } catch (err) {
    showToast('Failed to move booking: ' + (err.message || 'Unknown error'), 'error');
  }
}

// ── Notify Customer of Change ────────────────────────────────
async function calNotifyCustomer(bookingId) {
  try {
    await apiFetch('/v2/api/bookings/' + bookingId + '/send-change-notification', {
      method: 'POST',
    });
    showToast('Customer notified of schedule change.', 'success');
    CAL_STATE.changedBookings.delete(bookingId);
    renderCalendar();
  } catch (err) {
    showToast('Failed to notify customer: ' + (err.message || 'Unknown error'), 'error');
  }
}

// Alias
async function calSendChangeNotification(bookingId) {
  return calNotifyCustomer(bookingId);
}

// ── Day Detail Panel ─────────────────────────────────────────
function selectCalendarDay(dateStr) {
  renderDayDetail(dateStr);
}

function renderDayDetail(dateStr) {
  var panel = document.getElementById('ap-day-detail');
  if (!panel) return;

  panel.style.display = 'block';

  var bookings = CAL_STATE.bookingsByDate[dateStr] || [];
  var dayNames = ['Sunday','Monday','Tuesday','Wednesday','Thursday','Friday','Saturday'];
  var d = new Date(dateStr + 'T00:00:00');
  var dayLabel = dayNames[d.getDay()] + ' ' + formatDate(dateStr);

  var headerEl = panel.querySelector('.ap-day-detail-header');
  if (headerEl) {
    headerEl.innerHTML =
      '<h3>' + dayLabel + '</h3>' +
      '<span class="ap-badge">' + bookings.length + ' booking' + (bookings.length !== 1 ? 's' : '') + '</span>';
  }

  var actionsEl = document.getElementById('day-detail-actions');
  if (actionsEl) {
    actionsEl.style.display = 'block';
    actionsEl.innerHTML =
      '<button class="ap-btn ap-btn-sm ap-btn-danger" onclick="showCancelDayForm(\\'' + dateStr + '\\')">Cancel Day</button>';
  }

  var bodyHtml = '';
  if (bookings.length === 0) {
    bodyHtml = '<p class="ap-text-muted">No bookings for this day.</p>';
  } else {
    bookings.sort(function(a, b) {
      var tA = (a.booking_data && a.booking_data.preferred_time) || '';
      var tB = (b.booking_data && b.booking_data.preferred_time) || '';
      return tA.localeCompare(tB);
    });

    bodyHtml = '<div class="ap-day-booking-list">';
    bookings.forEach(function(b) {
      var bd = b.booking_data || {};
      var name = escapeHtml(bd.customer_name || bd.name || 'Unknown');
      var timeStr = bd.preferred_time || 'TBD';
      var service = serviceLabel(bd.service_type);
      var badge = statusBadge(b.status);
      var isChanged = CAL_STATE.changedBookings.has(b.id);

      bodyHtml += '<div class="ap-day-booking-item" onclick="openBookingDetail(\\'' + b.id + '\\')" style="cursor:pointer">';
      bodyHtml += '<div><strong>' + escapeHtml(timeStr) + '</strong> ' + badge + '</div>';
      bodyHtml += '<div>' + name + ' &mdash; ' + service + '</div>';
      if (isChanged) {
        bodyHtml += '<button class="cal-action-btn cal-btn-notify cal-pulse-notify" style="margin-top:4px" ';
        bodyHtml += 'onclick="event.stopPropagation();calNotifyCustomer(\\'' + b.id + '\\')">\\ud83d\\udce7 Notify</button>';
      }
      bodyHtml += '</div>';
    });
    bodyHtml += '</div>';
  }

  var bodyEl = panel.querySelector('.ap-day-detail-body');
  if (!bodyEl) {
    bodyEl = document.createElement('div');
    bodyEl.className = 'ap-day-detail-body';
    panel.appendChild(bodyEl);
  }
  bodyEl.innerHTML = bodyHtml;
}

// ── Cancel Day Form ──────────────────────────────────────────
function showCancelDayForm(dateStr) {
  showModal(
    'Cancel Day',
    '<p>Cancel all bookings on <strong>' + formatDate(dateStr) + '</strong>?</p>' +
    '<div class="ap-form-group ap-mt-16">' +
      '<label>Reason</label>' +
      '<textarea class="ap-textarea" id="cal-cancel-reason" placeholder="Reason for cancellation..." rows="3"></textarea>' +
    '</div>',
    '<button class="ap-btn ap-btn-danger" onclick="submitCancelDay(\\'' + dateStr + '\\')">Cancel All Jobs</button>'
  );
}

async function submitCancelDay(dateStr) {
  var reasonEl = document.getElementById('cal-cancel-reason');
  var reason = (reasonEl && reasonEl.value.trim()) ? reasonEl.value.trim() : 'No reason given';

  try {
    var data = await apiFetch('/v2/api/system/cancel-day', {
      method: 'POST',
      body: JSON.stringify({ date: dateStr, reason: reason }),
    });
    closeModal();
    var cancelled = (data.data && data.data.cancelled) ? data.data.cancelled : 0;
    showToast(cancelled + ' booking(s) cancelled', 'info');
    initCalendar();
  } catch (err) {
    showToast('Failed to cancel day: ' + (err.message || 'Unknown error'), 'error');
  }
}

// ── Inline Confirm / Decline from Calendar ───────────────────
async function calConfirmBooking(bookingId, dateStr) {
  try {
    await apiFetch('/v2/api/bookings/' + bookingId + '/confirm', { method: 'POST' });
    showToast('Booking confirmed.', 'success');
    await loadCalendarData();
    renderCalendar();
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
  } catch (err) {
    showToast('Could not decline: ' + (err.message || 'Unknown error'), 'error');
  }
}

// ── Calendar Keyboard Navigation ────────────────────────────
document.addEventListener('keydown', function(e) {
  // Only handle keys when calendar section is active
  if (APP.currentSection !== 'calendar') return;

  // Don't interfere with inputs or modals
  var tag = (document.activeElement || {}).tagName;
  if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;
  var modalOverlay = document.getElementById('ap-modal-overlay');
  if (modalOverlay && modalOverlay.classList.contains('open')) return;

  var handled = false;

  // Arrow Left / Right: navigate weeks
  if (e.key === 'ArrowLeft' && !e.shiftKey) {
    calNavWeek(-1);
    handled = true;
  } else if (e.key === 'ArrowRight' && !e.shiftKey) {
    calNavWeek(1);
    handled = true;
  }

  // Arrow Up / Down: scroll the calendar grid
  if (e.key === 'ArrowUp' || e.key === 'ArrowDown') {
    var grid = document.getElementById('ap-calendar-grid');
    if (grid) {
      var scrollDelta = e.key === 'ArrowUp' ? -CAL_SLOT_HEIGHT * 2 : CAL_SLOT_HEIGHT * 2;
      grid.scrollTop += scrollDelta;
      handled = true;
    }
  }

  // 't' key: go to today
  if (e.key === 't' || e.key === 'T') {
    calGoToday();
    handled = true;
  }

  if (handled) e.preventDefault();
});

//── Scoped Styles ────────────────────────────────────────────
function _calGetStyles() {
  return '' +

  // Navigation header
  '.cal-nav-header {' +
    'display: flex;' +
    'align-items: center;' +
    'gap: 12px;' +
    'padding: 12px 0;' +
    'margin-bottom: 8px;' +
  '}' +
  '.cal-nav-btn {' +
    'background: var(--ap-surface, #fff);' +
    'border: 1px solid var(--ap-border, #e2e8f0);' +
    'border-radius: 6px;' +
    'padding: 6px 12px;' +
    'cursor: pointer;' +
    'font-size: 14px;' +
    'color: var(--ap-text, #1e293b);' +
    'transition: background 0.15s;' +
  '}' +
  '.cal-nav-btn:hover {' +
    'background: var(--ap-bg, #f8fafc);' +
  '}' +
  '.cal-nav-label {' +
    'font-size: 16px;' +
    'font-weight: 600;' +
    'color: var(--ap-text, #1e293b);' +
    'flex: 1;' +
    'text-align: center;' +
  '}' +
  '.cal-nav-today-btn {' +
    'background: var(--ap-primary, #3b82f6);' +
    'color: #fff;' +
    'border: none;' +
    'border-radius: 6px;' +
    'padding: 6px 16px;' +
    'cursor: pointer;' +
    'font-size: 13px;' +
    'font-weight: 600;' +
    'transition: background 0.15s;' +
  '}' +
  '.cal-nav-today-btn:hover {' +
    'background: var(--ap-primary-dark, #2563eb);' +
  '}' +

  // Wrapper: time gutter + 5 day columns
  '.cal-week-wrapper {' +
    'display: grid;' +
    'grid-template-columns: 64px repeat(5, 1fr);' +
    'gap: 0;' +
    'border: 1px solid var(--ap-border, #e2e8f0);' +
    'border-radius: 8px;' +
    'overflow: hidden;' +
    'background: var(--ap-surface, #fff);' +
    'font-size: 13px;' +
  '}' +

  // Time gutter
  '.cal-time-gutter {' +
    'background: var(--ap-bg, #f8fafc);' +
    'border-right: 1px solid var(--ap-border, #e2e8f0);' +
  '}' +
  '.cal-gutter-header {' +
    'height: 40px;' +
    'border-bottom: 1px solid var(--ap-border, #e2e8f0);' +
  '}' +
  '.cal-gutter-body {' +
    'position: relative;' +
  '}' +
  '.cal-time-label {' +
    'position: absolute;' +
    'left: 0;' +
    'right: 4px;' +
    'text-align: right;' +
    'font-size: 11px;' +
    'color: var(--ap-text-muted, #64748b);' +
    'transform: translateY(-7px);' +
    'line-height: 1;' +
    'pointer-events: none;' +
    'white-space: nowrap;' +
  '}' +
  '.cal-time-dimmed {' +
    'opacity: 0.5;' +
  '}' +

  // Day columns
  '.cal-day-col {' +
    'border-right: 1px solid var(--ap-border, #e2e8f0);' +
    'min-width: 0;' +
  '}' +
  '.cal-day-col:last-child { border-right: none; }' +
  '.cal-day-today { background: rgba(59, 130, 246, 0.03); }' +

  // Day header
  '.cal-day-header {' +
    'height: 40px;' +
    'display: flex;' +
    'align-items: center;' +
    'justify-content: center;' +
    'border-bottom: 1px solid var(--ap-border, #e2e8f0);' +
    'font-weight: 600;' +
    'font-size: 13px;' +
    'color: var(--ap-text, #1e293b);' +
    'user-select: none;' +
    'cursor: pointer;' +
    'transition: background 0.15s;' +
  '}' +
  '.cal-day-header:hover {' +
    'background: rgba(59, 130, 246, 0.06);' +
  '}' +
  '.cal-header-today {' +
    'color: var(--ap-primary, #3b82f6);' +
    'background: rgba(59, 130, 246, 0.08);' +
  '}' +

  // Day body
  '.cal-day-body {' +
    'position: relative;' +
    'overflow: hidden;' +
  '}' +
  '.cal-day-body.cal-drag-over {' +
    'background: rgba(59, 130, 246, 0.05);' +
  '}' +

  // Slot backgrounds
  '.cal-slot-bg {' +
    'position: absolute;' +
    'left: 0; right: 0;' +
    'box-sizing: border-box;' +
  '}' +
  '.cal-slot-dimmed {' +
    'background: var(--ap-bg, #f8fafc);' +
  '}' +

  // Grid lines
  '.cal-hour-line {' +
    'position: absolute;' +
    'left: 0; right: 0;' +
    'height: 1px;' +
    'background: var(--ap-border, #e2e8f0);' +
    'pointer-events: none;' +
    'z-index: 1;' +
  '}' +
  '.cal-half-line {' +
    'position: absolute;' +
    'left: 0; right: 0;' +
    'height: 1px;' +
    'background: var(--ap-border, #e2e8f0);' +
    'opacity: 0.4;' +
    'pointer-events: none;' +
    'z-index: 1;' +
  '}' +

  // Current time indicator
  '.cal-now-line {' +
    'position: absolute;' +
    'left: 0; right: 0;' +
    'height: 2px;' +
    'background: #ef4444;' +
    'z-index: 5;' +
    'pointer-events: none;' +
  '}' +
  '.cal-now-line::before {' +
    'content: "";' +
    'position: absolute;' +
    'left: -4px;' +
    'top: -3px;' +
    'width: 8px;' +
    'height: 8px;' +
    'background: #ef4444;' +
    'border-radius: 50%;' +
  '}' +

  // Booking card
  '.cal-booking-card {' +
    'position: absolute;' +
    'box-sizing: border-box;' +
    'border-radius: 4px;' +
    'padding: 3px 6px;' +
    'overflow: hidden;' +
    'cursor: pointer;' +
    'z-index: 3;' +
    'font-size: 11px;' +
    'line-height: 1.3;' +
    'transition: box-shadow 0.15s, opacity 0.15s;' +
    'border-left: 3px solid transparent;' +
    'box-shadow: 0 1px 3px rgba(0,0,0,0.1);' +
  '}' +
  '.cal-booking-card:hover {' +
    'box-shadow: 0 2px 8px rgba(0,0,0,0.18);' +
    'z-index: 4;' +
  '}' +
  '.cal-booking-card[draggable="true"] { cursor: grab; }' +
  '.cal-booking-card[draggable="true"]:active { cursor: grabbing; }' +

  // Card colors
  '.cal-card-confirmed {' +
    'background: #ecfdf5;' +
    'border-left-color: #10b981;' +
    'color: #065f46;' +
  '}' +
  '.cal-card-pending {' +
    'background: #fffbeb;' +
    'border-left-color: #f59e0b;' +
    'color: #78350f;' +
  '}' +

  // Changed card (pulsing border)
  '.cal-card-changed {' +
    'animation: calPulseChanged 1.5s ease-in-out infinite;' +
    'border-left-color: #f97316;' +
  '}' +
  '@keyframes calPulseChanged {' +
    '0%, 100% { box-shadow: 0 1px 3px rgba(249,115,22,0.2); }' +
    '50% { box-shadow: 0 1px 8px rgba(249,115,22,0.5); }' +
  '}' +

  // Card dragging state
  '.cal-card-dragging {' +
    'opacity: 0.5;' +
    'box-shadow: none;' +
  '}' +

  // Card inner elements
  '.cal-card-time {' +
    'font-weight: 700;' +
    'font-size: 11px;' +
    'white-space: nowrap;' +
    'overflow: hidden;' +
    'text-overflow: ellipsis;' +
  '}' +
  '.cal-card-name {' +
    'font-weight: 600;' +
    'white-space: nowrap;' +
    'overflow: hidden;' +
    'text-overflow: ellipsis;' +
  '}' +
  '.cal-card-info {' +
    'white-space: nowrap;' +
    'overflow: hidden;' +
    'text-overflow: ellipsis;' +
    'opacity: 0.8;' +
    'font-size: 10px;' +
  '}' +

  // Card action buttons
  '.cal-card-actions {' +
    'display: flex;' +
    'gap: 4px;' +
    'margin-top: 2px;' +
  '}' +
  '.cal-action-btn {' +
    'border: none;' +
    'border-radius: 3px;' +
    'padding: 1px 6px;' +
    'font-size: 10px;' +
    'cursor: pointer;' +
    'font-weight: 600;' +
    'line-height: 1.6;' +
  '}' +
  '.cal-btn-confirm {' +
    'background: #10b981;' +
    'color: #fff;' +
  '}' +
  '.cal-btn-confirm:hover { background: #059669; }' +
  '.cal-btn-decline {' +
    'background: #ef4444;' +
    'color: #fff;' +
  '}' +
  '.cal-btn-decline:hover { background: #dc2626; }' +
  '.cal-btn-notify {' +
    'background: #f97316;' +
    'color: #fff;' +
  '}' +
  '.cal-btn-notify:hover { background: #ea580c; }' +
  '.cal-pulse-notify {' +
    'animation: calPulseNotify 1.5s ease-in-out infinite;' +
  '}' +
  '@keyframes calPulseNotify {' +
    '0%, 100% { opacity: 1; }' +
    '50% { opacity: 0.7; }' +
  '}' +

  // Drop indicator
  '.cal-drop-indicator {' +
    'position: absolute;' +
    'left: 2px; right: 2px;' +
    'background: rgba(59, 130, 246, 0.15);' +
    'border: 2px dashed #3b82f6;' +
    'border-radius: 4px;' +
    'z-index: 10;' +
    'pointer-events: none;' +
    'display: flex;' +
    'align-items: flex-start;' +
    'padding: 2px 6px;' +
    'font-size: 11px;' +
    'font-weight: 600;' +
    'color: #3b82f6;' +
  '}' +

  // Day detail booking list
  '.ap-day-booking-list {' +
    'display: flex;' +
    'flex-direction: column;' +
    'gap: 8px;' +
  '}' +
  '.ap-day-booking-item {' +
    'padding: 8px 12px;' +
    'border: 1px solid var(--ap-border, #e2e8f0);' +
    'border-radius: 6px;' +
    'background: var(--ap-surface, #fff);' +
    'transition: box-shadow 0.15s;' +
  '}' +
  '.ap-day-booking-item:hover {' +
    'box-shadow: 0 2px 8px rgba(0,0,0,0.08);' +
  '}' +

  // Responsive
  '@media (max-width: 768px) {' +
    '.cal-week-wrapper {' +
      'grid-template-columns: 48px repeat(5, 1fr);' +
      'font-size: 11px;' +
    '}' +
    '.cal-time-label { font-size: 9px; }' +
    '.cal-day-header { font-size: 11px; }' +
    '.cal-booking-card { font-size: 10px; padding: 2px 3px; }' +
    '.cal-nav-header { flex-wrap: wrap; }' +
    '.cal-nav-label { font-size: 13px; }' +
  '}' +
  '';
}
"""
