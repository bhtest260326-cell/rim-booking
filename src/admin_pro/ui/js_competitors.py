"""
admin_pro/ui/js_competitors.py
Market Pricing section JavaScript for the Admin Pro dashboard.
"""

JS_COMPETITORS = """
// ---------------------------------------------------------------------------
// Market Pricing — Competitor Price Monitoring
// ---------------------------------------------------------------------------

const SERVICE_TYPES = {
  rim_repair:    'Wheel Doctor',
  paint_touchup: 'Paint Touch-up',
  multiple_rims: 'Multiple Rims',
};

const PRICE_SOURCES = ['website', 'manual', 'phone_inquiry'];

let _competitorsCache = [];

async function initMarketPricing() {
  await Promise.all([
    loadCompetitors(),
    loadPriceComparison(),
    loadPriceLog(),
  ]);
}

// ---------------------------------------------------------------------------
// Load & render competitors table
// ---------------------------------------------------------------------------
async function loadCompetitors() {
  try {
    const res = await apiFetch('/v2/api/competitors?active_only=0');
    _competitorsCache = res.data || [];
    renderCompetitorsTable(_competitorsCache);
    populateCompetitorSelects(_competitorsCache);
  } catch (e) {
    console.error('loadCompetitors', e);
  }
}

function renderCompetitorsTable(competitors) {
  const tbody = document.getElementById('competitors-tbody');
  if (!tbody) return;
  if (!competitors.length) {
    tbody.innerHTML = '<tr><td colspan="6" class="ap-table-empty">No competitors added yet.</td></tr>';
    return;
  }
  tbody.innerHTML = competitors.map(c => `
    <tr class="${c.active ? '' : 'ap-row-muted'}">
      <td><strong>${esc(c.name)}</strong></td>
      <td>${c.website ? '<a href="' + esc(c.website) + '" target="_blank" rel="noopener" style="color:#3b82f6">' + esc(c.website) + '</a>' : '—'}</td>
      <td>${esc(c.phone || '—')}</td>
      <td>${esc(c.location || '—')}</td>
      <td><span class="ap-badge ${c.active ? 'ap-badge-green' : 'ap-badge-muted'}">${c.active ? 'Active' : 'Inactive'}</span></td>
      <td>
        <button class="ap-btn ap-btn-ghost ap-btn-xs" onclick="toggleCompetitorActive(${c.id}, ${c.active ? 0 : 1})">
          ${c.active ? 'Deactivate' : 'Activate'}
        </button>
      </td>
    </tr>
  `).join('');
}

function populateCompetitorSelects(competitors) {
  const selects = document.querySelectorAll('.competitor-select');
  const active = competitors.filter(c => c.active);
  selects.forEach(sel => {
    const current = sel.value;
    sel.innerHTML = '<option value="">Select competitor...</option>' +
      active.map(c => `<option value="${c.id}">${esc(c.name)}</option>`).join('');
    if (current) sel.value = current;
  });
}

function esc(s) {
  if (!s) return '';
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

// ---------------------------------------------------------------------------
// Add competitor
// ---------------------------------------------------------------------------
async function addCompetitor(e) {
  e.preventDefault();
  const form = e.target;
  const body = {
    name: form.querySelector('[name=comp_name]').value.trim(),
    website: form.querySelector('[name=comp_website]').value.trim() || null,
    phone: form.querySelector('[name=comp_phone]').value.trim() || null,
    location: form.querySelector('[name=comp_location]').value.trim() || null,
  };
  if (!body.name) { showToast('Name is required', 'error'); return; }
  try {
    await apiFetch('/v2/api/competitors', { method: 'POST', body: JSON.stringify(body) });
    showToast('Competitor added', 'success');
    form.reset();
    await loadCompetitors();
  } catch (e) {
    showToast('Failed: ' + (e.message || e), 'error');
  }
}

async function toggleCompetitorActive(id, newState) {
  try {
    await apiFetch('/v2/api/competitors/' + id, {
      method: 'PUT',
      body: JSON.stringify({ active: newState }),
    });
    showToast(newState ? 'Activated' : 'Deactivated', 'success');
    await Promise.all([loadCompetitors(), loadPriceComparison()]);
  } catch (e) {
    showToast('Failed: ' + (e.message || e), 'error');
  }
}

// ---------------------------------------------------------------------------
// Log price
// ---------------------------------------------------------------------------
async function logPrice(e) {
  e.preventDefault();
  const form = e.target;
  const compId = form.querySelector('[name=price_competitor]').value;
  if (!compId) { showToast('Select a competitor', 'error'); return; }
  const body = {
    service_type: form.querySelector('[name=price_service]').value,
    price_low: parseFloat(form.querySelector('[name=price_low]').value) || null,
    price_high: parseFloat(form.querySelector('[name=price_high]').value) || null,
    source: form.querySelector('[name=price_source]').value || null,
    notes: form.querySelector('[name=price_notes]').value.trim() || null,
  };
  if (!body.service_type) { showToast('Select a service type', 'error'); return; }
  if (!body.price_low && !body.price_high) { showToast('Enter at least one price', 'error'); return; }
  try {
    await apiFetch('/v2/api/competitors/' + compId + '/prices', {
      method: 'POST',
      body: JSON.stringify(body),
    });
    showToast('Price logged', 'success');
    form.reset();
    await Promise.all([loadPriceComparison(), loadPriceLog()]);
  } catch (e) {
    showToast('Failed: ' + (e.message || e), 'error');
  }
}

// ---------------------------------------------------------------------------
// Price comparison chart
// ---------------------------------------------------------------------------
async function loadPriceComparison() {
  try {
    const res = await apiFetch('/v2/api/competitors/comparison');
    renderComparisonChart(res.data || []);
    renderComparisonTable(res.data || []);
  } catch (e) {
    console.error('loadPriceComparison', e);
  }
}

function renderComparisonChart(data) {
  destroyChart('priceComparison');
  const canvas = document.getElementById('price-comparison-chart');
  if (!canvas || !data.length) return;

  const labels = data.map(d => d.service_label);
  const ourPrices = data.map(d => d.our_price || 0);
  const marketAvg = data.map(d => d.market_avg || 0);

  APP.charts.priceComparison = new Chart(canvas, {
    type: 'bar',
    data: {
      labels,
      datasets: [
        {
          label: 'Our Price ($)',
          data: ourPrices,
          backgroundColor: CHART_COLORS.blue,
          borderRadius: 4,
        },
        {
          label: 'Market Average ($)',
          data: marketAvg,
          backgroundColor: CHART_COLORS.amber,
          borderRadius: 4,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { position: 'top' },
        tooltip: BASE_TOOLTIP,
      },
      scales: {
        x: { grid: GRID_STYLE, ticks: TICK_STYLE },
        y: {
          grid: GRID_STYLE,
          ticks: { ...TICK_STYLE, callback: v => '$' + v },
          beginAtZero: true,
        },
      },
    },
  });
}

function renderComparisonTable(data) {
  const tbody = document.getElementById('comparison-tbody');
  if (!tbody) return;
  if (!data.length) {
    tbody.innerHTML = '<tr><td colspan="6" class="ap-table-empty">No price data yet. Log competitor prices to see comparisons.</td></tr>';
    return;
  }
  tbody.innerHTML = data.map(d => {
    let diffHtml = '—';
    if (d.our_price != null && d.market_avg != null) {
      const diff = d.our_price - d.market_avg;
      const pct = ((diff / d.market_avg) * 100).toFixed(0);
      const cls = diff > 0 ? 'ap-badge-red' : diff < 0 ? 'ap-badge-green' : 'ap-badge-muted';
      const sign = diff > 0 ? '+' : '';
      diffHtml = '<span class="ap-badge ' + cls + '">' + sign + '$' + diff.toFixed(0) + ' (' + sign + pct + '%)</span>';
    }
    return '<tr>' +
      '<td><strong>' + esc(d.service_label) + '</strong></td>' +
      '<td>' + (d.our_price != null ? '$' + d.our_price : '—') + '</td>' +
      '<td>$' + (d.market_avg != null ? d.market_avg.toFixed(0) : '—') + '</td>' +
      '<td>' + (d.market_min != null ? '$' + d.market_min : '—') + ' – ' + (d.market_max != null ? '$' + d.market_max : '—') + '</td>' +
      '<td>' + d.num_competitors + '</td>' +
      '<td>' + diffHtml + '</td>' +
      '</tr>';
  }).join('');
}

// ---------------------------------------------------------------------------
// Recent price log
// ---------------------------------------------------------------------------
async function loadPriceLog() {
  try {
    const res = await apiFetch('/v2/api/competitors/prices');
    renderPriceLog(res.data || []);
  } catch (e) {
    console.error('loadPriceLog', e);
  }
}

function renderPriceLog(prices) {
  const tbody = document.getElementById('price-log-tbody');
  if (!tbody) return;
  const recent = prices.slice(0, 20);
  if (!recent.length) {
    tbody.innerHTML = '<tr><td colspan="6" class="ap-table-empty">No prices logged yet.</td></tr>';
    return;
  }
  tbody.innerHTML = recent.map(p => {
    const priceStr = (p.price_low && p.price_high && p.price_low !== p.price_high)
      ? '$' + p.price_low + ' – $' + p.price_high
      : '$' + (p.price_low || p.price_high || 0);
    const dateStr = p.recorded_at ? new Date(p.recorded_at).toLocaleDateString('en-AU') : '—';
    return '<tr>' +
      '<td>' + esc(p.competitor_name) + '</td>' +
      '<td>' + esc(SERVICE_TYPES[p.service_type] || p.service_type) + '</td>' +
      '<td>' + priceStr + '</td>' +
      '<td><span class="ap-badge ap-badge-muted">' + esc(p.source || '—') + '</span></td>' +
      '<td>' + dateStr + '</td>' +
      '<td>' + esc(p.notes || '—') + '</td>' +
      '</tr>';
  }).join('');
}
"""
