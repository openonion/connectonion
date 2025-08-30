# Complete Guide to max_iterations in ConnectOnion

## Quick Reference

```python
# Default (10 iterations) - Works for most tasks
agent = Agent("assistant", tools=[...])

# Simple tasks (3-5 iterations)
calc_agent = Agent("calculator", tools=[calculate], max_iterations=5)

# Standard tasks (8-10 iterations)
general_agent = Agent("helper", tools=[...], max_iterations=10)

# Complex tasks (15-20 iterations)
research_agent = Agent("researcher", tools=[...], max_iterations=20)

# Browser automation (15-25 iterations)
browser_agent = Agent("browser", tools=browser, max_iterations=20)

# Multi-step workflows (20-30 iterations)
workflow_agent = Agent("workflow", tools=[...], max_iterations=30)
```

## What is max_iterations?

`max_iterations` controls how many times an agent can use tools to complete a task. Each tool call counts as one iteration.

### Why It Matters

- **Too few iterations**: Agent might not complete complex tasks
- **Too many iterations**: Wastes API calls and time
- **Just right**: Efficient completion without waste

## Recommended Settings by Use Case

### 🧮 Simple Calculations & Single Tool Tasks
**Recommended: 3-5 iterations**

```python
# Math calculations
calc_agent = Agent(
    "calculator",
    tools=[calculate],
    max_iterations=5  # Rarely needs more than 2-3
)

# Simple queries
query_agent = Agent(
    "query_bot",
    tools=[lookup, get_info],
    max_iterations=5
)
```

### 💬 Conversational Agents
**Recommended: 8-10 iterations**

```python
# Chatbots with multiple tools
chat_agent = Agent(
    "assistant",
    tools=[search, calculate, get_time, weather],
    max_iterations=10  # Default is usually perfect
)

# Customer support
support_agent = Agent(
    "support",
    tools=[lookup_ticket, create_response, send_email],
    max_iterations=8
)
```

### 📊 Data Analysis & Processing
**Recommended: 10-15 iterations**

```python
# Data analysis
analyst = Agent(
    "data_analyst",
    tools=[load_data, analyze, visualize, save_report],
    max_iterations=15  # Multiple analysis steps
)

# File processing
file_agent = Agent(
    "file_processor",
    tools=[read_file, process, transform, write_file],
    max_iterations=12
)
```

### 🌐 Web Automation & Scraping
**Recommended: 15-25 iterations**

```python
# Browser automation
browser_agent = Agent(
    "web_scraper",
    tools=browser_instance,  # Multiple navigation steps
    max_iterations=20
)

# API interactions
api_agent = Agent(
    "api_client",
    tools=[authenticate, fetch, paginate, aggregate],
    max_iterations=15
)
```

### 🔬 Research & Complex Workflows
**Recommended: 20-30 iterations**

```python
# Research tasks
researcher = Agent(
    "researcher",
    tools=[search, analyze, summarize, cite, write],
    max_iterations=25
)

# Multi-agent coordination
coordinator = Agent(
    "coordinator",
    tools=[delegate, collect, merge, validate, report],
    max_iterations=30
)
```

### 🎯 Specialized High-Iteration Tasks
**Recommended: 30-50 iterations**

```python
# Complex debugging
debug_agent = Agent(
    "debugger",
    tools=[analyze_code, test, fix, verify, document],
    max_iterations=40  # May need many fix-test cycles
)

# Full automation workflows
automation_agent = Agent(
    "full_auto",
    tools=[...],  # Many tools
    max_iterations=50  # Complete autonomy
)
```

## Dynamic Iteration Strategies

### Per-Task Override

```python
agent = Agent("flex", tools=[...], max_iterations=10)

# Simple task uses default
result = agent.input("What is 2+2?")

# Complex task needs more
result = agent.input(
    "Research AI trends, analyze data, and create a report",
    max_iterations=30  # Override for this task only
)
```

### Adaptive Based on Task Complexity

```python
def smart_input(agent, task):
    """Automatically adjust iterations based on task complexity."""
    # Count indicators of complexity
    complexity_keywords = ['analyze', 'research', 'multiple', 'all', 'compare', 'detailed']
    complexity = sum(1 for word in complexity_keywords if word in task.lower())
    
    # Set iterations based on complexity
    if complexity == 0:
        max_iter = 5
    elif complexity <= 2:
        max_iter = 10
    elif complexity <= 4:
        max_iter = 20
    else:
        max_iter = 30
    
    return agent.input(task, max_iterations=max_iter)
```

### Template-Based Settings

```python
# Define templates for different agent types
AGENT_TEMPLATES = {
    'simple': {'max_iterations': 5},
    'standard': {'max_iterations': 10},
    'complex': {'max_iterations': 20},
    'research': {'max_iterations': 30},
    'browser': {'max_iterations': 25},
}

def create_agent(name, agent_type, tools):
    """Create agent with template settings."""
    settings = AGENT_TEMPLATES.get(agent_type, AGENT_TEMPLATES['standard'])
    return Agent(name, tools=tools, **settings)

# Usage
calc = create_agent("calc", "simple", [calculate])
researcher = create_agent("researcher", "research", research_tools)
```

## Common Patterns & Anti-Patterns

### ✅ Good Patterns

```python
# Start conservative, increase if needed
agent = Agent("test", tools=[...], max_iterations=10)
# Monitor failures, adjust accordingly

# Different limits for different environments
if ENVIRONMENT == "production":
    max_iter = 20  # More reliable
else:
    max_iter = 10  # Faster development

# Document your reasoning
agent = Agent(
    "analyzer",
    tools=[...],
    max_iterations=15  # Needs: search (3) + analyze (5) + summarize (3) + buffer (4)
)
```

### ❌ Anti-Patterns

```python
# Don't set arbitrarily high
agent = Agent("wasteful", tools=[...], max_iterations=100)  # Wastes resources

# Don't ignore task requirements
agent = Agent("browser", tools=browser, max_iterations=5)  # Too low for browser

# Don't use same setting for all agents
# Each agent type has different needs!
```

## Debugging Iteration Issues

### Signs You Need More Iterations

```python
# Agent output indicates incomplete task
"I need to continue but reached the iteration limit..."
"Task partially completed..."

# History shows hitting the limit
if len(agent.history.last_record.tool_calls) == agent.max_iterations:
    print("Hit iteration limit - consider increasing")
```

### Signs You Have Too Many Iterations

```python
# Most tasks complete in < 50% of limit
# Check average iterations used
avg_iterations = sum(
    len(record.tool_calls) 
    for record in agent.history.records
) / len(agent.history.records)

if avg_iterations < agent.max_iterations * 0.3:
    print(f"Only using {avg_iterations}/{agent.max_iterations} on average")
```

## Performance Considerations

### Cost Optimization

```python
# Estimate cost per iteration
COST_PER_ITERATION = 0.002  # Example: $0.002 per tool call

def estimate_cost(agent, task_count):
    """Estimate operational cost."""
    avg_iterations = 10  # From your metrics
    total_iterations = task_count * avg_iterations
    return total_iterations * COST_PER_ITERATION

# Budget-aware agent
class BudgetAgent:
    def __init__(self, daily_budget=10.0):
        self.budget = daily_budget
        self.spent = 0.0
    
    def can_run(self, max_iterations):
        cost = max_iterations * COST_PER_ITERATION
        return self.spent + cost <= self.budget
```

### Latency Optimization

```python
# Parallel execution for independent tasks
async def fast_research(queries):
    """Run multiple agents in parallel with appropriate limits."""
    agents = [
        Agent(f"researcher_{i}", tools=[search], max_iterations=5)
        for i in range(len(queries))
    ]
    
    # Run in parallel
    results = await asyncio.gather(*[
        agent.ainput(query) for agent, query in zip(agents, queries)
    ])
    return results
```

## Best Practices Summary

1. **Start with defaults** (10 iterations) - adjust based on actual usage
2. **Monitor your agents** - track average iterations used
3. **Set by task type** - different tasks need different limits
4. **Use overrides** - flexibility for specific complex tasks
5. **Document your choices** - explain why you chose specific limits
6. **Test edge cases** - ensure limits work for both simple and complex inputs
7. **Consider costs** - balance completeness with API usage
8. **Learn from history** - analyze past runs to optimize settings

## Quick Decision Tree

```
Is your task...
├── Single tool, simple calculation? → 3-5 iterations
├── Multiple tools, standard complexity? → 8-10 iterations  
├── Data analysis or file processing? → 10-15 iterations
├── Web automation or API calls? → 15-25 iterations
├── Research or complex workflows? → 20-30 iterations
└── Highly complex, many steps? → 30-50 iterations
```

## Examples by Industry

### E-commerce
```python
# Product search
search_agent = Agent("product_search", tools=[search_products], max_iterations=8)

# Order processing  
order_agent = Agent("order_processor", tools=[...], max_iterations=15)

# Customer service
service_agent = Agent("customer_service", tools=[...], max_iterations=10)
```

### Healthcare
```python
# Patient lookup
lookup_agent = Agent("patient_lookup", tools=[search_patient], max_iterations=5)

# Diagnosis assistant
diagnosis_agent = Agent("diagnosis", tools=[...], max_iterations=20)

# Report generation
report_agent = Agent("report_gen", tools=[...], max_iterations=15)
```

### Finance
```python
# Transaction processing
transaction_agent = Agent("transactions", tools=[...], max_iterations=10)

# Risk analysis
risk_agent = Agent("risk_analysis", tools=[...], max_iterations=25)

# Fraud detection
fraud_agent = Agent("fraud_detect", tools=[...], max_iterations=30)
```

## Remember

- There's no perfect number - it depends on your use case
- Start conservative and increase based on real usage
- Monitor and adjust based on actual performance
- Different tasks need different limits - use overrides!

The goal is to give your agent enough iterations to succeed without wasting resources. With these guidelines, you'll find the sweet spot for your specific needs.