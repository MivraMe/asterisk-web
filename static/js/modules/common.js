// Shared utilities: API client, toast, modal, validators

// ------------------------------------------------------------------ //
// API fetch wrapper                                                    //
// ------------------------------------------------------------------ //

export async function apiFetch(path, opts = {}) {
  const url = path.startsWith('/') ? path : `/api/${path}`;
  const res = await fetch(url, {
    headers: { 'Content-Type': 'application/json', ...(opts.headers || {}) },
    ...opts,
    body: opts.body ? (typeof opts.body === 'string' ? opts.body : JSON.stringify(opts.body)) : undefined,
  });
  if (!res.ok) {
    let msg = `HTTP ${res.status}`;
    try {
      const data = await res.json();
      msg = data.detail || data.message || msg;
    } catch (_) {}
    throw new Error(msg);
  }
  const ct = res.headers.get('content-type') || '';
  if (ct.includes('application/json')) return res.json();
  return res.text();
}

// ------------------------------------------------------------------ //
// Toast notifications                                                  //
// ------------------------------------------------------------------ //

const ICONS = { success: '✓', error: '✗', warning: '⚠', info: 'ℹ' };

export function showToast(message, type = 'info', duration = 3500) {
  const container = document.getElementById('toast-container');
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  toast.innerHTML = `
    <span class="toast-icon">${ICONS[type] || 'ℹ'}</span>
    <span class="toast-msg">${escapeHtml(message)}</span>
    <span class="toast-close" role="button" aria-label="Close">×</span>
  `;
  const close = () => {
    toast.classList.add('removing');
    toast.addEventListener('animationend', () => toast.remove(), { once: true });
  };
  toast.querySelector('.toast-close').addEventListener('click', close);
  container.appendChild(toast);
  setTimeout(close, duration);
}

// ------------------------------------------------------------------ //
// Modal                                                                //
// ------------------------------------------------------------------ //

export function showModal({ title, bodyHTML, onConfirm, confirmLabel = 'Confirm', danger = false }) {
  const overlay = document.getElementById('modal-overlay');
  const modalTitle = document.getElementById('modal-title');
  const modalBody = document.getElementById('modal-body');
  const confirmBtn = document.getElementById('modal-confirm');
  const cancelBtn = document.getElementById('modal-cancel');

  modalTitle.textContent = title;
  modalBody.innerHTML = bodyHTML;
  confirmBtn.textContent = confirmLabel;
  confirmBtn.className = `btn ${danger ? 'btn-danger' : 'btn-primary'}`;

  const close = () => overlay.classList.remove('open');
  confirmBtn.onclick = async () => {
    if (onConfirm) {
      try { await onConfirm(); } catch (e) { showToast(e.message, 'error'); }
    }
    close();
  };
  cancelBtn.onclick = close;
  overlay.onclick = (e) => { if (e.target === overlay) close(); };

  overlay.classList.add('open');
  return close;
}

// ------------------------------------------------------------------ //
// Validators                                                           //
// ------------------------------------------------------------------ //

export function validateMAC(str) {
  const clean = str.replace(/[:\-\.]/g, '').toLowerCase();
  return /^[0-9a-f]{12}$/.test(clean);
}

export function validateExtension(str) {
  return /^\d{3,6}$/.test(str.trim());
}

export function validateIP(str) {
  return /^(\d{1,3}\.){3}\d{1,3}$/.test(str.trim());
}

// ------------------------------------------------------------------ //
// Helpers                                                              //
// ------------------------------------------------------------------ //

export function escapeHtml(str) {
  const d = document.createElement('div');
  d.textContent = String(str);
  return d.innerHTML;
}

export function formatDateTime(iso) {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleString();
  } catch (_) { return iso; }
}

export function formatDuration(seconds) {
  if (seconds == null) return '—';
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${String(s).padStart(2, '0')}`;
}

export function badgeHtml(text, variant) {
  const variantMap = {
    // Asterisk PJSIP states (normalized by CLI parser)
    Available: 'badge-ok',
    'In Use': 'badge-active',
    'On Hold': 'badge-warning',
    Ringing: 'badge-info',
    Unavailable: 'badge-unavailable',
    Unknown: 'badge-unknown',
    // Legacy / raw Asterisk states (fallback)
    Up: 'badge-ok', up: 'badge-ok',
    unavailable: 'badge-unavailable',
    unknown: 'badge-unknown',
    // App-level statuses
    ok: 'badge-ok',
    orphan: 'badge-warning',
    active: 'badge-active',
    error: 'badge-error',
    pending: 'badge-pending',
    completed: 'badge-ok',
    failed: 'badge-error',
  };
  const cls = variantMap[text] || variantMap[variant] || 'badge-pending';
  return `<span class="badge ${cls}">${escapeHtml(text)}</span>`;
}

export function renderLoading(colSpan = 6) {
  return `<tr class="loading-row"><td colspan="${colSpan}"><div class="spinner"></div> Loading…</td></tr>`;
}

export function renderEmpty(msg = 'No data', colSpan = 6) {
  return `<tr class="loading-row"><td colspan="${colSpan}">${escapeHtml(msg)}</td></tr>`;
}
