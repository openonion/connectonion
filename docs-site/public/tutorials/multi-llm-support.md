# Multi-LLM Support

**One line. Any model. That's it.**

```python
# With Agent
agent = Agent("assistant", model="gpt-4o")        # OpenAI
agent = Agent("assistant", model="gemini-1.5-pro") # Google  
agent = Agent("assistant", model="claude-3-5-sonnet-latest") # Anthropic

# With llm_do
llm_do("Hello", model="gpt-4o")        # OpenAI
llm_do("Hello", model="gemini-1.5-flash")  # Google
llm_do("Hello", model="claude-3-5-haiku-20241022") # Anthropic
```

No configuration files. No provider setup. No complexity. Just change the model name.

## Setup (30 seconds)

```bash
pip install connectonion
export OPENAI_API_KEY="sk-..."      # For GPT models
export GOOGLE_API_KEY="AIza..."     # For Gemini models  
export ANTHROPIC_API_KEY="sk-ant-..." # For Claude models
```

Done. You're ready.

## The Basics: It Just Works

```python
from connectonion import Agent

# Create an agent with OpenAI's GPT-5
agent_openai = Agent("assistant", model="gpt-5")
response = agent_openai.input("Hello! What model are you?")
print("OpenAI:", response)

# Create an agent with Google's Gemini
agent_google = Agent("assistant", model="gemini-2.5-pro")
response = agent_google.input("Hello! What model are you?")
print("Google:", response)

# Create an agent with Anthropic's Claude
agent_claude = Agent("assistant", model="claude-opus-4.1")
response = agent_claude.input("Hello! What model are you?")
print("Claude:", response)
```

That's literally it. Same code. Different model. It just works.

## Compare Models in 10 Lines

```python
from connectonion import Agent

def compare_models(prompt):
    """Compare how different models respond to the same prompt."""
    
    # Define models to compare
    models = {
        "OpenAI GPT-5": "gpt-5-mini",
        "Google Gemini": "gemini-1.5-flash",
        "Claude Haiku": "claude-3-5-haiku"
    }
    
    print(f"Prompt: {prompt}\n")
    print("-" * 50)
    
    for name, model in models.items():
        try:
            agent = Agent(f"compare_{model}", model=model)
            response = agent.input(prompt)
            print(f"\n{name}:")
            print(response)
            print("-" * 50)
        except Exception as e:
            print(f"\n{name}: Error - {e}")
            print("-" * 50)

# Try it with different prompts
compare_models("Write a haiku about programming")
compare_models("Explain recursion in one sentence")
```

## Tools Work Everywhere

Same tools. Any model. Zero changes.

```python
from connectonion import Agent
import datetime

# Define some useful tools
def get_current_time():
    """Get the current date and time."""
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def calculate(expression: str) -> float:
    """Calculate a mathematical expression."""
    # Simple calculator (in production, use a safe math parser)
    allowed = set("0123456789+-*/()., ")
    if all(c in allowed for c in expression):
        return eval(expression)
    raise ValueError("Invalid expression")

def search_knowledge(query: str) -> str:
    """Search for information (simulated)."""
    # In real app, this would search a database or API
    knowledge = {
        "python": "Python is a high-level programming language.",
        "ai": "AI stands for Artificial Intelligence.",
        "connectonion": "ConnectOnion is a framework for AI agents."
    }
    for key, value in knowledge.items():
        if key in query.lower():
            return value
    return "No information found."

# Create agents with the same tools
tools = [get_current_time, calculate, search_knowledge]

agent_openai = Agent("assistant", model="gpt-5-mini", tools=tools)
agent_google = Agent("assistant", model="gemini-1.5-flash", tools=tools)
agent_claude = Agent("assistant", model="claude-3-5-haiku", tools=tools)

# All agents can use the tools
prompt = "What time is it? Calculate 15% of 250. What is Python?"

print("OpenAI GPT-5 Mini:")
print(agent_openai.input(prompt))
print("\n" + "="*50 + "\n")

print("Google Gemini Flash:")
print(agent_google.input(prompt))
print("\n" + "="*50 + "\n")

print("Claude Haiku:")
print(agent_claude.input(prompt))
```

## Pick the Right Model Automatically

```python
from connectonion import Agent

class SmartAssistant:
    """Automatically selects the best model for each task type."""
    
    def __init__(self):
        # Map task types to optimal models
        self.task_models = {
            "code": "claude-opus-4.1",      # Claude excels at coding
            "creative": "gpt-5",            # GPT-5 for creative tasks
            "analysis": "gemini-2.5-pro",   # Gemini for deep analysis
            "quick": "gpt-5-nano",          # Fast model for simple tasks
            "vision": "gemini-2.5-pro",     # Gemini supports many formats
            "reasoning": "gpt-5"            # GPT-5 for complex reasoning
        }
    
    def process(self, prompt: str, task_type: str = "general"):
        """Process a prompt with the optimal model for the task."""
        
        # Select model based on task type
        model = self.task_models.get(task_type, "gpt-5-mini")
        
        print(f"Task type: {task_type}")
        print(f"Selected model: {model}")
        print("-" * 40)
        
        try:
            agent = Agent(f"{task_type}_agent", model=model)
            return agent.input(prompt)
        except Exception as e:
            # Fallback to a reliable model
            print(f"Error with {model}, falling back to gpt-5-mini")
            fallback = Agent("fallback", model="gpt-5-mini")
            return fallback.input(prompt)

# Use the smart assistant
assistant = SmartAssistant()

# Different task types
print(assistant.process("Write a binary search function", task_type="code"))
print("\n" + "="*50 + "\n")

print(assistant.process("What's 2+2?", task_type="quick"))
print("\n" + "="*50 + "\n")

print(assistant.process("Write a poem about the ocean", task_type="creative"))
```

## Automatic Fallbacks

Model down? No problem. It switches automatically.

```python
from connectonion import Agent
import time

class RobustAssistant:
    """Assistant with automatic fallback to available models."""
    
    def __init__(self):
        # Priority order for models (best to fallback)
        self.model_chain = [
            "claude-opus-4.1",    # Most capable
            "gpt-5",             # Very capable
            "gemini-2.5-pro",    # Multimodal champion
            "gpt-5-mini",        # Fast and reliable
            "gemini-1.5-flash"   # Budget option
        ]
        
        self.agent = None
        self.current_model = None
        self._initialize_agent()
    
    def _initialize_agent(self):
        """Try to initialize with the best available model."""
        for model in self.model_chain:
            try:
                self.agent = Agent("robust_assistant", model=model)
                self.current_model = model
                print(f"✓ Initialized with {model}")
                return
            except Exception as e:
                print(f"✗ {model} unavailable: {e}")
                continue
        
        raise Exception("No models available!")
    
    def input(self, prompt: str, max_retries: int = 3):
        """Process input with automatic retry and fallback."""
        
        for attempt in range(max_retries):
            try:
                return self.agent.input(prompt)
            
            except Exception as e:
                error = str(e).lower()
                
                # Rate limit - wait and retry
                if "rate limit" in error:
                    wait_time = 2 ** attempt
                    print(f"Rate limited on {self.current_model}, waiting {wait_time}s...")
                    time.sleep(wait_time)
                    continue
                
                # Model error - try next model
                else:
                    print(f"Error with {self.current_model}: {e}")
                    
                    # Remove failed model and try next
                    if self.current_model in self.model_chain:
                        self.model_chain.remove(self.current_model)
                    
                    if self.model_chain:
                        self._initialize_agent()
                        print(f"Retrying with {self.current_model}...")
                    else:
                        raise Exception("All models failed!")
        
        return "Max retries exceeded"

# Use the robust assistant
assistant = RobustAssistant()
response = assistant.input("Explain the concept of recursion")
print(f"\nResponse from {assistant.current_model}:")
print(response)
```

## Save Money Automatically

```python
from connectonion import Agent

class CostOptimizedAssistant:
    """Selects models based on complexity and budget."""
    
    def __init__(self, budget_mode="standard"):
        """
        Initialize with budget mode:
        - 'premium': Use best models regardless of cost
        - 'standard': Balance quality and cost
        - 'economy': Minimize costs
        """
        self.budget_mode = budget_mode
        
        # Define model tiers with approximate costs
        self.model_tiers = {
            "premium": [
                ("claude-opus-4.1", 15.0),  # $15/1M tokens
                ("gpt-5", 10.0),            # $10/1M tokens
                ("gemini-2.5-pro", 5.0)     # $5/1M tokens
            ],
            "standard": [
                ("gpt-5-mini", 2.0),        # $2/1M tokens
                ("claude-3-5-haiku", 1.0),  # $1/1M tokens
                ("gemini-1.5-flash", 0.3)   # $0.3/1M tokens
            ],
            "economy": [
                ("gpt-5-nano", 0.5),        # $0.5/1M tokens
                ("gemini-1.5-flash-8b", 0.15)  # $0.15/1M tokens
            ]
        }
    
    def estimate_complexity(self, prompt: str) -> str:
        """Estimate task complexity from prompt."""
        complex_keywords = ["analyze", "explain", "design", "implement", "compare"]
        simple_keywords = ["what", "when", "list", "name", "define"]
        
        prompt_lower = prompt.lower()
        
        if any(word in prompt_lower for word in complex_keywords):
            return "complex"
        elif any(word in prompt_lower for word in simple_keywords):
            return "simple"
        else:
            return "medium"
    
    def select_model(self, prompt: str) -> tuple:
        """Select appropriate model based on prompt and budget."""
        complexity = self.estimate_complexity(prompt)
        
        # Adjust tier based on complexity and budget
        if self.budget_mode == "premium":
            models = self.model_tiers["premium"]
        elif self.budget_mode == "economy":
            models = self.model_tiers["economy"]
        else:  # standard
            if complexity == "complex":
                models = self.model_tiers["premium"][:2]  # Use better models
            elif complexity == "simple":
                models = self.model_tiers["economy"]
            else:
                models = self.model_tiers["standard"]
        
        # Try models in order of preference
        for model_name, cost in models:
            try:
                agent = Agent(f"cost_opt_{model_name}", model=model_name)
                return agent, model_name, cost
            except:
                continue
        
        # Fallback
        model_name = "gpt-5-nano"
        return Agent("fallback", model=model_name), model_name, 0.5
    
    def process(self, prompt: str):
        """Process prompt with cost-optimized model selection."""
        agent, model, cost = self.select_model(prompt)
        
        complexity = self.estimate_complexity(prompt)
        print(f"Complexity: {complexity}")
        print(f"Budget mode: {self.budget_mode}")
        print(f"Selected: {model} (≈${cost}/1M tokens)")
        print("-" * 40)
        
        response = agent.input(prompt)
        
        # Estimate tokens (rough approximation)
        estimated_tokens = len(prompt.split()) + len(response.split())
        estimated_cost = (estimated_tokens / 1_000_000) * cost
        
        print(f"\nEstimated cost: ${estimated_cost:.6f}")
        
        return response

# Try different budget modes
for budget in ["economy", "standard", "premium"]:
    assistant = CostOptimizedAssistant(budget_mode=budget)
    print(f"\n{'='*50}")
    print(f"Budget Mode: {budget.upper()}")
    print(f"{'='*50}\n")
    
    response = assistant.process("What is 2+2?")  # Simple
    print(f"Response: {response}\n")
    
    response = assistant.process("Explain quantum computing")  # Complex
    print(f"Response: {response[:100]}...\n")
```

## Quick Tips

### Handle Errors (5 lines)

```python
try:
    agent = Agent("assistant", model="claude-opus-4.1")
    response = agent.input(prompt)
except Exception as e:
    if "api key" in str(e).lower():
        print("Please set your ANTHROPIC_API_KEY")
    elif "rate limit" in str(e).lower():
        print("Rate limited, please wait")
    else:
        print(f"Error: {e}")
```

### Check Available Providers (3 lines)

```python
import os

# Check which providers are available
providers = {
    "OpenAI": os.getenv("OPENAI_API_KEY"),
    "Google": os.getenv("GOOGLE_API_KEY"),
    "Anthropic": os.getenv("ANTHROPIC_API_KEY")
}

available = [name for name, key in providers.items() if key]
print(f"Available providers: {', '.join(available)}")
```

### Model Cheat Sheet

| Need | Use | Why |
|------|-----|-----|
| Code | `claude-opus-4.1` | Best at coding |
| Speed | `gpt-5-nano` | Fastest |
| Long docs | `gemini-2.5-pro` | 2M tokens |
| Images | `gemini-2.5-pro` | Handles everything |

```python
# Track usage across models
usage_tracker = {}

def track_usage(model: str, tokens: int):
    if model not in usage_tracker:
        usage_tracker[model] = 0
    usage_tracker[model] += tokens

# After each call
track_usage("gpt-5", estimated_tokens)

# Review usage
for model, tokens in usage_tracker.items():
    print(f"{model}: {tokens:,} tokens")
```

## Try This Now

```python
from connectonion import Agent

# Just change this string to switch providers
model = "gpt-5"  # or "gemini-2.5-pro" or "claude-opus-4.1"

agent = Agent("demo", model=model)
print(agent.input("What model are you?"))
```

Seriously, that's all there is to it.

## The Bottom Line

**Before ConnectOnion:**
- Different code for each provider
- Complex configurations
- Incompatible tool formats
- Hours of integration work

**With ConnectOnion:**
- One line to switch models
- Tools work everywhere
- Automatic fallbacks
- Zero configuration

Stop wrestling with different APIs. Just build.