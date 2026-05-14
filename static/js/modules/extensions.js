import { apiFetch, badgeHtml, escapeHtml, formatDateTime, renderEmpty, renderLoading, showModal, showToast, validateExtension } from './common.js';

let _container = null;

async function render(container) {
  _container = container;
  container.innerHTML = `
    <div class="page-section active">
      <div class="section-header">
        <div>
          <div class="section-title">Extensions</div>
          <div class="section-subtitle">PJSIP endpoint management</div>
        </div>
        <button class="btn btn-primary" id="ext-add-btn">+ Add Extension</button>
      </div>
      <div class="table-wrapper">
        <div class="table-toolbar">
          <input type="search" id="ext-search" placeholder="Search extension…" style="max-width:220px">
        </div>
        <div class="table-scroll">
          <table>
            <thead><tr>
              <th>Extension</th><th>Name</th><th>Context</th><th>State</th><th>Actions</th>
            </tr></thead>
            <tbody id="ext-tbody">${renderLoading(5)}</tbody>
          </table>
        </div>
      </div>
    </div>
  `;
  document.getElementById('ext-add-btn').addEventListener('click', () => openForm());
  document.getElementById('ext-search').addEventListener('input', filterTable);
  await loadExtensions();
}

async function loadExtensions() {
  const tbody = document.getElementById('ext-tbody');
  if (!tbody) return;
  tbody.innerHTML = renderLoading(5);
  try {
    const exts = await apiFetch('/api/extensions/');
    renderTable(exts);
  } catch (e) {
    tbody.innerHTML = renderEmpty(`Error: ${e.message}`, 5);
    showToast(e.message, 'error');
  }
}

function renderTable(exts) {
  const tbody = document.getElementById('ext-tbody');
  if (!tbody) return;
  if (!exts.length) { tbody.innerHTML = renderEmpty('No extensions configured', 5); return; }
  tbody.innerHTML = exts.map(ext => `
    <tr data-search="${escapeHtml((ext.number + ' ' + (ext.name || '')).toLowerCase())}">
      <td><code>${escapeHtml(ext.number)}</code></td>
      <td>${escapeHtml(ext.name || '—')}</td>
      <td><code style="font-size:11px">${escapeHtml(ext.context || '')}</code></td>
      <td>${badgeHtml(ext.state || 'Unknown', ext.state)}</td>
      <td style="white-space:nowrap">
        <button class="btn btn-icon btn-sm" onclick="window._extEdit('${escapeHtml(ext.number)}')">✏</button>
        <button class="btn btn-icon btn-sm" style="color:var(--color-danger)" onclick="window._extDelete('${escapeHtml(ext.number)}')">🗑</button>
        <button class="btn btn-icon btn-sm" title="Test call" onclick="window._extTest('${escapeHtml(ext.number)}')">📞</button>
      </td>
    </tr>
  `).join('');
}

function filterTable() {
  const q = document.getElementById('ext-search').value.toLowerCase();
  document.querySelectorAll('#ext-tbody tr[data-search]').forEach(row => {
    row.style.display = row.dataset.search.includes(q) ? '' : 'none';
  });
}

function openForm(ext = null) {
  const isEdit = !!ext;
  const bodyHTML = `
    <div class="form-group">
      <label class="form-label">Extension Number</label>
      <input id="f-number" type="text" placeholder="e.g. 1001" value="${escapeHtml(ext?.number || '')}" ${isEdit ? 'readonly' : ''}>
    </div>
    <div class="form-group">
      <label class="form-label">Display Name</label>
      <input id="f-name" type="text" placeholder="Alice Smith" value="${escapeHtml(ext?.name || '')}">
    </div>
    <div class="form-group">
      <label class="form-label">SIP Password</label>
      <input id="f-password" type="text" placeholder="Secret" value="${escapeHtml(ext?.password || '')}">
    </div>
    <div class="form-group">
      <label class="form-label">Context</label>
      <input id="f-context" type="text" placeholder="from-internal" value="${escapeHtml(ext?.context || 'from-internal')}">
    </div>
  `;
  showModal({
    title: isEdit ? `Edit Extension ${ext.number}` : 'Add Extension',
    bodyHTML,
    confirmLabel: isEdit ? 'Save' : 'Create',
    onConfirm: async () => {
      const number = document.getElementById('f-number').value.trim();
      const name = document.getElementById('f-name').value.trim();
      const password = document.getElementById('f-password').value.trim();
      const context = document.getElementById('f-context').value.trim() || 'from-internal';

      if (!validateExtension(number)) throw new Error('Extension must be 3–6 digits');
      if (!password) throw new Error('Password is required');

      if (isEdit) {
        await apiFetch(`/api/extensions/${number}`, {
          method: 'PUT',
          body: { name, password, context },
        });
        showToast(`Extension ${number} updated`, 'success');
      } else {
        await apiFetch('/api/extensions/', {
          method: 'POST',
          body: { number, name, password, context },
        });
        showToast(`Extension ${number} created`, 'success');
      }
      await loadExtensions();
    },
  });
}

window._extEdit = async (number) => {
  try {
    const ext = await apiFetch(`/api/extensions/${number}`);
    openForm(ext);
  } catch (e) { showToast(e.message, 'error'); }
};

window._extDelete = (number) => {
  showModal({
    title: `Delete Extension ${number}`,
    bodyHTML: `<p>This will remove extension <strong>${escapeHtml(number)}</strong> from pjsip.conf and reload Asterisk.</p>`,
    confirmLabel: 'Delete',
    danger: true,
    onConfirm: async () => {
      await apiFetch(`/api/extensions/${number}`, { method: 'DELETE' });
      showToast(`Extension ${number} deleted`, 'success');
      await loadExtensions();
    },
  });
};

window._extTest = (number) => {
  const dest = prompt(`Test call from ${number} to extension:`);
  if (!dest) return;
  apiFetch(`/api/extensions/${number}/test?to=${encodeURIComponent(dest)}`, { method: 'POST' })
    .then(() => showToast('Test call originated', 'success'))
    .catch(e => showToast(e.message, 'error'));
};

function destroy() {
  _container = null;
  delete window._extEdit;
  delete window._extDelete;
  delete window._extTest;
}

export default { render, destroy };
