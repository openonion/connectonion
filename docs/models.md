# Models

ConnectOnion supports the latest models from OpenAI, Google Gemini, and Anthropic Claude. Simply specify the model name when creating an agent.

## Quick Start

```python
from connectonion import Agent

# Just change the model name
agent = Agent("assistant", model="gpt-5")              # OpenAI
agent = Agent("assistant", model="gemini-2.5-pro")     # Google
agent = Agent("assistant", model="claude-opus-4.1")    # Anthropic
```

## OpenAI Models

### GPT-5 Series
```python
# Best model for coding and agentic tasks across domains
agent = Agent("assistant", model="gpt-5")

# Faster, cost-efficient version for well-defined tasks
agent = Agent("assistant", model="gpt-5-mini")

# Fastest, most cost-efficient version
agent = Agent("assistant", model="gpt-5-nano")
```

### GPT-4.1
```python
# Smartest non-reasoning model
agent = Agent("assistant", model="gpt-4.1")
```

### GPT-4o Series (Previous Generation)
```python
# Multimodal model with vision capabilities
agent = Agent("assistant", model="gpt-4o")

# Affordable small model
agent = Agent("assistant", model="gpt-4o-mini")
```

### o1 Reasoning Models
```python
# Advanced reasoning and problem solving
agent = Agent("assistant", model="o1")

# Fast reasoning, cost-effective
agent = Agent("assistant", model="o1-mini")
```

## Google Gemini Models

### Gemini 2.5
```python
# Enhanced thinking and reasoning, multimodal understanding, advanced coding
# Supports: Audio, images, videos, text, and PDF
agent = Agent("assistant", model="gemini-2.5-pro")
```

### Gemini 2.0
```python
# Experimental multimodal model with native tool use
agent = Agent("assistant", model="gemini-2.0-flash-exp")

# With thinking/reasoning capabilities
agent = Agent("assistant", model="gemini-2.0-flash-thinking-exp")
```

### Gemini 1.5
```python
# 2M token context window
agent = Agent("assistant", model="gemini-1.5-pro")

# Fast and versatile, 1M token context
agent = Agent("assistant", model="gemini-1.5-flash")

# High-volume tasks, lower cost
agent = Agent("assistant", model="gemini-1.5-flash-8b")
```

## Anthropic Claude Models

### Claude Opus 4 Series
```python
# Claude Opus 4.1 - Latest and most capable
agent = Agent("assistant", model="claude-opus-4.1")

# Claude Opus 4 - Previous version
agent = Agent("assistant", model="claude-opus-4")
```

### Claude Sonnet 4
```python
# Balanced performance model
agent = Agent("assistant", model="claude-sonnet-4")
```

### Claude 3.5 Series (Previous Generation)
```python
# Excellent at coding
agent = Agent("assistant", model="claude-3-5-sonnet")

# Fast and cost-effective
agent = Agent("assistant", model="claude-3-5-haiku")
```

## Model Capabilities Comparison

### Latest Flagship Models

| Model | Provider | Key Strengths | Multimodal |
|-------|----------|---------------|------------|
| gpt-5 | OpenAI | Best for coding and agentic tasks | ✅ |
| gemini-2.5-pro | Google | Enhanced reasoning, supports audio/video/PDF | ✅ |
| claude-opus-4.1 | Anthropic | Most capable Claude model | ✅ |

### Context Windows

| Model | Context Window |
|-------|---------------|
| **OpenAI** | |
| gpt-5 | 200K tokens |
| gpt-5-mini | 200K tokens |
| gpt-5-nano | 128K tokens |
| gpt-4.1 | 128K tokens |
| **Google** | |
| gemini-2.5-pro | 2M tokens |
| gemini-1.5-pro | 2M tokens |
| gemini-1.5-flash | 1M tokens |
| **Anthropic** | |
| claude-opus-4.1 | 200K tokens |
| claude-opus-4 | 200K tokens |
| claude-sonnet-4 | 200K tokens |

### Tool Use Support

All models support function calling / tool use:

```python
def search(query: str) -> str:
    """Search for information."""
    return f"Results for {query}"

def calculate(expression: str) -> float:
    """Calculate mathematical expressions."""
    return eval(expression)

# Same tools work with all providers
tools = [search, calculate]

agent_openai = Agent("assistant", model="gpt-5", tools=tools)
agent_google = Agent("assistant", model="gemini-2.5-pro", tools=tools)
agent_claude = Agent("assistant", model="claude-opus-4.1", tools=tools)
```

## Setting Up API Keys

```bash
# OpenAI
export OPENAI_API_KEY="sk-..."

# Google  
export GOOGLE_API_KEY="AIza..."

# Anthropic
export ANTHROPIC_API_KEY="sk-ant-..."
```

## Model Selection Guide

### By Use Case

**Best Overall Performance**
```python
# Top tier models from each provider
agent = Agent("assistant", model="gpt-5")           # OpenAI flagship
agent = Agent("assistant", model="gemini-2.5-pro")  # Google flagship
agent = Agent("assistant", model="claude-opus-4.1") # Anthropic flagship
```

**Code Generation**
```python
# GPT-5 excels at coding and agentic tasks
agent = Agent("coder", model="gpt-5")

# Alternative: Claude Opus 4.1
agent = Agent("coder", model="claude-opus-4.1")
```

**Fast Responses**
```python
# Fastest options from each provider
agent = Agent("quick", model="gpt-5-nano")      # OpenAI fastest
agent = Agent("quick", model="gemini-1.5-flash") # Google fast
agent = Agent("quick", model="claude-3-5-haiku") # Anthropic fast
```

**Cost-Optimized**
```python
# Most cost-efficient options
agent = Agent("budget", model="gpt-5-nano")       # OpenAI cheapest
agent = Agent("budget", model="gemini-1.5-flash-8b") # Google cheapest
```

**Long Context (>200K tokens)**
```python
# Models with longest context windows
agent = Agent("reader", model="gemini-2.5-pro")  # 2M tokens
agent = Agent("reader", model="gemini-1.5-pro")  # 2M tokens
```

**Multimodal (Images, Audio, Video)**
```python
# Gemini 2.5 Pro supports the most modalities
agent = Agent("multimodal", model="gemini-2.5-pro")  # Audio, video, images, PDF

# Alternatives
agent = Agent("multimodal", model="gpt-5")           # Images, text
agent = Agent("multimodal", model="claude-opus-4.1") # Images, text
```

## Usage Examples

### Basic Usage

```python
from connectonion import Agent

# Create agents with different models
agent_openai = Agent("assistant", model="gpt-5")
agent_google = Agent("assistant", model="gemini-2.5-pro")
agent_claude = Agent("assistant", model="claude-opus-4.1")

# Same interface for all
response = agent_openai.input("Explain quantum computing")
response = agent_google.input("Explain quantum computing")
response = agent_claude.input("Explain quantum computing")
```

### Model Comparison

```python
# Compare responses from top models
models = ["gpt-5", "gemini-2.5-pro", "claude-opus-4.1"]
prompt = "Write a Python implementation of binary search"

for model in models:
    agent = Agent(f"compare_{model}", model=model)
    print(f"\n{model}:")
    print(agent.input(prompt))
```

### Smart Model Selection

```python
def select_model(task_type: str, speed_priority: bool = False) -> str:
    """Select optimal model based on requirements."""
    
    if speed_priority:
        # Fast models
        return {
            "code": "gpt-5-mini",
            "chat": "gpt-5-nano",
            "analysis": "gemini-1.5-flash",
            "creative": "claude-3-5-haiku"
        }.get(task_type, "gpt-5-nano")
    else:
        # Best quality models
        return {
            "code": "gpt-5",
            "reasoning": "gemini-2.5-pro",
            "analysis": "claude-opus-4.1",
            "multimodal": "gemini-2.5-pro"
        }.get(task_type, "gpt-5")

# Use appropriate model
model = select_model("code", speed_priority=False)
agent = Agent("coder", model=model)
```

### Fallback Chain

```python
import os

def create_agent_with_fallback(name: str):
    """Try multiple models if one fails."""
    
    # Priority order
    model_chain = [
        "gpt-5",              # Best overall
        "claude-opus-4.1",    # Strong alternative
        "gemini-2.5-pro",     # Multimodal option
        "gpt-5-mini",         # Faster fallback
        "gpt-4o"              # Legacy fallback
    ]
    
    for model in model_chain:
        try:
            # Check if API key exists for provider
            if model.startswith("gpt") and not os.getenv("OPENAI_API_KEY"):
                continue
            if model.startswith("claude") and not os.getenv("ANTHROPIC_API_KEY"):
                continue
            if model.startswith("gemini") and not os.getenv("GOOGLE_API_KEY"):
                continue
                
            return Agent(name, model=model)
        except Exception as e:
            print(f"Failed with {model}: {e}")
            continue
    
    raise Exception("No models available. Please set at least one API key.")

# Will use best available model
agent = create_agent_with_fallback("assistant")
```

### Using with Tools

```python
def analyze_data(data: str) -> str:
    """Analyze provided data."""
    return f"Analysis of: {data}"

def generate_report(analysis: str) -> str:
    """Generate a report from analysis."""
    return f"Report: {analysis}"

# Tools work identically across all models
tools = [analyze_data, generate_report]

# High-performance agent
agent_performance = Agent("analyst", 
                          model="gpt-5",
                          tools=tools)

# Cost-optimized agent
agent_budget = Agent("analyst_budget",
                    model="gpt-5-nano", 
                    tools=tools)

# Both can use the same tools
result1 = agent_performance.input("Analyze sales data and generate report")
result2 = agent_budget.input("Analyze sales data and generate report")
```

## Error Handling

```python
from connectonion import Agent
import time

def create_robust_agent(name: str, model: str, max_retries: int = 3):
    """Create agent with automatic error handling."""
    
    for attempt in range(max_retries):
        try:
            agent = Agent(name, model=model)
            # Test the agent works
            agent.input("test")
            return agent
            
        except Exception as e:
            error = str(e).lower()
            
            if "api key" in error:
                raise ValueError(f"Missing API key for {model}. "
                               f"Please set the appropriate environment variable.")
            
            if "rate limit" in error:
                wait = 2 ** attempt
                print(f"Rate limited. Waiting {wait}s...")
                time.sleep(wait)
                continue
            
            if "model not found" in error:
                # Try alternative model
                alternatives = {
                    "gpt-5": "gpt-5-mini",
                    "gemini-2.5-pro": "gemini-1.5-pro",
                    "claude-opus-4.1": "claude-opus-4"
                }
                alt_model = alternatives.get(model)
                if alt_model and attempt == 0:
                    print(f"Model {model} not available, trying {alt_model}")
                    model = alt_model
                    continue
                    
            if attempt < max_retries - 1:
                print(f"Attempt {attempt + 1} failed: {e}")
                continue
            else:
                raise
    
    raise Exception(f"Failed to create agent with {model}")

# Usage
agent = create_robust_agent("assistant", "gpt-5")
```

## Migration Guide

### From Single Model to Multi-Model

**Before (ConnectOnion 0.0.1)**
```python
# Only OpenAI GPT models supported
agent = Agent("assistant", model="gpt-4o-mini")
```

**After (ConnectOnion 0.0.2)**
```python
# Any provider, any model
agent = Agent("assistant", model="gpt-5")
agent = Agent("assistant", model="gemini-2.5-pro")
agent = Agent("assistant", model="claude-opus-4.1")
```

### From Direct SDK Usage

**Before (Using provider SDKs)**
```python
# Different code for each provider
import openai
client = openai.OpenAI()
response = client.chat.completions.create(model="gpt-4", ...)

import anthropic
client = anthropic.Anthropic()
response = client.messages.create(model="claude-3", ...)
```

**After (Unified with ConnectOnion)**
```python
# Same interface for all providers
agent = Agent("assistant", model="gpt-5")
response = agent.input(prompt)

agent = Agent("assistant", model="claude-opus-4.1")
response = agent.input(prompt)
```

## Optional: Managed Keys Service

Don't want to manage API keys? ConnectOnion also offers a managed keys service where we handle the API keys for you.

### Get Started with Free Credits

```bash
# Authenticate once
co auth
```

You'll receive **100K tokens** to start using any model immediately.

### Using Managed Models

Just add the `co/` prefix to any model name:

```python
from connectonion import Agent

# Instead of managing your own keys
agent = Agent("assistant", model="co/gpt-5")
agent = Agent("assistant", model="co/gemini-2.5-pro")
agent = Agent("assistant", model="co/claude-opus-4.1")

# Works the same way, no API key setup needed
response = agent.input("Hello!")
```

### Bonus Credits

⭐ **Star our GitHub repo** to get an additional **100K tokens**!

Visit [github.com/wu-changxing/connectonion](https://github.com/wu-changxing/connectonion) and click the Star button.

### When to Use Managed Keys

- **Getting started** - No API key setup required
- **Prototyping** - Quickly test different models
- **Learning** - Explore all providers with one account
- **Small projects** - Pay-as-you-go after free credits

For production or high-volume usage, we recommend using your own API keys for direct billing.

See [Authentication docs](auth.md) for more details on managed keys.

---

## See Also

- [Quick Start](quickstart.md) - Get started with ConnectOnion
- [Authentication](auth.md) - Using managed keys
- [Tools](tools.md) - Using tools with models
- [API Setup](setup.md) - Configuring your own API keys