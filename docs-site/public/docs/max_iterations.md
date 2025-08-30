# max_iterations Guide

## What Are Iterations?

Think of iterations as "attempts" - how many times your agent can use tools to complete a task.

```python
# Your agent tries to complete the task
# Iteration 1: "I need to search for info" → calls search tool
# Iteration 2: "Now I'll calculate something" → calls calculate tool  
# Iteration 3: "Let me save the result" → calls save tool
# Done! Task completed in 3 iterations
```

## Quick Start - Super Simple

### The Basics (90% of what you need)

```python
from connectonion import Agent

# Default: 10 iterations (works for most tasks!)
agent = Agent("my_bot", tools=[search, calculate])

# That's it! Just use it:
result = agent.input("What's 2+2?")  # Uses 1 iteration
result = agent.input("Search for Python tutorials")  # Uses 1-2 iterations
```

### When You Need More Power

```python
# Complex tasks need more iterations
research_agent = Agent(
    "researcher",
    tools=[search, analyze, summarize],
    max_iterations=25  # I need more attempts for complex research
)
```

### Quick Override for One Task

```python
# Normal agent
agent = Agent("helper", tools=[...])  # Default 10

# But this ONE task is complex:
result = agent.input(
    "Do something really complex",
    max_iterations=30  # Just for this task!
)
```

## Real Examples - See It In Action

### Example 1: Simple Calculator Bot

```python
def calculate(expression: str) -> float:
    return eval(expression)  # Simple math

# Calculator rarely needs many attempts
calc_bot = Agent(
    "calculator",
    tools=[calculate],
    max_iterations=3  # Math is simple, 3 attempts is plenty
)

# This works fine with just 1 iteration:
result = calc_bot.input("What's 15 * 8?")
print(result)  # "The answer is 120"
```

### Example 2: Research Assistant  

```python
def search(query: str) -> str:
    return f"Found 10 articles about {query}"

def summarize(text: str) -> str:
    return f"Summary: {text[:100]}..."

def save_notes(content: str) -> str:
    return "Notes saved!"

# Research needs more iterations
researcher = Agent(
    "researcher",
    tools=[search, summarize, save_notes],
    max_iterations=20  # Research involves many steps
)

# This might use 5-10 iterations:
result = researcher.input(
    "Research quantum computing, summarize findings, and save notes"
)
```

### Example 3: What Happens When You Hit The Limit?

```python
# Agent with very low limit
limited_bot = Agent("limited", tools=[...], max_iterations=2)

result = limited_bot.input("Do 5 different things")
print(result)
# Output: "Task incomplete: Maximum iterations (2) reached."

# Fix: Increase the limit!
result = limited_bot.input("Do 5 different things", max_iterations=10)
# Now it works!
```

## Cool Tricks & Advanced Patterns

### Trick 1: Auto-Retry with Higher Limit

```python
def smart_input(agent, prompt, max_retries=3):
    """Automatically increases iterations if task fails."""
    limits = [10, 25, 50]  # Try these limits in order
    
    for limit in limits:
        result = agent.input(prompt, max_iterations=limit)
        if "Maximum iterations" not in result:
            return result  # Success!
    
    return "Task too complex even with 50 iterations"

# Use it:
agent = Agent("smart", tools=[...])
result = smart_input(agent, "Complex task")  # Auto-adjusts!
```

### Trick 2: Dynamic Limit Based on Task

```python
class SmartAgent:
    def __init__(self, name, tools):
        self.agent = Agent(name, tools)
    
    def input(self, prompt):
        # Detect task complexity from keywords
        if "simple" in prompt or "what is" in prompt:
            max_iter = 5
        elif "analyze" in prompt or "research" in prompt:
            max_iter = 30
        else:
            max_iter = 15  # Default
        
        print(f"Using {max_iter} iterations for this task")
        return self.agent.input(prompt, max_iterations=max_iter)

# Use it:
smart = SmartAgent("auto", tools=[...])
smart.input("What is 2+2?")  # Uses 5 iterations
smart.input("Research and analyze market trends")  # Uses 30 iterations
```

### Trick 3: Self-Adjusting Agent

```python
class SelfAdjustingAgent:
    """Agent that learns optimal iterations from history."""
    
    def __init__(self, name, tools):
        self.agent = Agent(name, tools, max_iterations=10)
        self.task_history = {}
    
    def input(self, prompt):
        # Start with learned limit or default
        task_type = self._classify_task(prompt)
        max_iter = self.task_history.get(task_type, 10)
        
        # Try with current limit
        result = self.agent.input(prompt, max_iterations=max_iter)
        
        # If failed, increase and retry
        while "Maximum iterations" in result and max_iter < 50:
            max_iter += 10
            print(f"Increasing to {max_iter} iterations...")
            result = self.agent.input(prompt, max_iterations=max_iter)
        
        # Remember what worked
        if "Maximum iterations" not in result:
            self.task_history[task_type] = max_iter
            print(f"Learned: {task_type} tasks need {max_iter} iterations")
        
        return result
    
    def _classify_task(self, prompt):
        # Simple classification
        if "calculate" in prompt.lower():
            return "math"
        elif "research" in prompt.lower():
            return "research"
        else:
            return "general"

# It learns over time!
agent = SelfAdjustingAgent("learner", tools=[...])
agent.input("Calculate something")  # Learns math needs few iterations
agent.input("Research something")  # Learns research needs more
```

### Trick 4: Budget-Aware Agent

```python
class BudgetAgent:
    """Agent that tracks iteration 'budget' across multiple tasks."""
    
    def __init__(self, name, tools, daily_iteration_budget=1000):
        self.agent = Agent(name, tools)
        self.budget = daily_iteration_budget
        self.used = 0
    
    def input(self, prompt, priority="normal"):
        # Allocate iterations based on priority and remaining budget
        remaining = self.budget - self.used
        
        if priority == "high":
            max_iter = min(50, remaining)
        elif priority == "normal":
            max_iter = min(20, remaining)
        else:  # low priority
            max_iter = min(10, remaining)
        
        if max_iter <= 0:
            return "Iteration budget exhausted for today!"
        
        # Track what we use
        result = self.agent.input(prompt, max_iterations=max_iter)
        
        # Count actual iterations used (simplified)
        iterations_used = min(max_iter, 10)  # Estimate
        self.used += iterations_used
        
        print(f"Used {iterations_used} iterations. {remaining - iterations_used} remaining today.")
        return result

# Use it:
budget_agent = BudgetAgent("budgeted", tools=[...])
budget_agent.input("Important task", priority="high")  # Gets up to 50
budget_agent.input("Regular task")  # Gets up to 20
budget_agent.input("Low priority task", priority="low")  # Gets up to 10
```

### Trick 5: Parallel Agents with Different Limits

```python
def parallel_solve(prompt, tools):
    """Try multiple agents with different strategies in parallel."""
    import concurrent.futures
    
    strategies = [
        ("quick", 5),    # Fast but might fail
        ("normal", 15),  # Balanced
        ("thorough", 40) # Slow but thorough
    ]
    
    def try_strategy(name, limit):
        agent = Agent(f"{name}_solver", tools=tools, max_iterations=limit)
        return name, agent.input(prompt)
    
    # Run all strategies in parallel
    with concurrent.futures.ThreadPoolExecutor() as executor:
        futures = [
            executor.submit(try_strategy, name, limit) 
            for name, limit in strategies
        ]
        
        # Return first successful result
        for future in concurrent.futures.as_completed(futures):
            name, result = future.result()
            if "Maximum iterations" not in result:
                print(f"Strategy '{name}' succeeded!")
                return result
    
    return "All strategies failed"

# Use it:
result = parallel_solve("Complex problem", tools=[...])
```

## When to Use Each Approach

### Keep It Simple (Most Common)
```python
# Just use defaults for most cases
agent = Agent("helper", tools=[...])  # 10 iterations is usually fine
```

### Set and Forget
```python
# Know your use case? Set it once
chatbot = Agent("chat", tools=[...], max_iterations=5)  # Chatbots are simple
analyzer = Agent("analyzer", tools=[...], max_iterations=25)  # Analysis is complex
```

### Dynamic Override
```python
# Override for specific tasks
agent = Agent("flex", tools=[...])
result = agent.input("normal task")  # Uses default 10
result = agent.input("complex task", max_iterations=30)  # Override when needed
```

## Quick Reference

### How Many Iterations Do I Need?

| What You're Doing | Iterations | Example |
|-------------------|------------|---------|
| Simple Q&A | 3-5 | "What's the weather?" |
| Calculations | 5-10 | "Calculate my taxes" |
| Multi-step tasks | 10-20 | "Search and summarize" |
| Complex workflows | 20-40 | "Analyze all data and generate report" |
| Research projects | 30-50 | "Research topic from multiple sources" |

### Common Issues & Fixes

**"Maximum iterations reached" on simple tasks?**
```python
# Your tools might be failing. Check the history:
if "Maximum iterations" in result:
    print(agent.history.records[-1].tool_calls)  # See what went wrong
```

**Don't know what limit to set?**
```python
# Start with default, increase if needed:
agent = Agent("test", tools=[...])  # Start with 10
# If tasks fail, try max_iterations=20, then 30, etc.
```

**Want to prevent infinite loops?**
```python
# Set a low limit for untrusted tasks:
safe_agent = Agent("safe", tools=[...], max_iterations=5)
```

## The One-Minute Summary

1. **Most agents are fine with default `max_iterations=10`**
2. **Simple bots can use 5, complex ones need 20-30**
3. **Override per-task when needed: `agent.input(prompt, max_iterations=X)`**
4. **If you see "Maximum iterations reached", just increase the limit**
5. **Advanced: Build smart agents that adjust limits automatically**

That's it! You now know everything about iteration control. Start simple, adjust when needed! 🚀