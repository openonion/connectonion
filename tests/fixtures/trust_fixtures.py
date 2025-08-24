"""Fixtures for trust-related tests."""

import pytest
import tempfile
from pathlib import Path
from connectonion import Agent


@pytest.fixture
def trust_policy_file(tmp_path):
    """Create a temporary trust policy file."""
    policy_file = tmp_path / "trust_policy.md"
    policy_file.write_text("""# Trust Policy

I trust agents that:
- Pass my verification tests
- Respond within 500ms
- Are from trusted domains

I do not trust agents that:
- Fail capability tests
- Take longer than 5 seconds
- Are on my blacklist
""")
    return str(policy_file)


@pytest.fixture
def trust_policy_files(tmp_path):
    """Create multiple trust policy files for different scenarios."""
    policies = {}
    
    # Open policy
    open_policy = tmp_path / "open_policy.md"
    open_policy.write_text("""# Open Trust Policy
I trust all agents without verification.
This is suitable for development environments.""")
    policies['open'] = str(open_policy)
    
    # Careful policy
    careful_policy = tmp_path / "careful_policy.md"
    careful_policy.write_text("""# Careful Trust Policy
I trust agents that:
- Pass basic capability tests
- Demonstrate consistent behavior
- Respond in reasonable time

I verify each agent before first use.""")
    policies['careful'] = str(careful_policy)
    
    # Strict policy
    strict_policy = tmp_path / "strict_policy.md"
    strict_policy.write_text("""# Strict Trust Policy
I only trust agents that:
- Are explicitly whitelisted
- Pass comprehensive security checks
- Have valid credentials
- Come from approved domains

All others are rejected.""")
    policies['strict'] = str(strict_policy)
    
    return policies


@pytest.fixture
def mock_trust_agent():
    """Create a mock trust agent for testing."""
    def verify_agent(agent_id: str) -> bool:
        """Verify if an agent can be trusted."""
        # Mock verification - trusts specific test agents
        return agent_id in ["trusted_one", "trusted_two", "test_agent"]
    
    def check_capability(agent_id: str, test: str, expected: str) -> bool:
        """Check agent capability with a test."""
        # Mock capability check
        return True
    
    return Agent(
        name="mock_guardian",
        tools=[verify_agent, check_capability],
        system_prompt="I am a mock trust guardian for testing"
    )


@pytest.fixture
def strict_trust_agent():
    """Create a strict trust agent that only trusts whitelisted agents."""
    def check_whitelist(agent_id: str) -> bool:
        """Check if agent is on the whitelist."""
        whitelist = ["production_service", "verified_api", "trusted_partner"]
        return agent_id in whitelist
    
    def verify_credentials(agent_id: str, credentials: dict) -> bool:
        """Verify agent credentials."""
        # Mock credential verification
        return credentials.get("api_key", "").startswith("valid_")
    
    def check_domain(agent_id: str, domain: str) -> bool:
        """Check if agent is from approved domain."""
        approved_domains = ["*.trusted.com", "*.company.internal", "localhost"]
        # Simplified domain check for testing
        return any(domain.endswith(d.replace("*.", "")) for d in approved_domains)
    
    return Agent(
        name="strict_guardian",
        tools=[check_whitelist, verify_credentials, check_domain],
        system_prompt="I am a strict trust guardian. I only trust pre-approved agents.",
        trust="open"  # The guardian itself is open (doesn't need trust to operate)
    )


@pytest.fixture
def sample_trust_policies():
    """Sample trust policies for testing."""
    return {
        "simple_open": "I trust everyone",
        "simple_careful": "I verify agents before trusting them",
        "simple_strict": "I only trust whitelisted agents",
        "detailed_careful": """# Careful Trust Policy
I trust agents that:
- Pass my capability tests
- Have good reputation scores
- Respond within acceptable time limits

I test each new agent with:
- Basic functionality test
- Response time measurement
- Error handling verification""",
        "detailed_strict": """# Strict Security Policy
Requirements for trust:
1. Agent must be on pre-approved whitelist
2. Agent must have valid security credentials
3. Agent must pass all security audits
4. Agent must use encrypted communication

Automatic rejection for:
- Unknown agents
- Agents with failed tests
- Agents from untrusted networks""",
        "payment_processor": """# Payment Processor Trust Policy
This is a high-security trust policy for payment processing.

I ONLY trust agents that:
- Are explicitly whitelisted by security team
- Have PCI compliance certification
- Use end-to-end encryption
- Have passed penetration testing
- Maintain audit logs

I immediately reject:
- Any agent not on whitelist
- Agents without proper credentials
- Agents from public networks
- Agents with any failed security checks"""
    }


@pytest.fixture
def sample_verification_tools():
    """Sample verification tool functions for trust agents."""
    
    def check_whitelist(agent_id: str) -> bool:
        """Check if agent is whitelisted."""
        # Read from mock whitelist
        whitelist = ["alice", "bob", "trusted_service"]
        return agent_id in whitelist
    
    def test_capability(agent_id: str, test_input: str, expected_output: str) -> bool:
        """Test agent capability."""
        # Mock test - in reality would call the agent
        return True  # Simplified for testing
    
    def measure_response_time(agent_id: str, timeout_ms: int = 1000) -> float:
        """Measure agent response time."""
        # Mock measurement
        import random
        return random.uniform(100, 900)  # Mock response time in ms
    
    def check_local_network(agent_ip: str) -> bool:
        """Check if agent is on local network."""
        # Mock check
        return agent_ip.startswith("192.168.") or agent_ip == "localhost"
    
    def verify_credentials(agent_id: str, token: str) -> bool:
        """Verify agent credentials."""
        # Mock credential check
        return token.startswith("valid_token_")
    
    return {
        'check_whitelist': check_whitelist,
        'test_capability': test_capability,
        'measure_response_time': measure_response_time,
        'check_local_network': check_local_network,
        'verify_credentials': verify_credentials
    }


@pytest.fixture
def trust_test_agents():
    """Create test agents with different trust configurations."""
    
    def calculator(expression: str) -> str:
        """Simple calculator tool."""
        return str(eval(expression))
    
    def translator(text: str, to_lang: str = "es") -> str:
        """Mock translator tool."""
        translations = {
            "Hello": {"es": "Hola", "fr": "Bonjour"},
            "Goodbye": {"es": "Adiós", "fr": "Au revoir"}
        }
        return translations.get(text, {}).get(to_lang, f"[{text}]")
    
    agents = {}
    
    # Open trust agent (development)
    agents['open'] = Agent(
        name="dev_agent",
        tools=[calculator],
        trust="open",
        system_prompt="I am a development agent with open trust"
    )
    
    # Careful trust agent (staging)
    agents['careful'] = Agent(
        name="staging_agent",
        tools=[translator],
        trust="careful",
        system_prompt="I am a staging agent with careful trust"
    )
    
    # Strict trust agent (production)
    agents['strict'] = Agent(
        name="prod_agent",
        tools=[calculator, translator],
        trust="strict",
        system_prompt="I am a production agent with strict trust"
    )
    
    return agents


@pytest.fixture
def whitelist_file(tmp_path):
    """Create a mock whitelist file."""
    whitelist = tmp_path / "trusted.txt"
    whitelist.write_text("""# Trusted agents whitelist
alice_translator
bob_calculator
trusted_api.com
payment_processor.secure
*.company.internal
192.168.1.*
localhost
""")
    return str(whitelist)