"""
Purpose: CLI command for running and managing evals
LLM-Note:
  Dependencies: imports from [pathlib, yaml, json, rich, importlib] | imported by [cli/main.py]
  Data flow: handle_eval() → reads .co/evals/*.yaml → imports agent → runs with stored input → compares expected vs output
  Integration: exposes handle_eval(name, run) for CLI

Eval YAML format:
  - `turns`: List of inputs to send to agent sequentially (like a conversation).
    Each turn can have one input. Turns run in order within same agent session,
    simulating multi-round conversations. Use single turn for simple evals,
    or multiple turns to test conversation flow.
"""

import importlib.util
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel
from rich.console import Console
from rich.table import Table

console = Console()


class JudgeResult(BaseModel):
    """Result from LLM judge evaluation."""
    passed: bool
    analysis: str


def get_agent_from_file(file_path: str, cwd: str):
    """Import agent instance from file."""
    from connectonion import Agent

    if not os.path.isabs(file_path):
        file_path = os.path.join(cwd, file_path)

    if cwd not in sys.path:
        sys.path.insert(0, cwd)

    spec = importlib.util.spec_from_file_location("agent_module", file_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    if hasattr(module, 'agent') and isinstance(module.agent, Agent):
        agent = module.agent
        agent.logger.enable_sessions = False  # Prevent duplicate eval files
        return agent

    raise ValueError(
        f"No 'agent' instance found in {file_path}.\n\n"
        f"Structure your file like this:\n\n"
        f"    agent = Agent(...)\n\n"
        f"    if __name__ == '__main__':\n"
        f"        agent.input('...')\n"
    )


def handle_eval(name: Optional[str] = None, agent_file: Optional[str] = None):
    """Run evals and show results.

    Args:
        name: Optional specific eval name to run
        agent_file: Optional agent file path (overrides YAML setting)
    """
    evals_dir = Path(".co/evals")

    if not evals_dir.exists():
        console.print("[yellow]No evals found.[/yellow]")
        console.print("[dim]Create eval files in .co/evals/*.yaml[/dim]")
        return

    if name:
        eval_files = list(evals_dir.glob(f"{name}.yaml"))
        if not eval_files:
            console.print(f"[red]Eval not found: {name}[/red]")
            return
    else:
        eval_files = list(evals_dir.glob("*.yaml"))

    if not eval_files:
        console.print("[yellow]No eval files found in .co/evals/[/yellow]")
        return

    _run_evals(eval_files, agent_file)

    # Reload and show status
    if name:
        eval_files = list(evals_dir.glob(f"{name}.yaml"))
    else:
        eval_files = list(evals_dir.glob("*.yaml"))

    _show_eval_status(eval_files)


def _run_evals(eval_files: list, agent_override: Optional[str] = None):
    """Run agents for each eval and capture output."""
    cwd = os.getcwd()
    agents_cache = {}  # Cache agents by file path

    for eval_file in eval_files:
        with open(eval_file) as f:
            data = yaml.safe_load(f)

        # Get agent file: CLI override > YAML > error
        agent_file = agent_override or data.get('agent')
        if not agent_file:
            console.print(f"[red]No agent specified for {eval_file.stem}[/red]")
            console.print(f"[dim]Add 'agent: agent.py' to the YAML or use --agent flag[/dim]")
            continue

        # Load agent (cached)
        if agent_file not in agents_cache:
            console.print(f"[cyan]Loading:[/cyan] {agent_file}")
            agents_cache[agent_file] = get_agent_from_file(agent_file, cwd)
        agent = agents_cache[agent_file]

        turns = data.get('turns', [])
        if not turns:
            console.print(f"[yellow]No turns found in {eval_file.stem}[/yellow]")
            continue

        console.print(f"[cyan]Running:[/cyan] {eval_file.stem}")

        # Reset agent session for fresh state each eval
        agent.reset_conversation()

        file_modified = False
        for turn in turns:
            input_text = turn.get('input', '')
            if not input_text:
                continue

            # Show input (truncated)
            display_input = input_text[:60] + "..." if len(input_text) > 60 else input_text
            console.print(f"  [dim]input:[/dim] {display_input}")

            # Run agent and capture result
            result = agent.input(input_text)

            # Extract tools_called and metrics from agent session
            trace = agent.current_session.get('trace', [])
            tool_calls = [t for t in trace if t.get('type') == 'tool_execution']
            llm_calls = [t for t in trace if t.get('type') == 'llm_call']
            tools_called = [agent.logger._format_tool_call(t) for t in tool_calls]

            total_tokens = sum(
                (t.get('usage').input_tokens + t.get('usage').output_tokens)
                for t in llm_calls if t.get('usage')
            )
            total_cost = sum(
                t.get('usage').cost for t in llm_calls if t.get('usage')
            )

            # Build history as JSON array string (compact, easy to scan)
            history_str = turn.get('history', '[]')
            history = json.loads(history_str) if isinstance(history_str, str) else []
            if turn.get('output'):
                history.insert(0, {
                    "ts": turn.get('ts', ''),
                    "pass": turn.get('pass'),
                    "tokens": turn.get('tokens', 0),
                    "cost": turn.get('cost', 0)
                })

            # Store result in turn
            turn['output'] = result
            turn['tools_called'] = tools_called
            turn['tokens'] = total_tokens
            turn['cost'] = round(total_cost, 4)
            turn['ts'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            turn['run'] = data.get('runs', 0) + 1
            # Format history as multi-line JSON for readability
            if history:
                lines = [json.dumps(h) for h in history]
                turn['history'] = "[\n" + ",\n".join(lines) + "]"
            else:
                turn['history'] = "[]"
            file_modified = True

            # Judge immediately if expected exists
            expected = turn.get('expected', '')
            if expected:
                judge = _judge_with_llm(expected, result, input_text)
                turn['pass'] = judge.passed
                turn['analysis'] = judge.analysis
                status = "[green]✓[/green]" if judge.passed else "[red]✗[/red]"
                console.print(f"  {status} {judge.analysis[:60]}...")
            else:
                # Show output (truncated)
                display_output = result[:60] + "..." if len(result) > 60 else result
                console.print(f"  [green]output:[/green] {display_output}")

        if file_modified:
            # Update runs count and save
            data['runs'] = data.get('runs', 0) + 1
            data['updated'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with open(eval_file, 'w') as f:
                yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

        console.print(f"[green]✓[/green] {eval_file.stem} completed")
        console.print()

    console.print()


def _judge_with_llm(expected: str, output: str, input_text: str) -> JudgeResult:
    """Use LLM to judge if output matches expected."""
    from connectonion import llm_do

    prompt = f"""You are an eval judge. Determine if the agent's output satisfies the expected criteria.

Input: {input_text}
Expected: {expected}
Output: {output}

Does the output satisfy the expected criteria? Consider:
- Semantic similarity (not exact match)
- Key information presence
- Intent fulfillment
"""
    return llm_do(prompt, output=JudgeResult)


def _show_eval_status(eval_files: list):
    """Show pass/fail status for all evals (uses stored results, no re-judging)."""
    table = Table(title="Eval Results", show_header=True)
    table.add_column("Eval", style="cyan")
    table.add_column("Status", justify="center")
    table.add_column("Expected", max_width=30)
    table.add_column("Output", max_width=30)

    passed = 0
    failed = 0
    no_expected = 0

    for eval_file in sorted(eval_files):
        with open(eval_file) as f:
            data = yaml.safe_load(f)

        for turn in data.get('turns', []):
            expected = turn.get('expected', '')
            output = turn.get('output', '')
            pass_result = turn.get('pass')

            if not expected:
                status = "[dim]—[/dim]"
                no_expected += 1
            elif pass_result is True:
                status = "[green]✓ pass[/green]"
                passed += 1
            elif pass_result is False:
                status = "[red]✗ fail[/red]"
                failed += 1
            else:
                status = "[dim]pending[/dim]"
                no_expected += 1

            # Truncate for display
            expected_display = (expected[:27] + "...") if len(expected) > 30 else expected
            output_display = (output[:27] + "...") if len(output) > 30 else output

            table.add_row(
                eval_file.stem,
                status,
                expected_display or "[dim]not set[/dim]",
                output_display
            )

    console.print(table)
    console.print()

    # Summary
    if failed > 0:
        console.print(f"[bold red]✗ {failed} failed[/bold red], ", end="")
    if passed > 0:
        console.print(f"[bold green]✓ {passed} passed[/bold green], ", end="")
    if no_expected > 0:
        console.print(f"[dim]{no_expected} no expected[/dim]", end="")
    console.print()
