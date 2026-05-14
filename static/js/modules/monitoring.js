import { apiFetch, badgeHtml, escapeHtml, formatDateTime, showToast } from './common.js';

let _eventLines = [];
const MAX_EVENTS = 200;

async function render(container) {
  container.innerHTML = `
    <div class="page-section active">
      <div class="section-header">
        <div>
          <div class="section-title">Monitoring</div>
          <div class="section-subtitle">AMI events, logs, and diagnostics</div>
        </div>
      </div>
      <div class="tabs">
        <button class="tab-btn active" data-tab="events">AMI Events</button>
        <button class="tab-btn" data-tab="logs">App Logs</button>
        <button class="tab-btn" data-tab="diag">Diagnostics</button>
      </div>
      <div class="tab-content active" id="tab-events">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
          <span style="font-size:12px;color:var(--color-text-muted)">
            Live AMI event stream — <span id="event-count">0</span> events
          </span>
          <button class="btn btn-secondary btn-sm" id="clear-events">Clear</button>
        </div>
        <div class="event-stream" id="event-stream"></div>
      </div>
      <div class="tab-content" id="tab-logs">
        <div style="display:flex;gap:8px;margin-bottom:12px;flex-wrap:wrap">
          <select id="log-level" style="width:auto">
            <option value="">All levels</option>
            <option value="ERROR">ERROR</option>
            <option value="WARNING">WARNING</option>
            <option value="INFO">INFO</option>
          </select>
          <select id="log-module" style="width:auto">
            <option value="">All modules</option>
            <option value="extensions">Extensions</option>
            <option value="polycom">Polycom</option>
            <option value="features">Features</option>
          </select>
          <button class="btn btn-secondary btn-sm" id="log-refresh">↻ Refresh</button>
        </div>
        <div class="table-wrapper">
          <div class="table-scroll" style="max-height:400px">
            <table>
              <thead><tr><th>Time</th><th>Level</th><th>Module</th><th>Message</th></tr></thead>
              <tbody id="log-tbody"></tbody>
            </table>
          </div>
        </div>
      </div>
      <div class="tab-content" id="tab-diag">
        <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px">
          <button class="btn btn-secondary btn-sm" onclick="window._diagRun('core show uptime')">Uptime</button>
          <button class="btn btn-secondary btn-sm" onclick="window._diagRun('pjsip show endpoints')">PJSIP Endpoints</button>
          <button class="btn btn-secondary btn-sm" onclick="window._diagRun('dialplan show')">Dialplan</button>
          <button class="btn btn-secondary btn-sm" onclick="window._diagRun('core show channels concise')">Active Channels</button>
        </div>
        <pre id="diag-output" style="background:#050d14;padding:12px;border-radius:6px;font-size:12px;overflow:auto;max-height:400px;color:var(--color-accent);white-space:pre-wrap">Select a diagnostic command above…</pre>
      </div>
    </div>
  `;

  // Tab switching
  container.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      container.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      container.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
      btn.classList.add('active');
      document.getElementById(`tab-${btn.dataset.tab}`).classList.add('active');
      if (btn.dataset.tab === 'logs') loadLogs();
    });
  });

  document.getElementById('clear-events').addEventListener('click', () => {
    _eventLines = [];
    document.getElementById('event-stream').innerHTML = '';
    document.getElementById('event-count').textContent = '0';
  });
  document.getElementById('log-refresh').addEventListener('click', loadLogs);

  window._diagRun = async (cmd) => {
    const out = document.getElementById('diag-output');
    out.textContent = `Running: ${cmd}…`;
    try {
      const r = await apiFetch(`/api/monitoring/diag?cmd=${encodeURIComponent(cmd)}`);
      out.textContent = r.output.join('\n') || '(no output)';
    } catch (e) {
      out.textContent = `Error: ${e.message}`;
    }
  };

  await loadLogs();
}

async function loadLogs() {
  const tbody = document.getElementById('log-tbody');
  if (!tbody) return;
  const level = document.getElementById('log-level')?.value || '';
  const module = document.getElementById('log-module')?.value || '';
  try {
    const params = new URLSearchParams();
    if (level) params.set('level', level);
    if (module) params.set('module', module);
    const logs = await apiFetch(`/api/monitoring/logs?${params}`);
    if (!logs.length) { tbody.innerHTML = '<tr><td colspan="4" style="text-align:center;color:var(--color-text-muted)">No logs</td></tr>'; return; }
    tbody.innerHTML = logs.map(l => `
      <tr>
        <td style="font-size:11px;white-space:nowrap">${formatDateTime(l.timestamp)}</td>
        <td>${badgeHtml(l.level || '—', l.level?.toLowerCase())}</td>
        <td style="font-size:11px">${escapeHtml(l.module || '—')}</td>
        <td style="font-size:12px">${escapeHtml(l.message || '—')}</td>
      </tr>
    `).join('');
  } catch (e) {
    showToast(e.message, 'error');
  }
}

export function onAMIEvent(event) {
  const stream = document.getElementById('event-stream');
  if (!stream) return;

  _eventLines.unshift(event);
  if (_eventLines.length > MAX_EVENTS) _eventLines.pop();

  const line = document.createElement('div');
  line.className = `event-line ${escapeHtml(event.Event || '')}`;
  const ts = new Date().toLocaleTimeString();
  const keys = Object.entries(event).map(([k, v]) => `${k}: ${v}`).join(' | ');
  line.textContent = `[${ts}] ${keys}`;
  stream.prepend(line);

  const countEl = document.getElementById('event-count');
  if (countEl) countEl.textContent = _eventLines.length;
}

function destroy() {
  delete window._diagRun;
}

export default { render, destroy, onAMIEvent };
