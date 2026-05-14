import { apiFetch, badgeHtml, formatDateTime } from './common.js';

let _interval = null;

async function render(container) {
  container.innerHTML = `
    <div class="page-section active" id="sec-dashboard">
      <div class="section-header">
        <div>
          <div class="section-title">Dashboard</div>
          <div class="section-subtitle">System overview</div>
        </div>
        <button class="btn btn-secondary btn-sm" id="dash-refresh">↻ Refresh</button>
      </div>
      <div class="stats-grid" id="dash-stats">
        <div class="stat-card"><div class="spinner"></div></div>
      </div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;flex-wrap:wrap">
        <div class="card" id="dash-endpoints-card">
          <div class="card-header">Endpoints</div>
          <div id="dash-endpoints">Loading…</div>
        </div>
        <div class="card" id="dash-polycom-card">
          <div class="card-header">Polycom Devices</div>
          <div id="dash-polycom">Loading…</div>
        </div>
      </div>
    </div>
  `;
  document.getElementById('dash-refresh').addEventListener('click', load);
  await load();
  _interval = setInterval(load, 30000);
}

async function load() {
  try {
    const [status, stats, polyStatus] = await Promise.all([
      apiFetch('/api/monitoring/status'),
      apiFetch('/api/monitoring/stats'),
      apiFetch('/api/polycom/status'),
    ]);

    const statsEl = document.getElementById('dash-stats');
    if (!statsEl) return;
    statsEl.innerHTML = `
      <div class="stat-card">
        <div class="stat-value">${badgeHtml(status.ami_connected ? 'Online' : 'Offline', status.ami_connected ? 'ok' : 'error')}</div>
        <div class="stat-label">Asterisk AMI</div>
      </div>
      <div class="stat-card">
        <div class="stat-value" style="font-size:24px">${status.endpoint_count}</div>
        <div class="stat-label">Endpoints</div>
      </div>
      <div class="stat-card">
        <div class="stat-value" style="font-size:24px">${status.endpoints_up}</div>
        <div class="stat-label">Endpoints Up</div>
      </div>
      <div class="stat-card">
        <div class="stat-value" style="font-size:24px">${stats.active_calls}</div>
        <div class="stat-label">Active Calls</div>
      </div>
      <div class="stat-card">
        <div class="stat-value" style="font-size:24px">${stats.calls_today}</div>
        <div class="stat-label">Calls Today</div>
      </div>
      <div class="stat-card">
        <div class="stat-value" style="font-size:24px">${polyStatus.total_devices}</div>
        <div class="stat-label">Polycom Devices</div>
      </div>
    `;

    const uptime = status.uptime || {};
    const epsEl = document.getElementById('dash-endpoints');
    if (epsEl) {
      epsEl.innerHTML = `
        <table>
          <tr><td style="color:var(--color-text-muted)">System uptime</td><td>${uptime['System uptime'] || '—'}</td></tr>
          <tr><td style="color:var(--color-text-muted)">Last reload</td><td>${uptime['Last reload'] || '—'}</td></tr>
          <tr><td style="color:var(--color-text-muted)">Active calls</td><td>${stats.active_calls}</td></tr>
          <tr><td style="color:var(--color-text-muted)">Total calls</td><td>${stats.total_calls}</td></tr>
        </table>
      `;
    }
    const polyEl = document.getElementById('dash-polycom');
    if (polyEl) {
      polyEl.innerHTML = `
        <table>
          <tr><td style="color:var(--color-text-muted)">Total devices</td><td>${polyStatus.total_devices}</td></tr>
          <tr><td style="color:var(--color-text-muted)">Config files</td><td>${polyStatus.files_on_disk}</td></tr>
          <tr><td style="color:var(--color-text-muted)">Provisioned OK</td><td>${polyStatus.provisioned_ok}</td></tr>
          <tr><td style="color:var(--color-text-muted)">Errors</td><td>${polyStatus.errors}</td></tr>
        </table>
      `;
    }
  } catch (e) {
    const statsEl = document.getElementById('dash-stats');
    if (statsEl) statsEl.innerHTML = `<div class="stat-card"><div class="stat-label" style="color:var(--color-danger)">${e.message}</div></div>`;
  }
}

function destroy() {
  clearInterval(_interval);
  _interval = null;
}

export default { render, destroy };
