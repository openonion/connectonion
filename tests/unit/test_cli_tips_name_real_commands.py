"""Every tip the CLI prints names a command that exists.

A tip is read by an agent that has nothing but this output. If the tip says
`run co gmail to refresh`, the agent runs `co gmail to` — measured, not
imagined: the mail surface shipped with three tips like this and the model
invented `readmail 18f2a`, `!! --idempotency-key k-123` and `co gmail && co
gmail 3` for them. A tip that names a real command, spelled out, is the one
the agent gets right.

This sweeps the CLI source for tip strings — anything containing `Next:`,
`Tip:` or 💡, anything that begins with `co `, and every element of a list
named *TIPS — and checks each `co …` phrase in them against the register with
the group/leaf rule from discovery.check(). A tip in an f-string is read with
its placeholders blanked, so `co server check {name}` checks `co server
check`.

Sweep the source rather than register tips at runtime: a registry only holds
what someone remembered to register, and the tip that gets forgotten is the
one written in a hurry inside an error branch.
"""

import ast
from pathlib import Path

import pytest

from connectonion.cli import main as cli_main
from connectonion.cli.commands.command_tips import STATUS_TIPS, rotating_tip
from connectonion.cli.discovery import check, commands_in


CLI_ROOT = Path(cli_main.__file__).parent
TIP_MARKERS = ("Next:", "Tip:", "💡")


def _text(node) -> str | None:
    """A string literal's text; an f-string with its placeholders blanked."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(
            v.value if isinstance(v, ast.Constant) else "<x>" for v in node.values
        )
    return None


def _looks_like_a_tip(text: str) -> bool:
    return text.startswith("co ") or any(m in text for m in TIP_MARKERS)


def _tip_strings(path: Path):
    """(line, text) for every tip-shaped string literal in one source file."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    in_tips_list = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.List):
            if any(isinstance(t, ast.Name) and t.id.endswith("TIPS") for t in node.targets):
                in_tips_list.update(id(e) for e in node.value.elts)
    for node in ast.walk(tree):
        text = _text(node)
        if text is None:
            continue
        if id(node) in in_tips_list or _looks_like_a_tip(text):
            yield node.lineno, text


def _all_tips():
    for path in sorted(CLI_ROOT.rglob("*.py")):
        if "templates" in path.parts:
            continue                  # scaffolding shipped to users, not CLI output
        for line, text in _tip_strings(path):
            yield path.relative_to(CLI_ROOT.parent.parent), line, text


ALL_TIPS = list(_all_tips())


def test_the_sweep_found_the_tips_it_is_for():
    """If the sweep finds nothing, it is broken, not the code clean."""
    texts = [t for _, _, t in ALL_TIPS]
    assert any("co browser tab ls" in t for t in texts)        # browser TIPS
    assert any("co commands" in t for t in texts)              # STATUS_TIPS
    assert any(t.startswith("Next: co ") for t in texts)       # a plain Next: tip
    assert len(ALL_TIPS) > 50


@pytest.mark.parametrize("path, line, text", ALL_TIPS, ids=[f"{p}:{l}" for p, l, _ in ALL_TIPS])
def test_every_command_a_tip_names_exists(path, line, text):
    bad = [(phrase, check(cli_main.app, phrase)) for phrase in commands_in(text)]
    bad = [(phrase, why) for phrase, why in bad if why]
    assert bad == [], f"{path}:{line} names a command that does not exist: {bad}\n  in: {text!r}"


def test_the_sweep_would_catch_the_measured_failures():
    """The three tips that failed on the mail surface must fail here."""
    assert check(cli_main.app, commands_in("run co gmail to refresh")[0])
    assert commands_in("Retry the same command with --idempotency-key <key>") == []
    assert check(cli_main.app, "co gmail open")


class TestRotatingTip:

    def test_each_group_keeps_its_own_cursor(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        a = ["a1", "a2"]
        b = ["b1", "b2", "b3"]
        assert rotating_tip("alpha", a) == "a1"
        assert rotating_tip("beta", b) == "b1"
        assert rotating_tip("alpha", a) == "a2"
        assert rotating_tip("alpha", a) == "a1"            # wrapped
        assert rotating_tip("beta", b) == "b2"             # untouched by alpha
        assert (tmp_path / ".co" / ".alpha_tip").exists()
        assert (tmp_path / ".co" / ".beta_tip").exists()

    def test_a_garbled_cursor_resets_instead_of_crashing(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        (tmp_path / ".co").mkdir()
        (tmp_path / ".co" / ".x_tip").write_text("3\n7", encoding="utf-8")
        assert rotating_tip("x", ["first", "second"]) == "first"


def test_status_tips_each_name_one_command():
    """One next step per tip; two is a fork the reader resolves by guessing."""
    for tip in STATUS_TIPS:
        named = commands_in(tip)
        assert len(named) == 1, tip
        assert check(cli_main.app, named[0]) is None, tip
