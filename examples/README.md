# ConnectOnion Examples

This folder contains example scripts demonstrating how to use ConnectOnion with the new functional tools approach.

## 🚀 Quick Start

### Prerequisites
1. Make sure you have your OpenAI API key in the `.env` file (already copied here)
2. Install dependencies: `pip install -r ../requirements.txt`

### Running Examples

```bash
# Quick start - minimal example
python quick_start.py

# Basic example - comprehensive features
python basic_example.py

# Advanced example - complex tools and workflows
python advanced_example.py

# Interactive chat - type questions in terminal
python interactive_chat.py

# Personality examples - different agent roles and styles
python personality_examples.py
```

## 📁 Example Files

### 1. `quick_start.py` - Minimal Setup ⚡
**Perfect for beginners!**
- Shows the simplest way to create an agent
- 3 basic tools: search, calculate, get_time
- Clear step-by-step comments
- ~50 lines of code

```python
from connectonion import Agent

def calculate(expression: str) -> float:
    """Do math calculations."""
    return eval(expression)

agent = Agent("assistant", tools=[calculate])
result = agent.input("What is 42 * 17?")
```

### 2. `basic_example.py` - Complete Feature Demo 🎯
**Comprehensive overview of capabilities**
- Multiple tool types and return types
- Dynamic tool addition
- File operations
- Behavior history analysis
- Error handling examples

Features demonstrated:
- ✅ Simple functions as tools
- ✅ Tools with multiple parameters
- ✅ String and numeric return types
- ✅ File I/O operations
- ✅ Dynamic tool management
- ✅ Automatic behavior tracking

### 3. `advanced_example.py` - Production-Ready Tools 🔧
**Advanced use cases and best practices**
- Complex tools with error handling
- Different parameter types
- JSON processing
- System information
- File management
- Detailed analytics

Advanced features:
- ✅ Robust error handling
- ✅ Complex parameter schemas
- ✅ Multi-step workflows
- ✅ System integration
- ✅ Performance analytics
- ✅ Production-ready patterns

### 4. `interactive_chat.py` - Terminal Chat Interface 💬
**Real-time conversation with your agent**
- Type questions directly in the terminal
- Get instant responses from the agent
- Session history and summaries
- Multiple useful tools pre-configured

Interactive features:
- ✅ Real-time Q&A interface
- ✅ Search, calculate, weather, notes
- ✅ Session management
- ✅ Error handling and recovery
- ✅ Help commands and examples
- ✅ Graceful exit with summary

```bash
$ python interactive_chat.py
🤖 ConnectOnion Interactive Chat
Type your questions and I'll help you!

🧅 You: What is 25 * 4?
🤖 Assistant: The result of 25 * 4 is 100.

🧅 You: What's the weather in Tokyo?
🤖 Assistant: Weather in Tokyo: Sunny, 22°C

🧅 You: quit
👋 Thanks for using ConnectOnion! Goodbye!
```

### 5. `personality_examples.py` - Agent Personalities 🎭
**Explore different agent roles and communication styles**
- Compare responses from different personality types
- Professional, friendly, casual, technical, creative styles
- Same tasks, different approaches
- Learn how to craft effective system prompts

Agent personalities:
- ✅ Professional Business Assistant
- ✅ Friendly Teacher
- ✅ Casual Buddy  
- ✅ Technical Expert
- ✅ Creative Storyteller
- ✅ Side-by-side comparisons
- ✅ System prompt best practices

## 🎭 Customizing Agent Personality

### System Prompts
Define your agent's role, personality, and behavior with system prompts:

```python
# Professional assistant
agent = Agent(
    name="business_assistant",
    system_prompt="You are a professional business assistant. Provide clear, concise responses with a formal tone.",
    tools=[my_tools]
)

# Friendly teacher  
agent = Agent(
    name="tutor",
    system_prompt="You are an enthusiastic teacher who loves to educate. Explain concepts clearly and be encouraging.",
    tools=[my_tools]
)

# Technical expert
agent = Agent(
    name="expert",
    system_prompt="You are a technical expert. Provide detailed, precise explanations with technical terminology.",
    tools=[my_tools]
)
```

### System Prompt Best Practices
1. **Be Specific**: Define the exact tone and style you want
2. **Set Context**: Explain the agent's role and expertise  
3. **Define Behavior**: How should they interact with users?
4. **Include Examples**: Show the type of responses you want
5. **Test Variations**: Try different prompts to find what works

## 🛠️ Creating Your Own Tools

### Basic Function Tool
```python
def my_tool(param1: str, param2: int = 10) -> str:
    """Description of what this tool does."""
    # Your tool logic here
    return f"Processed {param1} with value {param2}"

# Use it with custom personality
agent = Agent(
    name="my_agent", 
    system_prompt="You are a helpful coding assistant.",
    tools=[my_tool]
)
```

### Key Principles
1. **Functions as Tools**: Just define regular Python functions
2. **Type Hints**: Use type hints for better schema generation
3. **Docstrings**: First line becomes the tool description
4. **Return Strings**: Tools should return strings for best compatibility
5. **Error Handling**: Handle errors gracefully in your functions

### Parameter Types Supported
- `str` → "string" 
- `int` → "integer"
- `float` → "number"  
- `bool` → "boolean"
- `list` → "array"
- `dict` → "object"

## 📊 What Gets Automatically Tracked

Every agent interaction is automatically recorded:

- **Task**: What the user asked for
- **Tool Calls**: Which tools were used with what parameters
- **Results**: What each tool returned
- **Duration**: How long everything took
- **Timestamp**: When it happened

All logged to: `.co/logs/{agent_name}.log`

## 🔧 Tips for Success

### 1. Keep Tools Focused
```python
# Good: Specific, single purpose
def calculate_tax(amount: float, rate: float) -> float:
    return amount * rate

# Less ideal: Too many responsibilities  
def handle_finances(action: str, amount: float, rate: float):
    # Complex branching logic...
```

### 2. Use Clear Descriptions
```python
def weather(city: str) -> str:
    """Get current weather conditions for a specific city."""
    # The LLM uses this description to decide when to call the tool
```

### 3. Handle Errors Gracefully
```python
def divide(a: float, b: float) -> float:
    """Divide two numbers."""
    if b == 0:
        raise ValueError("Cannot divide by zero")
    return a / b
```

### 4. Test Your Tools Individually
```python
# Test your function before giving it to the agent
result = calculate("2 + 2")
print(result)  # Make sure it works!
```

## 🐛 Troubleshooting

### Common Issues

1. **Import Error**: Make sure you're in the examples directory
2. **API Key Missing**: Check that `.env` file contains `OPENAI_API_KEY=your-key`
3. **Tool Not Called**: Ensure your function has a clear docstring
4. **JSON Errors**: Make sure tool functions return strings or handle type conversion

### Getting Help

- Check the main README in the parent directory
- Look at the test files in `../tests/` for more examples
- Review the behavior history JSON files for debugging

## 🎉 Next Steps

Once you're comfortable with these examples:

1. **Create Custom Tools**: Build tools specific to your use case
2. **Integrate APIs**: Connect to external services
3. **Add Error Handling**: Make your tools production-ready
4. **Scale Up**: Use multiple agents for complex workflows

Happy building with ConnectOnion! 🧅✨