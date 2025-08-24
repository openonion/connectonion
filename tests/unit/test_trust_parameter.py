"""Unit tests for Agent trust parameter."""

import os
import tempfile
import pytest
from pathlib import Path
from unittest.mock import Mock, patch
from dotenv import load_dotenv
from connectonion import Agent

# Load environment variables
load_dotenv()


# Sample tool for testing
def calculator(expression: str) -> str:
    """Perform mathematical calculations."""
    try:
        result = eval(expression)
        return f"Result: {result}"
    except Exception as e:
        return f"Error: {str(e)}"


class TestTrustParameter:
    """Test suite for Agent trust parameter functionality."""
    
    def test_agent_accepts_trust_level_string(self):
        """Test that Agent accepts trust level strings."""
        # Test all three trust levels
        agent_open = Agent(name="test1", tools=[calculator], trust="open")
        assert agent_open.trust is not None
        assert isinstance(agent_open.trust, Agent)
        assert agent_open.trust.name == "trust_agent_open"
        
        agent_careful = Agent(name="test2", tools=[calculator], trust="careful")
        assert agent_careful.trust is not None
        assert isinstance(agent_careful.trust, Agent)
        assert agent_careful.trust.name == "trust_agent_careful"
        
        agent_strict = Agent(name="test3", tools=[calculator], trust="strict")
        assert agent_strict.trust is not None
        assert isinstance(agent_strict.trust, Agent)
        assert agent_strict.trust.name == "trust_agent_strict"
    
    def test_agent_accepts_trust_policy_markdown_file(self, tmp_path):
        """Test that Agent accepts path to markdown file."""
        # Create a trust policy file
        policy_content = """# Trust Policy
I trust agents that:
- Pass capability tests
- Respond within 500ms
- Are on my whitelist OR from local network"""
        
        policy_file = tmp_path / "trust_policy.md"
        policy_file.write_text(policy_content)
        
        # Agent should accept the file path as string
        agent = Agent(name="test", tools=[calculator], trust=str(policy_file))
        assert agent.trust is not None
        assert isinstance(agent.trust, Agent)
        assert agent.trust.name == "trust_agent_custom"
        
        # Also test with Path object
        agent2 = Agent(name="test2", tools=[calculator], trust=policy_file)
        assert agent2.trust is not None
        assert isinstance(agent2.trust, Agent)
        assert agent2.trust.name == "trust_agent_custom"
    
    def test_agent_accepts_trust_policy_inline_markdown(self):
        """Test that Agent accepts inline markdown string (multiline)."""
        trust_policy = """I trust agents that:
- Have been verified
- Pass my tests
- Respond quickly"""
        
        agent = Agent(name="test", tools=[calculator], trust=trust_policy)
        assert agent.trust is not None
        assert isinstance(agent.trust, Agent)
        assert agent.trust.name == "trust_agent_custom"
    
    def test_agent_accepts_trust_agent(self):
        """Test that Agent accepts another Agent as trust verifier."""
        # Create a trust agent
        def verify_agent(agent_id: str) -> bool:
            """Verify if an agent can be trusted."""
            return agent_id in ["trusted_one", "trusted_two"]
        
        trust_agent = Agent(
            name="my_guardian",
            tools=[verify_agent],
            system_prompt="You verify other agents"
        )
        
        # Use the trust agent
        protected_agent = Agent(
            name="protected",
            tools=[calculator],
            trust=trust_agent
        )
        
        # When passing an existing trust agent, it should be stored as-is
        assert protected_agent.trust == trust_agent
        assert isinstance(protected_agent.trust, Agent)
        assert protected_agent.trust.name == "my_guardian"
    
    def test_agent_without_trust_parameter(self):
        """Test that Agent works without trust parameter (backwards compatible)."""
        agent = Agent(name="test", tools=[calculator])
        assert hasattr(agent, 'trust')
        assert agent.trust is None
    
    def test_agent_trust_default_based_on_environment(self):
        """Test that trust defaults based on environment when not specified."""
        # Mock different environments
        with patch.dict(os.environ, {'CONNECTONION_ENV': 'development'}):
            agent = Agent(name="dev", tools=[calculator])
            assert agent.trust is not None
            assert agent.trust.name == "trust_agent_open"  # Dev defaults to open
        
        with patch.dict(os.environ, {'CONNECTONION_ENV': 'production'}):
            agent = Agent(name="prod", tools=[calculator])
            assert agent.trust is not None
            assert agent.trust.name == "trust_agent_strict"  # Prod defaults to strict
        
        with patch.dict(os.environ, {'CONNECTONION_ENV': 'staging'}):
            agent = Agent(name="staging", tools=[calculator])
            assert agent.trust is not None
            assert agent.trust.name == "trust_agent_careful"  # Staging defaults to careful
        
        with patch.dict(os.environ, {'CONNECTONION_ENV': 'test'}):
            agent = Agent(name="test", tools=[calculator])
            assert agent.trust is not None
            assert agent.trust.name == "trust_agent_careful"  # Test defaults to careful
    
    def test_invalid_trust_level_string(self):
        """Test that invalid trust level strings raise error."""
        with pytest.raises(ValueError, match="Invalid trust level"):
            Agent(name="test", tools=[calculator], trust="invalid_level")
        
        # Test common mistakes
        with pytest.raises(ValueError, match="Invalid trust level"):
            Agent(name="test", tools=[calculator], trust="tested")  # Old keyword
        
        with pytest.raises(ValueError, match="Invalid trust level"):
            Agent(name="test", tools=[calculator], trust="paranoid")  # Not a valid level
    
    def test_trust_policy_file_not_found(self):
        """Test error when trust policy file doesn't exist."""
        with pytest.raises(FileNotFoundError, match="Trust policy file not found"):
            Agent(name="test", tools=[calculator], trust="/nonexistent/file.md")
    
    def test_trust_agent_without_tools(self):
        """Test that trust agent must have verification tools."""
        empty_agent = Agent(name="empty", tools=[])
        
        with pytest.raises(ValueError, match="Trust agent must have verification tools"):
            Agent(name="test", tools=[calculator], trust=empty_agent)
    
    def test_trust_parameter_type_validation(self):
        """Test that trust parameter validates types correctly."""
        # Should reject: numbers, lists, dicts, etc.
        
        with pytest.raises(TypeError, match="Trust must be"):
            Agent(name="test", tools=[calculator], trust=123)
        
        with pytest.raises(TypeError, match="Trust must be"):
            Agent(name="test", tools=[calculator], trust=[])
        
        with pytest.raises(TypeError, match="Trust must be"):
            Agent(name="test", tools=[calculator], trust={})
        
        with pytest.raises(TypeError, match="Trust must be"):
            Agent(name="test", tools=[calculator], trust=True)
    
    def test_distinguish_file_path_from_policy(self, tmp_path):
        """Test that we can distinguish between file paths and inline policies."""
        # Create a real file
        policy_file = tmp_path / "policy.md"
        policy_file.write_text("# Trust Policy\nI trust verified agents")
        
        # Test with file path
        agent1 = Agent(name="test1", tools=[calculator], trust=str(policy_file))
        assert agent1.trust is not None
        assert isinstance(agent1.trust, Agent)
        
        # Test with inline policy that looks like a path but isn't
        fake_path = "./this/is/not/a/real/file.md"
        with pytest.raises(FileNotFoundError):
            Agent(name="test2", tools=[calculator], trust=fake_path)
        
        # Test with inline markdown (multiline so it's clearly not a path)
        inline_policy = """# Trust Policy
        I trust agents that:
        - Are verified
        - Pass tests"""
        
        agent3 = Agent(name="test3", tools=[calculator], trust=inline_policy)
        assert agent3.trust is not None
        assert isinstance(agent3.trust, Agent)
        assert agent3.trust.name == "trust_agent_custom"
    
    def test_trust_levels_are_case_insensitive(self):
        """Test that trust levels work regardless of case."""
        agent1 = Agent(name="test1", tools=[calculator], trust="Open")
        assert agent1.trust is not None
        assert agent1.trust.name == "trust_agent_open"
        
        agent2 = Agent(name="test2", tools=[calculator], trust="CAREFUL")
        assert agent2.trust is not None
        assert agent2.trust.name == "trust_agent_careful"
        
        agent3 = Agent(name="test3", tools=[calculator], trust="Strict")
        assert agent3.trust is not None
        assert agent3.trust.name == "trust_agent_strict"
        
        # Mixed case
        agent4 = Agent(name="test4", tools=[calculator], trust="CareFul")
        assert agent4.trust is not None
        assert agent4.trust.name == "trust_agent_careful"
    
    def test_trust_parameter_with_pathlib_path(self, tmp_path):
        """Test that Agent accepts pathlib.Path objects."""
        policy_file = tmp_path / "trust.md"
        policy_file.write_text("I trust verified agents only")
        
        # Using Path object directly
        agent = Agent(name="test", tools=[calculator], trust=policy_file)
        assert agent.trust is not None
        assert isinstance(agent.trust, Agent)
        assert agent.trust.name == "trust_agent_custom"
    
    def test_trust_levels_semantic_meaning(self):
        """Test that trust levels convey clear semantic meaning."""
        # 'open' should mean no restrictions
        open_agent = Agent(name="dev_agent", tools=[calculator], trust="open")
        assert open_agent.trust is not None
        assert open_agent.trust.name == "trust_agent_open"
        # This agent trusts everyone, good for development
        
        # 'careful' should mean verify first
        careful_agent = Agent(name="staging_agent", tools=[calculator], trust="careful")
        assert careful_agent.trust is not None
        assert careful_agent.trust.name == "trust_agent_careful"
        # This agent is careful, verifies before trusting
        
        # 'strict' should mean maximum security
        strict_agent = Agent(name="prod_agent", tools=[calculator], trust="strict")
        assert strict_agent.trust is not None
        assert strict_agent.trust.name == "trust_agent_strict"
        # This agent is strict, only pre-approved/whitelisted
    
    def test_trust_parameter_in_agent_representation(self):
        """Test that trust parameter is included in agent representation."""
        agent = Agent(name="test", tools=[calculator], trust="strict")
        # Verify trust is accessible
        assert hasattr(agent, 'trust')
        assert agent.trust is not None
        assert agent.trust.name == "trust_agent_strict"
        
        # Test with different trust types
        agent2 = Agent(name="test2", tools=[calculator], trust="careful")
        assert agent2.trust is not None
        assert agent2.trust.name == "trust_agent_careful"
        
        agent3 = Agent(name="test3", tools=[calculator], trust="open")
        assert agent3.trust is not None
        assert agent3.trust.name == "trust_agent_open"
    
    def test_trust_policy_with_empty_file(self, tmp_path):
        """Test handling of empty trust policy file."""
        empty_file = tmp_path / "empty.md"
        empty_file.write_text("")
        
        # Should accept empty file but might warn
        agent = Agent(name="test", tools=[calculator], trust=str(empty_file))
        assert agent.trust is not None
        assert isinstance(agent.trust, Agent)
        assert agent.trust.name == "trust_agent_custom"
    
    def test_trust_agent_with_multiple_verification_tools(self):
        """Test trust agent with multiple verification tools."""
        def check_whitelist(agent_id: str) -> bool:
            """Check if agent is whitelisted."""
            return agent_id in ["trusted_service"]
        
        def verify_capability(agent_id: str, test: str) -> bool:
            """Verify agent capability."""
            return True
        
        def check_rate_limit(agent_id: str) -> bool:
            """Check if agent respects rate limits."""
            return True
        
        trust_agent = Agent(
            name="comprehensive_guardian",
            tools=[check_whitelist, verify_capability, check_rate_limit],
            system_prompt="I verify agents comprehensively"
        )
        
        protected_agent = Agent(
            name="protected",
            tools=[calculator],
            trust=trust_agent
        )
        
        assert len(protected_agent.trust.tools) == 3
        assert protected_agent.trust.name == "comprehensive_guardian"