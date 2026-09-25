"""What goes into the wheel's docs, and from there into every project's .co/docs/.

1.8.8b7 shipped docs/testing/ — 91 files of wiki test runs with ~245 absolute
paths from the maintainer's machine (`/Users/<name>/projects/.worktree/...`,
`/Users/<name>/.codex/sessions`) — and `co create` / `co init` copied it into
every new project's .co/docs/. The wheel mapped docs/ with a hatch
force-include, which exclusion rules never reach, so nothing could keep a
folder out.

These checks read the repository, so they run on every commit. The built wheel
itself is checked in tests/e2e/test_the_wheel_carries_no_maintainer_paths.py.
"""

import re
from pathlib import Path

try:
    import tomllib
except ImportError:  # Python 3.10; pytest itself depends on tomli there
    import tomli as tomllib

from connectonion.cli.commands import project_cmd_lib

REPO = Path(__file__).resolve().parents[2]
DOCS = REPO / "docs"

# `/Users/you/...` in an example is documentation; `/Users/<a real login>` is a leak.
PLACEHOLDER_HOMES = {"you", "me", "name", "user", "User"}
HOME = re.compile(rb"/Users/([A-Za-z0-9_.-]+)")


def _package_ignore() -> set:
    return project_cmd_lib._internal_docs(DOCS)


def test_the_wheel_excludes_exactly_what_package_ignore_lists():
    wheel = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
    wheel = wheel["tool"]["hatch"]["build"]["targets"]["wheel"]
    # force-include bypasses `exclude`; mapping docs/ that way is how testing/ leaked.
    assert "force-include" not in wheel
    assert wheel["sources"] == {"docs": "connectonion/docs"}
    assert {path.removeprefix("docs/") for path in wheel["exclude"]} == _package_ignore()
    assert "testing" in _package_ignore()


def _shipped_files():
    internal = _package_ignore()
    for path in DOCS.rglob("*"):
        relative = path.relative_to(DOCS).as_posix()
        if path.is_file() and not any(relative == p or relative.startswith(p + "/") for p in internal):
            yield path
    yield from (p for p in (REPO / "connectonion").rglob("*") if p.is_file() and "__pycache__" not in p.parts)


def test_nothing_shipped_names_a_real_home_directory():
    leaks = [
        f"{path.relative_to(REPO)}: /Users/{login.decode()}"
        for path in _shipped_files()
        for login in set(HOME.findall(path.read_bytes()))
        if login.decode() not in PLACEHOLDER_HOMES
    ]
    assert not leaks, "use /Users/you or ~ in shipped docs:\n" + "\n".join(sorted(leaks))


def test_co_init_leaves_internal_docs_out_of_the_project(tmp_path, monkeypatch):
    # An editable install copies straight from the repo's docs/, where the
    # internal trees still exist; the wheel no longer contains them at all.
    source = tmp_path / "docs"
    (source / "testing" / "artifacts").mkdir(parents=True)
    (source / "testing" / "artifacts" / "run.json").write_text("/Users/someone/")
    (source / "releases" / "assets").mkdir(parents=True)
    (source / "releases" / "assets" / "shot.png").write_bytes(b"png")
    (source / "releases" / "1.8.8.md").write_text("notes")
    (source / "archive").mkdir()
    (source / "archive" / "old.md").write_text("old")
    (source / "quickstart.md").write_text("start here")
    (source / ".package-ignore").write_text("# internal\ntesting\nreleases/assets\n")
    monkeypatch.setattr(project_cmd_lib, "get_docs_source", lambda: source)
    (tmp_path / ".co").mkdir()

    assert project_cmd_lib.copy_docs(tmp_path / ".co")

    copied = {p.relative_to(tmp_path / ".co" / "docs").as_posix()
              for p in (tmp_path / ".co" / "docs").rglob("*") if p.is_file()}
    assert copied == {"quickstart.md", "releases/1.8.8.md"}
