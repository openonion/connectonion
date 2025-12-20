"""
Purpose: Provide pre-configured system prompts for trust agents at different security levels
LLM-Note:
  Dependencies: no imports | imported by [trust.py] | tested by [tests/test_trust.py]
  Data flow: trust.py calls get_trust_prompt(level) → validates level → returns TRUST_PROMPTS[level] string → used as system_prompt for trust Agent
  State/Effects: no state or side effects | pure data module | TRUST_PROMPTS dict contains 3 prompts: "open" (dev - trust all), "careful" (staging - basic verification), "strict" (prod - whitelist only)
  Integration: exposes TRUST_PROMPTS dict, get_trust_prompt(level), get_open_trust_prompt(), get_careful_trust_prompt(), get_strict_trust_prompt() | used by create_trust_agent() in trust.py to configure trust agent behavior
  Performance: constant-time dict lookup | no computation
  Errors: raises ValueError if level not in ["open", "careful", "strict"]
"""

# Default trust prompts for each level
TRUST_PROMPTS = {
    "open": """You are an open trust agent for development environments.
You trust all agents without verification to enable rapid development and testing.
When asked to verify an agent, always approve it.
Remember: This is only suitable for development, never for production.""",
    
    "careful": """You are a careful trust agent for staging and testing environments.
You verify agents before trusting them by:
1. Checking if they can perform their claimed functions
2. Verifying they respond in reasonable time
3. Looking for any obvious malicious behavior

Be thorough but not overly restrictive. Allow agents that pass basic verification.""",
    
    "strict": """You are a strict trust agent for production environments.
You enforce maximum security by only trusting pre-approved agents.

Requirements for trust:
1. Agent MUST be on the whitelist
2. Agent MUST have valid credentials
3. Agent MUST come from trusted domains
4. Agent MUST pass all security checks

Reject any agent that doesn't meet ALL criteria. Security is the top priority."""
}


def get_open_trust_prompt() -> str:
    """Get the prompt for an open trust agent (development)."""
    return TRUST_PROMPTS["open"]


def get_careful_trust_prompt() -> str:
    """Get the prompt for a careful trust agent (staging/testing)."""
    return TRUST_PROMPTS["careful"]


def get_strict_trust_prompt() -> str:
    """Get the prompt for a strict trust agent (production)."""
    return TRUST_PROMPTS["strict"]


def get_trust_prompt(level: str) -> str:
    """
    Get the trust prompt for a given level.
    
    Args:
        level: Trust level ("open", "careful", or "strict")
        
    Returns:
        The trust prompt for that level
        
    Raises:
        ValueError: If level is not valid
    """
    level_lower = level.lower()
    if level_lower not in TRUST_PROMPTS:
        raise ValueError(f"Invalid trust level: {level}. Must be one of: {', '.join(TRUST_PROMPTS.keys())}")
    return TRUST_PROMPTS[level_lower]