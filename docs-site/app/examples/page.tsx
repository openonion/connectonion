'use client'

import React, { useState } from 'react'
import { Copy, Check, Play, Terminal, ArrowRight, Code, Database, User, FileText, Clock, Zap } from 'lucide-react'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism'
import Link from 'next/link'
import { CopyMarkdownButton } from '../../components/CopyMarkdownButton'

const examples = [
  {
    id: 'hello-world',
    title: '1. Hello World Agent',
    description: 'The simplest possible agent - just one greeting tool',
    icon: User,
    color: 'text-green-400',
    difficulty: 'Beginner',
    code: `from connectonion import Agent

def greet(name: str) -> str:
    """Say hello to someone."""
    return f"Hello, {name}! Nice to meet you!"

# Create the simplest agent
agent = Agent(
    name="greeter",
    tools=[greet]
)

# Use it
response = agent.run("Say hello to Alice")
print(response)`,
    output: `Hello, Alice! Nice to meet you!`
  },
  {
    id: 'calculator-basic',
    title: '2. Basic Calculator',
    description: 'Simple math operations with error handling',
    icon: Code,
    color: 'text-blue-400',
    difficulty: 'Beginner',
    code: `from connectonion import Agent

def calculate(expression: str) -> str:
    """Safely evaluate basic math expressions."""
    try:
        # Only allow safe characters
        allowed = set('0123456789+-*/()., ')
        if not all(c in allowed for c in expression):
            return "Error: Only basic math operations allowed"
        
        result = eval(expression)
        return f"{expression} = {result}"
    except Exception as e:
        return f"Error: {str(e)}"

# Create calculator agent
agent = Agent(
    name="calculator",
    tools=[calculate]
)

response = agent.run("What's 25 + 17 * 3?")
print(response)`,
    output: `25 + 17 * 3 = 76`
  },
  {
    id: 'weather-info',
    title: '3. Weather Information Agent',
    description: 'Multiple tools working together with data lookup',
    icon: Database,
    color: 'text-cyan-400',
    difficulty: 'Beginner',
    code: `from connectonion import Agent

def get_weather(city: str) -> dict:
    """Get weather information for a city."""
    # Simulated weather data
    weather_db = {
        "new york": {"temp": 72, "condition": "sunny", "humidity": 45},
        "london": {"temp": 65, "condition": "cloudy", "humidity": 80},
        "tokyo": {"temp": 78, "condition": "partly cloudy", "humidity": 55}
    }
    
    city_lower = city.lower()
    if city_lower in weather_db:
        return weather_db[city_lower]
    return {"error": f"Weather data not available for {city}"}

def format_weather(weather_data: dict) -> str:
    """Format weather information nicely."""
    if "error" in weather_data:
        return weather_data["error"]
    
    return f"""Weather Report:
🌡️  Temperature: {weather_data['temp']}°F
☁️  Condition: {weather_data['condition']}
💧 Humidity: {weather_data['humidity']}%"""

# Create weather agent
agent = Agent(
    name="weather_bot",
    tools=[get_weather, format_weather]
)

response = agent.run("What's the weather like in Tokyo?")
print(response)`,
    output: `Weather Report:
🌡️  Temperature: 78°F
☁️  Condition: partly cloudy
💧 Humidity: 55%`
  },
  {
    id: 'task-manager',
    title: '4. Personal Task Manager',
    description: 'Stateful agent with data persistence and CRUD operations',
    icon: FileText,
    color: 'text-purple-400',
    difficulty: 'Intermediate',
    code: `from connectonion import Agent
from datetime import datetime

# Simple in-memory storage (use database in production)
tasks = []
task_counter = 1

def add_task(title: str, priority: str = "medium") -> str:
    """Add a new task to the list."""
    global task_counter
    task = {
        "id": task_counter,
        "title": title,
        "priority": priority,
        "completed": False,
        "created": datetime.now().strftime("%Y-%m-%d %H:%M")
    }
    tasks.append(task)
    task_counter += 1
    return f"✅ Added task #{task['id']}: '{title}' (Priority: {priority})"

def list_tasks(status: str = "all") -> str:
    """List tasks with optional filtering."""
    if not tasks:
        return "📝 No tasks found."
    
    filtered = tasks
    if status == "pending":
        filtered = [t for t in tasks if not t["completed"]]
    elif status == "completed":
        filtered = [t for t in tasks if t["completed"]]
    
    if not filtered:
        return f"📝 No {status} tasks found."
    
    result = f"📋 Tasks ({status}):\\n"
    for task in filtered:
        icon = "✅" if task["completed"] else "⭕"
        result += f"{icon} #{task['id']} {task['title']} [{task['priority']}]\\n"
    return result

def complete_task(task_id: int) -> str:
    """Mark a task as completed."""
    for task in tasks:
        if task["id"] == task_id:
            if task["completed"]:
                return f"Task #{task_id} is already completed!"
            task["completed"] = True
            return f"🎉 Completed task #{task_id}: '{task['title']}'"
    return f"❌ Task #{task_id} not found"

# Create task manager agent  
agent = Agent(
    name="task_manager",
    system_prompt="""You are a helpful personal task manager. Help users:
    1. Add and organize tasks with priorities
    2. Track task completion 
    3. Filter and view tasks by status
    4. Maintain a clean, organized task list
    Always confirm actions and provide clear updates.""",
    tools=[add_task, list_tasks, complete_task]
)

# Demo workflow
print("=== Task Manager Demo ===")
agent.run("Add a high priority task to review quarterly reports")
agent.run("Add a task to call dentist")  
agent.run("Add a low priority task to organize photos")
print("\\nAll tasks:", agent.run("Show me all my tasks"))
agent.run("Complete task 1")
print("\\nPending tasks:", agent.run("Show me pending tasks"))`,
    output: `=== Task Manager Demo ===

All tasks: 📋 Tasks (all):
⭕ #1 review quarterly reports [high]
⭕ #2 call dentist [medium]  
⭕ #3 organize photos [low]

Pending tasks: 📋 Tasks (pending):
⭕ #2 call dentist [medium]
⭕ #3 organize photos [low]`
  }
]

export default function ExamplesPage() {
  const [copiedId, setCopiedId] = useState<string | null>(null)
  const [activeExample, setActiveExample] = useState(examples[0].id)

  const copyToClipboard = (text: string, id: string) => {
    navigator.clipboard.writeText(text)
    setCopiedId(id)
    setTimeout(() => setCopiedId(null), 2000)
  }

  const currentExample = examples.find(ex => ex.id === activeExample) || examples[0]

  const markdownContent = `# ConnectOnion Examples

A comprehensive collection of real-world ConnectOnion agent implementations, from simple "Hello World" to complex business applications.

## Progressive Learning Path

These examples follow a carefully designed progression from basic concepts to advanced implementations:

### 🟢 Beginner Level
- **Hello World Agent**: Basic tool usage and agent creation
- **Calculator Agent**: Input validation and error handling
- **Weather Bot**: Multiple tools working together

### 🟡 Intermediate Level  
- **Task Manager**: Stateful operations and data persistence
- **Math Tutor**: Educational interactions and explanations
- **File Analyzer**: System integration and safety checks

### 🔴 Advanced Level
- **API Integration**: External service orchestration
- **E-commerce Manager**: Complex business logic workflows

Each example includes complete working code, realistic outputs, and progressive complexity to ensure smooth learning.

## Installation

\`\`\`bash
pip install connectonion==0.0.1
\`\`\`

## Example Categories

### Utility Agents
Simple, focused agents for everyday tasks

### Educational Agents  
Interactive learning and teaching assistants

### Business Agents
Enterprise-grade workflow automation

### Integration Agents
External service and API management

## Usage Tips

1. **Start Simple**: Begin with Hello World, then progress through each example
2. **Understand Concepts**: Each example introduces new concepts building on previous ones
3. **Modify and Experiment**: Use examples as starting points for your own agents
4. **Real-World Application**: Examples use realistic data and scenarios

## Next Steps

After working through these examples:
- Explore [System Prompts](/prompts) for personality customization
- Learn [Debugging with @xray](/xray) for development workflows
- Check the [Quick Start Guide](/quickstart) for hands-on tutorials

---

*All examples use ConnectOnion v0.0.1 and include complete, working code with realistic outputs.*`

  return (
    <div className="max-w-6xl mx-auto px-8 py-12 lg:py-12 pt-16 lg:pt-12">
      {/* Header */}
      <div className="flex items-start justify-between mb-12">
        <div className="flex-1">
          {/* Breadcrumb */}
          <nav className="flex items-center gap-2 text-sm text-gray-400 mb-4">
            <Link href="/" className="hover:text-white transition-colors">Home</Link>
            <ArrowRight className="w-4 h-4" />
            <span className="text-white">Examples</span>
          </nav>

          <h1 className="text-4xl font-bold text-white mb-4">Progressive Examples</h1>
          <p className="text-xl text-gray-300 max-w-3xl">
            Learn ConnectOnion through hands-on examples, from simple "Hello World" to complex business applications. 
            Each example builds on previous concepts with complete working code and realistic outputs.
          </p>
        </div>
        
        <CopyMarkdownButton 
          content={markdownContent}
          filename="connectonion-examples.md"
          className="ml-8 flex-shrink-0"
        />
      </div>

      {/* Learning Path Overview */}
      <div className="mb-16 p-8 bg-gradient-to-r from-blue-900/20 to-purple-900/20 border border-blue-500/30 rounded-xl">
        <h2 className="text-2xl font-bold text-white mb-6">📚 Learning Path</h2>
        <div className="grid md:grid-cols-3 gap-6">
          <div className="text-center">
            <div className="w-16 h-16 mx-auto mb-4 bg-green-600 rounded-full flex items-center justify-center">
              <span className="text-2xl font-bold text-white">🟢</span>
            </div>
            <h3 className="text-lg font-semibold text-white mb-2">Beginner</h3>
            <p className="text-green-200 text-sm">Start with basic concepts, single tools, simple interactions</p>
          </div>
          <div className="text-center">
            <div className="w-16 h-16 mx-auto mb-4 bg-yellow-600 rounded-full flex items-center justify-center">
              <span className="text-2xl font-bold text-white">🟡</span>
            </div>
            <h3 className="text-lg font-semibold text-white mb-2">Intermediate</h3>
            <p className="text-yellow-200 text-sm">Multiple tools, state management, system integration</p>
          </div>
          <div className="text-center">
            <div className="w-16 h-16 mx-auto mb-4 bg-red-600 rounded-full flex items-center justify-center">
              <span className="text-2xl font-bold text-white">🔴</span>
            </div>
            <h3 className="text-lg font-semibold text-white mb-2">Advanced</h3>
            <p className="text-red-200 text-sm">Complex workflows, business logic, enterprise features</p>
          </div>
        </div>
      </div>

      {/* Progressive Examples */}
      <div className="space-y-16">
        {examples.map((example, index) => (
          <div key={example.id} className="bg-gray-900/50 border border-gray-700 rounded-xl p-8">
            {/* Example Header */}
            <div className="flex items-center justify-between mb-8">
              <div className="flex items-center gap-4">
                <div className={`w-12 h-12 rounded-xl flex items-center justify-center text-white font-bold text-lg ${
                  example.difficulty === 'Beginner' ? 'bg-green-600' : 
                  example.difficulty === 'Intermediate' ? 'bg-yellow-600' : 'bg-red-600'
                }`}>
                  {index + 1}
                </div>
                <div>
                  <div className="flex items-center gap-3 mb-1">
                    <h3 className="text-2xl font-bold text-white">{example.title}</h3>
                    <span className={`px-3 py-1 rounded-full text-xs font-medium ${
                      example.difficulty === 'Beginner' ? 'bg-green-900/50 text-green-300' :
                      example.difficulty === 'Intermediate' ? 'bg-yellow-900/50 text-yellow-300' : 'bg-red-900/50 text-red-300'
                    }`}>
                      {example.difficulty}
                    </span>
                  </div>
                  <p className="text-gray-400">{example.description}</p>
                </div>
              </div>
              <button
                onClick={() => copyToClipboard(example.code, example.id)}
                className="text-gray-400 hover:text-white transition-colors p-2 rounded-lg hover:bg-gray-800 flex items-center gap-2"
              >
                {copiedId === example.id ? (
                  <>
                    <Check className="w-4 h-4 text-green-400" />
                    <span className="text-green-400 text-sm">Copied!</span>
                  </>
                ) : (
                  <>
                    <Copy className="w-4 h-4" />
                    <span className="text-sm">Copy Code</span>
                  </>
                )}
              </button>
            </div>

            <div className="grid lg:grid-cols-2 gap-8">
              {/* Code Panel */}
              <div className="bg-gray-900 border border-gray-700 rounded-lg">
                <div className="flex items-center gap-3 px-4 py-3 border-b border-gray-700 bg-gray-800">
                  <Play className="w-4 h-4 text-blue-400" />
                  <span className="text-sm font-medium text-gray-300">Python Code</span>
                </div>
                
                <div className="p-4 overflow-auto max-h-[500px]">
                  <SyntaxHighlighter 
                    language="python" 
                    style={vscDarkPlus}
                    customStyle={{
                      background: 'transparent',
                      padding: 0,
                      margin: 0,
                      fontSize: '0.8rem',
                      lineHeight: '1.4'
                    }}
                    showLineNumbers={true}
                    lineNumberStyle={{ 
                      color: '#6b7280', 
                      paddingRight: '1rem',
                      userSelect: 'none',
                      fontSize: '0.75rem'
                    }}
                  >
                    {example.code}
                  </SyntaxHighlighter>
                </div>
              </div>

              {/* Output Panel */}
              <div className="bg-gray-900 border border-gray-700 rounded-lg">
                <div className="flex items-center gap-3 px-4 py-3 border-b border-gray-700 bg-gray-800">
                  <Terminal className="w-4 h-4 text-green-400" />
                  <span className="text-sm font-medium text-gray-300">Expected Output</span>
                </div>
                
                <div className="p-4">
                  <div className="bg-black/70 rounded-lg p-4 font-mono text-sm overflow-auto max-h-[500px] border border-gray-600">
                    <pre className="text-green-200 whitespace-pre-line">
                      {example.output}
                    </pre>
                  </div>
                </div>
              </div>
            </div>

            {/* Progress Indicator */}
            {index < examples.length - 1 && (
              <div className="flex justify-center mt-8">
                <div className="flex items-center gap-2 text-gray-500">
                  <div className="w-2 h-2 bg-gray-600 rounded-full"></div>
                  <div className="w-2 h-2 bg-gray-600 rounded-full"></div>
                  <div className="w-2 h-2 bg-gray-600 rounded-full"></div>
                  <ArrowRight className="w-4 h-4" />
                </div>
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Next Steps */}
      <div className="mt-16 p-8 bg-gradient-to-r from-purple-900/20 to-pink-900/20 border border-purple-500/30 rounded-xl">
        <h2 className="text-2xl font-bold text-white mb-6">🎯 What's Next?</h2>
        <p className="text-gray-300 mb-6">
          Ready to take your ConnectOnion skills to the next level? Here are some great next steps:
        </p>
        <div className="grid md:grid-cols-2 gap-6">
          <Link 
            href="/prompts" 
            className="group bg-purple-900/20 border border-purple-500/30 rounded-lg p-6 hover:border-purple-400/50 transition-all"
          >
            <div className="flex items-center gap-3 mb-3">
              <FileText className="w-6 h-6 text-purple-400" />
              <h3 className="text-lg font-semibold text-white">System Prompts</h3>
              <ArrowRight className="w-4 h-4 text-purple-400 group-hover:translate-x-1 transition-transform" />
            </div>
            <p className="text-purple-100 text-sm">
              Learn to craft perfect agent personalities and behaviors with advanced prompting techniques.
            </p>
          </Link>

          <Link 
            href="/xray" 
            className="group bg-blue-900/20 border border-blue-500/30 rounded-lg p-6 hover:border-blue-400/50 transition-all"
          >
            <div className="flex items-center gap-3 mb-3">
              <Zap className="w-6 h-6 text-blue-400" />
              <h3 className="text-lg font-semibold text-white">@xray Debugging</h3>
              <ArrowRight className="w-4 h-4 text-blue-400 group-hover:translate-x-1 transition-transform" />
            </div>
            <p className="text-blue-100 text-sm">
              Master debugging techniques and get complete visibility into your agent's decision-making process.
            </p>
          </Link>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex justify-between items-center pt-8 border-t border-gray-800 mt-16">
        <Link 
          href="/xray/trace" 
          className="flex items-center gap-2 text-gray-400 hover:text-white transition-colors"
        >
          <ArrowRight className="w-4 h-4 rotate-180" />
          trace() Visual Flow
        </Link>
        <Link 
          href="/quickstart" 
          className="flex items-center gap-2 text-gray-400 hover:text-white transition-colors"
        >
          Quick Start Guide
          <ArrowRight className="w-4 h-4" />
        </Link>
      </nav>
    </div>
  )
}