// Simulates the frontend's SSE consumption against a running backend.
// Usage: node scripts/sse-smoke.mjs [target] [baseUrl]
const target = process.argv[2] ?? 'src/index.ts:1'
const base =
  process.argv[3] ?? process.env.SMOKE_BASE_URL ?? 'http://localhost:8000'

const res = await fetch(`${base}/investigate`, {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    Origin: 'http://localhost:3000',
  },
  body: JSON.stringify({ target }),
})

if (!res.ok || !res.body) {
  const detail = await res.json().catch(() => null)
  console.error(`HTTP ${res.status}: ${detail?.detail ?? 'request failed'}`)
  process.exit(1)
}

const decoder = new TextDecoder()
let buffer = ''
let sawEvent = false

const reader = res.body.getReader()
while (true) {
  const { done, value } = await reader.read()
  if (done) break
  buffer += decoder.decode(value, { stream: true })

  let sep
  while ((sep = buffer.indexOf('\n\n')) !== -1) {
    const frame = buffer.slice(0, sep)
    buffer = buffer.slice(sep + 2)
    const line = frame.split('\n').find((l) => l.startsWith('data: '))
    if (!line) continue
    const event = JSON.parse(line.slice(6))
    sawEvent = true
    if (event.type === 'result') {
      console.log(
        `RESULT: ${event.verdict} (${event.confidence}) — ${event.summary}`,
      )
    } else if (event.type === 'error') {
      console.log(`ERROR: ${event.message}`)
      process.exitCode = 2
    } else {
      console.log(`${event.type}: ${event.display_name ?? ''}`)
    }
  }
}

if (!sawEvent) {
  console.error('No SSE events received')
  process.exit(1)
}
