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



def test_prompts_only_name_templates_that_exist():
    """The agent reads these prompts and runs the commands in them verbatim.

    `agent-design.md` taught `--template playwright` and `--template
    email-agent`; neither has ever existed in this tree. An agent following the
    prompt confidently ran a command that could not work — and `co create`
    exited 0 while doing it, so nothing downstream noticed either.
    """
    import re
    from pathlib import Path

    root = Path(__file__).resolve().parents[2] / "connectonion" / "cli"
    available = {p.name for p in (root / "templates").iterdir() if p.is_dir()} | {"custom"}

    offenders = []
    for md in (root / "co_ai" / "prompts").rglob("*.md"):
        for name in re.findall(r"--template\s+([a-z0-9-]+)", md.read_text(encoding="utf-8")):
            if name not in available:
                offenders.append(f"{md.name}: --template {name}")

    assert not offenders, (
        "prompts name templates that do not exist; the agent will run a command "
        f"that fails: {offenders}"
    )
