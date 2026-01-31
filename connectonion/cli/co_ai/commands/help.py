"""Help command for OO CLI."""

from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown

console = Console()

HELP_TEXT = """
# OO Commands

## Built-in Commands

| Command | Description |
|---------|-------------|
| `/init` | Initialize .co/OO.md for the project |
| `/review-pr` | Review a GitHub PR (agent skill) |
| `/cost` | Show session cost and token usage |
| `/compact` | Compress conversation (LLM summarization) |
| `/tasks` | List background tasks |
| `/help` | Show this help message |
| `clear` | Clear the screen |
| `exit` | Exit OO |

## Usage

```bash
# One-shot mode
oo "fix the bug in auth.py"

# Interactive mode
oo

# With options
oo -m co/gemini-2.5-pro "task"   # Use different model
oo -y "task"                      # Auto-approve file changes
```

## Agent Tools

**Search:** `glob`, `grep`
**Files:** `read_file`, `edit`, `write`
**Execute:** `bash`
**Sub-agents:** `task` (explore, plan)
**Plan Mode:** `enter_plan_mode`, `exit_plan_mode`
**Interaction:** `ask_user`, `confirm`
**Skills:** `skill` (auto-invoked when relevant)
**Background:** `run_background`, `task_output`, `kill_task`

## Skills

Skills are auto-discovered instruction sets. Built-in skills:
- `commit` - Create git commits with good messages
- `review-pr` - Review GitHub pull requests

Add custom skills in `.co/skills/skill-name/SKILL.md`

## Configuration

OO reads context from (in priority order):
1. `.co/OO.md` - OO-specific instructions
2. `CLAUDE.md` - Compatibility with Claude Code
3. `README.md` - Project understanding

Run `/init` to create `.co/OO.md` for your project.

## Tips

- Use `@` to autocomplete file paths
- Use `/` to autocomplete commands
- Use `/cost` to check spending
- Use `/compact` when context is high (>70%)
- Use `/tasks` to monitor background operations
"""


def cmd_help(args: str = "") -> str:
    """Show help message."""
    console.print(Panel(Markdown(HELP_TEXT), title="oo /help", border_style="blue"))
    return "Help displayed"
