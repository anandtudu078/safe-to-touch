import type { AgentDefinition } from '@codebuff/sdk'

export const investigateSafety: AgentDefinition = {
  id: 'investigate-safety',
  displayName: 'Investigate Safety',
  model: 'base',
  spawnerPrompt:
    'Spawn when a user asks whether a specific file/line/function in a legacy codebase is safe to change or delete. Runs 4 checks in parallel (history, docs, dependents, tests) and merges them into a Safe/Risky/Needs Review verdict.',
  toolNames: ['spawn_agents'],
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
      verdict: { type: 'string', enum: ['Safe', 'Risky', 'Needs Review'] },
      confidence: { type: 'string', enum: ['High', 'Medium', 'Low'] },
      summary: { type: 'string', description: 'One-paragraph verdict rationale' },
      history: { type: 'string', description: 'One short sentence: what the History check found' },
      docs: { type: 'string', description: 'One short sentence: what the Docs check found' },
      dependents: { type: 'string', description: 'One short sentence: what the Dependents check found' },
      tests: { type: 'string', description: 'One short sentence: what the Tests check found' },
      evidence: {
        type: 'object',
        description: 'Raw evidence excerpts per check, for drill-down display',
        properties: {
          history: { type: 'string', description: 'Commit hashes, dates, subjects, churn summary — 2-6 lines' },
          docs: { type: 'string', description: 'Verbatim doc quote(s) with source file — 1-4 lines' },
          dependents: { type: 'string', description: 'The DETAIL lines: dependent file + how it uses the target' },
          tests: { type: 'string', description: 'TEST_FILES and WHAT_ASSERTED lines, or the no-coverage statement' },
        },
        required: ['history', 'docs', 'dependents', 'tests'],
      },
      suggestions: {
        type: 'array',
        items: { type: 'string' },
        description: '0-3 concrete next steps for the developer',
      },
    },
    required: ['verdict', 'confidence', 'summary', 'history', 'docs', 'dependents', 'tests'],
  },
  instructionsPrompt: `You are the MERGE step of a "should I touch this" investigation. The 4 parallel check results are in your message history as the tool result of spawn_agents (each item carries an agentType — history-analyst, docs-analyst, dependents-mapper, test-coverage-checker — plus that agent's report; the report body may be nested inside message content, extract the plain text).

Apply these rules EXACTLY, in order:

RISKY if any of:
- Tests check: COVERED is no (no test asserts on this code) AND Dependents check: DEPENDENT_COUNT > 0
- History check: CHURN is HOT, or SUSPICIOUS is yes
- Docs check: STATUS is WARNED

SAFE if any of:
- Docs check: STATUS is DOCUMENTED_CURRENT AND Tests check: COVERED is yes or indirectly
- Dependents check: SELF_CONTAINED is yes AND Tests check: COVERED is not no AND Docs check: STATUS is not WARNED
- History check: CHURN is SINGLE_INTRO AND Dependents check: SELF_CONTAINED is yes

NEEDS REVIEW otherwise, and ALWAYS if:
- Two or more reports are INCONCLUSIVE, or
- Reports directly conflict (e.g. Docs says DOCUMENTED_CURRENT but Dependents found many external callers with no tests).

CONFIDENCE:
- High: all 4 reports concrete (none INCONCLUSIVE) and the rule that fired was unambiguous.
- Medium: exactly 1 report INCONCLUSIVE, or the verdict comes from a weaker rule combination.
- Low: 2+ reports INCONCLUSIVE, or the target could not be located in the repo.

For each of history/docs/dependents/tests write ONE short sentence (max ~20 words) summarizing that check's finding, e.g. "History: added in commit a1b2c3d (2023-04) to fix a timezone parsing bug; 2 later fixes.". If a report was INCONCLUSIVE, say so plainly.

Also, before/alongside the structured output, print a compact human-readable card like:
  VERDICT: Risky (Medium confidence)
  Why: <summary>
  History: ...
  Docs: ...
  Dependents: ...
  Tests: ...
so a CLI reader sees the verdict without parsing JSON.

EVIDENCE: fill the evidence object with the raw excerpts a developer would otherwise dig up manually:
- history: the actual commit line(s) (hash, date, subject) and the CHURN line from the History report.
- docs: the verbatim quote(s) and the file they came from (the QUOTE and SOURCE lines).
- dependents: the per-file DETAIL lines from the Dependents report (path + how it uses the target).
- tests: the TEST_FILES and WHAT_ASSERTED lines, or the exact no-coverage statement.`,
  handleSteps: function* (ctx) {
    const target =
      (ctx && ctx.params && ctx.params.target) ||
      (ctx && ctx.prompt) ||
      ''

    const checkPrompt = `TARGET under investigation: ${target}

Investigate this exact target in the current repo. Follow your own instructions for steps and output format. Read-only: change nothing.`

    // Fan out all 4 checks in one call => they run in parallel.
    const { toolResult } = yield {
      toolName: 'spawn_agents',
      input: {
        agents: [
          { agent_type: 'history-analyst', prompt: checkPrompt },
          { agent_type: 'docs-analyst', prompt: checkPrompt },
          { agent_type: 'dependents-mapper', prompt: checkPrompt },
          { agent_type: 'test-coverage-checker', prompt: checkPrompt },
        ],
      },
    }

    // A failed fan-out shows up as no results, or JSON parts carrying an errorMessage.
    const spawnFailed =
      !toolResult ||
      toolResult.length === 0 ||
      toolResult.some((part) => {
        if (part.type !== 'json') return false
        const value: unknown = part.value
        return (
          typeof value === 'object' &&
          value !== null &&
          'errorMessage' in value
        )
      })

    if (spawnFailed) {
      yield {
        toolName: 'spawn_agents',
        input: {
          agents: [
            {
              agent_type: 'history-analyst',
              prompt: `TARGET: ${target}\n\nThe parallel fan-out of the 4 checks failed. Re-run ONLY your history check for this target and produce your normal report.`,
            },
          ],
        },
      }
    }

    // STEP_ALL: the merger LLM applies the verdict rules and emits structured output.
    yield 'STEP_ALL'
  },
}

export default investigateSafety
