"""
Purpose: Orchestrate AI agent execution with LLM calls, tool execution, and automatic logging
LLM-Note:
  Dependencies: imports from [llm.py, tool_factory.py, prompts.py, decorators.py, logger.py, tool_executor.py, tool_registry.py, wire_events.py] | imported by [__init__.py, debug_agent/__init__.py] | tested by [tests/unit/test_agent.py, tests/test_agent_prompts.py, tests/test_agent_workflows.py, tests/unit/test_wire_events.py]
  Data flow: receives user prompt: str from Agent.input() → creates/extends current_session with messages → calls llm.complete() with tool schemas → receives LLMResponse with tool_calls → executes tools via tool_executor.execute_and_record_tools() → appends tool results to messages → repeats loop until no tool_calls or max_iterations → logger logs to .co/logs/{name}.log and .co/evals/{name}.yaml → returns final response: str
  State/Effects: modifies self.current_session['messages', 'trace', 'turn', 'iteration'] | writes to .co/logs/{name}.log and .co/evals/ via logger.py | streams a detached OIP-normalized copy without changing canonical trace statuses
  Integration: exposes Agent(name, tools, system_prompt, model, log, quiet), .input(prompt), .execute_tool(name, args), .add_tool(func), .remove_tool(name), .list_tools(), .reset_conversation() | tools stored in ToolRegistry with attribute access (agent.tools.tool_name) and instance storage (agent.tools.gmail) | tool execution delegates to tool_executor module | log defaults to .co/logs/ (None), can be True (current dir), False (disabled), or custom path | quiet=True suppresses console but keeps eval logging | trust enforcement moved to host() for network access control
  Performance: max_iterations=100 default (configurable per-input) | session state persists across turns for multi-turn conversations | ToolRegistry provides O(1) tool lookup via .get() or attribute access
  Errors: LLM errors bubble up | tool execution errors captured in trace and returned to LLM for retry
"""

import base64
import os
import time
from contextlib import suppress
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Union
from uuid import uuid4

from ..logger import Logger
from ..prompts import load_system_prompt
from .events import EventHandler
from .interrupt import InterruptibleStepTimeout, run_interruptible
from .llm import LLM, TokenUsage, create_llm
from .mode import FULL_ACCESS, full_access_turns_left, mode_of, set_mode
from .provider_messages import messages_for_provider
from .tool_executor import execute_and_record_tools, execute_single_tool
from .tool_factory import create_tool_from_function, extract_methods_from_instance, is_class_instance
from .tool_registry import ToolRegistry
from .usage import DEFAULT_MODEL, get_context_limit, turn_usage_from_trace
from .wire_events import normalize_wire_event

_REMOVED_MODE_FIELDS = {
    "approval_profile",
    "full_access_prompt",
    "full_access_turns",
    "full_access_turns_used",
    "permission_profile",
    "skip_tool_approval",
    "ulw_prompt",
    "ulw_turns",
    "ulw_turns_used",
    "workflow_mode",
}

_POST_PROVIDER_LLM_TIMEOUT_SECONDS = 90.0
_NATIVE_PROVIDER_TOOL_NAMES = frozenset({"claude_code", "codex"})


def _has_unsettled_native_provider_result(trace: list[dict[str, Any]]) -> bool:
    """Whether the latest model decision completed native-provider work.

    The durable trace is the hosted runtime's authoritative record.  Scan only
    back to the latest LLM call: an older provider result must not put an
    unrelated later tool batch on the settlement deadline.
    """
    for entry in reversed(trace):
        if entry.get("type") == "llm_call":
            return False
        if (
            entry.get("type") == "tool_result"
            and entry.get("name") in _NATIVE_PROVIDER_TOOL_NAMES
        ):
            return True
    return False


def _normalized_runtime_mode_session(session: Mapping[str, Any]) -> dict[str, Any]:
    """Apply the 1.7 schema boundary without translating old authority."""

    normalized = dict(session)
    canonical = mode_of(normalized)
    remaining = full_access_turns_left(normalized)
    for field in _REMOVED_MODE_FIELDS:
        normalized.pop(field, None)
    if canonical == FULL_ACCESS:
        set_mode(normalized, FULL_ACCESS, turns_left=remaining)
    else:
        set_mode(normalized, canonical)
    return normalized


def _normalized_plan(entries: Any) -> list[dict[str, str]]:
    if not isinstance(entries, list):
        raise ValueError("Plan entries must be a list")
    normalized = []
    for entry in entries:
        if not isinstance(entry, Mapping) or set(entry) != {
            "content", "priority", "status"
        }:
            raise ValueError("Plan entries must use the canonical shape")
        content = entry["content"]
        priority = entry["priority"]
        status = entry["status"]
        if not isinstance(content, str) or not content:
            raise ValueError("Plan content must be a non-empty string")
        if not isinstance(priority, str) or priority not in {
            "high", "medium", "low"
        }:
            raise ValueError(f"Unsupported plan priority: {priority!r}")
        if not isinstance(status, str) or status not in {
            "pending", "in_progress", "completed"
        }:
            raise ValueError(f"Unsupported plan status: {status!r}")
        normalized.append(dict(entry))
    return normalized


class Agent:
    """Agent that can use tools to complete tasks."""

    def __init__(
        self,
        name: str,
        llm: Optional[LLM] = None,
        tools: Optional[Union[List[Callable], Callable, Any]] = None,
        system_prompt: Union[str, Path, None] = None,
        api_key: Optional[str] = None,
        model: str = DEFAULT_MODEL,
        max_iterations: int = 100,
        log: Optional[Union[bool, str, Path]] = None,
        quiet: bool = False,
        plugins: Optional[List[List[EventHandler]]] = None,
        on_events: Optional[List[EventHandler]] = None,
        co_dir: Optional[Union[str, Path]] = None,
        state_dir: Optional[Union[str, Path]] = None,
    ):
        self.name = name
        self.co_dir = Path(co_dir) if co_dir else Path(".co")
        self.system_prompt = load_system_prompt(system_prompt)
        self.max_iterations = max_iterations

        # Current session context (runtime only)
        self.current_session = None

        # I/O to client (None locally, injected by host() for WebSocket)
        self.io = None

        # Session storage (None locally, injected by host() for persistence)
        self.storage = None

        # Token usage tracking
        self.total_cost: float = 0.0  # Cumulative cost in USD
        self.last_usage: Optional[TokenUsage] = None  # From most recent LLM call

        # Initialize logger (unified: terminal + file + YAML evals)
        # Environment override stays highest priority for the legacy path. An
        # explicit state root is an isolation boundary, so hidden process state
        # must not redirect its file log outside that root.
        effective_log = log
        if state_dir is None and os.getenv('CONNECTONION_LOG'):
            effective_log = Path(os.getenv('CONNECTONION_LOG'))

        self.logger = Logger(
            agent_name=name,
            quiet=quiet,
            log=effective_log,
            co_dir=state_dir if state_dir is not None else co_dir,
        )

        # Initialize event registry
        # Note: before_each_tool/after_each_tool fire for EACH tool
        # before_tools/after_tools fire ONCE per batch (safe for adding messages)
        self.events = {
            'on_agent_ready': [],      # Fires once during initialization when agent is ready
            'after_user_input': [],
            'before_iteration': [],    # Start of each iteration (poll IO, mode changes)
            'after_iteration': [],     # End of each iteration (metrics, checkpoints)
            'before_llm': [],
            'after_llm': [],
            'before_each_tool': [],    # Fires before EACH tool
            'before_tools': [],        # Fires ONCE before ALL tools in a batch
            'after_each_tool': [],     # Fires after EACH tool (don't add messages here!)
            'after_tools': [],         # Fires ONCE after ALL tools (safe for messages)
            'on_error': [],
            'on_complete': [],
            'on_stop_signal': []
        }

        # Register plugin events (flatten list of lists)
        if plugins:
            for event_list in plugins:
                for event_func in event_list:
                    self._register_event(event_func)

        # Register custom event handlers (supports both single functions and lists)
        if on_events:
            for item in on_events:
                if isinstance(item, list):
                    # Multiple handlers: before_tool(fn1, fn2) returns [fn1, fn2]
                    for fn in item:
                        self._register_event(fn)
                else:
                    # Single handler: @before_tool or before_tool(fn)
                    self._register_event(item)

        # Process tools: convert raw functions and class instances to tool schemas automatically
        self.tools = ToolRegistry()

        if tools is not None:
            tools_list = tools if isinstance(tools, list) else [tools]

            for tool in tools_list:
                if is_class_instance(tool):
                    # Store instance (agent.tools.gmail.my_id)
                    class_name = tool.__class__.__name__.lower()
                    self.tools.add_instance(class_name, tool)

                    # Extract methods as tools (agent.tools.send())
                    for method_tool in extract_methods_from_instance(tool):
                        self.tools.add(method_tool)
                elif callable(tool):
                    if not hasattr(tool, 'to_function_schema'):
                        processed = create_tool_from_function(tool)
                    else:
                        processed = tool
                    self.tools.add(processed)

        # Initialize LLM
        if llm:
            self.llm = llm
        else:
            # Use factory function to create appropriate LLM based on model
            # Each LLM provider checks its own env var if api_key is None:
            # - OpenAI models check OPENAI_API_KEY
            # - Anthropic models check ANTHROPIC_API_KEY
            # - Google models check GOOGLE_API_KEY
            # - co/ models check OPENONION_API_KEY
            self.llm = create_llm(model=model, api_key=api_key)

        # Fire on_agent_ready event (agent is fully initialized and ready to use)
        # Plugins can: add tools, modify system_prompt, initialize state
        self._invoke_events('on_agent_ready')

        # Print banner (if console enabled)
        if self.logger.console:
            # Determine log_dir if logging is enabled
            log_dir = ".co/" if self.logger.enable_sessions else None
            self.logger.console.print_banner(
                agent_name=self.name,
                model=self.llm.model,
                tools=len(self.tools),
                log_dir=log_dir,
                llm=self.llm,
                skills=getattr(self, 'skills', []),
            )

    def _next_trace_id(self) -> str:
        """Generate unique trace entry ID (UUID)."""
        import uuid
        return str(uuid.uuid4())

    def _record_plan(self, entries: list[Mapping[str, Any]]) -> None:
        """Persist and stream one canonical complete plan replacement."""
        if not isinstance(self.current_session, dict):
            return
        normalized = _normalized_plan(entries)
        self.current_session["plan"] = [dict(entry) for entry in normalized]
        self._record_trace({
            "type": "plan",
            "entries": [dict(entry) for entry in normalized],
        })

    def _record_trace(
        self,
        entry: dict,
        *,
        wire_extras: Optional[dict] = None,
    ) -> None:
        """Record trace entry and stream to io if connected.

        This is the single place where trace entries are recorded.
        Ensures both local trace and remote streaming stay in sync.
        Also includes current session state so client can persist it
        (client-side is source of truth for session state).
        """
        if 'id' not in entry:
            entry['id'] = self._next_trace_id()
        if 'ts' not in entry:
            entry['ts'] = time.time()

        self.current_session['trace'].append(entry)

        if self.io:
            # Wire-only fields belong on a separate top-level object. The
            # canonical entry is already in trace and is what session_sync
            # persists. Sharing one object and deleting fields after send would
            # race asynchronous transports.
            # Canonical correlation and status fields always win collisions.
            wire_entry = normalize_wire_event(
                {**wire_extras, **entry} if wire_extras else entry
            )
            # Send entry first (without session to avoid circular ref)
            send_persisted_trace = getattr(
                self.io, "_send_persisted_trace", self.io.send
            )
            send_persisted_trace(wire_entry)
            # Then send session sync separately
            self.io.send({
                'type': 'session_sync',
                'session': self.current_session,
            })

    def _invoke_events(self, event_type: str):
        """Invoke all event handlers for given type. Exceptions propagate (fail fast)."""
        for handler in self.events.get(event_type, []):
            handler(self)

    def _register_event(self, event_func: EventHandler):
        """
        Register a single event handler to appropriate event type.

        Args:
            event_func: Event handler wrapped with after_llm(), after_tool(), etc.

        Raises:
            TypeError: If event handler is not callable
            ValueError: If event handler missing _event_type or invalid event type
        """
        # First check if it's callable (type validation)
        if not callable(event_func):
            raise TypeError(f"Event must be callable, got {type(event_func).__name__}")

        # Then check if it has _event_type attribute (wrapper validation)
        event_type = getattr(event_func, '_event_type', None)
        if not event_type:
            func_name = getattr(event_func, '__name__', str(event_func))
            raise ValueError(
                f"Event handler '{func_name}' missing _event_type. "
                f"Did you forget to wrap it? Use after_llm({func_name}), etc."
            )

        # Finally check if it's a valid event type (value validation)
        if event_type not in self.events:
            raise ValueError(f"Invalid event type: {event_type}")

        self.events[event_type].append(event_func)

    def input(self, prompt: str, max_iterations: Optional[int] = None,
              session: Optional[Dict] = None, images: list[str] | None = None,
              files: list[dict] | None = None,
              _upload_reservation: Any = None) -> str:
        """Provide input to the agent and get response.

        Args:
            prompt: The input prompt or data to process
            max_iterations: Override agent's max_iterations for this request
            session: Optional session to continue a conversation.
            images: Optional list of base64 data URLs for multimodal input
            files: Optional list of file dicts with keys:
                - name: filename (e.g. "report.pdf")
                - data: base64-encoded data URL (e.g. "data:application/pdf;base64,...")

        Returns:
            The agent's response after processing the input
        """
        if self.logger.console:
            self.logger.console.print_task(prompt)

        # Session restoration: if session passed, restore it (stateless API continuation)
        start_logger_session = False
        logger_session_id = None
        if session is not None:
            # Everything the caller passed, not four chosen keys. Plugins keep
            # their state here — Full access's mode and turn budget, the approval gate's
            # requester — and rebuilding from a whitelist silently dropped all of
            # it: Full access fell back to Default after a turn, and the approval gate saw
            # every requester as unknown. #191.
            #
            # Which of these keys a client is allowed to state is decided before
            # this point, in input_handler: a session arriving over the wire has
            # the server-owned ones stripped and re-applied from what the server
            # stored. Here we only restore what we were handed.
            self.current_session = _normalized_runtime_mode_session(session)
            self.current_session['session_id'] = session.get('session_id')
            self.current_session['messages'] = list(session.get('messages', []))
            self.current_session['trace'] = list(session.get('trace', []))
            self.current_session['turn'] = session.get('turn', 0)
            start_logger_session = True
            logger_session_id = session.get('session_id')
        elif self.current_session is None:
            # Initialize new session
            self.current_session = {
                'messages': [{"role": "system", "content": self.system_prompt}],
                'trace': [],
                'turn': 0  # Track conversation turns
            }
            set_mode(self.current_session, mode_of(self.current_session))
            start_logger_session = True

        # Session shape is the turn boundary: from here, preprocessing, model
        # work, hooks, and their failures all receive one terminal outcome.
        self.current_session['turn'] += 1
        self.current_session['user_prompt'] = prompt  # Store user prompt for xray/debugging
        turn_start = time.time()
        turn_trace_start = len(self.current_session['trace'])

        try:
            if start_logger_session:
                self.logger.start_session(
                    self.system_prompt,
                    session_id=logger_session_id,
                )

            # Add user message to conversation (multimodal if images provided)
            if images:
                content = [{"type": "text", "text": prompt}]
                for img in images:
                    content.append({"type": "image_url", "image_url": {"url": img}})
                self.current_session['messages'].append({"role": "user", "content": content})
            else:
                self.current_session['messages'].append({"role": "user", "content": prompt})

            # Record only after messages contains this turn. The following
            # session_sync must never expose a trace ahead of its source state.
            self._record_trace({
                'type': 'user_input',
                'content': prompt,
                'turn': self.current_session['turn'],
                'ts': turn_start,
            })

            # Save uploaded files to .co/uploads/ and build file path references.
            saved_files = []
            try:
                if files:
                    # A hosted OIP session can bind this private staging root to the
                    # authenticated principal that owns the session. Other Agent
                    # entry points retain the historical project/global .co root.
                    uploads_dir = Path(
                        getattr(self, "_upload_dir", self.logger.co_dir / "uploads")
                    )
                    uploads_dir.mkdir(parents=True, exist_ok=True)
                    pending_files = []
                    for f in files:
                        safe_name = Path(f["name"]).name
                        file_path = uploads_dir / f"{uuid4().hex}_{safe_name}"
                        data_url = f["data"]
                        if "," in data_url:
                            raw_data = base64.b64decode(data_url.split(",", 1)[1])
                        else:
                            raw_data = base64.b64decode(data_url)
                        pending_files.append((file_path, raw_data))

                    written_files = []
                    try:
                        for file_path, raw_data in pending_files:
                            file_path.write_bytes(raw_data)
                            written_files.append(file_path)
                    except BaseException:
                        # write_bytes can create a partial file before raising.
                        # UUID paths are owned by this turn, so clean every target,
                        # not only calls that returned successfully.
                        for file_path, _raw_data in pending_files:
                            with suppress(Exception):
                                file_path.unlink(missing_ok=True)
                        raise
                    saved_files = [str(path.resolve()) for path in written_files]

            finally:
                # Hosted input holds a principal quota lock only while files are
                # staged. Model work, approvals, and commits must remain concurrent.
                if _upload_reservation is not None:
                    _upload_reservation.release()

            if saved_files:
                self._record_trace({
                    'type': 'files_received',
                    'files': [{'name': Path(p).name, 'path': p} for p in saved_files],
                    'turn': self.current_session['turn'],
                    'ts': time.time(),
                })
                if self.logger.console:
                    names = [Path(path).name for path in saved_files]
                    self.logger.console.print(
                        f"  [dim]↑ {len(saved_files)} file(s): {', '.join(names)}[/dim]"
                    )
                # File paths are internal context, not part of the user's text.
                from ..useful_plugins.system_reminder import reminder_message

                file_list = "\n".join(f"- {path}" for path in saved_files)
                upload_notice = (
                    f"The user uploaded the following files:\n{file_list}\n"
                    "Use your read_file tool or other available tools to read the file "
                    "contents before responding. Do not assume or guess the contents."
                )
                self.current_session['messages'].append(
                    reminder_message(upload_notice)
                )

            # Invoke after_user_input events
            self._invoke_events('after_user_input')

            # Process
            self.current_session['iteration'] = 0  # Reset iteration for this turn
            result, reason = self._run_iteration_loop(
                max_iterations or self.max_iterations
            )

            self.current_session['result'] = result

            self._invoke_events('on_complete')
            # A broken adapter must not turn completed work into a retryable
            # failure merely because best-effort stale-signal cleanup failed.
            with suppress(Exception):
                self._drain_completed_turn_interrupt(reason)
        except BaseException as error:
            # Outcome streaming must not replace the exception that ended the
            # turn. _record_trace appends before sending, so a failing adapter
            # still leaves the local terminal entry available.
            with suppress(Exception):
                self._record_turn_result(
                    reason='error',
                    trace_start=turn_trace_start,
                    error_type=type(error).__name__,
                )
            raise

        self._record_turn_result(reason=reason, trace_start=turn_trace_start)

        # Calculate duration
        duration = time.time() - turn_start

        # Log turn to YAML eval (after on_complete so handlers can modify state)
        self.logger.log_turn(prompt, result, duration * 1000, self.current_session, self.llm.model)

        # Print completion summary (after log_turn so we have the eval path)
        if self.logger.console:
            eval_path = self.logger.get_eval_path()
            self.logger.console.print_completion(duration, self.current_session, eval_path)

        return result

    def _drain_completed_turn_interrupt(self, reason: str) -> None:
        """Discard a Stop that lost its race with already completed work."""
        if reason not in ('natural', 'max_iterations'):
            return
        if self.io and hasattr(self.io, 'receive_all'):
            self.io.receive_all('INTERRUPT')
        if self.current_session.get('stop_signal') == 'user_interrupt':
            self.current_session.pop('stop_signal', None)

    def _record_turn_result(
        self,
        *,
        reason: str,
        trace_start: int,
        error_type: str | None = None,
    ) -> None:
        """Write one structured terminal event without changing input()'s API."""
        entry = {
            'type': 'turn_result',
            'turn': self.current_session['turn'],
            'reason': reason,
            'usage': turn_usage_from_trace(
                self.current_session['trace'][trace_start:]
            ),
        }
        if error_type is not None:
            entry['error_type'] = error_type
        trace = self.current_session['trace']
        trace_length = len(trace)
        try:
            self._record_trace(entry)
        except Exception:
            # Once the local terminal entry exists, the Agent turn is complete.
            # Reporting a failed turn because only its terminal IO frame failed
            # would invite callers to retry already-committed side effects.
            if len(trace) == trace_length + 1 and trace[-1] is entry:
                return
            raise

    def reset_conversation(self):
        """Reset the conversation session. Start fresh."""
        self.current_session = None

    def execute_tool(self, tool_name: str, arguments: Optional[Dict] = None) -> Dict[str, Any]:
        """Execute a single tool by name. Useful for testing and debugging.

        Args:
            tool_name: Name of the tool to execute
            arguments: Tool arguments (default: {})

        Returns:
            Dict with: result, status, timing, name, arguments
        """
        arguments = arguments or {}

        # Create temporary session if needed
        if self.current_session is None:
            self.current_session = {
                'messages': [{"role": "system", "content": self.system_prompt}],
                'trace': [],
                'turn': 0,
                'iteration': 1,
                'user_prompt': 'Manual tool execution'
            }
            set_mode(self.current_session, mode_of(self.current_session))

        # Execute using the tool_executor
        trace_entry = execute_single_tool(
            tool_name=tool_name,
            tool_args=arguments,
            tool_id=f"manual_{tool_name}_{time.time()}",
            tools=self.tools,
            agent=self,
            logger=self.logger
        )

        # Note: trace_entry already added to session in execute_single_tool

        if trace_entry["status"] == "interrupted":
            self.current_session.pop('stop_signal', None)
            self._invoke_events('on_stop_signal')
            return {
                "name": trace_entry["name"],
                "args": trace_entry.get("args", {}),
                "result": trace_entry["result"],
                "status": trace_entry["status"],
                "timing_ms": trace_entry.get("timing_ms")
            }

        # Fire events (same as execute_and_record_tools)
        # on_error fires first for errors/not_found
        if trace_entry["status"] in ("error", "not_found"):
            self._invoke_events('on_error')

        # after_each_tool fires for this tool execution
        self._invoke_events('after_each_tool')

        # after_tools fires after all tools in batch (for single execution, fires once)
        self._invoke_events('after_tools')

        # Return simplified result (omit internal fields)
        return {
            "name": trace_entry["name"],
            "args": trace_entry.get("args", {}),
            "result": trace_entry["result"],
            "status": trace_entry["status"],
            "timing_ms": trace_entry.get("timing_ms")
        }

    def _create_initial_messages(self, prompt: str) -> List[Dict[str, Any]]:
        """Create initial conversation messages."""
        return [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": prompt}
        ]

    def _run_iteration_loop(self, max_iterations: int) -> tuple[str, str]:
        """Return the existing response string and its private terminal reason."""
        completed_tools = False
        empty_terminal_retries = 0
        provider_settlement_required = False
        provider_timeout_retries = 0
        while self.current_session['iteration'] < max_iterations:
            self.current_session['iteration'] += 1

            # Fire before_iteration (poll IO, check mode changes)
            self._invoke_events('before_iteration')

            # Hosted provider plugins publish their completed tool result into
            # the durable trace.  Re-derive the bound here as a fail-safe for
            # any observer that normalized the in-memory ToolCall after the
            # original decision.  RC9's public Work Room gate proved that the
            # post-execution-only name check was not sufficient in this path.
            if (
                not provider_settlement_required
                and _has_unsettled_native_provider_result(
                    self.current_session.get('trace', [])
                )
            ):
                provider_settlement_required = True

            # Get LLM response
            try:
                response = self._get_llm_decision(
                    timeout_seconds=(
                        _POST_PROVIDER_LLM_TIMEOUT_SECONDS
                        if provider_settlement_required
                        else None
                    )
                )
            except InterruptibleStepTimeout as error:
                if provider_settlement_required and provider_timeout_retries == 0:
                    from ..useful_plugins.system_reminder import reminder_message

                    self.current_session['messages'].append(reminder_message(
                        "The previous model call did not return within the bounded "
                        "settlement window after native provider work. Return a concise "
                        "user-facing final answer based only on the recorded tool results. "
                        "Do not claim work that those results do not prove."
                    ))
                    provider_timeout_retries += 1
                    max_iterations += 1
                    continue
                raise TimeoutError(
                    "LLM did not settle native provider tool results after one bounded retry"
                ) from error

            if response is not None:
                if not response.tool_calls:
                    content = response.content or ""
                    if content.strip():
                        self.current_session['messages'].append({
                            "role": "assistant",
                            "content": content,
                            "id": self._next_trace_id(),
                        })
                else:
                    # Arm the settlement bound from the model's immutable
                    # decision before tool execution.  The hosted co-ai path
                    # lets provider plugins and event handlers observe and
                    # normalize a call while it runs; detecting the provider
                    # only after that path returned left the real Work Room
                    # continuation unbounded even though minimal Agent tests
                    # retained the original ToolCall name.
                    native_provider_batch = any(
                        getattr(call, "name", "") in _NATIVE_PROVIDER_TOOL_NAMES
                        for call in response.tool_calls
                    )
                    if native_provider_batch:
                        provider_settlement_required = True
                    # Process tool calls
                    self._execute_and_record_tools(response.tool_calls)
                    completed_tools = True

            # Fire after_iteration
            self._invoke_events('after_iteration')

            continuing = self.current_session.get('_continue_iteration', False)
            if response is not None and not response.tool_calls and not continuing:
                # Ignore Stop frames that raced a completed terminal answer,
                # including frames received while after_iteration ran.
                if self.io and hasattr(self.io, 'receive_all'):
                    self.io.receive_all('INTERRUPT')
                if self.current_session.get('stop_signal') == 'user_interrupt':
                    self.current_session.pop('stop_signal', None)

            # Check if plugin set stop_signal (stop loop, wait for user input)
            stop_signal = self.current_session.pop('stop_signal', None)
            if stop_signal:
                self._invoke_events('on_stop_signal')
                reason = (
                    'interrupted'
                    if stop_signal in ('user_interrupt', 'Interrupted by user')
                    else 'stopped'
                )
                return "What would you like me to do?", reason

            if response is None:
                raise RuntimeError("LLM returned no response without an interrupt")

            if not response.tool_calls:
                if self.current_session.pop('_continue_iteration', False):
                    # An accepted follow-up is new work. Give it the LLM call it
                    # needs even when the original request used its full budget.
                    max_iterations += 1
                    continue
                if not content.strip():
                    if completed_tools and empty_terminal_retries == 0:
                        from ..useful_plugins.system_reminder import reminder_message

                        self.current_session['messages'].append(reminder_message(
                            "The previous model response was empty after tool execution. "
                            "Return a concise user-facing final answer based only on the "
                            "recorded tool results. Do not claim work that those results "
                            "do not prove."
                        ))
                        empty_terminal_retries += 1
                        max_iterations += 1
                        continue
                    raise RuntimeError("LLM returned an empty terminal response")
                return content, 'natural'

        # Hit max iterations
        return (
            f"Task incomplete: Maximum iterations ({max_iterations}) reached.",
            'max_iterations',
        )

    def _get_llm_decision(self, timeout_seconds: float | None = None):
        """Get the next action/decision from the LLM."""
        # Get tool schemas
        tool_schemas = [tool.to_function_schema() for tool in self.tools] if self.tools else None

        # Show request info
        if self.logger.console:
            self.logger.console.print_llm_request(self.llm.model, self.current_session, self.max_iterations)

        # Invoke before_llm events
        self._invoke_events('before_llm')

        # Generate ID for correlation between llm_call and llm_result
        llm_id = self._next_trace_id()

        # Record llm_call BEFORE calling LLM (streams to client for "thinking" indicator)
        self._record_trace({
            'type': 'llm_call',
            'id': llm_id,
            'model': self.llm.model,
            'iteration': self.current_session['iteration'],
            'status': 'running',
            **(
                {'timeout_seconds': timeout_seconds}
                if timeout_seconds is not None
                else {}
            ),
        })

        start = time.time()
        messages = messages_for_provider(self.current_session['messages'])
        try:
            response, interrupted = run_interruptible(
                lambda: self.llm.complete(messages, tools=tool_schemas),
                self.io,
                timeout_seconds=timeout_seconds,
            )
        except InterruptibleStepTimeout:
            duration = (time.time() - start) * 1000
            self._record_trace({
                'type': 'llm_result',
                'id': llm_id,
                'model': self.llm.model,
                'iteration': self.current_session['iteration'],
                'duration_ms': duration,
                'status': 'error',
                'error_type': 'TimeoutError',
            })
            raise
        duration = (time.time() - start) * 1000  # milliseconds

        if interrupted:
            self._record_trace({
                'type': 'llm_result',
                'id': llm_id,
                'model': self.llm.model,
                'iteration': self.current_session['iteration'],
                'duration_ms': duration,
                'status': 'interrupted',
            })
            self.current_session['stop_signal'] = 'user_interrupt'
            return None

        # Track token usage
        if response.usage:
            self.last_usage = response.usage
            self.total_cost += response.usage.cost

        # Record llm_result AFTER LLM completes (streams to client)
        # Convert usage to dict for JSON serialization (Pydantic objects need model_dump())
        usage_dict = (
            response.usage.model_dump(exclude_none=True)
            if response.usage else None
        )
        self._record_trace({
            'type': 'llm_result',
            'id': llm_id,
            'model': self.llm.model,
            'iteration': self.current_session['iteration'],
            'duration_ms': duration,
            'tool_calls_count': len(response.tool_calls) if response.tool_calls else 0,
            'usage': usage_dict,
            'context_percent': self.context_percent,  # Show context usage in UI
            'status': 'success',
        })

        # Invoke after_llm events (after trace entry is added)
        self._invoke_events('after_llm')

        self.logger.log_llm_response(self.llm.model, duration, len(response.tool_calls), response.usage, self.context_percent)

        return response

    def _execute_and_record_tools(self, tool_calls):
        """Execute requested tools and update conversation messages."""
        execute_and_record_tools(
            tool_calls=tool_calls,
            tools=self.tools,
            agent=self,
            logger=self.logger
        )

    def add_tool(self, tool: Callable):
        """Add a new tool to the agent."""
        if not hasattr(tool, 'to_function_schema'):
            processed_tool = create_tool_from_function(tool)
        else:
            processed_tool = tool
        self.tools.add(processed_tool)

    def remove_tool(self, tool_name: str) -> bool:
        """Remove a tool by name."""
        return self.tools.remove(tool_name)

    def list_tools(self) -> List[str]:
        """List all available tool names."""
        return self.tools.names()

    @property
    def context_percent(self) -> float:
        """Get current context window usage as percentage (0-100).

        Returns the percentage of context window used based on input_tokens
        from the last LLM call. Returns 0 if no LLM calls have been made yet.
        """
        if not self.last_usage:
            return 0.0
        limit = get_context_limit(self.llm.model)
        return (self.last_usage.input_tokens / limit) * 100

    def auto_debug(self, prompt: Optional[str] = None):
        """Start a debugging session for the agent.

        Args:
            prompt: Optional prompt to debug. If provided, runs single debug session.
                   If None, starts interactive debug mode.

        This MVP version provides:
        - Breakpoints at @xray decorated tools
        - Display of tool execution context
        - Interactive menu to continue or edit values

        Examples:
            # Interactive mode
            agent = Agent("my_agent", tools=[search, analyze])
            agent.auto_debug()

            # Single prompt mode
            agent.auto_debug("Find information about Python")
        """
        from ..debug.auto_debug import AutoDebugger
        debugger = AutoDebugger(self)
        debugger.start_debug_session(prompt)
