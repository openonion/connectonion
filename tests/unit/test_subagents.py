"""
Unit tests for subagents plugin
"""

import pytest
from pathlib import Path
from connectonion import Agent
from connectonion.useful_plugins import subagents, task
from connectonion.useful_plugins.subagents import (
    _discover_all_agents,
    _load_agent,
    _parse_agent_content,
    _get_agent_paths,
)


class TestSubagentsPlugin:
    """Test subagents plugin functionality"""

    def test_plugin_initialization(self):
        """Test that on_agent_ready event registers task() tool and modifies system_prompt"""
        agent = Agent(
            name="test-agent",
            tools=[],
            plugins=[subagents],
            model="co/gemini-2.5-flash",
            quiet=True
        )

        # Verify task tool was registered
        assert 'task' in agent.tools._tools, "task() tool should be registered"

        # Verify system prompt was modified
        assert 'Available Sub-Agents' in agent.system_prompt
        assert 'explore' in agent.system_prompt
        assert 'plan' in agent.system_prompt

    def test_agent_discovery(self):
        """Test that builtin agents are discovered"""
        agents = _discover_all_agents()
        agent_names = [a['name'] for a in agents]

        assert 'explore' in agent_names, "explore agent should be discovered"
        assert 'plan' in agent_names, "plan agent should be discovered"
        assert len(agents) >= 2, "Should discover at least 2 builtin agents"

        # Verify structure
        for agent in agents:
            assert 'name' in agent
            assert 'description' in agent
            assert 'location' in agent

    def test_load_explore_agent(self):
        """Test loading explore agent configuration"""
        config = _load_agent('explore')

        assert config is not None, "explore agent should be loadable"
        assert 'frontmatter' in config
        assert 'system_prompt' in config

        # Verify frontmatter
        fm = config['frontmatter']
        assert fm['name'] == 'explore'
        assert fm['model'] == 'co/gemini-2.5-pro'
        assert fm['max_iterations'] == 15
        assert 'glob' in fm['tools']
        assert 'grep' in fm['tools']
        assert 'read_file' in fm['tools']

        # Verify system prompt
        assert len(config['system_prompt']) > 0
        assert 'explore agent' in config['system_prompt'].lower()

    def test_load_plan_agent(self):
        """Test loading plan agent configuration"""
        config = _load_agent('plan')

        assert config is not None, "plan agent should be loadable"

        # Verify frontmatter
        fm = config['frontmatter']
        assert fm['name'] == 'plan'
        assert fm['model'] == 'co/gemini-2.5-pro'
        assert fm['max_iterations'] == 10
        assert 'glob' in fm['tools']
        assert 'grep' in fm['tools']
        assert 'read_file' in fm['tools']

    def test_load_nonexistent_agent(self):
        """Test loading agent that doesn't exist returns None"""
        config = _load_agent('nonexistent-agent-xyz')
        assert config is None

    def test_parse_agent_content(self):
        """Test parsing AGENT.md content with YAML frontmatter"""
        content = """---
name: test
description: Test agent
model: co/gemini-2.5-flash
max_iterations: 5
tools:
  - glob
  - grep
---

This is the system prompt.
With multiple lines.
"""
        frontmatter, system_prompt = _parse_agent_content(content)

        assert frontmatter['name'] == 'test'
        assert frontmatter['description'] == 'Test agent'
        assert frontmatter['model'] == 'co/gemini-2.5-flash'
        assert frontmatter['max_iterations'] == 5
        assert frontmatter['tools'] == ['glob', 'grep']

        assert system_prompt == "This is the system prompt.\nWith multiple lines."

    def test_parse_agent_content_no_frontmatter(self):
        """Test parsing content without frontmatter"""
        content = "Just a plain system prompt"
        frontmatter, system_prompt = _parse_agent_content(content)

        assert frontmatter == {}
        assert system_prompt == "Just a plain system prompt"

    def test_get_agent_paths_priority(self):
        """Test that agent paths are returned in correct priority order"""
        paths = _get_agent_paths('test-agent')

        assert len(paths) == 3
        # Priority: project > user > builtin
        assert '.co/agents/test-agent/AGENT.md' in str(paths[0])
        assert str(paths[0]).startswith(str(Path.cwd()))

        assert '.co/agents/test-agent/AGENT.md' in str(paths[1])
        assert str(paths[1]).startswith(str(Path.home()))

        assert 'builtin_agents/test-agent/AGENT.md' in str(paths[2])

    def test_task_invalid_agent_type(self):
        """Test task() returns helpful error for invalid agent type"""
        agent = Agent(
            name="test-agent",
            tools=[],
            plugins=[subagents],
            model="co/gemini-2.5-flash",
            quiet=True
        )

        result = task(agent, "test prompt", "invalid-agent-type")

        assert "not found" in result.lower()
        assert "explore" in result  # Should list available agents
        assert "plan" in result

    def test_tool_map_includes_browser(self):
        """Test that Browser tool is in the tool map"""
        from connectonion.useful_plugins.subagents import _resolve_tools

        # Create agent config that requests Browser tool
        tool_names = ['Browser', 'glob']
        tools = _resolve_tools(tool_names, 'test')

        # Should resolve 2 tools
        assert len(tools) == 2

        # First tool should be BrowserAutomation instance
        from connectonion.useful_tools.browser_tools import BrowserAutomation
        assert isinstance(tools[0], BrowserAutomation)

    def test_subagents_export(self):
        """Test that subagents and task are properly exported"""
        # Should be importable from useful_plugins
        from connectonion.useful_plugins import subagents, task

        assert subagents is not None
        assert task is not None
        assert callable(task)
        assert isinstance(subagents, list)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
