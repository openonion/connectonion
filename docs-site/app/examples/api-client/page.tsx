'use client'

import React, { useState } from 'react'
import { Copy, Check, Database, ArrowRight, ArrowLeft, Download, Play, Terminal, Lightbulb, Globe, Zap, Lock } from 'lucide-react'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { okaidia as monokai } from 'react-syntax-highlighter/dist/esm/styles/prism'
import Link from 'next/link'
import { CopyMarkdownButton } from '../../../components/CopyMarkdownButton'

const agentCode = `from connectonion import Agent
import requests
import json

def fetch_weather(city: str) -> str:
    """Fetch weather information for a city (demo with mock data)."""
    # In real use: requests.get(f"https://api.weather.com/v1/current?city={city}")
    mock_data = {
        "New York": {"temp": 72, "condition": "sunny", "humidity": 45},
        "London": {"temp": 63, "condition": "cloudy", "humidity": 78},
        "Tokyo": {"temp": 75, "condition": "rainy", "humidity": 82}
    }
    
    city_key = next((k for k in mock_data.keys() if k.lower() in city.lower()), None)
    if city_key:
        data = mock_data[city_key]
        return f"Weather in {city_key}: {data['temp']}°F, {data['condition']}"
    return f"Weather data not available for {city}"

def fetch_user_info(user_id: str) -> str:
    """Fetch user information (demo with mock data)."""
    mock_users = {
        "123": {"name": "Alice Johnson", "email": "alice@example.com"},
        "456": {"name": "Bob Smith", "email": "bob@example.com"}
    }
    
    if user_id in mock_users:
        user = mock_users[user_id]
        return f"User {user_id}: {user['name']} ({user['email']})"
    return f"User ID {user_id} not found"

# Create API client agent
agent = Agent(
    name="api_client",
    tools=[fetch_weather, fetch_user_info]
)`

const fullExampleCode = `# api_client_agent.py
import os
import requests
import json
from typing import Dict, Any, Optional
from connectonion import Agent
from datetime import datetime

# Set your OpenAI API key
os.environ['OPENAI_API_KEY'] = 'your-api-key-here'

def make_api_request(url: str, method: str = "GET", headers: Optional[Dict] = None, data: Optional[Dict] = None) -> str:
    """Make HTTP requests to external APIs with proper error handling."""
    try:
        # Default headers
        default_headers = {
            "User-Agent": "ConnectOnion-Agent/1.0",
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
        
        if headers:
            default_headers.update(headers)
        
        # Make the request
        if method.upper() == "GET":
            response = requests.get(url, headers=default_headers, timeout=10)
        elif method.upper() == "POST":
            response = requests.post(url, headers=default_headers, json=data, timeout=10)
        elif method.upper() == "PUT":
            response = requests.put(url, headers=default_headers, json=data, timeout=10)
        elif method.upper() == "DELETE":
            response = requests.delete(url, headers=default_headers, timeout=10)
        else:
            return f"❌ Unsupported HTTP method: {method}"
        
        # Check response status
        if response.status_code == 200:
            return f"✅ **Success** ({response.status_code})\\n\\n{response.text[:1000]}{'...' if len(response.text) > 1000 else ''}"
        elif response.status_code == 404:
            return f"❌ **Not Found** (404)\\n\\nThe requested resource was not found at {url}"
        elif response.status_code == 401:
            return f"🔐 **Unauthorized** (401)\\n\\nAuthentication required or invalid credentials for {url}"
        elif response.status_code == 403:
            return f"🚫 **Forbidden** (403)\\n\\nAccess denied to {url}"
        elif response.status_code >= 500:
            return f"🔥 **Server Error** ({response.status_code})\\n\\nThe server encountered an error processing your request"
        else:
            return f"⚠️ **HTTP {response.status_code}**\\n\\n{response.text[:500]}"
            
    except requests.exceptions.Timeout:
        return f"⏱️ **Timeout Error**\\n\\nRequest to {url} timed out after 10 seconds"
    except requests.exceptions.ConnectionError:
        return f"🔌 **Connection Error**\\n\\nCould not connect to {url}. Check your internet connection."
    except requests.exceptions.RequestException as e:
        return f"❌ **Request Error**\\n\\n{str(e)}"
    except Exception as e:
        return f"❌ **Unexpected Error**\\n\\n{str(e)}"

def fetch_github_user(username: str) -> str:
    """Fetch GitHub user information using the GitHub API."""
    url = f"https://api.github.com/users/{username}"
    
    try:
        response = requests.get(url, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            
            # Extract key information
            user_info = f"""👤 **GitHub User: {data['login']}**
            
**Profile Information:**
• Name: {data.get('name', 'Not provided')}
• Bio: {data.get('bio', 'No bio available')}
• Location: {data.get('location', 'Not specified')}
• Company: {data.get('company', 'Not specified')}
• Blog: {data.get('blog', 'None')}

**GitHub Stats:**
• Public Repos: {data['public_repos']}
• Followers: {data['followers']}
• Following: {data['following']}
• Account Created: {data['created_at'][:10]}

**Profile URL:** {data['html_url']}"""

            return user_info
            
        elif response.status_code == 404:
            return f"❌ GitHub user '{username}' not found\\n\\nPlease check the username and try again."
        else:
            return f"❌ GitHub API error: HTTP {response.status_code}"
            
    except Exception as e:
        return f"❌ Error fetching GitHub user: {str(e)}"

def fetch_json_placeholder_data(resource: str, resource_id: str = "") -> str:
    """Fetch data from JSONPlaceholder API for testing purposes."""
    base_url = "https://jsonplaceholder.typicode.com"
    
    valid_resources = ["posts", "comments", "albums", "photos", "todos", "users"]
    if resource not in valid_resources:
        return f"❌ Invalid resource '{resource}'. Valid options: {', '.join(valid_resources)}"
    
    # Build URL
    url = f"{base_url}/{resource}"
    if resource_id:
        url += f"/{resource_id}"
    
    try:
        response = requests.get(url, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            
            # Format the response based on resource type
            if resource == "users" and resource_id:
                user = data
                return f"""👤 **User #{user['id']}**
                
• Name: {user['name']} ({user['username']})
• Email: {user['email']}
• Phone: {user['phone']}
• Website: {user['website']}
• Company: {user['company']['name']}
• Address: {user['address']['city']}, {user['address']['zipcode']}"""
                
            elif resource == "posts" and resource_id:
                post = data
                return f"""📝 **Post #{post['id']}**
                
**Title:** {post['title']}

**Content:**
{post['body']}

**Author:** User #{post['userId']}"""
                
            elif isinstance(data, list):
                count = len(data)
                return f"📊 **{resource.title()} Collection**\\n\\nFound {count} {resource}\\n\\nFirst item: {json.dumps(data[0], indent=2) if data else 'None'}"
            else:
                return f"📄 **{resource.title()} Data**\\n\\n{json.dumps(data, indent=2)}"
                
        elif response.status_code == 404:
            return f"❌ {resource.title()} {f'#{resource_id}' if resource_id else ''} not found"
        else:
            return f"❌ API error: HTTP {response.status_code}"
            
    except Exception as e:
        return f"❌ Error fetching {resource}: {str(e)}"

def test_api_endpoint(url: str) -> str:
    """Test if an API endpoint is accessible and return basic information."""
    try:
        start_time = datetime.now()
        
        response = requests.get(url, timeout=5)
        
        end_time = datetime.now()
        response_time = (end_time - start_time).total_seconds() * 1000
        
        result = f"""🌐 **API Endpoint Test**

**URL:** {url}
**Response Time:** {response_time:.0f}ms
**Status Code:** {response.status_code}

**Response Headers:**
• Content-Type: {response.headers.get('content-type', 'Not specified')}
• Content-Length: {response.headers.get('content-length', 'Unknown')}
• Server: {response.headers.get('server', 'Unknown')}

**Status:** """
        
        if 200 <= response.status_code < 300:
            result += "✅ Healthy - API is responding correctly"
        elif 400 <= response.status_code < 500:
            result += "⚠️ Client Error - Check request parameters"
        elif 500 <= response.status_code < 600:
            result += "🔥 Server Error - API is experiencing issues"
        else:
            result += f"❓ Unexpected status code: {response.status_code}"
        
        # Show a preview of the response
        if response.text:
            preview = response.text[:200]
            result += f"\\n\\n**Response Preview:**\\n{preview}{'...' if len(response.text) > 200 else ''}"
        
        return result
        
    except requests.exceptions.Timeout:
        return f"⏱️ **Timeout** - API at {url} did not respond within 5 seconds"
    except requests.exceptions.ConnectionError:
        return f"🔌 **Connection Failed** - Cannot reach {url}"
    except Exception as e:
        return f"❌ **Test Error** - {str(e)}"

def simulate_webhook_payload(event_type: str, data: Dict[str, Any] = None) -> str:
    """Simulate creating a webhook payload for testing purposes."""
    if not data:
        data = {}
    
    timestamp = datetime.now().isoformat()
    
    # Common webhook event types and their example payloads
    webhook_templates = {
        "user.created": {
            "user_id": "12345",
            "username": "john_doe",
            "email": "john@example.com",
            "created_at": timestamp
        },
        "order.completed": {
            "order_id": "ORD-789",
            "customer_id": "CUST-456", 
            "total_amount": 99.99,
            "currency": "USD",
            "status": "completed"
        },
        "payment.successful": {
            "payment_id": "PAY-123",
            "amount": 49.99,
            "currency": "USD",
            "method": "credit_card"
        }
    }
    
    # Use template or provided data
    if event_type in webhook_templates:
        payload_data = webhook_templates[event_type]
        payload_data.update(data)  # Override with any provided data
    else:
        payload_data = data
    
    webhook_payload = {
        "event": event_type,
        "timestamp": timestamp,
        "data": payload_data,
        "webhook_id": f"wh_{int(datetime.now().timestamp())}"
    }
    
    return f"""🔗 **Webhook Payload Simulation**

**Event Type:** {event_type}
**Timestamp:** {timestamp}

**Payload:**
{json.dumps(webhook_payload, indent=2)}

**Usage:** This payload can be used to test webhook endpoints and event processing systems."""

# Create the API client agent
agent = Agent(
    name="api_client",
    system_prompt="""You are an expert API client assistant that helps with:

🌐 **HTTP Requests**: Making GET, POST, PUT, DELETE requests to any API
📊 **Data Fetching**: Retrieving and parsing data from external services  
🔍 **API Testing**: Testing endpoint health and response times
🔗 **Webhook Simulation**: Creating test payloads for webhook development
📝 **Response Analysis**: Parsing and formatting API responses

Always handle errors gracefully and provide clear, actionable feedback about API interactions.
Be security-conscious about API keys and sensitive data.""",
    tools=[make_api_request, fetch_github_user, fetch_json_placeholder_data, test_api_endpoint, simulate_webhook_payload]
)

if __name__ == "__main__":
    print("=== API Client Agent Demo ===\\n")
    
    # Demo commands
    demo_commands = [
        "Get GitHub user information for 'octocat'",
        "Test if the JSONPlaceholder API is working",
        "Fetch user #1 from JSONPlaceholder",
        "Create a webhook payload for a user.created event",
        "Test the health of https://httpbin.org/get"
    ]
    
    for i, command in enumerate(demo_commands, 1):
        print(f"Command {i}: {command}")
        response = agent.input(command)
        print(f"Response: {response}\\n")
        print("-" * 70)`

export default function ApiClientPage() {
  const [copiedId, setCopiedId] = useState<string | null>(null)

  const copyToClipboard = (text: string, id: string) => {
    navigator.clipboard.writeText(text)
    setCopiedId(id)
    setTimeout(() => setCopiedId(null), 2000)
  }

  const markdownContent = `# API Client Agent - ConnectOnion Tutorial

Learn HTTP requests, external API integration, and error handling by building a comprehensive API client agent.

## What You'll Learn

- HTTP request methods (GET, POST, PUT, DELETE)
- External API integration patterns
- Error handling for network operations
- Response parsing and data formatting
- API testing and health monitoring
- Webhook simulation and testing

## Key Features

- 🌐 Full HTTP client with all major methods
- 📊 GitHub API integration for user data
- 🔍 JSONPlaceholder API for testing
- ⚡ API endpoint health testing
- 🔗 Webhook payload simulation
- 🛡️ Comprehensive error handling

## Complete Example

\`\`\`python
${fullExampleCode}
\`\`\`

## API Integration Concepts

This example demonstrates:
- **HTTP Methods**: GET, POST, PUT, DELETE request handling
- **Error Handling**: Network timeouts, connection errors, HTTP status codes
- **Response Processing**: JSON parsing and data formatting
- **API Testing**: Endpoint health checks and performance monitoring
- **Security**: Proper headers, timeout handling, and error messages

Perfect foundation for building agents that integrate with external services!`

  return (
    <div className="max-w-6xl mx-auto px-8 py-12 lg:py-12 pt-16 lg:pt-12">
      <nav className="flex items-center gap-2 text-sm text-gray-400 mb-8">
        <Link href="/" className="hover:text-white transition-colors">Home</Link>
        <ArrowRight className="w-4 h-4" />
        <Link href="/examples" className="hover:text-white transition-colors">Agent Building</Link>
        <ArrowRight className="w-4 h-4" />
        <span className="text-white">API Client</span>
      </nav>

      <div className="flex items-start justify-between mb-12">
        <div className="flex-1">
          <div className="flex items-center gap-4 mb-4">
            <div className="w-16 h-16 bg-indigo-600 rounded-xl flex items-center justify-center">
              <span className="text-2xl font-bold text-white">7</span>
            </div>
            <div>
              <div className="flex items-center gap-3 mb-2">
                <Database className="w-8 h-8 text-indigo-400" />
                <h1 className="text-4xl font-bold text-white">API Client Agent</h1>
                <span className="px-3 py-1 bg-indigo-900/50 text-indigo-300 rounded-full text-sm font-medium">
                  Advanced
                </span>
              </div>
              <p className="text-xl text-gray-300">
                Learn HTTP requests and external API integration with a comprehensive API client system.
              </p>
            </div>
          </div>
        </div>
        
        <CopyMarkdownButton 
          content={markdownContent}
          filename="api-client-agent.md"
          className="ml-8 flex-shrink-0"
        />
      </div>

      <div className="mb-12 p-6 bg-indigo-900/20 border border-indigo-500/30 rounded-xl">
        <h2 className="text-xl font-bold text-white mb-4 flex items-center gap-3">
          <Lightbulb className="w-6 h-6 text-indigo-400" />
          What You'll Learn
        </h2>
        <div className="grid md:grid-cols-4 gap-6">
          <div className="text-center">
            <div className="w-12 h-12 mx-auto mb-3 bg-indigo-600 rounded-lg flex items-center justify-center">
              <Globe className="w-6 h-6 text-white" />
            </div>
            <h3 className="text-white font-semibold mb-1">HTTP Methods</h3>
            <p className="text-indigo-200 text-sm">GET, POST, PUT, DELETE requests</p>
          </div>
          <div className="text-center">
            <div className="w-12 h-12 mx-auto mb-3 bg-indigo-600 rounded-lg flex items-center justify-center">
              <Zap className="w-6 h-6 text-white" />
            </div>
            <h3 className="text-white font-semibold mb-1">API Integration</h3>
            <p className="text-indigo-200 text-sm">External service integration patterns</p>
          </div>
          <div className="text-center">
            <div className="w-12 h-12 mx-auto mb-3 bg-indigo-600 rounded-lg flex items-center justify-center">
              <Lock className="w-6 h-6 text-white" />
            </div>
            <h3 className="text-white font-semibold mb-1">Error Handling</h3>
            <p className="text-indigo-200 text-sm">Network and HTTP error management</p>
          </div>
          <div className="text-center">
            <div className="w-12 h-12 mx-auto mb-3 bg-indigo-600 rounded-lg flex items-center justify-center">
              <Terminal className="w-6 h-6 text-white" />
            </div>
            <h3 className="text-white font-semibold mb-1">API Testing</h3>
            <p className="text-indigo-200 text-sm">Health checks and monitoring</p>
          </div>
        </div>
      </div>

      <nav className="flex justify-between items-center pt-12 mt-12 border-t border-gray-800">
        <div className="text-center">
          <p className="text-sm text-gray-400 mb-1">Previous in series</p>
          <Link 
            href="/examples/file-analyzer" 
            className="flex items-center gap-2 text-white hover:text-gray-300 transition-colors font-medium"
          >
            <ArrowLeft className="w-4 h-4" />
            6. File Analyzer
          </Link>
        </div>
        <div className="text-center">
          <p className="text-sm text-gray-400 mb-1">Next in series</p>
          <Link 
            href="/examples/ecommerce-manager" 
            className="flex items-center gap-2 text-white hover:text-gray-300 transition-colors font-medium"
          >
            8. E-commerce Manager
            <ArrowRight className="w-4 h-4" />
          </Link>
        </div>
      </nav>
    </div>
  )
}