#!/usr/bin/env node
// Bridges the Codebuff investigation modes to the FastAPI backend.
// Protocol: one JSON request on stdin -> NDJSON events on stdout.
// Events: check_start | check_finish | result | error
// Modes:  "investigate" (single target verdict) | "heatmap" (whole-file ranking)
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { CodebuffClient, loadLocalAgents } from '@codebuff/sdk'

const here = dirname(fileURLToPath(import.meta.url))
const projectRoot = resolve(here, '..', '..')

const MODES = {
  investigate: {
    agent: 'investigate-safety',
    promptKey: 'target',
    prompt: (t) =>
      `Investigate whether this code is safe to change or delete: ${t}`,
    paramKey: 'target',
  },
  heatmap: {
    agent: 'risk-heatmap',
    promptKey: 'file',
    prompt: (f) => `Build a risk heatmap for every function in this file: ${f}`,
    paramKey: 'file',
  },
}

function emit(event) {
  process.stdout.write(JSON.stringify(event) + '\n')
}

function fail(message, statusCode) {
  emit({ type: 'error', message: friendlyError(message, statusCode) })
  process.exit(1)
}

function friendlyError(message, statusCode) {
  const msg = String(message ?? '')
  if (statusCode === 402 || /payment required|out of credits/i.test(msg)) {
    return (
      'Your Codebuff account is out of credits. Add credits or a plan at ' +
      'https://www.codebuff.com (account billing), then run the investigation again.'
    )
  }
  if (/invalid api key|unauthorized|401/i.test(msg)) {
    return (
      'Your CODEBUFF_API_KEY was rejected. Get a fresh key at ' +
      'https://www.codebuff.com/api-keys and update .env.'
    )
  }
  return msg
}

async function main() {
  let raw
  try {
    raw = readFileSync(0, 'utf8')
  } catch (err) {
    return fail(`Could not read request from stdin: ${err?.message ?? err}`)
  }

  let req
  try {
    req = JSON.parse(raw)
  } catch (err) {
    return fail(`Invalid JSON request: ${err?.message ?? err}`)
  }

  const mode = MODES[req.mode] ? req.mode : 'investigate'
  const modeCfg = MODES[mode]
  const subject = String(req[modeCfg.promptKey] ?? '').trim()
  if (!subject) return fail(`Missing required field: ${modeCfg.promptKey}`)

  const apiKey = process.env.CODEBUFF_API_KEY
  if (!apiKey) {
    return fail(
      'CODEBUFF_API_KEY is not set. Copy .env.example to .env and add your key from codebuff.com/api-keys',
    )
  }

  const repoPath = resolve(projectRoot, req.repo_path ?? 'target-repo')

  const { agents, validationErrors } = await loadLocalAgents({
    agentsPath: resolve(projectRoot, '.agents'),
    validate: true,
  })
  if (validationErrors && validationErrors.length > 0) {
    return fail(
      `Invalid agent definitions: ${validationErrors
        .map((e) => `${e.filePath}: ${e.message}`)
        .join('; ')}`,
    )
  }
  if (!agents[modeCfg.agent]) {
    return fail(`${modeCfg.agent} agent not found in .agents/`)
  }

  const client = new CodebuffClient({ apiKey, cwd: repoPath })

  const emitted = new Set()
  const { output } = await client.run({
    agent: modeCfg.agent,
    prompt: modeCfg.prompt(subject),
    params: { [modeCfg.paramKey]: subject },
    agentDefinitions: Object.values(agents),
    handleEvent: (event) => {
      if (event.type === 'subagent_start' || event.type === 'subagent_finish') {
        const key = `${event.type}:${event.agentId}`
        if (emitted.has(key)) return
        emitted.add(key)
        emit({
          type: event.type === 'subagent_start' ? 'check_start' : 'check_finish',
          agent_id: event.agentId,
          agent_type: event.agentType,
          display_name: event.displayName,
        })
      } else if (event.type === 'error') {
        emit({ type: 'error', message: event.message })
      }
    },
  })

  if (output.type === 'structuredOutput' && output.value) {
    emit({ type: 'result', mode, ...output.value })
    return
  }
  if (output.type === 'error') {
    return fail(output.message, output.statusCode)
  }
  fail(
    `Run ended without a structured result (output type: ${output.type})`,
  )
}

main().catch((err) => {
  fail(err instanceof Error ? err.message : String(err))
})
