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

import typer
from rich.console import Console

console = Console()


def handle_ai(
    prompt: str = None,
    port: int = 8000,
    model: str = "co/claude-opus-4-5",
    max_iterations: int = 100,
    yolo: bool = False,
    yolo_turns: int = 100,
    json_output: bool = False,
    resume: str = None,
):
    """Start AI coding agent or run one-shot prompt.

    Args:
        prompt: One-shot prompt (runs and exits)
        port: Port for web server
        model: LLM model to use
        max_iterations: Max tool iterations
        yolo: Skip tool approvals and keep working across turns
        yolo_turns: Maximum autonomous turns before a checkpoint
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

    if prompt and json_output:
        _handle_json_one_shot(
            prompt, model, max_iterations, yolo, yolo_turns, resume
        )
        return

    agent = _create_agent(model, max_iterations, yolo, yolo_turns)
    if prompt:
        _handle_plain_one_shot(agent, prompt)
    else:
        from ..co_ai.main import start_server
        start_server(agent, port=port)


def _create_agent(model, max_iterations, yolo, yolo_turns, *, resumable=False):
    from ..co_ai.agent import GLOBAL_CO_DIR, create_agent

    return create_agent(
        model=model,
        max_iterations=max_iterations,
        co_dir=GLOBAL_CO_DIR,
        yolo_turns=yolo_turns if yolo else None,
        background_tools=not resumable,
    )


def _handle_plain_one_shot(agent, prompt: str) -> None:
    from ...core.exceptions import LLMProviderError

    try:
        result = agent.input(prompt)
    except LLMProviderError as exc:
        console.print(f"\n[red]✗ Model request failed:[/red] {exc}\n")
        raise typer.Exit(1) from None
    print("\n" + result)


def _handle_json_one_shot(prompt, model, max_iterations, yolo, yolo_turns, resume):
    session_id = resume
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

            lock = session_lock(GLOBAL_CO_DIR, resume) if resume else nullcontext()
            with lock:
                # Loading validates the project cwd before agent construction reads
                # project instructions or grants tools access to the filesystem.
                session, tools = (
                    load_snapshot(GLOBAL_CO_DIR, resume) if resume else (None, {})
                )
                agent = _create_agent(
                    model, max_iterations, yolo, yolo_turns, resumable=True
                )
                restore_tool_state(agent, tools)
                if session is None:
                    session_id = new_session_id()
                    session = _fresh_session(agent, session_id)
                result = agent.input(prompt, session=session)
                agent.current_session["session_id"] = session_id
                save_snapshot(
                    GLOBAL_CO_DIR, agent.current_session, capture_tool_state(agent)
                )
    except Exception as exc:
        _print_envelope(resume, None, str(exc))
        raise typer.Exit(1) from None
    _print_envelope(session_id, result, None)


def _fresh_session(agent, session_id: str) -> dict:
    return {
        "session_id": session_id,
        "messages": [{"role": "system", "content": agent.system_prompt}],
        "trace": [],
        "turn": 0,
    }


def _print_envelope(session_id, result, error) -> None:
    envelope = {"session_id": session_id, "result": result, "error": error}
    print(json.dumps(envelope, ensure_ascii=False, separators=(",", ":")))
