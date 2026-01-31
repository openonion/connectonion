"""Load ConnectOnion framework guides."""

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