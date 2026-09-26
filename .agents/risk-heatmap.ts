import type { AgentDefinition } from '@codebuff/sdk'

export const riskHeatmap: AgentDefinition = {
  id: 'risk-heatmap',
  displayName: 'Risk Heatmap',
  model: 'base',
  spawnerPrompt:
    'Spawn when you need a risk ranking of every function in a single legacy file, so the developer knows which lines are dangerous before they start reading.',
  toolNames: ['read_files', 'code_search', 'glob', 'spawn_agents'],
  spawnableAgents: [
    'history-analyst',
    'docs-analyst',
    'dependents-mapper',
    'test-coverage-checker',
  ],
  outputMode: 'structured_output',
  outputSchema: {
    type: 'object',
    properties: {
      file: { type: 'string', description: 'The scanned file path' },
      functions: {
        type: 'array',
        description: 'Every function in the file, hottest first',
        items: {
          type: 'object',
          properties: {
            name: { type: 'string' },
            line: { type: 'integer', description: 'Line where the function starts' },
            verdict: { type: 'string', enum: ['Safe', 'Risky', 'Needs Review'] },
            confidence: { type: 'string', enum: ['High', 'Medium', 'Low'] },
            reason: {
              type: 'string',
              description: 'One sentence naming the strongest evidence',
            },
          },
          required: ['name', 'line', 'verdict', 'confidence', 'reason'],
        },
      },
      summary: {
        type: 'string',
        description: 'One paragraph: overall state of the file and where to start',
      },
    },
    required: ['file', 'functions', 'summary'],
  },
  instructionsPrompt: `You are the RISK HEATMAP orchestrator. Input: a file path inside the current repo. If the file does not exist, output functions: [] and say so in the summary.

PHASE 1 (deterministic, no LLM): read the file and list every function it defines, with its starting line. Use read_files; if the path is unclear, code_search/glob to locate it first.

PHASE 2 (parallel checks): spawn the 4 check agents — history-analyst, docs-analyst, dependents-mapper, test-coverage-checker — IN ONE spawn_agents call so they run in parallel. Prompt each with ALL functions listed, asking for one report PER FUNCTION, clearly separated with headers like "FUNCTION: <name>". Instruct them to follow their own output format inside each section and set INCONCLUSIVE per function when evidence is thin.

PHASE 3: STEP_ALL — then apply the SAME verdict rules as the investigate-safety merger, PER FUNCTION:
- Risky: no test coverage AND at least one dependent; or HOT churn / SUSPICIOUS history; or docs WARNED.
- Safe: documented current AND covered; or self-contained AND not uncovered; or single-intro AND self-contained.
- Needs Review: everything else; always when 2+ reports are inconclusive or evidence conflicts.

Rank functions hottest first: Risky before Needs Review before Safe; within a group, more dependents first. Give each function a one-sentence reason citing its strongest piece of evidence (e.g. "3 commits since intro incl. a revert; zero tests; called from api.ts").

In the summary, state the file's overall health and the single safest starting point for a developer who wants to clean it up.`,
  handleSteps: function* (ctx) {
    const file =
      (ctx && ctx.params && ctx.params.file) || (ctx && ctx.prompt) || ''

    // STEP_ALL first: the LLM lists the functions (phase 1) and then spawns
    // the 4 checks itself in one parallel call (phase 2), per instructions.
    yield 'STEP_ALL'
  },
}

export default riskHeatmap
