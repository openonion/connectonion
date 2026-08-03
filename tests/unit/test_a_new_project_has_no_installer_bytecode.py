"""A brand-new project contains only what the user is meant to read.

`pip install` byte-compiles every `.py` in the wheel. `cli/templates/co-ai/
agent.py` is a template rather than a module, but it is a `.py` under the
package, so installation leaves:

    site-packages/connectonion/cli/templates/co-ai/__pycache__/agent.cpython-310.pyc

`co create` copies the template directory as it finds it, so every new project
arrives with a `__pycache__` holding bytecode compiled on the installing
machine, for whatever interpreter did the installing. Observed from a real
wheel install:

    $ co create wheeltest --template co-ai
    $ ls -a wheeltest
    .co  .env  .gitignore  Dockerfile  __pycache__  agent.py  requirements.txt

Nothing breaks — a mismatched magic number is ignored and .gitignore covers the
directory. But a person opening their first ConnectOnion project should not
have to work out why there is compiled output for code they have not run, and
"is that mine?" is a question the template is supposed to prevent.

Only source is copied; the interpreter makes its own bytecode when the user
runs the thing.
"""

import shutil
from pathlib import Path

import pytest

from connectonion.cli.commands import create as create_cmd


@pytest.fixture
def template_with_bytecode(tmp_path, monkeypatch):
    """A template directory as pip leaves it: source plus a __pycache__."""
    templates = tmp_path / "templates"
    co_ai = templates / "co-ai"
    co_ai.mkdir(parents=True)
    (co_ai / "agent.py").write_text("from connectonion import host\n")
    (co_ai / "requirements.txt").write_text("connectonion\n")
    cache = co_ai / "__pycache__"
    cache.mkdir()
    (cache / "agent.cpython-310.pyc").write_bytes(b"\x6f\x0d\x0d\x0a stale")

    monkeypatch.setattr(create_cmd, "TEMPLATES_DIR", templates)
    return templates


def _copy(template_with_bytecode, tmp_path) -> Path:
    project = tmp_path / "project"
    project.mkdir()
    create_cmd.copy_template_files("co-ai", project, [])
    return project


class TestWhatArrivesInTheProject:

    def test_the_source_is_there(self, template_with_bytecode, tmp_path):
        project = _copy(template_with_bytecode, tmp_path)

        assert (project / "agent.py").exists()
        assert (project / "requirements.txt").exists()

    def test_the_installers_bytecode_is_not(self, template_with_bytecode, tmp_path):
        project = _copy(template_with_bytecode, tmp_path)

        assert not (project / "__pycache__").exists(), list(project.iterdir())


class TestNestedDirectoriesToo:
    """A template with a subdirectory gets the same treatment — copytree would
    otherwise carry a __pycache__ from any depth."""

    def test_a_nested_pycache_is_left_behind(self, template_with_bytecode, tmp_path):
        nested = template_with_bytecode / "co-ai" / "tools"
        nested.mkdir()
        (nested / "search.py").write_text("def search(): ...\n")
        (nested / "__pycache__").mkdir()
        (nested / "__pycache__" / "search.cpython-310.pyc").write_bytes(b"stale")

        project = _copy(template_with_bytecode, tmp_path)

        assert (project / "tools" / "search.py").exists()
        assert not (project / "tools" / "__pycache__").exists()


class TestCoInitToo:
    """`co init --template co-ai` copies the same directory by its own loop."""

    def test_init_leaves_the_bytecode_behind(self, template_with_bytecode, tmp_path, monkeypatch):
        from connectonion.cli.commands import init as init_cmd

        home = Path.home()
        (home / ".co").mkdir(parents=True, exist_ok=True)
        (home / ".co" / "keys.env").write_text("OPENONION_API_KEY=token\n")

        project = tmp_path / "into"
        project.mkdir()
        monkeypatch.chdir(project)
        monkeypatch.setattr(init_cmd, "TEMPLATES_DIR", template_with_bytecode,
                            raising=False)

        init_cmd.handle_init(ai=False, key=None, template="co-ai",
                             description=None, yes=True, force=True)

        assert (project / "agent.py").exists()
        assert not (project / "__pycache__").exists(), list(project.iterdir())
