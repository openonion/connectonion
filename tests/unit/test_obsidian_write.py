"""Preview-bound writes in synthetic vaults; no registry, model, or real notes."""

import os
from hashlib import sha256
from contextlib import contextmanager

import pytest

from connectonion.useful_tools import obsidian as api
from tests.unit.test_obsidian import isolated_home  # noqa: F401


POSIX_WRITE = pytest.mark.skipif(os.open not in os.supports_dir_fd, reason="POSIX publication required")


@pytest.fixture
def vault(tmp_path):
    root = tmp_path / "Vault"
    (root / "Course").mkdir(parents=True)
    (root / "Private").mkdir()
    (root / "Course/A.md").write_bytes(b"---\r\ntags: [demo]\r\n---\r\nOriginal")
    return root


def apply(change, vault, path, content, *, folders=("Course",)):
    preview = change(vault, path, content, folders=folders)
    return change(vault, path, content, folders=folders, yes=True, expect=preview["expect"])


@POSIX_WRITE
def test_create_preview_and_confirmation(vault):
    preview = api.create_note(vault, "Course/New.md", "# 中文\n", folders=["Course"])
    assert preview["preview"] is True
    assert not (vault / "Course/New.md").exists()
    result = api.create_note(vault, "Course/New.md", "# 中文\n", folders=["Course"],
                             yes=True, expect=preview["expect"])
    assert result["preview"] is False
    assert (vault / "Course/New.md").read_bytes() == "# 中文\n".encode()
    assert result["sha256"] == sha256("# 中文\n".encode()).hexdigest()


def test_create_never_overwrites_and_does_not_make_directories(vault):
    original = (vault / "Course/A.md").read_bytes()
    with pytest.raises(api.ObsidianError, match="already exists"):
        api.create_note(vault, "Course/A.md", "replace", folders=["Course"])
    with pytest.raises(api.ObsidianError):
        api.create_note(vault, "Course/Missing/New.md", "new", folders=["Course"])
    assert (vault / "Course/A.md").read_bytes() == original
    assert not (vault / "Course/Missing").exists()


@POSIX_WRITE
def test_append_preserves_frontmatter_and_crlf_and_used_token_fails(vault):
    note = vault / "Course/A.md"
    before = note.read_bytes()
    preview = api.append_note(vault, "Course/A.md", "Added", folders=["Course"])
    assert note.read_bytes() == before
    api.append_note(vault, "Course/A.md", "Added", folders=["Course"], yes=True, expect=preview["expect"])
    assert note.read_bytes() == before + b"\r\nAdded"
    with pytest.raises(api.ObsidianError, match="preview"):
        api.append_note(vault, "Course/A.md", "Added", folders=["Course"], yes=True, expect=preview["expect"])
    assert note.read_bytes() == before + b"\r\nAdded"


@pytest.mark.parametrize("original,content,expected", [(b"", "", b""), (b"a\n", "b", b"a\nb"),
                                                      (b"a", "b", b"a\nb"), (b"a", "", b"a")])
@POSIX_WRITE
def test_append_newlines_and_empty_input(vault, original, content, expected):
    note = vault / "Course/A.md"
    note.write_bytes(original)
    inode = note.stat().st_ino
    result = apply(api.append_note, vault, "Course/A.md", content)
    assert note.read_bytes() == expected
    assert result["changed"] == bool(content)
    if not content:
        assert note.stat().st_ino == inode


@POSIX_WRITE
def test_empty_create_is_allowed(vault):
    apply(api.create_note, vault, "Course/Empty.md", "")
    assert (vault / "Course/Empty.md").read_bytes() == b""


@pytest.mark.parametrize("path", ["../outside.md", "/tmp/out.md", "C:/out.md", "Course/../out.md",
                                  "Course\\out.md", "Course/out.txt", "Private/out.md", "Course/a\n.md",
                                  ".obsidian/x.md", ".trash/x.md", ".git/x.md"])
def test_unsafe_paths_are_rejected_without_creating_files(vault, path):
    before = set(vault.rglob("*"))
    with pytest.raises(ValueError):
        api.create_note(vault, path, "new", folders=["Course"])
    assert set(vault.rglob("*")) == before


def test_symlink_and_hardlink_append_are_refused(vault, tmp_path):
    outside = tmp_path / "outside.md"
    outside.write_text("private")
    (vault / "Course/link.md").symlink_to(outside)
    with pytest.raises(ValueError, match="symlink"):
        api.append_note(vault, "Course/link.md", "new", folders=["Course"])
    os.link(outside, vault / "Course/hard.md")
    with pytest.raises(api.ObsidianError, match="hard link"):
        api.append_note(vault, "Course/hard.md", "new", folders=["Course"])
    assert outside.read_text() == "private"


def test_symlink_parent_is_refused(vault):
    (vault / "Course/alias").symlink_to(vault / "Private", target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        api.create_note(vault, "Course/alias/A.md", "new", folders=["Course"])
    assert not (vault / "Private/A.md").exists()


@pytest.mark.parametrize("change", [api.create_note, api.append_note])
def test_confirmation_is_required(change, vault):
    with pytest.raises(ValueError, match="expect"):
        change(vault, "Course/New.md", "new", folders=["Course"], yes=True)
    with pytest.raises(ValueError, match="expect"):
        change(vault, "Course/New.md", "new", folders=["Course"], expect="0" * 64)


@pytest.mark.parametrize("alteration", ["content", "path", "scope", "vault", "file"])
def test_preview_is_bound_to_target_scope_content_and_version(vault, tmp_path, alteration):
    path, content, folders, root = "Course/A.md", "Added", ["Course"], vault
    preview = api.append_note(root, path, content, folders=folders)
    (vault / "Course/B.md").write_bytes((vault / path).read_bytes())
    if alteration == "content":
        content = "Other"
    elif alteration == "path":
        path = "Course/B.md"
    elif alteration == "scope":
        folders = ["."]
    elif alteration == "vault":
        root = tmp_path / "Second"
        (root / "Course").mkdir(parents=True)
        (root / path).write_bytes((vault / path).read_bytes())
    else:
        (vault / path).write_text("Edited elsewhere")
    before = (root / path).read_bytes()
    with pytest.raises(api.ObsidianError, match="preview"):
        api.append_note(root, path, content, folders=folders, yes=True, expect=preview["expect"])
    assert (root / path).read_bytes() == before


def test_create_rejects_replaced_parent_after_preview(vault):
    preview = api.create_note(vault, "Course/New.md", "new", folders=["Course"])
    (vault / "Course").rename(vault / "Old")
    (vault / "Course").mkdir()
    with pytest.raises(api.ObsidianError, match="preview"):
        api.create_note(vault, "Course/New.md", "new", folders=["Course"], yes=True, expect=preview["expect"])
    assert not (vault / "Course/New.md").exists()


@POSIX_WRITE
def test_failed_staging_preserves_original_and_cleans_temp(vault, monkeypatch):
    note = vault / "Course/A.md"
    before = note.read_bytes()
    preview = api.append_note(vault, "Course/A.md", "more", folders=["Course"])
    def fail_fsync(fd):
        raise OSError("simulated disk failure")
    monkeypatch.setattr(api.os, "fsync", fail_fsync)
    with pytest.raises(api.ObsidianError):
        api.append_note(vault, "Course/A.md", "more", folders=["Course"], yes=True, expect=preview["expect"])
    assert note.read_bytes() == before
    assert sorted(p.name for p in note.parent.iterdir()) == ["A.md"]


def test_append_missing_invalid_utf8_and_readonly_fail(vault):
    with pytest.raises(api.ObsidianError, match="never creates"):
        api.append_note(vault, "Course/Missing.md", "x", folders=["Course"])
    note = vault / "Course/A.md"
    note.write_bytes(b"\xff")
    with pytest.raises(api.ObsidianError):
        api.append_note(vault, "Course/A.md", "x", folders=["Course"])
    assert note.read_bytes() == b"\xff"
    note.chmod(0o444)
    with pytest.raises(api.ObsidianError, match="read-only"):
        api.append_note(vault, "Course/A.md", "x", folders=["Course"])


@POSIX_WRITE
def test_append_preserves_mode(vault):
    note = vault / "Course/A.md"
    note.chmod(0o640)
    apply(api.append_note, vault, "Course/A.md", "x")
    assert note.stat().st_mode & 0o777 == 0o640


@pytest.mark.parametrize("operation,path", [("create", "Course/New.md"), ("append", "Course/A.md")])
@POSIX_WRITE
def test_editor_change_during_staging_is_preserved(vault, monkeypatch, operation, path):
    change = api.create_note if operation == "create" else api.append_note
    preview = change(vault, path, "CLI text", folders=["Course"])
    def edit_during_flush(fd):
        (vault / path).write_text("Editor text\n")
    monkeypatch.setattr(api.os, "fsync", edit_during_flush)
    with pytest.raises(api.ObsidianError):
        change(vault, path, "CLI text", folders=["Course"], yes=True, expect=preview["expect"])
    assert (vault / path).read_text() == "Editor text\n"
    assert not list((vault / "Course").glob(".co-note-*.tmp"))


@POSIX_WRITE
def test_write_never_indexes_or_reads_sibling_notes(vault, monkeypatch):
    (vault / "Private/Broken.md").write_bytes(b"\xff")
    def forbidden(*args, **kwargs):
        pytest.fail("a single write must not index or parse other notes")
    monkeypatch.setattr(api, "_build_scope_index", forbidden)
    monkeypatch.setattr(api, "_load_scope_notes", forbidden)
    apply(api.create_note, vault, "Course/New.md", "New")
    apply(api.append_note, vault, "Course/A.md", "Added")
    assert (vault / "Private/Broken.md").read_bytes() == b"\xff"


@POSIX_WRITE
def test_parent_replaced_while_staging_is_not_written(vault, monkeypatch):
    preview = api.create_note(vault, "Course/New.md", "new", folders=["Course"])
    def swap_during_flush(fd):
        (vault / "Course").rename(vault / "Old")
        (vault / "Course").mkdir()
    monkeypatch.setattr(api.os, "fsync", swap_during_flush)
    with pytest.raises(api.ObsidianError):
        api.create_note(vault, "Course/New.md", "new", folders=["Course"], yes=True, expect=preview["expect"])
    assert not (vault / "Course/New.md").exists()
    assert not (vault / "Old/New.md").exists()
    assert not list((vault / "Old").glob(".co-note-*.tmp"))


def test_unsupported_directory_handles_refuse_without_a_file(vault, monkeypatch):
    preview = api.create_note(vault, "Course/New.md", "new", folders=["Course"])
    @contextmanager
    def unsupported(path):
        yield None
    monkeypatch.setattr(api, "_open_directory", unsupported)
    with pytest.raises(api.ObsidianError, match="POSIX"):
        api.create_note(vault, "Course/New.md", "new", folders=["Course"], yes=True, expect=preview["expect"])
    assert sorted(p.name for p in (vault / "Course").iterdir()) == ["A.md"]


@POSIX_WRITE
def test_busy_directory_refuses_without_writing(vault):
    import fcntl
    preview = api.create_note(vault, "Course/New.md", "new", folders=["Course"])
    with api._open_directory(vault / "Course") as parent:
        fcntl.flock(parent, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(api.ObsidianError, match="Another CLI write"):
            api.create_note(vault, "Course/New.md", "new", folders=["Course"], yes=True, expect=preview["expect"])
    assert sorted(p.name for p in (vault / "Course").iterdir()) == ["A.md"]
