import { apiFetch, badgeHtml, escapeHtml, formatDateTime, renderEmpty, renderLoading, showModal, showToast, validateIP, validateMAC } from './common.js';

async function render(container) {
  container.innerHTML = `
    <div class="page-section active">
      <div class="section-header">
        <div>
          <div class="section-title">Polycom Provisioning</div>
          <div class="section-subtitle">Device configuration management</div>
        </div>
        <div style="display:flex;gap:8px">
          <button class="btn btn-secondary" id="poly-site-btn">⚙ Site Config</button>
          <button class="btn btn-secondary" id="poly-sync-btn">🔄 Sync IP</button>
          <button class="btn btn-primary" id="poly-add-btn">+ Add Device</button>
        </div>
      </div>
      <div class="table-wrapper">
        <div class="table-toolbar">
          <input type="search" id="poly-search" placeholder="Search MAC / extension…" style="max-width:240px">
          <span id="poly-status-badge"></span>
        </div>
        <div class="table-scroll">
          <table>
            <thead><tr>
              <th>MAC Address</th><th>Extension</th><th>Model</th><th>Asterisk IP</th><th>Status</th><th>Last Provision</th><th>Actions</th>
            </tr></thead>
            <tbody id="poly-tbody">${renderLoading(7)}</tbody>
          </table>
        </div>
      </div>
    </div>
  `;

  document.getElementById('poly-add-btn').addEventListener('click', () => openDeviceForm());
  document.getElementById('poly-site-btn').addEventListener('click', openSiteConfig);
  document.getElementById('poly-sync-btn').addEventListener('click', openSyncIP);
  document.getElementById('poly-search').addEventListener('input', filterTable);

  await loadDevices();
}

async function loadDevices() {
  const tbody = document.getElementById('poly-tbody');
  if (!tbody) return;
  tbody.innerHTML = renderLoading(7);
  try {
    const [devices, status] = await Promise.all([
      apiFetch('/api/polycom/devices'),
      apiFetch('/api/polycom/status'),
    ]);
    const badge = document.getElementById('poly-status-badge');
    if (badge) badge.innerHTML = `${badgeHtml(status.provisioned_ok + ' OK', 'ok')} ${badgeHtml(status.errors + ' errors', status.errors > 0 ? 'error' : 'ok')}`;
    renderDeviceTable(devices);
  } catch (e) {
    tbody.innerHTML = renderEmpty(`Error: ${e.message}`, 7);
    showToast(e.message, 'error');
  }
}

function renderDeviceTable(devices) {
  const tbody = document.getElementById('poly-tbody');
  if (!tbody) return;
  if (!devices.length) { tbody.innerHTML = renderEmpty('No devices provisioned', 7); return; }
  tbody.innerHTML = devices.map(d => {
    const extLabel = d.extension_number || (d.extension_id ? String(d.extension_id) : '—');
    const editBtn = d.provisioning_status === 'orphan'
      ? `<button class="btn btn-icon btn-sm btn-secondary" onclick="window._polyAdopt('${escapeHtml(d.mac_address)}')" title="Add to database">➕</button>`
      : `<button class="btn btn-icon btn-sm" onclick="window._polyEdit('${escapeHtml(d.mac_address)}')">✏</button>`;
    return `
    <tr data-search="${escapeHtml((d.mac_address + ' ' + extLabel).toLowerCase())}">
      <td><code>${escapeHtml(formatMAC(d.mac_address))}</code></td>
      <td>${escapeHtml(extLabel)}</td>
      <td>${escapeHtml(d.model || '—')}</td>
      <td><code>${escapeHtml(d.asterisk_ip || '—')}</code></td>
      <td>${badgeHtml(d.provisioning_status || 'unknown', d.provisioning_status)}</td>
      <td style="font-size:11px">${formatDateTime(d.last_provision)}</td>
      <td style="white-space:nowrap">
        ${editBtn}
        <button class="btn btn-icon btn-sm" style="color:var(--color-danger)" onclick="window._polyDelete('${escapeHtml(d.mac_address)}')">🗑</button>
        <a class="btn btn-icon btn-sm" href="/polycom/${escapeHtml(d.mac_address)}.cfg" target="_blank" title="View config">📄</a>
      </td>
    </tr>`;
  }).join('');
}

function filterTable() {
  const q = document.getElementById('poly-search').value.toLowerCase();
  document.querySelectorAll('#poly-tbody tr[data-search]').forEach(row => {
    row.style.display = row.dataset.search.includes(q) ? '' : 'none';
  });
}

function formatMAC(mac) {
  if (mac.length !== 12) return mac;
  return mac.replace(/(.{2})(?=.)/g, '$1:');
}

async function openDeviceForm(device = null) {
  let extensions = [];
  try { extensions = await apiFetch('/api/extensions/'); } catch (_) {}

  const isEdit = !!device;
  // Use extension_number (SIP string) for comparison, not extension_id (DB int)
  const currentExt = device?.extension_number || null;
  const placeholder = `<option value="" disabled ${currentExt ? '' : 'selected'}>— Select extension —</option>`;
  const extOptions = placeholder + extensions.map(e =>
    `<option value="${escapeHtml(e.number)}" ${currentExt === e.number ? 'selected' : ''}>${escapeHtml(e.number)} — ${escapeHtml(e.name || '')}</option>`
  ).join('');

  const bodyHTML = `
    <div class="form-group">
      <label class="form-label">MAC Address</label>
      <input id="f-mac" type="text" placeholder="00:04:f2:xx:xx:xx" value="${escapeHtml(device?.mac_address ? formatMAC(device.mac_address) : '')}" ${isEdit ? 'readonly' : ''}>
    </div>
    <div class="form-group">
      <label class="form-label">Extension</label>
      <select id="f-ext">${extOptions}</select>
    </div>
    <div class="form-group">
      <label class="form-label">Model</label>
      <input id="f-model" type="text" placeholder="VVX250" value="${escapeHtml(device?.model || 'VVX250')}">
    </div>
    <div class="form-group">
      <label class="form-label">Asterisk IP (leave blank for default)</label>
      <input id="f-astip" type="text" placeholder="192.168.0.107" value="${escapeHtml(device?.asterisk_ip || '')}">
    </div>
  `;

  showModal({
    title: isEdit ? `Edit Device ${device.mac_address}` : 'Add Polycom Device',
    bodyHTML,
    confirmLabel: isEdit ? 'Save' : 'Create',
    onConfirm: async () => {
      const mac = document.getElementById('f-mac').value.trim();
      const ext = document.getElementById('f-ext').value.trim();
      const model = document.getElementById('f-model').value.trim() || 'VVX250';
      const astip = document.getElementById('f-astip').value.trim() || null;

      if (!validateMAC(mac)) throw new Error('Invalid MAC address');
      if (!ext) throw new Error('Please select an extension');
      if (astip && !validateIP(astip)) throw new Error('Invalid IP address');

      if (isEdit) {
        await apiFetch(`/api/polycom/devices/${mac.replace(/[:\-]/g, '').toLowerCase()}`, {
          method: 'PUT',
          body: { extension_number: ext, model, asterisk_ip: astip },
        });
        showToast('Device updated', 'success');
      } else {
        await apiFetch('/api/polycom/devices', {
          method: 'POST',
          body: { mac_address: mac, extension_number: ext, model, asterisk_ip: astip },
        });
        showToast('Device provisioned', 'success');
      }
      await loadDevices();
    },
  });
}

window._polyEdit = async (mac) => {
  try {
    const d = await apiFetch(`/api/polycom/devices/${mac}`);
    openDeviceForm(d);
  } catch (e) { showToast(e.message, 'error'); }
};

// Open the Add form pre-filled with the orphan MAC so the user can assign an extension
window._polyAdopt = (mac) => {
  openDeviceForm({ mac_address: mac, model: 'VVX250', asterisk_ip: '', extension_number: null });
};

window._polyDelete = (mac) => {
  showModal({
    title: 'Delete Device',
    bodyHTML: `<p>Remove device <strong>${escapeHtml(mac)}</strong> and its config file?</p>`,
    confirmLabel: 'Delete',
    danger: true,
    onConfirm: async () => {
      await apiFetch(`/api/polycom/devices/${mac}`, { method: 'DELETE' });
      showToast('Device deleted', 'success');
      await loadDevices();
    },
  });
};

async function openSiteConfig() {
  let cfg = {};
  try { cfg = await apiFetch('/api/polycom/config'); } catch (_) {}

  const bodyHTML = `
    <div class="form-group">
      <label class="form-label">Provisioning IP</label>
      <input id="sc-ip" type="text" value="${escapeHtml(cfg['device.prov.serverName'] || '192.168.0.107')}">
    </div>
    <div class="form-group">
      <label class="form-label">Provisioning User</label>
      <input id="sc-user" type="text" value="${escapeHtml(cfg['device.prov.user'] || 'admin')}">
    </div>
    <div class="form-group">
      <label class="form-label">Provisioning Password</label>
      <input id="sc-pw" type="password" value="">
    </div>
  `;
  showModal({
    title: 'Edit Site Config (site.cfg)',
    bodyHTML,
    confirmLabel: 'Save',
    onConfirm: async () => {
      const ip = document.getElementById('sc-ip').value.trim();
      const user = document.getElementById('sc-user').value.trim();
      const pw = document.getElementById('sc-pw').value;
      if (!validateIP(ip)) throw new Error('Invalid IP');
      await apiFetch('/api/polycom/config', {
        method: 'PUT',
        body: { provisioning_ip: ip, prov_user: user, prov_password: pw },
      });
      showToast('site.cfg updated', 'success');
    },
  });
}

async function openSyncIP() {
  const bodyHTML = `
    <p style="color:var(--color-warning);margin-bottom:12px">⚠ This will update the Asterisk IP in <strong>site.cfg</strong> and regenerate <strong>all</strong> device configs.</p>
    <div class="form-group">
      <label class="form-label">New Asterisk IP</label>
      <input id="sync-ip" type="text" placeholder="192.168.0.107">
    </div>
  `;
  showModal({
    title: 'Sync Asterisk IP Everywhere',
    bodyHTML,
    confirmLabel: 'Sync',
    danger: true,
    onConfirm: async () => {
      const ip = document.getElementById('sync-ip').value.trim();
      if (!validateIP(ip)) throw new Error('Invalid IP address');
      const result = await apiFetch('/api/polycom/config/sync-ip', {
        method: 'POST',
        body: { new_ip: ip },
      });
      showToast(`IP synced to ${ip} — ${result.devices_updated} devices updated`, 'success');
      await loadDevices();
    },
  });
}

function destroy() {
  delete window._polyEdit;
  delete window._polyDelete;
}

export default { render, destroy };
