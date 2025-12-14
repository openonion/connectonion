"""
Purpose: Unified logging interface for agents - terminal output + plain text + YAML sessions
LLM-Note:
  Dependencies: imports from [datetime, pathlib, typing, yaml, console.py] | imported by [agent.py, tool_executor.py] | tested by [tests/unit/test_logger.py]
  Data flow: receives from Agent/tool_executor → delegates to Console for terminal/file → writes YAML sessions to .co/sessions/
  State/Effects: writes to .co/sessions/{agent_name}.yaml (one file per agent, appends turns) | delegates file logging to Console | session data persisted after each turn
  Integration: exposes Logger(agent_name, quiet, log), .print(), .log_tool_call(name, args), .log_tool_result(result, timing), .log_llm_response(), .start_session(), .log_turn()
  Session format: metadata at top → turns summary (with tools_called as function-call style) → system_prompt + messages at end (see docs/session-yaml-format.md)
  Performance: YAML written after each turn (incremental) | loads existing session file on start | Console delegation is direct passthrough
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

    Session files use one file per agent (.co/sessions/{agent_name}.yaml) to
    reduce file clutter. New turns are appended to the same file.

    Args:
        agent_name: Name of the agent (used in filenames)
        quiet: Suppress console output (default False)
        log: Enable file logging (default True, or path string for custom location)

    Files created:
        - .co/logs/{agent_name}.log: Plain text log with session markers
        - .co/sessions/{agent_name}.yaml: Structured YAML with all turns

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

    def log_tool_call(self, tool_name: str, tool_args: dict):
        """Log tool call."""
        if self.console:
            self.console.log_tool_call(tool_name, tool_args)

    def log_tool_result(self, result: str, timing_ms: float):
        """Log tool result."""
        if self.console:
            self.console.log_tool_result(result, timing_ms)

    def _format_tool_call(self, trace_entry: dict) -> str:
        """Format tool call as natural function-call style: greet(name='Alice')"""
        tool_name = trace_entry.get('tool_name', '')
        args = trace_entry.get('arguments', {})
        parts = []
        for k, v in args.items():
            if isinstance(v, str):
                v_str = v if len(v) <= 50 else v[:50] + "..."
                parts.append(f"{k}='{v_str}'")
            else:
                v_str = str(v)
                if len(v_str) > 50:
                    v_str = v_str[:50] + "..."
                parts.append(f"{k}={v_str}")
        return f"{tool_name}({', '.join(parts)})"

    # Session logging (YAML)
    def start_session(self, system_prompt: str = "", session_id: Optional[str] = None):
        """Initialize session YAML file.

        Uses one file per session_id (for HTTP API) or per agent (for interactive).
        Loads existing session data if file exists, appends new turns.

        Args:
            system_prompt: The system prompt for this session
            session_id: Optional session identifier. If provided, logs to
                       .co/sessions/{session_id}.yaml for thread-safe HTTP API.
                       If None, uses agent name for interactive mode.
        """
        if not self.enable_sessions:
            return

        sessions_dir = Path(".co/sessions")
        sessions_dir.mkdir(parents=True, exist_ok=True)

        # Use session_id if provided (HTTP API), otherwise use agent_name (interactive)
        filename = session_id if session_id else self.agent_name
        # Sanitize: keep only safe characters (alphanumeric, dash, underscore)
        import re
        filename = re.sub(r'[^a-zA-Z0-9_-]', '_', filename)[:255] or 'default'
        self.session_file = sessions_dir / f"{filename}.yaml"

        # Load existing session or create new
        if self.session_file.exists():
            with open(self.session_file, 'r') as f:
                self.session_data = yaml.safe_load(f) or {}
            # Ensure ALL required fields exist (handles empty/corrupted files)
            if 'name' not in self.session_data:
                self.session_data['name'] = self.agent_name
            if 'session_id' not in self.session_data and session_id:
                self.session_data['session_id'] = session_id
            if 'created' not in self.session_data:
                self.session_data['created'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            if 'total_cost' not in self.session_data:
                self.session_data['total_cost'] = 0.0
            if 'total_tokens' not in self.session_data:
                self.session_data['total_tokens'] = 0
            if 'turns' not in self.session_data:
                self.session_data['turns'] = []
            if 'messages' not in self.session_data:
                self.session_data['messages'] = {}
            # Update system_prompt if provided
            if system_prompt:
                self.session_data['system_prompt'] = system_prompt
        else:
            self.session_data = {
                "name": self.agent_name,
                "session_id": session_id,
                "created": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "total_cost": 0.0,
                "total_tokens": 0,
                "system_prompt": system_prompt,
                "turns": [],
                "messages": {}  # Dict keyed by turn number
            }

    def log_turn(self, user_input: str, result: str, duration_ms: float, session: dict, model: str):
        """Log turn summary + messages to YAML file.

        Args:
            user_input: The user's input prompt
            result: The agent's final response
            duration_ms: Total duration in milliseconds
            session: Agent's current_session dict (contains messages, trace)
            model: Model name string
        """
        if not self.enable_sessions or not self.session_data:
            return

        # Aggregate from trace
        trace = session.get('trace', [])
        llm_calls = [t for t in trace if t.get('type') == 'llm_call']
        tool_calls = [t for t in trace if t.get('type') == 'tool_execution']

        total_tokens = sum(
            (t.get('usage').input_tokens + t.get('usage').output_tokens)
            for t in llm_calls if t.get('usage')
        )
        total_cost = sum(
            t.get('usage').cost
            for t in llm_calls if t.get('usage')
        )

        turn_data = {
            'input': user_input,
            'expected': session.get('expected', ''),
            'model': model,
            'duration_ms': int(duration_ms),
            'tokens': total_tokens,
            'cost': round(total_cost, 4),
            'tools_called': [self._format_tool_call(t) for t in tool_calls],
            'result': result,
            'evaluation': session.get('evaluation', '')
        }

        # Update session aggregates
        self.session_data['updated'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.session_data['total_cost'] = round(
            self.session_data.get('total_cost', 0) + turn_data['cost'], 4
        )
        self.session_data['total_tokens'] = (
            self.session_data.get('total_tokens', 0) + turn_data['tokens']
        )

        # Add turn number and timestamp
        turn_num = len(self.session_data['turns']) + 1
        turn_data['turn'] = turn_num
        turn_data['timestamp'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.session_data['turns'].append(turn_data)

        # Extract this turn's messages (everything after what we've already saved)
        all_messages = session.get('messages', [])
        saved_count = sum(len(msgs) for msgs in self.session_data['messages'].values())
        turn_messages = all_messages[saved_count + 1:]  # +1 to skip system message
        self.session_data['messages'][turn_num] = turn_messages

        # Write YAML
        self._write_session()

    def _write_session(self):
        """Write session data with turns summary first, detail at end."""
        # Build ordered dict: compact metadata → turns → detail (system_prompt + messages)
        ordered = {
            'name': self.session_data['name'],
            'session_id': self.session_data.get('session_id'),
            'created': self.session_data['created'],
            'updated': self.session_data.get('updated', ''),
            'total_cost': self.session_data.get('total_cost', 0),
            'total_tokens': self.session_data.get('total_tokens', 0),
            'turns': self.session_data['turns'],
            # Detail section (scroll down)
            'system_prompt': self.session_data.get('system_prompt', ''),
            'messages': self.session_data['messages']
        }
        with open(self.session_file, 'w') as f:
            yaml.dump(ordered, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    def load_messages(self) -> list:
        """Load and reconstruct full message list from session file.

        Returns:
            Full message list: [system_message] + all turn messages in order
        """
        if not self.session_file or not self.session_file.exists():
            return []
        with open(self.session_file, 'r') as f:
            data = yaml.safe_load(f) or {}

        # Reconstruct: system prompt + all turn messages in order
        messages = []
        if data.get('system_prompt'):
            messages.append({"role": "system", "content": data['system_prompt']})

        turn_messages = data.get('messages', {})
        for turn_num in sorted(turn_messages.keys()):
            messages.extend(turn_messages[turn_num])

        return messages

    def load_session(self) -> dict:
        """Load session data from file."""
        if not self.session_file or not self.session_file.exists():
            return {'system_prompt': '', 'turns': [], 'messages': {}}
        with open(self.session_file, 'r') as f:
            return yaml.safe_load(f) or {'system_prompt': '', 'turns': [], 'messages': {}}
