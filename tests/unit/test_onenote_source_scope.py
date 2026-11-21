import json
from pathlib import Path
import httpx
import pytest
import yaml
from connectonion.provider_credentials import ProviderCredentialError
from connectonion.useful_tools.onenote_source import OneNoteSource
from onenote_source_fixtures import graph, BASE, DATA, HTML

def test_notebook_section_and_page_pagination_and_visible_bound(graph):
    routes, calls = graph
    for path, field in [("/me/onenote/notebooks", "notebooks"),
                        ("/me/onenote/notebooks/nb-fixture/sections", "sections"),
                        ("/me/onenote/sections/section-fixture/pages", "pages")]:
        rows = DATA[field]
        routes[path] = {"value": rows[:1], "@odata.nextLink": BASE + path + "?$skip=1"}
        routes[path + "?$skip=1"] = {"value": rows[1:] or [{"id": "second", "displayName": "Later"}]}
    source = OneNoteSource()
    assert len(source.notebooks()) == 2
    assert len(source.sections("nb-fixture")) == 2
    listing = source.pages("nb-fixture", "section-fixture", limit=2)
    assert len(listing["pages"]) == 2 and listing["truncated"] is True
    assert any("$skip=1" in url for _, url, _ in calls)


@pytest.mark.parametrize("link", ["https://evil.invalid/steal", BASE + "/me/messages", "//evil.invalid/path",
                                  BASE + "/me/onenote/sections/other/pages"])
def test_untrusted_next_link_cannot_escape_collection(graph, link):
    routes, calls = graph
    routes["/me/onenote/notebooks"] = {"value": [], "@odata.nextLink": link}
    with pytest.raises(ValueError, match="pagination"):
        OneNoteSource().notebooks()
    assert len(calls) == 1


def test_pagination_loop_does_not_silently_return_partial_success(graph):
    routes, _ = graph
    path = "/me/onenote/notebooks"
    routes[path] = {"value": [], "@odata.nextLink": BASE + path}
    with pytest.raises(ValueError, match="pagination"):
        OneNoteSource().notebooks()


def test_empty_scope_is_valid_and_invalid_section_is_rejected(graph):
    routes, calls = graph
    routes["/me/onenote/sections/section-fixture/pages"] = {"value": []}
    assert OneNoteSource().pages("nb-fixture", "section-fixture")["pages"] == []
    with pytest.raises(ValueError, match="section"):
        OneNoteSource().pages("nb-fixture", "unknown")
    assert not any("unknown/pages" in url for _, url, _ in calls)


def test_nested_section_groups_are_not_silently_omitted(graph):
    routes, _ = graph
    routes["/me/onenote/notebooks/nb-fixture/sectionGroups"] = {"value": [{"id": "group"}]}
    routes["/me/onenote/sectionGroups/group/sections"] = {"value": [{"id": "nested", "displayName": "Nested notes"}]}
    routes["/me/onenote/sectionGroups/group/sectionGroups"] = {"value": []}
    assert {row["id"] for row in OneNoteSource().sections("nb-fixture")} == {"section-fixture", "nested"}


def test_section_group_cycle_fails_explicitly(graph):
    routes, _ = graph
    routes["/me/onenote/notebooks/nb-fixture/sectionGroups"] = {"value": [{"id": "cycle"}]}
    routes["/me/onenote/sectionGroups/cycle/sections"] = {"value": []}
    routes["/me/onenote/sectionGroups/cycle/sectionGroups"] = {"value": [{"id": "cycle"}]}
    with pytest.raises(ValueError, match="safety bound"):
        OneNoteSource().sections("nb-fixture")


def test_cli_success_empty_truncation_and_invalid_scope(graph):
    from typer.testing import CliRunner
    from connectonion.cli.main import app
    runner = CliRunner()
    routes, _ = graph
    result = runner.invoke(app, ["onenote", "source", "notebooks", "--json"])
    assert result.exit_code == 0 and json.loads(result.stdout)["notebooks"]
    result = runner.invoke(app, ["onenote", "source", "pages", "nb-fixture", "section-fixture", "--limit", "1"])
    assert result.exit_code == 0 and "more pages remain" in result.output
    routes["/me/onenote/sections/section-fixture/pages"] = {"value": []}
    result = runner.invoke(app, ["onenote", "source", "pages", "nb-fixture", "section-fixture"])
    assert result.exit_code == 0 and "No pages" in result.output
    result = runner.invoke(app, ["onenote", "source", "pages", "nb-fixture", "unknown", "--json"])
    assert result.exit_code == 1 and "section" in json.loads(result.stdout)["error"]


def test_selected_page_scope_guard_rejects_outside_page_before_body_read(graph):
    _, calls = graph
    source = OneNoteSource()
    scope = source.scope("nb-fixture", "section-fixture")
    assert source.selected_page("page-good", scope)["id"] == "page-good"
    with pytest.raises(ValueError, match="outside"):
        source.selected_page("page-outside", scope)
    assert not any(url.endswith("/content") for _, url, _ in calls)


def test_scope_config_preserves_policy_provenance_and_refuses_another_selection(tmp_path):
    from connectonion.useful_tools.onenote_scope import source_config
    scope = {"notebook": "nb-fixture", "section": "section-fixture", "pages": ["page-good"]}
    config = source_config(tmp_path, "fixture-account", scope, "co onenote source pages")
    assert config["driver"] == "onenote" and config["scope"] == scope
    assert config["retention"] == "90d" and config["media_policy"] == "metadata_only"
    assert config["read_only"] and config["registration"] == "external_import_only"
    assert config["validated_with"]["connectonion_version"]
    assert config["validated_with"]["path"] == str((tmp_path / "source.yaml").resolve())
    assert not list(tmp_path.iterdir()), "Building a declaration must not create import files"
    (tmp_path / "source.yaml").write_text(yaml.safe_dump(config), encoding="utf-8")
    with pytest.raises(ValueError, match="another account or scope"):
        source_config(tmp_path, "another-account", scope, "co onenote source pages")
