/* ── State ───────────────────────────────────────────────────────────────────── */

let currentUser   = '';
let chartCache    = {};   // tab → raw API response (cleared on refresh)
let minGamesValue = 5;

const isDark = () => window.matchMedia('(prefers-color-scheme: dark)').matches;

/* ── DOM refs ────────────────────────────────────────────────────────────────── */

const $ = id => document.getElementById(id);

const usernameInput = $('username-input');
const loadBtn       = $('load-btn');
const refreshBtn    = $('refresh-btn');
const kpiStrip      = $('kpi-strip');
const dashboard     = $('dashboard');
const emptyState    = $('empty-state');
const errorState    = $('error-state');
const errorMsg      = $('error-message');

/* ── Init ────────────────────────────────────────────────────────────────────── */

document.addEventListener('DOMContentLoaded', () => {
  const params = new URLSearchParams(window.location.search);
  const u = params.get('u') || 'sahas_etikyala';
  usernameInput.value = u;
  loadUser(u);

  loadBtn.addEventListener('click',   () => loadUser(usernameInput.value.trim()));
  refreshBtn.addEventListener('click', refreshData);
  usernameInput.addEventListener('keydown', e => {
    if (e.key === 'Enter') loadUser(usernameInput.value.trim());
  });

  // Tab switching
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => switchTab(btn.dataset.tab));
  });

  // Openings min-games slider
  const slider  = $('min-games-slider');
  const sliderV = $('min-games-val');
  let debounce;
  slider.addEventListener('input', () => {
    minGamesValue = parseInt(slider.value);
    sliderV.textContent = minGamesValue;
    clearTimeout(debounce);
    debounce = setTimeout(() => {
      delete chartCache['openings'];   // invalidate so next render re-fetches
      loadTab('openings');
    }, 400);
  });

  // H2H dropdown
  $('h2h-select').addEventListener('change', e => {
    if (e.target.value) loadH2H(e.target.value);
  });

  // Keep Plotly charts responsive on window resize
  window.addEventListener('resize', () => {
    document.querySelectorAll('.chart-card').forEach(card => {
      if (card.querySelector('.js-plotly-plot')) {
        Plotly.Plots.resize(card);
      }
    });
  });

  // Rerender on color scheme change (light ↔ dark)
  window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
    chartCache = {};
    const active = document.querySelector('.tab-btn.active')?.dataset.tab;
    if (active && currentUser) loadTab(active);
  });
});

/* ── Load user ───────────────────────────────────────────────────────────────── */

async function loadUser(username) {
  if (!username) return;
  currentUser = username.toLowerCase();
  chartCache  = {};

  showLoading();

  try {
    const summary = await apiFetch(`/api/${currentUser}/summary`);
    renderKPIs(summary);
    showDashboard();
    // Update URL without reload
    history.replaceState({}, '', `?u=${currentUser}`);
    // Load the currently active tab
    const activeTab = document.querySelector('.tab-btn.active')?.dataset.tab || 'overview';
    loadTab(activeTab);
  } catch (err) {
    showError(err.message);
  }
}

/* ── Refresh ─────────────────────────────────────────────────────────────────── */

async function refreshData() {
  if (!currentUser) return;
  refreshBtn.querySelector('svg').parentElement.classList.add('spinning');
  try {
    await apiFetch(`/api/${currentUser}/cache`, { method: 'DELETE' });
    chartCache = {};
    const activeTab = document.querySelector('.tab-btn.active')?.dataset.tab || 'overview';
    await loadUser(currentUser);
  } finally {
    refreshBtn.classList.remove('spinning');
  }
}

/* ── Tab switching ───────────────────────────────────────────────────────────── */

function switchTab(tab) {
  document.querySelectorAll('.tab-btn').forEach(b => {
    b.classList.toggle('active', b.dataset.tab === tab);
    b.setAttribute('aria-selected', b.dataset.tab === tab);
  });
  document.querySelectorAll('.tab-pane').forEach(p => {
    p.classList.toggle('active', p.id === `tab-${tab}`);
  });
  if (currentUser) loadTab(tab);
}

/* ── Load tab ────────────────────────────────────────────────────────────────── */

async function loadTab(tab) {
  if (chartCache[tab]) {
    renderTab(tab, chartCache[tab]);
    return;
  }

  const url = tab === 'openings'
    ? `/api/${currentUser}/charts/${tab}?min_games=${minGamesValue}`
    : `/api/${currentUser}/charts/${tab}`;

  try {
    const data = await apiFetch(url);
    chartCache[tab] = data;
    renderTab(tab, data);
  } catch (err) {
    console.error(`Failed to load tab ${tab}:`, err);
  }
}

/* ── Render tabs ─────────────────────────────────────────────────────────────── */

function renderTab(tab, data) {
  switch (tab) {
    case 'overview':  renderOverview(data);   break;
    case 'openings':  renderOpenings(data);   break;
    case 'time':      renderTime(data);       break;
    case 'opponents': renderOpponents(data);  break;
  }
}

function renderOverview(data) {
  renderChart('ch-rating-over-time', data.rating_over_time);
  renderChart('ch-volatility',       data.volatility);
  renderChart('ch-termination',      data.termination);
  renderChart('ch-accuracy',         data.accuracy);
}

function renderOpenings(data) {
  renderChart('ch-win-rate-opening', data.win_rate);
  renderChart('ch-repertoire',       data.repertoire);
  if (data.phase) renderChart('ch-phase', data.phase);
}

function renderTime(data) {
  renderChart('ch-time-class',    data.time_class);
  renderChart('ch-heatmap',       data.heatmap);
  if (data.game_length)   renderChart('ch-game-length',   data.game_length);
  if (data.clock_pattern) renderChart('ch-clock-pattern', data.clock_pattern);

  if (data.time_pressure) {
    const tp = data.time_pressure;
    $('tp-normal').textContent   = tp.avg_time_normal    != null ? tp.avg_time_normal.toFixed(1) + 's'    : '—';
    $('tp-pressure').textContent = tp.avg_time_under_pressure != null ? tp.avg_time_under_pressure.toFixed(1) + 's' : '—';
    $('tp-count').textContent    = tp.moves_under_pressure ?? '—';
    $('time-pressure-row').classList.remove('hidden');
  }
}

function renderOpponents(data) {
  renderChart('ch-rating-gap', data.rating_gap);

  if (data.comeback) {
    const cb = data.comeback;
    $('cb-games-down').textContent = cb.games_down ?? '—';
    $('cb-wins').textContent       = cb.comeback_wins ?? '—';
    $('cb-rate').textContent       = cb.comeback_rate != null ? (cb.comeback_rate * 100).toFixed(1) + '%' : '—';
    $('comeback-row').classList.remove('hidden');
  }

  if (data.top_opponents) {
    renderTopOpponentsTable(data.top_opponents);
  }

  if (data.opponent_list) {
    const sel = $('h2h-select');
    sel.innerHTML = '<option value="">Select an opponent…</option>';
    data.opponent_list.forEach(opp => {
      const opt = document.createElement('option');
      opt.value = opp;
      opt.textContent = opp;
      sel.appendChild(opt);
    });
  }
}

/* ── H2H ─────────────────────────────────────────────────────────────────────── */

async function loadH2H(opponent) {
  try {
    const data = await apiFetch(`/api/${currentUser}/h2h/${encodeURIComponent(opponent)}`);
    $('h2h-wins').textContent   = data.wins;
    $('h2h-losses').textContent = data.losses;
    $('h2h-draws').textContent  = data.draws;
    $('h2h-metrics').classList.remove('hidden');
    renderGamesTable('h2h-table', data.games);
  } catch (err) {
    console.error('H2H fetch failed:', err);
  }
}

/* ── Chart rendering ─────────────────────────────────────────────────────────── */

function renderChart(divId, figData) {
  if (!figData) return;
  const el = $(divId);
  if (!el) return;

  // Clear skeleton
  el.innerHTML = '';

  const dark = isDark();
  const layout = Object.assign({}, figData.layout, {
    paper_bgcolor: 'rgba(0,0,0,0)',
    plot_bgcolor:  'rgba(0,0,0,0)',
    font: {
      family: "'Space Grotesk', system-ui, sans-serif",
      color:  dark ? '#FAFAFA' : '#09090B',
      size:   13,
    },
    xaxis: Object.assign({}, figData.layout?.xaxis, {
      gridcolor:    dark ? '#27272A' : '#E4E4E7',
      linecolor:    dark ? '#27272A' : '#E4E4E7',
      zerolinecolor: dark ? '#27272A' : '#E4E4E7',
    }),
    yaxis: Object.assign({}, figData.layout?.yaxis, {
      gridcolor:    dark ? '#27272A' : '#E4E4E7',
      linecolor:    dark ? '#27272A' : '#E4E4E7',
      zerolinecolor: dark ? '#27272A' : '#E4E4E7',
    }),
    legend: Object.assign({}, figData.layout?.legend, {
      bgcolor: 'rgba(0,0,0,0)',
    }),
    margin: { t: 48, r: 16, b: 48, l: 48, ...(figData.layout?.margin || {}) },
    autosize: true,
  });

  const config = {
    responsive:     true,
    displayModeBar: false,
  };

  Plotly.react(el, figData.data, layout, config);
}

/* ── Table helpers ───────────────────────────────────────────────────────────── */

function renderTopOpponentsTable(rows) {
  const cols = ['opponent', 'total', 'win', 'loss', 'draw', 'win_rate'];
  const labels = { opponent: 'Opponent', total: 'Games', win: 'W', loss: 'L', draw: 'D', win_rate: 'Win Rate' };

  let html = '<table><thead><tr>';
  cols.forEach(c => { html += `<th>${labels[c]}</th>`; });
  html += '</tr></thead><tbody>';

  rows.forEach(row => {
    html += '<tr>';
    cols.forEach(c => {
      let val = row[c];
      if (c === 'win_rate') val = (val * 100).toFixed(1) + '%';
      html += `<td>${val ?? '—'}</td>`;
    });
    html += '</tr>';
  });

  html += '</tbody></table>';
  $('top-opponents-table').innerHTML = html;
}

function renderGamesTable(divId, games) {
  if (!games || games.length === 0) {
    $(divId).innerHTML = '<p style="color:var(--text-muted);padding:.5rem 0">No games found.</p>';
    return;
  }

  let html = '<table><thead><tr><th>Date</th><th>Color</th><th>Result</th><th>Time Class</th><th>Link</th></tr></thead><tbody>';
  games.forEach(g => {
    const resClass = `result-${g.result}`;
    const date = g.date ? g.date.split('T')[0] : '—';
    const link = g.url ? `<a href="${g.url}" target="_blank" rel="noopener">↗</a>` : '—';
    html += `<tr>
      <td>${date}</td>
      <td>${g.your_color ?? '—'}</td>
      <td class="${resClass}">${g.result ?? '—'}</td>
      <td>${g.time_class ?? '—'}</td>
      <td>${link}</td>
    </tr>`;
  });
  html += '</tbody></table>';
  $(divId).innerHTML = html;
}

/* ── KPIs ────────────────────────────────────────────────────────────────────── */

function renderKPIs(data) {
  $('kpi-total').textContent   = data.total?.toLocaleString() ?? '—';
  $('kpi-wins').textContent    = data.wins?.toLocaleString()  ?? '—';
  $('kpi-losses').textContent  = data.losses?.toLocaleString() ?? '—';
  $('kpi-winrate').textContent = data.win_rate != null ? (data.win_rate * 100).toFixed(1) + '%' : '—';
}

/* ── UI state helpers ────────────────────────────────────────────────────────── */

function showLoading() {
  emptyState.classList.add('hidden');
  errorState.classList.add('hidden');
  kpiStrip.classList.add('hidden');
  dashboard.classList.add('hidden');
}

function showDashboard() {
  kpiStrip.classList.remove('hidden');
  dashboard.classList.remove('hidden');
}

function showError(msg) {
  emptyState.classList.add('hidden');
  kpiStrip.classList.add('hidden');
  dashboard.classList.add('hidden');
  errorMsg.textContent = msg || 'Something went wrong. Check the username and try again.';
  errorState.classList.remove('hidden');
}

/* ── API fetch ───────────────────────────────────────────────────────────────── */

async function apiFetch(url, options = {}) {
  const resp = await fetch(url, options);
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({}));
    throw new Error(body.detail || `Request failed (${resp.status})`);
  }
  if (resp.status === 204 || options.method === 'DELETE') return {};
  return resp.json();
}
