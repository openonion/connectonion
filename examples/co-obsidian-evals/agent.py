"""The Agent co eval drives for the Obsidian Usage Skill.

Like co-asana-evals, its only terminal tool invokes real commands against
synthetic data. Every case gets a new temporary vault, including fresh rows.
"""

import json
import shlex
import socket
import tempfile
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from connectonion import Agent, after_user_input, host
from connectonion.useful_plugins import skill, skills

HERE = Path(__file__).parent
FIXTURE = HERE / ".co" / "benchmarks" / "fixtures" / "obsidian-course" / "workspace.json"
state = {}


class Workspace:
    """A fresh vault and row cache for one evaluation case."""

    def __init__(self, fixture):
        self.temporary = tempfile.TemporaryDirectory(prefix="obsidian-eval-")
        self.root = Path(self.temporary.name)
        self.vault = self.root / "CourseVault"
        data = json.loads(Path(fixture).read_text(encoding="utf-8"))
        for relative, content in data["notes"].items():
            path = self.vault / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        self.registry = self.root / "obsidian.json"
        self.registry.write_text(json.dumps({"vaults": {
            "synthetic": {"path": str(self.vault), "open": True}}}), encoding="utf-8")

    def close(self):
        self.temporary.cleanup()


def run(command: str, workspace: Workspace, *, stdin: str = "") -> str:
    """Run one CLI command, refusing shells, other groups and non-synthetic vaults."""
    from typer.testing import CliRunner
    from connectonion.cli.main import app
    from connectonion.cli.commands import obsidian_commands
    from connectonion.useful_tools import obsidian

    try:
        words = shlex.split(command)
    except ValueError as error:
        return f"Shell parse error: {error}\n[exit 2]"
    if words[:2] != ["co", "obsidian"] or any(w in (";", "&&", "|", ">", "<") for w in words):
        return "Refused: run one co obsidian command; pass piped text in stdin.\n[exit 2]"
    validate = obsidian._validate_scope

    def scoped(vault, folders):
        if Path(vault).resolve() != workspace.vault.resolve():
            raise obsidian.ObsidianError("Only the synthetic CourseVault is available.", "co obsidian vaults")
        return validate(vault, folders)

    def offline(*args, **kwargs):
        raise RuntimeError("Obsidian evaluation commands cannot access the network")

    with ExitStack() as stack:
        stack.enter_context(patch.object(obsidian, "_registry_path", lambda: workspace.registry))
        stack.enter_context(patch.object(obsidian, "_validate_scope", scoped))
        stack.enter_context(patch.object(obsidian_commands, "global_config_dir", lambda: workspace.root))
        stack.enter_context(patch.object(socket.socket, "connect", offline))
        stack.enter_context(patch.object(socket, "create_connection", offline))
        result = CliRunner().invoke(app, words[1:], input=stdin, prog_name="co",
                                    env={"NO_COLOR": "1", "COLUMNS": "160"})
    shown = (result.stdout or "") + (result.stderr or "")
    return f"$ {command}\n{shown.rstrip()}\n[exit {result.exit_code}]"


def fresh_workspace(agent=None):
    previous = state.pop("workspace", None)
    if previous is not None:
        previous.close()
    state["workspace"] = Workspace(FIXTURE)


def co(command: str, stdin: str = "") -> str:
    """Run one co obsidian command and return its output and exit code.

    Use the registered name CourseVault or the path printed by vaults.
    Only synthetic files exist here. Pass text for --content - using stdin;
    this tool does not interpret shell pipelines or execute other commands.
    """
    if "workspace" not in state:
        fresh_workspace()
    return run(command, state["workspace"], stdin=stdin)


SYSTEM = ("Help the user with Obsidian from a terminal. Your only terminal tool runs "
          "co obsidian commands in a synthetic CourseVault. Answer from command output; "
          "do not claim a preview wrote a file. Follow the user's selected folders.")


def build():
    return Agent("co-obsidian-eval", tools=[co, skill], system_prompt=SYSTEM,
                 plugins=[skills, [after_user_input(fresh_workspace)]])


host(build)
