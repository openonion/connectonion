# System Prompts Collection

This directory contains example system prompts for ConnectOnion agents. These prompts define agent personalities, behaviors, and approaches to tasks.

## Directory Structure

```
prompts/
├── examples/        # Complete example prompts
├── templates/       # Reusable prompt templates
├── roles/          # Role-specific prompts
└── domains/        # Domain-specific prompts
```

## File Formats

ConnectOnion supports multiple prompt formats:
- **Markdown (.md)** - Human-readable, structured prompts
- **YAML (.yaml/.yml)** - Structured data format for complex configurations
- **JSON (.json)** - Machine-readable format with schema support
- **Plain text (.txt)** - Simple text prompts
- **No extension** - Any text file works

## Usage

### Direct String
```python
agent = Agent(
    name="helper",
    system_prompt="You are a helpful assistant.",
    tools=[...]
)
```

### Load from File
```python
# Auto-detects and loads file content
agent = Agent(
    name="expert",
    system_prompt="prompts/examples/senior_developer.md",
    tools=[...]
)
```

### Using Path Object
```python
from pathlib import Path

agent = Agent(
    name="analyst",
    system_prompt=Path("prompts/examples/data_analyst.yaml"),
    tools=[...]
)
```

## Example Prompts Included

### Markdown Examples
- `examples/customer_support.md` - Empathetic customer service agent
- `examples/senior_developer.md` - Experienced Python developer
- `templates/teaching_assistant.md` - Educational AI tutor

### YAML Examples
- `examples/data_analyst.yaml` - Data analysis expert with structured config
- `templates/code_reviewer.yaml` - Code review checklist and priorities

### JSON Examples
- `examples/product_manager.json` - Product management with decision frameworks

## Creating Your Own Prompts

### Best Practices

1. **Define Clear Role**: Start with who the agent is
2. **Specify Expertise**: List specific skills and knowledge areas
3. **Set Behavioral Guidelines**: How should the agent act?
4. **Include Examples**: Show good and bad responses
5. **Define Output Format**: Specify how responses should be structured

### Template Structure

```markdown
# [Role Title]

## Core Competencies
- [Skill 1]
- [Skill 2]

## Behavioral Guidelines
- [Guideline 1]
- [Guideline 2]

## Communication Style
- [Style preference 1]
- [Style preference 2]

## Response Format
[Describe preferred response structure]
```

## Loading Prompts Programmatically

### Dynamic Loading
```python
import os

# Select prompt based on environment
env = os.getenv("ENV", "dev")
prompt_file = f"prompts/{env}/assistant.md"

agent = Agent("assistant", system_prompt=prompt_file)
```

### Fallback Handling
```python
from pathlib import Path

def create_agent(name: str, prompt_path: str, tools: list):
    """Create agent with fallback to default prompt."""
    path = Path(prompt_path)
    
    if path.exists() and path.stat().st_size > 0:
        return Agent(name, system_prompt=path, tools=tools)
    else:
        print(f"Using default prompt (file not found: {prompt_path})")
        return Agent(name, tools=tools)
```

## Testing Your Prompts

```python
# Test prompt loading
from connectonion.prompts import load_system_prompt

prompt = load_system_prompt("prompts/examples/customer_support.md")
print(prompt[:200])  # Preview first 200 characters
```

## Contributing

Feel free to contribute your own prompt examples! When adding new prompts:

1. Use descriptive filenames
2. Include comments explaining the use case
3. Test the prompt with actual agents
4. Document any special requirements

## License

These prompt examples are provided as-is for educational and practical use with ConnectOnion.