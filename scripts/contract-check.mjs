// Verifies the end-to-end output contract without an API key:
//   backend pydantic schemas  ==  frontend result-card fields
// Run with: npm run smoke:contract
import { readFileSync, existsSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { spawnSync } from 'node:child_process'

function fail(msg) {
  console.error(`FAIL: ${msg}`)
  process.exit(1)
}

// Extract the field lists straight from the pydantic schemas via the venv python.
const root = fileURLToPath(new URL('..', import.meta.url))
function findPython() {
  // Prefer the project venv, then fall back to a system interpreter
  // (CI installs backend/requirements.txt into the system Python).
  for (const p of [`${root}.venv/Scripts/python.exe`, `${root}.venv/bin/python`]) {
    if (existsSync(p)) return p
  }
  for (const cmd of ['python', 'python3']) {
    if (spawnSync(cmd, ['--version'], { encoding: 'utf8' }).status === 0) return cmd
  }
  return null
}
const python = findPython()
if (!python) {
  fail('No Python interpreter found; run: python -m venv .venv && pip install -r backend/requirements.txt')
}

const extract = [
  "import sys; sys.path.insert(0, 'backend');",
  'from app.schemas import VerdictResult, HeatmapFunction;',
  'import json;',
  "print(json.dumps({'verdict': list(VerdictResult.model_fields),",
  "'required': [k for k, v in VerdictResult.model_fields.items() if v.is_required()],",
  "'heat': list(HeatmapFunction.model_fields)}))",
].join(' ')
const res = spawnSync(python, ['-c', extract], { encoding: 'utf8', cwd: root })
if (res.status !== 0) {
  if (res.stderr.includes('ModuleNotFoundError')) {
    fail(`Python deps missing; run: pip install -r backend/requirements.txt (${res.stderr.trim()})`)
  }
  fail(`schema extraction failed: ${res.stderr}`)
}
const schema = JSON.parse(res.stdout)
const schemaProps = schema.verdict
const required = new Set(schema.required)
if (schemaProps.length === 0) fail('VerdictResult has no fields')

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

// Backend forwards the pydantic verdict verbatim into the result event
const mainSrc = readFileSync(
  fileURLToPath(new URL('../backend/app/main.py', import.meta.url)),
  'utf8',
)
if (!mainSrc.includes('**result.model_dump()')) {
  fail('backend does not forward the verdict model verbatim')
}
if (!mainSrc.includes('**merged.model_dump()')) {
  fail('backend does not forward the heatmap model verbatim')
}
// SSE display names must match the frontend check keys exactly
for (const display of ['History Analyst', 'Docs Analyst', 'Dependents Mapper', 'Test Coverage Checker']) {
  if (!mainSrc.includes(`"${display}"`)) fail(`backend missing canonical check name '${display}'`)
  if (!pageSrc.includes(`'${display}'`)) fail(`frontend missing check key '${display}'`)
}

// Heatmap contract: HeatmapFunction schema vs the heatmap card in page.tsx
// (schema.heat is a list of field names)
const heatFields = new Set(schema.heat)
for (const field of ['verdict', 'reason', 'line', 'name', 'confidence']) {
  if (!heatFields.has(field)) fail(`HeatmapFunction missing field '${field}'`)
}
for (const field of heatFields) {
  if (!pageSrc.includes(`f.${field}`) && !pageSrc.includes(`'${field}'`)) {
    fail(`heatmap field '${field}' is not rendered by the frontend`)
  }
}

console.log(
  `CONTRACT_OK: ${schemaProps.length} fields (${[...required].length} required, ` +
    `${optional.length} optional), verdicts ${VERDICTS.join('/')} all handled`,
)
