"""Kind first, then the name (owner, 2026-11-19, #3140): `co rem investigate person "Jalaj Jain"`. Invented data only."""
import json

import pytest
from typer.testing import CliRunner

from connectonion.cli.commands.rem_help import page as help_page
from connectonion.cli.main import app
from connectonion.rem import named_pages
from connectonion.rem.config import prepare
from connectonion.rem.files import Notebook, RemError, state_path, write_json

GLOSSARY = open(__file__.replace("tests/unit/test_rem_named_pages.py", "docs/cli/rem-naming.md"), encoding="utf-8").read()


@pytest.fixture
def book(tmp_path):
    prepare(tmp_path)
    book = Notebook(tmp_path)
    book.write("people/lena-brandt-a1b2c3d4e5.md", "# Lena Brandt\n\n## Facts\n- Also known as: Lena B, LB\n- Tags: kiln-pilot\n")
    book.write("people/lena-park.md", "# Lena Park\n\n## Facts\n- Also known as: LB\n- Tags: kiln-pilot\n")
    book.write("orgs/harbour-labs.md", "# Harbour Labs\n\n## Facts\n- Kind: company\n")
    book.write("projects/kiln-control.md", "# Kiln Control\n\n## What it is\nA controller.\n")
    book.write("skills/catalog/brief.md", "# brief\n\n## What it does\nWrites briefs.\n")
    book.write("decisions/one-vocabulary.md", "# One vocabulary\n\nOne list of tags.\n")
    write_json(state_path(tmp_path, "tags.json"), {"tags": {"kiln-pilot": {"label": "Kiln pilot", "kind": "project", "aliases": ["kp"]}}})
    return book


@pytest.mark.parametrize("kind, name, page", [
    ("person", "lena brandt", "people/lena-brandt-a1b2c3d4e5.md"),   # case and spaces ignored, hashed file name
    ("person", "Lena B", "people/lena-brandt-a1b2c3d4e5.md"),        # an alias
    ("org", "harbourlabs", "orgs/harbour-labs.md"),
    ("project", "Kiln Control", "projects/kiln-control.md"),
    ("skill", "brief", "skills/catalog/brief.md"),
    ("decision", "One vocabulary", "decisions/one-vocabulary.md"),
    ("tag", "Kiln pilot", "knowledge/kiln-pilot.md"),
    ("topic", "kp", "knowledge/kiln-pilot.md"),                       # topic is the same word as tag
])
def test_each_kind_resolves_a_name_to_one_page(book, kind, name, page):
    assert named_pages.resolve(book.root, kind, name) == page


def test_a_name_two_pages_share_is_refused_with_both_full_names(book):
    with pytest.raises(RemError) as raised:
        named_pages.resolve(book.root, "person", "LB")
    assert "Lena Brandt (people/lena-brandt-a1b2c3d4e5.md)" in str(raised.value)
    assert "Lena Park (people/lena-park.md)" in str(raised.value)


def test_an_unknown_kind_is_refused_with_the_kinds(book):
    with pytest.raises(RemError, match="person, org, project, tag"):
        named_pages.resolve(book.root, "company", "Harbour Labs")


def test_the_cli_takes_kind_and_name_a_plural_and_the_old_path(book):
    cli = CliRunner()
    run = lambda *args: cli.invoke(app, ["rem", "--root", str(book.root), "--json", *args])  # noqa: E731
    out = json.loads(run("investigate", "wibble").output)
    assert out["ok"] is False and "is not a kind" in json.dumps(out)
    out = json.loads(run("investigate", "person", "LB").output)
    assert out["ok"] is False and "lena-park.md" in json.dumps(out)
    listed = json.loads(run("investigate", "topics", "--list").output)  # a plural (an alias) runs the category
    assert listed["data"]["category"] == "tags"
    # The old path form still resolves (it reaches the investigation, which then needs a model here).
    out = json.loads(run("investigate", "people/no-such-page.md").output)
    assert "is not a kind" not in json.dumps(out)


def test_both_help_pages_open_with_the_same_glossary_the_naming_doc_holds():
    glossary = GLOSSARY.split("```\n", 2)[1].split("\n```")[0]
    assert glossary.startswith("Words:\n  page ")
    for name in ("co rem tag", "co rem investigate"):
        # The glossary opens the page, under its one-line title where the page has one: every help page's first
        # line is `co rem NAME — what it does`, and a wrapper sees its own name there.
        page = help_page(name)
        if page.startswith(name + " — "):
            page = page.split("\n\n", 1)[1]
        assert page.startswith(glossary), name
