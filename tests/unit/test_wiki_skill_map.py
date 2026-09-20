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
    assert "Human usage notes.\n" in notebook.read(page)
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


def test_reader_groups_installations_without_discarding_notes(tmp_path):
    from connectonion.wiki.reader import snapshot
    source = tmp_path / 'installed'
    skill(source, 'one')
    skill(source, 'two', description='A different implementation')
    nb = Notebook(tmp_path / 'wiki')
    result = map_skills(nb, [source])
    nb.write(result['created'][1], nb.read(result['created'][1]) + '\nKeep my notes.\n')
    before = {p: nb.read(p) for p in nb.list()}
    data = snapshot(nb.root)
    copies = [r for r in data['records'] if r.get('installation')]
    assert len(copies) == 2
    primary = next(r for r in copies if not r.get('catalog_parent'))
    assert len(primary['installations']) == 2
    assert any('Keep my notes.' in r['text'] for r in copies)
    assert before == {p: nb.read(p) for p in nb.list()}


def test_init_mail_is_explicit_metadata_only(tmp_path, monkeypatch):
    import connectonion.wiki.service as service
    import connectonion.wiki.map as mapping
    monkeypatch.setattr(service, 'mail_available', lambda kind: True)
    calls = []
    monkeypatch.setattr(service, 'mail_client', lambda kind: calls.append(kind) or object())
    monkeypatch.setattr(mapping, 'build_map', lambda root, sources, clients, **kw: {'mail_sources': sorted(clients)})
    runner = CliRunner()
    plain = runner.invoke(app, ['wiki', '--root', str(tmp_path), 'init'])
    assert plain.exit_code == 0, plain.output
    assert 'people_setup' in plain.output and not calls
    selected = runner.invoke(app, ['wiki', '--root', str(tmp_path), 'init', '--mail', 'outlook'])
    assert selected.exit_code == 0, selected.output
    assert calls == ['outlook']
    assert not service.subscriptions(tmp_path)['outlook']['enabled']
    invalid = runner.invoke(app, ['wiki', '--root', str(tmp_path), 'init', '--mail', 'invalid'])
    assert invalid.exit_code == 1
