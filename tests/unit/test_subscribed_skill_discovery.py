"""Active subscriptions are visible to both ConnectOnion skill readers."""

from pathlib import Path

from connectonion.cli.co_ai.skills.loader import discover_skills
from connectonion.useful_plugins.skills import _discover_all_skills, _get_skill_paths


def test_active_subscribed_skill_is_namespaced_and_loadable(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    skill_file = tmp_path / ".co" / "subs" / "alice" / "skills" / "demo" / "SKILL.md"
    skill_file.parent.mkdir(parents=True)
    skill_file.write_text("---\nname: demo\ndescription: One signed skill\n---\nDo work\n")
    (tmp_path / ".co" / "subscriptions.txt").write_text(
        "0x" + "a" * 64 + " alice\n"
    )

    ai = discover_skills(base_path=tmp_path)
    runtime = _discover_all_skills(project_dir=tmp_path)
    assert any(s.name == "alice-demo" and s.path == skill_file for s in ai)
    assert any(s.name == "alice-demo" and s.path == skill_file for s in runtime)
    assert skill_file in _get_skill_paths("alice-demo")

    (tmp_path / ".co" / "subscriptions.txt").write_text("")
    assert not any(s.name == "alice-demo" for s in discover_skills(base_path=tmp_path))
