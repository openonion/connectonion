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
import { Copy, Check, Terminal, ArrowRight, FileText, Package, GitBranch, AlertCircle, Zap, Code, Folder, BookOpen, ChevronRight, Key, Sparkles, Shield } from 'lucide-react'
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

The ConnectOnion CLI provides commands to quickly scaffold and manage AI agent projects.

## Installation

\`\`\`bash
pip install connectonion
\`\`\`

This provides two equivalent commands:
- \`co\` (short form)
- \`connectonion\` (full form)

## Commands Overview

ConnectOnion provides two main commands for project creation:

- **\`co create [name]\`** - Creates a new project directory
- **\`co init\`** - Initializes the current directory

Both commands share the same interactive flow:
1. AI feature toggle (Yes/No)
2. API key input (with auto-detection)
3. Template selection

## Commands

### co create [name]

Create a new ConnectOnion project in a new directory.

#### Basic Usage

\`\`\`bash
# Interactive mode (prompts for project name)
co create

# With project name (skips name prompt)
co create my-agent

# With all options (no interaction)
co create my-agent --ai --key sk-proj-xxx --template minimal
\`\`\`

#### Options

- \`[name]\`: Optional project name (creates directory)
- \`--ai/--no-ai\`: Enable or disable AI features
- \`--key\`: API key for AI provider (auto-detects provider)
- \`--template\`: Choose template (\`minimal\`, \`web-research\`, \`custom\`)
- \`--description\`: Description for custom template (requires AI)
- \`--yes, -y\`: Skip all prompts, use defaults

### co init

Initialize a ConnectOnion project in the current directory.

#### Basic Usage

\`\`\`bash
# Initialize current directory interactively
co init

# Skip prompts with options
co init --no-ai --template minimal
\`\`\`

#### Options

Same as \`co create\`, except no \`[name]\` parameter (uses current directory name).

## Templates

### Minimal
Basic agent structure with essential components:
- Simple agent.py with basic tools
- Minimal dependencies
- Quick start configuration

### Web Research
Advanced template for data analysis and web scraping:
- Web scraping tools
- Data extraction utilities
- Browser automation support
- API integration examples

### Custom (AI-only)
Only available when AI is enabled. Generates a complete custom template based on your description.

## API Key Detection

The CLI automatically detects your API provider from the key format:

| Provider | Key Format | Example |
|----------|------------|---------|
| OpenAI | \`sk-...\` or \`sk-proj-...\` | \`sk-proj-abc123...\` |
| Anthropic | \`sk-ant-...\` | \`sk-ant-api03-xyz...\` |
| Google | \`AIza...\` | \`AIzaSyAbc123...\` |
| Groq | \`gsk_...\` | \`gsk_abc123...\` |

## What Gets Created

### Project Structure

\`\`\`
my-agent/
├── agent.py           # Main agent implementation
├── tools/             # Custom tools directory (if applicable)
├── prompts/           # System prompts (for AI-enabled projects)
├── .env               # Environment configuration (API keys)
├── .co/               # ConnectOnion metadata
│   ├── config.toml    # Project configuration
│   ├── keys/          # Agent cryptographic keys
│   │   ├── agent.key  # Private signing key
│   │   ├── recovery.txt # 12-word recovery phrase
│   │   └── DO_NOT_SHARE # Security warning
│   └── docs/
│       └── co-vibecoding-principles-docs-contexts-all-in-one.md # Complete VibeCoding & framework docs
├── README.md          # Project documentation
└── .gitignore        # Git ignore rules (if in git repo)
\`\`\`

### Agent Identity

Every project automatically gets:
- **Ed25519 cryptographic keys** for agent identity
- **Unique address** (hex-encoded public key)
- **12-word recovery phrase** for key restoration
- Keys are stored in \`.co/keys/\` and auto-added to \`.gitignore\`

## Quick Command Reference

| Command | Description |
|---------|-------------|
| \`co create\` | Create new project (interactive) |
| \`co create my-agent\` | Create with name |
| \`co init\` | Initialize current directory |
| \`co create --no-ai\` | Create without AI features |
| \`co create --ai --template custom\` | Create custom AI template |
| \`co --version\` | Show version |
| \`co --help\` | Show help |

## Browser Features

### Browser Commands

Use the \`-b\` flag for browser automation with natural language:

\`\`\`bash
# Take a screenshot
co -b "screenshot example.com save to screenshot.png"

# Screenshot with device preset
co -b "screenshot example.com save to mobile.png size iPhone"
\`\`\`

### Device Presets

- iPhone: 390x844
- iPad: 768x1024
- Desktop: 1920x1080 (default)

## Best Practices

1. **Choose the right command**:
   - Use \`co create\` when starting a new project
   - Use \`co init\` when adding to an existing directory

2. **API Key Security**:
   - Never commit \`.env\` files
   - Store API keys securely
   - Use environment variables in production

3. **Template Selection**:
   - Start with Minimal for learning
   - Use Web Research for data projects
   - Choose Custom (with AI) for specific needs

4. **Agent Keys**:
   - Never share \`.co/keys/\` directory
   - Backup your recovery phrase
   - Keys are automatically generated and protected

## Troubleshooting

### Command Not Found

If \`co\` command is not found after installation:
\`\`\`bash
# Use full command
python -m connectonion.cli.main create

# Or reinstall
pip uninstall connectonion
pip install connectonion
\`\`\`

### Permission Denied

Ensure you have write permissions in the target directory.

### API Key Issues

- Check key format matches your provider
- Ensure key is active and has credits
- Try pasting without quotes or spaces

### Python Version

ConnectOnion requires Python 3.8+:
\`\`\`bash
python --version
\`\`\`
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
          <div className="font-mono text-blue-300">co create <span className="text-gray-400">→ New project</span></div>
          <div className="font-mono text-blue-300">co init <span className="text-gray-400">→ Current directory</span></div>
          <div className="font-mono text-blue-300">co create --ai <span className="text-gray-400">→ With AI features</span></div>
          <div className="font-mono text-blue-300">co -b "screenshot..." <span className="text-gray-400">→ Browser commands</span></div>
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

      {/* Commands Overview */}
      <section className="mb-16">
        <h2 className="text-2xl font-bold text-white mb-6 flex items-center gap-3">
          <Terminal className="w-6 h-6 text-green-400" />
          Commands Overview
        </h2>

        <p className="text-gray-300 mb-6">
          ConnectOnion provides two main commands for project creation:
        </p>

        <div className="grid md:grid-cols-2 gap-4 mb-8">
          <div className="bg-gradient-to-b from-green-900/20 to-green-800/10 border border-green-500/30 rounded-lg p-6">
            <div className="flex items-center gap-2 mb-3">
              <Sparkles className="w-5 h-5 text-green-400" />
              <h3 className="text-lg font-semibold text-white">co create [name]</h3>
            </div>
            <p className="text-gray-300 text-sm">
              Creates a new project directory with all necessary files
            </p>
          </div>

          <div className="bg-gradient-to-b from-purple-900/20 to-purple-800/10 border border-purple-500/30 rounded-lg p-6">
            <div className="flex items-center gap-2 mb-3">
              <Folder className="w-5 h-5 text-purple-400" />
              <h3 className="text-lg font-semibold text-white">co init</h3>
            </div>
            <p className="text-gray-300 text-sm">
              Initializes the current directory as a ConnectOnion project
            </p>
          </div>
        </div>

        <div className="bg-gray-900 border border-gray-700 rounded-lg p-6">
          <p className="text-gray-300 mb-4">Both commands share the same interactive flow:</p>
          <ol className="space-y-2 text-gray-300">
            <li className="flex items-center gap-3">
              <span className="flex-shrink-0 w-6 h-6 bg-blue-500/20 border border-blue-500/50 rounded-full flex items-center justify-center text-xs text-blue-300">1</span>
              <span>AI feature toggle (Yes/No)</span>
            </li>
            <li className="flex items-center gap-3">
              <span className="flex-shrink-0 w-6 h-6 bg-blue-500/20 border border-blue-500/50 rounded-full flex items-center justify-center text-xs text-blue-300">2</span>
              <span>API key input (with auto-detection)</span>
            </li>
            <li className="flex items-center gap-3">
              <span className="flex-shrink-0 w-6 h-6 bg-blue-500/20 border border-blue-500/50 rounded-full flex items-center justify-center text-xs text-blue-300">3</span>
              <span>Template selection</span>
            </li>
          </ol>
        </div>
      </section>

      {/* co create Command */}
      <section className="mb-16">
        <h2 className="text-2xl font-bold text-white mb-6 flex items-center gap-3">
          <Sparkles className="w-6 h-6 text-green-400" />
          co create [name]
        </h2>
        
        <p className="text-gray-300 mb-6">
          Create a new ConnectOnion project in a new directory.
        </p>

        {/* Basic Usage */}
        <div className="mb-8">
          <h3 className="text-lg font-semibold text-white mb-4">Basic Usage</h3>
          
          <div className="space-y-4">
            <CommandBlock 
              title="Interactive mode (prompts for project name)"
              commands={['co create']}
            />

            <CommandBlock 
              title="With project name (skips name prompt)"
              commands={['co create my-agent']}
            />

            <CommandBlock 
              title="With all options (no interaction)"
              commands={['co create my-agent --ai --key sk-proj-xxx --template minimal']}
            />
          </div>
        </div>

        {/* Options Table */}
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
                  <td className="px-4 py-3 font-mono text-sm text-blue-300">[name]</td>
                  <td className="px-4 py-3 text-gray-300">Optional project name (creates directory)</td>
                </tr>
                <tr>
                  <td className="px-4 py-3 font-mono text-sm text-blue-300">--ai/--no-ai</td>
                  <td className="px-4 py-3 text-gray-300">Enable or disable AI features</td>
                </tr>
                <tr>
                  <td className="px-4 py-3 font-mono text-sm text-blue-300">--key</td>
                  <td className="px-4 py-3 text-gray-300">API key for AI provider (auto-detects provider)</td>
                </tr>
                <tr>
                  <td className="px-4 py-3 font-mono text-sm text-blue-300">--template</td>
                  <td className="px-4 py-3 text-gray-300">
                    Choose template: <code className="bg-gray-800 px-2 py-1 rounded text-xs">minimal</code>, 
                    <code className="bg-gray-800 px-2 py-1 rounded text-xs ml-2">web-research</code>, 
                    <code className="bg-gray-800 px-2 py-1 rounded text-xs ml-2">custom</code>
                  </td>
                </tr>
                <tr>
                  <td className="px-4 py-3 font-mono text-sm text-blue-300">--description</td>
                  <td className="px-4 py-3 text-gray-300">Description for custom template (requires AI)</td>
                </tr>
                <tr>
                  <td className="px-4 py-3 font-mono text-sm text-blue-300">--yes, -y</td>
                  <td className="px-4 py-3 text-gray-300">Skip all prompts, use defaults</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        {/* Interactive Flow Example */}
        <div className="mb-8">
          <h3 className="text-lg font-semibold text-white mb-4">Interactive Flow Example</h3>
          
          <div className="bg-gray-900 border border-gray-700 rounded-lg overflow-hidden">
            <div className="flex items-center justify-between bg-gray-800 px-4 py-3 border-b border-gray-700">
              <span className="text-sm text-gray-300 font-mono">Terminal Output</span>
            </div>
            <div className="p-6">
              <pre className="text-sm text-gray-300 font-mono">
{`$ co create

✔ Project name: … my-agent
✔ Enable AI features? (Y/n) … Y
✔ Paste your API key (or Enter to skip): … sk-proj-abc123
  ✓ Detected OpenAI API key
✔ Choose a template:
  ❯ Minimal - Simple starting point
    Web Research - Data analysis & web scraping
    Custom - AI generates based on your needs

✅ Created 'my-agent' with Minimal template

Next steps:
  cd my-agent
  python agent.py`}
              </pre>
            </div>
          </div>
        </div>
      </section>

      {/* co init Command */}
      <section className="mb-16">
        <h2 className="text-2xl font-bold text-white mb-6 flex items-center gap-3">
          <Folder className="w-6 h-6 text-purple-400" />
          co init
        </h2>
        
        <p className="text-gray-300 mb-6">
          Initialize a ConnectOnion project in the current directory.
        </p>

        {/* Basic Usage */}
        <div className="mb-8">
          <h3 className="text-lg font-semibold text-white mb-4">Basic Usage</h3>
          
          <div className="space-y-4">
            <CommandBlock 
              title="Initialize current directory interactively"
              commands={['co init']}
            />

            <CommandBlock 
              title="Skip prompts with options"
              commands={['co init --no-ai --template minimal']}
            />
          </div>
        </div>

        <div className="bg-gradient-to-b from-purple-900/30 to-purple-800/10 border border-purple-500/30 rounded-lg p-4">
          <p className="text-purple-200">
            <strong>Note:</strong> Options are the same as <code className="bg-black/30 px-2 py-1 rounded">co create</code>, 
            except no <code className="bg-black/30 px-2 py-1 rounded">[name]</code> parameter (uses current directory name).
          </p>
        </div>
      </section>

      {/* Browser Features */}
      <section className="mb-16">
        <h2 className="text-2xl font-bold text-white mb-6 flex items-center gap-3">
          <Zap className="w-6 h-6 text-yellow-400" />
          Browser Features
        </h2>

        <p className="text-gray-300 mb-6">
          Use the <code className="bg-gray-800 px-2 py-1 rounded">-b</code> flag for browser automation with natural language:
        </p>

        <div className="space-y-4 mb-8">
          <CommandBlock 
            title="Take a screenshot"
            commands={['co -b "screenshot example.com save to screenshot.png"']}
          />

          <CommandBlock 
            title="Screenshot with device preset"
            commands={['co -b "screenshot example.com save to mobile.png size iPhone"']}
          />
        </div>

        {/* Device Presets */}
        <div className="bg-gradient-to-b from-yellow-900/30 to-yellow-800/10 border border-yellow-500/30 rounded-lg p-6">
          <h3 className="text-lg font-semibold text-white mb-4">Device Presets</h3>
          <div className="grid grid-cols-3 gap-4 text-sm">
            <div>
              <span className="font-semibold text-yellow-200">iPhone</span>
              <p className="text-gray-400">390×844</p>
            </div>
            <div>
              <span className="font-semibold text-yellow-200">iPad</span>
              <p className="text-gray-400">768×1024</p>
            </div>
            <div>
              <span className="font-semibold text-yellow-200">Desktop</span>
              <p className="text-gray-400">1920×1080 (default)</p>
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

        <div className="space-y-6">
          {/* Minimal Template */}
          <div className="bg-gradient-to-b from-blue-900/20 to-blue-800/10 border border-blue-500/30 rounded-lg p-6">
            <h3 className="text-xl font-semibold text-white mb-3 flex items-center gap-2">
              <div className="w-2 h-2 bg-blue-400 rounded-full"></div>
              Minimal
            </h3>
            <p className="text-gray-300 mb-4">
              Basic agent structure with essential components:
            </p>
            <ul className="space-y-2 text-gray-300 text-sm">
              <li className="flex items-center gap-2">
                <ChevronRight className="w-4 h-4 text-blue-400" />
                Simple agent.py with basic tools
              </li>
              <li className="flex items-center gap-2">
                <ChevronRight className="w-4 h-4 text-blue-400" />
                Minimal dependencies
              </li>
              <li className="flex items-center gap-2">
                <ChevronRight className="w-4 h-4 text-blue-400" />
                Quick start configuration
              </li>
            </ul>
          </div>

          {/* Web Research Template */}
          <div className="bg-gradient-to-b from-green-900/20 to-green-800/10 border border-green-500/30 rounded-lg p-6">
            <h3 className="text-xl font-semibold text-white mb-3 flex items-center gap-2">
              <div className="w-2 h-2 bg-green-400 rounded-full"></div>
              Web Research
            </h3>
            <p className="text-gray-300 mb-4">
              Advanced template for data analysis and web scraping:
            </p>
            <ul className="space-y-2 text-gray-300 text-sm">
              <li className="flex items-center gap-2">
                <ChevronRight className="w-4 h-4 text-green-400" />
                Web scraping tools
              </li>
              <li className="flex items-center gap-2">
                <ChevronRight className="w-4 h-4 text-green-400" />
                Data extraction utilities
              </li>
              <li className="flex items-center gap-2">
                <ChevronRight className="w-4 h-4 text-green-400" />
                Browser automation support
              </li>
              <li className="flex items-center gap-2">
                <ChevronRight className="w-4 h-4 text-green-400" />
                API integration examples
              </li>
            </ul>
          </div>

          {/* Custom Template */}
          <div className="bg-gradient-to-b from-purple-900/20 to-purple-800/10 border border-purple-500/30 rounded-lg p-6">
            <h3 className="text-xl font-semibold text-white mb-3 flex items-center gap-2">
              <div className="w-2 h-2 bg-purple-400 rounded-full"></div>
              Custom (AI-only)
            </h3>
            <p className="text-gray-300 mb-4">
              Only available when AI is enabled. Generates a complete custom template based on your description:
            </p>
            <div className="bg-black/30 rounded-lg p-4">
              <pre className="text-sm text-gray-300 font-mono">
{`✔ Choose template: Custom
✔ Describe what you want to build: … 
  I need an agent that monitors GitHub repos and 
  sends notifications for new issues

⚡ Generating custom template with AI...
✅ Created custom GitHub monitoring agent`}
              </pre>
            </div>
          </div>
        </div>
      </section>

      {/* API Key Detection */}
      <section className="mb-16">
        <h2 className="text-2xl font-bold text-white mb-6 flex items-center gap-3">
          <Key className="w-6 h-6 text-orange-400" />
          API Key Detection
        </h2>

        <p className="text-gray-300 mb-6">
          The CLI automatically detects your API provider from the key format:
        </p>

        <div className="bg-gray-900 border border-gray-700 rounded-lg overflow-hidden">
          <table className="w-full">
            <thead>
              <tr className="bg-gray-800 border-b border-gray-700">
                <th className="text-left px-4 py-3 text-gray-300 font-medium">Provider</th>
                <th className="text-left px-4 py-3 text-gray-300 font-medium">Key Format</th>
                <th className="text-left px-4 py-3 text-gray-300 font-medium">Example</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-700">
              <tr>
                <td className="px-4 py-3 text-white font-medium">OpenAI</td>
                <td className="px-4 py-3 font-mono text-sm text-blue-300">sk-... or sk-proj-...</td>
                <td className="px-4 py-3 font-mono text-xs text-gray-400">sk-proj-abc123...</td>
              </tr>
              <tr>
                <td className="px-4 py-3 text-white font-medium">Anthropic</td>
                <td className="px-4 py-3 font-mono text-sm text-blue-300">sk-ant-...</td>
                <td className="px-4 py-3 font-mono text-xs text-gray-400">sk-ant-api03-xyz...</td>
              </tr>
              <tr>
                <td className="px-4 py-3 text-white font-medium">Google</td>
                <td className="px-4 py-3 font-mono text-sm text-blue-300">AIza...</td>
                <td className="px-4 py-3 font-mono text-xs text-gray-400">AIzaSyAbc123...</td>
              </tr>
              <tr>
                <td className="px-4 py-3 text-white font-medium">Groq</td>
                <td className="px-4 py-3 font-mono text-sm text-blue-300">gsk_...</td>
                <td className="px-4 py-3 font-mono text-xs text-gray-400">gsk_abc123...</td>
              </tr>
            </tbody>
          </table>
        </div>

        <div className="bg-gradient-to-b from-orange-900/30 to-orange-800/10 border border-orange-500/30 rounded-lg p-4 mt-6">
          <p className="text-orange-200 text-sm">
            The appropriate environment variables and model configurations are set automatically.
          </p>
        </div>
      </section>

      {/* What Gets Created */}
      <section className="mb-16">
        <h2 className="text-2xl font-bold text-white mb-6 flex items-center gap-3">
          <FileText className="w-6 h-6 text-blue-400" />
          What Gets Created
        </h2>

        {/* Project Structure */}
        <div className="mb-8">
          <h3 className="text-lg font-semibold text-white mb-4">Project Structure</h3>
          
          <FileTree 
            structure={[
              {
                name: 'my-agent',
                type: 'folder',
                children: [
                  { name: 'agent.py', type: 'file', icon: 'python', comment: 'Main agent implementation' },
                  { 
                    name: 'tools',
                    type: 'folder',
                    comment: 'Custom tools directory',
                    children: []
                  },
                  { 
                    name: 'prompts',
                    type: 'folder',
                    comment: 'System prompts (AI-enabled)',
                    children: []
                  },
                  { name: '.env', type: 'file', icon: 'env', comment: 'Environment configuration' },
                  { 
                    name: '.co',
                    type: 'folder',
                    comment: 'ConnectOnion metadata',
                    children: [
                      { name: 'config.toml', type: 'file', icon: 'config', comment: 'Project configuration' },
                      {
                        name: 'keys',
                        type: 'folder',
                        comment: 'Agent cryptographic keys',
                        children: [
                          { name: 'agent.key', type: 'file', comment: 'Private signing key' },
                          { name: 'recovery.txt', type: 'file', comment: '12-word recovery phrase' },
                          { name: 'DO_NOT_SHARE', type: 'file', comment: 'Security warning' }
                        ]
                      },
                      {
                        name: 'docs',
                        type: 'folder',
                        children: [
                          { name: 'co-vibecoding-principles-docs-contexts-all-in-one.md', type: 'file', icon: 'markdown', comment: 'Complete VibeCoding & framework docs' }
                        ]
                      }
                    ]
                  },
                  { name: 'README.md', type: 'file', icon: 'markdown', comment: 'Project documentation' },
                  { name: '.gitignore', type: 'file', icon: 'git', comment: 'Git ignore rules' }
                ]
              }
            ]}
          />
        </div>

        {/* Agent Identity */}
        <div className="bg-gradient-to-b from-purple-900/20 to-purple-800/10 border border-purple-500/30 rounded-lg p-6">
          <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
            <Shield className="w-5 h-5 text-purple-400" />
            Agent Identity
          </h3>
          <p className="text-gray-300 mb-4">
            Every project automatically gets:
          </p>
          <ul className="space-y-2 text-gray-300">
            <li className="flex items-start gap-2">
              <Key className="w-4 h-4 text-purple-400 mt-0.5" />
              <div>
                <strong className="text-purple-200">Ed25519 cryptographic keys</strong> for agent identity
              </div>
            </li>
            <li className="flex items-start gap-2">
              <Key className="w-4 h-4 text-purple-400 mt-0.5" />
              <div>
                <strong className="text-purple-200">Unique address</strong> (hex-encoded public key)
              </div>
            </li>
            <li className="flex items-start gap-2">
              <Key className="w-4 h-4 text-purple-400 mt-0.5" />
              <div>
                <strong className="text-purple-200">12-word recovery phrase</strong> for key restoration
              </div>
            </li>
          </ul>
          <div className="mt-4 p-3 bg-black/30 rounded-lg flex items-center gap-2">
            <AlertCircle className="w-4 h-4 text-yellow-400" />
            <p className="text-yellow-200 text-sm">
              Keys are stored in <code className="bg-black/30 px-2 py-1 rounded">.co/keys/</code> and auto-added to <code className="bg-black/30 px-2 py-1 rounded">.gitignore</code>
            </p>
          </div>
        </div>
      </section>

      {/* Examples */}
      <section className="mb-16">
        <h2 className="text-2xl font-bold text-white mb-6">Examples</h2>

        <div className="space-y-4">
          <CommandBlock 
            title="Minimal project without AI"
            commands={['co create simple-bot --no-ai --template minimal']}
          />

          <CommandBlock 
            title="Web research project with AI"
            commands={['co create research-agent --ai --template web-research']}
          />

          <CommandBlock 
            title="Custom AI agent with description"
            commands={['co create slack-bot --ai --template custom --description "Slack bot that answers questions"']}
          />

          <CommandBlock 
            title="Initialize existing directory"
            commands={[
              'cd my-existing-project',
              'co init --ai --template minimal'
            ]}
          />
        </div>
      </section>

      {/* Best Practices */}
      <section className="mb-16">
        <h2 className="text-2xl font-bold text-white mb-6">Best Practices</h2>

        <div className="grid md:grid-cols-2 gap-6">
          <div className="bg-gradient-to-b from-purple-900/20 to-purple-800/10 border border-purple-500/30 rounded-lg p-6">
            <Terminal className="w-8 h-8 text-purple-400 mb-3" />
            <h3 className="text-lg font-semibold text-white mb-2">Choose the Right Command</h3>
            <p className="text-gray-300 text-sm">
              Use <code className="bg-black/30 px-2 py-1 rounded">co create</code> for new projects, 
              <code className="bg-black/30 px-2 py-1 rounded ml-1">co init</code> for existing directories.
            </p>
          </div>

          <div className="bg-gradient-to-b from-green-900/20 to-green-800/10 border border-green-500/30 rounded-lg p-6">
            <Key className="w-8 h-8 text-green-400 mb-3" />
            <h3 className="text-lg font-semibold text-white mb-2">API Key Security</h3>
            <p className="text-gray-300 text-sm">
              Never commit <code className="bg-black/30 px-2 py-1 rounded">.env</code> files. Store API keys securely.
            </p>
          </div>

          <div className="bg-gradient-to-b from-orange-900/20 to-orange-800/10 border border-orange-500/30 rounded-lg p-6">
            <Code className="w-8 h-8 text-orange-400 mb-3" />
            <h3 className="text-lg font-semibold text-white mb-2">Template Selection</h3>
            <p className="text-gray-300 text-sm">
              Start with Minimal for learning. Use Custom (with AI) for specific needs.
            </p>
          </div>

          <div className="bg-gradient-to-b from-blue-900/20 to-blue-800/10 border border-blue-500/30 rounded-lg p-6">
            <Shield className="w-8 h-8 text-blue-400 mb-3" />
            <h3 className="text-lg font-semibold text-white mb-2">Agent Keys</h3>
            <p className="text-gray-300 text-sm">
              Never share <code className="bg-black/30 px-2 py-1 rounded">.co/keys/</code> directory. Backup your recovery phrase.
            </p>
          </div>
        </div>
      </section>

      {/* Troubleshooting */}
      <section className="mb-16">
        <h2 className="text-2xl font-bold text-white mb-6">Troubleshooting</h2>

        <div className="space-y-6">
          <div className="bg-gray-900 border border-gray-700 rounded-lg p-6">
            <h3 className="text-lg font-semibold text-white mb-3">Command Not Found</h3>
            <p className="text-gray-300 mb-4">
              If <code className="bg-gray-800 px-2 py-1 rounded">co</code> command is not found after installation:
            </p>
            <CommandBlock 
              commands={[
                '# Use full command',
                'python -m connectonion.cli.main create',
                '',
                '# Or reinstall',
                'pip uninstall connectonion',
                'pip install connectonion'
              ]}
            />
          </div>

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
            <h3 className="text-lg font-semibold text-white mb-3">API Key Issues</h3>
            <ul className="space-y-2 text-gray-300">
              <li className="flex items-center gap-2">
                <ChevronRight className="w-4 h-4 text-gray-400" />
                Check key format matches your provider
              </li>
              <li className="flex items-center gap-2">
                <ChevronRight className="w-4 h-4 text-gray-400" />
                Ensure key is active and has credits
              </li>
              <li className="flex items-center gap-2">
                <ChevronRight className="w-4 h-4 text-gray-400" />
                Try pasting without quotes or spaces
              </li>
            </ul>
          </div>
        </div>
      </section>

      {/* Navigation */}
      <ContentNavigation />

      </div>
    </div>
  )
}