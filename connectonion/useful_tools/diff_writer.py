"""
Purpose: Human-in-the-loop file writing tool with diff preview and approval workflow
LLM-Note:
  Dependencies: imports from [difflib, pathlib, rich.console, rich.panel, rich.text, connectonion.tui.pick] | imported by [useful_tools/__init__.py] | tested by [tests/unit/test_diff_writer.py, tests/unit/test_diff_writer_tool.py]
  Data flow: Agent calls DiffWriter.write(path, content) → reads existing file → generates unified diff → displays via Rich panel → pick() prompts for approval → writes if approved → returns status string
  State/Effects: reads and writes files on filesystem | displays Rich-formatted diff in terminal | blocks for user input (unless auto_approve=True) | creates new files if path doesn't exist
  Integration: exposes DiffWriter class with write(path, content), diff(path, content), read(path) | used as agent tool via Agent(tools=[DiffWriter()]) | auto_approve=True for automation
  Performance: file I/O per operation | difflib is O(n) for diff generation | Rich rendering is fast | blocks on user input
  Errors: returns error string if file unreadable | returns "Cancelled" if user rejects | no exceptions raised

DiffWriter - Human-in-the-loop file writing with diff display.

Usage:
    from connectonion import Agent, DiffWriter

    writer = DiffWriter()
    agent = Agent("coder", tools=[writer])

    # Agent can now use:
    # - write(path, content) - Write with diff display and approval
    # - diff(path, content) - Preview diff without writing
    # - read(path) - Read file contents
"""

import difflib
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from connectonion.tui import pick


class DiffWriter:
    """File writer with diff display and human approval."""

    def __init__(self, auto_approve: bool = False):
        """Initialize DiffWriter.

        Args:
            auto_approve: If True, skip approval prompts (for automation)
        """
        self.auto_approve = auto_approve
        self._console = Console()

    def write(self, path: str, content: str) -> str:
        """Write content to a file with diff display and approval.

        Args:
            path: File path to write to
            content: Content to write

        Returns:
            Success message, rejection message, or user feedback for agent
        """
        file_path = Path(path)

        if not self.auto_approve:
            diff_text = self._generate_diff(path, content)
            if diff_text:
                self._display_diff(diff_text, path)
            else:
                self._display_new_file(path, content)

            choice = self._ask_approval(path)

            if choice == "reject":
                self._console.print()
                self._console.print("[bold yellow]What should the agent do instead?[/]")
                feedback = input("> ")
                return f"User rejected changes to {path}. Feedback: {feedback}"

            if choice == "approve_all":
                self.auto_approve = True

        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding='utf-8')
        return f"Wrote {len(content)} bytes to {path}"

    def diff(self, path: str, content: str) -> str:
        """Show diff without writing (preview mode).

        Args:
            path: File path to compare against
            content: New content to compare

        Returns:
            Diff string in unified format
        """
        diff_text = self._generate_diff(path, content)
        if diff_text:
            self._display_diff(diff_text, path)
            return diff_text
        return f"No changes to {path}"

    def read(self, path: str) -> str:
        """Read file contents.

        Args:
            path: File path to read

        Returns:
            File contents or error message
        """
        file_path = Path(path)
        if not file_path.exists():
            return f"Error: File {path} not found"
        return file_path.read_text(encoding='utf-8')

    def _ask_approval(self, path: str) -> str:
        """Ask user for approval with single keypress.

        Returns:
            'approve', 'approve_all', or 'reject'
        """
        self._console.print()
        self._console.print(f"[bold cyan]File:[/] {path}")

        choice = pick(
            f"Apply changes to {path}?",
            {
                "1": "Yes, apply this change",
                "2": "Yes to all (auto-approve for session)",
                "3": "No, and tell agent what to do instead",
            },
            console=self._console,
        )
        return {"1": "approve", "2": "approve_all", "3": "reject"}[choice]

    def _generate_diff(self, path: str, new_content: str) -> str:
        """Generate unified diff between existing file and new content."""
        file_path = Path(path)

        if file_path.exists():
            original_lines = file_path.read_text(encoding='utf-8').splitlines(keepends=True)
        else:
            return ""  # New file, no diff

        new_lines = new_content.splitlines(keepends=True)

        diff = difflib.unified_diff(
            original_lines,
            new_lines,
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
        )

        return ''.join(diff)

    def _display_diff(self, diff_text: str, path: str):
        """Display colorized diff."""
        styled = Text()

        for line in diff_text.splitlines():
            if line.startswith('+++') or line.startswith('---'):
                styled.append(line + '\n', style="bold white")
            elif line.startswith('@@'):
                styled.append(line + '\n', style="cyan")
            elif line.startswith('+'):
                styled.append(line + '\n', style="green")
            elif line.startswith('-'):
                styled.append(line + '\n', style="red")
            else:
                styled.append(line + '\n', style="dim")

        panel = Panel(
            styled,
            title=f"[bold yellow]Changes to {path}[/]",
            border_style="yellow",
            padding=(0, 1)
        )
        self._console.print(panel)

    def _display_new_file(self, path: str, content: str):
        """Display preview of new file."""
        styled = Text()

        lines = content.splitlines()
        for line in lines[:50]:  # Limit preview to 50 lines
            styled.append(f"+ {line}\n", style="green")

        if len(lines) > 50:
            styled.append(f"... ({len(lines) - 50} more lines)\n", style="dim")

        panel = Panel(
            styled,
            title=f"[bold yellow]New file: {path}[/]",
            border_style="yellow",
            padding=(0, 1)
        )
        self._console.print(panel)
