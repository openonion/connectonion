/*
  @date: 2025-01-01
  @description: CLI Reference Page
  
  DESIGN ISSUES TO FIX:
  
  1. **Command Documentation Structure** (Priority: HIGH)
     - Commands shown without clear syntax patterns
     - Missing required vs optional parameter indicators
     - No command output examples shown
     - Fix: Add syntax diagrams, use [optional] notation, show example outputs
  
  2. **Missing Copy Button** (Priority: HIGH)
     - No copy-all-content button as required by CLAUDE.md
     - Individual command blocks lack context when copied
     - Fix: Add CopyMarkdownButton, ensure commands copy with descriptions
  
  3. **Visual Hierarchy** (Priority: MEDIUM)
     - All commands look equally important
     - No quick command reference card
     - Missing "most used commands" section
     - Fix: Highlight primary commands, add command cheat sheet, group by frequency
  
  4. **Navigation Issues** (Priority: MEDIUM)
     - Long page with no table of contents
     - No anchor links to specific commands
     - Missing search functionality
     - Fix: Add sticky TOC, implement command search, add deep linking
  
  5. **Template Examples** (Priority: LOW)
     - Template options not visually differentiated
     - Missing preview of what each template creates
     - No comparison table of templates
     - Fix: Add template preview cards, create comparison matrix, show file structure
  
  NAVIGATION INCONSISTENCY FOUND (2025-01-02):
  - Uses PageNavigation component (line 46) for automatic Previous/Next
  - Has breadcrumb navigation at top
  - Has CopyMarkdownButton component
  - Consistent with main docs but different from examples/* pages
  - Shows proper integration of standard navigation components
*/

'use client'

import { useState } from 'react'
import { Copy, Check, Terminal, ArrowRight, FileText, Package, GitBranch, AlertCircle, Zap, Code, Folder, BookOpen, ChevronRight } from 'lucide-react'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { okaidia as monokai } from 'react-syntax-highlighter/dist/esm/styles/prism'
import Link from 'next/link'
import { CommandBlock } from '../../components/CommandBlock'
import { FileTree } from '../../components/FileTree'
import { ContentNavigation } from '../../components/ContentNavigation'
import { CopyMarkdownButton } from '../../components/CopyMarkdownButton'

export default function CLIPage() {
  const [copiedId, setCopiedId] = useState<string | null>(null)

  const copyToClipboard = (text: string, id: string) => {
    navigator.clipboard.writeText(text)
    setCopiedId(id)
    setTimeout(() => setCopiedId(null), 2000)
  }

  const pageContent = `# ConnectOnion CLI Reference

Quick reference for the ConnectOnion command-line interface.

## Installation
\`\`\`bash
pip install connectonion
\`\`\`

## Commands

### co init [options]
Initialize a new ConnectOnion agent project.

**Options:**
- \`--template, -t <name>\` - Choose template: meta-agent (default), playwright
- \`--force\` - Overwrite existing files

**Examples:**
\`\`\`bash
# Create default meta-agent
co init

# Create playwright agent
co init --template playwright
\`\`\`

## Templates

### Meta-Agent (Default)
A development assistant with built-in ConnectOnion knowledge and code generation tools.

### Playwright Template  
Web automation agent with browser control capabilities.

## Quick Command Reference

| Command | Description |
|---------|-------------|
| \`co init\` | Initialize new project |
| \`co init -t playwright\` | Create playwright agent |
| \`co --version\` | Show version |
| \`co --help\` | Show help |
`



  return (
    <div className="px-4 md:px-8 py-8 md:py-12 lg:py-12">
      <div className="max-w-4xl mx-auto">
      {/* Header with Copy Button */}
      <div className="flex flex-col lg:flex-row lg:items-start lg:justify-between gap-4 mb-8">
        <div className="flex-1">
          {/* Breadcrumb */}
          <nav className="flex items-center gap-2 text-sm text-gray-400 mb-4">
            <Link href="/" className="hover:text-white transition-colors">Home</Link>
            <ArrowRight className="w-4 h-4" />
            <span className="text-white">CLI Reference</span>
          </nav>
          
          <h1 className="text-3xl md:text-4xl font-bold text-white mb-4">CLI Reference</h1>
          <p className="text-lg md:text-xl text-gray-300">
            Quickly scaffold and manage ConnectOnion agent projects with the CLI.
          </p>
        </div>
        <CopyMarkdownButton 
          content={pageContent}
          filename="cli-reference.md"
          className="flex-shrink-0"
        />
      </div>
      
      {/* Quick Command Cheat Sheet */}
      <div className="mb-12 p-4 bg-gradient-to-r from-blue-900/20 to-purple-900/20 border border-blue-500/30 rounded-lg">
        <h2 className="text-base font-semibold text-white mb-3 flex items-center gap-2">
          <BookOpen className="w-4 h-4 text-blue-400" />
          Quick Reference
        </h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-sm">
          <div className="font-mono text-blue-300">co init <span className="text-gray-400">→ Create project</span></div>
          <div className="font-mono text-blue-300">co init -t playwright <span className="text-gray-400">→ Web agent</span></div>
          <div className="font-mono text-blue-300">co --version <span className="text-gray-400">→ Show version</span></div>
          <div className="font-mono text-blue-300">co --help <span className="text-gray-400">→ Get help</span></div>
        </div>
      </div>

      {/* Installation */}
      <section className="mb-16">
        <h2 className="text-2xl font-bold text-white mb-6 flex items-center gap-3">
          <Package className="w-6 h-6 text-blue-400" />
          Installation
        </h2>
        
        <p className="text-gray-300 mb-6">
          The CLI is automatically installed when you install ConnectOnion:
        </p>

        <CommandBlock 
          commands={['pip install connectonion']}
        />

        <div className="bg-gradient-to-b from-blue-900/30 to-blue-800/10 border border-blue-500/30 rounded-lg p-4 mt-6">
          <p className="text-blue-200">
            This provides two equivalent commands: <code className="bg-black/30 px-2 py-1 rounded">co</code> (short form) 
            and <code className="bg-black/30 px-2 py-1 rounded">connectonion</code> (full form)
          </p>
        </div>
      </section>

      {/* co init Command */}
      <section className="mb-16">
        <h2 className="text-2xl font-bold text-white mb-6 flex items-center gap-3">
          <Terminal className="w-6 h-6 text-green-400" />
          co init
        </h2>
        
        <p className="text-gray-300 mb-6">
          Initialize a new ConnectOnion agent project in the current directory.
        </p>

        {/* Basic Usage */}
        <div className="mb-8">
          <h3 className="text-lg font-semibold text-white mb-4">Basic Usage</h3>
          
          <div className="space-y-4">
            {/* Meta-agent */}
            <CommandBlock 
              title="Create meta-agent (default)"
              commands={[
                'mkdir meta-agent',
                'cd meta-agent',
                'co init'
              ]}
            />

            {/* Playwright */}
            <CommandBlock 
              title="Create web automation agent"
              commands={[
                'mkdir playwright-agent',
                'cd playwright-agent',
                'co init --template playwright'
              ]}
            />
          </div>
        </div>

        {/* Options */}
        <div className="mb-8">
          <h3 className="text-lg font-semibold text-white mb-4">Options</h3>
          
          <div className="bg-gray-900 border border-gray-700 rounded-lg overflow-hidden">
            <table className="w-full">
              <thead>
                <tr className="bg-gray-800 border-b border-gray-700">
                  <th className="text-left px-4 py-3 text-gray-300 font-medium">Option</th>
                  <th className="text-left px-4 py-3 text-gray-300 font-medium">Description</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-700">
                <tr>
                  <td className="px-4 py-3 font-mono text-sm text-blue-300">--template, -t</td>
                  <td className="px-4 py-3 text-gray-300">
                    Choose a template: <code className="bg-gray-800 px-2 py-1 rounded text-xs">meta-agent</code> (default), 
                    <code className="bg-gray-800 px-2 py-1 rounded text-xs ml-2">playwright</code>
                  </td>
                </tr>
                <tr>
                  <td className="px-4 py-3 font-mono text-sm text-blue-300">--force</td>
                  <td className="px-4 py-3 text-gray-300">Overwrite existing files</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        {/* What Gets Created */}
        <div className="mb-8">
          <h3 className="text-lg font-semibold text-white mb-4">What Gets Created</h3>
          
          <div className="grid md:grid-cols-2 gap-4">
            {/* Meta-Agent Structure */}
            <div>
              <h4 className="text-sm font-semibold text-blue-300 mb-3">Meta-Agent (default)</h4>
              <FileTree 
                structure={[
                  {
                    name: 'my-project',
                    type: 'folder',
                    children: [
                      { name: 'agent.py', type: 'file', icon: 'python' },
                      { 
                        name: 'prompts',
                        type: 'folder',
                        children: [
                          { name: 'metagent.md', type: 'file', icon: 'markdown' },
                          { name: 'docs_retrieve_prompt.md', type: 'file', icon: 'markdown' },
                          { name: 'answer_prompt.md', type: 'file', icon: 'markdown' },
                          { name: 'think_prompt.md', type: 'file', icon: 'markdown' }
                        ]
                      },
                      { name: 'README.md', type: 'file', icon: 'markdown' },
                      { name: '.env.example', type: 'file', icon: 'env' },
                      { name: '.co', type: 'folder' }
                    ]
                  }
                ]}
              />
            </div>

            {/* Playwright Structure */}
            <div>
              <h4 className="text-sm font-semibold text-purple-300 mb-3">Playwright Template</h4>
              <FileTree 
                structure={[
                  {
                    name: 'my-project',
                    type: 'folder',
                    children: [
                      { name: 'agent.py', type: 'file', icon: 'python' },
                      { name: 'prompt.md', type: 'file', icon: 'markdown' },
                      { name: '.env.example', type: 'file', icon: 'env' },
                      {
                        name: '.co',
                        type: 'folder',
                        children: [
                          { name: 'config.toml', type: 'file', icon: 'config' },
                          {
                            name: 'docs',
                            type: 'folder',
                            children: [
                              { name: 'connectonion.md', type: 'file', icon: 'markdown' }
                            ]
                          }
                        ]
                      },
                      { name: '.gitignore', type: 'file', icon: 'git' }
                    ]
                  }
                ]}
              />
            </div>
          </div>
        </div>
      </section>

      {/* Templates */}
      <section className="mb-16">
        <h2 className="text-2xl font-bold text-white mb-6 flex items-center gap-3">
          <Code className="w-6 h-6 text-purple-400" />
          Templates
        </h2>

        {/* Meta-Agent Template */}
        <div className="mb-12">
          <h3 className="text-xl font-semibold text-white mb-4 flex items-center gap-2">
            <div className="w-2 h-2 bg-blue-400 rounded-full"></div>
            Meta-Agent (Default)
          </h3>
          
          <p className="text-gray-300 mb-6">
            A ConnectOnion development assistant powered by <code className="bg-gray-800 px-2 py-1 rounded text-xs">llm_do()</code> for intelligent operations:
          </p>

          <div className="bg-gradient-to-b from-blue-900/30 to-blue-800/10 border border-blue-500/30 rounded-lg p-6 mb-6">
            <div className="grid md:grid-cols-2 gap-4 text-sm">
              <div className="space-y-2">
                <div className="flex items-start gap-2">
                  <Zap className="w-4 h-4 text-blue-400 mt-0.5" />
                  <div>
                    <span className="font-semibold text-blue-200">answer_connectonion_question()</span>
                    <p className="text-gray-400 text-xs">Uses llm_do() for intelligent doc retrieval</p>
                  </div>
                </div>
                <div className="flex items-start gap-2">
                  <Zap className="w-4 h-4 text-blue-400 mt-0.5" />
                  <div>
                    <span className="font-semibold text-blue-200">think()</span>
                    <p className="text-gray-400 text-xs">AI reflection on task progress</p>
                  </div>
                </div>
                <div className="flex items-start gap-2">
                  <Zap className="w-4 h-4 text-blue-400 mt-0.5" />
                  <div>
                    <span className="font-semibold text-blue-200">add_todo() / delete_todo()</span>
                    <p className="text-gray-400 text-xs">Task management functions</p>
                  </div>
                </div>
                <div className="flex items-start gap-2">
                  <Zap className="w-4 h-4 text-blue-400 mt-0.5" />
                  <div>
                    <span className="font-semibold text-blue-200">run_shell()</span>
                    <p className="text-gray-400 text-xs">Generate pytest test suites</p>
                  </div>
                </div>
              </div>
              <div className="space-y-2">
                <div className="flex items-start gap-2">
                  <Zap className="w-4 h-4 text-blue-400 mt-0.5" />
                  <div>
                    <span className="font-semibold text-blue-200">think()</span>
                    <p className="text-gray-400 text-xs">Self-reflection on tasks</p>
                  </div>
                </div>
                <div className="flex items-start gap-2">
                  <Zap className="w-4 h-4 text-blue-400 mt-0.5" />
                  <div>
                    <span className="font-semibold text-blue-200">generate_todo_list()</span>
                    <p className="text-gray-400 text-xs">Create structured plans (GPT-4o-mini)</p>
                  </div>
                </div>
                <div className="flex items-start gap-2">
                  <Zap className="w-4 h-4 text-blue-400 mt-0.5" />
                  <div>
                    <span className="font-semibold text-blue-200">suggest_project_structure()</span>
                    <p className="text-gray-400 text-xs">Architecture recommendations</p>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div className="bg-gray-900 border border-gray-700 rounded-lg overflow-hidden">
            <div className="flex items-center justify-between bg-gray-800 px-4 py-3 border-b border-gray-700">
              <span className="text-sm text-gray-300 font-mono">Example usage</span>
              <button
                onClick={() => copyToClipboard(`# Learn about ConnectOnion
result = agent.input("What is ConnectOnion and how do tools work?")

# Generate agent code
result = agent.input("Create a web scraper agent")

# Create tool functions
result = agent.input("Generate a tool for sending emails")`, 'meta-usage')}
                className="text-gray-400 hover:text-white transition-colors p-1.5 rounded hover:bg-gray-700"
              >
                {copiedId === 'meta-usage' ? (
                  <Check className="w-4 h-4 text-green-400" />
                ) : (
                  <Copy className="w-4 h-4" />
                )}
              </button>
            </div>
            <div className="p-6">
              <SyntaxHighlighter 
                language="python" 
                style={monokai}
                customStyle={{
                  background: 'transparent',
                  padding: 0,
                  margin: 0,
                  fontSize: '0.875rem',
                  lineHeight: '1.5'
                }}
                showLineNumbers={true}
              >
{`# Learn about ConnectOnion
result = agent.input("What is ConnectOnion and how do tools work?")

# Generate agent code
result = agent.input("Create a web scraper agent")

# Create tool functions
result = agent.input("Generate a tool for sending emails")`}
              </SyntaxHighlighter>
            </div>
          </div>
        </div>

        {/* Playwright Template */}
        <div>
          <h3 className="text-xl font-semibold text-white mb-4 flex items-center gap-2">
            <div className="w-2 h-2 bg-yellow-400 rounded-full"></div>
            Playwright Template
          </h3>
          
          <p className="text-gray-300 mb-6">
            Web automation agent with stateful browser control:
          </p>

          <div className="bg-gradient-to-b from-yellow-900/30 to-yellow-800/10 border border-yellow-500/30 rounded-lg p-6 mb-6">
            <div className="grid md:grid-cols-2 gap-4 text-sm">
              <div className="space-y-2">
                <div className="flex items-start gap-2">
                  <Zap className="w-4 h-4 text-yellow-400 mt-0.5" />
                  <div>
                    <span className="font-semibold text-yellow-200">start_browser()</span>
                    <p className="text-gray-400 text-xs">Launch browser instance</p>
                  </div>
                </div>
                <div className="flex items-start gap-2">
                  <Zap className="w-4 h-4 text-yellow-400 mt-0.5" />
                  <div>
                    <span className="font-semibold text-yellow-200">navigate()</span>
                    <p className="text-gray-400 text-xs">Go to URLs</p>
                  </div>
                </div>
                <div className="flex items-start gap-2">
                  <Zap className="w-4 h-4 text-yellow-400 mt-0.5" />
                  <div>
                    <span className="font-semibold text-yellow-200">scrape_content()</span>
                    <p className="text-gray-400 text-xs">Extract page content</p>
                  </div>
                </div>
                <div className="flex items-start gap-2">
                  <Zap className="w-4 h-4 text-yellow-400 mt-0.5" />
                  <div>
                    <span className="font-semibold text-yellow-200">fill_form()</span>
                    <p className="text-gray-400 text-xs">Fill and submit forms</p>
                  </div>
                </div>
              </div>
              <div className="space-y-2">
                <div className="flex items-start gap-2">
                  <Zap className="w-4 h-4 text-yellow-400 mt-0.5" />
                  <div>
                    <span className="font-semibold text-yellow-200">take_screenshot()</span>
                    <p className="text-gray-400 text-xs">Capture pages</p>
                  </div>
                </div>
                <div className="flex items-start gap-2">
                  <Zap className="w-4 h-4 text-yellow-400 mt-0.5" />
                  <div>
                    <span className="font-semibold text-yellow-200">extract_links()</span>
                    <p className="text-gray-400 text-xs">Get all links</p>
                  </div>
                </div>
                <div className="flex items-start gap-2">
                  <Zap className="w-4 h-4 text-yellow-400 mt-0.5" />
                  <div>
                    <span className="font-semibold text-yellow-200">execute_javascript()</span>
                    <p className="text-gray-400 text-xs">Run JS code</p>
                  </div>
                </div>
                <div className="flex items-start gap-2">
                  <Zap className="w-4 h-4 text-yellow-400 mt-0.5" />
                  <div>
                    <span className="font-semibold text-yellow-200">close_browser()</span>
                    <p className="text-gray-400 text-xs">Clean up resources</p>
                  </div>
                </div>
              </div>
            </div>
            
            <div className="mt-4 p-3 bg-black/30 rounded-lg flex items-center gap-2">
              <AlertCircle className="w-4 h-4 text-yellow-400" />
              <p className="text-yellow-200 text-sm">
                Note: Requires running the following command first:
              </p>
            </div>
            <CommandBlock 
              commands={['pip install playwright && playwright install']}
            />
          </div>
        </div>
      </section>

      {/* Interactive Features */}
      <section className="mb-16">
        <h2 className="text-2xl font-bold text-white mb-6 flex items-center gap-3">
          <Zap className="w-6 h-6 text-yellow-400" />
          Interactive Features
        </h2>

        <div className="bg-gray-900 border border-gray-700 rounded-lg p-6">
          <p className="text-gray-300 mb-4">The CLI will:</p>
          <ul className="space-y-3 text-gray-300">
            <li className="flex items-start gap-3">
              <AlertCircle className="w-5 h-5 text-orange-400 mt-0.5" />
              <span>Warn if you're in a special directory (home, root, system)</span>
            </li>
            <li className="flex items-start gap-3">
              <AlertCircle className="w-5 h-5 text-orange-400 mt-0.5" />
              <span>Ask for confirmation if the directory is not empty</span>
            </li>
            <li className="flex items-start gap-3">
              <GitBranch className="w-5 h-5 text-green-400 mt-0.5" />
              <span>Automatically detect git repositories and update <code className="bg-gray-800 px-2 py-1 rounded text-sm">.gitignore</code></span>
            </li>
            <li className="flex items-start gap-3">
              <Check className="w-5 h-5 text-green-400 mt-0.5" />
              <span>Provide clear next steps after initialization</span>
            </li>
          </ul>
        </div>
      </section>

      {/* Best Practices */}
      <section className="mb-16">
        <h2 className="text-2xl font-bold text-white mb-6">Best Practices</h2>

        <div className="grid md:grid-cols-2 gap-6">
          <div className="bg-gradient-to-b from-purple-900/20 to-purple-800/10 border border-purple-500/30 rounded-lg p-6">
            <FileText className="w-8 h-8 text-purple-400 mb-3" />
            <h3 className="text-lg font-semibold text-white mb-2">Use Markdown for Prompts</h3>
            <p className="text-gray-300 text-sm">
              Always store system prompts in <code className="bg-black/30 px-2 py-1 rounded">prompt.md</code> files for better formatting and readability.
            </p>
          </div>

          <div className="bg-gradient-to-b from-green-900/20 to-green-800/10 border border-green-500/30 rounded-lg p-6">
            <AlertCircle className="w-8 h-8 text-green-400 mb-3" />
            <h3 className="text-lg font-semibold text-white mb-2">Environment Variables</h3>
            <p className="text-gray-300 text-sm">
              Never commit <code className="bg-black/30 px-2 py-1 rounded">.env</code> files. Use <code className="bg-black/30 px-2 py-1 rounded">.env.example</code> as a template.
            </p>
          </div>

          <div className="bg-gradient-to-b from-orange-900/20 to-orange-800/10 border border-orange-500/30 rounded-lg p-6">
            <GitBranch className="w-8 h-8 text-orange-400 mb-3" />
            <h3 className="text-lg font-semibold text-white mb-2">Git Integration</h3>
            <p className="text-gray-300 text-sm">
              The CLI automatically handles <code className="bg-black/30 px-2 py-1 rounded">.gitignore</code> for git repositories.
            </p>
          </div>

          <div className="bg-gradient-to-b from-blue-900/20 to-blue-800/10 border border-blue-500/30 rounded-lg p-6">
            <Folder className="w-8 h-8 text-blue-400 mb-3" />
            <h3 className="text-lg font-semibold text-white mb-2">Embedded Documentation</h3>
            <p className="text-gray-300 text-sm">
              The docs in <code className="bg-black/30 px-2 py-1 rounded">.co/docs/</code> allow agents to work offline.
            </p>
          </div>
        </div>
      </section>

      {/* Troubleshooting */}
      <section className="mb-16">
        <h2 className="text-2xl font-bold text-white mb-6">Troubleshooting</h2>

        <div className="space-y-6">
          <div className="bg-gray-900 border border-gray-700 rounded-lg p-6">
            <h3 className="text-lg font-semibold text-white mb-3">Python Version</h3>
            <p className="text-gray-300 mb-4">
              ConnectOnion requires Python 3.8 or higher. Check your version:
            </p>
            <CommandBlock 
              commands={['python --version']}
            />
          </div>

          <div className="bg-gray-900 border border-gray-700 rounded-lg p-6">
            <h3 className="text-lg font-semibold text-white mb-3">API Keys Setup</h3>
            <p className="text-gray-300 mb-4">
              After running <code className="bg-gray-800 px-2 py-1 rounded">co init</code>, set up your API keys:
            </p>
            <CommandBlock 
              commands={[
                'cp .env.example .env',
                '# Edit .env and add your actual API keys',
                'nano .env  # or use your preferred editor'
              ]}
            />
          </div>
        </div>
      </section>

      {/* Navigation */}
      <ContentNavigation />

      </div>
    </div>
  )
}