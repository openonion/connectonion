/*
  NAVIGATION INCONSISTENCY FOUND (2025-01-02):
  - Custom navigation with "Previous/Next in series" labels
  - No consistent breadcrumb navigation
  - Different from PageNavigation component
  - Being updated to use UnifiedNavigation
*/

'use client'

import React, { useState } from 'react'
import { Copy, Check, Database, ArrowRight, ArrowLeft, Download, Play, Terminal, Lightbulb, Cloud, MapPin } from 'lucide-react'
import { ContentNavigation } from '../../../components/ContentNavigation'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { okaidia as monokai } from 'react-syntax-highlighter/dist/esm/styles/prism'
import Link from 'next/link'
import { CopyMarkdownButton } from '../../../components/CopyMarkdownButton'

const agentCode = `from connectonion import Agent

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
    tools=[get_weather, format_weather],
    max_iterations=5  # Weather queries are simple
)

response = agent.input("What's the weather like in Tokyo?")
print(response)`

const expectedOutput = `Weather Report:
🌡️  Temperature: 78°F
☁️  Condition: partly cloudy
💧 Humidity: 55%`

const fullExampleCode = `# weather_bot.py
import os
from connectonion import Agent
from typing import Dict, Any

# Set your OpenAI API key
os.environ['OPENAI_API_KEY'] = 'your-api-key-here'

def get_weather(city: str) -> Dict[str, Any]:
    """Get current weather information for a specific city."""
    # In a real application, you'd use a weather API like OpenWeatherMap
    # For this demo, we use simulated data
    weather_database = {
        "new york": {
            "temp": 72, "condition": "sunny", "humidity": 45, 
            "wind": "5 mph", "pressure": "30.1 inHg"
        },
        "london": {
            "temp": 65, "condition": "cloudy", "humidity": 80,
            "wind": "12 mph", "pressure": "29.8 inHg"
        },
        "tokyo": {
            "temp": 78, "condition": "partly cloudy", "humidity": 55,
            "wind": "8 mph", "pressure": "30.0 inHg"
        },
        "paris": {
            "temp": 68, "condition": "rainy", "humidity": 85,
            "wind": "15 mph", "pressure": "29.7 inHg"
        },
        "sydney": {
            "temp": 82, "condition": "sunny", "humidity": 40,
            "wind": "10 mph", "pressure": "30.2 inHg"
        }
    }
    
    city_key = city.lower().strip()
    if city_key in weather_database:
        return weather_database[city_key]
    
    return {"error": f"Weather data not available for {city}. Available cities: {', '.join(weather_database.keys()).title()}"}

def format_weather_report(weather_data: Dict[str, Any]) -> str:
    """Format weather data into a nice readable report."""
    if "error" in weather_data:
        return f"❌ {weather_data['error']}"
    
    # Create a formatted weather report
    report = f"""🌤️ Weather Report
    
🌡️  Temperature: {weather_data['temp']}°F
☁️  Condition: {weather_data['condition'].title()}
💧 Humidity: {weather_data['humidity']}%
💨 Wind: {weather_data['wind']}
🌀 Pressure: {weather_data['pressure']}"""
    
    return report

def get_available_cities() -> str:
    """Get list of cities with available weather data."""
    cities = ["New York", "London", "Tokyo", "Paris", "Sydney"]
    return f"🌍 Available cities: {', '.join(cities)}"

def compare_weather(city1: str, city2: str) -> str:
    """Compare weather between two cities."""
    weather1 = get_weather(city1)
    weather2 = get_weather(city2)
    
    if "error" in weather1:
        return f"❌ Could not get weather for {city1}: {weather1['error']}"
    if "error" in weather2:
        return f"❌ Could not get weather for {city2}: {weather2['error']}"
    
    temp_diff = weather1['temp'] - weather2['temp']
    humidity_diff = weather1['humidity'] - weather2['humidity']
    
    comparison = f"""🔄 Weather Comparison: {city1.title()} vs {city2.title()}

🌡️ Temperature:
   • {city1.title()}: {weather1['temp']}°F
   • {city2.title()}: {weather2['temp']}°F
   • Difference: {abs(temp_diff)}°F {'warmer' if temp_diff > 0 else 'cooler'} in {city1.title() if temp_diff > 0 else city2.title()}

☁️ Conditions:
   • {city1.title()}: {weather1['condition'].title()}
   • {city2.title()}: {weather2['condition'].title()}

💧 Humidity:
   • {city1.title()}: {weather1['humidity']}%
   • {city2.title()}: {weather2['humidity']}%
   • Difference: {abs(humidity_diff)}% {'more humid' if humidity_diff > 0 else 'less humid'} in {city1.title() if humidity_diff > 0 else city2.title()}"""
    
    return comparison

# Create the weather bot agent
agent = Agent(
    name="weather_bot",
    system_prompt="""You are a helpful weather assistant. You can:
    1. Get weather information for specific cities
    2. Format weather reports in a nice, readable way
    3. Compare weather between two cities
    4. Show available cities
    
    Always be friendly and provide useful weather information!""",
    tools=[get_weather, format_weather_report, get_available_cities, compare_weather]
)

if __name__ == "__main__":
    print("=== Weather Bot Demo ===\\n")
    
    # Test various weather queries
    test_queries = [
        "What's the weather like in Tokyo?",
        "Show me available cities",
        "Compare the weather in New York and London",
        "What's the weather in Miami?",  # This will show error handling
        "Get weather for Paris"
    ]
    
    for i, query in enumerate(test_queries, 1):
        print(f"Query {i}: {query}")
        response = agent.input(query)
        print(f"Response: {response}\\n")
        print("-" * 60)`

export default function WeatherBotPage() {
  const [copiedId, setCopiedId] = useState<string | null>(null)

  const copyToClipboard = (text: string, id: string) => {
    navigator.clipboard.writeText(text)
    setCopiedId(id)
    setTimeout(() => setCopiedId(null), 2000)
  }

  const markdownContent = `# Weather Bot Agent - ConnectOnion Tutorial

Learn data processing, tool coordination, and structured output by building a weather information agent.

## What You'll Learn

- Working with structured data and dictionaries
- Tool coordination and data flow between functions
- Output formatting and presentation
- Error handling for data that doesn't exist

## Key Features

- 🌍 Multi-city weather database simulation
- 📊 Structured data processing
- 🎨 Formatted output generation  
- 🔄 Tool coordination patterns
- ❌ Graceful error handling

## Complete Example

\`\`\`python
${fullExampleCode}
\`\`\`

## Key Concepts

This example demonstrates:
- **Data Flow**: How tools pass data between each other
- **Structured Output**: Converting raw data into formatted reports  
- **Tool Coordination**: Agent decides which tools to use and in what order
- **Error Handling**: Graceful handling of missing data

Perfect foundation for building data-driven agents!`

  return (
    <div className="max-w-6xl mx-auto px-4 md:px-8 py-8 md:py-12 lg:py-12 pt-16 lg:pt-12">
      {/* Navigation */}

      {/* Header */}
      <div className="flex items-start justify-between mb-12">
        <div className="flex-1">
          <div className="flex items-center gap-4 mb-4">
            <div className="w-16 h-16 bg-cyan-600 rounded-xl flex items-center justify-center">
              <span className="text-2xl font-bold text-white">3</span>
              
</div>
            <div>
              <div className="flex items-center gap-3 mb-2">
                <Database className="w-8 h-8 text-cyan-400" />
                <h1 className="text-4xl font-bold text-white">Weather Bot Agent</h1>
                <span className="px-3 py-1 bg-cyan-900/50 text-cyan-300 rounded-full text-sm font-medium">
                  Beginner
                </span>
                
</div>
              <p className="text-xl text-gray-300">
                Learn data processing, tool coordination, and structured output formatting with a weather information bot.
              </p>
              
</div>
            
</div>
          
</div>
        
        <CopyMarkdownButton 
          content={markdownContent}
          filename="weather-bot-agent.md"
          className="ml-8 flex-shrink-0"
        />
        
</div>

      {/* Key Concepts */}
      <div className="mb-12 p-6 bg-cyan-900/20 border border-cyan-500/30 rounded-xl">
        <h2 className="text-xl font-bold text-white mb-4 flex items-center gap-3">
          <Lightbulb className="w-6 h-6 text-cyan-400" />
          What You'll Learn
        </h2>
        <div className="grid md:grid-cols-4 gap-6">
          <div className="text-center">
            <div className="w-12 h-12 mx-auto mb-3 bg-cyan-600 rounded-lg flex items-center justify-center">
              <Database className="w-6 h-6 text-white" />
              
</div>
            <h3 className="text-white font-semibold mb-1">Data Processing</h3>
            <p className="text-cyan-200 text-sm">Handle structured data and dictionaries</p>
            
</div>
          <div className="text-center">
            <div className="w-12 h-12 mx-auto mb-3 bg-cyan-600 rounded-lg flex items-center justify-center">
              <Play className="w-6 h-6 text-white" />
              
</div>
            <h3 className="text-white font-semibold mb-1">Tool Coordination</h3>
            <p className="text-cyan-200 text-sm">Multiple tools working together</p>
            
</div>
          <div className="text-center">
            <div className="w-12 h-12 mx-auto mb-3 bg-cyan-600 rounded-lg flex items-center justify-center">
              <Cloud className="w-6 h-6 text-white" />
              
</div>
            <h3 className="text-white font-semibold mb-1">Output Formatting</h3>
            <p className="text-cyan-200 text-sm">Convert data into readable reports</p>
            
</div>
          <div className="text-center">
            <div className="w-12 h-12 mx-auto mb-3 bg-cyan-600 rounded-lg flex items-center justify-center">
              <MapPin className="w-6 h-6 text-white" />
              
</div>
            <h3 className="text-white font-semibold mb-1">Error Handling</h3>
            <p className="text-cyan-200 text-sm">Graceful handling of missing data</p>
            
</div>
          
</div>
        
</div>

      <div className="grid lg:grid-cols-2 gap-12">
        {/* Code Examples */}
        <div className="space-y-8">
          {/* Basic Example */}
          <div className="bg-gray-900 border border-gray-700 rounded-lg">
            <div className="flex items-center justify-between px-6 py-4 border-b border-gray-700">
              <h3 className="text-xl font-semibold text-white">Basic Weather Bot</h3>
              <button
                onClick={() => copyToClipboard(agentCode, 'basic')}
                className="text-gray-400 hover:text-white transition-colors p-2 rounded-lg hover:bg-gray-800 flex items-center gap-2"
              >
                {copiedId === 'basic' ? (
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
                style={monokai}
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
                {agentCode}
              </SyntaxHighlighter>
              
</div>
            
</div>

          {/* Complete Example */}
          <div className="bg-gray-900 border border-gray-700 rounded-lg">
            <div className="flex items-center justify-between px-6 py-4 border-b border-gray-700">
              <h3 className="text-xl font-semibold text-white">Complete Weather Bot</h3>
              <button
                onClick={() => copyToClipboard(fullExampleCode, 'complete')}
                className="text-gray-400 hover:text-white transition-colors p-2 rounded-lg hover:bg-gray-800 flex items-center gap-2"
              >
                {copiedId === 'complete' ? (
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
            
            <div className="p-6 ">
              <SyntaxHighlighter 
                language="python" 
                style={monokai}
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
                {fullExampleCode}
              </SyntaxHighlighter>
              
</div>
            
</div>
          
</div>

        {/* Right Panel */}
        <div className="space-y-8">
          {/* Output */}
          <div className="bg-gray-900 border border-gray-700 rounded-lg">
            <div className="flex items-center gap-3 px-6 py-4 border-b border-gray-700">
              <Terminal className="w-5 h-5 text-cyan-400" />
              <h3 className="text-xl font-semibold text-white">Expected Output</h3>
              
</div>
            
            <div className="p-6">
              <div className="bg-black/50 rounded-lg p-4 font-mono text-sm">
                <pre className="text-cyan-200 whitespace-pre-wrap">
                  {`=== Weather Bot Demo ===

Query 1: What's the weather like in Tokyo?
Response: 🌤️ Weather Report
    
🌡️  Temperature: 78°F
☁️  Condition: Partly Cloudy
💧 Humidity: 55%
💨 Wind: 8 mph
🌀 Pressure: 30.0 inHg

Query 2: Compare the weather in New York and London
Response: 🔄 Weather Comparison: New York vs London

🌡️ Temperature:
   • New York: 72°F
   • London: 65°F
   • Difference: 7°F warmer in New York

☁️ Conditions:
   • New York: Sunny
   • London: Cloudy`}
                </pre>
                
</div>
              
</div>
            
</div>

          {/* Data Flow */}
          <div className="bg-gray-900 border border-gray-700 rounded-lg p-6">
            <h3 className="text-xl font-semibold text-white mb-4">Tool Coordination</h3>
            <div className="space-y-4 text-sm">
              <div>
                <h4 className="font-semibold text-cyan-400 mb-2">🔄 Data Flow</h4>
                <p className="text-gray-300">get_weather() → format_weather_report() creates a seamless data pipeline.</p>
                
</div>
              <div>
                <h4 className="font-semibold text-cyan-400 mb-2">🎯 Smart Selection</h4>
                <p className="text-gray-300">Agent automatically chooses which tools to use based on user questions.</p>
                
</div>
              <div>
                <h4 className="font-semibold text-cyan-400 mb-2">📊 Structured Output</h4>
                <p className="text-gray-300">Raw data gets transformed into beautiful, readable weather reports.</p>
                
</div>
              
</div>
            
</div>

          {/* Features */}
          <div className="bg-gray-900 border border-gray-700 rounded-lg p-6">
            <h3 className="text-lg font-semibold text-white mb-4">Advanced Features</h3>
            <div className="space-y-3 text-sm">
              <div className="p-3 bg-cyan-900/20 border border-cyan-500/30 rounded">
                <p className="text-cyan-300 font-medium mb-1">🌍 Multi-City Support</p>
                <p className="text-cyan-200">New York, London, Tokyo, Paris, Sydney weather data available</p>
                
</div>
              <div className="p-3 bg-cyan-900/20 border border-cyan-500/30 rounded">
                <p className="text-cyan-300 font-medium mb-1">🔄 Weather Comparison</p>
                <p className="text-cyan-200">Side-by-side comparison between any two cities</p>
                
</div>
              <div className="p-3 bg-cyan-900/20 border border-cyan-500/30 rounded">
                <p className="text-cyan-300 font-medium mb-1">❌ Error Handling</p>
                <p className="text-cyan-200">Graceful handling of cities not in database</p>
                
</div>
              
</div>
            
</div>

          {/* Download */}
          <div className="bg-gray-900 border border-gray-700 rounded-lg p-6">
            <h3 className="text-lg font-semibold text-white mb-4">Try It Yourself</h3>
            <div className="space-y-3">
              <a
                href={`data:text/plain;charset=utf-8,${encodeURIComponent(fullExampleCode)}`}
                download="weather_bot.py"
                className="w-full flex items-center justify-center gap-2 px-4 py-3 bg-cyan-600 hover:bg-cyan-700 rounded-lg text-white transition-colors font-medium"
              >
                <Download className="w-4 h-4" />
                Download Complete Example
              </a>
              <p className="text-xs text-gray-400 text-center">
                Ready-to-run weather bot with multiple cities and comparison features
              </p>
              
</div>
            
</div>
          
</div>
      </div>

      {/* Navigation */}
      <ContentNavigation />
    </div>
  )
}
