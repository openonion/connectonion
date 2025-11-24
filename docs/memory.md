# Memory System

Give your agents persistent memory using markdown-based storage.

## Quick Start

```python
from connectonion import Agent, Memory

memory = Memory()
agent = Agent(
    name="assistant",
    system_prompt="You are a helpful assistant with memory.",
    tools=[memory]
)

# Agent can now remember things
agent.input("Remember that Alice prefers email communication")
agent.input("What do I know about Alice?")
```

## What is Memory?

Memory is a simple, file-based storage system that lets your agents:
- Save information persistently across sessions
- Retrieve information by key
- Search across all memories with regex
- Organize knowledge in markdown format

**Storage**: Memories start in a single `memory.md` file. When the file exceeds 3000 lines, it automatically splits into a directory structure with separate `.md` files per memory key.

## Installation

Memory is included in ConnectOnion:

```bash
pip install connectonion
```

## Basic Usage

### Creating a Memory Instance

```python
from connectonion import Memory

# Default (creates memory.md)
memory = Memory()

# Custom file path
memory = Memory(memory_file="agent_knowledge.md")

# Legacy: directory structure (creates directory immediately)
memory = Memory(memory_dir="agent_knowledge")
```

### Adding Memory to an Agent

```python
from connectonion import Agent, Memory

memory = Memory()
agent = Agent("assistant", tools=[memory])
```

Now your agent has access to 4 memory methods:
- `write_memory(key, content)` - Save or update information
- `read_memory(key)` - Retrieve information
- `list_memories()` - Show all stored memories
- `search_memory(pattern)` - Search with regex

## Memory Methods

### write_memory

Save information to memory:

```python
memory.write_memory("alice-notes", "Alice prefers email\nAlice works at TechCorp")
# Returns: "Memory saved: alice-notes"
```

**Keys are sanitized:**
- Only alphanumeric, hyphens, and underscores allowed
- Converted to lowercase
- `"Alice Notes!"` becomes `"alicenotes"`

### read_memory

Retrieve saved information:

```python
memory.read_memory("alice-notes")
# Returns:
# Memory: alice-notes
#
# Alice prefers email
# Alice works at TechCorp
```

If not found:
```python
memory.read_memory("unknown")
# Returns: "Memory not found: unknown\nAvailable memories: alice-notes, project-x"
```

### list_memories

Show all stored memories:

```python
memory.list_memories()
# Returns:
# Stored Memories (3):
# 1. alice-notes (85 bytes)
# 2. bob-notes (62 bytes)
# 3. project-x (120 bytes)
```

### search_memory

Search across all memories using regex:

```python
# Simple text search (case-sensitive by default)
memory.search_memory("email")
# Returns:
# Search Results (2 matches):
#
# alice-notes:
#   Line 1: Alice prefers email
#
# contacts:
#   Line 3: Email: alice@example.com

# Case-insensitive search with (?i) flag
memory.search_memory("(?i)email")

# Regex patterns
memory.search_memory(r"\w+@\w+\.\w+")  # Find email addresses
memory.search_memory(r"Project [A-Z]")  # Find project names
```

## Examples

### Example 1: Customer Notes

```python
from connectonion import Agent, Memory

memory = Memory(memory_dir="customer_notes")
agent = Agent(
    name="sales-assistant",
    system_prompt="You help track customer information.",
    tools=[memory]
)

# Save customer info
agent.input("Remember that Alice from TechCorp is interested in our API product and prefers email contact")

# Later, recall the information
agent.input("What do I know about Alice?")
# Agent will use read_memory() to retrieve Alice's info
```

### Example 2: Project Tracker

```python
from connectonion import Agent, Memory

memory = Memory(memory_dir="projects")
agent = Agent(
    name="project-manager",
    system_prompt="You track project status and notes.",
    tools=[memory]
)

# Save project updates
agent.input("Remember: Project Alpha is 80% complete, needs final testing")
agent.input("Remember: Project Beta is blocked, waiting on API keys")

# Search for blocked projects
agent.input("Which projects are blocked?")
# Agent will use search_memory("blocked") to find relevant projects
```

### Example 3: Research Assistant

```python
from connectonion import Agent, Memory

def web_search(query: str) -> str:
    """Search the web for information."""
    # Your search implementation
    return f"Results for {query}"

memory = Memory(memory_dir="research")
agent = Agent(
    name="researcher",
    system_prompt="You research topics and save key findings.",
    tools=[web_search, memory]
)

# Research and save
agent.input("Research the history of Python programming and save key points")
# Agent will search, then use write_memory() to save findings

# Later, recall research
agent.input("What did I learn about Python's history?")
```

### Example 4: Multi-Agent Shared Memory

```python
from connectonion import Agent, Memory

# Shared memory between agents
shared_memory = Memory(memory_dir="shared_knowledge")

researcher = Agent(
    name="researcher",
    system_prompt="You research and document findings.",
    tools=[shared_memory]
)

writer = Agent(
    name="writer",
    system_prompt="You write articles based on research.",
    tools=[shared_memory]
)

# Researcher saves findings
researcher.input("Research AI trends and save the findings")

# Writer uses the same memory
writer.input("Write an article based on AI trends research")
```

## Advanced Patterns

### Memory with Different Tools

Memory works alongside any other tools:

```python
from connectonion import Agent, Memory

def calculate(expression: str) -> float:
    """Calculate math expressions."""
    return eval(expression)

def send_email(to: str, subject: str, body: str) -> str:
    """Send an email."""
    # Implementation
    return "Email sent"

memory = Memory()

agent = Agent(
    name="multi-tool-agent",
    tools=[calculate, send_email, memory]
)
```

### Custom Memory File Organization

Organize memories by category:

```python
# Separate memory files for different purposes
customer_memory = Memory(memory_file="data/customers.md")
project_memory = Memory(memory_file="data/projects.md")
research_memory = Memory(memory_file="data/research.md")

agent = Agent(
    name="organized-agent",
    tools=[customer_memory, project_memory, research_memory]
)
```

### Regex Search Patterns

Powerful search with regex:

```python
# Find email addresses
memory.search_memory(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")

# Find phone numbers
memory.search_memory(r"\d{3}-\d{3}-\d{4}")

# Find dates
memory.search_memory(r"\d{4}-\d{2}-\d{2}")

# Find URLs
memory.search_memory(r"https?://[^\s]+")

# Find specific keywords (word boundaries, case-insensitive)
memory.search_memory(r"(?i)\bproject\b")
```

## File Format

### Single File (Default)

Memories start in a single `memory.md` file using section headers:

```markdown
## alice-notes

Alice prefers email communication
Works at TechCorp
Interested in API product
Last contact: 2025-11-20

## bob-notes

Bob from Marketing
Prefers phone calls

## project-x

Project X is 80% complete
Needs final testing
```

### Auto-Split to Directory

When `memory.md` exceeds 3000 lines, it automatically migrates to a directory structure:

```
memory/
├── alice-notes.md
├── bob-notes.md
└── project-x.md
```

Each file contains plain text/markdown content (without the `##` header).

**Benefits of this approach:**
- Simple by default (one file)
- Scales automatically when needed
- Human-readable
- Version control friendly (git)
- Easy to edit manually if needed
- Supports rich formatting

## Best Practices

### 1. Use Descriptive Keys

```python
# Good
memory.write_memory("alice-techcorp-contact-info", content)
memory.write_memory("project-alpha-status", content)

# Bad
memory.write_memory("note1", content)
memory.write_memory("data", content)
```

### 2. Structure Your Content

```python
# Use markdown formatting for better organization
content = """# Alice - TechCorp

## Contact Info
- Email: alice@techcorp.com
- Prefers: Email over phone

## Projects
- Interested in API product
- Budget: $50k

## Notes
- Decision maker
- Wants demo next week
"""

memory.write_memory("alice-techcorp", content)
```

### 3. Keep Memories Updated

```python
# Update or overwrite outdated memories
agent.input("Review and update any memories older than 6 months")
```

### 4. Search Before Creating

```python
# Check if similar memory exists
agent.input("Do we have any notes about Alice?")
# Agent will search before creating duplicate memory
```

### 5. Use Consistent Naming

```python
# Choose a naming convention and stick to it
memory.write_memory("customer-alice-techcorp", ...)
memory.write_memory("customer-bob-acmecorp", ...)
memory.write_memory("project-alpha", ...)
memory.write_memory("project-beta", ...)
```

## Limitations

### Storage

- All memories are kept in memory during search operations
- For very large memory stores (>1000 files or >100MB), consider database alternatives
- No built-in memory limits - monitor disk usage

### Concurrency

- File-based storage is not optimized for high-concurrency scenarios
- Multiple agents writing to the same memory simultaneously may cause race conditions
- For production multi-agent systems, consider database-backed storage

### Search Performance

- Regex search scans all files linearly
- Performance degrades with more memories
- For large-scale search needs, consider full-text search solutions (Elasticsearch, etc.)

## Troubleshooting

### "Memory not found"

Check available memories:
```python
print(memory.list_memories())
```

Remember that keys are sanitized (lowercase, alphanumeric + hyphens/underscores).

### "Invalid key name"

Use only alphanumeric characters, hyphens, and underscores:
```python
# Good
memory.write_memory("alice-notes", content)

# Bad (will be rejected or sanitized)
memory.write_memory("alice@notes!", content)
```

### Memory file not created

Memory creates the file automatically on first write:
```python
import os
memory = Memory()
memory.write_memory("test", "content")
print(os.path.exists("memory.md"))  # Should be True
```

## Next Steps

- See [Examples](../examples/memory_agent.py) for complete working code
- Learn about [Plugins](./plugin.md) for automatic memory behaviors
- Explore [Multi-Agent Systems](./multi-agent.md) with shared memory

## Related Documentation

- [Agent Basics](./agent.md)
- [Tools](./tools.md)
- [Plugins](./plugin.md)
