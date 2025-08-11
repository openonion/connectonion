# Migration Strategy

Seamless transition from existing agent frameworks to ConnectOnion's behavior-based approach.

## Overview

Moving to ConnectOnion doesn't require abandoning your existing code. We provide progressive migration paths from popular frameworks, letting you adopt behavioral agents at your own pace.

## Migration Principles

1. **No Big Bang** - Gradual adoption, one agent at a time
2. **Preserve Investment** - Existing code continues to work
3. **Immediate Value** - Benefits from day one
4. **Easy Rollback** - Can revert if needed

## From OpenAI Function Calling

### Current Approach
```python
# Traditional OpenAI function calling
def get_weather(location: str, unit: str = "celsius"):
    """Get the current weather in a given location"""
    # Implementation
    return weather_data

functions = [
    {
        "name": "get_weather",
        "description": "Get the current weather in a given location",
        "parameters": {
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": "The city and state"
                },
                "unit": {"type": "string", "enum": ["celsius", "fahrenheit"]}
            },
            "required": ["location"]
        }
    }
]

response = openai.ChatCompletion.create(
    model="gpt-3.5-turbo",
    messages=messages,
    functions=functions
)
```

### Migration Step 1: Wrap Existing Functions
```python
from connectonion import Agent

# Your existing function stays the same
def get_weather(location: str, unit: str = "celsius"):
    """Get the current weather in a given location"""
    # Existing implementation unchanged
    return weather_data

# Create agent with your function
weather_agent = Agent(
    name="weather_service",
    tools=[get_weather]  # Auto-converts to behavioral agent
)

# Use it the same way
result = weather_agent.input("What's the weather in Paris?")
```

### Migration Step 2: Make Discoverable
```python
from connectonion import agent

# Add decorator to make discoverable
@agent(port=8001)
def get_weather(location: str, unit: str = "celsius"):
    """Get the current weather in a given location"""
    # Same implementation
    return weather_data

# Now other agents can discover and use it
weather = discover("weather information")
result = weather("Paris", "celsius")
```

### Migration Step 3: Remove OpenAI Dependency
```python
# Before: Tied to OpenAI
response = openai.ChatCompletion.create(...)

# After: Any LLM backend
agent = Agent(
    name="assistant",
    llm=YourPreferredLLM(),  # Or defaults to OpenAI
    tools=[...]
)
```

## From LangChain

### Current Approach
```python
from langchain import LLMChain, PromptTemplate
from langchain.agents import Tool, AgentExecutor

# Complex chain setup
tools = [
    Tool(
        name="Search",
        func=search.run,
        description="Search for information"
    ),
    Tool(
        name="Calculator",
        func=calculator.run,
        description="Perform calculations"
    )
]

agent = initialize_agent(
    tools, 
    llm, 
    agent=AgentType.ZERO_SHOT_REACT_DESCRIPTION
)

result = agent.input("Search for Python tutorials and calculate 25 * 4")
```

### Migration Step 1: Convert Tools
```python
from connectonion import Agent

# Convert LangChain tools to functions
def search(query: str) -> str:
    """Search for information"""
    return search_engine.run(query)

def calculate(expression: str) -> float:
    """Perform calculations"""
    return calculator.run(expression)

# Create ConnectOnion agent
agent = Agent(
    name="research_assistant",
    tools=[search, calculate]
)

result = agent.input("Search for Python tutorials and calculate 25 * 4")
```

### Migration Step 2: Simplify Chains
```python
# Before: Complex chain orchestration
chain = LLMChain(
    llm=llm,
    prompt=prompt,
    output_parser=parser
) | RunnablePassthrough() | another_chain

# After: Simple function composition
@agent
def research_chain(topic: str) -> str:
    """Research a topic comprehensively"""
    
    # Each step is just a function call
    search_results = search(topic)
    summary = summarize(search_results)
    analysis = analyze(summary)
    
    return format_report(analysis)
```

### Migration Step 3: Distributed Chains
```python
# Before: Chains run in single process
chain = SequentialChain(chains=[chain1, chain2, chain3])

# After: Chains can run distributed
@agent
def distributed_pipeline(data: str) -> str:
    """Process data through distributed pipeline"""
    
    # Each step can run on different machines
    step1 = discover("preprocessing")
    step2 = discover("analysis") 
    step3 = discover("reporting")
    
    return step3(step2(step1(data)))
```

## From AutoGPT/BabyAGI

### Current Approach
```python
# Autonomous agent with complex orchestration
class AutonomousAgent:
    def __init__(self):
        self.memory = LongTermMemory()
        self.tools = ToolRegistry()
        self.planner = TaskPlanner()
    
    def run(self, objective):
        tasks = self.planner.decompose(objective)
        for task in tasks:
            tool = self.select_tool(task)
            result = tool.execute(task)
            self.memory.store(result)
```

### Migration Step 1: Behavioral Decomposition
```python
from connectonion import agent

# Break into behavioral agents
@agent
def task_planner(objective: str) -> list:
    """Decompose objective into tasks"""
    return task_list

@agent
def task_executor(task: str) -> str:
    """Execute a single task"""
    tool = discover(task.required_capability)
    return tool(task.parameters)

@agent
def autonomous_agent(objective: str) -> str:
    """Autonomous agent using behavioral composition"""
    
    tasks = task_planner(objective)
    results = []
    
    for task in tasks:
        result = task_executor(task)
        results.append(result)
        
        # Store in behavioral history automatically
        # No explicit memory management needed
    
    return synthesize_results(results)
```

### Migration Step 2: Dynamic Tool Discovery
```python
# Before: Static tool registry
self.tools = {
    "search": SearchTool(),
    "calculate": CalculatorTool(),
    # ... fixed set of tools
}

# After: Dynamic behavioral discovery
@agent
def adaptive_executor(task: str) -> str:
    """Execute task by discovering capable agents"""
    
    # Understand what's needed
    capability = extract_required_capability(task)
    
    # Discover agents that can help
    capable_agents = discover_all(capability)
    
    # Try until success
    for agent in capable_agents:
        try:
            return agent(task)
        except:
            continue  # Natural failover
```

## From Custom Frameworks

### Step 1: Identify Core Functions
```python
# Your custom framework
class MyCustomAgent:
    def process_text(self, text):
        # Complex processing logic
        return processed
    
    def analyze_data(self, data):
        # Analysis logic
        return results

# Extract as standalone functions
def process_text(text: str) -> str:
    """Process text"""
    # Same logic
    return processed

def analyze_data(data: dict) -> dict:
    """Analyze data"""
    # Same logic
    return results
```

### Step 2: Add Behavioral Layer
```python
from connectonion import Agent

# Wrap in ConnectOnion agent
agent = Agent(
    name="custom_processor",
    tools=[process_text, analyze_data],
    system_prompt="You are a specialized processor"
)

# Or make individual functions discoverable
@agent
def process_text(text: str) -> str:
    """Process text"""
    return processed
```

### Step 3: Enable Discovery
```python
# Before: Hard-coded integrations
processor = MyCustomAgent()
analyzer = MyAnalyzer()
result = analyzer.analyze(processor.process(data))

# After: Dynamic discovery
processor = discover("text processing")
analyzer = discover("data analysis")
result = analyzer(processor(data))
```

## Hybrid Approach

### Running Both Systems
```python
# Use ConnectOnion alongside existing framework
class HybridSystem:
    def __init__(self):
        # Keep existing system
        self.legacy_agent = LegacyAgent()
        
        # Add ConnectOnion agents
        self.behavior_agent = Agent(
            name="enhancer",
            tools=[self.enhance_results]
        )
    
    def process(self, request):
        # Use legacy for main processing
        result = self.legacy_agent.process(request)
        
        # Enhance with behavioral agent
        enhanced = self.behavior_agent.input(
            f"Improve this result: {result}"
        )
        
        return enhanced
```

### Gradual Migration
```python
# Phase 1: New features use ConnectOnion
@agent
def new_feature(data: str) -> str:
    """New capability built with ConnectOnion"""
    return process_new_way(data)

# Phase 2: Migrate high-value functions
@agent
def critical_function(params: dict) -> dict:
    """Migrated from legacy system"""
    # Reuse existing logic
    return legacy.critical_function(**params)

# Phase 3: Replace orchestration layer
@agent
def orchestrator(task: str) -> str:
    """New orchestrator using behavioral discovery"""
    
    # Mix of legacy and new
    if "legacy" in task:
        return legacy_system.handle(task)
    else:
        handler = discover(task.type)
        return handler(task)
```

## Migration Tools

### Automatic Conversion
```python
from connectonion.migrate import convert_langchain

# Convert LangChain agent
langchain_agent = create_langchain_agent(tools, llm)
connectonion_agent = convert_langchain(langchain_agent)

# Now works with behavioral discovery
result = connectonion_agent.input("Do something")
```

### Compatibility Wrappers
```python
from connectonion.compat import openai_function

# Make ConnectOnion agent work like OpenAI function
@agent
def my_agent_function(param: str) -> str:
    """My agent logic"""
    return result

# Get OpenAI-compatible function definition
openai_func = openai_function(my_agent_function)
# Returns: {"name": "my_agent_function", "parameters": {...}}
```

### Testing During Migration
```python
import pytest
from connectonion.testing import behavior_test

@behavior_test
def test_migration_compatibility():
    """Ensure migrated function behaves identically"""
    
    # Test legacy
    legacy_result = legacy_function(test_input)
    
    # Test migrated
    migrated = convert_to_agent(legacy_function)
    new_result = migrated(test_input)
    
    assert new_result == legacy_result
```

## Common Patterns

### Pattern 1: Tool Registry → Discovery
```python
# Before
tools = ToolRegistry()
tools.register("search", SearchTool())
tool = tools.get("search")

# After
tool = discover("search")  # Finds any search-capable agent
```

### Pattern 2: Fixed Pipeline → Dynamic Composition
```python
# Before
pipeline = [step1, step2, step3]
result = run_pipeline(data, pipeline)

# After
@agent
def dynamic_pipeline(data: str) -> str:
    steps = discover_pipeline_for(data)
    return compose(steps)(data)
```

### Pattern 3: Central Orchestrator → Peer-to-Peer
```python
# Before
orchestrator.assign_task(agent1, task1)
orchestrator.assign_task(agent2, task2)
results = orchestrator.collect_results()

# After
@agent
def peer_coordinator(tasks: list) -> list:
    # Agents find each other
    results = []
    for task in tasks:
        capable_peer = discover(task.requirement)
        results.append(capable_peer(task))
    return results
```

## Best Practices

### 1. Start Small
- Migrate one function at a time
- Test thoroughly before expanding
- Keep fallback to legacy system

### 2. Preserve Interfaces
- Keep same function signatures
- Return compatible data types
- Maintain error handling

### 3. Monitor Performance
```python
from connectonion.monitoring import migration_metrics

@migration_metrics
def migrated_function(data):
    """Track performance vs legacy"""
    return new_implementation(data)
```

### 4. Document Behaviors
```python
@agent
def migrated_tool(query: str) -> str:
    """
    Search tool migrated from LangChain.
    
    Behavioral profile:
    - Accepts: Natural language queries
    - Returns: Relevant search results
    - Avg response: 200ms
    - Trust score: 0.95
    """
    return search_implementation(query)
```

## Migration Timeline

### Week 1-2: Evaluation
- Identify high-value functions to migrate
- Set up ConnectOnion alongside existing system
- Create proof of concept with one function

### Week 3-4: Pilot
- Migrate 5-10 functions
- Set up behavioral discovery
- Run in parallel with legacy system

### Month 2: Expansion
- Migrate 25% of functions
- Enable agent-to-agent discovery
- Monitor behavioral metrics

### Month 3: Integration
- Migrate 50% of functions
- Replace orchestration layer
- Enable full behavioral routing

### Month 4+: Optimization
- Complete migration of suitable functions
- Optimize behavioral patterns
- Decommission legacy components

## Rollback Strategy

```python
from connectonion.migration import rollback_manager

# Enable rollback tracking
with rollback_manager() as rm:
    # Migrate function
    rm.track(old_function, new_function)
    
    # If issues arise
    if performance_degraded():
        rm.rollback()  # Reverts to old_function
```

## Success Metrics

Track these during migration:

1. **Function Coverage** - % of functions migrated
2. **Discovery Success** - % of discoveries that find suitable agents  
3. **Performance Delta** - Response time comparison
4. **Error Rate** - Failures vs legacy system
5. **Developer Velocity** - Speed of adding new capabilities

## Conclusion

Migration to ConnectOnion is not a risky rewrite but a progressive enhancement. Start with one function, see the benefits of behavioral discovery, and expand at your own pace. Your existing code continues to work while gaining new superpowers.

The journey from identity-based to behavior-based agents begins with a single function.