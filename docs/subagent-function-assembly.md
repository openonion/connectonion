# Sub-Agent Function Assembly

## How Tool Functions Are Assembled into Agent

This document explains how tool names in YAML (`["glob", "grep", "read_file"]`) become actual callable functions in the Agent.

## Complete Assembly Flow

```
┌─────────────────────────────────────────────────────────────────┐
│ Step 1: YAML Definition (explore.md)                            │
└─────────────────────────────────────────────────────────────────┘
---
name: explore
tools:
  - glob         # ← String name
  - grep         # ← String name
  - read_file    # ← String name
read_only: true  # ← Permission flag
---
                ↓
┌─────────────────────────────────────────────────────────────────┐
│ Step 2: Loader Parses YAML (loader.py)                          │
└─────────────────────────────────────────────────────────────────┘
SubAgentDefinition(
    name="explore",
    tools=["glob", "grep", "read_file"],  # List[str]
    read_only=True,                       # bool
    ...
)
                ↓
┌─────────────────────────────────────────────────────────────────┐
│ Step 3: Factory Resolves Tools (factory.py)                     │
└─────────────────────────────────────────────────────────────────┘
Line 58: tools = _resolve_tools(
    definition.tools,              # ["glob", "grep", "read_file"]
    read_only=definition.read_only # True
)
                ↓
┌─────────────────────────────────────────────────────────────────┐
│ Step 4: _resolve_tools() Creates FileTools Instance             │
└─────────────────────────────────────────────────────────────────┘
def _resolve_tools(tool_names: List[str], read_only: bool):
    from connectonion.useful_tools.file_tools import FileTools

    if read_only:
        return [FileTools(permission="read")]   # Read-only mode
    else:
        return [FileTools(permission="write")]  # Full access

Result: [FileTools(permission="read")]
                ↓
┌─────────────────────────────────────────────────────────────────┐
│ Step 5: FileTools Instance Structure                            │
└─────────────────────────────────────────────────────────────────┘
class FileTools:
    def __init__(self, permission="write"):
        self._permission = permission  # "read" or "write"
        self._snapshots = {}           # Track read files

    # Always available
    def read_file(self, path, offset, limit): ...
    def glob(self, pattern, path): ...
    def grep(self, pattern, path, ...): ...

    # Blocked if permission="read"
    def edit(self, file_path, old_string, new_string):
        if self._permission == "read":
            return "Error: Permission denied - read-only mode"
        ...

    def write(self, file_path, content):
        if self._permission == "read":
            return "Error: Permission denied - read-only mode"
        ...

FileTools(permission="read") instance created ✓
                ↓
┌─────────────────────────────────────────────────────────────────┐
│ Step 6: Agent Constructor (core/agent.py)                       │
└─────────────────────────────────────────────────────────────────┘
Agent(
    name="subagent-explore",
    tools=[FileTools(permission="read")],  # ← Class instance
    plugins=[],
    system_prompt="# Explore Agent...",
    model="co/gemini-2.5-flash",
    max_iterations=15
)
                ↓
┌─────────────────────────────────────────────────────────────────┐
│ Step 7: Agent.__init__ Processes Tools (core/agent.py:104-125)  │
└─────────────────────────────────────────────────────────────────┘
Line 105: self.tools = ToolRegistry()

Line 107: tools_list = [FileTools(permission="read")]

Line 110-124: for tool in tools_list:
    if is_class_instance(tool):  # ✓ FileTools is instance
        # Store instance reference
        class_name = "filetools"
        self.tools.add_instance("filetools", tool)

        # Extract methods as individual tools
        for method_tool in extract_methods_from_instance(tool):
            self.tools.add(method_tool)
                ↓
┌─────────────────────────────────────────────────────────────────┐
│ Step 8: extract_methods_from_instance() (core/tool_factory.py)  │
└─────────────────────────────────────────────────────────────────┘
def extract_methods_from_instance(instance):
    """Extract all public methods from class instance."""
    tools = []

    for attr_name in dir(instance):  # Get all attributes
        if attr_name.startswith('_'):  # Skip private
            continue

        attr = getattr(instance, attr_name)
        if callable(attr):  # Is it a method?
            tool = create_tool_from_function(attr)
            tools.append(tool)

    return tools

For FileTools(permission="read"), extracts:
  ✓ read_file → Tool
  ✓ glob → Tool
  ✓ grep → Tool
  ✓ edit → Tool (will error at runtime)
  ✓ write → Tool (will error at runtime)
  ✓ multi_edit → Tool (will error at runtime)
                ↓
┌─────────────────────────────────────────────────────────────────┐
│ Step 9: create_tool_from_function() Wraps Methods               │
└─────────────────────────────────────────────────────────────────┘
For each method (e.g., read_file):

1. Extract function signature:
   def read_file(self, path: str, offset: int, limit: int) -> str

2. Generate OpenAI function schema:
   {
     "type": "function",
     "function": {
       "name": "read_file",
       "description": "Read and return file contents with line numbers",
       "parameters": {
         "type": "object",
         "properties": {
           "path": {"type": "string", "description": "Path to file"},
           "offset": {"type": "integer", "description": "Line to start"},
           "limit": {"type": "integer", "description": "Lines to read"}
         },
         "required": ["path"]
       }
     }
   }

3. Wrap in Tool class:
   Tool(
     name="read_file",
     func=<bound method FileTools.read_file>,
     schema=<OpenAI schema>,
     description="Read and return file contents..."
   )
                ↓
┌─────────────────────────────────────────────────────────────────┐
│ Step 10: ToolRegistry Populated                                 │
└─────────────────────────────────────────────────────────────────┘
agent.tools = ToolRegistry {
    # Tool lookup
    "read_file": Tool(func=FileTools.read_file, schema=...),
    "glob": Tool(func=FileTools.glob, schema=...),
    "grep": Tool(func=FileTools.grep, schema=...),
    "edit": Tool(func=FileTools.edit, schema=...),
    "write": Tool(func=FileTools.write, schema=...),
    "multi_edit": Tool(func=FileTools.multi_edit, schema=...),

    # Instance storage
    instances: {
        "filetools": FileTools(permission="read")
    }
}

Access patterns:
  agent.tools.get("read_file")       # → Tool object
  agent.tools.read_file              # → Tool object (attribute access)
  agent.tools.filetools              # → FileTools instance
                ↓
┌─────────────────────────────────────────────────────────────────┐
│ Step 11: Runtime - Agent Uses Tools                             │
└─────────────────────────────────────────────────────────────────┘
Agent.input("Find all auth files")
    ↓
LLM generates tool_calls:
    [
      {"name": "glob", "arguments": {"pattern": "**/*auth*"}},
      {"name": "grep", "arguments": {"pattern": "login|jwt"}},
      {"name": "read_file", "arguments": {"path": "src/auth.py"}}
    ]
    ↓
Tool Executor:
    for tool_call in tool_calls:
        tool_name = tool_call["name"]  # "glob"
        tool = agent.tools.get(tool_name)  # Tool object
        result = tool.func(**tool_call["arguments"])
        # Calls: FileTools.glob(pattern="**/*auth*")

    Results returned to LLM for next iteration
```

## Why Use FileTools Class Instead of Individual Functions?

### Option 1: Individual Functions (NOT used)
```python
from connectonion import glob, grep, read_file

def glob(pattern: str, path: str = None) -> str:
    """Search for files."""
    ...

def grep(pattern: str, path: str = None) -> str:
    """Search content."""
    ...

def read_file(path: str) -> str:
    """Read file."""
    ...

# Agent
Agent(tools=[glob, grep, read_file])
```

**Problems:**
- ❌ No shared state (can't track which files were read)
- ❌ Can't enforce permissions (each function independent)
- ❌ No read-before-edit validation

### Option 2: FileTools Class (USED)
```python
class FileTools:
    def __init__(self, permission="write"):
        self._permission = permission
        self._snapshots = {}  # Shared state

    def read_file(self, path):
        result = _read_file(path)
        self._snapshots[path] = hash(content)  # Track
        return result

    def edit(self, path, old, new):
        if self._permission == "read":
            return "Error: read-only"  # Enforce permission
        if path not in self._snapshots:
            return "Error: read file first"  # Validate
        ...

# Agent
Agent(tools=[FileTools(permission="read")])
```

**Benefits:**
- ✓ Shared state across methods (tracks read files)
- ✓ Permission enforcement (one flag controls all)
- ✓ Read-before-edit validation (stale-read protection)
- ✓ Bundled operations (all file tools together)

## Read-Only Permission Enforcement

```
FileTools(permission="read")
    ↓
Agent calls edit tool
    ↓
def edit(self, file_path, old_string, new_string):
    if self._permission == "read":  # ← Check permission
        return "Error: Permission denied - FileTools is in read-only mode"
    ...
    ↓
Returns error to LLM
    ↓
LLM sees error and tries different approach
```

## Example: Sub-Agent Execution with Tools

```python
# User code
result = task("Find all authentication files", "explore")

# Internal execution
┌─────────────────────────────────────────────────────────────┐
│ 1. create_subagent("explore")                               │
│    → FileTools(permission="read")                           │
│    → Agent(tools=[FileTools])                               │
└─────────────────────────────────────────────────────────────┘
        ↓
┌─────────────────────────────────────────────────────────────┐
│ 2. Agent.input("Find all authentication files")            │
└─────────────────────────────────────────────────────────────┘
        ↓
┌─────────────────────────────────────────────────────────────┐
│ 3. Iteration 1: LLM Response                                │
│    Tool calls: [                                            │
│      {"name": "glob", "arguments": {"pattern": "**/*auth*"}}│
│    ]                                                        │
└─────────────────────────────────────────────────────────────┘
        ↓
┌─────────────────────────────────────────────────────────────┐
│ 4. Execute Tool                                             │
│    tool = agent.tools.get("glob")                           │
│    result = tool.func(pattern="**/*auth*")                  │
│    → Calls FileTools.glob("**/*auth*")                      │
│    → Returns ["src/auth.py", "middleware/auth.py", ...]     │
└─────────────────────────────────────────────────────────────┘
        ↓
┌─────────────────────────────────────────────────────────────┐
│ 5. Iteration 2: LLM sees glob results                       │
│    Tool calls: [                                            │
│      {"name": "grep", "arguments": {                        │
│         "pattern": "login|session|jwt",                     │
│         "path": "src"                                       │
│      }}                                                     │
│    ]                                                        │
└─────────────────────────────────────────────────────────────┘
        ↓
┌─────────────────────────────────────────────────────────────┐
│ 6. Execute Tool                                             │
│    tool = agent.tools.get("grep")                           │
│    result = tool.func(pattern="login|session|jwt", ...)     │
│    → Calls FileTools.grep(...)                              │
│    → Returns matches from files                             │
└─────────────────────────────────────────────────────────────┘
        ↓
┌─────────────────────────────────────────────────────────────┐
│ 7. Iteration 3: LLM reads key file                          │
│    Tool calls: [                                            │
│      {"name": "read_file", "arguments": {                   │
│         "path": "src/auth.py"                               │
│      }}                                                     │
│    ]                                                        │
└─────────────────────────────────────────────────────────────┘
        ↓
┌─────────────────────────────────────────────────────────────┐
│ 8. Execute Tool                                             │
│    tool = agent.tools.get("read_file")                      │
│    result = tool.func(path="src/auth.py")                   │
│    → Calls FileTools.read_file("src/auth.py")               │
│    → Tracks in _snapshots["src/auth.py"] = hash             │
│    → Returns file content with line numbers                 │
└─────────────────────────────────────────────────────────────┘
        ↓
┌─────────────────────────────────────────────────────────────┐
│ 9. Iteration 4: LLM finalizes (no tools)                    │
│    Returns structured findings:                             │
│    "## Files Found                                          │
│     - src/auth.py - JWT authentication                      │
│     - middleware/auth.py - Auth middleware                  │
│     ..."                                                    │
└─────────────────────────────────────────────────────────────┘
```

## Summary: YAML String → Callable Function

```
YAML:              tools: ["glob"]
                      ↓
Loader:            SubAgentDefinition(tools=["glob"])
                      ↓
Factory:           _resolve_tools(["glob"], read_only=True)
                      ↓
                   FileTools(permission="read")
                      ↓
Agent.__init__:    extract_methods_from_instance()
                      ↓
                   Tool(name="glob", func=FileTools.glob, schema=...)
                      ↓
ToolRegistry:      agent.tools["glob"] = Tool(...)
                      ↓
Runtime:           LLM → tool_call{"name": "glob"}
                      ↓
                   tool = agent.tools.get("glob")
                      ↓
                   result = tool.func(pattern="...")
                      ↓
                   FileTools.glob(pattern="...") executes
```

**Key transformation:**
String `"glob"` → `FileTools` class → Method extraction → Tool wrapper → Executable function

This design is **clean, type-safe, and maintainable**.
