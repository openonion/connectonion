"""
Sub-agent definition loader with YAML frontmatter parsing.

This module discovers and loads sub-agent definitions from .md files with YAML frontmatter.

File format:
    ---
    name: explore
    description: Fast codebase exploration
    model: co/gemini-2.5-flash
    max_iterations: 15
    tools:
      - glob
      - grep
      - read_file
    read_only: true
    ---

    # System Prompt
    You are an exploration agent...

Architecture:
- Auto-discovers .md files in subagents/ directory
- Parses YAML frontmatter for config
- Extracts markdown body as system prompt
- Global registry for caching definitions
"""

from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass
import re


@dataclass
class SubAgentDefinition:
    """Sub-agent configuration and prompt."""
    name: str
    description: str
    model: str
    max_iterations: int
    tools: List[str]
    system_prompt: str
    read_only: bool = False
    file_path: Optional[Path] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "description": self.description,
            "model": self.model,
            "max_iterations": self.max_iterations,
            "tools": self.tools,
            "system_prompt": self.system_prompt,
            "read_only": self.read_only,
        }


def parse_yaml_frontmatter(content: str) -> Tuple[Dict[str, Any], str]:
    """
    Parse YAML frontmatter from markdown content.

    Args:
        content: Markdown file content

    Returns:
        Tuple of (frontmatter_dict, markdown_body)
    """
    # Match --- ... --- at start of file
    match = re.match(r'^---\s*\n(.*?)\n---\s*\n(.+)', content, re.DOTALL)
    if not match:
        return {}, content

    frontmatter_text, markdown_body = match.groups()

    # Simple YAML parser (no PyYAML dependency needed)
    config = {}
    current_key = None
    current_list = []

    for line in frontmatter_text.split('\n'):
        line = line.rstrip()

        if not line:
            continue

        # Handle list items: "  - item"
        if line.startswith('  - '):
            item = line[4:].strip()
            current_list.append(item)
            continue

        # Handle key-value: "key: value"
        if ':' in line and not line.startswith(' '):
            # Save previous list if any
            if current_key and current_list:
                config[current_key] = current_list
                current_list = []

            key, value = line.split(':', 1)
            key = key.strip()
            value = value.strip()

            # Start new list if value is empty
            if not value:
                current_key = key
                continue

            current_key = None

            # Parse value
            if value.lower() in ('true', 'false'):
                config[key] = value.lower() == 'true'
            elif value.isdigit():
                config[key] = int(value)
            else:
                config[key] = value

    # Save last list if any
    if current_key and current_list:
        config[current_key] = current_list

    return config, markdown_body.strip()


def parse_subagent_file(file_path: Path) -> Optional[SubAgentDefinition]:
    """
    Parse a sub-agent definition file.

    Args:
        file_path: Path to .md file

    Returns:
        SubAgentDefinition or None if parsing fails
    """
    if not file_path.exists():
        return None

    content = file_path.read_text(encoding="utf-8")
    config, system_prompt = parse_yaml_frontmatter(content)

    if not config:
        return None

    return SubAgentDefinition(
        name=config.get('name', file_path.stem),
        description=config.get('description', ''),
        model=config.get('model', 'co/gemini-2.5-flash'),
        max_iterations=config.get('max_iterations', 15),
        tools=config.get('tools', []),
        system_prompt=system_prompt,
        read_only=config.get('read_only', False),
        file_path=file_path,
    )


def discover_subagents(subagents_dir: Path) -> Dict[str, SubAgentDefinition]:
    """
    Discover all sub-agent definitions in directory.

    Args:
        subagents_dir: Directory containing .md definition files

    Returns:
        Dict mapping agent name to SubAgentDefinition
    """
    if not subagents_dir.exists():
        return {}

    definitions = {}

    for file_path in subagents_dir.glob("*.md"):
        definition = parse_subagent_file(file_path)
        if definition:
            definitions[definition.name] = definition

    return definitions


# Global registry (singleton pattern)
_SUBAGENT_REGISTRY: Dict[str, SubAgentDefinition] = {}


def load_subagents(subagents_dir: Optional[Path] = None) -> Dict[str, SubAgentDefinition]:
    """
    Load all sub-agent definitions.

    Args:
        subagents_dir: Directory to load from (defaults to package subagents/)

    Returns:
        Dict mapping agent name to SubAgentDefinition
    """
    global _SUBAGENT_REGISTRY

    if subagents_dir is None:
        # Default to package subagents directory
        subagents_dir = Path(__file__).parent

    _SUBAGENT_REGISTRY = discover_subagents(subagents_dir)
    return _SUBAGENT_REGISTRY


def get_subagent_definition(name: str) -> Optional[SubAgentDefinition]:
    """
    Get a sub-agent definition by name.

    Args:
        name: Sub-agent name (e.g., "explore", "plan")

    Returns:
        SubAgentDefinition or None if not found
    """
    if not _SUBAGENT_REGISTRY:
        load_subagents()

    return _SUBAGENT_REGISTRY.get(name)


def list_subagents() -> List[str]:
    """
    List all available sub-agent names.

    Returns:
        List of sub-agent names
    """
    if not _SUBAGENT_REGISTRY:
        load_subagents()

    return list(_SUBAGENT_REGISTRY.keys())
