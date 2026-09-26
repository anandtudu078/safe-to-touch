// Validates that all local agent definitions in .agents/ load cleanly via the SDK.
// Run with: npm run smoke:agents
import { fileURLToPath } from 'node:url'
import { loadLocalAgents } from '@codebuff/sdk'

const agentsPath = fileURLToPath(new URL('../.agents', import.meta.url))
const { agents, validationErrors } = await loadLocalAgents({
  agentsPath,
  validate: true,
})

if (validationErrors && validationErrors.length > 0) {
  console.error('Agent validation errors:')
  for (const e of validationErrors) {
    console.error(`  ${e.filePath}: ${e.message}`)
  }
  process.exit(1)
}

const ids = Object.keys(agents)
const expected = [
  'investigate-safety',
  'risk-heatmap',
  'history-analyst',
  'docs-analyst',
  'dependents-mapper',
  'test-coverage-checker',
]

const missing = expected.filter((id) => !ids.includes(id))
if (missing.length > 0) {
  console.error(`Missing agents: ${missing.join(', ')} (loaded: ${ids.join(', ')})`)
  process.exit(1)
}

for (const id of ['investigate-safety', 'risk-heatmap']) {
  const orchestrator = agents[id]
  if (!orchestrator.spawnableAgents || orchestrator.spawnableAgents.length !== 4) {
    console.error(`${id} must spawn exactly 4 subagents`)
    process.exit(1)
  }
  if (orchestrator.outputMode !== 'structured_output') {
    console.error(`${id} must emit structured output`)
    process.exit(1)
  }
}

console.log(`SMOKE_OK: ${ids.length} agents loaded — ${ids.join(', ')}`)
