import { apiFetch, badgeHtml, escapeHtml, renderEmpty, renderLoading, showModal, showToast } from './common.js';

let _interval = null;

async function render(container) {
  container.innerHTML = `
    <div class="page-section active">
      <div class="section-header">
        <div>
          <div class="section-title">Active Calls</div>
          <div class="section-subtitle">Live channel overview (auto-refresh every 5s)</div>
        </div>
        <button class="btn btn-secondary btn-sm" id="calls-refresh">↻ Refresh</button>
      </div>
      <div class="table-wrapper">
        <div class="table-scroll">
          <table>
            <thead><tr>
              <th>Channel</th><th>Context</th><th>Extension</th><th>State</th><th>Application</th><th>Actions</th>
            </tr></thead>
            <tbody id="calls-tbody">${renderLoading(6)}</tbody>
          </table>
        </div>
      </div>
    </div>
  `;
  document.getElementById('calls-refresh').addEventListener('click', loadCalls);
  await loadCalls();
  _interval = setInterval(loadCalls, 5000);
}

async function loadCalls() {
  const tbody = document.getElementById('calls-tbody');
  if (!tbody) return;
  try {
    const channels = await apiFetch('/api/calls/');
    if (!channels.length) { tbody.innerHTML = renderEmpty('No active calls', 6); return; }
    tbody.innerHTML = channels.map(ch => `
      <tr>
        <td style="font-size:11px"><code>${escapeHtml(ch.channel || '—')}</code></td>
        <td>${escapeHtml(ch.context || '—')}</td>
        <td>${escapeHtml(ch.extension || '—')}</td>
        <td>${badgeHtml(ch.state || 'Unknown', ch.state)}</td>
        <td>${escapeHtml(ch.app || '—')}</td>
        <td>
          <button class="btn btn-sm btn-danger" onclick="window._callHangup('${escapeHtml(ch.channel || '')}')">Hang up</button>
        </td>
      </tr>
    `).join('');
  } catch (e) {
    tbody.innerHTML = renderEmpty(`Error: ${e.message}`, 6);
  }
}

window._callHangup = (channel) => {
  showModal({
    title: 'Hang Up',
    bodyHTML: `<p>Hang up channel <code>${escapeHtml(channel)}</code>?</p>`,
    confirmLabel: 'Hang Up',
    danger: true,
    onConfirm: async () => {
      await apiFetch(`/api/calls/${encodeURIComponent(channel)}/hangup`, { method: 'POST' });
      showToast('Hangup sent', 'success');
      await loadCalls();
    },
  });
};

export function onAMIEvent(event) {
  if (['Newchannel', 'Hangup', 'DialBegin', 'DialEnd'].includes(event.Event)) {
    loadCalls();
  }
}

function destroy() {
  clearInterval(_interval);
  _interval = null;
  delete window._callHangup;
}

export default { render, destroy, onAMIEvent };
