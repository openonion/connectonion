"""
Purpose: Unified logging interface for agents - terminal output + plain text + YAML sessions
LLM-Note:
  Dependencies: imports from [datetime, pathlib, typing, yaml, console.py] | imported by [agent.py] | tested by [tests/unit/test_logger.py]
  Data flow: receives from Agent → delegates to Console for terminal/file → writes YAML sessions to .co/sessions/
  State/Effects: writes to .co/sessions/{agent_name}_{timestamp}.yaml | delegates file logging to Console | session data persisted after each turn
  Integration: exposes Logger(agent_name, quiet, log), .print(), .log_llm_response(), .start_session(), .log_turn()
  Performance: YAML written after each turn (incremental) | Console delegation is direct passthrough
  Errors: let I/O errors bubble up (no try-except)
"""

from datetime import datetime
from pathlib import Path
from typing import Optional, Union, Dict, Any
import yaml

from .console import Console


class Logger:
    """Unified logging: terminal output + plain text + YAML sessions.

    Facade pattern: wraps Console for terminal/file logging, adds YAML sessions.

    Args:
        agent_name: Name of the agent (used in filenames)
        quiet: Suppress console output (default False)
        log: Enable file logging (default True, or path string for custom location)

    Examples:
        # Development (default) - see output + save everything
        logger = Logger("my-agent")

        # Eval mode - quiet but record sessions
        logger = Logger("my-agent", quiet=True)

        # Benchmark - completely off
        logger = Logger("my-agent", log=False)

        # Custom log path
        logger = Logger("my-agent", log="custom/path.log")
    """

    def __init__(
        self,
        agent_name: str,
        quiet: bool = False,
        log: Union[bool, str, Path, None] = None
    ):
        self.agent_name = agent_name

        # Determine what to enable
        self.enable_console = not quiet
        self.enable_sessions = True  # Sessions on unless log=False
        self.enable_file = True
        self.log_file_path = Path(f".co/logs/{agent_name}.log")

        # Parse log parameter
        if log is False:
            # log=False: disable everything
            self.enable_file = False
            self.enable_sessions = False
        elif isinstance(log, (str, Path)) and log:
            # Custom path
            self.log_file_path = Path(log)
        # else: log=True or log=None → defaults

        # If quiet=True, also disable file (only keep sessions)
        if quiet:
            self.enable_file = False

        # Console for terminal output (only if not quiet)
        self.console = None
        if self.enable_console:
            file_path = self.log_file_path if self.enable_file else None
            self.console = Console(log_file=file_path)

        # Session state (YAML)
        self.session_file: Optional[Path] = None
        self.session_data: Optional[Dict[str, Any]] = None

    # Delegate to Console
    def print(self, message: str, style: str = None):
        """Print message to console (if enabled)."""
        if self.console:
            self.console.print(message, style)

    def print_xray_table(self, *args, **kwargs):
        """Print xray table for decorated tools."""
        if self.console:
            self.console.print_xray_table(*args, **kwargs)

    def log_llm_response(self, *args, **kwargs):
        """Log LLM response with token usage."""
        if self.console:
            self.console.log_llm_response(*args, **kwargs)

    # Session logging (YAML)
    def start_session(self):
        """Initialize session YAML file."""
        if not self.enable_sessions:
            return

        sessions_dir = Path(".co/sessions")
        sessions_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        self.session_file = sessions_dir / f"{self.agent_name}_{timestamp}.yaml"
        self.session_data = {
            "name": self.agent_name,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "turns": []
        }

    def log_turn(self, turn_data: dict):
        """Log a turn to session YAML.

        Args:
            turn_data: Dict with keys: input, model, duration_ms, tokens, cost,
                      tools_called, result, messages (JSON string)
        """
        if not self.enable_sessions or not self.session_data:
            return

        self.session_data["turns"].append(turn_data)

        with open(self.session_file, "w") as f:
            yaml.dump(self.session_data, f, default_flow_style=False, allow_unicode=True)
