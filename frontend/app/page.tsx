'use client'

import { useState, useEffect, useRef, useCallback } from 'react'

// Same-origin by default (single-container deploy: FastAPI serves this app).
// Local dev can override via NEXT_PUBLIC_API_URL (see frontend/.env.local.example).
const API_BASE = process.env.NEXT_PUBLIC_API_URL || ''

type CheckStatus = 'pending' | 'running' | 'done'

type CheckState = {
  key: string
  label: string
  status: CheckStatus
}

const INITIAL_CHECKS: CheckState[] = [
  { key: 'History Analyst', label: 'History', status: 'pending' },
  { key: 'Docs Analyst', label: 'Docs', status: 'pending' },
  { key: 'Dependents Mapper', label: 'Dependents', status: 'pending' },
  { key: 'Test Coverage Checker', label: 'Tests', status: 'pending' },
]

type Evidence = {
  history?: string
  docs?: string
  dependents?: string
  tests?: string
}

type Result = {
  verdict: string
  confidence: string
  summary: string
  history: string
  docs: string
  dependents: string
  tests: string
  evidence?: Evidence
  suggestions?: string[]
}

type HeatmapFunction = {
  name: string
  line: number
  verdict: string
  confidence: string
  reason: string
}

type HeatmapResult = {
  mode: 'heatmap'
  file: string
  functions: HeatmapFunction[]
  summary: string
}

type DiffFunction = {
  name: string
  file: string
  line: number
  verdict: string
  confidence: string
  reason: string
}

type DiffResult = {
  mode: 'diff'
  summary: string
  functions: DiffFunction[]
  changed_files: string[]
}

type RepoFileRisk = {
  file: string
  functions: number
  risky: number
  review: number
  safe: number
  verdict: string
  score: number
}

type RepoHeatmapResult = {
  mode: 'repo'
  files: RepoFileRisk[]
  summary: string
}

type RepoStatus = {
  connected: boolean
  name?: string
  path?: string
  branch?: string
  latest_commit?: string
  file_count?: number
  error?: string
}

const VERDICT_CLASS: Record<string, string> = {
  Safe: 'verdict-safe',
  Risky: 'verdict-risky',
  'Needs Review': 'verdict-review',
}

const SECTION_BY_AGENT: Record<string, keyof Evidence> = {
  'History Analyst': 'history',
  'Docs Analyst': 'docs',
  'Dependents Mapper': 'dependents',
  'Test Coverage Checker': 'tests',
}

// ---------------------------------------------------------------------------
// RepoConnector — step 1: connect a remote URL or local path as the active repo
// ---------------------------------------------------------------------------

type RepoConnectorProps = {
  onConnected: () => void
}

function RepoConnector({ onConnected }: RepoConnectorProps) {
  const [open, setOpen] = useState(false)
  const [source, setSource] = useState('')
  const [loading, setLoading] = useState(false)
  const [status, setStatus] = useState<RepoStatus | null>(null)
  const [connectError, setConnectError] = useState<string | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  // Load current repo status on mount
  useEffect(() => {
    fetch(`${API_BASE}/repo/status`)
      .then((r) => r.json())
      .then((d: RepoStatus) => setStatus(d))
      .catch(() => {})
  }, [])

  useEffect(() => {
    if (open) setTimeout(() => inputRef.current?.focus(), 50)
  }, [open])

  async function connect() {
    if (!source.trim() || loading) return
    setLoading(true)
    setConnectError(null)
    try {
      const res = await fetch(`${API_BASE}/repo/connect`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ source: source.trim() }),
      })
      const data = await res.json()
      if (!res.ok) {
        setConnectError(typeof data.detail === 'string' ? data.detail : `Error ${res.status}`)
      } else {
        setStatus(data as RepoStatus)
        setSource('')
        setOpen(false)
        onConnected()
      }
    } catch (e) {
      setConnectError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="repo-connector">
      {/* Status badge */}
      <div className="repo-status-row">
        <span className={`repo-badge ${status?.connected ? 'repo-connected' : 'repo-disconnected'}`}>
          {status?.connected ? '● ' : '○ '}
          {status?.connected
            ? `${status.name} · ${status.branch} · ${status.file_count} files`
            : 'No repo connected'}
        </span>
        {status?.connected && status.latest_commit && (
          <span className="repo-commit" title={status.path}>
            {status.latest_commit}
          </span>
        )}
        <button
          className="repo-toggle"
          onClick={() => setOpen((v) => !v)}
          title={open ? 'Close' : 'Connect a different repo'}
        >
          {open ? '✕' : status?.connected ? '⚙ Switch repo' : '⚙ Connect repo'}
        </button>
      </div>

      {open && (
        <div className="repo-panel">
          <p className="repo-hint">
            Paste a <strong>git URL</strong> (https/ssh) to clone, or an <strong>absolute local path</strong> to an existing repo.
          </p>
          <div className="repo-input-row">
            <input
              ref={inputRef}
              className="repo-input"
              placeholder="https://github.com/org/repo.git  or  /home/user/my-project"
              value={source}
              onChange={(e) => setSource(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && connect()}
              disabled={loading}
            />
            <button
              className="repo-connect-btn"
              onClick={connect}
              disabled={loading || !source.trim()}
            >
              {loading ? 'Connecting…' : 'Connect'}
            </button>
          </div>
          {connectError && <p className="repo-error">{connectError}</p>}
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// FileBrowser — fetches /files once and renders a searchable file list
// ---------------------------------------------------------------------------

type FileBrowserProps = {
  onSelect: (file: string) => void
  mode: 'investigate' | 'heatmap' | 'diff'
  refreshKey: number
}

function FileBrowser({ onSelect, mode, refreshKey }: FileBrowserProps) {
  const [open, setOpen] = useState(false)
  const [files, setFiles] = useState<string[]>([])
  const [query, setQuery] = useState('')
  const [loading, setLoading] = useState(false)
  const [fetchError, setFetchError] = useState<string | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  const loadFiles = useCallback(() => {
    setLoading(true)
    setFetchError(null)
    fetch(`${API_BASE}/files`)
      .then((r) => r.json())
      .then((data) => {
        setFiles(data.files ?? [])
        if (data.error) setFetchError(data.error)
        setLoading(false)
        setTimeout(() => inputRef.current?.focus(), 50)
      })
      .catch((e) => {
        setFetchError(e.message)
        setLoading(false)
      })
  }, [])

  useEffect(() => {
    if (!open) return
    loadFiles()
  }, [open, loadFiles, refreshKey])  // refreshKey triggers reload after repo switch

  const filtered = query
    ? files.filter((f) => f.toLowerCase().includes(query.toLowerCase()))
    : files

  function pick(file: string) {
    onSelect(file)
    setOpen(false)
    setQuery('')
  }

  return (
    <div className="file-browser">
      <button
        className="browser-toggle"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-label="Browse repo files"
        title="Browse files in the target repo"
      >
        {open ? '✕ Close browser' : '📂 Browse files'}
      </button>

      {open && (
        <div className="browser-panel">
          <input
            ref={inputRef}
            className="browser-search"
            placeholder="Filter files…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          {loading && <p className="browser-status">Loading…</p>}
          {fetchError && <p className="browser-status browser-error">{fetchError}</p>}
          {!loading && !fetchError && filtered.length === 0 && (
            <p className="browser-status">No files found.</p>
          )}
          <ul className="browser-list">
            {filtered.map((f) => (
              <li key={f} className="browser-item">
                <button
                  className="browser-file"
                  onClick={() => pick(mode === 'investigate' ? `${f}:1` : f)}
                  title={f}
                >
                  {f.includes('/') ? '📄 ' : ''}{f.split('/').pop()}
                  <em className="browser-path">{f.includes('/') ? f.slice(0, f.lastIndexOf('/')) : ''}</em>
                </button>
                <button
                  className="browser-select"
                  onClick={() => pick(mode === 'investigate' ? `${f}:1` : f)}
                  title={`Select ${f}`}
                  aria-label={`Select ${f}`}
                >
                  Select
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// FileEditor — step 2: open any repo file, edit it in a textarea, save back
// ---------------------------------------------------------------------------

type FileEditorProps = {
  refreshKey: number
}

function FileEditor({ refreshKey }: FileEditorProps) {
  const [open, setOpen] = useState(false)
  const [files, setFiles] = useState<string[]>([])
  const [selectedFile, setSelectedFile] = useState<string | null>(null)
  const [content, setContent] = useState('')
  const [originalContent, setOriginalContent] = useState('')
  const [lineCount, setLineCount] = useState(0)
  const [loadingFiles, setLoadingFiles] = useState(false)
  const [loadingContent, setLoadingContent] = useState(false)
  const [saving, setSaving] = useState(false)
  const [committing, setCommitting] = useState(false)
  const [saveMsg, setSaveMsg] = useState<string | null>(null)
  const [editorError, setEditorError] = useState<string | null>(null)
  const [filterQuery, setFilterQuery] = useState('')

  // Load file list when editor opens or repo changes
  useEffect(() => {
    if (!open) return
    setLoadingFiles(true)
    setEditorError(null)
    fetch(`${API_BASE}/files`)
      .then((r) => r.json())
      .then((data) => {
        setFiles(data.files ?? [])
        setLoadingFiles(false)
      })
      .catch((e) => {
        setEditorError(e.message)
        setLoadingFiles(false)
      })
  }, [open, refreshKey])

  async function openFile(file: string) {
    setLoadingContent(true)
    setEditorError(null)
    setSaveMsg(null)
    try {
      const res = await fetch(`${API_BASE}/file-content?file=${encodeURIComponent(file)}`)
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || `Error ${res.status}`)
      setSelectedFile(file)
      setContent(data.content)
      setOriginalContent(data.content)
      setLineCount(data.line_count)
    } catch (e) {
      setEditorError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoadingContent(false)
    }
  }

  async function saveFile() {
    if (!selectedFile || saving) return
    setSaving(true)
    setSaveMsg(null)
    setEditorError(null)
    try {
      const res = await fetch(`${API_BASE}/file-content`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ file: selectedFile, content }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || `Error ${res.status}`)
      setOriginalContent(content)
      setLineCount(data.line_count)
      setSaveMsg(`Saved — ${data.line_count} lines`)
    } catch (e) {
      setEditorError(e instanceof Error ? e.message : String(e))
    } finally {
      setSaving(false)
    }
  }

  function discardChanges() {
    setContent(originalContent)
    setSaveMsg(null)
    setEditorError(null)
  }

  async function commitFile() {
    if (!selectedFile || committing || content === originalContent) return
    const message = window.prompt(`Commit message for ${selectedFile}:`, `update ${selectedFile}`)
    if (!message) return
    setCommitting(true)
    setEditorError(null)
    setSaveMsg(null)
    try {
      const res = await fetch(`${API_BASE}/file-commit`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ file: selectedFile, content, message }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || `Error ${res.status}`)
      setOriginalContent(content)
      setLineCount(content.split('\n').length)
      setSaveMsg(`Committed as ${data.commit} — "${message}"`)
    } catch (e) {
      setEditorError(e instanceof Error ? e.message : String(e))
    } finally {
      setCommitting(false)
    }
  }

  const isDirty = content !== originalContent
  const filteredFiles = filterQuery
    ? files.filter((f) => f.toLowerCase().includes(filterQuery.toLowerCase()))
    : files

  return (
    <div className="file-editor-wrap">
      <button
        className="editor-toggle"
        onClick={() => { setOpen((v) => !v); setSelectedFile(null); setContent('') }}
        title={open ? 'Close editor' : 'Open file editor'}
      >
        {open ? '✕ Close editor' : '✏️ Edit files'}
      </button>

      {open && (
        <div className="editor-panel">
          <div className="editor-sidebar">
            <input
              className="browser-search"
              placeholder="Filter files…"
              value={filterQuery}
              onChange={(e) => setFilterQuery(e.target.value)}
            />
            {loadingFiles && <p className="browser-status">Loading…</p>}
            {editorError && !selectedFile && <p className="browser-status browser-error">{editorError}</p>}
            <ul className="browser-list editor-file-list">
              {filteredFiles.map((f) => (
                <li key={f}>
                  <button
                    className={`browser-file ${selectedFile === f ? 'editor-file-active' : ''}`}
                    onClick={() => openFile(f)}
                    title={f}
                  >
                    {f}
                  </button>
                </li>
              ))}
            </ul>
          </div>

          <div className="editor-main">
            {!selectedFile && (
              <p className="editor-placeholder">← Select a file to view and edit</p>
            )}
            {loadingContent && <p className="editor-placeholder">Loading…</p>}
            {selectedFile && !loadingContent && (
              <>
                <div className="editor-topbar">
                  <span className="editor-filename">{selectedFile}</span>
                  <span className="editor-meta">{lineCount} lines</span>
                  {isDirty && (
                    <span className="editor-dirty" title="Unsaved changes">● unsaved</span>
                  )}
                  <div className="editor-actions">
                    {isDirty && (
                      <button
                        className="editor-btn editor-discard"
                        onClick={discardChanges}
                        title="Discard changes"
                      >
                        Discard
                      </button>
                    )}
                    <button
                      className="editor-btn editor-save"
                      onClick={saveFile}
                      disabled={!isDirty || saving}
                      title="Save file"
                    >
                      {saving ? 'Saving…' : 'Save'}
                    </button>
                    <button
                      className="editor-btn editor-commit"
                      onClick={commitFile}
                      disabled={isDirty || committing}
                      title={isDirty ? 'Save first, then commit' : 'Commit this file'}
                    >
                      {committing ? 'Committing…' : '✔ Commit'}
                    </button>
                  </div>
                </div>
                {saveMsg && <p className="editor-save-msg">{saveMsg}</p>}
                {editorError && <p className="browser-status browser-error">{editorError}</p>}
                <textarea
                  className="editor-textarea"
                  value={content}
                  onChange={(e) => { setContent(e.target.value); setSaveMsg(null) }}
                  spellCheck={false}
                  autoComplete="off"
                  autoCorrect="off"
                  autoCapitalize="off"
                />
              </>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main page — flow: 1) connect a repo  2) (optional) edit files  3) investigate
// ---------------------------------------------------------------------------

export default function Home() {
  const [mode, setMode] = useState<'investigate' | 'heatmap' | 'diff' | 'repo'>('investigate')
  const [target, setTarget] = useState('')
  const [investigating, setInvestigating] = useState(false)
  const [checks, setChecks] = useState<CheckState[]>(INITIAL_CHECKS)
  const [result, setResult] = useState<Result | null>(null)
  const [heatmap, setHeatmap] = useState<HeatmapResult | null>(null)
  const [diffResult, setDiffResult] = useState<DiffResult | null>(null)
  const [repoResult, setRepoResult] = useState<RepoHeatmapResult | null>(null)
  const [openEvidence, setOpenEvidence] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  // Bumped whenever a new repo is connected — forces FileBrowser + FileEditor to reload
  const [repoRefreshKey, setRepoRefreshKey] = useState(0)
  // The connection gate: tools appear only once a repo is connected
  const [repoConnected, setRepoConnected] = useState(false)

  useEffect(() => {
    fetch(`${API_BASE}/repo/status`)
      .then((r) => r.json())
      .then((d: RepoStatus) => setRepoConnected(Boolean(d.connected)))
      .catch(() => {})
  }, [])

  async function run() {
    const subject = target.trim()
    if (investigating) return
    if (mode !== 'diff' && mode !== 'repo' && !subject) return
    setInvestigating(true)
    setResult(null)
    setHeatmap(null)
    setDiffResult(null)
    setRepoResult(null)
    setOpenEvidence(null)
    setError(null)
    setChecks(INITIAL_CHECKS.map((c) => ({ ...c, status: 'pending' })))

    try {
      const endpoint =
        mode === 'investigate' ? '/investigate'
        : mode === 'heatmap' ? '/heatmap'
        : mode === 'diff' ? '/diff-investigate'
        : '/repo-heatmap'
      const body =
        mode === 'investigate' ? { target: subject }
        : mode === 'heatmap' ? { file: subject }
        : null
      const res = await fetch(`${API_BASE}${endpoint}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: body ? JSON.stringify(body) : undefined,
      })

      if (!res.ok || !res.body) {
        const detail = await res.json().catch(() => null)
        throw new Error(detail?.detail || `Request failed (${res.status})`)
      }

      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })

        let sep: number
        while ((sep = buffer.indexOf('\n\n')) !== -1) {
          const frame = buffer.slice(0, sep)
          buffer = buffer.slice(sep + 2)
          const line = frame.split('\n').find((l) => l.startsWith('data: '))
          if (!line) continue
          handleEvent(JSON.parse(line.slice(6)))
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setInvestigating(false)
    }
  }

  function handleEvent(event: Record<string, unknown> & { type: string }) {
    if (event.type === 'check_start' || event.type === 'check_finish') {
      const name = event.display_name as string
      setChecks((prev) =>
        prev.map((c) =>
          c.key === name
            ? { ...c, status: event.type === 'check_start' ? 'running' : 'done' }
            : c,
        ),
      )
    } else if (event.type === 'result') {
      const m = (event as { mode?: string }).mode
      if (m === 'heatmap') {
        setHeatmap(event as unknown as HeatmapResult)
      } else if (m === 'diff') {
        setDiffResult(event as unknown as DiffResult)
      } else if (m === 'repo') {
        setRepoResult(event as unknown as RepoHeatmapResult)
      } else {
        setResult(event as unknown as Result)
      }
    } else if (event.type === 'error') {
      setError(event.message as string)
    }
  }

  function clearOutput() {
    setResult(null)
    setHeatmap(null)
    setDiffResult(null)
    setRepoResult(null)
    setOpenEvidence(null)
    setError(null)
    setChecks(INITIAL_CHECKS.map((c) => ({ ...c, status: 'pending' })))
  }

  return (
    <main>
      <h1>
        Should I <span className="touch">Touch</span> This?
      </h1>
      <p className="tagline">
        Connect a repo. Make changes. Investigate before you touch risky code.
      </p>

      {/* ── Step 1: repo connector (always visible) ─────────────────── */}
      <RepoConnector
        onConnected={() => {
          setRepoConnected(true)
          setRepoRefreshKey((k) => k + 1)
          setTarget('')
          clearOutput()
        }}
      />

      {!repoConnected && (
        <p className="connect-gate">
          ↑ Connect a repository first — paste a git URL or an absolute local path.
          The 4 checks (history, docs, dependents, tests) run against the connected repo.
        </p>
      )}

      {repoConnected && (
        <>
          <div className="mode-tabs" role="tablist">
            <button
              role="tab"
              aria-selected={mode === 'investigate'}
              className={mode === 'investigate' ? 'tab active' : 'tab'}
              onClick={() => setMode('investigate')}
            >
              One line
            </button>
            <button
              role="tab"
              aria-selected={mode === 'heatmap'}
              className={mode === 'heatmap' ? 'tab active' : 'tab'}
              onClick={() => setMode('heatmap')}
            >
              Whole file
            </button>
            <button
              role="tab"
              aria-selected={mode === 'diff'}
              className={mode === 'diff' ? 'tab active' : 'tab'}
              onClick={() => setMode('diff')}
            >
              My changes
            </button>
            <button
              role="tab"
              aria-selected={mode === 'repo'}
              className={mode === 'repo' ? 'tab active' : 'tab'}
              onClick={() => setMode('repo')}
            >
              Whole repo
            </button>
          </div>

          <div className="input-row" style={mode === 'diff' || mode === 'repo' ? { display: 'none' } : undefined}>
            <input
              value={target}
              onChange={(e) => setTarget(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && run()}
              placeholder={
                mode === 'investigate'
                  ? 'src/utils/date.ts:120  or  parseDateString in src/date.ts'
                  : 'src/utils/date.ts'
              }
              disabled={investigating}
            />
            <button onClick={run} disabled={investigating || !target.trim()}>
              {investigating ? 'Scanning…' : mode === 'investigate' ? 'Investigate' : 'Scan file'}
            </button>
          </div>

          {(mode === 'diff' || mode === 'repo') && (
            <div className="input-row">
              <button onClick={run} disabled={investigating} className="wide-action">
                {investigating
                  ? 'Scanning…'
                  : mode === 'diff'
                    ? '🔍 Review my uncommitted changes'
                    : '🗺️ Scan whole repo risk'}
              </button>
            </div>
          )}

          {mode !== 'repo' && (
            <FileBrowser
              mode={mode}
              refreshKey={repoRefreshKey}
              onSelect={(file) => {
                setTarget(file)
                clearOutput()
              }}
            />
          )}

          {/* ── Step 2: file editor ──────────────────────────────────── */}
          <FileEditor refreshKey={repoRefreshKey} />

          {(investigating || checks.some((c) => c.status !== 'pending')) && (
            <ul className="checks">
              {checks.map((c) => (
                <li key={c.key} className={`check check-${c.status}`}>
                  <span className="dot" />
                  {c.label}
                  <em>
                    {c.status === 'pending' && 'waiting'}
                    {c.status === 'running' && 'running…'}
                    {c.status === 'done' && 'done'}
                  </em>
                </li>
              ))}
            </ul>
          )}

          {error && <div className="error">{error}</div>}

          {result && (
            <section className={`card ${VERDICT_CLASS[result.verdict] ?? 'verdict-review'}`}>
              <div className="card-head">
                <span className="verdict">{result.verdict}</span>
                <span className="confidence">{result.confidence} confidence</span>
              </div>
              <p className="summary">{result.summary}</p>
              <dl>
                {checks.map((c) => {
                  const key = SECTION_BY_AGENT[c.key]
                  const isOpen = openEvidence === key
                  const raw = result.evidence?.[key]
                  return (
                    <div key={c.key} className="finding">
                      <dt>{c.label}:</dt>
                      <dd>{(result[key] as string) ?? '—'}</dd>
                      {raw && (
                        <button
                          className={`chevron ${isOpen ? 'open' : ''}`}
                          aria-label={`Toggle ${c.label} evidence`}
                          onClick={() => setOpenEvidence(isOpen ? null : key)}
                        >
                          ▸
                        </button>
                      )}
                      {isOpen && raw && (
                        <pre className="evidence">{raw}</pre>
                      )}
                    </div>
                  )
                })}
              </dl>
              {result.suggestions && result.suggestions.length > 0 && (
                <div className="suggestions">
                  <h2>Next steps</h2>
                  <ul>
                    {result.suggestions.map((s, i) => (
                      <li key={i}>{s}</li>
                    ))}
                  </ul>
                </div>
              )}
            </section>
          )}

          {heatmap && (
            <section className="card heatmap">
              <div className="card-head">
                <span className="verdict heatmap-title">Risk heatmap</span>
                <span className="confidence">{heatmap.file}</span>
              </div>
              <p className="summary">{heatmap.summary}</p>
              {heatmap.functions.length === 0 ? (
                <p className="empty">No functions found in that file.</p>
              ) : (
                <ul className="heat-list">
                  {heatmap.functions.map((f, i) => (
                    <li key={`${f.name}-${i}`} className={`heat-row ${VERDICT_CLASS[f.verdict] ?? 'verdict-review'}`}>
                      <span className={`heat-badge ${VERDICT_CLASS[f.verdict] ?? 'verdict-review'}`}>
                        {f.verdict}
                      </span>
                      <span className="heat-name">
                        {f.name}
                        <em>:{f.line}</em>
                      </span>
                      <span className="heat-conf">{f.confidence}</span>
                      <span className="heat-reason">{f.reason}</span>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          )}

          {diffResult && (
            <section className="card heatmap">
              <div className="card-head">
                <span className="verdict heatmap-title">My changes</span>
                <span className="confidence">
                  {diffResult.changed_files.length} file(s) changed
                </span>
              </div>
              <p className="summary">{diffResult.summary}</p>
              {diffResult.functions.length === 0 ? (
                <p className="empty">{diffResult.summary}</p>
              ) : (
                <ul className="heat-list">
                  {diffResult.functions.map((f, i) => (
                    <li
                      key={`${f.name}-${i}`}
                      className={`heat-row ${VERDICT_CLASS[f.verdict] ?? 'verdict-review'}`}
                      onClick={() => {
                        setMode('investigate')
                        setTarget(`${f.file}:${f.line}`)
                        clearOutput()
                      }}
                    >
                      <span className={`heat-badge ${VERDICT_CLASS[f.verdict] ?? 'verdict-review'}`}>
                        {f.verdict}
                      </span>
                      <span className="heat-name">
                        {f.name}
                        <em>:{f.line}</em>
                      </span>
                      <span className="heat-conf">{f.confidence}</span>
                      <span className="heat-reason">{f.reason}</span>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          )}

          {repoResult && (
            <section className="card heatmap">
              <div className="card-head">
                <span className="verdict heatmap-title">Repo risk treemap</span>
                <span className="confidence">{repoResult.files.length} files</span>
              </div>
              <p className="summary">{repoResult.summary}</p>
              {repoResult.files.length === 0 ? (
                <p className="empty">{repoResult.summary}</p>
              ) : (
                <>
                  <div className="treemap">
                    {repoResult.files.map((f) => {
                      const cls = VERDICT_CLASS[f.verdict] ?? 'verdict-review'
                      const flex = Math.max(f.score * 2 + 1, 1)
                      return (
                        <button
                          key={f.file}
                          className={`tree-cell ${cls}`}
                          style={{ flexGrow: flex }}
                          title={`${f.file} — ${f.risky} risky, ${f.review} review, ${f.safe} safe of ${f.functions} functions`}
                          onClick={() => {
                            setMode('heatmap')
                            setTarget(f.file)
                            clearOutput()
                          }}
                        >
                          <span className="tree-file">{f.file.split('/').pop()}</span>
                          <span className="tree-counts">
                            {f.risky}R · {f.review}? · {f.safe}S
                          </span>
                        </button>
                      )
                    })}
                  </div>
                  <ul className="heat-list">
                    {repoResult.files.map((f) => (
                      <li
                        key={f.file}
                        className={`heat-row ${VERDICT_CLASS[f.verdict] ?? 'verdict-review'}`}
                        onClick={() => {
                          setMode('heatmap')
                          setTarget(f.file)
                          clearOutput()
                        }}
                      >
                        <span className={`heat-badge ${VERDICT_CLASS[f.verdict] ?? 'verdict-review'}`}>
                          {f.verdict}
                        </span>
                        <span className="heat-name">{f.file}</span>
                        <span className="heat-conf">{f.functions} fn</span>
                        <span className="heat-reason">
                          {f.risky} risky · {f.review} review · {f.safe} safe
                        </span>
                      </li>
                    ))}
                  </ul>
                </>
              )}
            </section>
          )}
        </>
      )}
    </main>
  )
}
