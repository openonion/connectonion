# Models

ConnectOnion supports the latest models from OpenAI, Google Gemini, and Anthropic Claude. Get started in 60 seconds with managed keys, or bring your own API keys.

## Quick Start (60 Seconds)

**Easiest Way: Use Managed Keys** - No API key setup required!

```bash
# Authenticate once (includes 100K free tokens)
co auth
```

```python
from connectonion import Agent

# Add co/ prefix - that's it!
agent = Agent("assistant", model="co/gpt-5")
response = agent.input("Hello!")
```

⭐ **Bonus**: [Star our repo](https://github.com/openonion/connectonion) for +100K tokens!

**Alternative: Bring Your Own Keys**

```bash
# Set your API key
export OPENAI_API_KEY="sk-..."
```

```python
from connectonion import Agent

# Use model names directly
agent = Agent("assistant", model="gpt-5")
response = agent.input("Hello!")
```

## Available Models

All models below work with both managed keys (`co/` prefix) and your own API keys.

### OpenAI Models

#### GPT-5 Series
```python
# Best model for coding and agentic tasks across domains
agent = Agent("assistant", model="co/gpt-5")        # Managed
agent = Agent("assistant", model="gpt-5")           # Your key

# Faster, cost-efficient version for well-defined tasks
agent = Agent("assistant", model="co/gpt-5-mini")   # Managed
agent = Agent("assistant", model="gpt-5-mini")      # Your key

# Fastest, most cost-efficient version
agent = Agent("assistant", model="co/gpt-5-nano")   # Managed
agent = Agent("assistant", model="gpt-5-nano")      # Your key
```

#### GPT-4.1
```python
# Smartest non-reasoning model
agent = Agent("assistant", model="co/gpt-4.1")      # Managed
agent = Agent("assistant", model="gpt-4.1")         # Your key
```

#### GPT-4o Series (Previous Generation)
```python
# Multimodal model with vision capabilities
agent = Agent("assistant", model="co/gpt-4o")       # Managed
agent = Agent("assistant", model="gpt-4o")          # Your key

# Affordable small model
agent = Agent("assistant", model="co/gpt-4o-mini")  # Managed
agent = Agent("assistant", model="gpt-4o-mini")     # Your key
```

#### o1 Reasoning Models
```python
# Advanced reasoning and problem solving
agent = Agent("assistant", model="co/o1")           # Managed
agent = Agent("assistant", model="o1")              # Your key

# Fast reasoning, cost-effective
agent = Agent("assistant", model="co/o1-mini")      # Managed
agent = Agent("assistant", model="o1-mini")         # Your key
```

### Google Gemini Models

#### Gemini 3 (Newest - State-of-the-Art Reasoning)
```python
# Most intelligent model family with state-of-the-art reasoning
# 1M token context, dynamic thinking levels (low/medium/high)
agent = Agent("assistant", model="co/gemini-3-pro-preview")  # Managed
agent = Agent("assistant", model="gemini-3-pro-preview")     # Your key

# Image generation model with grounded generation
agent = Agent("assistant", model="co/gemini-3-pro-image-preview")  # Managed
agent = Agent("assistant", model="gemini-3-pro-image-preview")     # Your key
```

#### Gemini 2.5
```python
# Enhanced thinking and reasoning, multimodal understanding, advanced coding
# Supports: Audio, images, videos, text, and PDF
agent = Agent("assistant", model="co/gemini-2.5-pro")  # Managed
agent = Agent("assistant", model="gemini-2.5-pro")     # Your key
```

#### Gemini 2.0
```python
# Experimental multimodal model with native tool use
agent = Agent("assistant", model="co/gemini-2.0-flash-exp")  # Managed
agent = Agent("assistant", model="gemini-2.0-flash-exp")     # Your key

# With thinking/reasoning capabilities
agent = Agent("assistant", model="co/gemini-2.0-flash-thinking-exp")  # Managed
agent = Agent("assistant", model="gemini-2.0-flash-thinking-exp")     # Your key
```

#### Gemini 1.5
```python
# 2M token context window
agent = Agent("assistant", model="co/gemini-1.5-pro")    # Managed
agent = Agent("assistant", model="gemini-1.5-pro")       # Your key

# Fast and versatile, 1M token context
agent = Agent("assistant", model="co/gemini-1.5-flash")  # Managed
agent = Agent("assistant", model="gemini-1.5-flash")     # Your key

# High-volume tasks, lower cost
agent = Agent("assistant", model="co/gemini-1.5-flash-8b")  # Managed
agent = Agent("assistant", model="gemini-1.5-flash-8b")     # Your key
```

### Anthropic Claude Models

#### Claude 4.5 Series (Latest)
```python
# Claude Sonnet 4.5 - Best balance of intelligence and speed
agent = Agent("assistant", model="co/claude-sonnet-4-5")  # Managed
agent = Agent("assistant", model="claude-sonnet-4-5")     # Your key

# Claude Haiku 4.5 - Fastest with near-frontier intelligence
agent = Agent("assistant", model="co/claude-haiku-4-5")   # Managed
agent = Agent("assistant", model="claude-haiku-4-5")      # Your key
```

#### Claude Opus 4 Series
```python
# Claude Opus 4.1 - Specialized reasoning
agent = Agent("assistant", model="co/claude-opus-4-1")    # Managed
agent = Agent("assistant", model="claude-opus-4-1")       # Your key

# Claude Opus 4 - Previous version
agent = Agent("assistant", model="co/claude-opus-4")      # Managed
agent = Agent("assistant", model="claude-opus-4")         # Your key
```

#### Claude Sonnet 4
```python
# Balanced performance model
agent = Agent("assistant", model="co/claude-sonnet-4")    # Managed
agent = Agent("assistant", model="claude-sonnet-4")       # Your key
```

## Model Capabilities Comparison

### Latest Flagship Models

| Model | Provider | Key Strengths | Multimodal |
|-------|----------|---------------|------------|
| gpt-5 | OpenAI | Best for coding and agentic tasks | ✅ |
| gemini-3-pro-preview | Google | State-of-the-art reasoning, dynamic thinking | ✅ |
| claude-sonnet-4-5 | Anthropic | Best balance of intelligence and speed | ✅ |

### Context Windows

| Model | Context Window |
|-------|---------------|
| **OpenAI** | |
| gpt-5 | 200K tokens |
| gpt-5-mini | 200K tokens |
| gpt-5-nano | 128K tokens |
| gpt-4.1 | 128K tokens |
| **Google** | |
| gemini-3-pro-preview | 1M tokens |
| gemini-3-pro-image-preview | 65K tokens |
| gemini-2.5-pro | 2M tokens |
| gemini-1.5-pro | 2M tokens |
| gemini-1.5-flash | 1M tokens |
| **Anthropic** | |
| claude-sonnet-4-5 | 200K tokens |
| claude-haiku-4-5 | 200K tokens |
| claude-opus-4-1 | 200K tokens |

## Pricing (Managed Keys)

All prices are **per 1M tokens** and match official provider pricing:

### OpenAI Models

| Model | Input | Output | Notes |
|-------|-------|--------|-------|
| gpt-5 | $1.25 | $10.00 | Best overall |
| gpt-5-mini | $0.25 | $2.00 | Fast, cost-effective |
| gpt-5-nano | $0.05 | $0.40 | Cheapest |
| gpt-4o | $2.50 | $10.00 | Previous gen flagship |
| gpt-4o-mini | $0.15 | $0.60 | Most cost-effective |
| o4-mini | $3.00 | $12.00 | Reasoning model |

### Google Gemini Models

| Model | Input | Output | Notes |
|-------|-------|--------|-------|
| gemini-3-pro-preview | $2.00 | $12.00 | State-of-the-art reasoning |
| gemini-3-pro-image-preview | $2.00 | $0.134 | Image generation |
| gemini-2.5-pro | $1.25 | $10.00 | Advanced thinking |
| gemini-2.5-flash | $0.30 | $2.50 | Best price-performance |
| gemini-2.5-flash-lite | $0.10 | $0.40 | Ultra fast, cheapest |
| gemini-2.0-flash | $0.10 | $0.40 | Previous gen |

### Anthropic Claude Models

| Model | Input | Output | Notes |
|-------|-------|--------|-------|
| claude-sonnet-4-5 | $3.00 | $15.00 | Best intelligence/speed balance |
| claude-haiku-4-5 | $1.00 | $5.00 | Fastest Claude |
| claude-opus-4-1 | $15.00 | $75.00 | Specialized reasoning |
| claude-sonnet-4 | $3.00 | $15.00 | Previous gen |
| claude-opus-4 | $15.00 | $75.00 | Previous gen |

### Cost Estimation Examples

```python
# Typical conversation (~1000 input, ~500 output tokens)
# gpt-5:           $0.00125 + $0.005 = $0.00625 (~$6.25 per 1000 requests)
# gemini-2.5-flash: $0.0003 + $0.00125 = $0.00155 (~$1.55 per 1000 requests)
# claude-sonnet-4-5: $0.003 + $0.0075 = $0.0105 (~$10.50 per 1000 requests)

# With 100K free tokens, you can make approximately:
# - 66 requests with gpt-5 (1500 tokens each)
# - 66 requests with gemini-2.5-pro
# - 66 requests with claude-sonnet-4-5
```

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
agent_claude = Agent("assistant", model="claude-sonnet-4-5", tools=tools)
```

## Two Ways to Use Models

### Option 1: Managed Keys (Recommended for Getting Started)

No API key setup required - authenticate once and start using all models:

```bash
# One-time authentication
co auth
```

```python
from connectonion import Agent

# Use any model with co/ prefix
agent = Agent("assistant", model="co/gpt-5")
agent = Agent("assistant", model="co/gemini-2.5-pro")
agent = Agent("assistant", model="co/claude-sonnet-4-5")
```

**Includes:**
- 100K free tokens to start
- Access to all providers (OpenAI, Google, Anthropic)
- No API key management needed
- ⭐ Bonus: [Star our repo](https://github.com/openonion/connectonion) for +100K tokens

**When to use:**
- Getting started with ConnectOnion
- Prototyping and testing different models
- Learning AI agent development
- Small projects and experiments

See [Authentication docs](auth.md) for more details.

### Option 2: Bring Your Own API Keys

For production use or high-volume applications, use your own API keys for direct billing:

```bash
# OpenAI
export OPENAI_API_KEY="sk-..."

# Google Gemini (recommended - matches Google's official SDK)
export GEMINI_API_KEY="AIza..."
# Note: GOOGLE_API_KEY also works but GEMINI_API_KEY is preferred

# Anthropic
export ANTHROPIC_API_KEY="sk-ant-..."
```

```python
from connectonion import Agent

# Use models without co/ prefix
agent = Agent("assistant", model="gpt-5")
agent = Agent("assistant", model="gemini-2.5-pro")
agent = Agent("assistant", model="claude-opus-4.1")
```

**Important:** For Gemini models, use `GEMINI_API_KEY` as recommended by [Google's official documentation](https://ai.google.dev/gemini-api/docs/api-key). While `GOOGLE_API_KEY` is supported for backward compatibility, `GEMINI_API_KEY` is the standard used by Google's Python SDK and most tools in the ecosystem.

**When to use:**
- Production deployments
- High-volume usage
- Direct billing relationships with providers
- Existing API key infrastructure

## Model Selection Guide

### By Use Case

**Best Overall Performance**
```python
# Top tier models from each provider
agent = Agent("assistant", model="gpt-5")             # OpenAI flagship
agent = Agent("assistant", model="gemini-2.5-pro")    # Google flagship
agent = Agent("assistant", model="claude-sonnet-4-5") # Anthropic flagship
```

**Code Generation**
```python
# GPT-5 excels at coding and agentic tasks
agent = Agent("coder", model="gpt-5")

# Alternative: Claude Sonnet 4.5
agent = Agent("coder", model="claude-sonnet-4-5")
```

**Fast Responses**
```python
# Fastest options from each provider
agent = Agent("quick", model="gpt-5-nano")       # OpenAI fastest
agent = Agent("quick", model="gemini-1.5-flash") # Google fast
agent = Agent("quick", model="claude-haiku-4-5") # Anthropic fast
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

# With managed keys (easiest)
agent_openai = Agent("assistant", model="co/gpt-5")
agent_google = Agent("assistant", model="co/gemini-2.5-pro")
agent_claude = Agent("assistant", model="co/claude-opus-4.1")

# OR with your own API keys
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
# Compare responses from top models (using managed keys)
models = ["co/gpt-5", "co/gemini-2.5-pro", "co/claude-sonnet-4-5"]
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
        "claude-sonnet-4-5",  # Strong alternative
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
            if model.startswith("gemini") and not os.getenv("GEMINI_API_KEY"):
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
                    "claude-sonnet-4-5": "claude-sonnet-4"
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
agent = Agent("assistant", model="claude-sonnet-4-5")
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

agent = Agent("assistant", model="claude-sonnet-4-5")
response = agent.input(prompt)
```


## See Also

- [Quick Start](quickstart.md) - Get started with ConnectOnion
- [Authentication](auth.md) - Using managed keys
- [Tools](tools.md) - Using tools with models
- [API Setup](setup.md) - Configuring your own API keys