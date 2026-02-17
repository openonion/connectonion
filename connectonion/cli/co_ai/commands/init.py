"""
LLM-Note: Project initialization command for co_ai - Creates .co/OO.md configuration file

This module implements the /init command which sets up co_ai for a new project
by creating the .co directory structure and OO.md configuration template.

Key components:
- cmd_init(args): Main command handler for project initialization
- OO_MD_TEMPLATE: Template markdown content for .co/OO.md configuration file

Initialization workflow:
1. Check if .co/OO.md already exists (skip if exists)
2. Create .co/ directory if needed
3. Write OO_MD_TEMPLATE to .co/OO.md
4. Detect existing context files (README.md, CLAUDE.md)
5. Display status panel with creation results and detected files

Configuration priority (how co_ai reads context):
1. .co/OO.md - Primary project-specific instructions (created by this command)
2. CLAUDE.md - Compatibility with Claude Code
3. README.md - General project understanding

Template sections:
- About This Project (description)
- Key Files (directory structure)
- Commands (dev/test/build commands)
- Coding Conventions (style guide)
- Important Notes (co_ai-specific context)

Initialize OO for a project.
"""

from pathlib import Path
from rich.console import Console
from rich.panel import Panel

console = Console()

OO_MD_TEMPLATE = """# Project Configuration for OO

## About This Project

[Describe what this project does]

## Key Files

- `src/` - Source code
- `tests/` - Tests

## Commands

```bash
# Development
npm run dev

# Testing
npm test

# Build
npm run build
```

## Coding Conventions

- [Add your coding style preferences]
- [Add naming conventions]
- [Add any project-specific rules]

## Important Notes

- [Add things OO should know when working on this project]
"""


def cmd_init(args: str = "") -> str:
    """
    Initialize .co/ directory with OO.md configuration.

    Creates:
    - .co/OO.md - Project configuration file for OO

    Detects:
    - README.md - Will be used for project understanding
    - CLAUDE.md - Will be used for compatibility
    """
    cwd = Path.cwd()
    co_dir = cwd / ".co"
    oo_md = co_dir / "OO.md"

    # Check what already exists
    readme_exists = (cwd / "README.md").exists()
    claude_exists = (cwd / "CLAUDE.md").exists()
    oo_exists = oo_md.exists()

    if oo_exists:
        console.print(f"[yellow].co/OO.md already exists[/]")
        console.print(f"Edit [cyan]{oo_md}[/] to update configuration.")
        return "Already initialized"

    # Create .co directory
    co_dir.mkdir(exist_ok=True)

    # Create OO.md
    oo_md.write_text(OO_MD_TEMPLATE, encoding="utf-8")

    # Build status message
    lines = [
        "[green]✓[/] Created [cyan].co/OO.md[/]",
        "",
        "Detected:",
    ]

    if readme_exists:
        lines.append("  [green]✓[/] README.md (will use for project understanding)")
    else:
        lines.append("  [dim]○[/] README.md (not found)")

    if claude_exists:
        lines.append("  [green]✓[/] CLAUDE.md (will use for compatibility)")
    else:
        lines.append("  [dim]○[/] CLAUDE.md (not found)")

    lines.extend([
        "",
        f"Edit [cyan].co/OO.md[/] to configure OO for your project.",
    ])

    output = "\n".join(lines)
    console.print(Panel(output, title="oo /init", border_style="green"))

    return "Initialized"
