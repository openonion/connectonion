"""Test Agent with flexible system prompts."""

import os
import tempfile
import pytest
from pathlib import Path
from unittest.mock import Mock
from connectonion import Agent
from connectonion.prompts import DEFAULT_PROMPT


class TestAgentSystemPrompts:
    """Test Agent initialization with various system prompt formats."""
    
    def test_agent_with_default_prompt(self):
        """Test agent with no prompt specified uses default."""
        agent = Agent("test_agent", api_key="fake_key")
        assert agent.system_prompt == DEFAULT_PROMPT
        assert "helpful assistant" in agent.system_prompt
    
    def test_agent_with_string_prompt(self):
        """Test agent with direct string prompt."""
        prompt = "You are a Python expert"
        agent = Agent("test_agent", system_prompt=prompt, api_key="fake_key")
        assert agent.system_prompt == prompt
    
    def test_agent_with_file_path_string(self):
        """Test agent loading prompt from file path as string."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            content = "# AI Assistant\nYou help with coding tasks."
            f.write(content)
            temp_path = f.name
        
        try:
            agent = Agent("test_agent", system_prompt=temp_path, api_key="fake_key")
            assert agent.system_prompt == content
        finally:
            os.unlink(temp_path)
    
    def test_agent_with_path_object(self):
        """Test agent loading prompt from Path object."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            content = "You are a data analyst."
            f.write(content)
            temp_path = Path(f.name)
        
        try:
            agent = Agent("test_agent", system_prompt=temp_path, api_key="fake_key")
            assert agent.system_prompt == content
        finally:
            temp_path.unlink()
    
    def test_agent_with_custom_extension_file(self):
        """Test agent with custom file extensions."""
        extensions = ['.prompt', '.yaml', '.custom', '']  # Including no extension
        
        for ext in extensions:
            with tempfile.NamedTemporaryFile(mode='w', suffix=ext, delete=False) as f:
                content = f"Prompt for {ext or 'no'} extension"
                f.write(content)
                temp_path = f.name
            
            try:
                agent = Agent("test_agent", system_prompt=temp_path, api_key="fake_key")
                assert agent.system_prompt == content
            finally:
                os.unlink(temp_path)
    
    def test_agent_with_nonexistent_file_path_object(self):
        """Test agent with Path object to nonexistent file raises error."""
        path = Path("/nonexistent/prompt.md")
        with pytest.raises(FileNotFoundError):
            Agent("test_agent", system_prompt=path, api_key="fake_key")
    
    def test_agent_with_string_that_looks_like_path(self):
        """Test agent with string that looks like path but isn't a file."""
        # These should be treated as literal prompts
        prompts = [
            "config/assistant",
            "You are helpful with math/science",
            "prompts/template"
        ]
        
        for prompt in prompts:
            agent = Agent("test_agent", system_prompt=prompt, api_key="fake_key")
            assert agent.system_prompt == prompt
    
    def test_agent_prompt_with_tools(self):
        """Test that system prompt works correctly with tools."""
        def calculator(x: int, y: int) -> int:
            """Add two numbers."""
            return x + y
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            content = "You are a math tutor. Use tools to help with calculations."
            f.write(content)
            temp_path = f.name
        
        try:
            agent = Agent(
                "math_agent",
                system_prompt=temp_path,
                tools=[calculator],
                api_key="fake_key"
            )
            assert agent.system_prompt == content
            assert len(agent.tools) == 1
            assert agent.tools[0].name == "calculator"
        finally:
            os.unlink(temp_path)
    
    def test_agent_with_multiline_prompt_file(self):
        """Test agent with multiline prompt from file."""
        content = """# Customer Support Agent

## Your Role
You are a senior customer support specialist with 10 years of experience.

## Guidelines
- Always empathize with the customer first
- Look for the root cause of issues
- Suggest preventive measures

## Tone
Professional yet friendly and approachable."""
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write(content)
            temp_path = f.name
        
        try:
            agent = Agent("support_agent", system_prompt=temp_path, api_key="fake_key")
            assert "customer support specialist" in agent.system_prompt
            assert "empathize" in agent.system_prompt
            assert "Professional yet friendly" in agent.system_prompt
        finally:
            os.unlink(temp_path)