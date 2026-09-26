#!/usr/bin/env bash
# Creates the synthetic "legacy" demo repo used for demos and smoke tests.
# Usage: bash scripts/create-demo-repo.sh /path/to/target-repo
set -euo pipefail

DEST="${1:-target-repo}"
rm -rf "$DEST"
mkdir -p "$DEST/src" "$DEST/tests"
cd "$DEST"

git init -q
git config user.email demo@example.com
git config user.name Demo

cat > src/date.ts <<'EOF'
export function parseDateString(input: string): Date {
  // NOTE: legacy parser, do not touch without reading DECISIONS in README
  const normalized = input.trim().replace(/Z$/, '')
  const [datePart, timePart] = normalized.split('T')
  const [y, m, d] = datePart.split('-').map(Number)
  if (timePart) {
    const [hh, mm] = timePart.split(':').map(Number)
    return new Date(y, m - 1, d, hh, mm)
  }
  return new Date(y, m - 1, d)
}

export function formatDate(date: Date): string {
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
}
EOF
git add . && git commit -qm "add date parsing utilities"

cat > src/api.ts <<'EOF'
import { parseDateString } from './date'

export async function fetchSince(dateInput: string) {
  const since = parseDateString(dateInput)
  const res = await fetch('/api/items?since=' + since.toISOString())
  return res.json()
}
EOF
git add . && git commit -qm "add API client using date parser"

printf '\n// HOTFIX 2024-03: strip trailing Z suffix before parsing (prod crash on ISO strings)\n' >> src/date.ts
git add src/date.ts && git commit -qm "hotfix: strip trailing Z before parsing (crashed on ISO dates)"

cat > README.md <<'EOF'
# Demo Legacy App

## Date handling
`formatDate` is the stable public helper - use it everywhere.

`parseDateString` is our in-house ISO-ish parser. It is intentionally
naive: it drops the timezone suffix because the backend expects naive
datetimes (see 2024 hotfix). Changing this will shift every stored
timestamp. Coordinate with the platform team first.
EOF
git add . && git commit -qm "docs: explain date parsing decisions"

cat > tests/date.test.ts <<'EOF'
import { formatDate } from '../src/date'

test('formatDate pads months and days', () => {
  expect(formatDate(new Date(2024, 0, 5))).toBe('2024-01-05')
})
EOF
git add . && git commit -qm "add tests for formatDate"

echo "demo repo created at $DEST ($(git rev-list --count HEAD) commits)"
