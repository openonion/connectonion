"""
Purpose: AI coding agent CLI command with resumable machine-readable one-shot runs
LLM-Note:
  Dependencies: imports from [cli/co_ai/main.py, cli/co_ai/agent.py] | imported by [cli/main.py] | no direct tests
  Data flow: CLI args → start_server() or agent.input() for one-shot
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

console = Console()


def handle_ai(
    prompt: str = None,
    port: int = 8000,
    model: str = DEFAULT_MODEL,
    max_iterations: int = 100,
    full_access: bool = False,
    full_access_turns: int = 100,
    evaluate: bool = False,
    json_output: bool = False,
    resume: str = None,
):
    """Start AI coding agent or run one-shot prompt.

    Args:
        prompt: One-shot prompt (runs and exits)
        port: Port for web server
        model: LLM model to use
        max_iterations: Max tool iterations
        full_access: Bypass tool approvals for a bounded user-driven turn budget
        full_access_turns: User-driven turns before expiry to Auto
        evaluate: Score completion with the eval debugging plugin
        json_output: Emit one JSON envelope to stdout
        resume: Continue a prior one-shot session ID

    Examples:
        co ai                                    # Start web server
        co ai "Create a calculator agent"        # One-shot
    """
    if not prompt and (json_output or resume):
        message = "--json and --resume require a one-shot prompt"
        if json_output:
            _print_envelope(None, None, message)
        else:
            console.print(f"[red]{message}[/red]")
        raise typer.Exit(2)

    if resume and not json_output:
        console.print("[red]--resume requires --json[/red]")
        raise typer.Exit(2)

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

    agent = agent_factory(model, max_iterations, full_access, full_access_turns)
    if prompt:
        _handle_plain_one_shot(agent, prompt)
    else:
        from ..co_ai.main import start_server
        start_server(
            agent,
            port=port,
            model=model,
            max_iterations=max_iterations,
            full_access=full_access,
            full_access_turns=full_access_turns,
            agent_factory=agent_factory,
        )


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
    print("\n" + result)


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
        _print_envelope(error_session_id, None, str(exc))
        raise typer.Exit(1) from None
    _print_envelope(session_id, result, None)


def _fresh_session(agent, session_id: str) -> dict:
    return {
        "session_id": session_id,
        "messages": [{"role": "system", "content": agent.system_prompt}],
        "trace": [],
        "turn": 0,
        "plan": [],
    }


def _print_envelope(session_id, result, error) -> None:
    envelope = {"session_id": session_id, "result": result, "error": error}
    print(json.dumps(envelope, ensure_ascii=False, separators=(",", ":")))
