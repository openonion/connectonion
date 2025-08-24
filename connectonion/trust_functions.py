"""Trust verification functions for ConnectOnion trust agents.

These functions are tools that trust agents can use to verify other agents.
They return strings that describe what they're checking, which the AI agent
then interprets according to its trust policy.
"""

from pathlib import Path
from typing import List, Callable


def check_whitelist(agent_id: str) -> str:
    """
    Check if an agent is on the whitelist.
    
    Args:
        agent_id: Identifier of the agent to check
        
    Returns:
        String indicating if agent is whitelisted or not
    """
    whitelist_path = Path.home() / ".connectonion" / "trusted.txt"
    if whitelist_path.exists():
        try:
            whitelist = whitelist_path.read_text()
            lines = whitelist.strip().split('\n')
            for line in lines:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                if line == agent_id:
                    return f"{agent_id} is on the whitelist"
                # Simple wildcard support
                if '*' in line:
                    pattern = line.replace('*', '')
                    if pattern in agent_id:
                        return f"{agent_id} matches whitelist pattern: {line}"
            return f"{agent_id} is NOT on the whitelist"
        except Exception as e:
            return f"Error reading whitelist: {e}"
    return "No whitelist file found at ~/.connectonion/trusted.txt"


def test_capability(agent_id: str, test: str, expected: str) -> str:
    """
    Test an agent's capability with a specific test.
    
    Args:
        agent_id: Identifier of the agent to test
        test: The test to perform
        expected: The expected result
        
    Returns:
        Test description for the trust agent to evaluate
    """
    return f"Testing {agent_id} with: {test}, expecting: {expected}"


def verify_agent(agent_id: str, agent_info: str = "") -> str:
    """
    General verification of an agent.
    
    Args:
        agent_id: Identifier of the agent
        agent_info: Additional information about the agent
        
    Returns:
        Verification context for the trust agent
    """
    return f"Verifying agent: {agent_id}. Info: {agent_info}"


def get_trust_verification_tools() -> List[Callable]:
    """
    Get the list of trust verification tools.
    
    Returns:
        List of trust verification functions
    """
    return [
        check_whitelist,
        test_capability,
        verify_agent
    ]