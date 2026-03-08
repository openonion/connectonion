# 024: Sub-Agent System Design

## Context

When building AI agents, there are often tasks that require exploration or planning but don't need the full power (and cost) of the main agent. For example:
- Finding files in a codebase
- Searching for patterns across multiple files
- Planning implementation steps
- Analyzing code structure

These tasks are repetitive, well-defined, and can be handled by cheaper, faster models. But we need a way to delegate work to specialized agents without adding complexity.

## The Problem

### Cost Problem
Using Opus-4.5 for everything is expensive:
- Input: $15 / 1M tokens
- Output: $75 / 1M tokens

Example: Finding all API endpoints in a large codebase might consume 50k tokens just for exploration. With Opus, that costs $0.75. If the main agent does this frequently, costs add up fast.

### Complexity Problem
We want to add specialized agents without:
- Writing lots of boilerplate code
- Maintaining separate Python files for each agent type
- Breaking changes when adding new agent types
- Complex registration systems

### Isolation Problem
Sub-agents should be:
- Stateless (fresh instance per call)
- Isolated (no access to parent's conversation)
- Sandboxed (limited tools, read-only when appropriate)
- Simple (no plugins, no complex features)

## Design Requirements

1. **Simple definition** - Define sub-agent in single file
2. **Auto-discovery** - No code changes to add new agent types
3. **Cost optimization** - Use cheap models for simple tasks
4. **Tool restriction** - Limit tools based on agent purpose
5. **Type safety** - Clear schema and validation
6. **Git-friendly** - Text files, easy to diff and version
7. **Self-documenting** - Config and prompt in one place
8. **Testable** - Easy to test in isolation

## Considered Alternatives

### Alternative 1: Python-based definitions

```python
# subagents/explore.py
from connectonion import Agent

def create_explore_agent():
    return Agent(
        name="explore",
        tools=[glob, grep, read_file],
        system_prompt="""
        You are an exploration agent...
        """,
        model="co/gemini-2.5-flash",
        max_iterations=15,
    )
```

**Pros:**
- Type-safe (Python types)
- IDE autocomplete
- Can import and reuse code

**Cons:**
- Requires Python knowledge
- Code changes to add new agents
- System prompt mixed with config
- Hard to share (need Python environment)
- Not self-documenting

**Rejected because:** Too much boilerplate, not friendly for non-developers.

### Alternative 2: JSON configuration

```json
{
  "name": "explore",
  "description": "Fast codebase exploration",
  "model": "co/gemini-2.5-flash",
  "max_iterations": 15,
  "tools": ["glob", "grep", "read_file"],
  "system_prompt_file": "prompts/explore.txt"
}
```

**Pros:**
- Standard format
- Easy to parse
- Type-safe with JSON schema

**Cons:**
- Config and prompt in separate files
- JSON doesn't support comments
- Not great for long text (system prompts)
- Harder to read and edit

**Rejected because:** Splits config from prompt, poor ergonomics for text.

### Alternative 3: TOML configuration

```toml
[explore]
name = "explore"
description = "Fast codebase exploration"
model = "co/gemini-2.5-flash"
max_iterations = 15
tools = ["glob", "grep", "read_file"]

[explore.system_prompt]
content = """
You are an exploration agent...
"""
```

**Pros:**
- Comments supported
- Better for configuration
- Single file possible

**Cons:**
- Less common than YAML
- Multiline strings awkward
- No syntax highlighting for prompts
- Not markdown (less readable)

**Rejected because:** Less ergonomic than YAML + markdown.

## Chosen Solution: Markdown with YAML Frontmatter

```markdown
---
name: explore
description: Fast agent for exploring codebases
model: co/gemini-2.5-flash
max_iterations: 15
tools:
  - glob
  - grep
  - read_file
read_only: true
---

# Explore Agent

You are a read-only exploration agent specialized in quickly understanding codebases.

## CRITICAL: READ-ONLY MODE

You are PROHIBITED from:
- Creating, modifying, or deleting files
...
```

### Why This Works

**1. Single File**
- Config (YAML frontmatter) + prompt (markdown body) in one place
- No need to manage separate files
- Everything version-controlled together

**2. Human-Friendly**
- Markdown is readable and familiar
- Syntax highlighting in any editor
- Easy to review in GitHub/GitLab
- Can include formatting, lists, code blocks

**3. Git-Friendly**
- Text file, easy to diff
- Meaningful changes visible in git log
- Merge conflicts easier to resolve
- Can comment on specific lines in PR reviews

**4. Auto-Discovery**
- Drop `.md` file in `subagents/` directory
- No code changes needed
- No registration required
- Just works

**5. Self-Documenting**
- Description in frontmatter
- Full instructions in markdown
- Examples can be embedded
- Guidelines included

**6. Validation**
- YAML schema defines structure
- Type safety for config
- Simple parser (no PyYAML dependency)
- Clear error messages

**7. Extensible**
- Add new fields without breaking old files
- Optional fields (e.g., `read_only: true`)
- Future: `cost_optimization`, `timeout`, etc.
- Backward compatible

## Implementation

### Data Structure

```python
@dataclass
class SubAgentDefinition:
    """Sub-agent configuration and prompt."""
    name: str               # Unique identifier
    description: str        # One-line description
    model: str             # LLM model (e.g., "co/gemini-2.5-flash")
    max_iterations: int    # Max iteration limit
    tools: List[str]       # Tool names ["glob", "grep", "read_file"]
    system_prompt: str     # Full markdown body
    read_only: bool        # Read-only flag (default: False)
    file_path: Path        # Path to .md file
```

### Loader Architecture

```python
# Simple YAML parser (no dependencies)
def parse_yaml_frontmatter(content: str) -> Tuple[Dict[str, Any], str]:
    """Parse YAML frontmatter + markdown body."""
    match = re.match(r'^---\s*\n(.*?)\n---\s*\n(.+)', content, re.DOTALL)
    frontmatter_text, markdown_body = match.groups()

    config = {}
    # Parse YAML with simple line-by-line parser
    # Handles: key: value, lists with "  - item", booleans, integers

    return config, markdown_body

# File loader
def parse_subagent_file(file_path: Path) -> SubAgentDefinition:
    """Load and parse a sub-agent definition file."""
    content = file_path.read_text(encoding="utf-8")
    config, system_prompt = parse_yaml_frontmatter(content)
    return SubAgentDefinition(**config, system_prompt=system_prompt)

# Auto-discovery
def discover_subagents(subagents_dir: Path) -> Dict[str, SubAgentDefinition]:
    """Find all .md files and load them."""
    return {
        definition.name: definition
        for file_path in subagents_dir.glob("*.md")
        if (definition := parse_subagent_file(file_path))
    }
```

### Factory Pattern

```python
def create_subagent(agent_type: str) -> Agent:
    """Create Agent instance from definition."""
    definition = get_subagent_definition(agent_type)

    return Agent(
        name=f"subagent-{definition.name}",
        tools=_resolve_tools(definition.tools),
        plugins=[],  # NO plugins for sub-agents
        system_prompt=definition.system_prompt,
        model=definition.model,
        max_iterations=definition.max_iterations,
    )
```

### Clean API

```python
def task(prompt: str, agent_type: str = "explore") -> str:
    """Delegate task to sub-agent."""
    subagent = create_subagent(agent_type)
    result = subagent.input(prompt)
    return result
```

## Cost Optimization

Sub-agents enable massive cost savings:

| Agent Type | Model | Input Cost | Output Cost | Multiplier |
|------------|-------|------------|-------------|------------|
| Main | opus-4.5 | $15/1M | $75/1M | 1x (baseline) |
| Explore | flash | $0.15/1M | $0.60/1M | **100x cheaper** |
| Plan | pro | $2.50/1M | $10/1M | **6x cheaper** |

**Real example:**
- Task: "Find all authentication files in codebase"
- Tokens: ~50k (exploration) + 10k (main agent processing)
- With Opus only: $0.75 + $0.15 = **$0.90**
- With Explore sub-agent: $0.0075 + $0.15 = **$0.16**
- **Savings: 82%**

If main agent does 20 explorations per session, savings = $14.80 per session.

## Tool Restriction Design

Sub-agents have limited tools by design:

```yaml
# Explore agent - READ ONLY
tools:
  - glob      # Find files
  - grep      # Search content
  - read_file # Read files
# NO: edit, write, bash
```

**Why:**
1. **Safety** - Read-only agents can't break things
2. **Focus** - Limited tools = clearer purpose
3. **Speed** - Fewer tools = faster LLM decisions
4. **Principle of least privilege** - Only give what's needed

System prompt enforces this:

```markdown
## CRITICAL: READ-ONLY MODE

You are PROHIBITED from:
- Creating, modifying, or deleting files
- Moving, copying, or renaming files
- Any operation that changes the filesystem

You can ONLY use: glob, grep, read_file.

This is a HARD CONSTRAINT, not a guideline.
```

## Isolation Design

Sub-agents are completely isolated from parent:

```
Main Agent State          Sub-Agent State (Fresh)
├─ messages: [...]        ├─ messages: [only this task]
├─ trace: [...]           ├─ trace: [new trace]
├─ turn: 3                ├─ turn: 1
├─ todo_list: [...]       ├─ (no todo_list)
└─ plan_mode: true        └─ (no plan_mode)

NO SHARING - Complete isolation
```

**Why:**
1. **Predictability** - Same input = same output
2. **Simplicity** - No state management
3. **Debugging** - Each sub-agent session logged separately
4. **Concurrency** - Can run multiple sub-agents in parallel

**Implementation:**
```python
def task(prompt: str, agent_type: str) -> str:
    subagent = create_subagent(agent_type)  # Fresh instance
    result = subagent.input(prompt)          # New conversation
    return result                             # String only
    # subagent discarded, garbage collected
```

## No Plugins Design

Sub-agents have NO plugins:

```python
return Agent(
    plugins=[],  # Always empty
    ...
)
```

**Why:**
1. **Simplicity** - Plugins add complexity
2. **Speed** - No plugin overhead (eval, approval, etc.)
3. **Focus** - Sub-agents are workers, not interactive agents
4. **Isolation** - Plugins might expect parent context

**Exception:** If needed in future, allow opt-in per definition:

```yaml
plugins:
  - logging  # Only if explicitly needed
```

## Extensibility

Easy to add new fields without breaking changes:

```yaml
# Current
name: explore
model: co/gemini-2.5-flash
max_iterations: 15
tools: [glob, grep, read_file]

# Future (all optional, backward compatible)
cost_optimization: true   # Flag for analytics
timeout: 30               # Max execution time
retry: 3                  # Retry failed tools
cache: true               # Cache identical prompts
examples:                 # For testing
  - prompt: "Find API endpoints"
    expected: "glob routes → grep decorators"
```

Parser handles unknown fields gracefully (ignores them).

## Testing Strategy

Easy to test in isolation:

```python
# Unit test
def test_parse_explore_definition():
    definition = parse_subagent_file("subagents/explore.md")
    assert definition.name == "explore"
    assert definition.model == "co/gemini-2.5-flash"
    assert "glob" in definition.tools

# Integration test
def test_explore_agent():
    result = task("Find all .py files", "explore")
    assert "Files Found" in result
```

## Migration Path

For existing systems with Python-based sub-agents:

1. Create .md file with equivalent config
2. Copy system prompt to markdown body
3. Test both versions work identically
4. Remove Python file
5. Update imports

**Example:**

Before (Python):
```python
# subagents/explore.py
EXPLORE_CONFIG = {
    "model": "co/gemini-2.5-flash",
    "max_iterations": 15,
}
EXPLORE_PROMPT = "You are an explorer..."
```

After (Markdown):
```markdown
---
name: explore
model: co/gemini-2.5-flash
max_iterations: 15
---

You are an explorer...
```

## Lessons Learned

1. **Markdown is underrated** - Great for configuration + documentation
2. **YAML frontmatter pattern** - Used by Jekyll, Hugo, works well
3. **Simple parser is enough** - Don't need PyYAML for this
4. **Auto-discovery >> registration** - Drop file, it works
5. **Cost optimization matters** - 100x cheaper makes huge difference
6. **Isolation simplifies** - No shared state = no bugs
7. **Read-only is powerful** - Safe to delegate exploration

## Open Questions

1. **Hot reload?** - Should we watch .md files and reload on change?
   - Answer: Not needed, just restart. Keep it simple.

2. **Validation on load?** - Should we validate all definitions on import?
   - Answer: Yes, fail fast with clear errors.

3. **Nested sub-agents?** - Can sub-agents spawn sub-agents?
   - Answer: No, keep it one level. Prevents complexity.

4. **Custom tools?** - How to let users define new tools for sub-agents?
   - Answer: Future enhancement. For now, use built-in tools only.

## Alternatives Considered But Rejected

- **Database storage** - Too complex, files are better
- **API-based registration** - Adds network dependency
- **Plugin system for sub-agents** - Defeats purpose of simplicity
- **YAML-only (no markdown)** - Poor for long prompts
- **Separate config + prompt files** - Harder to maintain

## Conclusion

Markdown with YAML frontmatter is the optimal format because:

✓ Single file (config + prompt together)
✓ Human-friendly (readable, familiar)
✓ Git-friendly (text, easy diffs)
✓ Auto-discovery (drop file, works)
✓ Self-documenting (format is obvious)
✓ Extensible (add fields without breaking)
✓ Simple (no dependencies)

This design achieves all requirements while remaining simple and maintainable.

## References

- Jekyll frontmatter: https://jekyllrb.com/docs/front-matter/
- Hugo frontmatter: https://gohugo.io/content-management/front-matter/
- Cost comparison: Claude pricing, Gemini pricing
- Sub-agent pattern: Common in multi-agent systems
