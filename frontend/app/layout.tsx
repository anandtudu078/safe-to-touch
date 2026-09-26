import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'Should I Touch This',
  description:
    'Paste a line of legacy code. Four parallel checks. One verdict: Safe, Risky, or Needs Review.',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  )
}
