// Verifies the end-to-end output contract without an API key:
//   orchestrator outputSchema  ==  frontend result-card fields
// (The backend forwards SDK structured output verbatim, so it has no field
// list of its own; the contract is between the two ends of the pipeline.)
// Run with: npm run smoke:contract
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { loadLocalAgents } from '@codebuff/sdk'

function fail(msg) {
  console.error(`FAIL: ${msg}`)
  process.exit(1)
}

const agentsPath = fileURLToPath(new URL('../.agents', import.meta.url))
const { agents } = await loadLocalAgents({ agentsPath, validate: true })

const def = agents['investigate-safety']
if (!def) fail('investigate-safety agent not found')
if (def.outputMode !== 'structured_output') {
  fail(`outputMode must be 'structured_output', got '${def.outputMode}'`)
}

const schemaProps = Object.keys(def.outputSchema?.properties ?? {})
const required = new Set(def.outputSchema?.required ?? [])
if (schemaProps.length === 0) fail('outputSchema has no properties')

// Fields the frontend card actually renders (see frontend/app/page.tsx)
const pageSrc = readFileSync(
  fileURLToPath(new URL('../frontend/app/page.tsx', import.meta.url)),
  'utf8',
)

const VERDICTS = ['Safe', 'Risky', 'Needs Review']
if (!schemaProps.includes('verdict')) fail('schema missing verdict field')
for (const v of VERDICTS) {
  // Verdicts may appear as quoted strings or unquoted object keys in page.tsx
  const handled =
    pageSrc.includes(`'${v}'`) || pageSrc.includes(`"${v}"`) || pageSrc.includes(`${v}:`)
  if (!handled) fail(`frontend does not handle verdict '${v}'`)
}
if (!pageSrc.includes('verdict-safe') || !pageSrc.includes('verdict-risky') || !pageSrc.includes('verdict-review')) {
  fail('frontend missing a verdict CSS class')
}

// Every required schema field must be consumed somewhere in page.tsx
for (const field of required) {
  if (!pageSrc.includes(`'${field}'`) && !pageSrc.includes(`"${field}"`) && !pageSrc.includes(`result.${field}`)) {
    fail(`required schema field '${field}' is not rendered by the frontend`)
  }
}

// Optional fields must not crash the card if absent
const optional = schemaProps.filter((f) => !required.has(f))
for (const field of optional) {
  const guarded =
    pageSrc.includes(`result.${field}`) || pageSrc.includes(`'${field}'`)
  if (!guarded) console.warn(`WARN: optional field '${field}' never rendered`)
}

// Backend forwards output verbatim: result spread + type tag (see backend runner+app)
const runnerSrc = readFileSync(
  fileURLToPath(new URL('../backend/runner/investigate.mjs', import.meta.url)),
  'utf8',
)
if (!runnerSrc.includes("{ type: 'result', mode, ...output.value }")) {
  fail('runner does not forward structured output verbatim')
}

// Heatmap contract: risk-heatmap schema vs the heatmap card in page.tsx
const heat = agents['risk-heatmap']
if (!heat) fail('risk-heatmap agent not found')
if (heat.outputMode !== 'structured_output') {
  fail("risk-heatmap outputMode must be 'structured_output'")
}
const fnProps = heat.outputSchema?.properties?.functions?.items?.properties
if (!fnProps?.verdict || !fnProps?.reason || !fnProps?.line) {
  fail('risk-heatmap function items must have verdict/reason/line')
}
for (const field of heat.outputSchema?.required ?? []) {
  if (!pageSrc.includes(`heatmap.${field}`)) {
    fail(`heatmap field '${field}' is not rendered by the frontend`)
  }
}

console.log(
  `CONTRACT_OK: ${schemaProps.length} fields (${[...required].length} required, ` +
    `${optional.length} optional), verdicts ${VERDICTS.join('/')} all handled`,
)
