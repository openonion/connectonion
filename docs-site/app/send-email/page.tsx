'use client'

import { useState } from 'react'
import { Mail, Send, Check, Copy, AlertCircle, Zap, Shield, Globe, Clock, ArrowRight } from 'lucide-react'
import { FaStar, FaCheckCircle, FaEnvelope } from 'react-icons/fa'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { okaidia as monokai } from 'react-syntax-highlighter/dist/esm/styles/prism'
import { CommandBlock } from '../../components/CommandBlock'
import { CopyMarkdownButton } from '../../components/CopyMarkdownButton'
import { ContentNavigation } from '../../components/ContentNavigation'

export default function SendEmailPage() {
  const [copiedCode, setCopiedCode] = useState<string | null>(null)

  const handleCopyCode = (code: string, id: string) => {
    navigator.clipboard.writeText(code)
    setCopiedCode(id)
    setTimeout(() => setCopiedCode(null), 2000)
  }

  const CodeBlock = ({ code, language = 'python', id }: { code: string; language?: string; id: string }) => (
    <div className="relative group max-w-4xl mx-auto">
      <button
        onClick={() => handleCopyCode(code, id)}
        className="absolute right-2 top-2 p-2 bg-gray-700 hover:bg-gray-600 rounded-lg opacity-0 group-hover:opacity-100 transition-opacity z-10"
        aria-label="Copy code"
      >
        {copiedCode === id ? (
          <Check className="w-4 h-4 text-green-400" />
        ) : (
          <Copy className="w-4 h-4 text-gray-300" />
        )}
      </button>
      <SyntaxHighlighter 
        language={language} 
        style={monokai}
        customStyle={{
          borderRadius: '0.5rem',
          padding: '1.25rem',
          margin: 0,
          fontSize: '0.875rem',
          lineHeight: '1.5',
          overflowX: 'auto'
        }}
      >
        {code}
      </SyntaxHighlighter>
    </div>
  )

  const CodeWithResult = ({ code, result, language = 'python', id }: { code: string; result: string; language?: string; id: string }) => (
    <div className="space-y-4 mb-12 max-w-4xl mx-auto">
      <div>
        <div className="text-sm font-semibold text-purple-400 mb-2 uppercase tracking-wider">Code</div>
        <CodeBlock code={code} language={language} id={id} />
      </div>
      <div>
        <div className="text-sm font-semibold text-purple-400 mb-2 uppercase tracking-wider">Result</div>
        <div className="bg-gray-900 border border-gray-700 rounded-lg p-4 overflow-x-auto">
          <pre className="text-sm text-gray-300 whitespace-pre-wrap font-mono">{result}</pre>
        </div>
      </div>
    </div>
  )

  return (
    <div className="min-h-screen bg-gray-950 text-white">
      <div className="max-w-5xl mx-auto px-6 md:px-8 py-12">
        {/* Header */}
        <div className="mb-16">
          <div className="flex items-center gap-4 mb-6">
            <div className="p-3 bg-gradient-to-r from-purple-500/20 to-pink-500/20 rounded-xl border border-purple-500/30">
              <Mail className="w-8 h-8 text-purple-400" />
            </div>
            <div>
              <h1 className="text-4xl md:text-5xl font-bold bg-gradient-to-r from-purple-400 to-pink-400 bg-clip-text text-transparent">
                Send Email
              </h1>
              <p className="text-gray-400 mt-2">Send emails with one line of code. No config, no complexity.</p>
            </div>
          </div>
          <CopyMarkdownButton />
        </div>

        {/* Quick Start */}
        <section className="mb-20">
          <div className="flex items-center gap-3 mb-8">
            <Zap className="w-6 h-6 text-yellow-400" />
            <h2 className="text-3xl font-bold">Quick Start</h2>
            <span className="text-sm text-gray-500 bg-gray-800 px-3 py-1 rounded-full">30 seconds to first email</span>
          </div>

          <div className="bg-gradient-to-r from-purple-500/10 to-pink-500/10 rounded-xl p-8 border border-purple-500/20 mb-8">
            <p className="text-xl font-semibold mb-6 text-purple-300">One line. That's it.</p>
            <CodeBlock 
              code={`from connectonion import send_email

send_email("alice@example.com", "Welcome!", "Thanks for joining us!")`}
              id="quickstart"
            />
          </div>

          <div className="mb-8">
            <p className="text-gray-400 mb-6 text-lg">Run it:</p>
            <CodeWithResult
              code={`>>> send_email("alice@example.com", "Welcome!", "Thanks for joining us!")`}
              result={`{'success': True, 'message_id': 'msg_123', 'from': '0x1234abcd@mail.openonion.ai'}`}
              language="python"
              id="quickstart-run"
            />
            <div className="text-center">
              <p className="text-green-400 font-semibold text-xl flex items-center justify-center gap-2">
                <FaStar className="text-yellow-400" />
                Email sent. Done.
              </p>
            </div>
          </div>
        </section>

        {/* Core Concept */}
        <section className="mb-20">
          <h2 className="text-3xl font-bold mb-8">Core Concept</h2>
          
          <div className="bg-gray-900/50 backdrop-blur border border-gray-700 rounded-xl p-8 mb-10">
            <h3 className="text-xl font-semibold mb-6 text-purple-300">What you get:</h3>
            <div className="grid md:grid-cols-2 gap-6">
              <div className="flex items-start gap-3">
                <Send className="w-5 h-5 text-purple-400 mt-1 flex-shrink-0" />
                <div>
                  <p className="font-medium">Simple function</p>
                  <code className="text-sm bg-gray-800 px-2 py-0.5 rounded">send_email(to, subject, message)</code>
                </div>
              </div>
              <div className="flex items-start gap-3">
                <Shield className="w-5 h-5 text-purple-400 mt-1 flex-shrink-0" />
                <div>
                  <p className="font-medium">Zero configuration</p>
                  <p className="text-sm text-gray-400">No API keys to manage</p>
                </div>
              </div>
              <div className="flex items-start gap-3">
                <Mail className="w-5 h-5 text-purple-400 mt-1 flex-shrink-0" />
                <div>
                  <p className="font-medium">Your own email</p>
                  <p className="text-sm text-gray-400">Unique address for every agent</p>
                </div>
              </div>
              <div className="flex items-start gap-3">
                <Globe className="w-5 h-5 text-purple-400 mt-1 flex-shrink-0" />
                <div>
                  <p className="font-medium">Professional delivery</p>
                  <p className="text-sm text-gray-400">Good reputation & reliability</p>
                </div>
              </div>
            </div>
          </div>

          <div className="mb-8 max-w-4xl mx-auto">
            <h3 className="text-xl font-semibold mb-4">The function signature</h3>
            <CodeBlock 
              code={`def send_email(to: str, subject: str, message: str) -> dict:
    """Send an email. Returns success/failure."""`}
              id="function-signature"
            />
            <p className="text-gray-400 mt-4 text-center">Three parameters. Nothing else.</p>
          </div>
        </section>

        {/* Examples */}
        <section className="mb-20">
          <h2 className="text-3xl font-bold mb-10">Examples</h2>

          <div className="space-y-12">
            <div>
              <h3 className="text-xl font-semibold mb-4 flex items-center gap-2">
                <ArrowRight className="w-5 h-5 text-purple-400" />
                Basic notification
              </h3>
              <CodeWithResult
                code={`send_email("user@example.com", "Order shipped", "Track it: ABC123")`}
                result={`{'success': True, 'message_id': 'msg_124'}`}
                id="example-notification"
              />
            </div>

            <div>
              <h3 className="text-xl font-semibold mb-4 flex items-center gap-2">
                <ArrowRight className="w-5 h-5 text-purple-400" />
                Verification code
              </h3>
              <CodeWithResult
                code={`send_email("bob@example.com", "Your code: 456789", "Verify your account")`}
                result={`{'success': True, 'message_id': 'msg_125'}`}
                id="example-verification"
              />
            </div>

            <div>
              <h3 className="text-xl font-semibold mb-4 flex items-center gap-2">
                <ArrowRight className="w-5 h-5 text-purple-400" />
                Status update
              </h3>
              <CodeWithResult
                code={`send_email("team@example.com", "Build passed", "All tests green")`}
                result={`{'success': True, 'message_id': 'msg_126'}`}
                id="example-status"
              />
            </div>

            <div>
              <h3 className="text-xl font-semibold mb-4 flex items-center gap-2">
                <ArrowRight className="w-5 h-5 text-purple-400" />
                HTML content (automatic)
              </h3>
              <CodeWithResult
                code={`send_email(
    "alice@example.com",
    "Weekly Report",
    "<h1>Progress</h1><p>3 features shipped!</p>"
)`}
                result={`{'success': True, 'message_id': 'msg_127'}`}
                id="example-html"
              />
            </div>
          </div>
        </section>

        {/* Your Email Address */}
        <section className="mb-20">
          <h2 className="text-3xl font-bold mb-10">Your Email Address</h2>

          <div className="bg-gradient-to-r from-purple-500/5 to-pink-500/5 border border-purple-500/20 rounded-xl p-8 mb-10">
            <p className="mb-6 text-lg">Every agent automatically gets an email address:</p>
            <div className="bg-gray-900 rounded-lg p-6 font-mono text-purple-400 text-xl text-center mb-8">
              0x1234abcd@mail.openonion.ai
            </div>
            <div className="grid md:grid-cols-2 gap-4 text-sm">
              <div className="flex items-start gap-2">
                <span className="text-purple-400">•</span>
                <span>Based on your public key (first 10 characters)</span>
              </div>
              <div className="flex items-start gap-2">
                <span className="text-purple-400">•</span>
                <span>Professional domain with good reputation</span>
              </div>
              <div className="flex items-start gap-2">
                <span className="text-purple-400">•</span>
                <span>Generated during <code className="bg-gray-800 px-2 py-0.5 rounded">co init</code></span>
              </div>
              <div className="flex items-start gap-2">
                <span className="text-yellow-400">•</span>
                <span className="text-yellow-400 font-semibold">Activated with <code className="bg-gray-800 px-2 py-0.5 rounded">co auth</code></span>
              </div>
            </div>
          </div>

          <div className="space-y-10 max-w-4xl mx-auto">
            <div>
              <h3 className="text-xl font-semibold mb-4">Check your email address</h3>
              <p className="text-gray-400 mb-4">
                Your email is configured in <code className="bg-gray-800 px-2 py-0.5 rounded">.co/config.toml</code>:
              </p>
              <CodeBlock 
                code={`[agent]
address = "0x04e1c4ae3c57d716383153479dae869e51e86d43d88db8dfa22fba7533f3968d"
short_address = "0x04e1c4ae"
email = "0x04e1c4ae@mail.openonion.ai"
email_active = false  # Becomes true after 'co auth'`}
                language="toml"
                id="config-example"
              />
            </div>

            <div>
              <h3 className="text-xl font-semibold mb-6">Email Activation Lifecycle</h3>
              
              <div className="space-y-4 mb-8">
                <div className="flex items-start gap-4">
                  <span className="bg-purple-500/20 text-purple-400 px-3 py-1 rounded-full font-bold">1</span>
                  <div>
                    <p className="font-semibold">Generated</p>
                    <p className="text-sm text-gray-400">Email address created during <code className="bg-gray-800 px-2 py-0.5 rounded text-xs">co init</code></p>
                  </div>
                </div>
                <div className="flex items-start gap-4">
                  <span className="bg-purple-500/20 text-purple-400 px-3 py-1 rounded-full font-bold">2</span>
                  <div>
                    <p className="font-semibold">Activation Prompt</p>
                    <p className="text-sm text-gray-400">You'll be asked to activate your agent's email</p>
                  </div>
                </div>
                <div className="flex items-start gap-4">
                  <span className="bg-purple-500/20 text-purple-400 px-3 py-1 rounded-full font-bold">3</span>
                  <div>
                    <p className="font-semibold">Active</p>
                    <p className="text-sm text-gray-400">Email is fully functional after authentication</p>
                  </div>
                </div>
              </div>

              <h4 className="font-semibold mb-6 text-purple-300">Two ways to activate:</h4>
              
              <div className="space-y-6">
                <div className="bg-gray-900/50 rounded-lg p-6 border border-gray-700">
                  <p className="font-semibold text-purple-400 mb-3">Option 1: Immediate activation (recommended)</p>
                  <CommandBlock commands={['co init']} />
                  <pre className="text-xs text-gray-400 mt-4 font-mono bg-gray-900 p-3 rounded flex items-start gap-2">
<FaEnvelope className="text-purple-400 mt-1 flex-shrink-0" />
<span>Agent email: 0x1234abcd@mail.openonion.ai (inactive)

Your agent can send emails!
Would you like to activate your agent's email now? [Y/n]: y
Email activated! Your agent can now send emails.</span>
                  </pre>
                </div>

                <div className="bg-gray-900/50 rounded-lg p-6 border border-gray-700">
                  <p className="font-semibold text-purple-400 mb-3">Option 2: Activate later</p>
                  <CommandBlock commands={['co auth']} />
                </div>
              </div>
            </div>
          </div>

          <div className="bg-gradient-to-r from-purple-500/10 to-pink-500/10 rounded-xl p-6 border border-purple-500/20 mt-10">
            <h3 className="text-lg font-semibold mb-3">Want a custom name?</h3>
            <p className="text-gray-400 mb-4">Upgrade to a custom email for $0.99:</p>
            <div className="bg-gray-900 rounded-lg p-4 font-mono text-purple-400 space-y-1">
              <div>mybot@mail.openonion.ai</div>
              <div>ai-assistant@mail.openonion.ai</div>
              <div>support@mail.openonion.ai</div>
            </div>
          </div>
        </section>

        {/* Return Values */}
        <section className="mb-20">
          <h2 className="text-3xl font-bold mb-10">Return Values</h2>

          <div className="space-y-8 max-w-4xl mx-auto">
            <div>
              <h3 className="text-xl font-semibold mb-4 text-green-400">✓ Success</h3>
              <CodeBlock 
                code={`{
    'success': True,
    'message_id': 'msg_123',
    'from': '0x1234abcd@mail.openonion.ai'  # Your agent's email
}`}
                language="python"
                id="return-success"
              />
            </div>

            <div>
              <h3 className="text-xl font-semibold mb-4 text-red-400">✗ Failure</h3>
              <CodeBlock 
                code={`{
    'success': False,
    'error': 'Rate limit exceeded'
}`}
                language="python"
                id="return-failure"
              />
            </div>

            <div className="bg-gray-900/50 rounded-lg p-6 border border-gray-700">
              <h3 className="text-lg font-semibold mb-4">Common errors:</h3>
              <ul className="space-y-2 text-sm">
                <li className="flex items-start gap-2">
                  <span className="text-red-400">•</span>
                  <span><code className="bg-gray-800 px-2 py-0.5 rounded">"Rate limit exceeded"</code> - Hit your quota</span>
                </li>
                <li className="flex items-start gap-2">
                  <span className="text-red-400">•</span>
                  <span><code className="bg-gray-800 px-2 py-0.5 rounded">"Invalid email address"</code> - Check the recipient</span>
                </li>
                <li className="flex items-start gap-2">
                  <span className="text-red-400">•</span>
                  <span><code className="bg-gray-800 px-2 py-0.5 rounded">"Authentication failed"</code> - Token issue</span>
                </li>
              </ul>
            </div>
          </div>
        </section>

        {/* Using with an Agent */}
        <section className="mb-20">
          <h2 className="text-3xl font-bold mb-10">Using with an Agent</h2>

          <div className="max-w-4xl mx-auto space-y-10">
            <div>
              <p className="text-gray-400 mb-6 text-lg">Give your agent the ability to send emails:</p>
              <CodeBlock 
                code={`from connectonion import Agent, send_email

# Create an agent with email capability
agent = Agent(
    "customer_support",
    tools=[send_email],
    instructions="You help users and send them email confirmations"
)

# The agent can now send emails autonomously
response = agent("Send a welcome email to alice@example.com")
# Agent sends: send_email("alice@example.com", "Welcome!", "Thanks for joining...")`}
                id="agent-basic"
              />
            </div>

            <div>
              <h3 className="text-xl font-semibold mb-4">Real-world monitoring example</h3>
              <CodeBlock 
                code={`from connectonion import Agent, send_email
import time

def check_system_status() -> dict:
    """Check if the system is running properly."""
    cpu_usage = 95  # Simulated high CPU
    return {"status": "warning", "cpu": cpu_usage}

# Create monitoring agent
monitor = Agent(
    "system_monitor",
    tools=[check_system_status, send_email],
    instructions="Monitor system health and alert admin@example.com if issues"
)

# Agent checks system and sends alerts
monitor("Check the system and alert if there are problems")
# Agent will:
# 1. Call check_system_status() 
# 2. See high CPU (95%)
# 3. Call send_email("admin@example.com", "Alert: High CPU", "CPU at 95%...")`}
                id="agent-realworld"
              />
            </div>
          </div>
        </section>

        {/* Complete Example */}
        <section className="mb-20">
          <h2 className="text-3xl font-bold mb-10">Complete Example</h2>

          <div className="max-w-4xl mx-auto">
            <p className="text-gray-400 mb-6 text-lg">Here's a real-world example sending different types of emails:</p>

            <CodeBlock 
              code={`from connectonion import send_email

# Welcome email
result = send_email(
    "new_user@example.com",
    "Welcome to our platform!",
    "We're excited to have you. Check out our docs to get started."
)
print(f"Welcome email: {result['success']}")

# Alert notification
result = send_email(
    "admin@example.com",
    "🚨 High CPU usage detected",
    "Server CPU at 95% for the last 5 minutes"
)
print(f"Alert sent: {result['success']}")

# Daily report with HTML
result = send_email(
    "team@example.com",
    "Daily Summary",
    """
    <h2>Today's Metrics</h2>
    <ul>
        <li>Users: 1,234</li>
        <li>Revenue: $5,678</li>
        <li>Uptime: 99.9%</li>
    </ul>
    """
)
print(f"Report sent: {result['success']}")`}
              id="complete-example"
            />
          </div>
        </section>

        {/* The Details */}
        <section className="mb-20">
          <h2 className="text-3xl font-bold mb-10">The Details</h2>

          <div className="grid md:grid-cols-2 gap-6 mb-10">
            <div className="bg-gray-900/50 backdrop-blur border border-gray-700 rounded-xl p-6">
              <h3 className="text-lg font-semibold mb-4 text-purple-300">Quotas</h3>
              <ul className="space-y-3 text-sm">
                <li className="flex justify-between">
                  <span className="text-gray-400">Free tier:</span>
                  <span className="font-mono">100 emails/month</span>
                </li>
                <li className="flex justify-between">
                  <span className="text-gray-400">Plus tier:</span>
                  <span className="font-mono">1,000 emails/month</span>
                </li>
                <li className="flex justify-between">
                  <span className="text-gray-400">Pro tier:</span>
                  <span className="font-mono">10,000 emails/month</span>
                </li>
              </ul>
            </div>

            <div className="bg-gray-900/50 backdrop-blur border border-gray-700 rounded-xl p-6">
              <h3 className="text-lg font-semibold mb-4 text-purple-300">Rate Limiting</h3>
              <p className="text-gray-400 text-sm mb-3">Automatic rate limiting prevents abuse:</p>
              <ul className="space-y-2 text-sm">
                <li className="flex items-start gap-2">
                  <span className="text-purple-400">•</span>
                  <span>Returns error on limit exceeded</span>
                </li>
                <li className="flex items-start gap-2">
                  <span className="text-purple-400">•</span>
                  <span>Resets monthly</span>
                </li>
                <li className="flex items-start gap-2">
                  <span className="text-purple-400">•</span>
                  <span>No configuration needed</span>
                </li>
              </ul>
            </div>

            <div className="bg-gray-900/50 backdrop-blur border border-gray-700 rounded-xl p-6">
              <h3 className="text-lg font-semibold mb-4 text-purple-300">Content Types</h3>
              <ul className="space-y-3 text-sm">
                <li className="flex items-start gap-2">
                  <span className="text-purple-400">•</span>
                  <div>
                    <span className="font-medium">Plain text</span>
                    <p className="text-gray-500 text-xs">Just send a string</p>
                  </div>
                </li>
                <li className="flex items-start gap-2">
                  <span className="text-purple-400">•</span>
                  <div>
                    <span className="font-medium">HTML</span>
                    <p className="text-gray-500 text-xs">Auto-detected from tags</p>
                  </div>
                </li>
                <li className="flex items-start gap-2">
                  <span className="text-purple-400">•</span>
                  <div>
                    <span className="font-medium">Mixed</span>
                    <p className="text-gray-500 text-xs">HTML with plain fallback</p>
                  </div>
                </li>
              </ul>
            </div>

            <div className="bg-gray-900/50 backdrop-blur border border-gray-700 rounded-xl p-6">
              <h3 className="text-lg font-semibold mb-4 text-purple-300">From Address</h3>
              <ul className="space-y-3 text-sm">
                <li>
                  <span className="text-gray-400">Free tier:</span>
                  <div className="font-mono text-xs mt-1 text-purple-400">0x{'{key_prefix}'}@mail.openonion.ai</div>
                </li>
                <li>
                  <span className="text-gray-400">Custom name:</span>
                  <div className="font-mono text-xs mt-1 text-purple-400">yourname@mail.openonion.ai</div>
                </li>
              </ul>
            </div>
          </div>

          <div className="bg-gray-900/50 backdrop-blur border border-gray-700 rounded-xl p-8">
            <h3 className="text-lg font-semibold mb-6 text-purple-300">Behind the Scenes</h3>
            <div className="grid md:grid-cols-2 gap-4 text-sm">
              <div className="flex items-start gap-2">
                <span className="text-purple-400">•</span>
                <span>Email configured during <code className="bg-gray-800 px-2 py-0.5 rounded text-xs">co init</code></span>
              </div>
              <div className="flex items-start gap-2">
                <span className="text-purple-400">•</span>
                <span>Stored in <code className="bg-gray-800 px-2 py-0.5 rounded text-xs">.co/config.toml</code></span>
              </div>
              <div className="flex items-start gap-2">
                <span className="text-purple-400">•</span>
                <span>Uses Resend API for delivery</span>
              </div>
              <div className="flex items-start gap-2">
                <span className="text-purple-400">•</span>
                <span>Automatic retry on failures</span>
              </div>
              <div className="flex items-start gap-2">
                <span className="text-purple-400">•</span>
                <span>Logs all emails for debugging</span>
              </div>
              <div className="flex items-start gap-2">
                <span className="text-purple-400">•</span>
                <span>SPF/DKIM configured</span>
              </div>
            </div>
          </div>
        </section>

        {/* Philosophy */}
        <section className="mb-20">
          <div className="bg-gradient-to-br from-purple-500/10 via-pink-500/10 to-purple-500/10 rounded-2xl p-10 border border-purple-500/20">
            <h2 className="text-3xl font-bold mb-6">Philosophy</h2>
            <p className="text-2xl font-semibold text-purple-300 mb-6">
              One function, one purpose: Send an email
            </p>
            <p className="text-gray-400 mb-6">
              No templates to learn. No configuration files. No complex APIs.
            </p>
            <p className="text-gray-300 mb-8">
              Just <code className="bg-gray-800 px-3 py-1.5 rounded text-purple-400">send_email(to, subject, message)</code>.
            </p>
            <div className="text-center">
              <p className="text-xl font-bold bg-gradient-to-r from-purple-400 to-pink-400 bg-clip-text text-transparent">
                Keep simple things simple.
              </p>
            </div>
          </div>
        </section>

        {/* Navigation */}
        <ContentNavigation />
      </div>
    </div>
  )
}