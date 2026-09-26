import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))

/** @type {import('next').NextConfig} */
const nextConfig = {
  // The frontend is its own npm workspace; don't let Next infer the repo
  // root as workspace root (it sees the root package-lock.json too).
  outputFileTracingRoot: __dirname,
  // Single-container deploys: FastAPI serves the exported static files.
  output: 'export',
  images: { unoptimized: true },
}

export default nextConfig
