'use client'

import { useState } from 'react'
import Link from 'next/link'
import CopyButton from '../../components/CopyButton'
import { CopyMarkdownButton } from '../../components/CopyMarkdownButton'
import { CommandBlock } from '../../components/CommandBlock'
import { ChevronRight, Zap, Package, Shield, Code, Layers, ArrowRight } from 'lucide-react'

export default function LLMPage() {
  const [copiedId, setCopiedId] = useState<string | null>(null)

  const pageContent = `# One-shot LLM Calls

Make direct LLM calls with optional structured output.

## Quick Start

\`\`\`python
from connectonion import llm

answer = llm("What's 2+2?")  
print(answer)  # "4"
\`\`\`

That's it! One function for any LLM task.

## With Structured Output

\`\`\`python
from pydantic import BaseModel

class Analysis(BaseModel):
    sentiment: str
    confidence: float
    keywords: list[str]

result = llm(
    "I absolutely love this product! Best purchase ever!",
    output=Analysis
)
print(result.sentiment)    # "positive"
print(result.confidence)   # 0.98
print(result.keywords)     # ["love", "best", "ever"]
\`\`\`

## Real Examples

### Extract Data from Text

\`\`\`python
class Invoice(BaseModel):
    invoice_number: str
    total_amount: float
    due_date: str

invoice_text = """
Invoice #INV-2024-001
Total: $1,234.56
Due: January 15, 2024
"""

invoice = llm(invoice_text, output=Invoice)
print(invoice.total_amount)  # 1234.56
\`\`\`

### Use Custom Prompts

\`\`\`python
# With prompt file
summary = llm(
    long_article,
    prompt="prompts/summarizer.md"  # Loads from file
)

# With inline prompt
translation = llm(
    "Hello world",
    prompt="You are a translator. Translate to Spanish only."
)
print(translation)  # "Hola mundo"
\`\`\`

### Quick Analysis Tool

\`\`\`python
def analyze_feedback(text: str) -> str:
    """Analyze customer feedback with structured output."""
    
    class FeedbackAnalysis(BaseModel):
        category: str  # bug, feature, praise, complaint
        priority: str  # high, medium, low
        summary: str
        action_required: bool
    
    analysis = llm(text, output=FeedbackAnalysis)
    
    if analysis.action_required:
        return f"🚨 {analysis.priority.upper()}: {analysis.summary}"
    return f"📝 {analysis.category}: {analysis.summary}"

# Use in an agent
from connectonion import Agent
agent = Agent("support", tools=[analyze_feedback])
\`\`\`

## Advanced Usage

\`\`\`python
result = llm(
    input="Your text here",
    output=YourModel,        # Optional: Pydantic model for structure
    prompt="instructions",   # Optional: String or file path
    model="gpt-4",          # Optional: Default is "gpt-4o-mini"
    temperature=0.7,        # Optional: Default is 0.1 (consistent)
)
\`\`\`

## Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| \`input\` | str | required | The input text/question |
| \`output\` | BaseModel | None | Pydantic model for structured output |
| \`prompt\` | str\\|Path | None | System prompt (string or file path) |
| \`model\` | str | "gpt-4o-mini" | OpenAI model to use (fast & cheap by default) |
| \`temperature\` | float | 0.1 | Randomness (0=deterministic, 2=creative) |

## What You Get

- ✅ **One-shot execution** - Single LLM round, no loops
- ✅ **Type safety** - Full IDE autocomplete with Pydantic
- ✅ **Flexible prompts** - Inline strings or external files
- ✅ **Smart defaults** - Fast model, low temperature
- ✅ **Clean errors** - Clear messages when things go wrong

## Common Patterns

### Data Extraction
\`\`\`python
class Person(BaseModel):
    name: str
    age: int
    occupation: str

person = llm("John Doe, 30, software engineer", output=Person)
\`\`\`

### Quick Decisions
\`\`\`python
is_urgent = llm("Customer says: My server is down!") 
if "urgent" in is_urgent.lower():
    escalate()
\`\`\`

### Format Conversion
\`\`\`python
class JSONData(BaseModel):
    data: dict

json_result = llm("Convert to JSON: name=John age=30", output=JSONData)
print(json_result.data)  # {"name": "John", "age": 30}
\`\`\`

### Validation
\`\`\`python
def validate_input(user_text: str) -> bool:
    result = llm(
        f"Is this valid SQL? Reply yes/no only: {user_text}",
        temperature=0  # Maximum consistency
    )
    return result.strip().lower() == "yes"
\`\`\`

## Tips

1. **Use low temperature (0-0.3) for consistent results**
2. **Provide examples in your prompt for better accuracy**
3. **Use Pydantic models for anything structured**
4. **Cache prompts in files for reusability**

## Comparison with Agent

| Feature | \`llm()\` | \`Agent()\` |
|---------|---------|-----------|
| Purpose | One-shot calls | Multi-step workflows |
| Tools | No | Yes |
| Iterations | Always 1 | Up to max_iterations |
| State | Stateless | Maintains history |
| Best for | Quick tasks | Complex automation |

\`\`\`python
# Use llm() for simple tasks
answer = llm("What's the capital of France?")

# Use Agent for multi-step workflows
agent = Agent("assistant", tools=[search, calculate])
result = agent.input("Find the population and calculate density")
\`\`\`

## Error Handling

\`\`\`python
from connectonion import llm
from pydantic import ValidationError

try:
    result = llm("Analyze this", output=ComplexModel)
except ValidationError as e:
    print(f"Output didn't match model: {e}")
except Exception as e:
    print(f"LLM call failed: {e}")
\`\`\``

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
              Make direct LLM calls with optional structured output. One function for any LLM task.
            </p>
          </div>
          <CopyMarkdownButton content={pageContent} />
        </div>
      </div>

            {/* Quick Start Section */}
            <section className="mb-12">
              <h2 className="text-2xl font-bold text-green-400 mb-4">Quick Start</h2>
              
              <div className="bg-gray-900 rounded-lg p-6 mb-6">
                <div className="relative">
                  <CopyButton text={`from connectonion import llm\n\nanswer = llm("What's 2+2?")\nprint(answer)  # "4"`} />
                  <pre className="text-sm overflow-x-auto">
                    <code className="language-python">{`from connectonion import llm

answer = llm("What's 2+2?")  
print(answer)  # "4"`}</code>
                  </pre>
                </div>
              </div>
              
              <p className="text-gray-300">That's it! One function for any LLM task.</p>
            </section>

            {/* With Structured Output */}
            <section className="mb-12">
              <h2 className="text-2xl font-bold text-green-400 mb-4">With Structured Output</h2>
              
              <div className="bg-gray-900 rounded-lg p-6 mb-6">
                <div className="relative">
                  <CopyButton text={`from pydantic import BaseModel

class Analysis(BaseModel):
    sentiment: str
    confidence: float
    keywords: list[str]

result = llm(
    "I absolutely love this product! Best purchase ever!",
    output=Analysis
)
print(result.sentiment)    # "positive"
print(result.confidence)   # 0.98
print(result.keywords)     # ["love", "best", "ever"]`} />
                  <pre className="text-sm overflow-x-auto">
                    <code className="language-python">{`from pydantic import BaseModel

class Analysis(BaseModel):
    sentiment: str
    confidence: float
    keywords: list[str]

result = llm(
    "I absolutely love this product! Best purchase ever!",
    output=Analysis
)
print(result.sentiment)    # "positive"
print(result.confidence)   # 0.98
print(result.keywords)     # ["love", "best", "ever"]`}</code>
                  </pre>
                </div>
              </div>
            </section>

            {/* Real Examples */}
            <section className="mb-12">
              <h2 className="text-2xl font-bold text-green-400 mb-6">Real Examples</h2>
              
              <div className="space-y-8">
                {/* Extract Data from Text */}
                <div>
                  <h3 className="text-xl font-semibold text-green-400 mb-3">Extract Data from Text</h3>
                  <div className="bg-gray-900 rounded-lg p-6">
                    <div className="relative">
                      <CopyButton text={`class Invoice(BaseModel):
    invoice_number: str
    total_amount: float
    due_date: str

invoice_text = """
Invoice #INV-2024-001
Total: $1,234.56
Due: January 15, 2024
"""

invoice = llm(invoice_text, output=Invoice)
print(invoice.total_amount)  # 1234.56`} />
                      <pre className="text-sm overflow-x-auto">
                        <code className="language-python">{`class Invoice(BaseModel):
    invoice_number: str
    total_amount: float
    due_date: str

invoice_text = """
Invoice #INV-2024-001
Total: $1,234.56
Due: January 15, 2024
"""

invoice = llm(invoice_text, output=Invoice)
print(invoice.total_amount)  # 1234.56`}</code>
                      </pre>
                    </div>
                  </div>
                </div>

                {/* Use Custom Prompts */}
                <div>
                  <h3 className="text-xl font-semibold text-green-400 mb-3">Use Custom Prompts</h3>
                  <div className="bg-gray-900 rounded-lg p-6">
                    <div className="relative">
                      <CopyButton text={`# With prompt file
summary = llm(
    long_article,
    prompt="prompts/summarizer.md"  # Loads from file
)

# With inline prompt
translation = llm(
    "Hello world",
    prompt="You are a translator. Translate to Spanish only."
)
print(translation)  # "Hola mundo"`} />
                      <pre className="text-sm overflow-x-auto">
                        <code className="language-python">{`# With prompt file
summary = llm(
    long_article,
    prompt="prompts/summarizer.md"  # Loads from file
)

# With inline prompt
translation = llm(
    "Hello world",
    prompt="You are a translator. Translate to Spanish only."
)
print(translation)  # "Hola mundo"`}</code>
                      </pre>
                    </div>
                  </div>
                </div>

                {/* Quick Analysis Tool */}
                <div>
                  <h3 className="text-xl font-semibold text-green-400 mb-3">Quick Analysis Tool</h3>
                  <div className="bg-gray-900 rounded-lg p-6">
                    <div className="relative">
                      <CopyButton text={`def analyze_feedback(text: str) -> str:
    """Analyze customer feedback with structured output."""
    
    class FeedbackAnalysis(BaseModel):
        category: str  # bug, feature, praise, complaint
        priority: str  # high, medium, low
        summary: str
        action_required: bool
    
    analysis = llm(text, output=FeedbackAnalysis)
    
    if analysis.action_required:
        return f"🚨 {analysis.priority.upper()}: {analysis.summary}"
    return f"📝 {analysis.category}: {analysis.summary}"

# Use in an agent
from connectonion import Agent
agent = Agent("support", tools=[analyze_feedback])`} />
                      <pre className="text-sm overflow-x-auto">
                        <code className="language-python">{`def analyze_feedback(text: str) -> str:
    """Analyze customer feedback with structured output."""
    
    class FeedbackAnalysis(BaseModel):
        category: str  # bug, feature, praise, complaint
        priority: str  # high, medium, low
        summary: str
        action_required: bool
    
    analysis = llm(text, output=FeedbackAnalysis)
    
    if analysis.action_required:
        return f"🚨 {analysis.priority.upper()}: {analysis.summary}"
    return f"📝 {analysis.category}: {analysis.summary}"

# Use in an agent
from connectonion import Agent
agent = Agent("support", tools=[analyze_feedback])`}</code>
                      </pre>
                    </div>
                  </div>
                </div>
              </div>
            </section>

            {/* Parameters Table */}
            <section className="mb-12">
              <h2 className="text-2xl font-bold text-green-400 mb-4">Parameters</h2>
              
              <div className="overflow-x-auto">
                <table className="w-full border-collapse">
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
                      <td className="py-3 px-4 text-gray-300">OpenAI model to use</td>
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
              
              <div className="grid md:grid-cols-2 gap-6">
                {/* Data Extraction */}
                <div className="bg-gray-900 rounded-lg p-6">
                  <h3 className="text-lg font-semibold text-green-400 mb-3">Data Extraction</h3>
                  <pre className="text-sm overflow-x-auto">
                    <code className="language-python">{`class Person(BaseModel):
    name: str
    age: int
    occupation: str

person = llm("John Doe, 30, software engineer", output=Person)`}</code>
                  </pre>
                </div>

                {/* Quick Decisions */}
                <div className="bg-gray-900 rounded-lg p-6">
                  <h3 className="text-lg font-semibold text-green-400 mb-3">Quick Decisions</h3>
                  <pre className="text-sm overflow-x-auto">
                    <code className="language-python">{`is_urgent = llm("Customer says: My server is down!") 
if "urgent" in is_urgent.lower():
    escalate()`}</code>
                  </pre>
                </div>

                {/* Format Conversion */}
                <div className="bg-gray-900 rounded-lg p-6">
                  <h3 className="text-lg font-semibold text-green-400 mb-3">Format Conversion</h3>
                  <pre className="text-sm overflow-x-auto">
                    <code className="language-python">{`class JSONData(BaseModel):
    data: dict

json_result = llm("Convert to JSON: name=John age=30", output=JSONData)
print(json_result.data)  # {"name": "John", "age": 30}`}</code>
                  </pre>
                </div>

                {/* Validation */}
                <div className="bg-gray-900 rounded-lg p-6">
                  <h3 className="text-lg font-semibold text-green-400 mb-3">Validation</h3>
                  <pre className="text-sm overflow-x-auto">
                    <code className="language-python">{`def validate_input(user_text: str) -> bool:
    result = llm(
        f"Is this valid SQL? Reply yes/no only: {user_text}",
        temperature=0  # Maximum consistency
    )
    return result.strip().lower() == "yes"`}</code>
                  </pre>
                </div>
              </div>
            </section>

            {/* Comparison with Agent */}
            <section className="mb-12">
              <h2 className="text-2xl font-bold text-green-400 mb-4">Comparison with Agent</h2>
              
              <div className="overflow-x-auto mb-6">
                <table className="w-full border-collapse">
                  <thead>
                    <tr className="border-b border-gray-700">
                      <th className="text-left py-3 px-4 text-green-400">Feature</th>
                      <th className="text-left py-3 px-4 text-green-400">llm()</th>
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

              <div className="bg-gray-900 rounded-lg p-6">
                <div className="relative">
                  <CopyButton text={`# Use llm() for simple tasks
answer = llm("What's the capital of France?")

# Use Agent for multi-step workflows
agent = Agent("assistant", tools=[search, calculate])
result = agent.input("Find the population and calculate density")`} />
                  <pre className="text-sm overflow-x-auto">
                    <code className="language-python">{`# Use llm() for simple tasks
answer = llm("What's the capital of France?")

# Use Agent for multi-step workflows
agent = Agent("assistant", tools=[search, calculate])
result = agent.input("Find the population and calculate density")`}</code>
                  </pre>
                </div>
              </div>
            </section>

            {/* Tips */}
            <section className="mb-12">
              <h2 className="text-2xl font-bold text-green-400 mb-4">Tips</h2>
              
              <div className="space-y-3">
                {[
                  "Use low temperature (0-0.3) for consistent results",
                  "Provide examples in your prompt for better accuracy",
                  "Use Pydantic models for anything structured",
                  "Cache prompts in files for reusability"
                ].map((tip, i) => (
                  <div key={i} className="bg-gray-900 rounded-lg p-4 flex items-start gap-3">
                    <span className="text-green-400 font-bold">{i + 1}.</span>
                    <span className="text-gray-300">{tip}</span>
                  </div>
                ))}
              </div>
            </section>

            {/* Next Steps */}
            <section className="mb-12">
              <h2 className="text-2xl font-bold text-green-400 mb-6">Next Steps</h2>
              
              <div className="grid md:grid-cols-3 gap-4">
                <a href="/tools" className="bg-gray-900 rounded-lg p-6 hover:bg-gray-800 transition-colors group">
                  <div className="flex items-center gap-3 mb-3">
                    <Code className="w-5 h-5 text-green-400" />
                    <h3 className="text-lg font-semibold text-green-400">Tools</h3>
                  </div>
                  <p className="text-gray-300 text-sm">Extend agents with custom tools</p>
                  <ChevronRight className="w-4 h-4 text-gray-400 group-hover:text-green-400 mt-2" />
                </a>
                
                <a href="/xray" className="bg-gray-900 rounded-lg p-6 hover:bg-gray-800 transition-colors group">
                  <div className="flex items-center gap-3 mb-3">
                    <Zap className="w-5 h-5 text-green-400" />
                    <h3 className="text-lg font-semibold text-green-400">@xray Decorator</h3>
                  </div>
                  <p className="text-gray-300 text-sm">Debug your LLM calls</p>
                  <ChevronRight className="w-4 h-4 text-gray-400 group-hover:text-green-400 mt-2" />
                </a>
                
                <a href="/prompts" className="bg-gray-900 rounded-lg p-6 hover:bg-gray-800 transition-colors group">
                  <div className="flex items-center gap-3 mb-3">
                    <Layers className="w-5 h-5 text-green-400" />
                    <h3 className="text-lg font-semibold text-green-400">System Prompts</h3>
                  </div>
                  <p className="text-gray-300 text-sm">Learn about prompt management</p>
                  <ChevronRight className="w-4 h-4 text-gray-400 group-hover:text-green-400 mt-2" />
                </a>
              </div>
            </section>
    </div>
  )
}