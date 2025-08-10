'use server'

import fs from 'fs/promises'
import path from 'path'
import { marked } from 'marked'

export default async function ThreatModelPage() {
  const mdPath = path.resolve(process.cwd(), '..', 'docs', 'roadmap', 'threat-model.md')
  let content = '# Threat Model\n\n_Not found_'
  try {
    content = await fs.readFile(mdPath, 'utf8')
  } catch (e) {
    content = '# Threat Model\n\nCould not load threat-model.md at build time.'
  }

  const html = marked.parse(content)

  return (
    <div className="max-w-4xl mx-auto px-6 py-10">
      <header className="mb-8">
        <h1 className="text-3xl md:text-4xl font-bold text-white mb-2">Threat Model</h1>
        <p className="text-gray-400">Multi‑Agent Collaboration Threat Model and Key Insights</p>
      </header>

      <article
        className="prose prose-invert max-w-none prose-headings:text-white prose-p:text-gray-300 prose-li:text-gray-300 prose-strong:text-white prose-code:text-purple-300"
        dangerouslySetInnerHTML={{ __html: html as string }}
      />
    </div>
  )
}

