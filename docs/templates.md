# ConnectOnion Templates

ConnectOnion provides pre-built templates to help you get started quickly with different types of AI agents.

## Available Templates

### Meta-Agent Template (Default)

The meta-agent is your ConnectOnion development assistant, specialized in helping you build agents.

**Tools included:**
- `answer_connectonion_question(question)` - Expert answers from embedded documentation
- `create_agent_from_template(name, template, description)` - Generate complete agents
- `generate_tool_code(name, parameters, description)` - Create tool functions
- `create_test_for_agent(agent_file)` - Generate pytest test suites
- `think(context)` - Self-reflection and task analysis
- `generate_todo_list(task, priority)` - Structured planning (uses GPT-4o-mini)
- `suggest_project_structure(type)` - Architecture recommendations

**Use cases:**
- Learning ConnectOnion framework
- Generating agent code and tools
- Creating test suites
- Planning complex projects
- Getting architecture guidance
- Answering documentation questions

**Example usage:**
```python
# Ask about ConnectOnion
result = agent.input("How do tools work in ConnectOnion?")
# Returns comprehensive documentation-based answer

# Generate agent code
result = agent.input("Create a web scraper agent")
# Generates complete agent implementation

# Create tool functions
result = agent.input("Generate a tool for sending emails with subject and body parameters")
# Returns properly formatted tool code

# Get project structure
result = agent.input("Suggest structure for a multi-agent system")
# Provides architecture recommendations
```

### Playwright Template

The Playwright template creates a web automation agent for browser control and scraping.

**Tools included:**
- `navigate_to_url(url, wait_for)` - Browse to web pages
- `scrape_page_content(url, selector)` - Extract content using CSS selectors
- `fill_form(url, form_data)` - Complete and submit forms
- `take_screenshot(url, output_path, full_page)` - Capture screenshots
- `extract_links(url, filter_pattern)` - Get all links from pages
- `wait_and_click(url, selector, wait_time)` - Click elements
- `execute_javascript(url, script)` - Run JS on pages
- `download_file(url, save_path)` - Download files

**Use cases:**
- Web scraping and data extraction
- Form automation
- Browser testing
- Screenshot documentation
- Link crawling
- File downloads

**Example usage:**
```python
# Scrape content
result = agent.input("Scrape the main content from example.com")

# Take screenshots
result = agent.input("Take a full-page screenshot of the documentation site")

# Form automation
result = agent.input('Fill the contact form with {"#name": "John", "#email": "john@example.com"}')

# Extract links
result = agent.input("Extract all PDF links from the downloads page")
```

**Installation:**
```bash
pip install playwright
playwright install chromium
```

## Template Structure

All templates follow the same structure:

```
template/
├── agent.py       # Agent implementation with tools
└── prompt.md      # System prompt in markdown
```

### agent.py Structure

```python
"""Template description"""

from connectonion import Agent

# Tool functions
def tool_one(param: str) -> str:
    """Tool description."""
    return result

def tool_two(param: str) -> str:
    """Tool description."""
    return result

# Create agent
agent = Agent(
    name="agent_name",
    system_prompt="prompt.md",  # Always use markdown
    tools=[tool_one, tool_two]
)

if __name__ == "__main__":
    # Example usage
    result = agent.input("Your query")
    print(result)
```

### prompt.md Structure

```markdown
# Agent Name

Agent description and purpose.

## Your Capabilities
- List of what the agent can do
- Specific skills and tools

## Communication Style
- How to interact with users
- Tone and personality

## Guidelines
- Specific rules or behaviors
- Best practices
```

## Creating Custom Templates

While ConnectOnion provides built-in templates, you can create your own:

1. **Start with a template**: Use `co init` to create a base
2. **Modify tools**: Add your own tool functions
3. **Update prompt**: Customize `prompt.md` for your use case
4. **Test thoroughly**: Ensure tools work as expected

### Example: Custom Research Agent

```python
# agent.py
from connectonion import Agent
import requests

def search_web(query: str) -> str:
    """Search the web for information."""
    # Your implementation
    return f"Search results for: {query}"

def summarize_text(text: str, length: int = 100) -> str:
    """Summarize long text."""
    return text[:length] + "..."

def save_research(topic: str, findings: str) -> str:
    """Save research findings to file."""
    with open(f"{topic}_research.md", "w") as f:
        f.write(findings)
    return f"Research saved to {topic}_research.md"

agent = Agent(
    name="researcher",
    system_prompt="prompt.md",
    tools=[search_web, summarize_text, save_research],
    max_iterations=20  # More iterations for complex research
)
```

## Template Selection Guide

Choose your template based on your needs:

| Template | Best For | Key Features |
|----------|----------|--------------|
| **meta-agent** | ConnectOnion development | Documentation expert, code generation, project planning |
| **playwright** | Web automation | Stateful browser control, scraping, form automation |

## Customization Tips

1. **Tools are just functions**: Any Python function with type hints can be a tool
2. **Prompts define personality**: Use `prompt.md` to shape agent behavior
3. **max_iterations matters**: Adjust based on task complexity
4. **Embedded docs**: The `.co/docs/` folder helps agents understand ConnectOnion

## Best Practices

1. **Start simple**: Use templates as a starting point
2. **Test incrementally**: Add one tool at a time
3. **Clear docstrings**: Tool descriptions guide the LLM
4. **Type hints required**: All parameters and returns need types
5. **Error handling**: Return error messages, don't raise exceptions

## Next Steps

- Read the [CLI Documentation](cli/) to learn about `co init`
- See [Tools Documentation](concepts/tools.md) for creating custom tools
- Check [Prompts Documentation](concepts/prompts.md) for prompt engineering
- View [Examples](examples.md) for more complex agents