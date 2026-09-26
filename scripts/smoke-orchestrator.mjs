// Offline unit test of the investigate-safety orchestrator's handleSteps logic.
// Drives the generator protocol directly — no API key, no network.
// Verifies: 4-agent parallel fan-out, fallback on failed fan-out, and the
// STEP_ALL handoff to the merge step. Run with: npm run smoke:orchestrator
import { fileURLToPath } from 'node:url'
import { loadLocalAgents } from '@codebuff/sdk'

const agentsPath = fileURLToPath(new URL('../.agents', import.meta.url))
const { agents, validationErrors } = await loadLocalAgents({
  agentsPath,
  validate: true,
})

if (validationErrors && validationErrors.length > 0) {
  console.error('Agent validation errors:', validationErrors)
  process.exit(1)
}

const def = agents['investigate-safety']
if (!def || !def.handleSteps) {
  console.error('investigate-safety with handleSteps not found')
  process.exit(1)
}

// loadLocalAgents serializes handleSteps to a string; the Codebuff runtime
// rebuilds it with eval('(' + src + ')'). Mirror that reconstruction here.
const handleSteps =
  typeof def.handleSteps === 'function'
    ? def.handleSteps
    : eval('(' + def.handleSteps + ')')
if (typeof handleSteps !== 'function') {
  console.error('handleSteps did not reconstruct into a function')
  process.exit(1)
}

function fail(msg) {
  console.error(`FAIL: ${msg}`)
  process.exit(1)
}

function assert(cond, msg) {
  if (!cond) fail(msg)
}

const EXPECTED = [
  'history-analyst',
  'docs-analyst',
  'dependents-mapper',
  'test-coverage-checker',
]

const agentState = { agentId: 'test-run', parentId: 'root', messageHistory: [] }

// --- Case 1: healthy fan-out -> all 4 agents in one parallel call -> STEP_ALL
{
  const gen = handleSteps({
    agentState,
    prompt: 'src/utils/date.ts:120',
    params: {},
  })

  const step1 = gen.next()
  assert(
    step1.value?.toolName === 'spawn_agents',
    `expected spawn_agents yield, got ${JSON.stringify(step1.value)}`,
  )
  const spawned = step1.value.input.agents
  assert(spawned.length === 4, `expected 4 spawned agents, got ${spawned.length}`)
  const types = spawned.map((a) => a.agent_type).sort()
  assert(
    JSON.stringify(types) === JSON.stringify([...EXPECTED].sort()),
    `spawned agents mismatch: ${types.join(', ')}`,
  )
  assert(
    spawned.every((a) => a.prompt.includes('src/utils/date.ts:120')),
    'spawn prompts must carry the target',
  )

  const okResult = [
    { type: 'json', value: { agentType: 'history-analyst', report: 'COMMIT: abc' } },
    { type: 'json', value: { agentType: 'docs-analyst', report: 'STATUS: UNDOCUMENTED' } },
    { type: 'json', value: { agentType: 'dependents-mapper', report: 'DEPENDENT_COUNT: 0' } },
    { type: 'json', value: { agentType: 'test-coverage-checker', report: 'COVERED: yes' } },
  ]
  const step2 = gen.next({ agentState, toolResult: okResult, stepsComplete: false })
  assert(step2.value === 'STEP_ALL', `expected STEP_ALL, got ${JSON.stringify(step2.value)}`)
  console.log('FANOUT_OK: 4 checks spawn in parallel, merge step handed off')
}

// --- Case 2: failed fan-out (empty result) -> fallback history re-run -> STEP_ALL
{
  const gen = handleSteps({
    agentState,
    prompt: 'parseThing in src/thing.ts',
    params: {},
  })

  gen.next() // first spawn_agents (already shape-checked in case 1)
  const fallback = gen.next({ agentState, toolResult: [], stepsComplete: false })
  assert(
    fallback.value?.toolName === 'spawn_agents',
    'empty fan-out result must trigger fallback spawn',
  )
  const retry = fallback.value.input.agents
  assert(retry.length === 1, 'fallback should retry exactly one agent')
  assert(
    retry[0].agent_type === 'history-analyst',
    `fallback agent should be history-analyst, got ${retry[0].agent_type}`,
  )
  const step3 = gen.next({ agentState, toolResult: [], stepsComplete: false })
  assert(step3.value === 'STEP_ALL', `expected STEP_ALL after fallback, got ${JSON.stringify(step3.value)}`)
  console.log('FALLBACK_OK: failed fan-out retries via history-analyst, then merges')
}

// --- Case 3: error-part result is treated as a failure too
{
  const gen = handleSteps({ agentState, prompt: 'x.ts:1', params: {} })
  gen.next()
  const fallback = gen.next({
    agentState,
    toolResult: [{ type: 'json', value: { errorMessage: 'spawn failed' } }],
    stepsComplete: false,
  })
  assert(
    fallback.value?.toolName === 'spawn_agents',
    'error-part result must trigger fallback spawn',
  )
  console.log('ERROR_PART_OK: error results route to the fallback path')
}

console.log('ORCHESTRATOR_SMOKE_OK')
