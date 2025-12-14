"""
Purpose: Store and manage agent tools and class instances with O(1) lookup and conflict detection
LLM-Note:
  Dependencies: None (standalone module) | imported by [agent.py] | tested by [tests/unit/test_tool_registry.py]
  Data flow: Agent.__init__() creates ToolRegistry → .add(tool) stores tool with tool.name key → .add_instance(name, instance) stores class instances → .get(name) returns tool or None → __getattr__ enables agent.tools.send() attribute access → __iter__ yields tools for LLM schema generation
  State/Effects: stores tools in _tools dict and instances in _instances dict | no file I/O or external effects | raises ValueError on duplicate names or conflicts between tool/instance names
  Integration: exposes ToolRegistry class with add(), add_instance(), get(), get_instance(), remove(), names() | supports iteration (for tool in registry) | supports len() and bool | supports 'in' operator | attribute access checks instances first, then tools
  Performance: O(1) dict-based lookup for all operations | iteration yields tools only (not instances) | memory proportional to number of tools/instances
  Errors: raises ValueError for duplicate tool names | raises ValueError if tool name conflicts with instance name | raises AttributeError for unknown tool/instance names via __getattr__

Agent tools and instances with attribute access and conflict detection.

Usage:
    # Call tools
    agent.tools.send(to, subject, body)
    agent.tools.search(query)

    # Access class instances (for properties)
    agent.tools.gmail.my_id
    agent.tools.calendar.timezone

    # API
    agent.tools.add(tool)
    agent.tools.add_instance('gmail', gmail_obj)
    agent.tools.get('send')
    agent.tools.get_instance('gmail')

    # Iteration (tools only)
    for tool in agent.tools:
        print(tool.name)
"""


class ToolRegistry:
    """Agent tools and class instances with attribute access and conflict detection."""

    def __init__(self):
        self._tools = {}
        self._instances = {}

    def add(self, tool):
        """Add a tool. Raises ValueError if name conflicts with existing tool or instance."""
        name = tool.name
        if name in self._tools:
            raise ValueError(f"Duplicate tool: '{name}'")
        if name in self._instances:
            raise ValueError(f"Tool name '{name}' conflicts with instance name")
        self._tools[name] = tool

    def add_instance(self, name: str, instance):
        """Add a class instance. Raises ValueError if name conflicts."""
        if name in self._instances:
            raise ValueError(f"Duplicate instance: '{name}'")
        if name in self._tools:
            raise ValueError(f"Instance name '{name}' conflicts with tool name")
        self._instances[name] = instance

    def get(self, name, default=None):
        """Get tool by name."""
        return self._tools.get(name, default)

    def get_instance(self, name, default=None):
        """
        this will be called like agent.tools.get_instance('deep_research_agent').tools.get_instance('web')
        Get instance by name."""
        return self._instances.get(name, default)

    def remove(self, name) -> bool:
        """Remove tool by name."""
        if name in self._tools:
            del self._tools[name]
            return True
        return False

    def names(self):
        """List all tool names."""
        return list(self._tools.keys())

    def __getattr__(self, name):
        """Attribute access: agent.tools.send() or agent.tools.gmail.my_id"""
        if name.startswith('_'):
            raise AttributeError(name)
        # Check instances first (gmail, calendar)
        if name in self._instances:
            return self._instances[name]
        # Then check tools (send, reply)
        tool = self._tools.get(name)
        if tool is None:
            raise AttributeError(f"No tool or instance: '{name}'")
        return tool

    def __iter__(self):
        """Iterate over tools only (for LLM schemas)."""
        return iter(self._tools.values())

    def __len__(self):
        """Count of tools (not instances)."""
        return len(self._tools)

    def __bool__(self):
        return len(self._tools) > 0

    def __contains__(self, name):
        """Check if tool or instance exists."""
        return name in self._tools or name in self._instances