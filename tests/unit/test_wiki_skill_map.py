from pathlib import Path

import pytest
from typer.testing import CliRunner

from connectonion.cli.main import app
from connectonion.wiki.files import Notebook, WikiError
from connectonion.wiki.skill_map import map_skills, scan_skills


def skill(root, folder, name="Example", description="Describe the work"):
    path = root / folder / "SKILL.md"
    path.parent.mkdir(parents=True)
    path.write_text(f"---\nname: {name}\ndescription: {description}\n---\n\nDo not execute this body.\n")
    return path


def test_mapping_preserves_prose_and_distinguishes_same_name_sources(tmp_path):
    source = tmp_path / "installed"
    one, two = skill(source, "one"), skill(source, "two")
    (source / "alias").symlink_to(one.parent, target_is_directory=True)
    notebook = Notebook(tmp_path / "wiki")
    result = map_skills(notebook, [source])
    assert len(result["created"]) == 2
    assert {s["path"] for s in result["skills"]} == {str(one), str(two)}
    page = result["created"][0]
    text = notebook.read(page)
    assert "## How to use" in text and "Unknown" in text
    assert "Do not execute this body" not in text
    notebook.write(page, text + "\nHuman usage notes.\n")
    again = map_skills(notebook, [source])
    assert again["created"] == [] and len(again["preserved"]) == 2
    assert notebook.read(page).endswith("Human usage notes.\n")
    assert one.read_text().endswith("Do not execute this body.\n")
    one.unlink()
    map_skills(notebook, [source])
    assert notebook.path(page).exists()


def test_missing_and_unreadable_sources_are_not_silently_complete(tmp_path):
    source = tmp_path / "installed"
    bad = source / "broken" / "SKILL.md"
    bad.parent.mkdir(parents=True)
    bad.write_bytes(b"\xff")
    result = scan_skills([source, tmp_path / "absent"])
    assert result["skills"] == []
    assert result["errors"] == [{"path": str(bad), "error": "UnicodeDecodeError"}]
    assert [r["status"] for r in result["roots"]] == ["searched", "missing"]


def test_catalog_does_not_allow_executable_or_approved_writes(tmp_path):
    notebook = Notebook(tmp_path)
    notebook.write("skills/catalog/example.md", "# Example")
    assert notebook.list("skills") == ["skills/catalog/example.md"]
    for record in ("skills/catalog/SKILL.md", "skills/approved/example.md", "skills/other/example.md"):
        with pytest.raises(WikiError):
            notebook.write(record, "do something")


def test_cli_map_and_init_seed_skills_before_model_stage(tmp_path, monkeypatch):
    import connectonion.wiki.runner as stage_runner
    import connectonion.wiki.skill_map as mapping

    source = tmp_path / "installed"
    skill(source, "one")
    real_scan = mapping.scan_skills
    monkeypatch.setattr(mapping, "scan_skills", lambda directories=None: real_scan([source]))
    root = tmp_path / "wiki"
    runner = CliRunner()
    result = runner.invoke(app, ["wiki", "--root", str(root), "map-skills", "--skills-dir", str(source)])
    assert result.exit_code == 0, result.output
    assert (root / "skills/catalog/index.md").is_file()

    fresh = tmp_path / "fresh"
    def run_stage(notebook, items, config, stage):
        assert stage == "init"
        assert notebook.path("skills/catalog/index.md").is_file()
        assert len(notebook.list("skills")) == 2
        return {"ok": True}
    monkeypatch.setattr(stage_runner, "run_stage", run_stage)
    result = runner.invoke(app, ["wiki", "--root", str(fresh), "init"])
    assert result.exit_code == 0, result.output
