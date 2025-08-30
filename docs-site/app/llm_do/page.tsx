'use client'

import { useState } from 'react'
import Link from 'next/link'
import CopyButton from '../../components/CopyButton'
import CodeWithResult from '../../components/CodeWithResult'
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
              Make direct LLM calls with optional structured output. One function for any LLM task.
            </p>
          </div>
        </div>
      </div>

            {/* Quick Start Section */}
            <section className="mb-12">
              <h2 className="text-2xl font-bold text-green-400 mb-4">Quick Start</h2>
              
              <CodeWithResult 
                code={`from connectonion import llm_do

answer = llm_do("What's 2+2?")
print(answer)`}
                result={`>>> answer = llm_do("What's 2+2?")
>>> print(answer)
4`}
                className="mb-6"
              />
              
              <p className="text-gray-300">That's it! One function for any LLM task.</p>
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
print(invoice.invoice_number)
print(invoice.total_amount)
print(invoice.due_date)`}
                    result={`>>> print(invoice.invoice_number)
'INV-2024-001'
>>> print(invoice.total_amount)
1234.56
>>> print(invoice.due_date)
'January 15, 2024'`}
                  />
                </div>

                {/* Use Custom Prompts */}
                <div>
                  <h3 className="text-xl font-semibold text-green-400 mb-3">Use Custom Prompts</h3>
                  <CodeWithResult 
                    code={`# With inline prompt
translation = llm_do(
    "Hello world",
    prompt="You are a translator. Translate to Spanish only."
)
print(translation)

# With prompt file
summary = llm_do(
    "Long technical article about AI...",
    prompt="prompts/summarizer.md"  # Loads from file
)
print(summary)`}
                    result={`>>> print(translation)
'Hola mundo'

>>> print(summary)
'AI technology is rapidly advancing with breakthroughs in...'`}
                  />
                </div>

                {/* Quick Analysis Tool */}
                <div>
                  <h3 className="text-xl font-semibold text-green-400 mb-3">Quick Analysis Tool</h3>
                  <CodeWithResult 
                    code={`from connectonion import llm_do, Agent
from pydantic import BaseModel

def analyze_feedback(text: str) -> str:
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

# Test the function
result = analyze_feedback("The app crashes when I try to upload files!")
print(result)

# Use in an agent
agent = Agent("support", tools=[analyze_feedback])`}
                    result={`>>> result = analyze_feedback("The app crashes when I try to upload files!")
>>> print(result)
🚨 HIGH: Application crashes during file upload process`}
                  />
                </div>
              </div>
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
                  />
                </div>

                {/* Quick Decisions */}
                <div>
                  <h3 className="text-lg font-semibold text-green-400 mb-3">Quick Decisions</h3>
                  <CodeWithResult 
                    code={`def check_urgency(message: str) -> bool:
    is_urgent = llm_do(f"Is this urgent? Reply yes/no: {message}")
    return "yes" in is_urgent.lower()

# Test with customer message
if check_urgency("Customer says: My server is down!"):
    print("🚨 Escalating to on-call team...")
else:
    print("📝 Added to regular queue")`}
                    result={`>>> if check_urgency("Customer says: My server is down!"):
...     print("🚨 Escalating to on-call team...")
... else:
...     print("📝 Added to regular queue")
🚨 Escalating to on-call team...`}
                  />
                </div>

                {/* Format Conversion */}
                <div>
                  <h3 className="text-lg font-semibold text-green-400 mb-3">Format Conversion</h3>
                  <CodeWithResult 
                    code={`from pydantic import BaseModel

class JSONData(BaseModel):
    data: dict

json_result = llm_do(
    "Convert to JSON: name=John age=30 city=NYC",
    output=JSONData
)
print(json_result.data)`}
                    result={`>>> print(json_result.data)
{'name': 'John', 'age': 30, 'city': 'NYC'}`}
                  />
                </div>

                {/* Validation */}
                <div>
                  <h3 className="text-lg font-semibold text-green-400 mb-3">Validation</h3>
                  <CodeWithResult 
                    code={`def validate_sql(query: str) -> bool:
    result = llm_do(
        f"Is this valid SQL? Reply yes/no only: {query}",
        temperature=0  # Maximum consistency
    )
    return result.strip().lower() == "yes"

# Test queries
queries = [
    "SELECT * FROM users WHERE id = 1",
    "SLECT * FORM users"  # Typo
]

for q in queries:
    is_valid = validate_sql(q)
    print(f"{'✓' if is_valid else '✗'} {q[:30]}...")`}
                    result={`>>> for q in queries:
...     is_valid = validate_sql(q)
...     print(f"{'✓' if is_valid else '✗'} {q[:30]}...")
✓ SELECT * FROM users WHERE id...
✗ SLECT * FORM users...`}
                  />
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
                code={`from connectonion import llm_do, Agent

# Use llm_do() for simple tasks
answer = llm_do("What's the capital of France?")
print(f"Capital: {answer}")

# Use Agent for multi-step workflows
def search_population(city: str) -> int:
    # Simulated search function
    return 2_161_000 if city == "Paris" else 0

def calculate_density(population: int, area_km2: float) -> float:
    return population / area_km2

agent = Agent("assistant", tools=[search_population, calculate_density])
result = agent.input("Find Paris population and calculate density (area: 105 km²)")
print(f"Agent result: {result}")`}
                result={`>>> print(f"Capital: {answer}")
Capital: Paris

>>> result = agent.input("Find Paris population and calculate density (area: 105 km²)")
>>> print(f"Agent result: {result}")
Agent result: The population density of Paris is approximately 20,580 people per km²`}
              />
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