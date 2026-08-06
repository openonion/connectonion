"""`docs/connectonion.md` promises seven templates; one ships (#724).

This file is what `co init` copies into every project's `.co/docs/`. It is the
reference an agent reads to learn the framework, and the first thing a person
reads. It says:

    --template, -t  Choose template: minimal (default), browser,
                    hosted-browser, coder, co-ai, web-research, custom

and then describes `minimal` and `coder` in detail, down to their tool lists and
plugins. The CLI offers two:

    --template  -t  TEXT  Template: co-ai (default), custom

and `connectonion/cli/templates/` holds one directory, `co-ai`. Following the
documentation:

    $ co create demo -t minimal        ❌ Template 'minimal' not found.
    $ co create demo -t coder          ❌ Template 'coder' not found.
    $ co create demo -t web-research   ❌ Template 'web-research' not found.

The descriptions are wrong about the template that does exist, too. `co-ai` is
not a tool list — it is four lines:

    from connectonion import host
    from connectonion.cli.co_ai.agent import create_agent
    agent = create_agent(role="coding")
    host(agent)

I filed this saying the fix was a product question, because deciding what
templates *should* exist is one. Describing what does exist is not, and that is
all this changes.

The test asserts against the CLI's own option help rather than a list written
here, so a template added tomorrow does not have to be added twice.
"""

import re
from pathlib import Path

import pytest


DOC = Path(__file__).resolve().parents[2] / "docs" / "connectonion.md"


def _documented_templates():
    """The names the `--template` line offers, as a reader reads them."""
    text = DOC.read_text(encoding="utf-8")
    match = re.search(r"`--template, -t`[^\n]*", text)
    assert match, "the --template line is gone; this test needs updating"
    return set(re.findall(r"`([a-z][a-z0-9-]*)`", match.group(0))) - {"--template", "-t"}


def _real_templates():
    """What `co create --help` says, which is generated from the code."""
    from typer.testing import CliRunner

    from connectonion.cli.main import app

    output = CliRunner().invoke(app, ["create", "--help"]).output
    line = " ".join(output.split())
    match = re.search(r"Template:\s*([^│]+?)\s*(?:│|--|$)", line)
    assert match, f"could not read the template option from --help: {line[:200]}"
    return set(re.findall(r"[a-z][a-z0-9-]*", match.group(1))) - {"default"}


class TestTheDocOffersWhatTheCliOffers:

    def test_it_promises_nothing_extra(self):
        phantom = _documented_templates() - _real_templates()

        assert phantom == set(), (
            f"docs/connectonion.md offers templates that do not exist: "
            f"{sorted(phantom)} — `co create -t <name>` fails for each"
        )

    def test_it_does_not_hide_one_that_exists(self):
        missing = _real_templates() - _documented_templates()

        assert missing == set(), f"the CLI offers {sorted(missing)} and the doc does not"

    def test_the_default_is_named(self):
        assert "co-ai" in _documented_templates()


class TestNoSectionDescribesATemplateThatIsGone:

    @pytest.mark.parametrize(
        "gone", ["minimal", "coder", "browser", "hosted-browser", "web-research"]
    )
    def test_it_has_no_heading_of_its_own(self, gone):
        text = DOC.read_text(encoding="utf-8")

        assert f"**{gone}" not in text, (
            f"a section still describes the {gone} template, which does not ship"
        )


class TestTheQuickStartDoesNotDestroyTheSetup:
    """Following it overwrote the credentials `co create` had just written.

        # 1. Copy environment template
        cp .env.example .env

        # 2. Add your OpenAI API key to .env
        echo "OPENAI_API_KEY=sk-your-key-here" > .env

    There is no `.env.example` — step 1 fails — and step 2 truncates the `.env`
    the CLI wrote, which holds OPENONION_API_KEY, AGENT_EMAIL and AGENT_ADDRESS.
    A new user following the documented quick start loses the managed key that
    was working, and the free credits with it.

    Measured on a real `co create`:

        files       .co .env .gitignore Dockerfile agent.py requirements.txt
        .env        OPENONION_API_KEY=…  AGENT_EMAIL=…  AGENT_ADDRESS=…
        .env.example  absent
    """

    @pytest.fixture
    def quick_start(self):
        text = DOC.read_text(encoding="utf-8")
        match = re.search(
            r"### Quick Start After Init\n(.*?)(?=\n### |\n## |\Z)", text, re.S
        )
        assert match, "the Quick Start section is gone; this test needs updating"
        return match.group(1)

    def test_it_does_not_copy_a_file_that_is_not_there(self, quick_start):
        assert ".env.example" not in quick_start

    def test_it_does_not_truncate_the_env_file(self, quick_start):
        # `>> .env` appends and is fine; `> .env` truncates. Matching the
        # substring caught both, which is the kind of check that makes the
        # correct fix look like the bug.
        truncating = re.search(r"(?<!>)>\s*\.env\b", quick_start)

        assert truncating is None, (
            "this overwrites the OPENONION_API_KEY that co create wrote: "
            f"{truncating.group(0) if truncating else ''}"
        )

    def test_appending_is_allowed(self, quick_start):
        """The doc has to be able to show how to add your own key."""
        assert ">> .env" in quick_start

    def test_it_still_tells_you_how_to_run_the_agent(self, quick_start):
        assert "python agent.py" in quick_start


class TestTheDocIsStillTheShippedReference:
    """Guard against fixing this by deleting the section."""

    def test_the_file_is_there(self):
        assert DOC.is_file()

    def test_it_still_explains_templates(self):
        assert "Template" in DOC.read_text(encoding="utf-8")

    def test_it_still_documents_the_other_options(self):
        text = DOC.read_text(encoding="utf-8")

        for option in ("--key", "--yes", "--description"):
            assert option in text
