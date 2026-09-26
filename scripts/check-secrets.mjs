// Fails if any git-tracked file contains a real-looking API key.
// Guards against committing secrets (e.g. pasting a key into .env.example).
// Run with: npm run check:secrets
import { readFileSync } from 'node:fs'
import { execSync } from 'node:child_process'

const tracked = execSync('git ls-files', { encoding: 'utf8' })
  .split('\n')
  .filter(Boolean)

// Patterns for keys that must never be committed
const SECRET_PATTERNS = [
  // Old Codebuff PATs
  { label: 'Codebuff PAT', re: /cb-pat-[0-9a-f]{16,}/ },
  // Google / Gemini API keys (AIza followed by 35 base64url chars)
  { label: 'Google API key', re: /AIza[0-9A-Za-z\-_]{35}/ },
  // Generic high-entropy assignments: KEY=<long token>
  { label: 'generic secret assignment', re: /(?:API_KEY|SECRET|TOKEN)\s*=\s*["']?[A-Za-z0-9+/\-_]{32,}["']?/ },
]

const offenders = []
for (const file of tracked) {
  // Skip binary files and lock files (noisy)
  if (/\.(png|jpg|gif|ico|woff2?|ttf|eot|lock|pack)$/.test(file)) continue
  let content
  try {
    content = readFileSync(file, 'utf8')
  } catch {
    continue // deleted or binary
  }
  for (const { label, re } of SECRET_PATTERNS) {
    if (re.test(content)) {
      offenders.push({ file, label })
    }
  }
}

if (offenders.length > 0) {
  console.error('FAIL: API-key-like secrets found in tracked files:')
  for (const { file, label } of offenders) console.error(`  [${label}] ${file}`)
  console.error('Move them into .env (gitignored) and rotate the key if it was pushed.')
  process.exit(1)
}

console.log(`SECRETS_OK: scanned ${tracked.length} tracked files, no API keys found`)
