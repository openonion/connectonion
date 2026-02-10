"""
Purpose: Web-based file writing tool with Claude Code-style permission modes
LLM-Note:
  Dependencies: imports from [difflib, pathlib, typing] | imported by [useful_tools/__init__.py, __init__.py] | tested by [tests/unit/test_diff_writer.py]
  Data flow: Agent calls DiffWriter.write(agent, path, content) -> show diff via agent.io -> ask approval via agent.io -> write file -> return status
  State/Effects: reads and writes files on filesystem | sends diff_preview and ask_user events via agent.io
  Integration: exposes DiffWriter class with write(agent, path, content), diff(path, content), read(path) | used as agent tool via Agent(tools=[DiffWriter()])
  Errors: returns error string if file unreadable | returns user feedback on rejection | no exceptions raised

Permission Modes (like Claude Code's Shift+Tab cycle):
  - normal: Prompt for every edit (default)
  - auto: Auto-approve all edits without prompting
  - plan: Read-only mode, no writes allowed

IO Access:
  write() declares 'agent' in its signature. The tool_executor detects this and
  injects the current agent automatically. Same pattern as ask_user — no sync
  hooks or back-references needed. The tool_factory excludes 'agent' from the
  LLM-facing schema so the LLM never sees it.

Usage:
    from connectonion import Agent, DiffWriter

    writer = DiffWriter()  # mode="normal" by default
    agent = Agent("coder", tools=[writer])

    # Agent can now use:
    # - write(path, content) - Write with diff display and approval
    # - diff(path, content) - Preview diff without writing
    # - read(path) - Read file contents
"""

import difflib
from pathlib import Path
from typing import Optional, Tuple


# Permission modes (like Claude Code's Shift+Tab cycle)
MODE_NORMAL = "normal"      # Prompt for every edit
MODE_AUTO = "auto"          # Auto-approve edits
MODE_PLAN = "plan"          # Read-only, no writes


class DiffWriter:
    """File writer with Claude Code-style permission modes (web mode).

    Requires io channel for approval prompts. Without io, falls back to auto-approve.

    Usage:
        writer = DiffWriter(mode="normal")  # Prompt for every edit
        writer = DiffWriter(mode="auto")    # Auto-approve all edits
        writer = DiffWriter(mode="plan")    # Read-only, preview only
    """

    def __init__(self, mode: str = MODE_NORMAL, preview_limit: int = 2000):
        """Initialize DiffWriter.

        Args:
            mode: Permission mode - "normal" (prompt), "auto" (auto-approve), "plan" (read-only)
            preview_limit: Max chars to include in diff preview
        """
        self.mode = mode
        self.preview_limit = preview_limit

    def write(self, agent, path: str, content: str) -> str:
        """Write content to a file with diff display and approval.

        Args:
            agent: Injected by tool_executor (provides agent.io for frontend communication)
            path: File path to write to
            content: Content to write

        Returns:
            Success message, rejection message with feedback, or plan mode preview
        """
        file_path = Path(path)
        file_exists = file_path.exists()
        io = agent.io if agent else None

        # Plan mode = read-only, just show what would happen
        if self.mode == MODE_PLAN:
            diff_text = self._generate_diff(path, content)
            preview = self._build_preview(diff_text, content, file_exists)
            return f"[Plan mode] Would write {len(content)} bytes to {path}\n\nPreview:\n{preview[:500]}"

        # Generate diff for display
        diff_text = self._generate_diff(path, content)
        preview = self._build_preview(diff_text, content, file_exists)
        preview, truncated = self._truncate_preview(preview)

        # Send diff preview to UI (best-effort, doesn't block)
        self._send_preview(io, path, preview, truncated, file_exists)

        # Check approval based on mode
        if self.mode == MODE_NORMAL:
            choice = self._ask_approval(io, path, preview, truncated)

            if choice == "reject":
                feedback = self._ask_feedback(io, path)
                return f"User rejected changes to {path}. Feedback: {feedback}"

            if choice == "approve_all":
                self.mode = MODE_AUTO  # Switch to auto mode for rest of session

        # Auto mode or approved: write file
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")

        mode_note = "" if self.mode == MODE_NORMAL else f" [{self.mode} mode]"
        return f"Wrote {len(content)} bytes to {path}{mode_note}"

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
        return file_path.read_text(encoding="utf-8")

    # =========================================================================
    # IO Communication (Web Mode)
    # All private methods receive io as first arg — passed from write().
    # =========================================================================

    def _send_preview(self, io, path: str, preview: str, truncated: bool, file_exists: bool) -> None:
        """Send diff preview event to UI client.

        This is informational - UI can render a nice diff view.
        Does not block or wait for response.
        """
        if not io:
            return
        io.send({
            "type": "diff_preview",
            "path": path,
            "preview": preview,
            "truncated": truncated,
            "file_exists": file_exists,
        })

    def _ask_approval(self, io, path: str, preview: str, truncated: bool) -> str:
        """Ask user for approval via io channel.

        Returns:
            "approve" - Apply this change
            "approve_all" - Apply and switch to auto mode
            "reject" - Reject and ask for feedback
        """
        if not io:
            # No io channel = auto-approve (for non-web usage)
            return "approve"

        question = f"Apply changes to {path}?"
        if truncated:
            question += " (preview truncated)"

        response = self._ask_user(
            io,
            question,
            options=[
                "Yes, apply this change",
                "Yes to all (auto-approve)",
                "No, reject and give feedback",
            ],
        )

        # Parse response
        if response == "Yes to all (auto-approve)":
            return "approve_all"
        if response == "Yes, apply this change":
            return "approve"

        # Handle free-text responses
        if response:
            lowered = response.strip().lower()
            if "yes to all" in lowered or lowered == "auto":
                return "approve_all"
            if lowered.startswith("yes") or lowered == "approve":
                return "approve"

        return "reject"

    def _ask_feedback(self, io, path: str) -> str:
        """Ask user for feedback when changes are rejected."""
        feedback = self._ask_user(io, f"What should the agent do instead for {path}?")
        return feedback or "No feedback provided"

    def _ask_user(self, io, question: str, options: Optional[list] = None) -> str:
        """Send ask_user event and block until user responds.

        Args:
            io: IO channel (agent.io)
            question: Question to display
            options: List of option strings (buttons in UI)

        Returns:
            User's answer string
        """
        if not io:
            return ""

        # Send ask_user event
        io.send({
            "type": "ask_user",
            "question": question,
            "options": options,
        })

        # Block waiting for response
        response = io.receive()

        # Handle connection closed
        if response.get("type") == "io_closed":
            return ""

        # Extract answer
        answer = response.get("answer", "")
        if isinstance(answer, list):
            return ", ".join([str(a) for a in answer])
        return str(answer) if answer is not None else ""

    # =========================================================================
    # Diff Generation
    # =========================================================================

    def _generate_diff(self, path: str, new_content: str) -> str:
        """Generate unified diff between existing file and new content."""
        file_path = Path(path)

        if not file_path.exists():
            return ""  # New file, no diff to show

        original_lines = file_path.read_text(encoding="utf-8").splitlines(keepends=True)
        new_lines = new_content.splitlines(keepends=True)

        diff = difflib.unified_diff(
            original_lines,
            new_lines,
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
        )

        return "".join(diff)

    def _build_preview(self, diff_text: str, content: str, file_exists: bool) -> str:
        """Build human-readable preview for approval dialog."""
        if diff_text:
            return diff_text
        if file_exists:
            return "(no changes)"
        return self._new_file_preview(content)

    def _truncate_preview(self, preview: str) -> Tuple[str, bool]:
        """Truncate preview to configured limit."""
        if len(preview) <= self.preview_limit:
            return preview, False
        return preview[: self.preview_limit] + "\n...(truncated)", True

    def _new_file_preview(self, content: str, max_lines: int = 50) -> str:
        """Create preview for new file (no existing file to diff against)."""
        lines = content.splitlines()
        preview_lines = lines[:max_lines]
        preview = "\n".join([f"+ {line}" for line in preview_lines])
        if len(lines) > max_lines:
            preview += f"\n... ({len(lines) - max_lines} more lines)"
        return preview
