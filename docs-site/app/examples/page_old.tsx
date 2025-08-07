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

def calculate(expression: str) -> str:
    """Safely evaluate mathematical expressions and show work."""
    try:
        # Validate safe characters
        allowed = set('0123456789+-*/()., ')
        if not all(c in allowed for c in expression):
            return "Error: Only basic math operations allowed"
        
        result = eval(expression)
        return f"Calculation: {expression} = {result}"
    except Exception as e:
        return f"Math Error: {str(e)}"

def get_math_help(topic: str) -> str:
    """Provide help with math concepts."""
    help_topics = {
        "percentage": "To calculate a percentage: (part/whole) × 100",
        "fractions": "To add fractions: find common denominator, then add numerators",
        "algebra": "Solve for x by isolating the variable on one side",
        "geometry": "Area of rectangle = length × width, Circle area = π × r²"
    }
    return help_topics.get(topic.lower(), f"I don't have help for '{topic}' yet. Try: percentage, fractions, algebra, geometry")

# Create the agent
agent = Agent(
    name="math_tutor",
    system_prompt="""You are a helpful math tutor. Always:
    1. Show your work step by step
    2. Explain the reasoning behind each step
    3. Provide encouragement
    4. Offer to help with related concepts""",
    tools=[calculate, get_math_help]
)

# Test the agent
print("=== Math Tutor Agent ===")
response = agent.run("I need to calculate 15% of 240, can you help me understand this?")
print(response)`,
    output: `=== Math Tutor Agent ===

I'd be happy to help you understand how to calculate 15% of 240!

Let me break this down step by step:

First, let me calculate it for you:
Calculation: 240 * 0.15 = 36.0

Now let me explain how percentages work:
To calculate a percentage: (part/whole) × 100

For your problem:
1. 15% means 15 out of 100, or 15/100 = 0.15
2. To find 15% OF something, multiply by 0.15
3. So: 240 × 0.15 = 36

The answer is 36!

This is really useful for things like calculating tips, discounts, or tax. Would you like me to help you practice with more percentage problems?`
  },
  {
    id: 'file-analyzer',
    title: 'File Analysis Agent',
    description: 'Analyzes files and provides detailed insights',
    icon: FileText,
    color: 'text-green-400',
    code: `from connectonion import Agent
import os
from pathlib import Path

def analyze_file(filepath: str) -> str:
    """Analyze a file and return detailed information."""
    try:
        path = Path(filepath)
        if not path.exists():
            return f"File not found: {filepath}"
        
        # Get file stats
        stat = path.stat()
        size = stat.st_size
        
        # Determine file type
        suffix = path.suffix.lower()
        file_types = {
            '.py': 'Python source code',
            '.js': 'JavaScript source code',
            '.md': 'Markdown documentation',
            '.txt': 'Plain text file',
            '.json': 'JSON data file',
            '.csv': 'CSV data file'
        }
        
        file_type = file_types.get(suffix, f'File with {suffix} extension')
        
        # Read content preview (first 200 chars for text files)
        preview = ""
        if suffix in ['.py', '.js', '.md', '.txt', '.json']:
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    content = f.read(200)
                    preview = f"Preview: {content[:200]}{'...' if len(content) == 200 else ''}"
            except:
                preview = "Cannot preview: binary or encoding issue"
        
        return f"""File Analysis: {path.name}
Type: {file_type}
Size: {size} bytes
Full path: {path.absolute()}
{preview}"""
        
    except Exception as e:
        return f"Analysis error: {str(e)}"

def search_files(directory: str, pattern: str) -> str:
    """Search for files matching a pattern in directory."""
    try:
        path = Path(directory)
        if not path.exists():
            return f"Directory not found: {directory}"
        
        matches = list(path.glob(pattern))[:10]  # Limit to 10 results
        
        if not matches:
            return f"No files matching '{pattern}' found in {directory}"
        
        result = f"Found {len(matches)} files matching '{pattern}' in {directory}:\\n"
        for match in matches:
            result += f"- {match.name} ({match.stat().st_size} bytes)\\n"
            
        return result
        
    except Exception as e:
        return f"Search error: {str(e)}"

# Create file analysis agent
agent = Agent(
    name="file_analyst",
    system_prompt="""You are a helpful file analysis assistant. You can:
    1. Analyze individual files and provide detailed information
    2. Search for files in directories
    3. Explain file types and suggest actions
    
    Always be thorough but concise in your analysis.""",
    tools=[analyze_file, search_files]
)

# Test the agent
print("=== File Analysis Agent ===")
response = agent.run("Can you analyze the file 'example.py' and then search for all Python files in the current directory?")
print(response)`,
    output: `=== File Analysis Agent ===

I'll help you analyze the file and search for Python files!

Let me start by analyzing 'example.py':

File Analysis: example.py
Type: Python source code
Size: 1247 bytes
Full path: /Users/demo/example.py
Preview: from connectonion import Agent

def calculate(expression: str) -> str:
    """Safely evaluate mathematical expressions."""
    try:
        allowed_chars = set('0123456789+-*/()., ')
        if all(c in allowed_chars...

Now let me search for all Python files in the current directory:

Found 5 files matching '*.py' in .:
- example.py (1247 bytes)
- agent_demo.py (892 bytes)
- test_tools.py (2341 bytes)
- main.py (456 bytes)
- utils.py (1089 bytes)

The analyzed file 'example.py' is a Python source file containing what looks like ConnectOnion agent code with a calculator function. I found 5 Python files total in your current directory. Would you like me to analyze any of the other Python files in more detail?`
  },
  {
    id: 'api-client',
    title: 'API Client Agent',
    description: 'Makes HTTP requests and processes API responses',
    icon: Database,
    color: 'text-purple-400',
    code: `from connectonion import Agent
import requests
import json

def fetch_weather(city: str) -> str:
    """Fetch weather information for a city (demo with mock data)."""
    # In real use, you'd use: requests.get(f"https://api.weather.com/v1/current?city={city}")
    # For demo, we'll simulate the response
    mock_data = {
        "New York": {"temp": 72, "condition": "sunny", "humidity": 45},
        "London": {"temp": 63, "condition": "cloudy", "humidity": 78},
        "Tokyo": {"temp": 75, "condition": "rainy", "humidity": 82}
    }
    
    city_key = next((k for k in mock_data.keys() if k.lower() in city.lower()), None)
    
    if city_key:
        data = mock_data[city_key]
        return f"""Weather in {city_key}:
Temperature: {data['temp']}°F
Condition: {data['condition']}
Humidity: {data['humidity']}%"""
    else:
        return f"Weather data not available for {city}"

def fetch_user_info(user_id: str) -> str:
    """Fetch user information (demo with mock data)."""
    # Simulated API response
    mock_users = {
        "123": {"name": "Alice Johnson", "email": "alice@example.com", "role": "Developer"},
        "456": {"name": "Bob Smith", "email": "bob@example.com", "role": "Designer"},
        "789": {"name": "Carol Davis", "email": "carol@example.com", "role": "Manager"}
    }
    
    if user_id in mock_users:
        user = mock_users[user_id]
        return f"""User Information:
ID: {user_id}
Name: {user['name']}
Email: {user['email']}
Role: {user['role']}"""
    else:
        return f"User ID {user_id} not found"

def post_data(data: str) -> str:
    """Send data to API endpoint (simulated)."""
    # In real use: requests.post("https://api.example.com/data", json=data)
    return f"Successfully posted data: {data[:100]}{'...' if len(data) > 100 else ''}"

# Create API client agent
agent = Agent(
    name="api_client",
    system_prompt="""You are an API client assistant. You can:
    1. Fetch weather information for cities
    2. Retrieve user information by ID
    3. Post data to API endpoints
    
    Always format responses clearly and handle errors gracefully.""",
    tools=[fetch_weather, fetch_user_info, post_data]
)

# Test the agent
print("=== API Client Agent ===")
response = agent.run("Get the weather for New York and user info for ID 123")
print(response)`,
    output: `=== API Client Agent ===

I'll fetch both the weather information for New York and the user information for ID 123.

Let me get the weather for New York first:

Weather in New York:
Temperature: 72°F
Condition: sunny
Humidity: 45%

Now let me retrieve the user information for ID 123:

User Information:
ID: 123
Name: Alice Johnson
Email: alice@example.com
Role: Developer

Perfect! New York is having great weather today - sunny and 72°F with comfortable humidity at 45%. And I found user 123 is Alice Johnson, a Developer at alice@example.com. Is there anything specific you'd like to know about either the weather or user data?`
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

Complete examples showing real-world agent implementations with actual outputs.

${examples.map(example => `
## ${example.title}

${example.description}

\`\`\`python
${example.code}
\`\`\`

**Output:**
\`\`\`
${example.output}
\`\`\`
`).join('\n')}
`

  return (
    <div className="max-w-7xl mx-auto px-8 py-12 lg:py-12 pt-16 lg:pt-12">
      {/* Header with Copy Button */}
      <div className="flex items-start justify-between mb-8">
        <div className="flex-1">
          {/* Breadcrumb */}
          <nav className="flex items-center gap-2 text-sm text-gray-400 mb-4">
            <Link href="/" className="hover:text-white transition-colors">Home</Link>
            <ArrowRight className="w-4 h-4" />
            <span className="text-white">Examples</span>
          </nav>

          <h1 className="text-4xl font-bold text-white mb-4">Complete Examples</h1>
          <p className="text-xl text-gray-300 max-w-3xl">
            Real-world ConnectOnion agent implementations with actual outputs. 
            Copy, run, and modify these examples to learn how agents work in practice.
          </p>
        </div>
        
        <CopyMarkdownButton 
          content={markdownContent}
          filename="connectonion-examples.md"
          className="ml-8 flex-shrink-0"
        />
      </div>

      {/* Time Estimate */}
      <div className="flex items-center gap-2 mb-12 p-4 bg-green-900/20 border border-green-500/30 rounded-lg">
        <Clock className="w-5 h-5 text-green-400" />
        <span className="text-green-200">
          <strong>Ready to run:</strong> Each example is complete and executable
        </span>
      </div>

      {/* Example Selector */}
      <div className="flex flex-wrap gap-4 mb-8">
        {examples.map((example) => {
          const IconComponent = example.icon
          const isActive = activeExample === example.id
          return (
            <button
              key={example.id}
              onClick={() => setActiveExample(example.id)}
              className={`px-6 py-3 rounded-lg font-medium flex items-center gap-3 border transition-all ${
                isActive
                  ? 'bg-gray-800 border-gray-500 text-white' 
                  : 'bg-gray-900 border-gray-600 hover:bg-gray-800 text-gray-300'
              }`}
            >
              <IconComponent className={`w-5 h-5 ${isActive ? currentExample.color : 'text-gray-400'}`} />
              {example.title}
            </button>
          )
        })}
      </div>

      <div className="grid lg:grid-cols-2 gap-8">
        {/* Code Panel */}
        <div className="space-y-6">
          <div className="bg-gray-900 border border-gray-700 rounded-lg">
            <div className="flex items-center justify-between px-6 py-4 border-b border-gray-700">
              <div className="flex items-center gap-3">
                {React.createElement(currentExample.icon, { 
                  className: `w-5 h-5 ${currentExample.color}` 
                })}
                <span className="text-lg font-semibold text-white">
                  {currentExample.title}
                </span>
              </div>
              <button
                onClick={() => copyToClipboard(currentExample.code, currentExample.id)}
                className="text-gray-400 hover:text-white transition-colors p-2 rounded-lg hover:bg-gray-800"
              >
                {copiedId === currentExample.id ? (
                  <Check className="w-5 h-5 text-green-400" />
                ) : (
                  <Copy className="w-5 h-5" />
                )}
              </button>
            </div>
            
            <div className="p-6 overflow-auto max-h-[600px]">
              <SyntaxHighlighter 
                language="python" 
                style={vscDarkPlus}
                customStyle={{
                  background: 'transparent',
                  padding: 0,
                  margin: 0,
                  fontSize: '0.875rem',
                  lineHeight: '1.5'
                }}
                showLineNumbers={true}
                lineNumberStyle={{ 
                  color: '#6b7280', 
                  paddingRight: '1rem',
                  userSelect: 'none'
                }}
              >
                {currentExample.code}
              </SyntaxHighlighter>
            </div>
          </div>

          {/* Run Instructions */}
          <div className="bg-blue-900/20 border border-blue-500/30 rounded-lg p-4">
            <div className="flex items-center gap-3 mb-3">
              <Play className="w-5 h-5 text-blue-400" />
              <span className="font-semibold text-blue-300">How to run:</span>
            </div>
            <div className="text-blue-200 text-sm space-y-2">
              <div>1. Save the code as <code className="bg-black/30 px-1 rounded">{currentExample.id}.py</code></div>
              <div>2. Run: <code className="bg-black/30 px-2 py-1 rounded">python {currentExample.id}.py</code></div>
              <div>3. Set <code className="bg-black/30 px-1 rounded">OPENAI_API_KEY</code> environment variable</div>
            </div>
          </div>
        </div>

        {/* Output Panel */}
        <div className="space-y-6">
          <div className="bg-gray-900 border border-gray-700 rounded-lg">
            <div className="flex items-center gap-3 px-6 py-4 border-b border-gray-700">
              <Terminal className="w-5 h-5 text-green-400" />
              <span className="text-lg font-semibold text-white">Example Output</span>
              <div className="flex items-center gap-1 ml-auto">
                <div className="w-2 h-2 bg-green-400 rounded-full animate-pulse"></div>
                <span className="text-xs text-green-400">live example</span>
              </div>
            </div>
            
            <div className="p-6">
              <div className="bg-black/50 rounded-lg p-4 font-mono text-sm text-green-200 whitespace-pre-line overflow-auto max-h-[600px]">
                {currentExample.output}
              </div>
            </div>
          </div>

          {/* Example Details */}
          <div className="bg-gray-900 border border-gray-700 rounded-lg p-6">
            <h4 className="font-semibold text-white mb-3">About This Example</h4>
            <p className="text-gray-300 text-sm mb-4">{currentExample.description}</p>
            
            <div className="space-y-2 text-sm">
              <div className="text-gray-400">
                <strong>Key Features:</strong>
              </div>
              {currentExample.id === 'calculator' && (
                <ul className="list-disc list-inside text-gray-300 space-y-1">
                  <li>Multiple tool functions</li>
                  <li>Error handling and validation</li>
                  <li>Educational system prompt</li>
                  <li>Step-by-step explanations</li>
                </ul>
              )}
              {currentExample.id === 'file-analyzer' && (
                <ul className="list-disc list-inside text-gray-300 space-y-1">
                  <li>File system interaction</li>
                  <li>Pattern matching and search</li>
                  <li>Content preview generation</li>
                  <li>Error handling for missing files</li>
                </ul>
              )}
              {currentExample.id === 'api-client' && (
                <ul className="list-disc list-inside text-gray-300 space-y-1">
                  <li>Simulated API interactions</li>
                  <li>Multiple data sources</li>
                  <li>Structured response formatting</li>
                  <li>Mock data for demonstrations</li>
                </ul>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex justify-between items-center pt-12 mt-12 border-t border-gray-800">
        <Link 
          href="/prompts/examples" 
          className="flex items-center gap-2 text-gray-400 hover:text-white transition-colors"
        >
          <ArrowRight className="w-4 h-4 rotate-180" />
          Prompt Examples
        </Link>
        <Link 
          href="/xray" 
          className="flex items-center gap-2 text-gray-400 hover:text-white transition-colors"
        >
          @xray Debugging
          <ArrowRight className="w-4 h-4" />
        </Link>
      </nav>
    </div>
  )
}