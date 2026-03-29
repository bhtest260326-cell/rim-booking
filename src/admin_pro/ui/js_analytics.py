"""
admin_pro/ui/js_analytics.py
Analytics section JavaScript for the Admin Pro dashboard.
Chart.js is loaded from CDN in the HTML head.
"""

JS_ANALYTICS = """
// ---------------------------------------------------------------------------
// Chart.js global defaults
// ---------------------------------------------------------------------------
Chart.defaults.color = '#64748b';
Chart.defaults.font.family = "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif";

// ---------------------------------------------------------------------------
// Colour palette
// ---------------------------------------------------------------------------
const CHART_COLORS = {
  blue:   '#3b82f6',
  green:  '#22c55e',
  amber:  '#f59e0b',
  red:    '#ef4444',
  purple: '#8b5cf6',
  teal:   '#14b8a6',
  orange: '#f97316',
  muted:  '#64748b',
};
const CHART_BG = 'rgba(255,255,255,0.05)';

// ---------------------------------------------------------------------------
// Shared grid / tick style helpers
// ---------------------------------------------------------------------------
const GRID_STYLE  = { color: 'rgba(255,255,255,0.05)' };
const TICK_STYLE  = { color: '#64748b' };
const BASE_TOOLTIP = {
  backgroundColor: 'rgba(15,23,42,0.9)',
  titleColor: '#f1f5f9',
  bodyColor: '#cbd5e1',
  borderColor: 'rgba(255,255,255,0.1)',
  borderWidth: 1,
  padding: 10,
  cornerRadius: 6,
};

// ---------------------------------------------------------------------------
// Chart cleanup
// ---------------------------------------------------------------------------
function destroyChart(key) {
  if (APP.charts[key]) {
    APP.charts[key].destroy();
    delete APP.charts[key];
  }
}

// ---------------------------------------------------------------------------
// Trend period selector state  (period in days; HTML buttons call setTrendPeriod)
// ---------------------------------------------------------------------------
let _trendDays = 30;

function setTrendPeriod(days) {
  _trendDays = days;
  // Update active button highlight on the hardcoded ap-pill buttons in HTML
  document.querySelectorAll('.ap-chart-controls .ap-pill').forEach(btn => {
    const btnDays = parseInt(btn.textContent, 10);
    btn.classList.toggle('active', btnDays === days);
  });
  loadTrendsChart();
}

// Keep the old name as an alias for compatibility
function setTrendsWeeks(weeks) {
  setTrendPeriod(weeks * 7);
}

// ---------------------------------------------------------------------------
// Analytics Overview KPIs
// ---------------------------------------------------------------------------
async function loadAnalyticsOverview() {
  try {
    const data = await apiFetch('/v2/api/analytics/overview');
    const d = data;

    // HTML value elements carry a -val suffix; the IDs without -val are the card wrappers
    const conversionEl = document.getElementById('ana-conversion-val');
    if (conversionEl) {
      conversionEl.textContent = (d.conversion_rate ?? 0).toFixed(1) + '%';
    }

    const avgConfirmEl = document.getElementById('ana-avg-confirm-val');
    if (avgConfirmEl) {
      const hours = d.avg_confirm_hours ?? 0;
      if (hours < 1) {
        avgConfirmEl.textContent = Math.round(hours * 60) + 'm';
      } else if (hours < 24) {
        avgConfirmEl.textContent = Math.round(hours) + 'h';
      } else {
        avgConfirmEl.textContent = (hours / 24).toFixed(1) + 'd';
      }
    }

    const weekEl = document.getElementById('ana-week-val');
    if (weekEl) {
      weekEl.textContent = d.this_week_confirmed ?? 0;
    }

  } catch (err) {
    console.error('loadAnalyticsOverview error:', err);
  }
}

// ---------------------------------------------------------------------------
// Bookings Trend Line Chart
// ---------------------------------------------------------------------------
async function loadTrendsChart() {
  try {
    // Convert days to weeks for the API; minimum 1 week
    const weeksParam = Math.max(1, Math.round(_trendDays / 7));
    const data = await apiFetch(`/v2/api/analytics/trends?weeks=${weeksParam}`);
    const d = data;

    destroyChart('trends');

    // HTML canvas ID is 'canvas-trend' (inside container 'chart-trend')
    const canvas = document.getElementById('canvas-trend');
    if (!canvas) return;

    // Hide placeholder once we have data
    const placeholder = document.getElementById('trend-placeholder');
    if (placeholder) placeholder.style.display = 'none';

    APP.charts['trends'] = new Chart(canvas, {
      type: 'line',
      data: {
        labels: d.labels,
        datasets: [{
          label: 'Confirmed Bookings',
          data: d.counts,
          borderColor: CHART_COLORS.blue,
          backgroundColor: 'rgba(59,130,246,0.1)',
          fill: true,
          tension: 0.4,
          pointBackgroundColor: CHART_COLORS.blue,
          pointBorderColor: CHART_COLORS.blue,
          pointRadius: 4,
          pointHoverRadius: 6,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            ...BASE_TOOLTIP,
            callbacks: {
              title: ctx => ctx[0].label,
              label: ctx => ` ${ctx.parsed.y} booking${ctx.parsed.y !== 1 ? 's' : ''}`,
            },
          },
        },
        scales: {
          x: {
            grid: GRID_STYLE,
            ticks: {
              ...TICK_STYLE,
              maxRotation: 30,
              autoSkip: true,
              maxTicksLimit: 8,
            },
          },
          y: {
            grid: GRID_STYLE,
            ticks: { ...TICK_STYLE, stepSize: 1 },
            beginAtZero: true,
          },
        },
        interaction: {
          mode: 'index',
          intersect: false,
        },
      },
    });
  } catch (err) {
    console.error('loadTrendsChart error:', err);
  }
}

// ---------------------------------------------------------------------------
// Service Type Doughnut Chart
// ---------------------------------------------------------------------------
async function loadServicesChart() {
  try {
    const data = await apiFetch('/v2/api/analytics/services');
    const services = data.services || [];

    destroyChart('services');

    // HTML canvas ID is 'canvas-service' (inside container 'chart-service')
    const canvas = document.getElementById('canvas-service');
    if (!canvas) return;

    // Hide placeholder once we have data
    const placeholder = document.getElementById('service-placeholder');
    if (placeholder) placeholder.style.display = 'none';

    const palette = [
      CHART_COLORS.blue,
      CHART_COLORS.green,
      CHART_COLORS.amber,
      CHART_COLORS.purple,
      CHART_COLORS.teal,
      CHART_COLORS.orange,
      CHART_COLORS.red,
    ];

    const labels = services.map(s => s.label || serviceLabel(s.type));
    const counts  = services.map(s => s.count);
    const colors  = services.map((_, i) => palette[i % palette.length]);

    APP.charts['services'] = new Chart(canvas, {
      type: 'doughnut',
      data: {
        labels,
        datasets: [{
          data: counts,
          backgroundColor: colors,
          borderColor: 'rgba(15,23,42,0.8)',
          borderWidth: 2,
          hoverOffset: 6,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        cutout: '60%',
        plugins: {
          legend: {
            display: true,
            position: 'bottom',
            labels: {
              color: '#94a3b8',
              padding: 12,
              boxWidth: 12,
              font: { size: 12 },
            },
          },
          tooltip: {
            ...BASE_TOOLTIP,
            callbacks: {
              label: ctx => {
                const total = ctx.dataset.data.reduce((a, b) => a + b, 0);
                const pct   = total ? ((ctx.parsed / total) * 100).toFixed(1) : 0;
                return ` ${ctx.label}: ${ctx.parsed} (${pct}%)`;
              },
            },
          },
        },
      },
    });
  } catch (err) {
    console.error('loadServicesChart error:', err);
  }
}

// ---------------------------------------------------------------------------
// Conversion Funnel — populates the existing HTML funnel widget elements.
// The HTML uses custom funnel steps (ap-funnel-step) not a canvas, so we
// update the count spans and bar widths directly.
// Stage order from the API: Emails Received → Booking Extracted → Sent to Owner → Confirmed
// HTML step IDs:            funnel-enquiries, funnel-pending, funnel-confirmed, funnel-completed
// ---------------------------------------------------------------------------
async function loadFunnelChart() {
  try {
    const data = await apiFetch('/v2/api/analytics/funnel');
    const stages = data.stages || [];

    // Map API stage labels to HTML element IDs and bar width percentages
    // Use the top-of-funnel count as 100 % baseline
    const topCount = stages.length ? (stages[0].count || 1) : 1;

    const idMap = [
      'funnel-enquiries',
      'funnel-pending',
      'funnel-confirmed',
      'funnel-completed',
    ];

    stages.forEach((stage, i) => {
      const stepId = idMap[i];
      if (!stepId) return;

      const countEl = document.getElementById(stepId + '-n');
      if (countEl) countEl.textContent = stage.count.toLocaleString();

      const barEl = document.querySelector('#' + stepId + ' .ap-funnel-bar');
      if (barEl) {
        const pct = topCount ? Math.round((stage.count / topCount) * 100) : 0;
        barEl.style.width = pct + '%';
      }
    });
  } catch (err) {
    console.error('loadFunnelChart error:', err);
  }
}

// ---------------------------------------------------------------------------
// Top Suburbs — renders into the existing HTML suburbs-list widget.
// The HTML uses an ap-suburbs-list div (no canvas), so we generate rows
// with inline progress bars rather than a Chart.js chart.
// ---------------------------------------------------------------------------
async function loadSuburbsChart() {
  try {
    const data = await apiFetch('/v2/api/analytics/suburbs');
    const suburbs = (data.suburbs || []).slice(0, 10);

    const listEl = document.getElementById('suburbs-list');
    if (!listEl) return;

    if (!suburbs.length) {
      listEl.innerHTML = '<div class="ap-table-empty">No suburb data yet.</div>';
      return;
    }

    const maxCount = Math.max(...suburbs.map(s => s.count));

    listEl.innerHTML = suburbs.map(s => {
      const pct = maxCount ? Math.round((s.count / maxCount) * 100) : 0;
      return `<div style="display:flex;align-items:center;gap:8px;height:36px;flex-shrink:0">` +
        `<span style="font-size:12px;min-width:90px;max-width:90px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${escapeHtml(s.name)}</span>` +
        `<div style="flex:1;background:rgba(255,255,255,0.06);border-radius:3px;height:6px">` +
          `<div style="background:${CHART_COLORS.blue};border-radius:3px;height:6px;width:${pct}%;transition:width 0.4s ease"></div>` +
        `</div>` +
        `<span style="font-size:12px;color:var(--ap-text-muted);min-width:28px;text-align:right">${s.count}</span>` +
      `</div>`;
    }).join('');
  } catch (err) {
    console.error('loadSuburbsChart error:', err);
  }
}

// ---------------------------------------------------------------------------
// Trend period selector init — HTML already has hardcoded ap-pill buttons
// calling setTrendPeriod(30) / setTrendPeriod(90). This function just syncs
// the active state to the current _trendDays value.
// ---------------------------------------------------------------------------
function initTrendsWeekSelector() {
  document.querySelectorAll('.ap-chart-controls .ap-pill').forEach(btn => {
    const btnDays = parseInt(btn.textContent, 10);
    btn.classList.toggle('active', btnDays === _trendDays);
  });
}

// ---------------------------------------------------------------------------
// CSV Export — client-side generation from already-fetched analytics data
// ---------------------------------------------------------------------------
async function exportAnalyticsCSV() {
  try {
    // Determine the date range from current trend period
    const endDate = new Date();
    const startDate = new Date();
    startDate.setDate(endDate.getDate() - _trendDays);

    const fmtDate = d => d.toISOString().split('T')[0];
    const startStr = fmtDate(startDate);
    const endStr = fmtDate(endDate);

    // Fetch all data in parallel for the export
    const [overview, trends, services, suburbs, funnel] = await Promise.all([
      apiFetch('/v2/api/analytics/overview'),
      apiFetch(`/v2/api/analytics/trends?weeks=${Math.max(1, Math.round(_trendDays / 7))}`),
      apiFetch('/v2/api/analytics/services'),
      apiFetch('/v2/api/analytics/suburbs'),
      apiFetch('/v2/api/analytics/funnel'),
    ]);

    const lines = [];

    // Overview KPIs
    lines.push('Section,Metric,Value');
    lines.push(`Overview,Total Bookings,${overview.total_bookings || 0}`);
    lines.push(`Overview,Confirmed,${overview.confirmed || 0}`);
    lines.push(`Overview,Declined,${overview.declined || 0}`);
    lines.push(`Overview,Pending,${overview.pending || 0}`);
    lines.push(`Overview,Conversion Rate,${overview.conversion_rate || 0}%`);
    lines.push(`Overview,Avg Confirm Hours,${overview.avg_confirm_hours || 0}`);
    lines.push(`Overview,This Week Confirmed,${overview.this_week_confirmed || 0}`);
    lines.push(`Overview,Total Customers,${overview.total_customers || 0}`);
    lines.push('');

    // Trends
    lines.push('Week,Bookings');
    if (trends.labels && trends.counts) {
      trends.labels.forEach((label, i) => {
        lines.push(`"${label}",${trends.counts[i] || 0}`);
      });
    }
    lines.push('');

    // Services
    lines.push('Service Type,Count');
    (services.services || []).forEach(s => {
      lines.push(`"${s.label || s.type}",${s.count}`);
    });
    lines.push('');

    // Funnel
    lines.push('Funnel Stage,Count');
    (funnel.stages || []).forEach(s => {
      lines.push(`"${s.label}",${s.count}`);
    });
    lines.push('');

    // Suburbs
    lines.push('Suburb,Bookings');
    (suburbs.suburbs || []).forEach(s => {
      lines.push(`"${s.name}",${s.count}`);
    });

    const csv = lines.join('\\n');
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `analytics_${startStr}_${endStr}.csv`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);

  } catch (err) {
    console.error('exportAnalyticsCSV error:', err);
    showToast && showToast('Export failed: ' + err.message, 'error');
  }
}

// ---------------------------------------------------------------------------
// Demand Heatmap — day-of-week x suburb with forecast overlay
// ---------------------------------------------------------------------------
let _demandData = null;
let _forecastVisible = false;

async function loadDemandHeatmap() {
  try {
    const data = await apiFetch('/v2/api/analytics/forecast');
    _demandData = data;

    const placeholder = document.getElementById('demand-placeholder');
    if (placeholder) placeholder.style.display = 'none';

    renderDemandHeatmap();
  } catch (err) {
    console.error('loadDemandHeatmap error:', err);
  }
}

function toggleDemandForecast() {
  _forecastVisible = !_forecastVisible;
  const btn = document.getElementById('forecast-toggle');
  if (btn) btn.classList.toggle('active', _forecastVisible);
  renderDemandHeatmap();
}

function renderDemandHeatmap() {
  const container = document.getElementById('demand-heatmap-content');
  if (!container || !_demandData) return;

  const heatmap = _demandData.heatmap || [];
  const forecast = _demandData.forecast || [];
  const forecastDates = _demandData.forecast_dates || [];

  const dowNames = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

  // Get top suburbs (up to 8) for the heatmap grid
  const suburbSet = {};
  heatmap.forEach(h => {
    if (!suburbSet[h.suburb]) suburbSet[h.suburb] = 0;
    suburbSet[h.suburb] += h.count;
  });
  const topSuburbs = Object.entries(suburbSet)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 8)
    .map(e => e[0]);

  if (!topSuburbs.length) {
    container.innerHTML = '<div class="ap-table-empty">No booking data for heatmap.</div>';
    return;
  }

  // Build lookup: (dow, suburb) -> count
  const lookup = {};
  heatmap.forEach(h => {
    lookup[h.dow + ':' + h.suburb] = h.count;
  });

  // Find max for colour scaling
  let maxCount = 1;
  heatmap.forEach(h => { if (h.count > maxCount) maxCount = h.count; });

  // Build the heatmap table
  let html = '<div style="overflow-x:auto">';
  html += '<table style="width:100%;border-collapse:collapse;font-size:12px">';
  html += '<thead><tr><th style="padding:6px 8px;text-align:left;color:#94a3b8;font-weight:500"></th>';
  dowNames.forEach(d => {
    html += '<th style="padding:6px 8px;text-align:center;color:#94a3b8;font-weight:500">' + d + '</th>';
  });
  html += '</tr></thead><tbody>';

  topSuburbs.forEach(suburb => {
    html += '<tr>';
    html += '<td style="padding:6px 8px;white-space:nowrap;color:#cbd5e1;font-size:11px;max-width:100px;overflow:hidden;text-overflow:ellipsis">' + escapeHtml(suburb) + '</td>';
    for (let dow = 0; dow < 7; dow++) {
      const count = lookup[dow + ':' + suburb] || 0;
      const intensity = maxCount ? count / maxCount : 0;
      const bg = count > 0
        ? 'rgba(59,130,246,' + (0.15 + intensity * 0.7).toFixed(2) + ')'
        : 'rgba(255,255,255,0.03)';
      html += '<td style="padding:6px 8px;text-align:center;border-radius:4px;background:' + bg + ';color:' + (count > 0 ? '#e2e8f0' : '#475569') + '">' + (count || '-') + '</td>';
    }
    html += '</tr>';
  });

  html += '</tbody></table></div>';

  // Forecast section
  if (_forecastVisible) {
    html += '<div style="margin-top:16px;padding-top:16px;border-top:1px solid rgba(255,255,255,0.06)">';
    html += '<div style="font-size:12px;color:#94a3b8;margin-bottom:10px;font-weight:500">2-Week Demand Forecast (based on 8-week moving average)</div>';

    // Forecast bar chart by day of week
    html += '<div style="display:flex;gap:6px;align-items:flex-end;height:120px;padding:0 8px">';
    const maxForecast = Math.max(...forecast.map(f => f.avg_per_week), 1);
    forecast.forEach(f => {
      const barH = Math.max(4, Math.round((f.avg_per_week / maxForecast) * 100));
      html += '<div style="flex:1;display:flex;flex-direction:column;align-items:center;gap:4px">';
      html += '<span style="font-size:10px;color:#94a3b8">' + f.avg_per_week + '</span>';
      html += '<div style="width:100%;max-width:40px;height:' + barH + 'px;background:rgba(139,92,246,0.5);border-radius:3px 3px 0 0;transition:height 0.3s ease"></div>';
      html += '<span style="font-size:10px;color:#64748b">' + f.dow_name + '</span>';
      html += '</div>';
    });
    html += '</div>';

    // Daily forecast for next 14 days
    html += '<div style="margin-top:12px;display:grid;grid-template-columns:repeat(7,1fr);gap:4px">';
    forecastDates.forEach(fd => {
      const dayNum = fd.date.split('-')[2];
      const intensity = maxForecast ? fd.predicted / maxForecast : 0;
      const bg = fd.predicted > 0
        ? 'rgba(139,92,246,' + (0.15 + intensity * 0.5).toFixed(2) + ')'
        : 'rgba(255,255,255,0.03)';
      html += '<div style="padding:6px 4px;text-align:center;border-radius:4px;background:' + bg + '">';
      html += '<div style="font-size:9px;color:#64748b">' + fd.dow_name + '</div>';
      html += '<div style="font-size:11px;color:#cbd5e1">' + dayNum + '</div>';
      html += '<div style="font-size:10px;color:#a78bfa">' + fd.predicted + '</div>';
      html += '</div>';
    });
    html += '</div>';

    html += '</div>';
  }

  container.innerHTML = html;
}

// ---------------------------------------------------------------------------
// Main init — called from the dashboard router when the analytics tab opens
// ---------------------------------------------------------------------------
async function initAnalytics() {
  // Reset trend week selector to default if this is a fresh open
  initTrendsWeekSelector();
  _forecastVisible = false;
  const fBtn = document.getElementById('forecast-toggle');
  if (fBtn) fBtn.classList.remove('active');

  await Promise.all([
    loadAnalyticsOverview(),
    loadTrendsChart(),
    loadServicesChart(),
    loadFunnelChart(),
    loadSuburbsChart(),
    loadDemandHeatmap(),
  ]);
}
"""
