"""
Purpose: AI coding agent CLI command with resumable machine-readable one-shot runs
LLM-Note:
  Dependencies: imports from [cli/co_ai/main.py, cli/co_ai/agent.py] | imported by [cli/main.py] | no direct tests
  Data flow: CLI args → validate invocation invite → start_server() or agent.input() for one-shot
  Integration: exposes handle_ai() | called from main.py as 'co ai' command
  Errors: known LLM provider failures print one actionable message and exit 1; programmer errors still propagate with their traceback
"""

import json
import sys
from contextlib import nullcontext, redirect_stdout
from functools import partial
from pathlib import Path

import typer
from rich.console import Console

from ...core.usage import DEFAULT_MODEL
from ..co_ai import harness as _harness

console = Console()


def handle_ai(
    prompt: str = None,
    port: int = 8000,
    model: str | None = None,
    max_iterations: int = 100,
    full_access: bool = False,
    full_access_turns: int = 100,
    evaluate: bool = False,
    json_output: bool = False,
    resume: str = None,
    invite_code: str = None,
    invite_code_file: Path = None,
    listen: list | None = None,
    harness: str = _harness.OURS,
    sandbox: str = _harness.DEFAULT_SANDBOX,
    permission_mode: str = "default",
    timeout: int = 600,
):
    """Start AI coding agent or run one-shot prompt.

    Args:
        prompt: One-shot prompt (runs and exits)
        port: Port for web server
        model: LLM model to use; None means this harness's own default
        max_iterations: Max tool iterations
        full_access: Bypass tool approvals for a bounded user-driven turn budget
        full_access_turns: User-driven turns before expiry to Auto
        evaluate: Score completion with the eval debugging plugin
        json_output: Emit one JSON envelope to stdout
        resume: Continue a prior one-shot session ID
        invite_code: In-memory invite code for this web-server run
        invite_code_file: File containing this web-server run's invite code
        listen: Channels to answer, overriding .co/host.yaml; [] answers none
        harness: Which agent loop runs the task: ours, codex, or claude-code
        sandbox: What a delegated Codex run may write: read-only,
            workspace-write (cwd + TMPDIR), or danger-full-access
        permission_mode: Claude Code's headless permission mode; default is manual

    Examples:
        co ai                                    # Start web server
        co ai "Create a calculator agent"        # One-shot
        co ai --listen feishu                    # Override host.yaml for one run
    """
    if invite_code is not None and invite_code_file is not None:
        console.print(
            "[red]--invite-code and --invite-code-file cannot be combined[/red]"
        )
        raise typer.Exit(2)

    if prompt and (invite_code is not None or invite_code_file is not None):
        console.print(
            "[red]Invite-code options are only available in web-server mode[/red]"
        )
        raise typer.Exit(2)

    runtime_invite_code = _read_runtime_invite_code(invite_code, invite_code_file)

    if harness != _harness.OURS or harness not in _harness.HARNESSES:
        _handle_delegated(harness, prompt, model, json_output, sandbox, timeout,
                          permission_mode)
        return

    if permission_mode != "default":
        console.print("[red]--permission-mode applies only to --harness claude-code.[/red]")
        raise typer.Exit(2)

    model = model or DEFAULT_MODEL

    if not prompt and (json_output or resume):
        message = "--json and --resume require a one-shot prompt"
        if json_output:
            _print_envelope(None, None, "error", message)
        else:
            console.print(f"[red]{message}[/red]")
        raise typer.Exit(2)

    if resume and not json_output:
        console.print("[red]--resume requires --json[/red]")
        raise typer.Exit(2)

    # Before anything that needs a key or a model: a typo in host.yaml should
    # be answered by the typo, not by whatever fails next.
    channels = [] if prompt else _channels(listen)

    # The web server owns turn-by-turn evaluation separately. ``--eval`` is a
    # one-shot option; attaching it to the long-lived browser agent makes every
    # browser turn bill an eval model and leaks that plugin into server tests.
    agent_factory = _agent_factory(evaluate=evaluate and bool(prompt))

    if prompt and json_output:
        _handle_json_one_shot(
            prompt,
            model,
            max_iterations,
            full_access,
            full_access_turns,
            resume,
            agent_factory=agent_factory,
        )
        return

    # One-shot Full access is selected before the prompt. A web Host only
    # advertises the ceiling and keeps every fresh session in Auto.
    agent = agent_factory(
        model,
        max_iterations,
        full_access if prompt else False,
        full_access_turns,
    )
    if prompt:
        _handle_plain_one_shot(agent, prompt)
    else:
        _start_listening(channels, agent_factory, model, max_iterations, full_access_turns)
        from ..co_ai.main import start_server
        start_server(
            agent,
            port=port,
            model=model,
            max_iterations=max_iterations,
            full_access=full_access,
            full_access_turns=full_access_turns,
            agent_factory=agent_factory,
            invite_code=runtime_invite_code,
        )


def _handle_delegated(harness, prompt, model, json_output, sandbox, timeout=600,
                      permission_mode="default") -> None:
    """Hand the whole task to a native coding agent, spending none of our tokens.

    This is the point of the flag: reaching Codex used to cost a full turn of
    our own model first, purely to have it decide to call the codex tool.
    """
    problem = (_harness.validate(harness, model) or _harness.validate_sandbox(harness, sandbox)
               or _harness.validate_permission(harness, permission_mode))
    if not problem and not prompt:
        # There is no web server to hand over: a delegate answers one task and exits.
        problem = f"--harness {harness} needs a one-shot prompt."
    if problem:
        if json_output:
            _print_envelope(None, None, "error", problem)
        else:
            console.print(f"[red]{problem}[/red]")
        raise typer.Exit(2)

    try:
        # An unset --model means "your default", not ours, which names nothing
        # in the delegate's catalogue.
        answer = _harness.run(harness, prompt, model or "", sandbox=sandbox, timeout=timeout,
                              permission_mode=permission_mode)
    except ValueError as exc:  # skill missing, or its requirements are not met
        if json_output:
            _print_envelope(None, None, "error", str(exc))
        else:
            console.print(f"[red]{exc}[/red]")
        raise typer.Exit(2) from None

    if json_output:
        _print_envelope(answer.get("session_id"), answer["result"], answer["outcome"],
                        answer["error"], usage=answer["usage"])
    elif answer["error"]:
        console.print(f"[red]{answer['error']}[/red]")
    else:
        console.print(answer["result"] or "")
    if answer["outcome"] != "natural":
        raise typer.Exit(1)


def _channels(override):
    """Which channels to answer, from ~/.co/host.yaml unless a flag overrides.

    ~/.co is where co ai keeps the rest of its configuration and where the
    inbox directories live: a chat application belongs to a person, not to
    whichever directory the terminal happens to be in.
    """
    from ...inbox.settings import configured_channels
    from ..co_ai.agent import GLOBAL_CO_DIR

    try:
        return configured_channels(GLOBAL_CO_DIR, override=override)
    except ValueError as error:
        # Starting with no channels would look exactly like starting with
        # them, right up until somebody wonders why the bot is ignoring them.
        console.print(f"[red]{error}[/red]")
        raise typer.Exit(2)


def _start_listening(channels, agent_factory, model, max_iterations, full_access_turns) -> None:
    """Answer those channels in the background.

    Chat gets an agent of its own rather than the web server's: a message from
    a group and a question typed in the browser are two conversations, and one
    Agent object holds one history.
    """
    import threading

    if not channels:
        return

    from ..co_ai.listen import listen as consume

    def build():
        return agent_factory(model, max_iterations, False, full_access_turns)

    threading.Thread(target=consume, args=(channels, build), daemon=True,
                     name="co-ai-listen").start()
    console.print(f"[dim]answering {', '.join(c.provider for c in channels)}[/dim]")


def _read_runtime_invite_code(invite_code, invite_code_file) -> str | None:
    """Resolve a web-server invite without persisting or exporting it."""
    if invite_code_file is not None:
        path = Path(invite_code_file).expanduser()
        try:
            if not path.is_file():
                raise OSError("not a regular file")
            invite_code = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            console.print(f"[red]Cannot read --invite-code-file: {exc}[/red]")
            raise typer.Exit(2) from None

    if invite_code is None:
        return None

    invite_code = invite_code.strip()
    if not invite_code:
        console.print("[red]Invite code cannot be empty[/red]")
        raise typer.Exit(2)
    if "\n" in invite_code or "\r" in invite_code:
        console.print("[red]Invite code must be a single line[/red]")
        raise typer.Exit(2)
    return invite_code


def _agent_factory(*, evaluate: bool):
    """Configure optional behavior once, before selecting a runtime mode."""
    extra_plugins = ()
    if evaluate:
        from ...useful_plugins import eval as eval_plugin

        extra_plugins = (eval_plugin,)
    return partial(_create_agent, extra_plugins=extra_plugins)


def _create_agent(
    model,
    max_iterations,
    full_access,
    full_access_turns,
    *,
    resumable=False,
    state_dir: Path | None = None,
    extra_plugins=(),
):
    from ..co_ai.agent import GLOBAL_CO_DIR, create_agent

    return create_agent(
        model=model,
        max_iterations=max_iterations,
        co_dir=GLOBAL_CO_DIR,
        state_dir=state_dir,
        full_access_turns=full_access_turns if full_access else None,
        background_tools=not resumable,
        extra_plugins=extra_plugins,
    )


def _handle_plain_one_shot(agent, prompt: str) -> None:
    from ...core.exceptions import LLMProviderError

    try:
        result = agent.input(prompt)
    except LLMProviderError as exc:
        console.print(f"\n[red]✗ Model request failed:[/red] {exc}\n")
        raise typer.Exit(1) from None
    outcome = _completed_outcome(agent)
    print("\n" + result)
    if outcome == "max_iterations":
        raise typer.Exit(1)


def _handle_json_one_shot(
    prompt,
    model,
    max_iterations,
    full_access,
    full_access_turns,
    resume,
    *,
    agent_factory=None,
    persist_session=True,
):
    session_id = resume if persist_session else None
    # Bound before the try so a failure that happened *after* some LLM calls
    # still reports what those cost. A run that burned tokens and then crashed
    # is not a free run, and the caller settling the bill cannot see the trace.
    agent = None
    try:
        with redirect_stdout(sys.stderr):
            from ..co_ai.agent import GLOBAL_CO_DIR
            from ..co_ai.one_shot_sessions import (
                capture_tool_state,
                load_snapshot,
                new_session_id,
                restore_tool_state,
                save_snapshot,
                session_lock,
            )

            if resume and not persist_session:
                raise ValueError("A transient one-shot run cannot resume a session.")
            lock = session_lock(GLOBAL_CO_DIR, resume) if resume else nullcontext()
            with lock:
                # Loading validates the project cwd before agent construction reads
                # project instructions or grants tools access to the filesystem.
                session, tools = (
                    load_snapshot(GLOBAL_CO_DIR, resume) if resume else (None, {})
                )
                factory = agent_factory or _create_agent
                agent = factory(
                    model,
                    max_iterations,
                    full_access,
                    full_access_turns,
                    resumable=True,
                )
                restore_tool_state(agent, tools)
                if session is None:
                    runtime_session_id = new_session_id()
                    session = _fresh_session(agent, runtime_session_id)
                    if persist_session:
                        session_id = runtime_session_id
                result = agent.input(prompt, session=session)
                if persist_session:
                    agent.current_session["session_id"] = session_id
                    save_snapshot(
                        GLOBAL_CO_DIR, agent.current_session, capture_tool_state(agent)
                    )
    except Exception as exc:
        error_session_id = resume if persist_session else None
        _print_envelope(error_session_id, None, "error", str(exc), agent)
        raise typer.Exit(1) from None
    outcome = _completed_outcome(agent)
    _print_envelope(session_id, result, outcome, None, agent)
    if outcome == "max_iterations":
        raise typer.Exit(1)


def _fresh_session(agent, session_id: str) -> dict:
    return {
        "session_id": session_id,
        "messages": [{"role": "system", "content": agent.system_prompt}],
        "trace": [],
        "turn": 0,
        "plan": [],
    }


def _completed_outcome(agent) -> str:
    """Return the canonical terminal reason for the latest completed turn."""

    for event in reversed(agent.current_session["trace"]):
        if event.get("type") != "turn_result":
            continue
        outcome = event.get("reason")
        if outcome not in {"natural", "max_iterations"}:
            raise RuntimeError(f"Unexpected completed turn outcome: {outcome!r}")
        return outcome
    raise RuntimeError("Completed Agent turn has no turn_result outcome")


def _turn_usage(agent) -> dict | None:
    """What this turn cost, sliced to this turn.

    A caller that shells out to `co ai --json` has no other way to know: the
    figure the terminal prints goes to stderr-shaped console output, and the
    session YAML records `tokens` as one scalar, which cannot answer "how much
    of that was cached". The trace carries the split, so the envelope can too.

    Sliced by `current_turn_trace`, not summed over the whole trace: a `--resume`
    run carries the earlier turns' `llm_result` entries in the same list, and
    billing this turn for those would overstate every resumed run.
    """
    if agent is None:
        return None
    from ...core.trace import current_turn_trace
    from ...core.usage import turn_usage_from_trace

    session = getattr(agent, "current_session", None) or {}
    return turn_usage_from_trace(
        current_turn_trace(session.get("trace", []), session.get("turn"))
    )


def _print_envelope(session_id, result, outcome, error, agent=None, usage=None) -> None:
    envelope = {
        "session_id": session_id,
        "result": result,
        "outcome": outcome,
        "error": error,
        # None when nothing measured — an all-zero usage would read as "free".
        # A delegated harness reports its own; only our loop has a trace to read.
        "usage": usage if usage is not None else _turn_usage(agent),
    }
    print(json.dumps(envelope, ensure_ascii=False, separators=(",", ":")))
