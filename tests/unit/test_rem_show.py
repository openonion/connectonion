"""Bare page names resolve across the notebook without guessing."""

import json

import pytest
from typer.testing import CliRunner

from connectonion.cli.main import app
from connectonion.rem.config import prepare
from connectonion.rem.files import Notebook


def show(root, name):
    return CliRunner().invoke(app, ["rem", "--root", str(root), "--json", "show", name])


def test_show_resolves_project_by_folder_name(tmp_path):
    prepare(tmp_path)
    Notebook(tmp_path).stub_project("projects/harbour-a13bd.md", "Harbour Console", ["/fictional/work/harbour"])
    result = show(tmp_path, "HARBOUR")
    assert result.exit_code == 0, result.output
    assert "# Harbour Console" in json.loads(result.stdout)["data"]


def test_show_lists_ambiguous_names_across_kinds_without_showing_a_page(tmp_path):
    prepare(tmp_path)
    notebook = Notebook(tmp_path)
    notebook.write("people/harbour.md", "# Harbour\nPrivate person details.")
    notebook.write("projects/harbour-a13bd.md", "# Harbour\nPrivate project details.")
    result = show(tmp_path, "harbour")
    assert result.exit_code == 1
    text = json.loads(result.stdout)["data"]
    assert "people/harbour.md" in text and "projects/harbour-a13bd.md" in text
    assert "details" not in text


@pytest.mark.parametrize("record", ["orgs/harbour.md", "skills/catalog/harbour.md", "projects/harbour.md"])
def test_show_resolves_titles_case_insensitively(tmp_path, record):
    prepare(tmp_path)
    Notebook(tmp_path).write(record, "# Harbour\nFictional page.")
    result = show(tmp_path, "HARBOUR")
    assert result.exit_code == 0, result.output
    assert "Fictional page." in json.loads(result.stdout)["data"]


def test_show_exact_page_path_wins_over_name_matches(tmp_path):
    prepare(tmp_path)
    notebook = Notebook(tmp_path)
    notebook.write("projects/harbour.md", "# Harbour\nThe selected project.")
    notebook.write("people/other.md", "# projects/harbour.md\nThe other page.")
    result = show(tmp_path, "projects/harbour.md")
    assert result.exit_code == 0, result.output
    assert "The selected project." in json.loads(result.stdout)["data"]


def test_show_missing_name_says_which_page_kinds_were_searched(tmp_path):
    result = show(tmp_path, "harbour")
    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    text = payload["data"]
    assert '"harbour"' in text
    assert all(kind in text for kind in ("people", "projects", "orgs", "skills"))
    assert 'Search names and paths with `co rem list`.' in text
    assert payload["next"].endswith(" list")
