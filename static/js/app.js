import dashboard  from './modules/dashboard.js';
import extensions from './modules/extensions.js';
import polycom    from './modules/polycom.js';
import calls      from './modules/calls.js';
import monitoring from './modules/monitoring.js';

// ------------------------------------------------------------------ //
// Module registry                                                      //
// ------------------------------------------------------------------ //

const MODULES = {
  dashboard,
  extensions,
  polycom,
  calls,
  monitoring,
};

// Placeholder modules for sections not yet fully implemented
const placeholder = (title) => ({
  render(container) {
    container.innerHTML = `
      <div class="page-section active">
        <div class="section-header">
          <div class="section-title">${title}</div>
        </div>
        <div class="empty-state">
          <div class="empty-icon">🚧</div>
          <p>Coming soon</p>
        </div>
      </div>
    `;
  },
  destroy() {},
});

MODULES.routing  = placeholder('Routing / Dialplan');
MODULES.features = placeholder('Feature Codes');
MODULES.cdr      = placeholder('Call History (CDR)');
MODULES.config   = placeholder('Configuration');

// ------------------------------------------------------------------ //
// SPA Router                                                           //
// ------------------------------------------------------------------ //

let activeModule = null;
const content = document.getElementById('content');

function navigate(hash) {
  const section = (hash || '#dashboard').replace('#', '');
  const mod = MODULES[section] || MODULES.dashboard;

  // Update sidebar active state
  document.querySelectorAll('#sidebar nav a').forEach(a => {
    a.classList.toggle('active', a.getAttribute('href') === `#${section}`);
  });

  if (activeModule?.destroy) activeModule.destroy();
  activeModule = mod;
  content.innerHTML = '';
  mod.render(content);
}

window.addEventListener('hashchange', () => navigate(location.hash));

// ------------------------------------------------------------------ //
// Sidebar toggle                                                       //
// ------------------------------------------------------------------ //

document.getElementById('sidebar-toggle').addEventListener('click', () => {
  document.getElementById('app').classList.toggle('sidebar-collapsed');
});

// ------------------------------------------------------------------ //
// WebSocket — AMI event stream                                         //
// ------------------------------------------------------------------ //

let ws = null;
let wsReconnectDelay = 1000;

function connectWS() {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  ws = new WebSocket(`${proto}://${location.host}/ws/events`);

  ws.onopen = () => {
    wsReconnectDelay = 1000;
    setAMIStatus(true);
  };

  ws.onmessage = (e) => {
    try {
      const event = JSON.parse(e.data);
      if (activeModule?.onAMIEvent) activeModule.onAMIEvent(event);
    } catch (_) {}
  };

  ws.onclose = () => {
    setAMIStatus(false);
    setTimeout(connectWS, wsReconnectDelay);
    wsReconnectDelay = Math.min(wsReconnectDelay * 2, 30000);
  };

  ws.onerror = () => ws.close();
}

function setAMIStatus(connected) {
  const dot = document.getElementById('ami-dot');
  const label = document.getElementById('ami-label');
  if (dot) dot.className = `${connected ? 'connected' : ''}`;
  if (label) label.textContent = connected ? 'AMI Connected' : 'AMI Offline';
}

// ------------------------------------------------------------------ //
// Clock                                                                //
// ------------------------------------------------------------------ //

function updateClock() {
  const el = document.getElementById('header-clock');
  if (el) el.textContent = new Date().toLocaleTimeString();
}
setInterval(updateClock, 1000);
updateClock();

// ------------------------------------------------------------------ //
// Boot                                                                 //
// ------------------------------------------------------------------ //

navigate(location.hash || '#dashboard');
connectWS();
