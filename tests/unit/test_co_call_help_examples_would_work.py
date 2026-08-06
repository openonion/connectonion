"""`co call --help`'s examples must be commands the shipped whitelist permits.

`co call` sends everything after the address as one bash string, and the remote
checks that string against its .co/host.yaml. So an example in the help is a
claim about two files at once: the help text, and the whitelist that has to
permit it. Nothing tied them together.

Found by getting it wrong. Against the real deployed nw-map agent:

    $ co call 0xcf1619cb… co status
    /bin/bash: line 1: co: command not found        exit 127

which reads like the example is wrong, and the obvious repair is to spell out
the venv path. That repair is refused:

    $ co call 0xcf1619cb… .venv/bin/co status
    blocked: command not in the permission whitelist

because the shipped entry is `Bash(co *)` and fnmatch does not stretch to a
path. The real cause of the 127 was the unit file, already fixed this release
(deploy_to_server.py puts {SRV}/{agent}/.venv/bin first on PATH, covered by
test_deploy_to_server.py) — nw-map is simply running a unit written before it.
Bare `co` is the correct example; my "fix" would have shipped an example that
every correctly-deployed agent refuses.

So the invariant, rather than the string: ask the real permission checker
whether each example would be allowed. That answers in one second what a live
deployment answered in two wrong directions.

Same family as the recurring one this release — a decision that lives in more
than one place — except here the two places are a docstring and a YAML default,
which no import links.
"""

import pathlib
import re

import pytest
import yaml
from typer.testing import CliRunner

from connectonion.cli.main import app
from connectonion.useful_plugins.tool_approval.approval import is_tool_permitted


runner = CliRunner()

HOST_YAML = (pathlib.Path(__file__).resolve().parents[2]
             / "connectonion/network/host/host.yaml")

ADDRESS = "0x3d40..."


ANSI = re.compile(r"\x1b\[[0-9;]*m")


@pytest.fixture
def help_text():
    """The help as a reader sees it, with styling removed.

    Rich emits ANSI when FORCE_COLOR is set, which is CI's environment and not
    this laptop's — and the style codes land INSIDE the option names, so `--out`
    stops being a substring of the output. `test_it_still_documents_the_options`
    failed on all four Linux jobs for that and nothing else. Reproduced locally
    with FORCE_COLOR=1: `ansi: True | plain --out found: False`.

    Third time a test of mine has broken on rendered output (the others read
    Rich-wrapped text). Hence TestTheOptionsAreDeclared below, which asks the
    command object instead of the panel — the durable form of this claim.
    """
    result = runner.invoke(app, ["call", "--help"], env={"COLUMNS": "200"})
    return " ".join(ANSI.sub("", result.output).split())


@pytest.fixture
def shipped_permissions():
    """The whitelist a fresh agent gets, read from the file `co init` copies."""
    loaded = yaml.safe_load(HOST_YAML.read_text(encoding="utf-8"))
    permissions = loaded.get("permissions") or {}
    assert permissions, f"no permissions block in {HOST_YAML}"
    return permissions


@pytest.fixture
def offered_commands():
    """The remote commands the help offers, one per example line.

    Read from the docstring, not from the rendered help: Rich joins and wraps
    the output, so an example's end is no longer marked and a regex over the
    flattened text swallowed the prose after it (bashlex then choked on a
    backtick from the next sentence). The docstring is the help — same text,
    with the line breaks that say where each example stops.
    """
    from connectonion.cli.main import call as call_command

    marker = ADDRESS + " "
    return [line.strip().split(marker, 1)[1]
            for line in (call_command.__doc__ or "").splitlines()
            if line.strip().startswith("co call ") and marker in line]


class TestTheExamplesArePermittedByTheShippedWhitelist:

    def test_examples_were_found(self, offered_commands):
        """If the help stops showing examples, this file has nothing to check
        and should fail rather than pass vacuously."""
        assert offered_commands

    def test_the_examples_are_the_ones_the_user_sees(self, offered_commands, help_text):
        """The docstring is only worth checking because it *is* the help."""
        for command in offered_commands:
            assert command in help_text

    def test_each_example_is_allowed(self, offered_commands, shipped_permissions):
        for command in offered_commands:
            allowed, reason = is_tool_permitted(
                "bash", {"command": command}, shipped_permissions
            )
            assert allowed, f"the help offers `{command}`, which the shipped whitelist refuses: {reason}"

    def test_the_path_form_is_the_refused_one(self, shipped_permissions):
        """The premise, stated so a future reader does not repeat the repair.

        If someone widens the whitelist to accept a path, this fails and the
        help may then legitimately use one."""
        allowed, _ = is_tool_permitted(
            "bash", {"command": ".venv/bin/co status"}, shipped_permissions
        )

        assert not allowed


class TestTheWhitelistedNameIsTheOneOnPath:
    """The other half — that the unit puts the venv on PATH, so the whitelisted
    name resolves — is owned by
    test_deploy_to_server.py::TestTheAgentCanFindItsOwnCommands, which asserts
    the exact directory and is where a reader of the unit file will look. Not
    duplicated here."""

    def test_the_whitelist_grants_the_bare_name(self, shipped_permissions):
        assert any(p.startswith("Bash(co ") for p in shipped_permissions)


class TestTheHelpStillDescribesTheCommand:
    """Guard against satisfying the above by deleting the examples."""

    def test_it_still_explains_what_call_does(self, help_text):
        assert "remote" in help_text.lower()

    def test_it_still_documents_the_options(self, help_text):
        for option in ("--out", "--timeout", "--relay"):
            assert option in help_text


class TestTheOptionsAreDeclared:
    """The same claim asked of the declaration rather than the rendered panel.

    `co call` declares exactly one parameter — `args` — because it parses
    --out/--timeout/--relay itself out of the token list. So they are not click
    params, and the first version of this class asserted they were and failed
    correctly. Where they ARE declared is that argument's own help string:

        args  [ARGS]...  [--out F] [--timeout S] [--relay U] <address> <command...>

    which is what the panel renders and what Rich styles. Reading it from the
    declaration is the same claim with the renderer out of the way.
    """

    @staticmethod
    def _args_help() -> str:
        import typer.main

        call = typer.main.get_command(app).commands["call"]
        args = [param for param in call.params if "args" in param.opts]

        assert args, f"co call no longer declares `args`: {[p.opts for p in call.params]}"
        return args[0].help or ""

    @pytest.mark.parametrize("option", ["--out", "--timeout", "--relay"])
    def test_the_argument_help_names_it(self, option):
        assert option in self._args_help(), (
            f"{option} is not named in `args`'s help: {self._args_help()!r}"
        )

    def test_it_still_says_what_the_positional_arguments_are(self):
        """Guard against satisfying the above by listing only options."""
        declared = self._args_help()

        assert "<address>" in declared and "command" in declared


class TestTheHelpStillDescribesTheCommand:
    """Guard against satisfying the above by deleting the examples."""

    def test_it_still_explains_what_call_does(self, help_text):
        assert "remote" in help_text.lower()

    def test_it_still_documents_the_options(self, help_text):
        for option in ("--out", "--timeout", "--relay"):
            assert option in help_text

    def test_it_still_names_the_whitelist(self, help_text):
        assert "whitelist" in help_text.lower() or "host.yaml" in help_text
