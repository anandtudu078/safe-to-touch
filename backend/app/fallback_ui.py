"""Single-file fallback UI, served when the exported Next.js build is absent.

Some HF Gradio runtimes do not hand the app every tracked directory (seen live:
frontend/out existed in the git repo but not in the container filesystem).
This page is baked into Python, so the deployed demo always works: same SSE
contract, same events, same verdict card and evidence drill-down as the
Next.js UI, in vanilla HTML/JS with the same dark palette.

Mirrors the connect-first flow in frontend/app/page.tsx:
  Step 1 – connect a repo (RepoConnector)
  Step 2 – (optional) browse / edit files
  Step 3 – investigate (one line) or scan (whole file heatmap)
"""

FALLBACK_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Should I Touch This?</title>
<style>
  :root { --bg:#0d1117; --panel:#161b22; --border:#30363d; --text:#e6edf3;
          --muted:#8b949e; --green:#3fb950; --red:#f85149; --amber:#d29922; --blue:#58a6ff; }
  * { box-sizing:border-box; margin:0; padding:0; }
  body { background:var(--bg); color:var(--text); font-family:ui-monospace,Menlo,Consolas,monospace;
         line-height:1.5; }
  main { min-height:100dvh; display:flex; flex-direction:column; align-items:center;
         text-align:center; padding:48px 20px; }
  h1 { font-size:1.6rem; margin-bottom:4px; } .touch { color:var(--blue); }
  .tagline { color:var(--muted); margin-bottom:20px; font-size:.9rem; }

  /* ── repo connector ───────────────────────────────────────────── */
  .repo-connector { width:100%; max-width:640px; margin-bottom:12px; }
  .repo-status-row { display:flex; align-items:center; gap:8px; flex-wrap:wrap; }
  .repo-badge { font-size:.8rem; padding:4px 10px; border-radius:999px;
                border:1px solid var(--border); }
  .repo-connected { color:var(--green); border-color:var(--green); }
  .repo-disconnected { color:var(--muted); }
  .repo-commit { font-size:.75rem; color:var(--muted); flex:1;
                 overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .repo-toggle { background:transparent; color:var(--blue); border:1px solid var(--blue);
                 font:inherit; font-size:.8rem; padding:4px 12px; border-radius:6px;
                 cursor:pointer; margin-left:auto; }
  .repo-panel { margin-top:8px; background:var(--panel); border:1px solid var(--border);
                border-radius:6px; padding:12px; text-align:left; }
  .repo-hint { font-size:.8rem; color:var(--muted); margin-bottom:8px; }
  .repo-hint strong { color:var(--text); }
  .repo-input-row { display:flex; gap:8px; }
  .repo-input { flex:1; background:var(--bg); border:1px solid var(--border); border-radius:6px;
                color:var(--text); padding:8px 10px; font:inherit; font-size:.85rem; }
  .repo-input:focus { outline:1px solid var(--blue); }
  .repo-connect-btn { background:var(--blue); border:none; border-radius:6px; color:#0d1117;
                      font:inherit; font-weight:700; padding:8px 14px; cursor:pointer; font-size:.85rem; }
  .repo-connect-btn:disabled { opacity:.5; cursor:not-allowed; }
  .repo-error { color:var(--red); font-size:.8rem; margin-top:6px; }
  .connect-gate { color:var(--muted); font-size:.85rem; margin-top:8px; margin-bottom:16px; }

  /* ── mode tabs ───────────────────────────────────────────────── */
  .mode-tabs { display:flex; gap:4px; margin-bottom:12px; }
  .tab { background:transparent; border:1px solid var(--border); border-radius:6px;
         color:var(--muted); font:inherit; padding:6px 18px; cursor:pointer; font-size:.85rem; }
  .tab.active { background:var(--blue); color:#0d1117; border-color:var(--blue); font-weight:700; }

  /* ── main input row ──────────────────────────────────────────── */
  .input-row { display:flex; gap:8px; width:100%; max-width:640px; }
  input { flex:1; background:var(--panel); border:1px solid var(--border); border-radius:6px;
          color:var(--text); padding:10px 12px; font:inherit; font-size:.9rem; }
  input:focus { outline:1px solid var(--blue); }
  button { background:var(--blue); border:none; border-radius:6px; color:#0d1117;
           font:inherit; font-weight:700; padding:10px 18px; cursor:pointer; }
  button:disabled { opacity:.5; cursor:not-allowed; }

  /* ── file browser ────────────────────────────────────────────── */
  .file-browser { width:100%; max-width:640px; margin-top:8px; text-align:left; }
  .browser-toggle { background:transparent; color:var(--blue); border:1px solid var(--blue);
                    font:inherit; font-size:.8rem; padding:4px 12px; border-radius:6px; cursor:pointer; }
  .browser-panel { margin-top:6px; background:var(--panel); border:1px solid var(--border);
                   border-radius:6px; padding:10px; max-height:260px; overflow-y:auto; }
  .browser-search { width:100%; background:var(--bg); border:1px solid var(--border);
                    border-radius:6px; color:var(--text); padding:6px 10px; font:inherit;
                    font-size:.8rem; margin-bottom:6px; }
  .browser-search:focus { outline:1px solid var(--blue); }
  .browser-status { font-size:.8rem; color:var(--muted); padding:4px 0; }
  .browser-error { color:var(--red); }
  .browser-list { list-style:none; }
  .browser-item { display:flex; align-items:stretch; border-bottom:1px solid var(--border); }
  .browser-list li:last-child .browser-item { border-bottom:none; }
  .browser-file { flex:1; min-width:0; background:transparent; border:none; color:var(--blue);
                  font:inherit; font-size:.8rem; cursor:pointer; padding:4px 6px; text-align:left;
                  overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .browser-file:hover { text-decoration:underline; }
  .browser-path { color:var(--border); font-style:normal; margin-left:6px; font-size:.72rem; }
  .browser-select { background:transparent; border:none; border-left:1px solid var(--border);
                    color:var(--blue); font:inherit; font-size:.72rem; font-weight:600;
                    padding:4px 8px; cursor:pointer; white-space:nowrap; }
  .browser-select:hover { background:var(--blue); color:#0d1117; }

  /* ── checks ─────────────────────────────────────────────────── */
  .checks { list-style:none; margin-top:20px; display:grid; gap:6px; width:100%;
            max-width:640px; text-align:left; }
  .check { display:flex; align-items:center; gap:10px; background:var(--panel);
           border:1px solid var(--border); border-radius:6px; padding:8px 12px; font-size:.85rem; }
  .check em { margin-left:auto; font-style:normal; color:var(--muted); font-size:.8rem; }
  .dot { width:8px; height:8px; border-radius:50%; background:var(--border); }
  .running .dot { background:var(--amber); animation:pulse 1.2s infinite; }
  .done .dot { background:var(--green); }
  @keyframes pulse { 50% { opacity:.3; } }

  /* ── error / card ────────────────────────────────────────────── */
  .error { margin-top:20px; width:100%; max-width:640px; border:1px solid var(--red);
           border-radius:6px; color:var(--red); padding:12px; font-size:.85rem; }
  .card { margin-top:24px; width:100%; max-width:640px; text-align:left; background:var(--panel);
          border:1px solid var(--border); border-left-width:4px; border-radius:6px; padding:20px; }
  .card-head { display:flex; align-items:center; gap:12px; margin-bottom:14px; flex-wrap:wrap; }
  .verdict { font-size:1.4rem; font-weight:700; text-transform:uppercase; letter-spacing:.04em;
             padding:6px 18px; border-radius:999px; border:1px solid currentColor; }
  .confidence { color:var(--muted); font-size:.8rem; text-transform:uppercase;
                letter-spacing:.06em; border:1px solid var(--border); padding:5px 12px;
                border-radius:999px; }
  .v-safe { border-left-color:var(--green); } .v-safe .verdict { color:var(--green); background:rgba(63,185,80,.12); }
  .v-risky { border-left-color:var(--red); } .v-risky .verdict { color:var(--red); background:rgba(248,81,73,.12); }
  .v-review { border-left-color:var(--amber); } .v-review .verdict { color:var(--amber); background:rgba(210,153,34,.12); }
  .summary { margin-bottom:14px; font-size:.9rem; }
  .finding { display:flex; gap:8px; margin-bottom:8px; font-size:.85rem; padding-left:10px;
             border-left:2px solid var(--border); flex-wrap:wrap; }
  .finding dt { color:var(--muted); white-space:nowrap; font-weight:600; }
  .chev { background:transparent; color:var(--muted); border:none; cursor:pointer; font-size:.9rem; }
  .chev.open { color:var(--blue); transform:rotate(90deg); }
  .evidence { width:100%; margin:6px 0 2px 18px; padding:10px 12px; background:var(--bg);
              border:1px solid var(--border); border-radius:6px; font-size:.75rem;
              white-space:pre-wrap; word-break:break-word; color:var(--muted); text-align:left; }
  .sugg { margin-top:14px; border-top:1px solid var(--border); padding-top:10px; font-size:.8rem;
          color:var(--muted); text-align:left; }
  .sugg b { text-transform:uppercase; letter-spacing:.05em; font-size:.7rem; display:block; margin-bottom:4px; }
  .sugg li { margin-left:16px; }
</style>
</head>
<body>
<main>
  <h1>Should I <span class="touch">Touch</span> This?</h1>
  <p class="tagline">Connect a repo. Make changes. Investigate before you touch risky code.</p>

  <!-- Step 1: repo connector -->
  <div class="repo-connector" id="repoConnector">
    <div class="repo-status-row">
      <span class="repo-badge repo-disconnected" id="repoBadge">○ No repo connected</span>
      <span class="repo-commit" id="repoCommit"></span>
      <button class="repo-toggle" id="repoToggle">⚙ Connect repo</button>
    </div>
    <div class="repo-panel" id="repoPanel" style="display:none">
      <p class="repo-hint">
        Paste a <strong>git URL</strong> (https/ssh) to clone, or an <strong>absolute local path</strong> to an existing repo.
      </p>
      <div class="repo-input-row">
        <input class="repo-input" id="repoSource"
               placeholder="https://github.com/org/repo.git  or  /home/user/my-project" />
        <button class="repo-connect-btn" id="repoConnectBtn">Connect</button>
      </div>
      <p class="repo-error" id="repoError" style="display:none"></p>
    </div>
  </div>

  <!-- Connection gate hint (hidden once connected) -->
  <p class="connect-gate" id="connectGate">
    ↑ Connect a repository first — paste a git URL or an absolute local path.
    The 4 checks (history, docs, dependents, tests) run against the connected repo.
  </p>

  <!-- Steps 2+3: shown only after repo is connected -->
  <div id="mainTools" style="display:none; width:100%; max-width:640px;">
    <!-- Mode tabs -->
    <div class="mode-tabs">
      <button class="tab active" id="tabInvestigate" onclick="switchMode('investigate')">One line</button>
      <button class="tab" id="tabHeatmap" onclick="switchMode('heatmap')">Whole file</button>
    </div>

    <!-- Target input -->
    <div class="input-row">
      <input id="t" placeholder="src/utils/date.ts:120  or  parseDateString in src/date.ts" />
      <button id="go">Investigate</button>
    </div>

    <!-- File browser -->
    <div class="file-browser" id="fileBrowser">
      <button class="browser-toggle" id="browserToggle" onclick="toggleBrowser()">📂 Browse files</button>
      <div class="browser-panel" id="browserPanel" style="display:none">
        <input class="browser-search" id="browserSearch" placeholder="Filter files…" oninput="filterFiles()" />
        <p class="browser-status" id="browserStatus" style="display:none"></p>
        <ul class="browser-list" id="browserList"></ul>
      </div>
    </div>
  </div>

  <ul class="checks" id="checks"></ul>
  <div class="error" id="err" style="display:none"></div>
  <section class="card" id="card" style="display:none"></section>
</main>
<script>
const CHECKS = [
  { key: 'history',    display: 'History Analyst',       label: 'History' },
  { key: 'docs',       display: 'Docs Analyst',          label: 'Docs' },
  { key: 'dependents', display: 'Dependents Mapper',     label: 'Dependents' },
  { key: 'tests',      display: 'Test Coverage Checker', label: 'Tests' },
];
const VCLASS = { Safe: 'v-safe', Risky: 'v-risky', 'Needs Review': 'v-review' };

const tEl = document.getElementById('t');
const goEl = document.getElementById('go');
const checksEl = document.getElementById('checks');
const errEl = document.getElementById('err');
const cardEl = document.getElementById('card');
const connectGateEl = document.getElementById('connectGate');
const mainToolsEl = document.getElementById('mainTools');
const repoBadgeEl = document.getElementById('repoBadge');
const repoCommitEl = document.getElementById('repoCommit');
const repoToggleEl = document.getElementById('repoToggle');
const repoPanelEl = document.getElementById('repoPanel');
const repoSourceEl = document.getElementById('repoSource');
const repoConnectBtnEl = document.getElementById('repoConnectBtn');
const repoErrorEl = document.getElementById('repoError');
const browserPanelEl = document.getElementById('browserPanel');
const browserToggleEl = document.getElementById('browserToggle');
const browserStatusEl = document.getElementById('browserStatus');
const browserListEl = document.getElementById('browserList');

let state = {}, busy = false, currentMode = 'investigate';
let repoConnected = false, allFiles = [];

// ── repo connector ────────────────────────────────────────────────

async function loadRepoStatus() {
  try {
    const d = await fetch('/repo/status').then(r => r.json());
    applyRepoStatus(d);
  } catch (_) {}
}

function applyRepoStatus(d) {
  repoConnected = Boolean(d.connected);
  if (d.connected) {
    repoBadgeEl.className = 'repo-badge repo-connected';
    repoBadgeEl.textContent = '● ' + d.name + ' · ' + d.branch + ' · ' + d.file_count + ' files';
    repoCommitEl.textContent = d.latest_commit || '';
    repoToggleEl.textContent = '⚙ Switch repo';
    connectGateEl.style.display = 'none';
    mainToolsEl.style.display = '';
  } else {
    repoBadgeEl.className = 'repo-badge repo-disconnected';
    repoBadgeEl.textContent = '○ No repo connected';
    repoCommitEl.textContent = '';
    repoToggleEl.textContent = '⚙ Connect repo';
    connectGateEl.style.display = '';
    mainToolsEl.style.display = 'none';
  }
}

repoToggleEl.onclick = () => {
  const open = repoPanelEl.style.display !== 'none';
  repoPanelEl.style.display = open ? 'none' : '';
  repoToggleEl.textContent = open
    ? (repoConnected ? '⚙ Switch repo' : '⚙ Connect repo')
    : '✕';
  if (!open) setTimeout(() => repoSourceEl.focus(), 50);
};

repoSourceEl.addEventListener('keydown', e => { if (e.key === 'Enter') connectRepo(); });
repoConnectBtnEl.onclick = connectRepo;

async function connectRepo() {
  const source = repoSourceEl.value.trim();
  if (!source || repoConnectBtnEl.disabled) return;
  repoConnectBtnEl.disabled = true;
  repoConnectBtnEl.textContent = 'Connecting…';
  repoErrorEl.style.display = 'none';
  try {
    const res = await fetch('/repo/connect', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ source }),
    });
    const data = await res.json();
    if (!res.ok) {
      repoErrorEl.textContent = typeof data.detail === 'string' ? data.detail : 'Error ' + res.status;
      repoErrorEl.style.display = '';
    } else {
      applyRepoStatus(data);
      repoSourceEl.value = '';
      repoPanelEl.style.display = 'none';
      repoToggleEl.textContent = '⚙ Switch repo';
      // reset investigation state
      tEl.value = ''; allFiles = [];
      browserListEl.innerHTML = '';
      browserPanelEl.style.display = 'none';
      browserToggleEl.textContent = '📂 Browse files';
      clearOutput();
    }
  } catch (e) {
    repoErrorEl.textContent = e.message;
    repoErrorEl.style.display = '';
  } finally {
    repoConnectBtnEl.disabled = false;
    repoConnectBtnEl.textContent = 'Connect';
  }
}

// ── mode tabs ─────────────────────────────────────────────────────

function switchMode(m) {
  currentMode = m;
  document.getElementById('tabInvestigate').className = 'tab' + (m === 'investigate' ? ' active' : '');
  document.getElementById('tabHeatmap').className = 'tab' + (m === 'heatmap' ? ' active' : '');
  tEl.placeholder = m === 'investigate'
    ? 'src/utils/date.ts:120  or  parseDateString in src/date.ts'
    : 'src/utils/date.ts';
  goEl.textContent = m === 'investigate' ? 'Investigate' : 'Scan file';
  clearOutput();
}

// ── file browser ──────────────────────────────────────────────────

function toggleBrowser() {
  const open = browserPanelEl.style.display !== 'none';
  if (open) {
    browserPanelEl.style.display = 'none';
    browserToggleEl.textContent = '📂 Browse files';
  } else {
    browserPanelEl.style.display = '';
    browserToggleEl.textContent = '✕ Close browser';
    loadFiles();
  }
}

async function loadFiles() {
  browserStatusEl.style.display = '';
  browserStatusEl.className = 'browser-status';
  browserStatusEl.textContent = 'Loading…';
  browserListEl.innerHTML = '';
  try {
    const data = await fetch('/files').then(r => r.json());
    allFiles = data.files || [];
    if (data.error) {
      browserStatusEl.className = 'browser-status browser-error';
      browserStatusEl.textContent = data.error;
    } else {
      browserStatusEl.style.display = 'none';
    }
    renderFileList(allFiles);
  } catch (e) {
    browserStatusEl.className = 'browser-status browser-error';
    browserStatusEl.textContent = e.message;
  }
}

function filterFiles() {
  const q = document.getElementById('browserSearch').value.toLowerCase();
  renderFileList(q ? allFiles.filter(f => f.toLowerCase().includes(q)) : allFiles);
}

function renderFileList(files) {
  if (!files.length) {
    browserStatusEl.style.display = '';
    browserStatusEl.className = 'browser-status';
    browserStatusEl.textContent = 'No files found.';
    browserListEl.innerHTML = '';
    return;
  }
  browserStatusEl.style.display = 'none';
  browserListEl.innerHTML = files.map(f => {
    const slash = f.lastIndexOf('/');
    const name = slash === -1 ? f : f.slice(slash + 1);
    const dir = slash === -1 ? '' : f.slice(0, slash);
    const arg = JSON.stringify(f).replace(/'/g, '&#39;');
    return `<li class="browser-item">` +
      `<button class="browser-file" onclick='pickFile(${arg})' title="${esc(f)}">` +
      (slash !== -1 ? '\U0001f4c4 ' : '') + esc(name) +
      (dir ? `<em class="browser-path">${esc(dir)}</em>` : '') +
      `</button>` +
      `<button class="browser-select" onclick='pickFile(${arg})' title="Select ${esc(f)}" aria-label="Select ${esc(f)}">Select</button>` +
      `</li>`;
  }).join('');
}

function pickFile(f) {
  tEl.value = currentMode === 'investigate' ? f + ':1' : f;
  browserPanelEl.style.display = 'none';
  browserToggleEl.textContent = '📂 Browse files';
  clearOutput();
}

// ── checks / output ────────────────────────────────────────────────

function clearOutput() {
  state = {}; renderChecks();
  errEl.style.display = 'none';
  cardEl.style.display = 'none';
}

function renderChecks() {
  const anyActive = CHECKS.some(c => (state[c.display] || 'pending') !== 'pending');
  checksEl.innerHTML = anyActive ? CHECKS.map(c => {
    const s = state[c.display] || 'pending';
    return `<li class="check ${s}"><span class="dot"></span>${c.label}<em>${
      s === 'running' ? 'running…' : s === 'done' ? 'done' : 'waiting'}</em></li>`;
  }).join('') : '';
}

function toggle(key, btn) {
  const pre = document.getElementById('ev-' + key);
  const open = pre.style.display === 'block';
  pre.style.display = open ? 'none' : 'block';
  btn.classList.toggle('open', !open);
}

async function run() {
  const target = tEl.value.trim();
  if (!target || busy) return;
  busy = true;
  goEl.disabled = true;
  goEl.textContent = currentMode === 'investigate' ? 'Investigating…' : 'Scanning…';
  clearOutput();
  CHECKS.forEach(c => { state[c.display] = 'pending'; });
  renderChecks();
  errEl.style.display = 'none';
  cardEl.style.display = 'none';

  try {
    const endpoint = currentMode === 'investigate' ? '/investigate' : '/heatmap';
    const body = currentMode === 'investigate' ? { target } : { file: target };
    const res = await fetch(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!res.ok || !res.body) {
      const d = await res.json().catch(() => null);
      throw new Error((d && d.detail) || ('HTTP ' + res.status));
    }
    const reader = res.body.getReader(), dec = new TextDecoder();
    let buf = '';
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      let i;
      while ((i = buf.indexOf('\\n\\n')) !== -1) {
        const frame = buf.slice(0, i); buf = buf.slice(i + 2);
        const line = frame.split('\\n').find(l => l.startsWith('data: '));
        if (line) handle(JSON.parse(line.slice(6)));
      }
    }
  } catch (e) {
    errEl.textContent = e.message;
    errEl.style.display = '';
  }
  busy = false;
  goEl.disabled = false;
  goEl.textContent = currentMode === 'investigate' ? 'Investigate' : 'Scan file';
}

function handle(ev) {
  if (ev.type === 'check_start' || ev.type === 'check_finish') {
    state[ev.display_name] = ev.type === 'check_start' ? 'running' : 'done';
    renderChecks();
  } else if (ev.type === 'result') {
    if (ev.mode === 'heatmap') { renderHeatmap(ev); return; }
    const r = ev;
    const rows = CHECKS.map(c => {
      const raw = r.evidence && r.evidence[c.key];
      return `<div class="finding"><dt>${c.label}:</dt><dd>${esc(r[c.key] || '—')}</dd>` +
        (raw ? `<button class="chev" onclick="toggle('${c.key}', this)">▸</button>
               <pre class="evidence" id="ev-${c.key}" style="display:none">${esc(raw)}</pre>` : '') +
        `</div>`;
    }).join('');
    cardEl.className = 'card ' + (VCLASS[r.verdict] || 'v-review');
    cardEl.innerHTML =
      `<div class="card-head"><span class="verdict">${esc(r.verdict)}</span>` +
      `<span class="confidence">${esc(r.confidence)} confidence</span></div>` +
      `<p class="summary">${esc(r.summary)}</p><dl>${rows}</dl>` +
      (r.suggestions && r.suggestions.length
        ? `<div class="sugg"><b>Next steps</b><ul>${r.suggestions.map(s => '<li>' + esc(s) + '</li>').join('')}</ul></div>` : '');
    cardEl.style.display = 'block';
  } else if (ev.type === 'error') {
    errEl.textContent = ev.message;
    errEl.style.display = '';
  }
}

function renderHeatmap(h) {
  const rows = (h.functions || []).map(f =>
    `<div class="finding"><dt>${esc(f.verdict)}</dt><dd><b>${esc(f.name)}:${f.line}</b>` +
    ` (${esc(f.confidence)}) — ${esc(f.reason)}</dd></div>`).join('');
  cardEl.className = 'card v-review';
  cardEl.innerHTML =
    `<div class="card-head"><span class="verdict">Risk heatmap</span>` +
    `<span class="confidence">${esc(h.file)}</span></div>` +
    `<p class="summary">${esc(h.summary)}</p>${rows || '<p>No functions found.</p>'}`;
  cardEl.style.display = 'block';
}

function esc(s) {
  return String(s).replace(/[&<>"']/g, c =>
    ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

goEl.onclick = run;
tEl.addEventListener('keydown', e => { if (e.key === 'Enter') run(); });

// Boot: load current repo status so the UI is correct on page load
loadRepoStatus();
</script>
</body>
</html>"""
