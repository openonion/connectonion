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


def _as_package_ignore(pattern: str) -> str:
    return "!" + pattern.removeprefix("!docs/") if pattern.startswith("!") else pattern.removeprefix("docs/")


def test_the_wheel_and_sdist_exclude_exactly_what_package_ignore_lists():
    targets = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
    targets = targets["tool"]["hatch"]["build"]["targets"]
    wheel = targets["wheel"]
    # force-include bypasses `exclude`; mapping docs/ that way is how testing/ leaked.
    assert "force-include" not in wheel
    assert wheel["sources"] == {"docs": "connectonion/docs"}
    # Order matters for `!` lines, so the lists are compared as lists.
    patterns = project_cmd_lib.package_ignore_patterns(DOCS)
    assert [_as_package_ignore(p) for p in wheel["exclude"]] == patterns
    assert [_as_package_ignore(p) for p in targets["sdist"]["exclude"]] == patterns
    assert "testing" in _package_ignore()


# Found in 1.8.8b9's wheel and in a fresh project's .co/docs/ after #1696:
# planning and positioning notes, and ~50 design records written for maintainers.
INTERNAL_NOTES = ["1.8-development-plan.md", "SELLING_POINTS.md", "PRODUCT.md",
                  "superpowers/plans", "superpowers/specs",
                  "design-decisions/001-choosing-input-method.md",
                  "design-decisions/072-claude-station-commits-per-turn.md"]


def test_planning_notes_and_uncited_design_records_do_not_ship():
    internal = _package_ignore()
    shipped = {p.relative_to(DOCS).as_posix() for p in _shipped_files() if DOCS in p.parents}
    for path in INTERNAL_NOTES:
        assert (DOCS / path).exists(), f"{path} moved; update this test"
        assert not any(s == path or s.startswith(path + "/") for s in shipped), f"{path} still ships"
    assert "design-decisions/063-one-directory-three-verbs.md" not in internal


LINK = re.compile(r"\]\(([^)#\s]+)")
NOT_CITED = ("design-decisions/", "superpowers/", "1.8-development-plan.md", "SELLING_POINTS.md", "PRODUCT.md")


def test_no_shipped_doc_links_to_a_doc_that_does_not_ship():
    # The reason a design decision ships at all: a user-facing doc cites it.
    # Link one that is left out and the reader gets a dead link in .co/docs/.
    import posixpath

    internal = _package_ignore()
    dead = []
    for path in _shipped_files():
        if DOCS not in path.parents or path.suffix != ".md":
            continue
        here = path.relative_to(DOCS).as_posix()
        for target in LINK.findall(path.read_text(encoding="utf-8", errors="ignore")):
            if "://" in target:
                continue
            linked = posixpath.normpath(posixpath.join(posixpath.dirname(here), target))
            # Release notes citing test evidence (acceptance/, releases/assets/)
            # predate this and point at the repository on purpose; the notes and
            # design records left out here must not be cited from a shipped doc.
            if not linked.startswith(NOT_CITED):
                continue
            if any(linked == p or linked.startswith(p + "/") for p in internal):
                dead.append(f"{here} -> {linked}")
    assert not dead, ("add a `!` line for these in docs/.package-ignore and pyproject.toml:\n"
                      + "\n".join(sorted(dead)))


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
    (source / "design-decisions").mkdir()
    (source / "design-decisions" / "001-internal.md").write_text("why, for maintainers")
    (source / "design-decisions" / "063-cited.md").write_text("why, cited by a user doc")
    (source / ".package-ignore").write_text(
        "# internal\ntesting\nreleases/assets\ndesign-decisions/*\n!design-decisions/063-cited.md\n")
    monkeypatch.setattr(project_cmd_lib, "get_docs_source", lambda: source)
    (tmp_path / ".co").mkdir()

    assert project_cmd_lib.copy_docs(tmp_path / ".co")

    copied = {p.relative_to(tmp_path / ".co" / "docs").as_posix()
              for p in (tmp_path / ".co" / "docs").rglob("*") if p.is_file()}
    assert copied == {"quickstart.md", "releases/1.8.8.md", "design-decisions/063-cited.md"}
