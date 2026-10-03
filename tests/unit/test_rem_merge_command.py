"""Manual page merges through the public co rem command."""

import json

import pytest
from typer.testing import CliRunner

from connectonion.cli.main import app
from connectonion.rem.config import prepare
from connectonion.rem.files import Notebook, read_json, state_path


@pytest.fixture
def notebook(tmp_path):
    prepare(tmp_path)
    notebook = Notebook(tmp_path)
    notebook.write("people/alice.md", "# Alice\n\n## History\n- Led the launch. [1]\n\n"
                   "## Sources\n- [1] mail:launch\n\nInvestigation: investigated 2026-09-30\n")
    notebook.write("people/alice-copy.md", "# Alice copy\n\n## History\n- Met the design team. [1]\n\n"
                   "## Sources\n- [1] mail:design\n\nInvestigation: investigated 2026-10-01\n")
    notebook.write("people/bob.md", "# Bob\n\n## History\n- [Alice](./alice-copy.md) helped.\n")
    return notebook


def invoke(notebook, *args, json_output=False):
    prefix = ["rem", "--root", str(notebook.root)]
    if json_output:
        prefix.append("--json")
    return CliRunner().invoke(app, [*prefix, "merge", *args])


def test_merge_two_pages_combines_content_and_archives_old(notebook):
    result = invoke(notebook, "people/alice.md", "people/alice-copy.md", "-r", "same person")

    assert result.exit_code == 0, result.output
    page = notebook.read("people/alice.md")
    assert "- Led the launch. [1]" in page
    assert "- Met the design team. [2]" in page
    assert "- [2] mail:design" in page
    assert not notebook.exists("people/alice-copy.md")
    archived = notebook.root / ".state/archived/people/alice-copy.md"
    assert "Met the design team" in archived.read_text()
    assert read_json(state_path(notebook.root, "aliases.json"), {})["people/alice-copy.md"]["into"] == "people/alice.md"
    assert "[Alice](./alice.md)" in notebook.read("people/bob.md")
    assert "people/alice.md" in result.stdout
    assert ".state/archived/people/alice-copy.md" in result.stdout
    assert f"Next: co rem --root {notebook.root} show people/alice.md" in result.stdout


@pytest.mark.parametrize("missing", ["people/alice.md", "people/alice-copy.md"])
@pytest.mark.parametrize("json_output", [False, True])
def test_merge_missing_page_raises_clean_error(notebook, missing, json_output):
    (notebook.root / missing).unlink()

    result = invoke(notebook, "people/alice.md", "people/alice-copy.md", json_output=json_output)

    assert result.exit_code == 1
    if json_output:
        payload = json.loads(result.stdout)
        assert payload["ok"] is False
        assert f"Record not found: {missing}" in payload["data"]
        assert payload["next"].endswith(" list")
    else:
        assert f"Record not found: {missing}" in result.stderr
        assert "Next: co rem" in result.stderr and " list" in result.stderr
    assert not notebook.exists(missing)
    other = "people/alice-copy.md" if missing == "people/alice.md" else "people/alice.md"
    assert notebook.exists(other)
    assert not (notebook.root / ".state/archived/people/alice-copy.md").exists()


def test_merge_page_into_itself_raises_clean_error(notebook):
    before = notebook.read("people/alice.md")

    result = invoke(notebook, "people/alice.md", "people/alice.md")

    assert result.exit_code == 1
    assert "Choose two different pages to merge" in result.stderr
    assert "Traceback" not in result.output
    assert notebook.read("people/alice.md") == before
    assert read_json(state_path(notebook.root, "aliases.json"), {}) == {}


def test_merge_an_alias_of_the_kept_page_raises_clean_error(notebook):
    first = invoke(notebook, "people/alice.md", "people/alice-copy.md")
    assert first.exit_code == 0, first.output
    before = notebook.read("people/alice.md")

    result = invoke(notebook, "people/alice.md", "people/alice-copy.md")

    assert result.exit_code == 1
    assert "Choose two different pages to merge" in result.stderr
    assert notebook.read("people/alice.md") == before


def test_merge_json_output(notebook):
    result = invoke(notebook, "people/alice.md", "people/alice-copy.md", json_output=True)

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload == {
        "ok": True,
        "data": {"from": "people/alice-copy.md", "into": "people/alice.md",
                 "reason": "manual merge", "lines_merged": 1, "relinked": ["people/bob.md"],
                 "archived": ".state/archived/people/alice-copy.md"},
        "next": f"co rem --root {notebook.root} show people/alice.md",
    }
    assert "Next:" not in result.stdout
