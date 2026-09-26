'use client'

import { useState } from 'react'

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

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

type Result = {
  verdict: string
  confidence: string
  summary: string
  history: string
  docs: string
  dependents: string
  tests: string
  suggestions?: string[]
}

const VERDICT_CLASS: Record<string, string> = {
  Safe: 'verdict-safe',
  Risky: 'verdict-risky',
  'Needs Review': 'verdict-review',
}

const SECTION_BY_AGENT: Record<string, keyof Result> = {
  'History Analyst': 'history',
  'Docs Analyst': 'docs',
  'Dependents Mapper': 'dependents',
  'Test Coverage Checker': 'tests',
}

export default function Home() {
  const [target, setTarget] = useState('')
  const [investigating, setInvestigating] = useState(false)
  const [checks, setChecks] = useState<CheckState[]>(INITIAL_CHECKS)
  const [result, setResult] = useState<Result | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function investigate() {
    if (!target.trim() || investigating) return
    setInvestigating(true)
    setResult(null)
    setError(null)
    setChecks(INITIAL_CHECKS.map((c) => ({ ...c, status: 'pending' })))

    try {
      const res = await fetch(`${API_BASE}/investigate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ target: target.trim() }),
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
      setResult(event as unknown as Result)
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

      <div className="input-row">
        <input
          value={target}
          onChange={(e) => setTarget(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && investigate()}
          placeholder="src/utils/date.ts:120  or  parseDateString in src/date.ts"
          disabled={investigating}
        />
        <button onClick={investigate} disabled={investigating || !target.trim()}>
          {investigating ? 'Investigating…' : 'Investigate'}
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
              return (
                <div key={c.key} className="finding">
                  <dt>{c.label}:</dt>
                  <dd>{(result[key] as string) ?? '—'}</dd>
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
    </main>
  )
}
