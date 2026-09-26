// Fails if any git-tracked file contains a real-looking Codebuff API key.
// Guards against committing secrets (e.g. pasting a key into .env.example).
// Run with: npm run check:secrets
import { execSync } from 'node:child_process'

const tracked = execSync('git ls-files', { encoding: 'utf8' })
  .split('\n')
  .filter(Boolean)

const offenders = []
for (const file of tracked) {
  let content
  try {
    content = require('node:fs').readFileSync(file, 'utf8')
  } catch {
    continue // deleted or binary
  }
  // Codebuff PATs start with cb-pat- followed by a long hex string
  if (/cb-pat-[0-9a-f]{16,}/.test(content)) {
    offenders.push(file)
  }
}

if (offenders.length > 0) {
  console.error('FAIL: API-key-like secrets found in tracked files:')
  for (const f of offenders) console.error(`  ${f}`)
  console.error('Move them into .env (gitignored) and rotate the key if it was pushed.')
  process.exit(1)
}

console.log(`SECRETS_OK: scanned ${tracked.length} tracked files, no API keys found`)
