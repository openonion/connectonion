"""A real model, unattended, writes a Rust CLI and gets it built, tested and run.

The scripted version of this job lives in
tests/e2e/test_an_unattended_agent_builds_a_rust_cli.py and runs on every CI
pass. This one lets the model choose the commands. It is the test that says
whether the read-only allowlist and the operator grants cover what a
model *actually* reaches for — `cargo new`? `cat -n`? `ls -la target/`? — not
what we imagined it would. Opt-in: real_api, paid, needs a key.

The verification at the end is independent of the model's own claims: the
test itself re-runs `cargo test` and the binary.
"""

import os
import pwd
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from connectonion import Agent
from connectonion.useful_plugins import prefer_write_tool
from connectonion.useful_plugins.tool_approval import tool_approval
from connectonion.useful_tools.bash import bash
from connectonion.useful_tools.file_tools import edit, read_file, write

CARGO = shutil.which("cargo") or shutil.which("cargo", path="/opt/homebrew/bin:/usr/local/bin")

pytestmark = [
    pytest.mark.slow,
    pytest.mark.timeout(600),   # a real model plus a cold cargo build, not a unit test
    pytest.mark.skipif(CARGO is None, reason="cargo is not installed on this machine"),
]

HOST_YAML = {
    "name": "rust-builder",
    "permissions": {
        "Bash(mkdir *)": {"allowed": True, "source": "config", "reason": "project layout", "expires": {"type": "never"}},
        "Bash(cargo *)": {"allowed": True, "source": "config", "reason": "cargo new/run are not in the focused list", "expires": {"type": "never"}},
        "Bash(./target/debug/greeter *)": {"allowed": True, "source": "config", "reason": "run what it built", "expires": {"type": "never"}},
        "Bash(./greeter/target/debug/greeter *)": {"allowed": True, "source": "config", "reason": "same binary from the parent dir", "expires": {"type": "never"}},
    },
}

PROMPT = (
    "Create a Rust command-line tool called greeter in the directory ./greeter "
    "(relative to the current directory). It takes --name <name> and prints "
    "'Hello, <name>!'. Include a unit test for the greeting function. Build it "
    "with cargo, run the tests, then run the binary with --name Aaron and show "
    "the first line of its output. You are running unattended: nobody can "
    "approve anything, so stay inside ./greeter and do not delete files."
)


def test_a_real_model_builds_tests_and_runs_the_cli_unattended(tmp_path, monkeypatch):
    real_home = Path(pwd.getpwuid(os.getuid()).pw_dir)
    for var, sub in (("RUSTUP_HOME", ".rustup"), ("CARGO_HOME", ".cargo")):
        if not os.environ.get(var) and (real_home / sub).is_dir():
            monkeypatch.setenv(var, str(real_home / sub))
    monkeypatch.setenv("CARGO_NET_OFFLINE", "true")
    monkeypatch.setenv("PATH", f"{Path(CARGO).parent}{os.pathsep}{os.environ.get('PATH', '')}")
    (tmp_path / ".co").mkdir()
    (tmp_path / ".co" / "host.yaml").write_text(yaml.safe_dump(HOST_YAML), encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    # prefer_write_tool is what a shipped co-ai agent runs with: the first
    # real run of this test wrote main.rs through `cat << 'EOF' > file`, a
    # heredoc bashlex cannot parse, and an unparseable command asks — so the
    # policy refused it. The plugin steers the model to the write tool, which
    # is the reversible edit the policy allows.
    # `edit` is here because the first runs showed why: the model ran
    # `cargo new`, which writes src/main.rs, and `write` refuses to overwrite
    # an existing file. Without `edit` it tried a heredoc (blocked), then
    # `python3 -c "open(...).write(...)"` (denied, correctly), then rewrote
    # the project around lib.rs. It got there; an operator would rather it
    # had an edit tool.
    agent = Agent(
        "rust-builder",
        tools=[bash, write, edit, read_file],
        plugins=[tool_approval, prefer_write_tool],
        max_iterations=25,
        log=False,
        quiet=True,
    )
    assert agent.io is None

    answer = agent.input(PROMPT)

    trace = agent.current_session["trace"]
    calls = [e for e in trace if e.get("type") == "tool_call"]
    what_it_did = [(c["name"], str(c["args"].get("command", c["args"].get("path")))[:160]) for c in calls]
    results = [e for e in trace if e.get("type") == "tool_result"]
    # Printed so a failure report shows the whole run, not a truncated repr.
    for call, result in zip(what_it_did, results):
        print(f"{call[0]:>10}  {result.get('status'):>8}  {call[1]!r}")
        if result.get("status") != "success":
            print(f"{'':>21}-> {str(result.get('result'))[:300]!r}")
    refused = [
        (c["args"].get("command", c["args"].get("path")), c.get("approval_policy"))
        for c in calls
        if (c.get("approval_policy") or {}).get("decision") != "allow"
    ]
    # Refusals are findings, not failures. The first runs refused
    # `ping -c 1 8.8.8.8` and `python3 -c "open(...).write(...)"` — both
    # correct — and the model finished the job anyway. What decides this test
    # is whether the job got done with nobody present. A refusal of a command
    # the policy *should* allow shows up in the printout above and, if the
    # model could not route around it, in the outcome asserts below.
    for command, policy in refused:
        print(f"refused: {command!r} -> {(policy or {}).get('reason')}")

    project = tmp_path / "greeter"
    binary = project / "target" / "debug" / "greeter"
    assert binary.exists(), f"no binary; model said: {answer!r}"
    tests = subprocess.run([CARGO, "test", "--quiet"], cwd=project, capture_output=True, text=True, timeout=600)
    assert tests.returncode == 0, tests.stdout + tests.stderr
    run = subprocess.run([str(binary), "--name", "Aaron"], capture_output=True, text=True, timeout=60)
    assert run.stdout.strip().splitlines()[0] == "Hello, Aaron!", run.stdout
