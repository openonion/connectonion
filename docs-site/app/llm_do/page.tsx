/*
  DESIGN ISSUES TO FIX:
  
  1. **Missing Core Components** (Priority: HIGH)
     - No CopyMarkdownButton for entire page content
     - Missing table of contents for navigation
     - No PageNavigation component at bottom
     - Fix: Add CopyMarkdownButton, TOC sidebar, PageNavigation
  
  2. **Content Structure** (Priority: HIGH)
     - Examples not progressively complex (violates CLAUDE.md)
     - Missing comparison between providers
     - No error handling examples
     - Fix: Reorder examples simple→complex, add provider comparison, show error cases
  
  3. **Visual Hierarchy** (Priority: MEDIUM)
     - All sections look equally important
     - Headers inconsistent (text-2xl vs text-xl)
     - No visual separation between major sections
     - Fix: Use consistent heading sizes, add section dividers, improve spacing
  
  4. **Mobile Experience** (Priority: MEDIUM)
     - Content too wide on mobile (max-w-5xl)
     - No responsive padding (px-8 fixed)
     - Code blocks require horizontal scroll
     - Fix: Responsive max-width, dynamic padding, better code wrapping
  
  5. **Documentation Gaps** (Priority: LOW)
     - Missing API reference section
     - No troubleshooting guide
     - No links to full documentation
     - Fix: Add API reference table, common issues section, doc links
*/

'use client'
/*
  
  @date: 2025-09-01
  @description: LLM Do Page
*/
import { useState } from 'react'
import Link from 'next/link'
import CopyButton from '../../components/CopyButton'
import CodeWithResult from '../../components/CodeWithResult'
import { ContentNavigation } from '../../components/ContentNavigation'
import { CommandBlock } from '../../components/CommandBlock'
import { ChevronRight, Zap, Package, Shield, Code, Layers, ArrowRight } from 'lucide-react'

export default function LLMPage() {
  const [copiedId, setCopiedId] = useState<string | null>(null)


  return (
    <div className="max-w-5xl mx-auto px-8 py-12 lg:py-12 pt-16 lg:pt-12">
      {/* Header */}
      <div className="mb-10">
        <div className="flex items-center gap-2 text-sm text-gray-400 mb-3">
          <Link href="/" className="hover:text-white transition-colors">Home</Link>
          <span>/</span>
          <span className="text-white">LLM Function</span>
        </div>
        <div className="flex justify-between items-start">
          <div>
            <h1 className="text-4xl font-bold text-white mb-3 flex items-center gap-3">
              <Zap className="w-7 h-7 text-blue-400" /> One-shot LLM Calls
            </h1>
            <p className="text-gray-300 max-w-2xl">
              Make direct LLM calls with optional structured output. Supports OpenAI, Google Gemini, and Anthropic models through a unified interface.
            </p>
          </div>
        </div>
      </div>

            {/* Quick Start Section */}
            <section className="mb-12">
              <h2 className="text-2xl font-bold text-green-400 mb-4">Quick Start</h2>
              
              <CodeWithResult 
                code={`from connectonion import llm_do

# OpenAI (default)
answer = llm_do("What's 2+2?")
print(answer)

# Google Gemini
answer = llm_do("What's 2+2?", model="gemini-1.5-flash")

# Anthropic Claude
answer = llm_do("What's 2+2?", model="claude-3-5-haiku-20241022")`}
                result={`>>> answer = llm_do("What's 2+2?")
>>> print(answer)
4`}
                className="mb-6"
              />
              
              <p className="text-gray-300">That's it! One function for any LLM task across multiple providers.</p>
            </section>

            {/* With Structured Output */}
            <section className="mb-12">
              <h2 className="text-2xl font-bold text-green-400 mb-4">With Structured Output</h2>
              
              <CodeWithResult 
                code={`from pydantic import BaseModel

class Analysis(BaseModel):
    sentiment: str
    confidence: float
    keywords: list[str]

result = llm_do(
    "I absolutely love this product! Best purchase ever!",
    output=Analysis
)
print(result.sentiment)
print(result.confidence)
print(result.keywords)`}
                result={`>>> print(result.sentiment)
'positive'
>>> print(result.confidence)
0.98
>>> print(result.keywords)
['love', 'best', 'ever']`}
                className="mb-6"
              />
            </section>

            {/* Real Examples */}
            <section className="mb-12">
              <h2 className="text-2xl font-bold text-green-400 mb-6">Real Examples</h2>
              
              <div className="space-y-8">
                {/* Extract Data from Text */}
                <div>
                  <h3 className="text-xl font-semibold text-green-400 mb-3">Extract Data from Text</h3>
                  <CodeWithResult 
                    code={`from pydantic import BaseModel

class Invoice(BaseModel):
    invoice_number: str
    total_amount: float
    due_date: str

invoice_text = """
Invoice #INV-2024-001
Total: $1,234.56
Due: January 15, 2024
"""

invoice = llm_do(invoice_text, output=Invoice)
print(invoice.total_amount)`}
                    result={`>>> print(invoice.total_amount)
1234.56`}
                    className="mb-4"
                  />
                </div>

                {/* Use Custom Prompts */}
                <div>
                  <h3 className="text-xl font-semibold text-green-400 mb-3">Use Custom Prompts</h3>
                  <CodeWithResult 
                    code={`# With prompt file
summary = llm_do(
    long_article,
    system_prompt="prompts/summarizer.md"  # Loads from file
)

# With inline prompt
translation = llm_do(
    "Hello world",
    system_prompt="You are a translator. Translate to Spanish only."
)
print(translation)`}
                    result={`>>> print(translation)
Hola mundo`}
                    className="mb-4"
                  />
                </div>

                {/* Quick Analysis Tool */}
                <div>
                  <h3 className="text-xl font-semibold text-green-400 mb-3">Quick Analysis Tool</h3>
                  <CodeWithResult 
                    code={`def analyze_feedback(text: str) -> str:
    """Analyze customer feedback with structured output."""
    
    class FeedbackAnalysis(BaseModel):
        category: str  # bug, feature, praise, complaint
        priority: str  # high, medium, low
        summary: str
        action_required: bool
    
    analysis = llm_do(text, output=FeedbackAnalysis)
    
    if analysis.action_required:
        return f"🚨 {analysis.priority.upper()}: {analysis.summary}"
    return f"📝 {analysis.category}: {analysis.summary}"

# Use in an agent
from connectonion import Agent
agent = Agent("support", tools=[analyze_feedback])`}
                    result={`>>> result = analyze_feedback("The app crashes when I try to upload files!")
>>> print(result)
🚨 HIGH: Application crashes during file upload process`}
                  />
                </div>
              </div>
            </section>

            {/* Supported Models */}
            <section className="mb-12">
              <h2 className="text-2xl font-bold text-green-400 mb-4">Supported Models</h2>
              
              <CodeWithResult 
                code={`# OpenAI models
llm_do("Hello", model="gpt-4o")
llm_do("Hello", model="gpt-4o-mini")
llm_do("Hello", model="gpt-3.5-turbo")

# Google Gemini models
llm_do("Hello", model="gemini-1.5-pro")
llm_do("Hello", model="gemini-1.5-flash")

# Anthropic Claude models
llm_do("Hello", model="claude-3-5-sonnet-latest")
llm_do("Hello", model="claude-3-5-haiku-20241022")
llm_do("Hello", model="claude-3-opus-latest")`}
                result={`>>> llm_do("Hello", model="gpt-4o")
'Hello! How can I assist you today?'

>>> llm_do("Hello", model="gemini-1.5-flash")
'Hello there! How can I help you?'

>>> llm_do("Hello", model="claude-3-5-haiku-20241022")
'Hello! How may I assist you today?'`}
                className="mb-6"
              />
            </section>

            {/* Parameters Table */}
            <section className="mb-12">
              <h2 className="text-2xl font-bold text-green-400 mb-4">Parameters</h2>
              
              <div className="table-wrapper">
                <table className="min-w-full border-collapse">
                  <thead>
                    <tr className="border-b border-gray-700">
                      <th className="text-left py-3 px-4 text-green-400">Parameter</th>
                      <th className="text-left py-3 px-4 text-green-400">Type</th>
                      <th className="text-left py-3 px-4 text-green-400">Default</th>
                      <th className="text-left py-3 px-4 text-green-400">Description</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr className="border-b border-gray-800">
                      <td className="py-3 px-4"><code className="text-purple-400">input</code></td>
                      <td className="py-3 px-4 text-gray-300">str</td>
                      <td className="py-3 px-4 text-gray-400">required</td>
                      <td className="py-3 px-4 text-gray-300">The input text/question</td>
                    </tr>
                    <tr className="border-b border-gray-800">
                      <td className="py-3 px-4"><code className="text-purple-400">output</code></td>
                      <td className="py-3 px-4 text-gray-300">BaseModel</td>
                      <td className="py-3 px-4 text-gray-400">None</td>
                      <td className="py-3 px-4 text-gray-300">Pydantic model for structured output</td>
                    </tr>
                    <tr className="border-b border-gray-800">
                      <td className="py-3 px-4"><code className="text-purple-400">prompt</code></td>
                      <td className="py-3 px-4 text-gray-300">str|Path</td>
                      <td className="py-3 px-4 text-gray-400">None</td>
                      <td className="py-3 px-4 text-gray-300">System prompt (string or file path)</td>
                    </tr>
                    <tr className="border-b border-gray-800">
                      <td className="py-3 px-4"><code className="text-purple-400">model</code></td>
                      <td className="py-3 px-4 text-gray-300">str</td>
                      <td className="py-3 px-4 text-gray-400">"gpt-4o-mini"</td>
                      <td className="py-3 px-4 text-gray-300">Model to use (supports OpenAI, Gemini, Claude)</td>
                    </tr>
                    <tr className="border-b border-gray-800">
                      <td className="py-3 px-4"><code className="text-purple-400">temperature</code></td>
                      <td className="py-3 px-4 text-gray-300">float</td>
                      <td className="py-3 px-4 text-gray-400">0.1</td>
                      <td className="py-3 px-4 text-gray-300">Randomness (0=deterministic, 2=creative)</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </section>

            {/* What You Get */}
            <section className="mb-12">
              <h2 className="text-2xl font-bold text-green-400 mb-6">What You Get</h2>
              
              <div className="grid md:grid-cols-2 gap-4">
                {[
                  { text: "One-shot execution - Single LLM round, no loops", icon: "✅" },
                  { text: "Type safety - Full IDE autocomplete with Pydantic", icon: "✅" },
                  { text: "Flexible prompts - Inline strings or external files", icon: "✅" },
                  { text: "Smart defaults - Fast model, low temperature", icon: "✅" },
                  { text: "Clean errors - Clear messages when things go wrong", icon: "✅" }
                ].map((item, i) => (
                  <div key={i} className="bg-gray-900 rounded-lg p-4 flex items-start gap-3">
                    <span className="text-2xl">{item.icon}</span>
                    <span className="text-gray-300">{item.text}</span>
                  </div>
                ))}
              </div>
            </section>

            {/* Common Patterns */}
            <section className="mb-12">
              <h2 className="text-2xl font-bold text-green-400 mb-6">Common Patterns</h2>
              
              <div className="space-y-6">
                {/* Data Extraction */}
                <div>
                  <h3 className="text-lg font-semibold text-green-400 mb-3">Data Extraction</h3>
                  <CodeWithResult 
                    code={`from pydantic import BaseModel

class Person(BaseModel):
    name: str
    age: int
    occupation: str

person = llm_do("John Doe, 30, software engineer", output=Person)
print(f"Name: {person.name}")
print(f"Age: {person.age}")
print(f"Job: {person.occupation}")`}
                    result={`>>> print(f"Name: {person.name}")
Name: John Doe
>>> print(f"Age: {person.age}")
Age: 30
>>> print(f"Job: {person.occupation}")
Job: software engineer`}
                    className="mb-4"
                  />
                </div>

                {/* Quick Decisions */}
                <div>
                  <h3 className="text-lg font-semibold text-green-400 mb-3">Quick Decisions</h3>
                  <CodeWithResult 
                    code={`is_urgent = llm_do("Customer says: My server is down!")
if "urgent" in is_urgent.lower():
    escalate()`}
                    result={`>>> is_urgent = llm_do("Customer says: My server is down!")
>>> print(is_urgent)
This appears to be an urgent issue that requires immediate attention.`}
                    className="mb-4"
                  />
                </div>

                {/* Format Conversion */}
                <div>
                  <h3 className="text-lg font-semibold text-green-400 mb-3">Format Conversion</h3>
                  <CodeWithResult 
                    code={`class JSONData(BaseModel):
    data: dict

json_result = llm_do("Convert to JSON: name=John age=30", output=JSONData)
print(json_result.data)`}
                    result={`>>> print(json_result.data)
{'name': 'John', 'age': 30}`}
                    className="mb-4"
                  />
                </div>

                {/* Validation */}
                <div>
                  <h3 className="text-lg font-semibold text-green-400 mb-3">Validation</h3>
                  <CodeWithResult 
                    code={`def validate_input(user_text: str) -> bool:
    result = llm_do(
        f"Is this valid SQL? Reply yes/no only: {user_text}",
        temperature=0  # Maximum consistency
    )
    return result.strip().lower() == "yes"`}
                    result={`>>> validate_input("SELECT * FROM users WHERE id = 1")
True
>>> validate_input("DROP TABLE; DELETE everything")
False`}
                    className="mb-4"
                  />
                </div>
              </div>
            </section>

            {/* Tips */}
            <section className="mb-12">
              <h2 className="text-2xl font-bold text-green-400 mb-4">Tips</h2>
              
              <div className="bg-gray-900 rounded-lg p-6">
                <ol className="space-y-3">
                  <li className="flex items-start gap-3">
                    <span className="text-green-400 font-bold">1.</span>
                    <span className="text-gray-300"><strong>Use low temperature (0-0.3) for consistent results</strong></span>
                  </li>
                  <li className="flex items-start gap-3">
                    <span className="text-green-400 font-bold">2.</span>
                    <span className="text-gray-300"><strong>Provide examples in your prompt for better accuracy</strong></span>
                  </li>
                  <li className="flex items-start gap-3">
                    <span className="text-green-400 font-bold">3.</span>
                    <span className="text-gray-300"><strong>Use Pydantic models for anything structured</strong></span>
                  </li>
                  <li className="flex items-start gap-3">
                    <span className="text-green-400 font-bold">4.</span>
                    <span className="text-gray-300"><strong>Cache prompts in files for reusability</strong></span>
                  </li>
                </ol>
              </div>
            </section>

            {/* Comparison with Agent */}
            <section className="mb-12">
              <h2 className="text-2xl font-bold text-green-400 mb-4">Comparison with Agent</h2>
              
              <div className="table-wrapper">
                <table className="min-w-full border-collapse">
                  <thead>
                    <tr className="border-b border-gray-700">
                      <th className="text-left py-3 px-4 text-green-400">Feature</th>
                      <th className="text-left py-3 px-4 text-green-400">llm_do()</th>
                      <th className="text-left py-3 px-4 text-green-400">Agent()</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr className="border-b border-gray-800">
                      <td className="py-3 px-4 text-gray-300">Purpose</td>
                      <td className="py-3 px-4 text-gray-300">One-shot calls</td>
                      <td className="py-3 px-4 text-gray-300">Multi-step workflows</td>
                    </tr>
                    <tr className="border-b border-gray-800">
                      <td className="py-3 px-4 text-gray-300">Tools</td>
                      <td className="py-3 px-4 text-gray-300">No</td>
                      <td className="py-3 px-4 text-gray-300">Yes</td>
                    </tr>
                    <tr className="border-b border-gray-800">
                      <td className="py-3 px-4 text-gray-300">Iterations</td>
                      <td className="py-3 px-4 text-gray-300">Always 1</td>
                      <td className="py-3 px-4 text-gray-300">Up to max_iterations</td>
                    </tr>
                    <tr className="border-b border-gray-800">
                      <td className="py-3 px-4 text-gray-300">State</td>
                      <td className="py-3 px-4 text-gray-300">Stateless</td>
                      <td className="py-3 px-4 text-gray-300">Maintains history</td>
                    </tr>
                    <tr className="border-b border-gray-800">
                      <td className="py-3 px-4 text-gray-300">Best for</td>
                      <td className="py-3 px-4 text-gray-300">Quick tasks</td>
                      <td className="py-3 px-4 text-gray-300">Complex automation</td>
                    </tr>
                  </tbody>
                </table>
              </div>

              <CodeWithResult 
                code={`# Use llm_do() for simple tasks
answer = llm_do("What's the capital of France?")

# Use Agent for multi-step workflows
agent = Agent("assistant", tools=[search, calculate])
result = agent.input("Find the population and calculate density")`}
                result={`>>> answer = llm_do("What's the capital of France?")
>>> print(answer)
The capital of France is Paris.

>>> result = agent.input("Find the population and calculate density")
>>> print(result)
I'll help you find the population and calculate the density. Let me search for the current data...`}
                className="mt-6"
              />
            </section>

            {/* Error Handling */}
            <section className="mb-12">
              <h2 className="text-2xl font-bold text-green-400 mb-4">Error Handling</h2>
              
              <CodeWithResult 
                code={`from connectonion import llm_do
from pydantic import ValidationError

try:
    result = llm_do("Analyze this", output=ComplexModel)
except ValidationError as e:
    print(f"Output didn't match model: {e}")
except Exception as e:
    print(f"LLM call failed: {e}")`}
                result={`>>> try:
...     result = llm_do("Analyze this", output=ComplexModel)
... except ValidationError as e:
...     print(f"Output didn't match model: {e}")
Output didn't match model: 2 validation errors for ComplexModel...`}
                className="mb-6"
              />
            </section>

            {/* Next Steps */}
            <section className="mb-12">
              <h2 className="text-2xl font-bold text-green-400 mb-4">Next Steps</h2>
              
              <div className="grid md:grid-cols-3 gap-4">
                <Link href="/agents" className="bg-gray-900 rounded-lg p-6 hover:bg-gray-800 transition-colors">
                  <h3 className="text-lg font-semibold text-white mb-2">Learn about Agents</h3>
                  <p className="text-sm text-gray-400">For multi-step workflows</p>
                </Link>
                <Link href="/tools" className="bg-gray-900 rounded-lg p-6 hover:bg-gray-800 transition-colors">
                  <h3 className="text-lg font-semibold text-white mb-2">Explore Tools</h3>
                  <p className="text-sm text-gray-400">For extending agents</p>
                </Link>
                <Link href="/xray" className="bg-gray-900 rounded-lg p-6 hover:bg-gray-800 transition-colors">
                  <h3 className="text-lg font-semibold text-white mb-2">See @xray</h3>
                  <p className="text-sm text-gray-400">For debugging</p>
                </Link>
              </div>
            </section>

            <ContentNavigation />
    </div>
  )
}