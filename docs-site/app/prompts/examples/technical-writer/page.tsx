'use client'

import React, { useState } from 'react'
import { Copy, Check, FileText, ArrowRight, ArrowLeft, Download, Lightbulb, MessageSquare, BookOpen, Layout } from 'lucide-react'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism'
import Link from 'next/link'
import { CopyMarkdownButton } from '../../../../components/CopyMarkdownButton'

const promptContent = `# Technical Documentation Specialist

You create clear, comprehensive technical documentation for developers.

## Documentation Principles
- **Clarity Over Cleverness**: Simple language always wins
- **Examples Everywhere**: Show, don't just tell
- **Progressive Disclosure**: Basic concepts first, advanced later
- **Searchability**: Use clear headings and keywords
- **User-Centered**: Write for your audience's skill level

## Document Types Expertise
- API documentation and reference guides
- User guides and tutorials
- Installation and setup instructions
- Troubleshooting and FAQ guides
- Architecture and design documents
- Code examples and samples

## Writing Style Guidelines
- Use active voice ("Click the button" not "The button should be clicked")
- Present tense for instructions ("The system returns..." not "The system will return...")
- Short sentences and paragraphs for readability
- Consistent terminology throughout
- Visual aids (diagrams, screenshots) when helpful
- Code examples for every concept

## Document Structure Template

### 1. Overview/Purpose
[What this document covers and why it's important]

### 2. Prerequisites
[What users need to know or have before starting]

### 3. Step-by-Step Instructions
[Clear, numbered steps with code examples]

### 4. Code Examples
[Working examples users can copy and run]

### 5. Common Issues and Solutions
[Troubleshooting section with specific error messages]

### 6. Additional Resources
[Links to related documentation, tutorials, community]

## Quality Checklist
- [ ] Can a new user follow this without getting stuck?
- [ ] Are all code examples tested and working?
- [ ] Are error messages and troubleshooting covered?
- [ ] Is the language appropriate for the target audience?
- [ ] Are there enough examples and visual aids?`

const usageExample = `from connectonion import Agent

agent = Agent(
    name="technical_writer",
    system_prompt="""${promptContent}""",
    tools=[...]
)

doc_request = """
Write API documentation for our new user authentication endpoint:
POST /api/auth/login
Parameters: email (string), password (string)  
Returns: JWT token or error message
"""

response = agent.run(doc_request)
print(response)`

const expectedOutput = `# User Authentication API

## Overview/Purpose
This endpoint authenticates users and returns JWT tokens for accessing protected resources.

## Prerequisites
- Valid user account in the system
- API access configured
- HTTP client (curl, Postman, or similar)

## API Endpoint

### POST /api/auth/login

Authenticate a user with email and password credentials.

**URL**: \`/api/auth/login\`
**Method**: \`POST\`
**Content-Type**: \`application/json\`

#### Parameters

| Parameter | Type   | Required | Description           |
|-----------|--------|----------|-----------------------|
| email     | string | Yes      | User's email address  |
| password  | string | Yes      | User's password       |

#### Request Example

\`\`\`bash
curl -X POST https://api.example.com/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "password": "your-password"
  }'
\`\`\`

#### Success Response (200 OK)

\`\`\`json
{
  "success": true,
  "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "expires_in": 3600,
  "user": {
    "id": 123,
    "email": "user@example.com",
    "name": "John Doe"
  }
}
\`\`\`

#### Error Response (401 Unauthorized)

\`\`\`json
{
  "success": false,
  "error": "Invalid credentials",
  "code": "AUTH_FAILED"
}
\`\`\`

## Common Issues and Solutions

**Q: Getting "Invalid credentials" error with correct password**
A: Ensure password doesn't contain special characters that need URL encoding.

**Q: Token expires quickly**  
A: Default expiration is 1 hour. Use refresh token endpoint for longer sessions.

## Additional Resources
- [JWT Token Usage Guide](/docs/jwt-usage)
- [Password Reset API](/docs/auth/reset-password)
- [API Rate Limiting](/docs/rate-limits)`

export default function TechnicalWriterPage() {
  const [copiedId, setCopiedId] = useState<string | null>(null)

  const copyToClipboard = (text: string, id: string) => {
    navigator.clipboard.writeText(text)
    setCopiedId(id)
    setTimeout(() => setCopiedId(null), 2000)
  }

  const markdownContent = `# Technical Writer System Prompt

${promptContent}

## Usage Example

\`\`\`python
${usageExample}
\`\`\`

## Expected Output

\`\`\`
${expectedOutput}
\`\`\`

## Key Learning Points

1. **Documentation Principles**: 5 core principles guide all technical writing decisions
2. **Structure Template**: 6-section format ensures comprehensive coverage
3. **Quality Checklist**: Verification steps ensure documentation effectiveness
4. **User-Centric Approach**: Always consider the reader's perspective and skill level

---

*This is example 6 of 8 in the Progressive Prompt Examples series. Previous: [Data Analyst](/prompts/examples/data-analyst) | Next: [Security Analyst](/prompts/examples/security-analyst)*`

  return (
    <div className="max-w-6xl mx-auto px-8 py-12 lg:py-12 pt-16 lg:pt-12">
      {/* Breadcrumb */}
      <nav className="flex items-center gap-2 text-sm text-gray-400 mb-8">
        <Link href="/" className="hover:text-white transition-colors">Home</Link>
        <ArrowRight className="w-4 h-4" />
        <Link href="/prompts" className="hover:text-white transition-colors">System Prompts</Link>
        <ArrowRight className="w-4 h-4" />
        <Link href="/prompts/examples" className="hover:text-white transition-colors">Examples</Link>
        <ArrowRight className="w-4 h-4" />
        <span className="text-white">Technical Writer</span>
      </nav>

      {/* Header */}
      <div className="flex items-start justify-between mb-12">
        <div className="flex-1">
          <div className="flex items-center gap-4 mb-4">
            <div className="w-16 h-16 bg-indigo-600 rounded-xl flex items-center justify-center">
              <span className="text-2xl font-bold text-white">6</span>
            </div>
            <div>
              <div className="flex items-center gap-3 mb-2">
                <FileText className="w-8 h-8 text-indigo-400" />
                <h1 className="text-4xl font-bold text-white">Technical Documentation Specialist</h1>
                <span className="px-3 py-1 bg-indigo-900/50 text-indigo-300 rounded-full text-sm font-medium">
                  Expert
                </span>
              </div>
              <p className="text-xl text-gray-300">
                Master comprehensive documentation frameworks with user-centric writing principles.
              </p>
            </div>
          </div>
        </div>
        
        <CopyMarkdownButton 
          content={markdownContent}
          filename="technical-writer-prompt.md"
          className="ml-8 flex-shrink-0"
        />
      </div>

      {/* Key Concepts */}
      <div className="mb-12 p-6 bg-indigo-900/20 border border-indigo-500/30 rounded-xl">
        <h2 className="text-xl font-bold text-white mb-4 flex items-center gap-3">
          <Lightbulb className="w-6 h-6 text-indigo-400" />
          Key Learning Concepts
        </h2>
        <div className="grid md:grid-cols-3 gap-6">
          <div className="flex items-start gap-3">
            <BookOpen className="w-5 h-5 text-indigo-400 mt-1 flex-shrink-0" />
            <div>
              <h3 className="text-white font-semibold mb-1">Documentation Principles</h3>
              <p className="text-indigo-200 text-sm">5 core principles that guide all technical writing decisions</p>
            </div>
          </div>
          <div className="flex items-start gap-3">
            <Layout className="w-5 h-5 text-indigo-400 mt-1 flex-shrink-0" />
            <div>
              <h3 className="text-white font-semibold mb-1">Structure Template</h3>
              <p className="text-indigo-200 text-sm">6-section format ensures comprehensive documentation coverage</p>
            </div>
          </div>
          <div className="flex items-start gap-3">
            <MessageSquare className="w-5 h-5 text-indigo-400 mt-1 flex-shrink-0" />
            <div>
              <h3 className="text-white font-semibold mb-1">Quality Standards</h3>
              <p className="text-indigo-200 text-sm">Checklist-driven approach ensures documentation effectiveness</p>
            </div>
          </div>
        </div>
      </div>

      <div className="grid lg:grid-cols-2 gap-12">
        {/* Prompt Content */}
        <div className="space-y-8">
          <div className="bg-gray-900 border border-gray-700 rounded-lg">
            <div className="flex items-center justify-between px-6 py-4 border-b border-gray-700">
              <h3 className="text-xl font-semibold text-white">System Prompt</h3>
              <button
                onClick={() => copyToClipboard(promptContent, 'prompt')}
                className="text-gray-400 hover:text-white transition-colors p-2 rounded-lg hover:bg-gray-800 flex items-center gap-2"
              >
                {copiedId === 'prompt' ? (
                  <>
                    <Check className="w-4 h-4 text-green-400" />
                    <span className="text-green-400 text-sm">Copied!</span>
                  </>
                ) : (
                  <>
                    <Copy className="w-4 h-4" />
                    <span className="text-sm">Copy</span>
                  </>
                )}
              </button>
            </div>
            
            <div className="p-6">
              <SyntaxHighlighter 
                language="markdown" 
                style={vscDarkPlus}
                customStyle={{
                  background: 'transparent',
                  padding: 0,
                  margin: 0,
                  fontSize: '0.875rem',
                  lineHeight: '1.6'
                }}
                wrapLines={true}
                wrapLongLines={true}
                showLineNumbers={true}
                lineNumberStyle={{ 
                  color: '#6b7280', 
                  paddingRight: '1rem',
                  userSelect: 'none'
                }}
              >
                {promptContent}
              </SyntaxHighlighter>
            </div>
          </div>

          {/* Usage Example */}
          <div className="bg-gray-900 border border-gray-700 rounded-lg">
            <div className="flex items-center justify-between px-6 py-4 border-b border-gray-700">
              <h3 className="text-xl font-semibold text-white">Usage Example</h3>
              <button
                onClick={() => copyToClipboard(usageExample, 'usage')}
                className="text-gray-400 hover:text-white transition-colors p-2 rounded-lg hover:bg-gray-800 flex items-center gap-2"
              >
                {copiedId === 'usage' ? (
                  <>
                    <Check className="w-4 h-4 text-green-400" />
                    <span className="text-green-400 text-sm">Copied!</span>
                  </>
                ) : (
                  <>
                    <Copy className="w-4 h-4" />
                    <span className="text-sm">Copy</span>
                  </>
                )}
              </button>
            </div>
            
            <div className="p-6">
              <SyntaxHighlighter 
                language="python" 
                style={vscDarkPlus}
                customStyle={{
                  background: 'transparent',
                  padding: 0,
                  margin: 0,
                  fontSize: '0.875rem',
                  lineHeight: '1.6'
                }}
                showLineNumbers={true}
                lineNumberStyle={{ 
                  color: '#6b7280', 
                  paddingRight: '1rem',
                  userSelect: 'none'
                }}
              >
                {usageExample}
              </SyntaxHighlighter>
            </div>
          </div>
        </div>

        {/* Right Panel */}
        <div className="space-y-8">
          {/* Expected Output */}
          <div className="bg-gray-900 border border-gray-700 rounded-lg">
            <div className="flex items-center gap-3 px-6 py-4 border-b border-gray-700">
              <MessageSquare className="w-5 h-5 text-indigo-400" />
              <h3 className="text-xl font-semibold text-white">Expected Output</h3>
            </div>
            
            <div className="p-6">
              <div className="bg-black/50 rounded-lg p-4 font-mono text-sm ">
                <pre className="text-indigo-200 whitespace-pre-wrap">
                  {expectedOutput}
                </pre>
              </div>
            </div>
          </div>

          {/* Analysis */}
          <div className="bg-gray-900 border border-gray-700 rounded-lg p-6">
            <h3 className="text-xl font-semibold text-white mb-4">Expert Documentation Techniques</h3>
            <div className="space-y-4 text-sm">
              <div>
                <h4 className="font-semibold text-indigo-400 mb-2">📋 Structured Templates</h4>
                <p className="text-gray-300">6-section format ensures comprehensive coverage for any documentation type.</p>
              </div>
              <div>
                <h4 className="font-semibold text-indigo-400 mb-2">✅ Quality Assurance</h4>
                <p className="text-gray-300">Built-in checklist prevents common documentation problems.</p>
              </div>
              <div>
                <h4 className="font-semibold text-indigo-400 mb-2">👥 User-Centric Focus</h4>
                <p className="text-gray-300">Always considers reader's skill level and real-world usage scenarios.</p>
              </div>
            </div>
          </div>

          {/* Download Options */}
          <div className="bg-gray-900 border border-gray-700 rounded-lg p-6">
            <h3 className="text-lg font-semibold text-white mb-4">Download & Customize</h3>
            <div className="space-y-3">
              <a
                href={`data:text/plain;charset=utf-8,${encodeURIComponent(promptContent)}`}
                download="technical_writer.md"
                className="w-full flex items-center justify-center gap-2 px-4 py-3 bg-indigo-600 hover:bg-indigo-700 rounded-lg text-white transition-colors font-medium"
              >
                <Download className="w-4 h-4" />
                Download Prompt File
              </a>
              <p className="text-xs text-gray-400 text-center">
                Perfect for API documentation and technical writing systems
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex justify-between items-center pt-12 mt-12 border-t border-gray-800">
        <div className="text-center">
          <p className="text-sm text-gray-400 mb-1">Previous in series</p>
          <Link 
            href="/prompts/examples/data-analyst" 
            className="flex items-center gap-2 text-white hover:text-gray-300 transition-colors font-medium"
          >
            <ArrowLeft className="w-4 h-4" />
            5. Data Analyst
          </Link>
        </div>
        <div className="text-center">
          <p className="text-sm text-gray-400 mb-1">Next in series</p>
          <Link 
            href="/prompts/examples/security-analyst" 
            className="flex items-center gap-2 text-white hover:text-gray-300 transition-colors font-medium"
          >
            7. Security Analyst
            <ArrowRight className="w-4 h-4" />
          </Link>
        </div>
      </nav>
    </div>
  )
}