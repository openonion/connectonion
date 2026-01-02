"""
useful_prompts - Prompt templates for ConnectOnion agents.

These are PROMPT TEMPLATES to copy to your project, not framework code to import.

Usage:
    1. Run: co copy coding_agent
    2. Customize the markdown files in prompts/coding_agent/
    3. Use assembler.py to build your system prompt

Available prompts:
    - coding_agent/  : Coding Agent Prompt - modular template for coding assistants

See README.md for details.
"""

from pathlib import Path

# Path to useful_prompts directory (for copying examples)
PROMPTS_DIR = Path(__file__).parent


def get_example_path(name: str) -> Path:
    """Get path to an example directory for copying.

    Args:
        name: Example name (e.g., "coding_agent")

    Returns:
        Path to the example directory

    Example:
        >>> from connectonion.useful_prompts import get_example_path
        >>> import shutil
        >>> shutil.copytree(get_example_path("coding_agent"), "my_prompts")
    """
    return PROMPTS_DIR / name
