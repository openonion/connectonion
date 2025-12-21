"""Tests for ToolRegistry class."""

import pytest
from unittest.mock import Mock

from connectonion.core.tool_registry import ToolRegistry


class TestToolRegistryAdd:
    """Test adding tools to registry."""

    def test_add_tool(self):
        """Add a tool successfully."""
        registry = ToolRegistry()
        tool = Mock()
        tool.name = "search"

        registry.add(tool)

        assert registry.get("search") is tool
        assert "search" in registry.names()

    def test_add_multiple_tools(self):
        """Add multiple tools."""
        registry = ToolRegistry()
        tool1 = Mock(name="search")
        tool1.name = "search"
        tool2 = Mock(name="fetch")
        tool2.name = "fetch"

        registry.add(tool1)
        registry.add(tool2)

        assert len(registry) == 2
        assert "search" in registry.names()
        assert "fetch" in registry.names()

    def test_add_duplicate_tool_raises(self):
        """Adding duplicate tool raises ValueError."""
        registry = ToolRegistry()
        tool1 = Mock()
        tool1.name = "search"
        tool2 = Mock()
        tool2.name = "search"

        registry.add(tool1)

        with pytest.raises(ValueError, match="Duplicate tool"):
            registry.add(tool2)

    def test_add_tool_conflicts_with_instance(self):
        """Adding tool with same name as instance raises ValueError."""
        registry = ToolRegistry()
        instance = Mock()
        tool = Mock()
        tool.name = "gmail"

        registry.add_instance("gmail", instance)

        with pytest.raises(ValueError, match="conflicts with instance"):
            registry.add(tool)


class TestToolRegistryAddInstance:
    """Test adding instances to registry."""

    def test_add_instance(self):
        """Add an instance successfully."""
        registry = ToolRegistry()
        instance = Mock()

        registry.add_instance("gmail", instance)

        assert registry.get_instance("gmail") is instance

    def test_add_multiple_instances(self):
        """Add multiple instances."""
        registry = ToolRegistry()
        gmail = Mock()
        calendar = Mock()

        registry.add_instance("gmail", gmail)
        registry.add_instance("calendar", calendar)

        assert registry.get_instance("gmail") is gmail
        assert registry.get_instance("calendar") is calendar

    def test_add_duplicate_instance_raises(self):
        """Adding duplicate instance raises ValueError."""
        registry = ToolRegistry()
        instance1 = Mock()
        instance2 = Mock()

        registry.add_instance("gmail", instance1)

        with pytest.raises(ValueError, match="Duplicate instance"):
            registry.add_instance("gmail", instance2)

    def test_add_instance_conflicts_with_tool(self):
        """Adding instance with same name as tool raises ValueError."""
        registry = ToolRegistry()
        tool = Mock()
        tool.name = "search"
        instance = Mock()

        registry.add(tool)

        with pytest.raises(ValueError, match="conflicts with tool"):
            registry.add_instance("search", instance)


class TestToolRegistryGet:
    """Test getting tools and instances."""

    def test_get_existing_tool(self):
        """Get an existing tool."""
        registry = ToolRegistry()
        tool = Mock()
        tool.name = "search"
        registry.add(tool)

        result = registry.get("search")

        assert result is tool

    def test_get_nonexistent_tool_returns_none(self):
        """Get nonexistent tool returns None."""
        registry = ToolRegistry()

        result = registry.get("nonexistent")

        assert result is None

    def test_get_with_default(self):
        """Get nonexistent tool with default value."""
        registry = ToolRegistry()
        default = Mock()

        result = registry.get("nonexistent", default)

        assert result is default

    def test_get_instance_existing(self):
        """Get an existing instance."""
        registry = ToolRegistry()
        instance = Mock()
        registry.add_instance("gmail", instance)

        result = registry.get_instance("gmail")

        assert result is instance

    def test_get_instance_nonexistent(self):
        """Get nonexistent instance returns None."""
        registry = ToolRegistry()

        result = registry.get_instance("nonexistent")

        assert result is None

    def test_get_instance_with_default(self):
        """Get nonexistent instance with default value."""
        registry = ToolRegistry()
        default = Mock()

        result = registry.get_instance("nonexistent", default)

        assert result is default


class TestToolRegistryRemove:
    """Test removing tools."""

    def test_remove_existing_tool(self):
        """Remove an existing tool."""
        registry = ToolRegistry()
        tool = Mock()
        tool.name = "search"
        registry.add(tool)

        result = registry.remove("search")

        assert result is True
        assert registry.get("search") is None
        assert "search" not in registry.names()

    def test_remove_nonexistent_tool(self):
        """Remove nonexistent tool returns False."""
        registry = ToolRegistry()

        result = registry.remove("nonexistent")

        assert result is False


class TestToolRegistryNames:
    """Test listing tool names."""

    def test_names_empty(self):
        """Names of empty registry."""
        registry = ToolRegistry()

        assert registry.names() == []

    def test_names_with_tools(self):
        """Names with tools."""
        registry = ToolRegistry()
        tool1 = Mock()
        tool1.name = "search"
        tool2 = Mock()
        tool2.name = "fetch"
        registry.add(tool1)
        registry.add(tool2)

        names = registry.names()

        assert set(names) == {"search", "fetch"}

    def test_names_does_not_include_instances(self):
        """Names only includes tools, not instances."""
        registry = ToolRegistry()
        tool = Mock()
        tool.name = "search"
        registry.add(tool)
        registry.add_instance("gmail", Mock())

        names = registry.names()

        assert names == ["search"]
        assert "gmail" not in names


class TestToolRegistryAttributeAccess:
    """Test attribute access via __getattr__."""

    def test_access_tool_by_attribute(self):
        """Access tool via attribute."""
        registry = ToolRegistry()
        tool = Mock()
        tool.name = "search"
        registry.add(tool)

        result = registry.search

        assert result is tool

    def test_access_instance_by_attribute(self):
        """Access instance via attribute."""
        registry = ToolRegistry()
        instance = Mock()
        instance.my_id = "test@example.com"
        registry.add_instance("gmail", instance)

        result = registry.gmail

        assert result is instance
        assert result.my_id == "test@example.com"

    def test_instance_takes_precedence_over_tool(self):
        """If same name exists as instance and tool, instance wins."""
        # This shouldn't happen due to conflict detection, but test the priority
        registry = ToolRegistry()
        registry._instances["shared"] = "instance"
        registry._tools["shared"] = "tool"

        result = registry.shared

        assert result == "instance"

    def test_access_nonexistent_raises(self):
        """Accessing nonexistent name raises AttributeError."""
        registry = ToolRegistry()

        with pytest.raises(AttributeError, match="No tool or instance"):
            _ = registry.nonexistent

    def test_access_private_attribute_raises(self):
        """Accessing private attributes raises AttributeError."""
        registry = ToolRegistry()

        with pytest.raises(AttributeError):
            _ = registry._private


class TestToolRegistryIteration:
    """Test iteration over tools."""

    def test_iterate_empty(self):
        """Iterate over empty registry."""
        registry = ToolRegistry()

        result = list(registry)

        assert result == []

    def test_iterate_with_tools(self):
        """Iterate over tools."""
        registry = ToolRegistry()
        tool1 = Mock()
        tool1.name = "search"
        tool2 = Mock()
        tool2.name = "fetch"
        registry.add(tool1)
        registry.add(tool2)

        result = list(registry)

        assert len(result) == 2
        assert tool1 in result
        assert tool2 in result

    def test_iterate_excludes_instances(self):
        """Iteration only includes tools, not instances."""
        registry = ToolRegistry()
        tool = Mock()
        tool.name = "search"
        instance = Mock()
        registry.add(tool)
        registry.add_instance("gmail", instance)

        result = list(registry)

        assert len(result) == 1
        assert tool in result
        assert instance not in result


class TestToolRegistryLen:
    """Test length of registry."""

    def test_len_empty(self):
        """Length of empty registry."""
        registry = ToolRegistry()

        assert len(registry) == 0

    def test_len_with_tools(self):
        """Length counts tools."""
        registry = ToolRegistry()
        tool1 = Mock()
        tool1.name = "search"
        tool2 = Mock()
        tool2.name = "fetch"
        registry.add(tool1)
        registry.add(tool2)

        assert len(registry) == 2

    def test_len_excludes_instances(self):
        """Length only counts tools, not instances."""
        registry = ToolRegistry()
        tool = Mock()
        tool.name = "search"
        registry.add(tool)
        registry.add_instance("gmail", Mock())

        assert len(registry) == 1


class TestToolRegistryBool:
    """Test boolean conversion."""

    def test_bool_empty_is_false(self):
        """Empty registry is falsy."""
        registry = ToolRegistry()

        assert bool(registry) is False

    def test_bool_with_tools_is_true(self):
        """Registry with tools is truthy."""
        registry = ToolRegistry()
        tool = Mock()
        tool.name = "search"
        registry.add(tool)

        assert bool(registry) is True

    def test_bool_with_only_instances_is_false(self):
        """Registry with only instances is still falsy (no tools)."""
        registry = ToolRegistry()
        registry.add_instance("gmail", Mock())

        assert bool(registry) is False


class TestToolRegistryContains:
    """Test membership checking."""

    def test_contains_tool(self):
        """Check if tool exists."""
        registry = ToolRegistry()
        tool = Mock()
        tool.name = "search"
        registry.add(tool)

        assert "search" in registry
        assert "nonexistent" not in registry

    def test_contains_instance(self):
        """Check if instance exists."""
        registry = ToolRegistry()
        registry.add_instance("gmail", Mock())

        assert "gmail" in registry
        assert "nonexistent" not in registry

    def test_contains_both_tool_and_instance(self):
        """Check membership for both tools and instances."""
        registry = ToolRegistry()
        tool = Mock()
        tool.name = "search"
        registry.add(tool)
        registry.add_instance("gmail", Mock())

        assert "search" in registry
        assert "gmail" in registry
        assert "nonexistent" not in registry
