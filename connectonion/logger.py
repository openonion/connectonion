"""
Purpose: Unified logging interface for agents - terminal output + plain text + YAML evals
LLM-Note:
  Dependencies: imports from [datetime, pathlib, typing, json, re, yaml, os, console.py] | imported by [agent.py, tool_executor.py] | tested by [tests/unit/test_logger.py]
  Data flow: receives from Agent/tool_executor → delegates to Console for terminal/file → writes YAML evals to .co/evals/
  State/Effects: writes to .co/evals/{input_slug}.yaml (one file per unique first input) | run data stored in .co/evals/{input_slug}/run_{n}.yaml | eval data persisted after each turn
  Integration: exposes Logger(agent_name, quiet, log), .print(), .log_tool_call(name, args), .log_tool_result(result, timing), .log_llm_response(), .start_session(), .log_turn()
  Eval format: eval.yaml (metadata + turns) | run_N.yaml (system_prompt, model, cwd, tokens, cost, duration_ms, timestamp, messages as multi-line JSON)
  Performance: YAML written after each turn (incremental) | Console delegation is direct passthrough
  Errors: let I/O errors bubble up (no try-except)
"""

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Optional, Union, Dict, Any, List

import yaml

from .console import Console


def _slugify(text: str, max_length: int = 50) -> str:
    """Convert text to URL-friendly slug for filenames.

    Args:
        text: Input text to slugify
        max_length: Maximum length of slug

    Returns:
        Lowercase slug with words separated by underscores
    """
    # Lowercase and replace spaces/special chars with underscores
    slug = re.sub(r'[^a-zA-Z0-9]+', '_', text.lower())
    # Remove leading/trailing underscores
    slug = slug.strip('_')
    # Truncate to max length at word boundary
    if len(slug) > max_length:
        slug = slug[:max_length].rsplit('_', 1)[0]
    return slug or 'default'


class Logger:
    """Unified logging: terminal output + plain text + YAML evals.

    Facade pattern: wraps Console for terminal/file logging, adds YAML evals.

    Eval files are named from the first input (slugified). Same input sequence
    = same file with multiple runs. Each run stored as YAML with messages as JSON.
    Log = Eval (same format, add expect field for tests).

    Args:
        agent_name: Name of the agent (used in log filenames)
        quiet: Suppress console output (default False)
        log: Enable file logging (default True, or path string for custom location)

    Files created:
        - .co/logs/{agent_name}.log: Plain text log with session markers
        - .co/evals/{input_slug}.yaml: Structured YAML with turns and history
        - .co/evals/{input_slug}/run_{n}.yaml: Run metadata + messages as multi-line JSON

    Examples:
        # Development (default) - see output + save everything
        logger = Logger("my-agent")

        # Eval mode - quiet but record evals
        logger = Logger("my-agent", quiet=True)

        # Benchmark - completely off
        logger = Logger("my-agent", log=False)
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
        self.enable_sessions = True  # Evals on unless log=False
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

        # If quiet=True, also disable file (only keep evals)
        if quiet:
            self.enable_file = False

        # Console for terminal output (only if not quiet)
        self.console = None
        if self.enable_console:
            file_path = self.log_file_path if self.enable_file else None
            self.console = Console(log_file=file_path)

        # Eval state
        self.eval_file: Optional[Path] = None
        self.eval_dir: Optional[Path] = None
        self.eval_data: Optional[Dict[str, Any]] = None
        self.current_run: int = 0
        self._first_input: Optional[str] = None  # Track first input for file naming

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
        tool_name = trace_entry.get('name', '')
        args = trace_entry.get('args', {})
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

    # Eval logging (YAML + JSONL) - Log = Eval, same format
    def start_session(self, system_prompt: str = "", session_id: Optional[str] = None):
        """Initialize eval session state.

        Note: The actual file is created lazily in log_turn() when we have
        the first input to generate the filename from.
        System prompt is stored in messages JSONL, not in eval YAML.

        Args:
            system_prompt: Unused (kept for backward compatibility)
            session_id: Optional session identifier (used for HTTP API thread safety)
        """
        if not self.enable_sessions:
            return

        self._first_input = None
        self.eval_file = None
        self.eval_dir = None
        self.eval_data = None
        self.current_run = 0

    def _init_eval_file(self, first_input: str):
        """Initialize or load eval file based on first input.

        Args:
            first_input: The first user input (used to name the file)
        """
        evals_dir = Path(".co/evals")
        evals_dir.mkdir(parents=True, exist_ok=True)

        # Generate filename from first input
        slug = _slugify(first_input)
        self.eval_file = evals_dir / f"{slug}.yaml"
        self.eval_dir = evals_dir / slug
        self._first_input = first_input

        # Load existing or create new
        if self.eval_file.exists():
            with open(self.eval_file, 'r') as f:
                self.eval_data = yaml.safe_load(f) or {}

            # Check if this is the same conversation (same first input)
            existing_turns = self.eval_data.get('turns', [])
            if existing_turns and existing_turns[0].get('input') == first_input:
                # Same conversation - new run
                self.current_run = self.eval_data.get('runs', 0) + 1
                self.eval_data['runs'] = self.current_run
            else:
                # Different first input but same slug (collision) - treat as new
                self.current_run = 1
                self.eval_data = self._create_new_eval_data(first_input)
        else:
            self.current_run = 1
            self.eval_data = self._create_new_eval_data(first_input)

        # Create messages directory
        self.eval_dir.mkdir(parents=True, exist_ok=True)

    def _create_new_eval_data(self, first_input: str) -> Dict[str, Any]:
        """Create new eval data structure."""
        return {
            "name": _slugify(first_input),
            "created": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "runs": 1,
            "model": "",
            "turns": []
        }

    def log_turn(self, user_input: str, result: str, duration_ms: float, session: dict, model: str):
        """Log turn to YAML file and messages to JSONL.

        Args:
            user_input: The user's input prompt
            result: The agent's final response
            duration_ms: Total duration in milliseconds
            session: Agent's current_session dict (contains messages, trace)
            model: Model name string
        """
        if not self.enable_sessions:
            return

        # Initialize file on first turn (lazy initialization)
        if self.eval_data is None:
            self._init_eval_file(user_input)

        # Aggregate from trace
        trace = session.get('trace', [])
        llm_calls = [t for t in trace if t.get('type') == 'llm_call']
        tool_calls = [t for t in trace if t.get('type') == 'tool_result']

        total_tokens = sum(
            (t.get('usage').input_tokens + t.get('usage').output_tokens)
            for t in llm_calls if t.get('usage')
        )
        total_cost = sum(
            t.get('usage').cost
            for t in llm_calls if t.get('usage')
        )

        # Build metadata as compact JSON string
        meta = json.dumps({
            "tokens": total_tokens,
            "cost": round(total_cost, 4),
            "duration_ms": int(duration_ms),
            "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })

        # Build turn data for this run
        run_data = {
            'run': self.current_run,
            'output': result,
            'tools_called': [self._format_tool_call(t) for t in tool_calls],
            'expected': session.get('expected', ''),
            'evaluation': session.get('evaluation', ''),
            'meta': meta
        }

        # Find or create turn entry
        turn_index = session.get('turn', 1) - 1  # 0-indexed
        turns = self.eval_data['turns']

        if turn_index < len(turns):
            # Existing turn - add to history
            existing_turn = turns[turn_index]
            if existing_turn.get('input') == user_input:
                # Same input - this is a new run
                history = existing_turn.get('history', [])
                # Move current run to history (metadata only)
                if existing_turn.get('run'):
                    history.insert(0, {
                        'run': existing_turn.get('run', self.current_run - 1),
                        'status': existing_turn.get('evaluation', ''),
                        'meta': existing_turn.get('meta', '')
                    })
                # Update with new run data
                existing_turn.update({
                    'run': run_data['run'],
                    'output': run_data['output'],
                    'tools_called': run_data['tools_called'],
                    'expected': run_data['expected'],
                    'evaluation': run_data['evaluation'],
                    'meta': run_data['meta'],
                    'history': history
                })
            else:
                # Different input at same position - shouldn't happen normally
                turns.append({
                    'input': user_input,
                    **run_data,
                    'history': []
                })
        else:
            # New turn
            turns.append({
                'input': user_input,
                **run_data,
                'history': []
            })

        # Update metadata
        self.eval_data['updated'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.eval_data['model'] = model

        # Write run YAML with messages
        self._write_run_yaml(
            messages=session.get('messages', []),
            model=model,
            tokens=total_tokens,
            cost=total_cost,
            duration_ms=duration_ms
        )

        # Write YAML
        self._write_eval()

    def _write_run_yaml(self, messages: List[Dict], model: str, tokens: int, cost: float, duration_ms: float):
        """Write run metadata and messages to YAML file.

        Args:
            messages: List of message dicts
            model: Model name
            tokens: Total tokens used
            cost: Total cost
            duration_ms: Duration in milliseconds
        """
        if not self.eval_dir:
            return

        import os
        import sys

        # Extract system prompt from messages
        system_prompt = ""
        for msg in messages:
            if msg.get('role') == 'system':
                system_prompt = msg.get('content', '')
                break

        # Get agent file path (the script being run)
        agent_file = sys.argv[0] if sys.argv else ""
        # Make it relative to cwd if possible
        cwd = os.getcwd()
        if agent_file and os.path.isabs(agent_file):
            try:
                agent_file = os.path.relpath(agent_file, cwd)
            except ValueError:
                pass  # Keep absolute if on different drive (Windows)

        # Format messages as pretty JSON (one message per line)
        messages_json_lines = []
        for msg in messages:
            messages_json_lines.append("  " + json.dumps(msg, ensure_ascii=False))
        messages_formatted = "[\n" + ",\n".join(messages_json_lines) + "\n]"

        # Build run data
        run_data = {
            'agent': agent_file,
            'system_prompt': system_prompt,
            'model': model,
            'cwd': cwd,
            'tokens': tokens,
            'cost': round(cost, 4),
            'duration_ms': int(duration_ms),
            'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'messages': messages_formatted
        }

        # Write YAML with messages as literal block
        run_file = self.eval_dir / f"run_{self.current_run}.yaml"
        with open(run_file, 'w', encoding='utf-8') as f:
            # Write metadata fields normally
            for key in ['agent', 'system_prompt', 'model', 'cwd', 'tokens', 'cost', 'duration_ms', 'timestamp']:
                value = run_data[key]
                if isinstance(value, str) and '\n' in value:
                    f.write(f"{key}: |\n")
                    for line in value.split('\n'):
                        f.write(f"  {line}\n")
                elif isinstance(value, str):
                    # Quote strings that might have special chars
                    f.write(f"{key}: {json.dumps(value)}\n")
                else:
                    f.write(f"{key}: {value}\n")
            # Write messages as literal block
            f.write("messages: |\n")
            for line in messages_formatted.split('\n'):
                f.write(f"  {line}\n")

    def _write_eval(self):
        """Write eval data to YAML file."""
        if not self.eval_file or not self.eval_data:
            return

        # Build ordered output
        ordered = {
            'name': self.eval_data['name'],
            'created': self.eval_data['created'],
            'updated': self.eval_data.get('updated', ''),
            'runs': self.eval_data['runs'],
            'model': self.eval_data['model'],
            'turns': self.eval_data['turns']
        }

        with open(self.eval_file, 'w', encoding='utf-8') as f:
            yaml.dump(ordered, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    def get_eval_path(self) -> Optional[str]:
        """Get the path to the current eval file.

        Returns:
            Path string like '.co/evals/what_is_25_x_4.yaml' or None
        """
        if self.eval_file:
            return str(self.eval_file)
        return None

    def load_messages(self, run: Optional[int] = None) -> list:
        """Load messages from run YAML file.

        Args:
            run: Run number to load (default: current run)

        Returns:
            List of message dicts
        """
        if not self.eval_dir:
            return []

        run_num = run or self.current_run
        run_file = self.eval_dir / f"run_{run_num}.yaml"

        if not run_file.exists():
            # Try legacy JSONL format
            jsonl_file = self.eval_dir / f"run_{run_num}.jsonl"
            if jsonl_file.exists():
                messages = []
                with open(jsonl_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        if line.strip():
                            messages.append(json.loads(line))
                return messages
            return []

        with open(run_file, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)

        messages_str = data.get('messages', '[]')
        return json.loads(messages_str)

    def load_session(self) -> dict:
        """Load eval data from file."""
        if not self.eval_file or not self.eval_file.exists():
            return {'turns': [], 'runs': 0}
        with open(self.eval_file, 'r') as f:
            return yaml.safe_load(f) or {'turns': [], 'runs': 0}
