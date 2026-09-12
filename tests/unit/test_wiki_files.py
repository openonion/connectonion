"""The notebook is plain files; its permission boundary is not a prompt."""


import pytest

from connectonion.wiki.config import prepare, read_config, set_config
from connectonion.wiki.files import CATEGORIES, Notebook, WikiError, maintenance_lock


def test_inspection_does_not_initialize(tmp_path):
    root = tmp_path / "wiki"
    assert read_config(root)["model"] == "gpt-5.3-codex-spark"
    assert Notebook(root).list() == []
    assert not root.exists()


def test_start_prepares_layout_without_overwriting(tmp_path):
    root = tmp_path / "wiki"
    prepare(root)
    note = Notebook(root)
    note.write("people/alice.md", "# Alice\nA colleague.")
    set_config(root, ["model", "gpt-5.6-luna"])
    prepare(root)
    assert note.read("people/alice.md").endswith("A colleague.")
    assert read_config(root)["model"] == "gpt-5.6-luna"
    assert (root / "skills/approved").is_dir()
    assert (root / "notes").is_dir()
    assert not (root / ".git").exists()
    assert not list(root.rglob("*.db"))


def test_confirmed_times_and_atomic_validation(tmp_path):
    prepare(tmp_path)
    assert read_config(tmp_path)["schedule"]["times"] == [
        "03:00", "04:00", "06:00", "17:00", "18:00", "19:00"]
    old = (tmp_path / "config.yaml").read_bytes()
    with pytest.raises(WikiError):
        set_config(tmp_path, ["model", "other", "schedule.times", "26:00"])
    assert (tmp_path / "config.yaml").read_bytes() == old


@pytest.mark.parametrize("name", [
    "../secret.md", "/tmp/secret.md", ".state/state.md", "config.yaml",
    "skills/approved/run.md", "skills/candidates/run.py", "people/../notes/a.md",
    "people/.hidden.md", "people/AGENTS.md", "people/SKILL.md",
])
def test_notebook_rejects_noncontent_targets(tmp_path, name):
    prepare(tmp_path)
    with pytest.raises(WikiError):
        Notebook(tmp_path).write(name, "must not write")


def test_symlink_cannot_escape_notebook(tmp_path):
    root = tmp_path / "wiki"
    prepare(root)
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / "people/escape").symlink_to(outside, target_is_directory=True)
    with pytest.raises(WikiError):
        Notebook(root).write("people/escape/secret.md", "bad")
    assert not list(outside.iterdir())


def test_lock_serializes_all_writers(tmp_path):
    prepare(tmp_path)
    with maintenance_lock(tmp_path):
        with pytest.raises(WikiError, match="busy"):
            with maintenance_lock(tmp_path):
                pytest.fail("two writers acquired the same notebook")
    with maintenance_lock(tmp_path):
        Notebook(tmp_path).write("notes/retry.md", "works")


def test_corrupt_state_is_not_silently_reset(tmp_path):
    prepare(tmp_path)
    (tmp_path / "config.yaml").write_text("model: [broken")
    with pytest.raises(WikiError):
        read_config(tmp_path)


def test_unchanged_write_preserves_mtime(tmp_path):
    prepare(tmp_path)
    notebook = Notebook(tmp_path)
    assert notebook.write("decisions/files.md", "Use Markdown") is True
    before = (tmp_path / "decisions/files.md").stat().st_mtime_ns
    assert notebook.write("decisions/files.md", "Use Markdown") is False
    assert (tmp_path / "decisions/files.md").stat().st_mtime_ns == before


def test_notebook_rejects_hardlinked_content(tmp_path):
    root = tmp_path / "wiki"
    prepare(root)
    outside = tmp_path / "outside.md"
    outside.write_text("outside secret")
    (root / "people/linked.md").hardlink_to(outside)
    with pytest.raises(WikiError):
        Notebook(root).read("people/linked.md")


def test_pages_refuse_secret_shaped_content(tmp_path):
    """With shell access the maintainer can read the whole disk; the notebook is its only
    write path, so a key pasted into a page is the exfiltration to stop."""
    from connectonion.wiki.config import prepare
    prepare(tmp_path)
    notebook = Notebook(tmp_path)
    for secret in ("-----BEGIN OPENSSH PRIVATE KEY-----\nAAAA", "token sk-abcdefghijklmnopqrstuvwxyz0123",
                   "AKIAIOSFODNN7EXAMPLE", "ghp_abcdefghijklmnopqrstuvwxyz0123456789", "xoxb-1234-abcdefgh"):
        with pytest.raises(WikiError, match="secret"):
            notebook.write("notes/a.md", f"# A\n{secret}\n")
    assert notebook.write("notes/a.md", "# A\nThe API key lives in keys.env, not here.\n")


def _person(root, path, body):
    (root / "people").mkdir(parents=True, exist_ok=True)
    (root / path).write_text(body, encoding="utf-8")


def test_the_roster_carries_what_it_takes_to_recognise_someone_again(tmp_path):
    """Literal search cannot bridge a changed letter; the roster is what can."""
    _person(tmp_path, "people/ody-zhou.md", "\n".join([
        "# Ody Zhou", "", "## Contact",
        "- Email: zhouodywork@gmail.com",
        "- Also known as: Ody, Odi, 欧迪, 周泽凯",
        "- Phone: Unknown",
        "", "## Who they are",
        "- OpenOnion partner running business development. [1]",
    ]))
    roster = Notebook(tmp_path).people()

    assert len(roster) == 1
    entry = roster[0]
    assert entry["path"] == "people/ody-zhou.md" and entry["title"] == "Ody Zhou"
    # The spelling a coding session would use is here even though it is not in the title.
    assert "Odi" in entry["aliases"] and "欧迪" in entry["aliases"]
    assert entry["emails"] == ["zhouodywork@gmail.com"]
    # The opening line says who they are, not what is missing from their contact card.
    assert "partner" in entry["summary"].lower()
    assert "Unknown" not in entry["summary"]


def test_an_address_written_inside_prose_is_read_as_an_address_not_the_prose(tmp_path):
    """A real page wrote "candidate `x@y` (case variant reported)"; splitting on
    commas handed that whole sentence back as an email."""
    _person(tmp_path, "people/andrew.md", "\n".join([
        "# Andrew", "", "## Contact",
        "- Email: candidate `andrewroth@coastalhomies.com.au` (case variant reported)",
        "", "## Who they are", "- A lead for outreach. [1]",
    ]))
    assert Notebook(tmp_path).people()[0]["emails"] == ["andrewroth@coastalhomies.com.au"]


def test_a_notebook_with_no_people_has_an_empty_roster(tmp_path):
    for name in CATEGORIES:
        (tmp_path / name).mkdir(parents=True, exist_ok=True)
    assert Notebook(tmp_path).people() == []
