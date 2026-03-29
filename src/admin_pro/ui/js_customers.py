JS_CUSTOMERS = """
// ─── Customers Section ────────────────────────────────────────────────────────
// API response formats (no ok/data wrapper):
//   GET /v2/api/customers              → {customers:[...], total:N}
//   GET /v2/api/customers/search?q=... → {results:[...]}
//   GET /v2/api/customers/<b64email>   → {email, name, phone, stats:{...}, bookings:[...], maintenance_due}
//
// HTML IDs:
//   #customers-count, #customer-search, #customers-tbody
// ─────────────────────────────────────────────────────────────────────────────

const CUSTOMERS_STATE = { all: [] };

async function initCustomers() {
  await loadCustomers();
}

// ─── Load & Render List ───────────────────────────────────────────────────────

async function loadCustomers() {
  const tbody = document.getElementById('customers-tbody');
  if (!tbody) return;
  tbody.innerHTML = '<tr><td colspan="5" class="ap-table-empty"><div class="ap-spinner ap-spinner-sm"></div></td></tr>';
  try {
    const data = await apiFetch('/v2/api/customers');
    CUSTOMERS_STATE.all = data.customers || [];
    renderCustomerTable(CUSTOMERS_STATE.all);
  } catch (e) {
    const tbody2 = document.getElementById('customers-tbody');
    if (tbody2) tbody2.innerHTML = `<tr><td colspan="5" class="ap-table-empty ap-text-danger">${escapeHtml(e.message)}</td></tr>`;
  }
}

function renderCustomerTable(customers) {
  const tbody = document.getElementById('customers-tbody');
  const countEl = document.getElementById('customers-count');
  if (!tbody) return;

  if (countEl) countEl.textContent = `${customers.length} customer${customers.length !== 1 ? 's' : ''}`;

  if (customers.length === 0) {
    tbody.innerHTML = '<tr><td colspan="5" class="ap-table-empty">No customers found</td></tr>';
    return;
  }

  tbody.innerHTML = customers.map(c => {
    // URL-safe base64 of email (compatible with Python urlsafe_b64decode)
    const b64 = btoa(c.email).replace(/\\+/g, '-').replace(/\\//g, '_').replace(/=/g, '');
    return `
      <tr class="ap-table-row-clickable" onclick="openCustomerDetail('${b64}')">
        <td><strong>${escapeHtml(c.name || '—')}</strong></td>
        <td class="ap-text-muted">${escapeHtml(c.email)}</td>
        <td class="ap-text-muted">${escapeHtml(c.phone || '—')}</td>
        <td>${c.total_bookings || 0}</td>
        <td class="ap-text-muted">${c.last_booking ? relativeTime(c.last_booking) : '—'}</td>
      </tr>
    `;
  }).join('');
}

// ─── Search ───────────────────────────────────────────────────────────────────

const searchCustomers = debounce(async function(query) {
  const q = (query || '').trim().toLowerCase();
  if (!q) {
    renderCustomerTable(CUSTOMERS_STATE.all);
    return;
  }
  if (q.length < 2) return;

  // Local filter first for instant results
  const local = CUSTOMERS_STATE.all.filter(c =>
    (c.name || '').toLowerCase().includes(q) ||
    (c.email || '').toLowerCase().includes(q) ||
    (c.phone || '').includes(q)
  );

  if (local.length > 0) {
    renderCustomerTable(local);
    return;
  }

  // Server search fallback
  try {
    const data = await apiFetch(`/v2/api/customers/search?q=${encodeURIComponent(query)}`);
    const results = (data.results || []).map(r => ({
      email: r.email,
      name: r.name,
      phone: r.phone,
      total_bookings: r.booking_count || 0,
      last_booking: null,
    }));
    renderCustomerTable(results);
  } catch (_) {
    renderCustomerTable([]);
  }
}, 300);

// ─── Customer Detail Modal ────────────────────────────────────────────────────

async function openCustomerDetail(emailB64) {
  // Show a loading state immediately
  showModal('Customer', '<div class="ap-loading"><div class="ap-spinner ap-spinner-sm"></div> Loading…</div>', '');
  const overlay = document.getElementById('ap-modal-overlay');
  if (overlay) {
    const modal = overlay.querySelector('.ap-modal');
    if (modal) modal.classList.add('ap-modal-wide');
  }

  try {
    const data = await apiFetch(`/v2/api/customers/${encodeURIComponent(emailB64)}`);
    const name = data.name || data.email;
    const phone = data.phone || '—';
    const email = data.email || '—';
    const total = data.stats?.total ?? '—';

    // Derive first/last booking dates
    const dates = (data.bookings || [])
      .map(b => b.booking_data?.preferred_date || b.created_at)
      .filter(Boolean)
      .sort();
    const firstDate = dates.length ? formatDateShort(dates[0]) : '—';
    const lastDate  = dates.length ? formatDateShort(dates[dates.length - 1]) : '—';

    // Build info rows
    const infoRows = [
      ['Email',         escapeHtml(email)],
      ['Phone',         escapeHtml(phone)],
      ['Total Bookings',String(total)],
      ['First Booking', escapeHtml(firstDate)],
      ['Last Booking',  escapeHtml(lastDate)],
    ].map(([label, val]) => `
      <div class="ap-info-row">
        <span class="ap-info-label">${label}</span>
        <span>${val}</span>
      </div>
    `).join('');

    // Build booking history rows
    const bookings = data.bookings || [];
    let historyRows;
    if (bookings.length === 0) {
      historyRows = '<tr><td colspan="4" class="ap-table-empty">No bookings</td></tr>';
    } else {
      historyRows = bookings.map(b => {
        const addr = escapeHtml(b.booking_data?.suburb || b.booking_data?.address || '—');
        return `
          <tr style="cursor:pointer" onclick="closeModal(); setTimeout(() => openBookingDetail('${b.id}'), 120)">
            <td>${b.booking_data?.preferred_date ? formatDateShort(b.booking_data.preferred_date) : '—'}</td>
            <td>${serviceLabel(b.booking_data?.service_type)}</td>
            <td class="ap-text-muted">${addr}</td>
            <td>${statusBadge(b.status)}</td>
          </tr>
        `;
      }).join('');
    }

    // Maintenance warning block
    const maintenanceHtml = data.maintenance_due
      ? '<div class="ap-card" style="border-color:var(--ap-amber);padding:10px;font-size:13px;margin-bottom:16px">&#9888; Maintenance reminder due</div>'
      : '';

    const gdprFooter = `
      <div style="margin-top:20px;padding-top:14px;border-top:1px solid var(--ap-border)">
        <div style="font-size:0.75rem;font-weight:700;color:var(--ap-text-dim);text-transform:uppercase;letter-spacing:.06em;margin-bottom:8px">GDPR / Privacy</div>
        <div style="display:flex;gap:8px;flex-wrap:wrap">
          <button class="ap-btn ap-btn-ghost ap-btn-xs" onclick="gdprExport('${emailB64}')">Export My Data</button>
          <button class="ap-btn ap-btn-ghost ap-btn-xs ap-text-danger" onclick="gdprPurge('${emailB64}', '${escapeHtml(email)}')">Anonymise (Right to Erasure)</button>
        </div>
      </div>`;

    const bodyHtml = `
      <div class="ap-customer-info" style="margin-bottom:16px">${infoRows}</div>
      ${maintenanceHtml}
      <div style="font-size:0.85rem;font-weight:700;color:var(--ap-text-dim);text-transform:uppercase;letter-spacing:.06em;margin-bottom:8px">Booking History</div>
      <div class="ap-table-wrap">
        <table class="ap-table">
          <thead><tr><th>Date</th><th>Service</th><th>Address</th><th>Status</th></tr></thead>
          <tbody>${historyRows}</tbody>
        </table>
      </div>
      ${gdprFooter}
    `;

    showModal(name, bodyHtml, '');
    // Re-apply wide class after showModal (it re-uses the same overlay element)
    if (overlay) {
      const modal = overlay.querySelector('.ap-modal');
      if (modal) modal.classList.add('ap-modal-wide');
    }
  } catch (e) {
    showModal('Error', '<p class="ap-text-danger">Failed to load customer: ' + escapeHtml(e.message) + '</p>', '');
  }
}
// ─── GDPR ────────────────────────────────────────────────────────────────────

async function gdprExport(emailB64) {
  try {
    const data = await apiFetch(`/v2/api/gdpr/export/${encodeURIComponent(emailB64)}`);
    if (!data.ok) throw new Error(data.error || 'Export failed');
    const json = JSON.stringify(data.data, null, 2);
    const blob = new Blob([json], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `gdpr-export-${emailB64.substring(0, 8)}.json`;
    a.click();
    URL.revokeObjectURL(url);
    showToast('GDPR export downloaded', 'success');
  } catch (e) {
    showToast('Export failed: ' + e.message, 'error');
  }
}

async function gdprPurge(emailB64, email) {
  if (!confirm(`Anonymise ALL personal data for ${email}? This cannot be undone.`)) return;
  try {
    const data = await apiFetch(`/v2/api/gdpr/purge/${encodeURIComponent(emailB64)}`, { method: 'POST' });
    if (!data.ok) throw new Error(data.error || 'Purge failed');
    showToast(`${data.records_anonymised} record(s) anonymised`, 'success');
    closeModal();
    await loadCustomers();
  } catch (e) {
    showToast('Purge failed: ' + e.message, 'error');
  }
}

// ─── End of Customers Section ─────────────────────────────────────────────────
"""
