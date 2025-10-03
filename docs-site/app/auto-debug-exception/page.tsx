'use client'

import { useState } from 'react'
import { Bug, Zap, Check, Copy, AlertTriangle, Terminal, Play, FileCode, Shield } from 'lucide-react'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { okaidia as monokai } from 'react-syntax-highlighter/dist/esm/styles/prism'
import { CommandBlock } from '../../components/CommandBlock'
import { CopyMarkdownButton } from '../../components/CopyMarkdownButton'
import { ContentNavigation } from '../../components/ContentNavigation'

export default function AutoDebugExceptionPage() {
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

  return (
    <div className="min-h-screen bg-gray-950 text-white">
      <div className="max-w-5xl mx-auto px-6 md:px-8 py-12">
        {/* Header */}
        <div className="mb-16">
          <div className="flex items-center gap-4 mb-6">
            <div className="p-3 bg-gradient-to-r from-red-500/20 to-orange-500/20 rounded-xl border border-red-500/30">
              <Bug className="w-8 h-8 text-red-400" />
            </div>
            <div>
              <h1 className="text-4xl md:text-5xl font-bold bg-gradient-to-r from-red-400 to-orange-400 bg-clip-text text-transparent">
                Auto Debug Exception
              </h1>
              <p className="text-gray-400 mt-2">AI debugger for uncaught exceptions with runtime inspection</p>
            </div>
          </div>

          {/* Important Notice */}
          <div className="bg-yellow-500/10 border border-yellow-500/30 rounded-xl p-6 mb-6">
            <div className="flex items-start gap-3">
              <AlertTriangle className="w-5 h-5 text-yellow-400 mt-1 flex-shrink-0" />
              <div>
                <p className="font-semibold text-yellow-400 mb-2">Debugs ONLY uncaught exceptions</p>
                <p className="text-sm text-gray-300">
                  This feature only works for uncaught exceptions - crashes, raised exceptions, and failed assertions.
                  For logic errors that don't crash, use <code className="bg-gray-800 px-2 py-0.5 rounded text-yellow-400">raise</code> or <code className="bg-gray-800 px-2 py-0.5 rounded text-yellow-400">assert</code> to convert them to exceptions.
                </p>
              </div>
            </div>
          </div>

          <CopyMarkdownButton />
        </div>

        {/* Quick Start */}
        <section className="mb-20">
          <div className="flex items-center gap-3 mb-8">
            <Zap className="w-6 h-6 text-yellow-400" />
            <h2 className="text-3xl font-bold">Quick Start</h2>
            <span className="text-sm text-gray-500 bg-gray-800 px-3 py-1 rounded-full">30 seconds to AI debugging</span>
          </div>

          <div className="bg-gradient-to-r from-red-500/10 to-orange-500/10 rounded-xl p-8 border border-red-500/20 mb-8">
            <p className="text-xl font-semibold mb-6 text-red-300">One line to enable. Automatic AI analysis on crashes.</p>
            <CodeBlock
              code={`from connectonion import auto_debug_exception

# Enable AI debugging for exceptions
auto_debug_exception()

# Your code - any uncaught exception triggers AI analysis
data = {"users": []}
average = sum(u["age"] for u in data["users"]) / len(data["users"])  # Crashes!`}
              id="quickstart"
            />
          </div>

          <div className="bg-gray-900/50 rounded-lg p-6 border border-gray-700 mb-8">
            <h3 className="text-lg font-semibold mb-4 text-red-300">When this crashes, the AI will:</h3>
            <div className="space-y-3">
              <div className="flex items-start gap-3">
                <span className="bg-red-500/20 text-red-400 px-3 py-1 rounded-full font-bold flex-shrink-0">1</span>
                <p>Show the normal Python traceback first</p>
              </div>
              <div className="flex items-start gap-3">
                <span className="bg-red-500/20 text-red-400 px-3 py-1 rounded-full font-bold flex-shrink-0">2</span>
                <p>Execute code in the crashed context to understand what happened</p>
              </div>
              <div className="flex items-start gap-3">
                <span className="bg-red-500/20 text-red-400 px-3 py-1 rounded-full font-bold flex-shrink-0">3</span>
                <p>Test potential fixes with your actual data</p>
              </div>
              <div className="flex items-start gap-3">
                <span className="bg-red-500/20 text-red-400 px-3 py-1 rounded-full font-bold flex-shrink-0">4</span>
                <p>Provide a working solution you can copy-paste</p>
              </div>
            </div>
          </div>
        </section>

        {/* What Makes This Special */}
        <section className="mb-20">
          <h2 className="text-3xl font-bold mb-10">What Makes This Special</h2>

          <div className="grid md:grid-cols-3 gap-6">
            <div className="bg-gray-900/50 backdrop-blur border border-gray-700 rounded-xl p-6">
              <FileCode className="w-8 h-8 text-red-400 mb-4" />
              <h3 className="text-xl font-semibold mb-3">Live Runtime Access</h3>
              <p className="text-gray-400 text-sm">
                The AI isn't just reading your code - it has access to the actual runtime state when the crash occurred.
                It can execute any Python expression using your variables and see the real values that caused the problem.
              </p>
            </div>

            <div className="bg-gray-900/50 backdrop-blur border border-gray-700 rounded-xl p-6">
              <Check className="w-8 h-8 text-green-400 mb-4" />
              <h3 className="text-xl font-semibold mb-3">Verified Solutions</h3>
              <p className="text-gray-400 text-sm">
                Every fix is tested with your actual data before being suggested.
                No more "this might work" - only proven solutions that actually work with your data.
              </p>
            </div>

            <div className="bg-gray-900/50 backdrop-blur border border-gray-700 rounded-xl p-6">
              <Bug className="w-8 h-8 text-red-400 mb-4" />
              <h3 className="text-xl font-semibold mb-3">Precise Analysis</h3>
              <p className="text-gray-400 text-sm">
                The AI can explore your data structures, check types, validate assumptions,
                and trace variables through the call stack to find the root cause.
              </p>
            </div>
          </div>
        </section>

        {/* Runtime Inspection Tools */}
        <section className="mb-20">
          <h2 className="text-3xl font-bold mb-10">Runtime Inspection Tools</h2>
          <p className="text-gray-400 mb-8 text-lg">
            The AI has access to powerful tools for investigating the crashed state:
          </p>

          <div className="space-y-4">
            <div className="bg-gray-900/50 border border-gray-700 rounded-lg p-6">
              <h3 className="font-mono text-red-400 text-lg mb-2">execute_in_frame(code)</h3>
              <p className="text-gray-400 text-sm">
                Run any Python code in the exception context. Check variables, test expressions, explore the state.
              </p>
            </div>

            <div className="bg-gray-900/50 border border-gray-700 rounded-lg p-6">
              <h3 className="font-mono text-red-400 text-lg mb-2">inspect_object(name)</h3>
              <p className="text-gray-400 text-sm">
                Deep dive into any object - see its type, attributes, methods, and values.
              </p>
            </div>

            <div className="bg-gray-900/50 border border-gray-700 rounded-lg p-6">
              <h3 className="font-mono text-red-400 text-lg mb-2">test_fix(original, fixed)</h3>
              <p className="text-gray-400 text-sm">
                Test a potential fix using the actual runtime data before suggesting it to you.
              </p>
            </div>

            <div className="bg-gray-900/50 border border-gray-700 rounded-lg p-6">
              <h3 className="font-mono text-red-400 text-lg mb-2">validate_assumption(hypothesis)</h3>
              <p className="text-gray-400 text-sm">
                Test hypotheses about what caused the crash by running code in the crashed context.
              </p>
            </div>

            <div className="bg-gray-900/50 border border-gray-700 rounded-lg p-6">
              <h3 className="font-mono text-red-400 text-lg mb-2">trace_variable(var_name)</h3>
              <p className="text-gray-400 text-sm">
                See how a variable's value changed through the call stack leading to the crash.
              </p>
            </div>
          </div>
        </section>

        {/* Real Examples */}
        <section className="mb-20">
          <h2 className="text-3xl font-bold mb-10">Real-World Examples</h2>

          <div className="space-y-12">
            {/* Example 1: Division by Zero */}
            <div>
              <h3 className="text-2xl font-semibold mb-4 flex items-center gap-2">
                <span className="text-red-400">1.</span> Empty Collection Crash
              </h3>
              <CodeBlock
                code={`from connectonion import auto_debug_exception
auto_debug_exception()

def calculate_metrics(scores):
    return {
        'average': sum(scores) / len(scores),  # Crashes if empty!
        'maximum': max(scores),
        'minimum': min(scores)
    }

result = calculate_metrics([])  # 💥 Multiple issues!`}
                id="example-1"
              />

              <div className="mt-6 bg-gray-900/70 border border-red-500/30 rounded-lg p-6">
                <p className="font-semibold text-red-300 mb-4">AI Runtime Debug Analysis:</p>
                <div className="space-y-4 text-sm">
                  <div>
                    <p className="font-semibold text-purple-400 mb-2">What I found:</p>
                    <ul className="space-y-1 text-gray-300 font-mono text-xs">
                      <li>• Executed: len(scores) → 0</li>
                      <li>• Executed: sum(scores) → 0</li>
                      <li>• The division 0/0 causes ZeroDivisionError</li>
                      <li>• Also tested: max([]) raises ValueError</li>
                    </ul>
                  </div>
                  <div>
                    <p className="font-semibold text-purple-400 mb-2">Why it failed:</p>
                    <p className="text-gray-300">Empty list causes division by zero and max()/min() to fail</p>
                  </div>
                  <div>
                    <p className="font-semibold text-green-400 mb-2">Verified fix (tested with your data):</p>
                    <CodeBlock
                      code={`def calculate_metrics(scores):
    if not scores:
        return {
            'average': 0,
            'maximum': None,
            'minimum': None
        }
    return {
        'average': sum(scores) / len(scores),
        'maximum': max(scores),
        'minimum': min(scores)
    }`}
                      id="example-1-fix"
                    />
                  </div>
                </div>
              </div>
            </div>

            {/* Example 2: KeyError */}
            <div>
              <h3 className="text-2xl font-semibold mb-4 flex items-center gap-2">
                <span className="text-red-400">2.</span> Nested Dictionary Access
              </h3>
              <CodeBlock
                code={`from connectonion import auto_debug_exception
auto_debug_exception()

# API response with unexpected structure
response = {
    'data': {
        'user': {
            'profile': {'name': 'Alice'}
            # Missing 'settings' key!
        }
    }
}

# Try to access nested key
theme = response['data']['user']['settings']['theme']  # 💥 KeyError!`}
                id="example-2"
              />

              <div className="mt-6 bg-gray-900/70 border border-red-500/30 rounded-lg p-6">
                <p className="font-semibold text-red-300 mb-4">AI Runtime Debug Analysis:</p>
                <div className="space-y-4 text-sm">
                  <div>
                    <p className="font-semibold text-purple-400 mb-2">What I found:</p>
                    <ul className="space-y-1 text-gray-300 font-mono text-xs">
                      <li>• Executed: response['data']['user'].keys() → ['profile']</li>
                      <li>• Missing key: 'settings' not in user dict</li>
                      <li>• Available: only 'profile' exists</li>
                    </ul>
                  </div>
                  <div>
                    <p className="font-semibold text-green-400 mb-2">Verified fix:</p>
                    <CodeBlock
                      code={`# Use .get() with default value
theme = response.get('data', {}).get('user', {}).get('settings', {}).get('theme', 'light')

# Or check existence first
if 'settings' in response['data']['user']:
    theme = response['data']['user']['settings']['theme']
else:
    theme = 'light'  # Default`}
                      id="example-2-fix"
                    />
                  </div>
                </div>
              </div>
            </div>

            {/* Example 3: Logic Error with Assert */}
            <div>
              <h3 className="text-2xl font-semibold mb-4 flex items-center gap-2">
                <span className="text-red-400">3.</span> Debugging Logic Errors with Assert
              </h3>
              <p className="text-gray-400 mb-4">
                For logic errors that don't crash, use <code className="bg-gray-800 px-2 py-0.5 rounded text-red-400">assert</code> to trigger AI debugging:
              </p>
              <CodeBlock
                code={`from connectonion import auto_debug_exception, Agent
auto_debug_exception()

# Create a sentiment analyzer
agent = Agent("sentiment", system_prompt="Analyze sentiment. Return ONLY 'positive', 'negative', or 'neutral'.")

text = "This product is terrible!"
result = agent.input(text)

# Validate output with assertion
valid_sentiments = ["positive", "negative", "neutral"]
actual = result.strip().lower()

assert actual in valid_sentiments, f"Invalid sentiment: '{actual}'"
assert actual == "negative", f"Wrong sentiment for '{text}': got '{actual}'"  # 💥 Triggers if wrong!`}
                id="example-3"
              />

              <div className="mt-6 bg-blue-500/10 border border-blue-500/30 rounded-lg p-6">
                <p className="font-semibold text-blue-300 mb-2">💡 Pro Tip:</p>
                <p className="text-gray-300 text-sm">
                  Use <code className="bg-gray-800 px-2 py-0.5 rounded">assert</code> statements to catch logic errors and wrong AI outputs.
                  When an assertion fails, auto_debug_exception kicks in with full runtime access to help you understand what went wrong.
                </p>
              </div>
            </div>
          </div>
        </section>

        {/* What It Debugs */}
        <section className="mb-20">
          <h2 className="text-3xl font-bold mb-10">What It Debugs</h2>

          <div className="grid md:grid-cols-2 gap-6">
            <div className="bg-green-500/10 border border-green-500/30 rounded-lg p-6">
              <h3 className="text-lg font-semibold mb-4 text-green-400 flex items-center gap-2">
                <Check className="w-5 h-5" />
                Debugs These
              </h3>
              <ul className="space-y-2 text-sm">
                <li className="flex items-start gap-2">
                  <span className="text-green-400">✓</span>
                  <span>Crashes: KeyError, TypeError, ZeroDivisionError, etc.</span>
                </li>
                <li className="flex items-start gap-2">
                  <span className="text-green-400">✓</span>
                  <span>Raised exceptions: raise ValueError("invalid")</span>
                </li>
                <li className="flex items-start gap-2">
                  <span className="text-green-400">✓</span>
                  <span>Failed assertions: assert x {'>'} 0, "must be positive"</span>
                </li>
                <li className="flex items-start gap-2">
                  <span className="text-green-400">✓</span>
                  <span>Any uncaught exception that reaches sys.excepthook</span>
                </li>
              </ul>
            </div>

            <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-6">
              <h3 className="text-lg font-semibold mb-4 text-red-400 flex items-center gap-2">
                <AlertTriangle className="w-5 h-5" />
                Doesn't Debug These
              </h3>
              <ul className="space-y-2 text-sm">
                <li className="flex items-start gap-2">
                  <span className="text-red-400">✗</span>
                  <span>Logic errors that don't raise exceptions</span>
                </li>
                <li className="flex items-start gap-2">
                  <span className="text-red-400">✗</span>
                  <span>Wrong outputs (unless you assert they're correct)</span>
                </li>
                <li className="flex items-start gap-2">
                  <span className="text-red-400">✗</span>
                  <span>Performance issues (slow code that runs fine)</span>
                </li>
                <li className="flex items-start gap-2">
                  <span className="text-red-400">✗</span>
                  <span>Infinite loops (code that never raises an exception)</span>
                </li>
              </ul>
            </div>
          </div>

          <div className="mt-8 bg-yellow-500/10 border border-yellow-500/30 rounded-lg p-6">
            <p className="font-semibold text-yellow-400 mb-2">Solution:</p>
            <p className="text-gray-300 text-sm">
              To debug logic errors, convert them to exceptions using <code className="bg-gray-800 px-2 py-0.5 rounded text-yellow-400">raise</code> or <code className="bg-gray-800 px-2 py-0.5 rounded text-yellow-400">assert</code>.
              This triggers auto_debug_exception and gives you AI analysis with runtime inspection.
            </p>
          </div>
        </section>

        {/* Configuration */}
        <section className="mb-20">
          <h2 className="text-3xl font-bold mb-10">Configuration</h2>

          <div className="space-y-8">
            <div>
              <h3 className="text-xl font-semibold mb-4">Choose AI Model</h3>
              <CodeBlock
                code={`# Default: o4-mini (fast and cheap)
auto_debug_exception()

# Use a more powerful model
auto_debug_exception(model="gpt-4o")

# Use Claude for complex analysis
auto_debug_exception(model="claude-sonnet-4")`}
                id="config-model"
              />
            </div>

            <div>
              <h3 className="text-xl font-semibold mb-4">Disable Temporarily</h3>
              <p className="text-gray-400 mb-4">Set environment variable to disable:</p>
              <CodeBlock
                code={`# In your .env file
CONNECTONION_AUTO_DEBUG=false

# Or in terminal
export CONNECTONION_AUTO_DEBUG=false`}
                language="bash"
                id="config-disable"
              />
            </div>
          </div>
        </section>

        {/* Philosophy */}
        <section className="mb-20">
          <div className="bg-gradient-to-br from-red-500/10 via-orange-500/10 to-red-500/10 rounded-2xl p-10 border border-red-500/20">
            <h2 className="text-3xl font-bold mb-6">Philosophy</h2>
            <p className="text-2xl font-semibold text-red-300 mb-6">
              No more guessing. Get verified solutions.
            </p>
            <p className="text-gray-400 mb-6">
              Traditional debugging tools show you *what* crashed. We show you *why* it crashed and *how* to fix it -
              tested with your actual data.
            </p>
            <p className="text-gray-300 mb-8">
              The AI has live access to your program's runtime state. It can execute code, inspect objects, and test fixes
              before suggesting them. Every solution is verified to work with your data.
            </p>
            <div className="text-center">
              <p className="text-xl font-bold bg-gradient-to-r from-red-400 to-orange-400 bg-clip-text text-transparent">
                From crash to solution in seconds.
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
