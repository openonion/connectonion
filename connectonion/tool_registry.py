"""
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
        """Get instance by name."""
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