# Tool: Task

Launch specialized sub-agents for complex investigations.

## When to Use

- **Codebase exploration** - "Find all API endpoints"
- **Multi-file analysis** - "How does auth work?"
- **Architecture questions** - "What's the project structure?"
- **Complex searches** requiring multiple rounds of glob/grep

## When NOT to Use

- Simple file reads → use `read_file` instead
- Specific known file → use `read_file` instead
- Quick single search → use `glob` or `grep` directly

## Available Agents

| Agent | Purpose |
|-------|---------|
| `explore` | Fast codebase navigation and search |
| `plan` | Design implementation approach |

## Guidelines

- Use explore agent for open-ended codebase questions
- Provide clear, specific task descriptions
- Let the agent work autonomously - it has its own tools
- Trust the agent's findings

## Examples

<good-example>
# Explore codebase structure
task("explore", "Find all API endpoints and their handlers")

# Understand a feature
task("explore", "How does the authentication system work?")

# Search for patterns
task("explore", "Find all database queries and their locations")
</good-example>

<bad-example>
# Too simple - just use grep directly
task("explore", "Find class MyClass")

# Specific file - just read it
task("explore", "Read src/auth.py")
</bad-example>
