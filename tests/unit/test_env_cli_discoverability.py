"""The selected account remains in error tips; text-only grading never executes replies."""
import json
import os
from pathlib import Path
import shlex
import sys
import tempfile
from unittest.mock import patch

import pytest
from typer.testing import CliRunner
from connectonion import environment
from connectonion.cli.main import app

CASES = [
    (["gmail", "inbox"], "Connect the Google account for this command", "auth google"),
    (["gdrive", "list"], "Connect the Google account for this command", "auth google"),
    (["gcalendar", "list"], "Connect the Google account for this command", "auth google"),
    (["youtube", "channel"], "Connect the Google account for this command", "auth google"),
    (["outlook", "inbox"], "Connect the Microsoft account for this command", "auth microsoft"),
    (["gmail", "inbox"], "Create the selected env file so the command can run", None),
    (["init"], "Initialize global configuration", "init"),
]


def capture(args, root, invalid=False):
    home = root / "home"
    home.mkdir(exist_ok=True)
    selected = root / "test.env"
    selected.write_text("")
    selector = root / "absent.env" if invalid else selected
    with patch.dict(os.environ, {"HOME": str(home), "USERPROFILE": str(home)}, clear=True), \
         patch.object(Path, "home", return_value=home), \
         patch.object(environment, "_loaded", {}), patch.object(environment, "_selected", None):
        return CliRunner().invoke(app, ["--env-file", str(selector), *args], prog_name="co")


@pytest.mark.parametrize("args,goal,recovery", CASES)
def test_selected_source_is_in_piped_recovery(args, goal, recovery, tmp_path):
    result = capture(args, tmp_path, invalid=recovery is None)
    assert result.exit_code == (2 if recovery in (None, "init") else 1), result.output
    # A missing selected file is created by saving its first setting; the tip
    # used to be `co --help`, which lists commands and creates nothing.
    expected = (f"co --env-file {shlex.quote(str(tmp_path / 'absent.env'))} env set" if recovery is None
                else "co init" if recovery == "init"
                else f"co --env-file {shlex.quote(str(tmp_path / 'test.env'))} {recovery}")
    assert expected in result.output, result.output
    assert "Traceback" not in result.output


if __name__ == "__main__":
    from connectonion import llm_do
    with tempfile.TemporaryDirectory(prefix="co-env-tips-") as directory:
        root = Path(directory).resolve()
        for args, goal, recovery in CASES:
            result = capture(args, root, invalid=recovery is None)
            expected = (f"co --env-file {shlex.quote(str(root / 'absent.env'))} env set" if recovery is None
                        else "co init" if recovery == "init"
                        else f"co --env-file {shlex.quote(str(root / 'test.env'))} {recovery}")
            reply = llm_do(f"You just ran a shell command. Its full output was:\n\n{result.output}\n\n"
                           f"Your goal: {goal}. Reply with ONE shell command and nothing else.",
                           model="co/gemini-3.7-flash").strip()
            print(json.dumps({"command": "co --env-file test.env " + " ".join(args),
                              "exit": result.exit_code, "output": result.output.replace(str(root), "<test>"),
                              "goal": goal, "reply": reply.replace(str(root), "<test>"),
                              "passed": shlex.split(reply) == shlex.split(expected)}), flush=True)
