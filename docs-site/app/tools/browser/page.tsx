'use client'

import { useState } from 'react'
import { Terminal, ArrowRight, Camera, Smartphone, Tablet, Monitor, AlertCircle, Zap, Copy, Check, FileText, Bug, Layers, Clock } from 'lucide-react'
import Link from 'next/link'
import { CommandBlock } from '../../../components/CommandBlock'
import { ContentNavigation } from '../../../components/ContentNavigation'
import { CopyMarkdownButton } from '../../../components/CopyMarkdownButton'

export default function BrowserPage() {
  const [copiedId, setCopiedId] = useState<string | null>(null)

  const copyToClipboard = (text: string, id: string) => {
    navigator.clipboard.writeText(text)
    setCopiedId(id)
    setTimeout(() => setCopiedId(null), 2000)
  }

  const pageContent = `# CLI Browser Feature

Quick browser screenshots for debugging web applications.

## Overview

The \`-b\` flag provides instant browser screenshots without writing code. Perfect for debugging, testing, and sharing visual proof of issues.

## Basic Usage

\`\`\`bash
co -b "screenshot localhost:3000"
\`\`\`

This command:
1. Opens a headless browser
2. Navigates to http://localhost:3000
3. Takes a screenshot
4. Saves as \`screenshot_[timestamp].png\`

## Command Format

\`\`\`bash
co -b "screenshot [URL] [save to PATH] [size SIZE]"
\`\`\`

All parts except URL are optional.

## Examples

### Basic Screenshot

\`\`\`bash
# Screenshot local development
co -b "screenshot localhost:3000"

# With specific port
co -b "screenshot localhost:8080"

# External site
co -b "screenshot example.com"
\`\`\`

### Save to Specific Path

\`\`\`bash
# Save to temp directory
co -b "screenshot localhost:3000 save to /tmp/debug.png"

# Save to current directory with name
co -b "screenshot localhost:3000 save to homepage.png"

# Save to subdirectory
co -b "screenshot localhost:3000 save to screenshots/test.png"
\`\`\`

### Device Sizes

\`\`\`bash
# iPhone viewport
co -b "screenshot localhost:3000 size iphone"

# Custom dimensions
co -b "screenshot localhost:3000 size 390x844"

# Common presets
co -b "screenshot localhost:3000 size ipad"
co -b "screenshot localhost:3000 size desktop"
\`\`\`

## Device Presets

| Preset | Dimensions | Device |
|--------|------------|--------|
| \`iphone\` | 390×844 | iPhone 14/15 |
| \`android\` | 360×800 | Common Android |
| \`ipad\` | 768×1024 | iPad |
| \`desktop\` | 1920×1080 | Full HD Desktop |

## URL Handling

The command intelligently handles URLs:

- \`localhost\` → \`http://localhost\`
- \`localhost:3000\` → \`http://localhost:3000\`
- \`example.com\` → \`https://example.com\`
- \`http://example.com\` → \`http://example.com\` (unchanged)

## Installation

Browser features require Playwright:

\`\`\`bash
pip install playwright
playwright install chromium
\`\`\`

Or install ConnectOnion with browser support:

\`\`\`bash
pip install connectonion[browser]
\`\`\`

## Use Cases

### Debug Local Development
\`\`\`bash
# Quick check of homepage
co -b "screenshot localhost:3000"

# Debug specific route
co -b "screenshot localhost:3000/api/status"
\`\`\`

### Document Bugs
\`\`\`bash
# Capture error state
co -b "screenshot localhost:3000/error save to bug.png"

# Mobile-specific issue
co -b "screenshot localhost:3000/mobile-bug save to mobile-issue.png size iphone"
\`\`\`

### Test Responsive Design
\`\`\`bash
# Test different viewports
for size in iphone android ipad desktop; do
  co -b "screenshot localhost:3000 save to view-$size.png size $size"
done
\`\`\`

### CI/CD Integration
\`\`\`bash
# In GitHub Actions or similar
co -b "screenshot $DEPLOY_URL save to artifacts/deployed.png"
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
              <Link href="/tools" className="hover:text-white transition-colors">Tools</Link>
              <ArrowRight className="w-4 h-4" />
              <span className="text-white">Browser Screenshots</span>
            </nav>
            
            <h1 className="text-3xl md:text-4xl font-bold text-white mb-4">Browser Screenshots</h1>
            <p className="text-lg md:text-xl text-gray-300">
              Quick browser screenshots for debugging web applications
            </p>
          </div>
          <CopyMarkdownButton 
            content={pageContent}
            filename="browser-screenshots.md"
            className="flex-shrink-0"
          />
        </div>

        {/* Quick Start Card */}
        <div className="mb-12 p-6 bg-gradient-to-r from-blue-900/20 to-purple-900/20 border border-blue-500/30 rounded-lg">
          <div className="flex items-center gap-3 mb-4">
            <Camera className="w-6 h-6 text-blue-400" />
            <h2 className="text-xl font-semibold text-white">Quick Start</h2>
          </div>
          <p className="text-gray-300 mb-4">
            Take a screenshot in one command - no setup required:
          </p>
          <CommandBlock 
            commands={['co -b "screenshot localhost:3000"']}
          />
          <div className="mt-4 grid grid-cols-1 sm:grid-cols-4 gap-4 text-sm">
            <div className="flex items-center gap-2">
              <Zap className="w-4 h-4 text-yellow-400" />
              <span className="text-gray-300">Instant capture</span>
            </div>
            <div className="flex items-center gap-2">
              <Clock className="w-4 h-4 text-green-400" />
              <span className="text-gray-300">Auto timestamp</span>
            </div>
            <div className="flex items-center gap-2">
              <Layers className="w-4 h-4 text-purple-400" />
              <span className="text-gray-300">Device presets</span>
            </div>
            <div className="flex items-center gap-2">
              <FileText className="w-4 h-4 text-orange-400" />
              <span className="text-gray-300">PNG format</span>
            </div>
          </div>
        </div>

        {/* Command Format */}
        <section className="mb-16">
          <h2 className="text-2xl font-bold text-white mb-6 flex items-center gap-3">
            <Terminal className="w-6 h-6 text-green-400" />
            Command Format
          </h2>

          <div className="bg-gray-900 border border-gray-700 rounded-lg p-6 mb-6">
            <div className="font-mono text-lg text-blue-300 mb-4">
              co -b "screenshot <span className="text-yellow-300">[URL]</span> <span className="text-gray-500">[save to PATH]</span> <span className="text-gray-500">[size SIZE]</span>"
            </div>
            <div className="space-y-2 text-sm">
              <div className="flex items-start gap-2">
                <span className="text-yellow-300 font-mono">[URL]</span>
                <span className="text-gray-300">Required. The page to screenshot (e.g., localhost:3000)</span>
              </div>
              <div className="flex items-start gap-2">
                <span className="text-gray-500 font-mono">[save to PATH]</span>
                <span className="text-gray-300">Optional. Where to save the screenshot</span>
              </div>
              <div className="flex items-start gap-2">
                <span className="text-gray-500 font-mono">[size SIZE]</span>
                <span className="text-gray-300">Optional. Viewport size or device preset</span>
              </div>
            </div>
          </div>
        </section>

        {/* Examples Grid */}
        <section className="mb-16">
          <h2 className="text-2xl font-bold text-white mb-6">Examples</h2>

          <div className="grid gap-6">
            {/* Basic Screenshots */}
            <div className="bg-gradient-to-b from-green-900/20 to-green-800/10 border border-green-500/30 rounded-lg p-6">
              <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
                <Camera className="w-5 h-5 text-green-400" />
                Basic Screenshots
              </h3>
              <CommandBlock 
                commands={[
                  '# Screenshot local development',
                  'co -b "screenshot localhost:3000"',
                  '',
                  '# With specific port',
                  'co -b "screenshot localhost:8080"',
                  '',
                  '# External site',
                  'co -b "screenshot example.com"'
                ]}
              />
            </div>

            {/* Save Locations */}
            <div className="bg-gradient-to-b from-blue-900/20 to-blue-800/10 border border-blue-500/30 rounded-lg p-6">
              <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
                <FileText className="w-5 h-5 text-blue-400" />
                Save to Specific Path
              </h3>
              <CommandBlock 
                commands={[
                  '# Save to temp directory',
                  'co -b "screenshot localhost:3000 save to /tmp/debug.png"',
                  '',
                  '# Save with custom name',
                  'co -b "screenshot localhost:3000 save to homepage.png"',
                  '',
                  '# Save to subdirectory',
                  'co -b "screenshot localhost:3000 save to screenshots/test.png"'
                ]}
              />
            </div>

            {/* Device Sizes */}
            <div className="bg-gradient-to-b from-purple-900/20 to-purple-800/10 border border-purple-500/30 rounded-lg p-6">
              <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
                <Smartphone className="w-5 h-5 text-purple-400" />
                Device Sizes
              </h3>
              <CommandBlock 
                commands={[
                  '# iPhone viewport',
                  'co -b "screenshot localhost:3000 size iphone"',
                  '',
                  '# Custom dimensions',
                  'co -b "screenshot localhost:3000 size 390x844"',
                  '',
                  '# Common presets',
                  'co -b "screenshot localhost:3000 size ipad"',
                  'co -b "screenshot localhost:3000 size desktop"'
                ]}
              />
            </div>
          </div>
        </section>

        {/* Device Presets Table */}
        <section className="mb-16">
          <h2 className="text-2xl font-bold text-white mb-6 flex items-center gap-3">
            <Layers className="w-6 h-6 text-purple-400" />
            Device Presets
          </h2>

          <div className="bg-gray-900 border border-gray-700 rounded-lg overflow-hidden">
            <table className="w-full">
              <thead>
                <tr className="bg-gray-800 border-b border-gray-700">
                  <th className="text-left px-4 py-3 text-gray-300 font-medium">Preset</th>
                  <th className="text-left px-4 py-3 text-gray-300 font-medium">Dimensions</th>
                  <th className="text-left px-4 py-3 text-gray-300 font-medium">Device</th>
                  <th className="text-left px-4 py-3 text-gray-300 font-medium">Icon</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-700">
                <tr>
                  <td className="px-4 py-3 font-mono text-blue-300">iphone</td>
                  <td className="px-4 py-3 text-gray-300">390×844</td>
                  <td className="px-4 py-3 text-gray-300">iPhone 14/15</td>
                  <td className="px-4 py-3"><Smartphone className="w-4 h-4 text-gray-400" /></td>
                </tr>
                <tr>
                  <td className="px-4 py-3 font-mono text-blue-300">android</td>
                  <td className="px-4 py-3 text-gray-300">360×800</td>
                  <td className="px-4 py-3 text-gray-300">Common Android</td>
                  <td className="px-4 py-3"><Smartphone className="w-4 h-4 text-gray-400" /></td>
                </tr>
                <tr>
                  <td className="px-4 py-3 font-mono text-blue-300">ipad</td>
                  <td className="px-4 py-3 text-gray-300">768×1024</td>
                  <td className="px-4 py-3 text-gray-300">iPad</td>
                  <td className="px-4 py-3"><Tablet className="w-4 h-4 text-gray-400" /></td>
                </tr>
                <tr>
                  <td className="px-4 py-3 font-mono text-blue-300">desktop</td>
                  <td className="px-4 py-3 text-gray-300">1920×1080</td>
                  <td className="px-4 py-3 text-gray-300">Full HD Desktop</td>
                  <td className="px-4 py-3"><Monitor className="w-4 h-4 text-gray-400" /></td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>

        {/* Complete Examples */}
        <section className="mb-16">
          <h2 className="text-2xl font-bold text-white mb-6 flex items-center gap-3">
            <Zap className="w-6 h-6 text-yellow-400" />
            Complete Examples
          </h2>

          <div className="space-y-4">
            <CommandBlock 
              title="Debug mobile checkout flow"
              commands={['co -b "screenshot localhost:3000/checkout save to /tmp/checkout-mobile.png size iphone"']}
            />

            <CommandBlock 
              title="Document bug on specific page"
              commands={['co -b "screenshot localhost:3000/xray save to bug-report.png size 1920x1080"']}
            />

            <CommandBlock 
              title="Test responsive design"
              commands={[
                'co -b "screenshot localhost:3000 save to mobile.png size 390x844"',
                'co -b "screenshot localhost:3000 save to tablet.png size 768x1024"',
                'co -b "screenshot localhost:3000 save to desktop.png size 1920x1080"'
              ]}
            />
          </div>
        </section>

        {/* Use Cases */}
        <section className="mb-16">
          <h2 className="text-2xl font-bold text-white mb-6">Use Cases</h2>

          <div className="grid md:grid-cols-2 gap-6">
            {/* Debug Development */}
            <div className="bg-gradient-to-b from-green-900/20 to-green-800/10 border border-green-500/30 rounded-lg p-6">
              <Bug className="w-8 h-8 text-green-400 mb-3" />
              <h3 className="text-lg font-semibold text-white mb-2">Debug Local Development</h3>
              <p className="text-gray-300 text-sm mb-4">
                Quick visual checks during development
              </p>
              <CommandBlock 
                commands={[
                  '# Quick check of homepage',
                  'co -b "screenshot localhost:3000"',
                  '',
                  '# Debug specific route',
                  'co -b "screenshot localhost:3000/api/status"'
                ]}
              />
            </div>

            {/* Document Bugs */}
            <div className="bg-gradient-to-b from-red-900/20 to-red-800/10 border border-red-500/30 rounded-lg p-6">
              <AlertCircle className="w-8 h-8 text-red-400 mb-3" />
              <h3 className="text-lg font-semibold text-white mb-2">Document Bugs</h3>
              <p className="text-gray-300 text-sm mb-4">
                Capture visual proof of issues
              </p>
              <CommandBlock 
                commands={[
                  '# Capture error state',
                  'co -b "screenshot localhost:3000/error save to bug.png"',
                  '',
                  '# Mobile-specific issue',
                  'co -b "screenshot localhost:3000/mobile-bug save to mobile-issue.png size iphone"'
                ]}
              />
            </div>

            {/* Test Responsive */}
            <div className="bg-gradient-to-b from-purple-900/20 to-purple-800/10 border border-purple-500/30 rounded-lg p-6">
              <Layers className="w-8 h-8 text-purple-400 mb-3" />
              <h3 className="text-lg font-semibold text-white mb-2">Test Responsive Design</h3>
              <p className="text-gray-300 text-sm mb-4">
                Verify layouts across devices
              </p>
              <div className="bg-black/30 rounded p-3 text-xs">
                <pre className="text-gray-300 font-mono">
{`for size in iphone android ipad desktop; do
  co -b "screenshot localhost:3000 save to view-$size.png size $size"
done`}
                </pre>
              </div>
            </div>

            {/* CI/CD Integration */}
            <div className="bg-gradient-to-b from-orange-900/20 to-orange-800/10 border border-orange-500/30 rounded-lg p-6">
              <Zap className="w-8 h-8 text-orange-400 mb-3" />
              <h3 className="text-lg font-semibold text-white mb-2">CI/CD Integration</h3>
              <p className="text-gray-300 text-sm mb-4">
                Automated visual testing
              </p>
              <CommandBlock 
                commands={[
                  '# In GitHub Actions',
                  'co -b "screenshot $DEPLOY_URL save to artifacts/deployed.png"'
                ]}
              />
            </div>
          </div>
        </section>

        {/* URL Handling */}
        <section className="mb-16">
          <h2 className="text-2xl font-bold text-white mb-6">URL Handling</h2>

          <div className="bg-gray-900 border border-gray-700 rounded-lg p-6">
            <p className="text-gray-300 mb-4">The command intelligently handles URLs:</p>
            
            <div className="space-y-3">
              <div className="flex items-center gap-4 font-mono text-sm">
                <span className="text-blue-300">localhost</span>
                <span className="text-gray-500">→</span>
                <span className="text-green-300">http://localhost</span>
              </div>
              <div className="flex items-center gap-4 font-mono text-sm">
                <span className="text-blue-300">localhost:3000</span>
                <span className="text-gray-500">→</span>
                <span className="text-green-300">http://localhost:3000</span>
              </div>
              <div className="flex items-center gap-4 font-mono text-sm">
                <span className="text-blue-300">example.com</span>
                <span className="text-gray-500">→</span>
                <span className="text-green-300">https://example.com</span>
              </div>
              <div className="flex items-center gap-4 font-mono text-sm">
                <span className="text-blue-300">http://example.com</span>
                <span className="text-gray-500">→</span>
                <span className="text-green-300">http://example.com</span>
                <span className="text-gray-400 text-xs ml-2">(unchanged)</span>
              </div>
            </div>
          </div>
        </section>

        {/* Installation */}
        <section className="mb-16">
          <h2 className="text-2xl font-bold text-white mb-6">Installation</h2>

          <div className="space-y-6">
            <div className="bg-gradient-to-b from-blue-900/20 to-blue-800/10 border border-blue-500/30 rounded-lg p-6">
              <h3 className="text-lg font-semibold text-white mb-3">Standard Installation</h3>
              <p className="text-gray-300 mb-4">Browser features require Playwright:</p>
              <CommandBlock 
                commands={[
                  'pip install playwright',
                  'playwright install chromium'
                ]}
              />
            </div>

            <div className="bg-gradient-to-b from-purple-900/20 to-purple-800/10 border border-purple-500/30 rounded-lg p-6">
              <h3 className="text-lg font-semibold text-white mb-3">With Browser Support</h3>
              <p className="text-gray-300 mb-4">Or install ConnectOnion with browser support:</p>
              <CommandBlock 
                commands={['pip install connectonion[browser]']}
              />
            </div>
          </div>
        </section>

        {/* Framework Examples */}
        <section className="mb-16">
          <h2 className="text-2xl font-bold text-white mb-6">Framework Examples</h2>

          <div className="grid md:grid-cols-2 gap-4">
            <div className="bg-gray-900 border border-gray-700 rounded-lg p-4">
              <h3 className="text-base font-semibold text-white mb-3">Next.js</h3>
              <CommandBlock 
                commands={[
                  'co -b "screenshot localhost:3000"',
                  'co -b "screenshot localhost:3000/_error save to error.png"'
                ]}
              />
            </div>

            <div className="bg-gray-900 border border-gray-700 rounded-lg p-4">
              <h3 className="text-base font-semibold text-white mb-3">FastAPI</h3>
              <CommandBlock 
                commands={[
                  'co -b "screenshot localhost:8000"',
                  'co -b "screenshot localhost:8000/docs save to api-docs.png"'
                ]}
              />
            </div>

            <div className="bg-gray-900 border border-gray-700 rounded-lg p-4">
              <h3 className="text-base font-semibold text-white mb-3">Django</h3>
              <CommandBlock 
                commands={[
                  'co -b "screenshot localhost:8000"',
                  'co -b "screenshot localhost:8000/admin save to admin.png"'
                ]}
              />
            </div>

            <div className="bg-gray-900 border border-gray-700 rounded-lg p-4">
              <h3 className="text-base font-semibold text-white mb-3">React Dev Server</h3>
              <CommandBlock 
                commands={[
                  'co -b "screenshot localhost:3000"',
                  'co -b "screenshot localhost:3000 size iphone"'
                ]}
              />
            </div>
          </div>
        </section>

        {/* Error Messages */}
        <section className="mb-16">
          <h2 className="text-2xl font-bold text-white mb-6 flex items-center gap-3">
            <AlertCircle className="w-6 h-6 text-red-400" />
            Common Error Messages
          </h2>

          <div className="bg-gray-900 border border-gray-700 rounded-lg overflow-hidden">
            <div className="p-6 space-y-6 font-mono text-sm">
              <div>
                <div className="text-red-400 mb-2">❌ Usage: co -b "screenshot [URL] [save to PATH] [size SIZE]"</div>
                <div className="text-gray-400">Missing URL in command</div>
              </div>

              <div>
                <div className="text-red-400 mb-2">❌ Browser tools not installed</div>
                <div className="text-gray-400">Run: pip install playwright && playwright install chromium</div>
              </div>

              <div>
                <div className="text-red-400 mb-2">❌ Cannot reach http://localhost:3000</div>
                <div className="text-gray-400">Is your server running?</div>
              </div>

              <div>
                <div className="text-red-400 mb-2">❌ Cannot save to /root/test.png (permission denied)</div>
                <div className="text-gray-400">Check file permissions</div>
              </div>
            </div>
          </div>
        </section>

        {/* Tips */}
        <section className="mb-16">
          <h2 className="text-2xl font-bold text-white mb-6">Tips</h2>

          <div className="grid md:grid-cols-2 gap-4">
            <div className="bg-gradient-to-b from-blue-900/20 to-blue-800/10 border border-blue-500/30 rounded-lg p-4">
              <h3 className="text-base font-semibold text-white mb-2">Quick Debug</h3>
              <p className="text-gray-300 text-sm">
                Just <code className="bg-black/30 px-2 py-1 rounded">co -b "screenshot localhost:3000"</code> for instant feedback
              </p>
            </div>

            <div className="bg-gradient-to-b from-green-900/20 to-green-800/10 border border-green-500/30 rounded-lg p-4">
              <h3 className="text-base font-semibold text-white mb-2">Organize Screenshots</h3>
              <p className="text-gray-300 text-sm">
                Use descriptive paths like <code className="bg-black/30 px-2 py-1 rounded">save to bugs/issue-123.png</code>
              </p>
            </div>

            <div className="bg-gradient-to-b from-purple-900/20 to-purple-800/10 border border-purple-500/30 rounded-lg p-4">
              <h3 className="text-base font-semibold text-white mb-2">Test Viewports</h3>
              <p className="text-gray-300 text-sm">
                Use device names (<code className="bg-black/30 px-2 py-1 rounded">iphone</code>, <code className="bg-black/30 px-2 py-1 rounded">ipad</code>) for common sizes
              </p>
            </div>

            <div className="bg-gradient-to-b from-orange-900/20 to-orange-800/10 border border-orange-500/30 rounded-lg p-4">
              <h3 className="text-base font-semibold text-white mb-2">Timestamps</h3>
              <p className="text-gray-300 text-sm">
                Default filenames include timestamp for versioning
              </p>
            </div>
          </div>
        </section>

        {/* Limitations */}
        <section className="mb-16">
          <h2 className="text-2xl font-bold text-white mb-6">Limitations</h2>

          <div className="bg-gray-900 border border-gray-700 rounded-lg p-6">
            <ul className="space-y-3 text-gray-300">
              <li className="flex items-start gap-3">
                <span className="text-yellow-400 mt-0.5">•</span>
                <span>Screenshots only (no interaction, clicking, forms)</span>
              </li>
              <li className="flex items-start gap-3">
                <span className="text-yellow-400 mt-0.5">•</span>
                <span>Single page at a time</span>
              </li>
              <li className="flex items-start gap-3">
                <span className="text-yellow-400 mt-0.5">•</span>
                <span>Headless browser only</span>
              </li>
              <li className="flex items-start gap-3">
                <span className="text-yellow-400 mt-0.5">•</span>
                <span>PNG format only</span>
              </li>
            </ul>

            <div className="mt-4 pt-4 border-t border-gray-700">
              <p className="text-gray-400 text-sm">
                For complex browser automation, use the full ConnectOnion browser agent or Playwright directly.
              </p>
            </div>
          </div>
        </section>

        {/* Summary */}
        <section className="mb-16">
          <div className="bg-gradient-to-r from-blue-900/20 to-purple-900/20 border border-blue-500/30 rounded-lg p-6">
            <h2 className="text-xl font-bold text-white mb-4">Summary</h2>
            <p className="text-gray-300">
              The <code className="bg-black/30 px-2 py-1 rounded">-b</code> flag provides dead-simple browser screenshots. 
              No setup, no complexity - just describe what screenshot you want and where to save it. 
              Perfect for debugging during development.
            </p>
          </div>
        </section>

        {/* Navigation */}
        <ContentNavigation />
      </div>
    </div>
  )
}