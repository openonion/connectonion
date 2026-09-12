"""An unattended agent writes a small Rust CLI, builds it, tests it, and runs it.

Why this test exists
--------------------
The Auto policy has sixty-odd unit tests, every one a single call to the
classifier: this command → this verdict. They were all green while a 7×/day
LinkedIn round died in production on `co browser ... get_text | head -40`,
because the tests encoded "unknown command asks" as correct and nothing
modelled what an unattended job actually *does*: make a directory, write
files, build, test, run the result, look at the output through a filter (#1481).

So this is the job, end to end, with the real Agent loop, the real tool
executor, the real approval plugin and a real toolchain. Only the model is
scripted. The scripted calls are the ones a model reaches for when told to
write a CLI: `mkdir`, two `write`s, `cargo build`, `cargo test`, run the
binary, inspect with `wc`/`ls`/`grep`. Every one of them must pass the
approval gate with nobody present, and the test records *which rule* carried
each step, so a policy change that quietly moves one of them from allow to
ask fails here with the step and the rule named.

What an operator has to grant
-----------------------------
Two things, in `.co/host.yaml`, and the test grants exactly those:
`Bash(mkdir *)` and `Bash(./target/debug/greeter *)`. Neither is read-only
and neither is a build tool, so the built-in policy asks about them, which
unattended is a refusal. Everything else — the file writes, `cargo build`,
`cargo test`, and every `cd`/`head`/`tail`/`wc`/`ls`/`grep` around them —
rides on the built-in policy alone.

Needs `cargo` on PATH. Skips, with that reason, where it is not installed.
"""

import os
import pwd
import shutil
from pathlib import Path

import pytest
import yaml

from connectonion import Agent
from connectonion.useful_plugins.tool_approval import tool_approval
from connectonion.useful_tools.bash import bash
from connectonion.useful_tools.file_tools import write
from tests.utils.mock_helpers import LLMResponseBuilder as R
from tests.utils.mock_helpers import MockLLM

CARGO = shutil.which("cargo") or shutil.which("cargo", path="/opt/homebrew/bin:/usr/local/bin")

pytestmark = pytest.mark.skipif(
    CARGO is None,
    reason="cargo is not installed on this machine; the Rust e2e cannot run here (it runs on CI, which ships a Rust toolchain)",
)

CARGO_TOML = """[package]
name = "greeter"
version = "0.1.0"
edition = "2021"

[dependencies]
"""

MAIN_RS = """use std::env;

fn greet(name: &str) -> String {
    format!("Hello, {}!", name)
}

fn main() {
    let args: Vec<String> = env::args().collect();
    let name = args
        .iter()
        .position(|a| a == "--name")
        .and_then(|i| args.get(i + 1))
        .map(String::as_str)
        .unwrap_or("world");
    println!("{}", greet(name));
}

#[cfg(test)]
mod tests {
    use super::greet;

    #[test]
    fn greets_by_name() {
        assert_eq!(greet("Aaron"), "Hello, Aaron!");
    }
}
"""

# The operator's standing grants. Each has a `reason` because that is what
# the approval audit shows; `source: config` is what `_headless_configured_command`
# looks for.
HOST_YAML = {
    "name": "rust-builder",
    "permissions": {
        "Bash(mkdir *)": {
            "allowed": True,
            "source": "config",
            "reason": "the builder lays out its own project directories",
            "expires": {"type": "never"},
        },
        "Bash(./target/debug/greeter *)": {
            "allowed": True,
            "source": "config",
            "reason": "running the binary it just built is the point",
            "expires": {"type": "never"},
        },
    },
}

# What the model does, in order, and which rule the test expects to carry it.
STEPS = [
    ("bash", {"command": "mkdir -p greeter/src", "description": "project layout"}, "workspace_edit"),
    ("write", {"path": "greeter/Cargo.toml", "content": CARGO_TOML}, "workspace_edit"),
    ("write", {"path": "greeter/src/main.rs", "content": MAIN_RS}, "workspace_edit"),
    ("bash", {"command": "cd greeter && cargo build --quiet 2>&1 | tail -20", "description": "build", "timeout": 300}, "verification"),
    ("bash", {"command": "cd greeter && cargo test --quiet 2>&1 | tail -20", "description": "test", "timeout": 300}, "verification"),
    ("bash", {"command": "cd greeter && ./target/debug/greeter --name Aaron | head -1", "description": "run it"}, "command"),
    ("bash", {"command": "wc -l greeter/src/main.rs && ls greeter/target/debug | grep -c '^greeter$'", "description": "inspect"}, "read"),
]


@pytest.fixture
def rust_toolchain_env(monkeypatch):
    """The suite isolates HOME, which is right for `~/.co` and wrong for rustup.

    A rustup-managed `cargo` is a proxy that finds the real toolchain through
    RUSTUP_HOME, defaulting to ~/.rustup — the real one, not the test's empty
    tmp HOME. CI sets RUSTUP_HOME/CARGO_HOME explicitly; a developer machine
    usually does not. Point them at the real home only when they are unset
    and the directories exist. A Homebrew cargo needs none of this.
    """
    real_home = Path(pwd.getpwuid(os.getuid()).pw_dir)
    for var, sub in (("RUSTUP_HOME", ".rustup"), ("CARGO_HOME", ".cargo")):
        if not os.environ.get(var) and (real_home / sub).is_dir():
            monkeypatch.setenv(var, str(real_home / sub))
    # No dependencies, so nothing to fetch — and nothing must try.
    monkeypatch.setenv("CARGO_NET_OFFLINE", "true")
    monkeypatch.setenv("PATH", f"{Path(CARGO).parent}{os.pathsep}{os.environ.get('PATH', '')}")


@pytest.fixture
def project(tmp_path, monkeypatch):
    """A fresh workspace with the operator's two grants and nothing else."""
    (tmp_path / ".co").mkdir()
    (tmp_path / ".co" / "host.yaml").write_text(yaml.safe_dump(HOST_YAML), encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _scripted_model():
    responses = [
        R.tool_call_response(name, args, call_id=f"call_{i}")
        for i, (name, args, _) in enumerate(STEPS)
    ]
    responses.append(R.text_response("Built greeter, its test passes, and it greets Aaron."))
    return MockLLM(responses=responses, model="scripted-rust-builder")


def test_an_unattended_agent_builds_tests_and_runs_a_rust_cli(project, rust_toolchain_env):
    agent = Agent(
        "rust-builder",
        llm=_scripted_model(),
        tools=[bash, write],
        plugins=[tool_approval],
        max_iterations=len(STEPS) + 2,
        log=False,
        quiet=True,
    )
    assert agent.io is None, "this test is about the run with nobody to ask"

    result = agent.input(
        "Create a Rust CLI called greeter in ./greeter that takes --name and prints "
        "'Hello, <name>!'. Add a unit test, build it, run the tests, run it for Aaron."
    )

    trace = agent.current_session["trace"]
    calls = [e for e in trace if e.get("type") == "tool_call"]
    results = [e for e in trace if e.get("type") == "tool_result"]

    # Every step ran, none was refused, and a person was never needed.
    assert len(calls) == len(STEPS), [c.get("name") for c in calls]
    refused = [r for r in results if r.get("status") != "success"]
    assert not refused, refused
    for (name, args, expected_rule), call in zip(STEPS, calls):
        policy = call.get("approval_policy") or {}
        assert policy.get("decision") == "allow", (args.get("command", args.get("path")), policy)
        assert policy.get("requires_human") is False, (args, policy)
        # Which rule carried the step. A policy change that moves a step to a
        # different rule is allowed to fail here: it is telling you the
        # operator's grants no longer mean what they did.
        assert policy.get("effect_class") == expected_rule, (args.get("command", args.get("path")), policy)

    # The toolchain did the real work.
    by_step = {i: r["result"] for i, r in enumerate(results)}
    assert "test result: ok. 1 passed" in by_step[4], by_step[4]
    assert by_step[5].strip() == "Hello, Aaron!", by_step[5]
    assert (project / "greeter" / "target" / "debug" / "greeter").exists()
    assert result == "Built greeter, its test passes, and it greets Aaron."


def test_the_job_needs_no_grant_at_all(project, rust_toolchain_env):
    """Take every grant away and the whole job still runs.

    This is the test that would have caught #1481 in reverse: it pins down
    that the built-in policy, not an operator grant, carries the file writes,
    the cargo runs and every pipe filter. If a future policy change made
    `| tail -20` need a grant again, this fails at the build step, not in
    production at iteration sixteen.

    It used to expect two refusals — `mkdir` and running the binary the job
    just built — which were carried by an operator grant rather than by the
    policy. Needing a standing `Bash(co *)` to make a directory was the shape
    of the problem, not a boundary worth keeping: with the default flipped
    (#1481), an ordinary local command runs and the rules that hold are the
    ones about leaving the machine, executing unreadable input, credentials
    and writing outside the workspace. A grant that still binds is covered in
    tests/unit/test_auto_approve_policy.py.
    """
    (project / ".co" / "host.yaml").write_text(yaml.safe_dump({"name": "rust-builder"}), encoding="utf-8")
    agent = Agent(
        "rust-builder",
        llm=_scripted_model(),
        tools=[bash, write],
        plugins=[tool_approval],
        max_iterations=len(STEPS) + 2,
        log=False,
        quiet=True,
    )

    agent.input("same job, no grants")

    calls = [e for e in agent.current_session["trace"] if e.get("type") == "tool_call"]
    decisions = [(s[1].get("command", s[1].get("path")), c["approval_policy"]["decision"]) for s, c in zip(STEPS, calls)]
    denied = [command for command, decision in decisions if decision == "deny"]
    assert denied == [], decisions
