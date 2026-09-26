'use client'

import { useState } from 'react'

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

const EVIDENCE_LABELS: { key: keyof Evidence; label: string }[] = [
  { key: 'history', label: 'History' },
  { key: 'docs', label: 'Docs' },
  { key: 'dependents', label: 'Dependents' },
  { key: 'tests', label: 'Tests' },
]

export default function Home() {
  const [mode, setMode] = useState<'investigate' | 'heatmap'>('investigate')
  const [target, setTarget] = useState('')
  const [investigating, setInvestigating] = useState(false)
  const [checks, setChecks] = useState<CheckState[]>(INITIAL_CHECKS)
  const [result, setResult] = useState<Result | null>(null)
  const [heatmap, setHeatmap] = useState<HeatmapResult | null>(null)
  const [openEvidence, setOpenEvidence] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function run() {
    const subject = target.trim()
    if (!subject || investigating) return
    setInvestigating(true)
    setResult(null)
    setHeatmap(null)
    setOpenEvidence(null)
    setError(null)
    setChecks(INITIAL_CHECKS.map((c) => ({ ...c, status: 'pending' })))

    try {
      const endpoint = mode === 'investigate' ? '/investigate' : '/heatmap'
      const body =
        mode === 'investigate' ? { target: subject } : { file: subject }
      const res = await fetch(`${API_BASE}${endpoint}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
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
      if ((event as unknown as HeatmapResult).mode === 'heatmap') {
        setHeatmap(event as unknown as HeatmapResult)
      } else {
        setResult(event as unknown as Result)
      }
    } else if (event.type === 'error') {
      setError(event.message as string)
    }
  }

  return (
    <main>
      <h1>
        Should I <span className="touch">Touch</span> This?
      </h1>
      <p className="tagline">
        Paste a file + line from a legacy codebase. Four checks run in parallel. One verdict.
      </p>

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
      </div>

      <div className="input-row">
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
    </main>
  )
}
