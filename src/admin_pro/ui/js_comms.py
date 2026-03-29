JS_COMMS = """
// ─── Communications Section ───────────────────────────────────────────────────
// API response formats (no ok/data wrapper):
//   GET /v2/api/comms/gmail        → {messages:[...], error:null}
//   GET /v2/api/comms/dlq          → {entries:[...]}
//   GET /v2/api/comms/clarifications → {clarifications:[...]}
//   GET /v2/api/comms/waitlist     → {waitlist:[...]}
//   POST /v2/api/comms/sms         → {ok:bool}
//   GET /v2/api/comms/sms/log      → {logs:[...]}
// ─────────────────────────────────────────────────────────────────────────────

const COMMS_STATE = { clarifications: [] };

// Delegated click handler for all comms data-action buttons (avoids JSON.stringify in onclick)
document.addEventListener('click', function(e) {
  const btn = e.target.closest('[data-action]');
  if (!btn) return;
  const action = btn.dataset.action;
  if (action === 'gmail-preview') {
    viewGmailSnippet(btn.dataset.subject || '', btn.dataset.snippet || '');
  } else if (action === 'dlq-dismiss') {
    dismissDlqEntry(btn.dataset.msgId || '', btn);
  } else if (action === 'clar-detail') {
    const idx = parseInt(btn.dataset.idx, 10);
    const c = COMMS_STATE.clarifications[idx];
    if (c) showClarificationDetail(c);
  } else if (action === 'waitlist-notify') {
    notifyWaitlistCustomer(parseInt(btn.dataset.id, 10), btn);
  }
});

// ─── Tab Switching ────────────────────────────────────────────────────────────

function switchCommsTab(tab) {
  document.querySelectorAll('#section-comms .ap-tab-content').forEach(el => el.classList.remove('active'));
  document.querySelectorAll('#comms-tabs .ap-tab').forEach(el => el.classList.remove('active'));

  const panel = document.getElementById('comms-' + tab);
  if (panel) panel.classList.add('active');
  const btn = document.querySelector(`#comms-tabs [data-tab="${tab}"]`);
  if (btn) btn.classList.add('active');

  if (tab === 'gmail') loadGmailQueue();
  else if (tab === 'dlq') loadDlq();
  else if (tab === 'clarifications') loadClarifications();
  else if (tab === 'waitlist') loadWaitlist();
  else if (tab === 'sms') loadSmsLog();
}

async function initComms() {
  await loadGmailQueue();
}

// ─── Gmail Queue ──────────────────────────────────────────────────────────────

async function loadGmailQueue() {
  const tbody = document.getElementById('gmail-queue-tbody');
  if (!tbody) return;
  tbody.innerHTML = '<tr><td colspan="5" class="ap-table-empty"><div class="ap-spinner ap-spinner-sm"></div></td></tr>';
  try {
    const data = await apiFetch('/v2/api/comms/gmail?limit=30');
    const msgs = data.messages || [];

    const badge = document.getElementById('tab-badge-gmail');
    if (badge) badge.textContent = msgs.length ? msgs.length : '';

    if (data.error) {
      tbody.innerHTML = `<tr><td colspan="5" class="ap-table-empty ap-text-muted">${escapeHtml(data.error)}</td></tr>`;
      return;
    }
    if (msgs.length === 0) {
      tbody.innerHTML = '<tr><td colspan="5" class="ap-table-empty">Inbox is empty</td></tr>';
      return;
    }
    tbody.innerHTML = msgs.map(m => `
      <tr>
        <td style="max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${escapeHtml(m.from || '?')}</td>
        <td>${escapeHtml(m.subject || '(no subject)')}</td>
        <td class="ap-text-muted" style="white-space:nowrap">${escapeHtml(m.date || '')}</td>
        <td><span class="ap-badge ap-badge-blue">${escapeHtml(m.classification || 'inbox')}</span></td>
        <td>
          <button class="ap-btn ap-btn-ghost ap-btn-xs" data-action="gmail-preview" data-subject="${escapeHtml(m.subject || '')}" data-snippet="${escapeHtml(m.snippet || '')}">Preview</button>
        </td>
      </tr>
    `).join('');
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="5" class="ap-table-empty ap-text-danger">Failed to load Gmail: ${escapeHtml(e.message)}</td></tr>`;
  }
}

function viewGmailSnippet(subject, snippet) {
  showModal(escapeHtml(subject) || 'Gmail Message', `
    <div class="ap-card" style="padding:16px;font-size:14px;line-height:1.6">${escapeHtml(snippet)}</div>
  `);
}

// ─── Dead-Letter Queue ────────────────────────────────────────────────────────

async function loadDlq() {
  const tbody = document.getElementById('dlq-tbody');
  if (!tbody) return;
  tbody.innerHTML = '<tr><td colspan="6" class="ap-table-empty"><div class="ap-spinner ap-spinner-sm"></div></td></tr>';
  try {
    const data = await apiFetch('/v2/api/comms/dlq');
    const entries = data.entries || [];

    const badge = document.getElementById('tab-badge-dlq');
    if (badge) badge.textContent = entries.length || '';

    if (entries.length === 0) {
      tbody.innerHTML = '<tr><td colspan="6" class="ap-table-empty">DLQ is empty — all emails processed successfully 🎉</td></tr>';
      return;
    }
    tbody.innerHTML = entries.map(e => `
      <tr>
        <td class="ap-text-muted" style="font-size:11px;max-width:100px;overflow:hidden;text-overflow:ellipsis">${escapeHtml((e.gmail_msg_id || '').substring(0, 16))}…</td>
        <td>${escapeHtml(e.customer_email || '—')}</td>
        <td class="ap-text-muted" style="max-width:150px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${escapeHtml(e.subject || '—')}</td>
        <td style="max-width:220px">
          <div class="ap-text-danger" style="font-size:12px">${escapeHtml(e.error_type || '')}</div>
          <div class="ap-text-muted" style="font-size:11px">${escapeHtml((e.error_message || '').substring(0, 80))}</div>
        </td>
        <td><span class="ap-badge ap-badge-red">${e.failure_count || 1}</span></td>
        <td>
          <button class="ap-btn ap-btn-ghost ap-btn-xs ap-text-danger"
                  data-action="dlq-dismiss" data-msg-id="${escapeHtml(e.gmail_msg_id || '')}">Dismiss</button>
        </td>
      </tr>
    `).join('');
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="6" class="ap-table-empty ap-text-danger">${escapeHtml(e.message)}</td></tr>`;
  }
}

async function dismissDlqEntry(msgId, btn) {
  if (!msgId || !confirm('Dismiss this DLQ entry?')) return;
  btn.disabled = true;
  btn.textContent = '…';
  try {
    await apiFetch(`/v2/api/comms/dlq/${encodeURIComponent(msgId)}/dismiss`, { method: 'POST' });
    showToast('DLQ entry dismissed', 'info');
    await loadDlq();
  } catch (e) {
    showToast('Dismiss failed: ' + e.message, 'error');
    btn.disabled = false;
    btn.textContent = 'Dismiss';
  }
}

// ─── Clarifications ───────────────────────────────────────────────────────────

async function loadClarifications() {
  const tbody = document.getElementById('clarifications-tbody');
  if (!tbody) return;
  tbody.innerHTML = '<tr><td colspan="5" class="ap-table-empty"><div class="ap-spinner ap-spinner-sm"></div></td></tr>';
  try {
    const data = await apiFetch('/v2/api/comms/clarifications');
    const items = data.clarifications || [];

    const badge = document.getElementById('tab-badge-clarifications');
    if (badge) badge.textContent = items.length || '';

    if (items.length === 0) {
      tbody.innerHTML = '<tr><td colspan="5" class="ap-table-empty">No pending clarifications</td></tr>';
      return;
    }
    COMMS_STATE.clarifications = items;
    tbody.innerHTML = items.map((c, i) => {
      let missing = [];
      try { missing = JSON.parse(c.missing_fields || '[]'); } catch(_) {}
      return `
        <tr>
          <td>${escapeHtml(c.customer_email || '—')}</td>
          <td>${missing.map(f => `<span class="ap-badge ap-badge-amber">${escapeHtml(f)}</span>`).join(' ')}</td>
          <td class="ap-text-muted">${relativeTime(c.created_at)}</td>
          <td><span class="ap-badge">${c.attempt_count || 0}</span></td>
          <td>
            <button class="ap-btn ap-btn-ghost ap-btn-xs" data-action="clar-detail" data-idx="${i}">View</button>
          </td>
        </tr>
      `;
    }).join('');
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="5" class="ap-table-empty ap-text-danger">${escapeHtml(e.message)}</td></tr>`;
  }
}

function showClarificationDetail(c) {
  let missing = [];
  try { missing = JSON.parse(c.missing_fields || '[]'); } catch(_) {}
  showModal('Clarification Details', `
    <div class="ap-info-row"><span class="ap-info-label">Customer</span><span>${escapeHtml(c.customer_email || '—')}</span></div>
    <div class="ap-info-row"><span class="ap-info-label">Missing</span>
      <span>${missing.map(f => `<span class="ap-badge ap-badge-amber">${escapeHtml(f)}</span>`).join(' ')}</span>
    </div>
    <div class="ap-info-row"><span class="ap-info-label">Attempts</span><span>${c.attempt_count || 0}</span></div>
    <div class="ap-info-row"><span class="ap-info-label">Created</span><span>${relativeTime(c.created_at)}</span></div>
    <div class="ap-info-row"><span class="ap-info-label">Thread ID</span><span class="ap-text-muted" style="font-size:12px">${escapeHtml(c.thread_id || '—')}</span></div>
  `);
}

// ─── Waitlist ─────────────────────────────────────────────────────────────────

async function loadWaitlist() {
  const tbody = document.getElementById('waitlist-tbody');
  if (!tbody) return;
  tbody.innerHTML = '<tr><td colspan="6" class="ap-table-empty"><div class="ap-spinner ap-spinner-sm"></div></td></tr>';
  try {
    const data = await apiFetch('/v2/api/comms/waitlist');
    const items = data.waitlist || [];

    const badge = document.getElementById('tab-badge-waitlist');
    if (badge) badge.textContent = items.length || '';

    if (items.length === 0) {
      tbody.innerHTML = '<tr><td colspan="6" class="ap-table-empty">Waitlist is empty</td></tr>';
      return;
    }
    tbody.innerHTML = items.map(w => `
      <tr>
        <td>
          <div>${escapeHtml(w.customer_name || w.customer_email)}</div>
          <div class="ap-text-muted" style="font-size:12px">${escapeHtml(w.customer_email)}</div>
        </td>
        <td>${escapeHtml(w.requested_date || '—')}</td>
        <td>${serviceLabel(w.service_type)}</td>
        <td>${w.rim_count || '—'}</td>
        <td class="ap-text-muted">${relativeTime(w.created_at)}</td>
        <td>
          ${!w.notified
            ? `<button class="ap-btn ap-btn-primary ap-btn-xs" data-action="waitlist-notify" data-id="${w.id}">Notify</button>`
            : '<span class="ap-badge ap-badge-green">Notified</span>'}
        </td>
      </tr>
    `).join('');
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="6" class="ap-table-empty ap-text-danger">${escapeHtml(e.message)}</td></tr>`;
  }
}

async function notifyWaitlistCustomer(id, btn) {
  btn.disabled = true;
  btn.textContent = 'Sending…';
  try {
    await apiFetch(`/v2/api/comms/waitlist/${id}/notify`, { method: 'POST' });
    showToast('Customer notified', 'success');
    await loadWaitlist();
  } catch (e) {
    showToast('Notify failed: ' + e.message, 'error');
    btn.disabled = false;
    btn.textContent = 'Notify';
  }
}

// ─── Manual SMS ───────────────────────────────────────────────────────────────

function updateSmsCount(textarea) {
  const el = document.getElementById('sms-char-count');
  if (el) el.textContent = `${textarea.value.length} / 160 characters`;
}

function clearSmsForm() {
  ['sms-to', 'sms-message', 'sms-booking-id'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.value = '';
  });
  const countEl = document.getElementById('sms-char-count');
  if (countEl) countEl.textContent = '0 / 160 characters';
}

async function sendManualSms() {
  const to = (document.getElementById('sms-to')?.value || '').trim();
  const message = (document.getElementById('sms-message')?.value || '').trim();
  const booking_id = (document.getElementById('sms-booking-id')?.value || '').trim();

  if (!to || !message) {
    showToast('Phone number and message are required', 'warning');
    return;
  }

  const sendBtn = document.querySelector('#comms-sms .ap-btn-primary');
  if (sendBtn) { sendBtn.disabled = true; sendBtn.textContent = 'Sending…'; }

  try {
    const body = { to, message };
    if (booking_id) body.booking_id = booking_id;
    const result = await apiFetch('/v2/api/comms/sms', { method: 'POST', body: JSON.stringify(body) });
    if (result.ok === false) throw new Error(result.error || 'Send failed');
    showToast('SMS sent successfully!', 'success');
    clearSmsForm();
    await loadSmsLog();
  } catch (e) {
    showToast('SMS failed: ' + e.message, 'error');
  } finally {
    if (sendBtn) { sendBtn.disabled = false; sendBtn.textContent = 'Send SMS'; }
  }
}

async function loadSmsLog() {
  const tbody = document.getElementById('sms-log-tbody');
  if (!tbody) return;
  tbody.innerHTML = '<tr><td colspan="4" class="ap-table-empty"><div class="ap-spinner ap-spinner-sm"></div></td></tr>';
  try {
    const data = await apiFetch('/v2/api/comms/sms/log?limit=20');
    const logs = data.logs || [];
    if (logs.length === 0) {
      tbody.innerHTML = '<tr><td colspan="4" class="ap-table-empty">No outbound SMS yet</td></tr>';
      return;
    }
    tbody.innerHTML = logs.map(s => `
      <tr>
        <td>${escapeHtml(s.to || '—')}</td>
        <td class="ap-text-muted" style="max-width:280px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${escapeHtml(s.message || '—')}</td>
        <td class="ap-text-muted">${relativeTime(s.sent_at)}</td>
        <td><span class="ap-badge ${s.status === 'delivered' ? 'ap-badge-green' : s.status === 'failed' ? 'ap-badge-red' : 'ap-badge-amber'}">${escapeHtml(s.status || 'sent')}</span></td>
      </tr>
    `).join('');
  } catch (_) {
    tbody.innerHTML = '<tr><td colspan="4" class="ap-table-empty ap-text-muted">SMS log unavailable</td></tr>';
  }
}
// ─── End of Communications Section ───────────────────────────────────────────
"""
