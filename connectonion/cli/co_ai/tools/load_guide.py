"""
LLM-Note: Load Guide tool for co_ai - Loads ConnectOnion framework documentation from embedded markdown guides

Key components:
- load_guide() function: Main entry point for loading framework documentation
- GUIDES_DIR: Points to connectonion/cli/co_ai/prompts/connectonion/ folder
- Parameter: path (like "concepts/agent", "useful_tools/shell")

Architecture:
- Embedded documentation system for co_ai agent
- Guides stored as markdown files in prompts/connectonion/
- Supports hierarchical paths (concepts/, useful_tools/, etc.)
- Returns guide content or helpful error message with available paths

Load ConnectOnion framework guides.
"""

from pathlib import Path

GUIDES_DIR = Path(__file__).parent.parent / "prompts" / "connectonion"


def load_guide(path: str) -> str:
    """
    Load a ConnectOnion framework guide.

    Args:
        path: Full path like "concepts/agent", "concepts/tools", "useful_tools/shell"

    Returns:
        Guide content
    """
    guide_file = GUIDES_DIR / f"{path}.md"

    if not guide_file.exists():
        return f"Guide '{path}' not found. Use full path: concepts/agent, concepts/tools, useful_tools/shell. See index.md."

    return guide_file.read_text(encoding="utf-8")