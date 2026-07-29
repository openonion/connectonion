"""The template is `co ai`, wrapped in host() — and must stay that way.

There used to be six templates that drifted apart: each carried its own tool
list, its own prompt, and its own idea of what an agent was. Now there is one,
and its whole job is to be the same agent the CLI runs. These tests pin that,
because the failure mode is silent — rename the factory and the template still
*looks* fine until someone runs `co create`.
"""

import ast
import inspect
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "connectonion"
TEMPLATE_ROOT = ROOT / "cli" / "templates"
TEMPLATE = TEMPLATE_ROOT / "co-ai"


def test_there_is_exactly_one_template():
    templates = sorted(p.name for p in TEMPLATE_ROOT.iterdir() if p.is_dir())

    assert templates == ["co-ai"], (
        f"expected only the co-ai template, found {templates}. A second template "
        "is a second definition of what an agent is — specialise with skills instead."
    )


def test_template_ships_what_a_deploy_needs():
    for name in ["agent.py", "Dockerfile", "requirements.txt"]:
        assert (TEMPLATE / name).exists(), f"template is missing {name}"


def test_template_uses_the_sdk_factory_rather_than_building_its_own_agent():
    tree = ast.parse((TEMPLATE / "agent.py").read_text(encoding="utf-8"))
    called = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }

    assert "create_agent" in called
    assert "host" in called, "the template has to serve, or `co deploy` gets nothing"
    assert "Agent" not in called, (
        "the template constructs its own Agent — that is how templates drift out "
        "of sync with `co ai`"
    )


def test_the_factory_the_template_imports_actually_exists():
    """The regression this file exists for: renaming the factory in the SDK
    without updating the template, which only surfaces on `co create`."""
    from connectonion.cli.co_ai import agent as co_ai_agent

    tree = ast.parse((TEMPLATE / "agent.py").read_text(encoding="utf-8"))
    imported = [
        (node.module, alias.name)
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    ]

    for module, name in imported:
        if module == "connectonion.cli.co_ai.agent":
            assert hasattr(co_ai_agent, name), f"template imports missing {name}"


def test_template_passes_a_role_the_sdk_can_load():
    """`role=` selects roles/{role}.md. A typo here produces an agent that
    raises at construction, which for a deployed agent means a dead container."""
    from connectonion.cli.co_ai.agent import create_agent

    tree = ast.parse((TEMPLATE / "agent.py").read_text(encoding="utf-8"))
    roles = [
        kw.value.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        for kw in node.keywords
        if kw.arg == "role" and isinstance(kw.value, ast.Constant)
    ]

    assert roles, "template should pass role= explicitly so it is obvious what to change"

    available = {p.stem for p in (ROOT / "cli" / "co_ai" / "prompts" / "roles").glob("*.md")}
    for role in roles:
        assert role is None or role in available, f"unknown role {role!r}, have {available}"

    assert "role" in inspect.signature(create_agent).parameters


def test_unknown_template_exits_nonzero_and_says_where_it_went():
    """Passing a retired template used to print an error and exit 0, so a script
    doing `co create x --template minimal && cd x` reported success and produced
    nothing. Five names were retired at once, so this is the path stale scripts
    and old blog posts land on."""
    from connectonion.cli.commands.project_cmd_lib import unknown_template_message

    message = unknown_template_message("minimal")

    assert "not found" in message
    assert "co-ai" in message, "must name a template that does exist"
    assert "retired" in message, "a retired name needs more than 'not found'"
    assert ".co/skills/" in message, "say what to do instead"

    # A name that was never a template gets the available list, without
    # claiming it used to exist.
    other = unknown_template_message("banana")
    assert "co-ai" in other
    assert "retired" not in other


def test_unknown_template_is_rejected_before_any_network_or_mkdir(tmp_path, monkeypatch):
    """The check used to sit after authenticate() and after the project
    directory was created, so a typo cost a network round trip and a
    mkdir/rmtree. Validate the name first."""
    import typer
    from connectonion.cli.commands import create as create_mod

    def fail(*args, **kwargs):
        raise AssertionError("authenticate() ran before the template was validated")

    monkeypatch.setattr(create_mod, "authenticate", fail)
    monkeypatch.setattr(create_mod, "ensure_global_config", lambda *a, **k: None)
    monkeypatch.chdir(tmp_path)

    import pytest
    with pytest.raises(typer.Exit) as excinfo:
        create_mod.handle_create(
            name="doomed", ai=None, key=None,
            template="minimal", description=None, yes=True,
        )

    assert excinfo.value.exit_code == 1
    assert not (tmp_path / "doomed").exists(), "no directory should be left behind"
