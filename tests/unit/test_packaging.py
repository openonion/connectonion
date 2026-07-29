"""The package has to be buildable, and only one CI job would tell us otherwise.

`connectonion/cli/co_ai/prompts/connectonion/` is a tree of symlinks mirroring
`docs/` — that is how `load_guide` serves documentation without a second copy.
Delete a page in `docs/` and the symlink pointing at it dangles.

hatchling calls `os.stat()` on every included file, so one dangling symlink
fails `python -m build` outright — on every platform, not just Windows.
`pip install -e .` archives nothing, so it keeps working and seven of our eight
CI jobs stay green. Only `windows-e2e` builds a wheel, which is where this was
caught: consolidating the templates deleted four `docs/templates/*.md` pages
and left four symlinks pointing at them.

A broken release is worse than a broken test, so check it in the fast suite.
"""

from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[2] / "connectonion"


def test_no_dangling_symlinks_in_the_package():
    dangling = sorted(
        str(path.relative_to(PACKAGE))
        for path in PACKAGE.rglob("*")
        if path.is_symlink() and not path.exists()
    )

    assert not dangling, (
        "dangling symlinks under connectonion/ — `python -m build` fails with "
        f"FileNotFoundError on the first one: {dangling}. They mirror docs/, so a "
        "deleted docs page leaves one behind; delete the symlink too."
    )


def test_prompts_do_not_teach_a_template_that_no_longer_exists():
    """The agent reads these, not just the humans. `tools/enter_plan_mode.md` is
    always in the system prompt and told the agent to scaffold with
    `--template browser/coder/web-research`; every one of those now exits 1.

    Docs were updated when the templates were retired and the prompts were not,
    which is a quieter failure: the agent confidently runs a dead command.
    """
    prompts = PACKAGE / "cli" / "co_ai" / "prompts"
    retired = ["minimal", "coder", "browser", "hosted-browser", "web-research",
               "playwright", "email-agent", "meta-agent"]

    offenders = []
    for path in prompts.rglob("*.md"):
        if path.is_symlink():
            continue  # mirrors docs/, covered by the docs' own review
        text = path.read_text(encoding="utf-8")
        for name in retired:
            if f"--template {name}" in text:
                offenders.append(f"{path.relative_to(prompts)}: --template {name}")

    assert not offenders, (
        "prompts instruct the agent to use a retired template; these commands "
        f"exit 1: {offenders}"
    )


def test_guide_index_does_not_advertise_the_retired_templates():
    """`load_guide(name)` is `GUIDES_DIR / f"{name}.md"` with no fallback, so a
    guide listed in index.md but absent from disk is a tool call that fails at
    runtime — the agent is told it can read something it cannot.

    Scoped to the templates this change retired. index.md advertises 11 other
    guides that have never existed; that is pre-existing and tracked separately.
    """
    guides = PACKAGE / "cli" / "co_ai" / "prompts" / "connectonion"
    listed = (guides / "index.md").read_text(encoding="utf-8")

    for retired in ["templates/minimal", "templates/coder",
                    "templates/browser", "templates/web-research"]:
        assert f"`{retired}`" not in listed, (
            f"index.md still offers {retired}, whose docs page was deleted"
        )
