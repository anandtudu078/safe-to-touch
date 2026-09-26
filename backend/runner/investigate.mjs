#!/usr/bin/env node
// Bridges the investigate-safety Codebuff mode to the FastAPI backend.
// Protocol: one JSON request on stdin -> NDJSON events on stdout.
// Events: check_start | check_finish | result | error
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { CodebuffClient, loadLocalAgents } from '@codebuff/sdk'

const here = dirname(fileURLToPath(import.meta.url))
const projectRoot = resolve(here, '..', '..')

function emit(event) {
  process.stdout.write(JSON.stringify(event) + '\n')
}

function fail(message) {
  emit({ type: 'error', message })
  process.exit(1)
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

  const target = typeof req.target === 'string' ? req.target.trim() : ''
  if (!target) return fail('Missing required field: target')

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
  if (!agents['investigate-safety']) {
    return fail('investigate-safety agent not found in .agents/')
  }

  const client = new CodebuffClient({ apiKey, cwd: repoPath })

  const emitted = new Set()
  const { output } = await client.run({
    agent: 'investigate-safety',
    prompt: `Investigate whether this code is safe to change or delete: ${target}`,
    params: { target },
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
    emit({ type: 'result', ...output.value })
    return
  }
  if (output.type === 'error') {
    return fail(output.message)
  }
  fail(
    `Investigation ended without a structured verdict (output type: ${output.type})`,
  )
}

main().catch((err) => {
  fail(err instanceof Error ? err.message : String(err))
})
