"""Single-file fallback UI, served when the exported Next.js build is absent.

Some HF Gradio runtimes do not hand the app every tracked directory (seen live:
frontend/out existed in the git repo but not in the container filesystem).
This page is baked into Python, so the deployed demo always works: same SSE
contract, same events, same verdict card and evidence drill-down as the
Next.js UI, in vanilla HTML/JS with the same dark palette.
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
  main { min-height:100dvh; display:flex; flex-direction:column; justify-content:center;
         align-items:center; text-align:center; padding:48px 20px; }
  h1 { font-size:1.6rem; margin-bottom:4px; } .touch { color:var(--blue); }
  .tagline { color:var(--muted); margin-bottom:20px; font-size:.9rem; }
  .input-row { display:flex; gap:8px; width:100%; max-width:640px; }
  input { flex:1; background:var(--panel); border:1px solid var(--border); border-radius:6px;
          color:var(--text); padding:10px 12px; font:inherit; font-size:.9rem; }
  input:focus { outline:1px solid var(--blue); }
  button { background:var(--blue); border:none; border-radius:6px; color:#0d1117;
           font:inherit; font-weight:700; padding:10px 18px; cursor:pointer; }
  button:disabled { opacity:.5; cursor:not-allowed; }
  .checks { list-style:none; margin-top:20px; display:grid; gap:6px; width:100%;
            max-width:640px; text-align:left; }
  .check { display:flex; align-items:center; gap:10px; background:var(--panel);
           border:1px solid var(--border); border-radius:6px; padding:8px 12px; font-size:.85rem; }
  .check em { margin-left:auto; font-style:normal; color:var(--muted); font-size:.8rem; }
  .dot { width:8px; height:8px; border-radius:50%; background:var(--border); }
  .running .dot { background:var(--amber); animation:pulse 1.2s infinite; }
  .done .dot { background:var(--green); }
  @keyframes pulse { 50% { opacity:.3; } }
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
             border-left:2px solid var(--border); }
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
  <p class="tagline">Paste a file + line from a legacy codebase. Four checks run in parallel. One verdict.</p>
  <div class="input-row">
    <input id="t" placeholder="parseDateString in src/date.ts  or  src/utils/date.ts:120" />
    <button id="go">Investigate</button>
  </div>
  <ul class="checks" id="checks"></ul>
  <div class="error" id="err" style="display:none"></div>
  <section class="card" id="card" style="display:none"></section>
</main>
<script>
const CHECKS = [
  { key: 'history',    display: 'History Analyst',    label: 'History' },
  { key: 'docs',       display: 'Docs Analyst',       label: 'Docs' },
  { key: 'dependents', display: 'Dependents Mapper',  label: 'Dependents' },
  { key: 'tests',      display: 'Test Coverage Checker', label: 'Tests' },
];
const VCLASS = { Safe: 'v-safe', Risky: 'v-risky', 'Needs Review': 'v-review' };
const t = document.getElementById('t'), go = document.getElementById('go');
const checksEl = document.getElementById('checks'), errEl = document.getElementById('err'),
      cardEl = document.getElementById('card');
let state = {}, busy = false;

function renderChecks() {
  checksEl.innerHTML = CHECKS.map(c => {
    const s = state[c.display] || 'pending';
    return `<li class="check ${s}"><span class="dot"></span>${c.label}<em>${
      s === 'running' ? 'running…' : s === 'done' ? 'done' : 'waiting'}</em></li>`;
  }).join('');
}
renderChecks();

function toggle(key, btn) {
  const pre = document.getElementById('ev-' + key);
  const open = pre.style.display === 'block';
  pre.style.display = open ? 'none' : 'block';
  btn.classList.toggle('open', !open);
}

async function investigate() {
  const target = t.value.trim();
  if (!target || busy) return;
  busy = true; go.disabled = true; go.textContent = 'Investigating…';
  state = {}; renderChecks();
  errEl.style.display = 'none'; cardEl.style.display = 'none';
  try {
    const res = await fetch('/investigate', { method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ target }) });
    if (!res.ok || !res.body) { const d = await res.json().catch(() => null);
      throw new Error((d && d.detail) || ('HTTP ' + res.status)); }
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
  } catch (e) { errEl.textContent = e.message; errEl.style.display = 'block'; }
  busy = false; go.disabled = false; go.textContent = 'Investigate';
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
    errEl.textContent = ev.message; errEl.style.display = 'block';
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

function esc(s) { return String(s).replace(/[&<>"']/g, c =>
  ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }

go.onclick = investigate;
t.addEventListener('keydown', e => { if (e.key === 'Enter') investigate(); });
</script>
</body>
</html>"""
