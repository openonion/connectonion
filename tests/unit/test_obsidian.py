"""Obsidian tool layer: vault discovery and folder scope (F13DBREAD-2), list_notes() and
read_note() (F13DBREAD-3), and search_notes() (F13DBREAD-7).

Only synthetic registries and vaults under tmp_path are used; no test reads a real
Obsidian installation, and discovery is checked to open no note and list no folder.
"""

import builtins
import io
import json
import os
import sys
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from connectonion.useful_tools import obsidian

HELP = "co obsidian vaults --help"


# -- fixtures --------------------------------------------------------------

@pytest.fixture(autouse=True)
def isolated_home(monkeypatch, tmp_path):
    """Home, HOME and the config dir all point into tmp_path; nothing real is read."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AGENT_CONFIG_PATH", str(tmp_path / "config"))
    return home


@pytest.fixture
def registry(monkeypatch, tmp_path):
    """Write obsidian.json and point discovery at it, whatever platform runs the test."""
    path = tmp_path / "registry" / "obsidian.json"
    path.parent.mkdir()
    monkeypatch.setattr(obsidian, "_registry_path", lambda: path)

    def write(data=None, *, raw=None):
        if raw is not None:
            path.write_bytes(raw)
        else:
            path.write_text(json.dumps(data), encoding="utf-8")
        return path
    return write


def _vault(tmp_path, name, notes=("Welcome.md",)):
    """A vault folder with a few notes, so a read of any of them would be noticed."""
    root = tmp_path / "vaults" / name
    (root / ".obsidian").mkdir(parents=True)
    for note in notes:
        (root / note).parent.mkdir(parents=True, exist_ok=True)
        (root / note).write_text(f"# {note}\nbody\n", encoding="utf-8")
    return root


def _entries(*paths, open_index=None, **extra):
    """obsidian.json as Obsidian writes it: {"vaults": {<id>: {"path", "ts", "open"?}}}."""
    vaults = {}
    for i, path in enumerate(paths):
        entry = {"path": str(path), "ts": 1790000000000 + i, **extra}
        if open_index == i:
            entry["open"] = True
        vaults[f"{i:016x}"] = entry
    return {"vaults": vaults}


class _Spy:
    """What the code under test read or listed; paused() hides the test's own snapshots."""

    def __init__(self):
        self.opened, self.listed, self.recording = [], [], True

    @contextmanager
    def paused(self):
        self.recording = False
        try:
            yield
        finally:
            self.recording = True


@pytest.fixture
def no_note_reads(monkeypatch, tmp_path):
    """Fail on reading any .md file or listing any directory under tmp_path/vaults.

    A test that inspects the disk itself (rglob for a before/after snapshot) does so
    inside `with no_note_reads.paused():`, so only the code under test is counted.
    """
    vaults = str(tmp_path / "vaults")
    spy = _Spy()
    opened, listed = spy.opened, spy.listed
    real_open = io.open

    def spy_open(file, mode="r", *args, **kwargs):
        name = os.fspath(file) if isinstance(file, (str, bytes, os.PathLike)) else ""
        writing = any(flag in mode for flag in "wax+")      # the test writing its own fixture notes
        if spy.recording and isinstance(name, str) and name.endswith(".md") and not writing:
            opened.append(name)
        return real_open(file, mode, *args, **kwargs)

    def refuse_listing(real):
        def spy_listing(path=".", *args, **kwargs):
            if spy.recording and os.fspath(path).startswith(vaults):
                listed.append(os.fspath(path))
            return real(path, *args, **kwargs)
        return spy_listing

    monkeypatch.setattr(io, "open", spy_open)
    monkeypatch.setattr(builtins, "open", spy_open)
    monkeypatch.setattr(os, "scandir", refuse_listing(os.scandir))
    monkeypatch.setattr(os, "listdir", refuse_listing(os.listdir))
    monkeypatch.setattr(os, "walk", refuse_listing(os.walk))
    yield spy
    assert opened == [], f"discovery opened notes: {opened}"
    assert listed == [], f"discovery listed vault folders: {listed}"


def _assert_registry_error(error):
    assert isinstance(error, obsidian.ObsidianError)
    assert str(error)
    assert error.next_step.startswith("co obsidian")
    assert "Traceback" not in str(error)


# -- ObsidianError ---------------------------------------------------------

def test_error_carries_cause_next_step_and_failed_paths():
    error = obsidian.ObsidianError("cannot read", "co obsidian vaults", failed_paths=["a.md", "b/c.md"])

    assert str(error) == "cannot read"
    assert error.next_step == "co obsidian vaults"
    assert error.failed_paths == ["a.md", "b/c.md"]


def test_error_failed_paths_default_to_none():
    assert obsidian.ObsidianError("x", HELP).failed_paths is None


# -- where the registry lives ---------------------------------------------

@pytest.mark.parametrize("platform,parts", [
    ("darwin", ("Library", "Application Support", "obsidian", "obsidian.json")),
    ("linux", (".config", "obsidian", "obsidian.json")),
])
def test_registry_path_is_the_platforms_own(platform, parts, monkeypatch, isolated_home):
    monkeypatch.setattr(sys, "platform", platform)

    assert obsidian._registry_path() == isolated_home.joinpath(*parts)


def test_registry_path_on_windows_is_under_appdata(monkeypatch, tmp_path):
    appdata = tmp_path / "AppData" / "Roaming"
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("APPDATA", str(appdata))

    assert obsidian._registry_path() == appdata / "obsidian" / "obsidian.json"


@pytest.mark.parametrize("appdata", [None, "", "   "], ids=["missing", "empty", "blank"])
def test_registry_path_on_windows_without_appdata_is_an_error(appdata, monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    if appdata is None:
        monkeypatch.delenv("APPDATA", raising=False)
    else:
        monkeypatch.setenv("APPDATA", appdata)

    with pytest.raises(obsidian.ObsidianError) as caught:
        obsidian._registry_path()
    _assert_registry_error(caught.value)


def test_registry_path_on_an_unsupported_platform_is_an_error(monkeypatch):
    monkeypatch.setattr(sys, "platform", "sunos5")

    with pytest.raises(obsidian.ObsidianError) as caught:
        obsidian._registry_path()
    _assert_registry_error(caught.value)


def test_registry_path_does_not_touch_the_disk(monkeypatch, isolated_home):
    """Locating the registry is a path computation; it never searches HOME."""
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(os, "scandir", lambda *a, **k: pytest.fail("scanned the disk"))
    monkeypatch.setattr(os, "walk", lambda *a, **k: pytest.fail("walked the disk"))

    obsidian._registry_path()
    assert not (isolated_home / ".config").exists()


# -- reading the registry --------------------------------------------------

def test_missing_registry_is_no_vaults(tmp_path):
    assert obsidian._read_vault_registry(tmp_path / "nowhere" / "obsidian.json") == []


@pytest.mark.parametrize("data", [{"vaults": {}}, {}], ids=["empty-vaults", "no-vaults-key"])
def test_registry_without_vaults_is_empty(data, registry):
    assert obsidian._read_vault_registry(registry(data)) == []


def test_registry_entries_keep_unknown_fields(registry, tmp_path):
    vault = _vault(tmp_path, "Notes")
    path = registry({"vaults": {"abc": {"path": str(vault), "ts": 1, "open": True, "future": {"x": 1}}},
                     "frame": "hidden", "updateDisabled": True})

    entries = obsidian._read_vault_registry(path)

    assert len(entries) == 1
    assert entries[0]["path"] == str(vault)
    assert entries[0]["open"] is True


@pytest.mark.parametrize("raw", [
    b"{not json",
    b"",
    b"\xff\xfe\x00 not utf-8",
], ids=["bad-json", "empty-file", "not-utf8"])
def test_unreadable_registry_text_is_an_error(raw, registry):
    path = registry(raw=raw)

    with pytest.raises(obsidian.ObsidianError) as caught:
        obsidian._read_vault_registry(path)
    _assert_registry_error(caught.value)


@pytest.mark.parametrize("data", [
    [],
    "vaults",
    {"vaults": []},
    {"vaults": "abc"},
    {"vaults": {"a": "not an object"}},
    {"vaults": {"a": {}}},
    {"vaults": {"a": {"path": None}}},
    {"vaults": {"a": {"path": 42}}},
    {"vaults": {"a": {"path": ""}}},
    {"vaults": {"a": {"path": "   "}}},
    {"vaults": {"a": {"path": "/tmp/bad\x00path"}}},
    {"vaults": {"a": {"path": "relative/vault"}}},
    {"vaults": {"a": {"path": "~/Vault"}}},
    {"vaults": {"a": {"path": "/abs/vault", "open": "true"}}},
    {"vaults": {"a": {"path": "/abs/vault", "open": 1}}},
    {"vaults": {"a": {"path": "/abs/vault", "open": None}}},
], ids=["top-list", "top-string", "vaults-list", "vaults-string", "entry-string", "no-path",
        "null-path", "number-path", "empty-path", "blank-path", "nul-path", "relative-path",
        "tilde-path", "open-string", "open-number", "open-null"])
def test_malformed_registry_is_an_error_not_an_empty_list(data, registry):
    path = registry(data)

    with pytest.raises(obsidian.ObsidianError) as caught:
        obsidian._read_vault_registry(path)
    _assert_registry_error(caught.value)


def test_one_bad_entry_fails_the_whole_registry(registry, tmp_path):
    good = _vault(tmp_path, "Good")
    path = registry({"vaults": {"a": {"path": str(good)}, "b": {"path": ""}}})

    with pytest.raises(obsidian.ObsidianError):
        obsidian._read_vault_registry(path)


def test_registry_that_is_a_directory_is_an_error(tmp_path):
    folder = tmp_path / "obsidian.json"
    folder.mkdir()

    with pytest.raises(obsidian.ObsidianError) as caught:
        obsidian._read_vault_registry(folder)
    _assert_registry_error(caught.value)


@pytest.mark.skipif(sys.platform == "win32" or (hasattr(os, "geteuid") and os.geteuid() == 0),
                    reason="needs POSIX permissions and a non-root user")
def test_registry_without_read_permission_is_an_error(registry):
    path = registry({"vaults": {}})
    path.chmod(0)
    try:
        with pytest.raises(obsidian.ObsidianError) as caught:
            obsidian._read_vault_registry(path)
        _assert_registry_error(caught.value)
    finally:
        path.chmod(0o600)


# -- discover_vaults() -----------------------------------------------------

def test_no_registry_discovers_nothing(registry):
    assert obsidian.discover_vaults() == []


def test_vault_record_has_exactly_the_contract_fields(registry, tmp_path):
    vault = _vault(tmp_path, "Course Notes")
    registry(_entries(vault, open_index=0))

    found = obsidian.discover_vaults()

    assert found == [{"name": "Course Notes", "path": str(vault.resolve()), "available": True, "open": True}]
    assert json.loads(json.dumps(found)) == found


def test_open_defaults_to_false(registry, tmp_path):
    registry(_entries(_vault(tmp_path, "Notes")))

    assert obsidian.discover_vaults()[0]["open"] is False


def test_vaults_are_sorted_by_name_then_path(registry, tmp_path):
    zeta, alpha = _vault(tmp_path, "Zeta"), _vault(tmp_path, "Alpha")
    same_b = tmp_path / "b" / "Same"
    same_a = tmp_path / "a" / "Same"
    for folder in (same_a, same_b):
        folder.mkdir(parents=True)
    registry(_entries(zeta, same_b, alpha, same_a))

    found = obsidian.discover_vaults()

    assert [v["name"] for v in found] == ["Alpha", "Same", "Same", "Zeta"]
    assert [v["path"] for v in found[1:3]] == [str(same_a.resolve()), str(same_b.resolve())]


def test_stale_paths_are_listed_as_unavailable(registry, tmp_path):
    """A moved or deleted vault stays visible, so the user sees why it cannot be used."""
    gone = tmp_path / "vaults" / "Gone"
    not_a_dir = tmp_path / "vaults" / "file-vault"
    not_a_dir.parent.mkdir(parents=True)
    not_a_dir.write_text("not a folder", encoding="utf-8")
    here = _vault(tmp_path, "Here")
    registry(_entries(gone, not_a_dir, here))

    found = {v["name"]: v for v in obsidian.discover_vaults()}

    assert found["Gone"]["available"] is False
    assert found["file-vault"]["available"] is False
    assert found["Here"]["available"] is True
    assert found["Gone"]["path"].endswith("Gone")


def test_duplicate_registrations_are_listed_once_and_stay_open(registry, tmp_path):
    vault = _vault(tmp_path, "Notes")
    registry({"vaults": {"a": {"path": str(vault)},
                         "b": {"path": str(vault) + os.sep, "open": True},
                         "c": {"path": str(vault / "sub" / "..")}}})

    found = obsidian.discover_vaults()

    assert len(found) == 1
    assert found[0]["open"] is True


@pytest.mark.skipif(sys.platform == "win32", reason="symlinks need privileges on Windows")
def test_a_symlink_to_a_registered_vault_is_the_same_vault(registry, tmp_path):
    vault = _vault(tmp_path, "Real")
    link = tmp_path / "Link"
    link.symlink_to(vault, target_is_directory=True)
    registry(_entries(vault, link))

    found = obsidian.discover_vaults()

    assert [v["path"] for v in found] == [str(vault.resolve())]


def test_several_vaults_with_one_open(registry, tmp_path):
    a, b, c = (_vault(tmp_path, n) for n in ("A", "B", "C"))
    registry(_entries(a, b, c, open_index=1))

    assert [(v["name"], v["open"]) for v in obsidian.discover_vaults()] == [("A", False), ("B", True), ("C", False)]


def test_discovery_reads_no_note_and_lists_no_folder(registry, tmp_path, no_note_reads):
    vault = _vault(tmp_path, "Notes", notes=("a.md", "deep/b.md", ".obsidian/workspace.md"))
    registry(_entries(vault, tmp_path / "vaults" / "Missing"))

    assert len(obsidian.discover_vaults()) == 2


def test_discovery_changes_nothing_on_disk(registry, tmp_path):
    vault = _vault(tmp_path, "Notes", notes=("a.md", "b/c.md"))
    path = registry(_entries(vault, open_index=0))

    def snapshot():
        files = sorted(p for p in tmp_path.rglob("*"))
        return [(str(p), p.stat().st_mtime_ns, p.is_file() and p.read_bytes()) for p in files]

    before = snapshot()
    obsidian.discover_vaults()
    obsidian.discover_vaults()

    assert snapshot() == before
    assert not (Path.home() / ".co" / "obsidian-listings").exists()
    assert path.read_text(encoding="utf-8") == json.dumps(_entries(vault, open_index=0))


def test_discovery_reports_a_malformed_registry(registry):
    registry({"vaults": {"a": {"path": "relative"}}})

    with pytest.raises(obsidian.ObsidianError) as caught:
        obsidian.discover_vaults()
    _assert_registry_error(caught.value)


@pytest.mark.parametrize("platform,parts", [
    ("darwin", ("Library", "Application Support", "obsidian", "obsidian.json")),
    ("linux", (".config", "obsidian", "obsidian.json")),
])
def test_discovery_reads_only_the_current_platforms_registry(platform, parts, monkeypatch, isolated_home, tmp_path):
    """The other platforms' registries are present but ignored."""
    mine, other = _vault(tmp_path, "Mine"), _vault(tmp_path, "Other")
    for candidate in (("Library", "Application Support", "obsidian", "obsidian.json"),
                      (".config", "obsidian", "obsidian.json")):
        target = isolated_home.joinpath(*candidate)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(_entries(mine if candidate == parts else other)), encoding="utf-8")
    monkeypatch.setattr(sys, "platform", platform)

    assert [v["name"] for v in obsidian.discover_vaults()] == ["Mine"]


def test_discovery_on_windows_reads_appdata(monkeypatch, tmp_path):
    appdata = tmp_path / "AppData" / "Roaming"
    (appdata / "obsidian").mkdir(parents=True)
    vault = _vault(tmp_path, "WinVault")
    (appdata / "obsidian" / "obsidian.json").write_text(json.dumps(_entries(vault)), encoding="utf-8")
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("APPDATA", str(appdata))

    assert [v["name"] for v in obsidian.discover_vaults()] == ["WinVault"]


# -- _validate_scope(): the folders a later command may read -------------

@pytest.fixture
def vault(tmp_path):
    root = _vault(tmp_path, "Scope", notes=("root.md", "Course/a.md", "Course/Week1/b.md", "Other/c.md"))
    (root / ".trash").mkdir()
    (root / ".git").mkdir()
    (root / "file.md").write_text("x", encoding="utf-8")
    return root


def test_dot_selects_the_whole_vault_with_system_exclusions(vault):
    scope = obsidian._validate_scope(vault, ["."])

    assert scope.vault_path == vault.resolve()
    assert scope.folders == (vault.resolve(),)
    assert scope.excluded_dirs == frozenset({".obsidian", ".trash", ".git"})
    assert scope.follow_symlinks is False


def test_vault_path_may_be_a_string(vault):
    assert obsidian._validate_scope(str(vault), ["Course"]).folders == ((vault / "Course").resolve(),)


def test_vault_path_expands_the_home_tilde(isolated_home, tmp_path):
    inside = isolated_home / "MyVault"
    (inside / "Notes").mkdir(parents=True)

    scope = obsidian._validate_scope("~/MyVault", ["Notes"])

    assert scope.vault_path == inside.resolve()


def test_several_folders_are_kept_in_a_stable_order(vault):
    scope = obsidian._validate_scope(vault, ["Other", "Course"])

    assert scope.folders == ((vault / "Course").resolve(), (vault / "Other").resolve())
    assert obsidian._validate_scope(vault, ["Course", "Other"]).folders == scope.folders


@pytest.mark.parametrize("folders,expected", [
    (["Course", "Course"], ["Course"]),
    (["Course/Week1", "Course"], ["Course"]),
    (["Course", "Course/Week1"], ["Course"]),
    ([".", "Course", "Other"], ["."]),
    (["Course/", "./Course"], ["Course"]),
], ids=["duplicate", "child-first", "parent-first", "dot-wins", "spelling"])
def test_overlapping_folders_are_deduplicated(folders, expected, vault):
    scope = obsidian._validate_scope(vault, folders)

    assert scope.folders == tuple((vault / e).resolve() for e in expected)


@pytest.mark.parametrize("folders", [None, [], (), "Course", b"Course"],
                         ids=["none", "empty-list", "empty-tuple", "bare-string", "bytes"])
def test_folders_must_be_given_explicitly(folders, vault):
    with pytest.raises(ValueError):
        obsidian._validate_scope(vault, folders)


@pytest.mark.parametrize("vault_path", [None, "", "   "], ids=["none", "empty", "blank"])
def test_vault_path_must_be_given(vault_path):
    with pytest.raises(ValueError):
        obsidian._validate_scope(vault_path, ["."])


@pytest.mark.parametrize("folder", ["", "   ", "Course\x00x", 5, None],
                         ids=["empty", "blank", "nul", "number", "none"])
def test_a_folder_must_be_a_non_empty_relative_string(folder, vault):
    with pytest.raises(ValueError):
        obsidian._validate_scope(vault, [folder])


@pytest.mark.parametrize("folder", ["..", "../Scope", "Course/../../x", "Course/../Other"],
                         ids=["parent", "parent-back-in", "escape", "inner-dotdot"])
def test_dotdot_is_refused(folder, vault):
    with pytest.raises(ValueError):
        obsidian._validate_scope(vault, [folder])


def test_absolute_folder_is_refused_even_inside_the_vault(vault):
    with pytest.raises(ValueError):
        obsidian._validate_scope(vault, [str(vault / "Course")])


@pytest.mark.parametrize("folder", [".obsidian", ".trash", ".git", "Course/.git", ".obsidian/plugins"])
def test_system_folders_cannot_be_selected(folder, vault):
    (vault / "Course" / ".git").mkdir(exist_ok=True)
    (vault / ".obsidian" / "plugins").mkdir(exist_ok=True)

    with pytest.raises(ValueError):
        obsidian._validate_scope(vault, [folder])


def test_one_bad_folder_refuses_the_whole_selection(vault):
    with pytest.raises(ValueError):
        obsidian._validate_scope(vault, ["Course", ".."])


@pytest.mark.parametrize("folder", ["Missing", "file.md"], ids=["missing", "a-file"])
def test_folder_must_be_an_existing_directory(folder, vault):
    with pytest.raises(obsidian.ObsidianError) as caught:
        obsidian._validate_scope(vault, [folder])
    _assert_registry_error(caught.value)


def test_missing_vault_is_an_error(tmp_path):
    with pytest.raises(obsidian.ObsidianError) as caught:
        obsidian._validate_scope(tmp_path / "vaults" / "Nope", ["."])
    _assert_registry_error(caught.value)


def test_a_file_is_not_a_vault(tmp_path):
    note = tmp_path / "note.md"
    note.write_text("x", encoding="utf-8")

    with pytest.raises(obsidian.ObsidianError):
        obsidian._validate_scope(note, ["."])


@pytest.mark.skipif(sys.platform == "win32", reason="symlinks need privileges on Windows")
class TestSymlinks:
    def test_symlinked_vault_is_refused(self, vault, tmp_path):
        link = tmp_path / "VaultLink"
        link.symlink_to(vault, target_is_directory=True)

        with pytest.raises(ValueError):
            obsidian._validate_scope(link, ["."])

    def test_symlinked_folder_inside_the_vault_is_refused(self, vault):
        (vault / "Alias").symlink_to(vault / "Course", target_is_directory=True)

        with pytest.raises(ValueError):
            obsidian._validate_scope(vault, ["Alias"])

    def test_symlink_pointing_outside_the_vault_is_refused(self, vault, tmp_path):
        outside = tmp_path / "outside"
        outside.mkdir()
        (vault / "Escape").symlink_to(outside, target_is_directory=True)

        with pytest.raises(ValueError):
            obsidian._validate_scope(vault, ["Escape"])

    def test_symlink_in_a_middle_component_is_refused(self, vault):
        (vault / "Hop").symlink_to(vault / "Course", target_is_directory=True)

        with pytest.raises(ValueError):
            obsidian._validate_scope(vault, ["Hop/Week1"])


@pytest.mark.skipif(sys.platform == "win32" or (hasattr(os, "geteuid") and os.geteuid() == 0),
                    reason="needs POSIX permissions and a non-root user")
def test_unreadable_folder_is_an_error(vault):
    locked = vault / "Locked"
    locked.mkdir()
    locked.chmod(0)
    try:
        with pytest.raises(obsidian.ObsidianError):
            obsidian._validate_scope(vault, ["Locked"])
    finally:
        locked.chmod(0o700)


def test_validating_a_scope_reads_no_note_and_lists_no_folder(vault, no_note_reads):
    obsidian._validate_scope(vault, [".", "Course", "Other"])


def test_validating_a_scope_changes_nothing_on_disk(vault):
    def snapshot():
        return sorted((str(p), p.stat().st_mtime_ns) for p in vault.rglob("*"))

    before = snapshot()
    obsidian._validate_scope(vault, ["Course", "Other"])

    assert snapshot() == before


# =========================================================================
# F13DBREAD-3: list_notes() and read_note() over an explicit folder scope
# =========================================================================

BASE_NS = 1_790_000_000_000_000_000          # 2026-09-21, so every mtime is a fixed, ordered value


def _notes_vault(tmp_path, files, name="Notes"):
    """A vault built from {relative path: text or bytes}; mtimes follow the dict order, oldest first."""
    root = tmp_path / "vaults" / name
    (root / ".obsidian").mkdir(parents=True)
    for i, (relative, body) in enumerate(files.items()):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(body, bytes):
            path.write_bytes(body)
        else:
            path.write_text(body, encoding="utf-8", newline="")
        os.utime(path, ns=(BASE_NS + i * 1_000_000_000, BASE_NS + i * 1_000_000_000))
    return root


def _by_path(notes):
    return {note["path"]: note for note in notes}


def _link(note, target):
    return next(link for link in note["links"] if link["target"] == target)


def _disk(root):
    """Every file and folder with its bytes and mtime, to prove a read changed nothing."""
    return sorted((str(p), p.stat().st_mtime_ns, p.read_bytes() if p.is_file() else None)
                  for p in root.rglob("*") if not p.is_symlink())


NOTE_FIELDS = {"note_key", "path", "title", "content", "body_offset", "frontmatter", "tags",
               "links", "backlinks", "modified_at", "mtime_ns"}
LINK_FIELDS = {"raw", "target", "alias", "anchor", "embedded", "target_kind", "resolved_path", "resolution"}


@pytest.fixture
def course(tmp_path):
    return _notes_vault(tmp_path, {
        "Course/Week1/Logic.md": "---\ntitle: Not the title\ntags: [COMP4418/logic, '#exam']\n"
                                 "id: lecture-1\ndate: 2026-10-01\n---\n# Heading is not the title\n"
                                 "See [[Sets]] and [[Week2/Proofs|the proofs]].\n",
        "Course/Week1/Sets.md": "Sets body links back to [[Logic]].\n",
        "Course/Week2/Proofs.md": "Proofs #proof\n",
        "Course/notes.txt": "plain text is not a note\n",
        "Course/board.canvas": "{}",
        "Course/.obsidian/hidden.md": "inside an excluded folder\n",
        "Other/Outside.md": "Out of scope\n",
        "Root.md": "At the vault root\n",
    })


def test_note_record_has_the_contract_fields(course):
    notes = obsidian.list_notes(course, folders=["Course"])

    assert notes
    for note in notes:
        assert set(note) == NOTE_FIELDS
        assert note["note_key"] == note["path"]
        for link in note["links"]:
            assert set(link) == LINK_FIELDS
    assert json.loads(json.dumps(notes)) == notes


def test_only_markdown_in_the_selected_folders_is_listed(course):
    paths = sorted(note["path"] for note in obsidian.list_notes(course, folders=["Course"]))

    assert paths == ["Course/Week1/Logic.md", "Course/Week1/Sets.md", "Course/Week2/Proofs.md"]


def test_dot_lists_the_whole_vault_without_system_folders(course):
    paths = {note["path"] for note in obsidian.list_notes(course, folders=["."])}

    assert paths == {"Course/Week1/Logic.md", "Course/Week1/Sets.md", "Course/Week2/Proofs.md",
                     "Other/Outside.md", "Root.md"}


def test_overlapping_folders_list_each_note_once(course):
    notes = obsidian.list_notes(course, folders=["Course", "Course/Week1", "Course/Week1"])

    paths = [note["path"] for note in notes]
    assert sorted(paths) == sorted(set(paths))
    assert len(paths) == 3


def test_paths_are_vault_relative_posix(course):
    for note in obsidian.list_notes(course, folders=["Course/Week1"]):
        assert not note["path"].startswith("/")
        assert "\\" not in note["path"]
        assert (course / note["path"]).is_file()


def test_title_is_the_filename_not_h1_or_frontmatter(course):
    logic = _by_path(obsidian.list_notes(course, folders=["Course"]))["Course/Week1/Logic.md"]

    assert logic["title"] == "Logic"


def test_content_is_the_whole_file_and_body_offset_skips_frontmatter(course):
    logic = _by_path(obsidian.list_notes(course, folders=["Course"]))["Course/Week1/Logic.md"]

    assert logic["content"] == (course / "Course/Week1/Logic.md").read_text(encoding="utf-8")
    assert logic["content"][logic["body_offset"]:].startswith("# Heading is not the title")


def test_a_note_without_frontmatter_has_offset_zero_and_empty_properties(course):
    sets = _by_path(obsidian.list_notes(course, folders=["Course"]))["Course/Week1/Sets.md"]

    assert sets["frontmatter"] == {}
    assert sets["body_offset"] == 0


def test_frontmatter_is_parsed_with_dates_as_iso_and_id_kept(course):
    logic = _by_path(obsidian.list_notes(course, folders=["Course"]))["Course/Week1/Logic.md"]

    assert logic["frontmatter"]["date"] == "2026-10-01"
    assert logic["frontmatter"]["id"] == "lecture-1"
    assert logic["note_key"] == "Course/Week1/Logic.md"


def test_crlf_and_utf8_bom_content_is_kept_byte_for_byte(tmp_path):
    raw = "﻿---\r\ntags: a\r\n---\r\n中文 body\r\n".encode("utf-8")
    vault = _notes_vault(tmp_path, {"Win.md": raw})

    note = obsidian.list_notes(vault, folders=["."])[0]

    assert note["content"].encode("utf-8") == raw
    assert note["frontmatter"] == {"tags": "a"}
    assert note["content"][note["body_offset"]:] == "中文 body\r\n"


def test_modified_at_is_utc_iso_and_matches_mtime(course):
    for note in obsidian.list_notes(course, folders=["Course"]):
        moment = datetime.fromisoformat(note["modified_at"])
        assert moment.utcoffset() == timedelta(0)
        assert note["mtime_ns"] == (course / note["path"]).stat().st_mtime_ns


def test_empty_folder_lists_nothing(tmp_path):
    vault = _notes_vault(tmp_path, {"Full/a.md": "a"})
    (vault / "Empty").mkdir()

    assert obsidian.list_notes(vault, folders=["Empty"]) == []


@pytest.mark.parametrize("folders", [None, []], ids=["none", "empty"])
def test_listing_without_folders_reads_nothing(folders, course, monkeypatch):
    monkeypatch.setattr(obsidian, "_read_markdown", lambda *a: pytest.fail("read a note"))

    with pytest.raises(ValueError):
        obsidian.list_notes(course, folders=folders)


def test_notes_outside_the_scope_are_never_read(tmp_path, monkeypatch):
    """An unreadable note outside the folders cannot fail the load, because it is not opened."""
    vault = _notes_vault(tmp_path, {"In/a.md": "[[b]]", "Out/b.md": b"\xff\xfe not utf-8"})
    read = []
    real = obsidian._read_markdown
    monkeypatch.setattr(obsidian, "_read_markdown", lambda scope, path: read.append(path.name) or real(scope, path))

    notes = obsidian.list_notes(vault, folders=["In"])

    assert [note["path"] for note in notes] == ["In/a.md"]
    assert read == ["a.md"]
    assert _link(notes[0], "b")["resolution"] == "out_of_scope"


def test_each_selected_note_is_read_once(course, monkeypatch):
    read = []
    real = obsidian._read_markdown
    monkeypatch.setattr(obsidian, "_read_markdown", lambda scope, path: read.append(path) or real(scope, path))

    obsidian.list_notes(course, folders=[".", "Course", "Course/Week1"])

    assert len(read) == len(set(read)) == 5


@pytest.mark.skipif(sys.platform == "win32", reason="symlinks need privileges on Windows")
def test_symlinked_notes_and_folders_are_skipped(tmp_path):
    vault = _notes_vault(tmp_path, {"Course/real.md": "real", "elsewhere/secret.md": "secret"})
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "leak.md").write_text("leak", encoding="utf-8")
    (vault / "Course" / "alias.md").symlink_to(vault / "Course" / "real.md")
    (vault / "Course" / "linked-dir").symlink_to(outside, target_is_directory=True)

    paths = [note["path"] for note in obsidian.list_notes(vault, folders=["Course"])]

    assert paths == ["Course/real.md"]


def test_bad_files_are_all_reported_together(tmp_path):
    vault = _notes_vault(tmp_path, {
        "Good.md": "fine",
        "BadUtf8.md": b"\xff\xfe\x00bad",
        "BadYaml.md": "---\ntags: [unclosed\n---\nbody",
        "Unclosed.md": "---\ntags: a\nno closing line\n",
        "ListYaml.md": "---\n- a\n- b\n---\nbody",
    })

    with pytest.raises(obsidian.ObsidianError) as caught:
        obsidian.list_notes(vault, folders=["."])

    bad = {"BadUtf8.md", "BadYaml.md", "Unclosed.md", "ListYaml.md"}
    assert set(caught.value.failed_paths) == bad
    for path in bad:
        assert path in str(caught.value)
    assert "Good.md" not in caught.value.failed_paths
    assert caught.value.next_step.startswith("co obsidian")


@pytest.mark.skipif(sys.platform == "win32" or (hasattr(os, "geteuid") and os.geteuid() == 0),
                    reason="needs POSIX permissions and a non-root user")
def test_an_unreadable_note_is_reported_with_its_path(tmp_path):
    vault = _notes_vault(tmp_path, {"ok.md": "ok", "locked.md": "secret"})
    (vault / "locked.md").chmod(0)
    try:
        with pytest.raises(obsidian.ObsidianError) as caught:
            obsidian.list_notes(vault, folders=["."])
        assert caught.value.failed_paths == ["locked.md"]
    finally:
        (vault / "locked.md").chmod(0o600)


def test_listing_changes_nothing_in_the_vault(course):
    before = _disk(course)

    obsidian.list_notes(course, folders=["."])
    obsidian.read_note(course, "Logic", folders=["Course"])

    assert _disk(course) == before


# -- tags ------------------------------------------------------------------

def _tags(tmp_path, text):
    vault = _notes_vault(tmp_path, {"t.md": text})
    return obsidian.list_notes(vault, folders=["."])[0]["tags"]


@pytest.mark.parametrize("frontmatter,expected", [
    ("tags: [one, '#two']", ["one", "two"]),
    ("tags: one two", ["one", "two"]),
    ("tags: one, two", ["one", "two"]),
    ("tag: solo", ["solo"]),
    ("tags:\n  - nested/child", ["nested/child"]),
], ids=["list", "space-string", "comma-string", "tag-key", "nested"])
def test_frontmatter_tags_in_every_shape(frontmatter, expected, tmp_path):
    assert _tags(tmp_path, f"---\n{frontmatter}\n---\nbody\n") == expected


def test_body_tags_are_found_and_nested_tags_kept_whole(tmp_path):
    assert _tags(tmp_path, "Studying #exam and #COMP4418/logic today, #中文 too.\n") == \
        ["exam", "COMP4418/logic", "中文"]


@pytest.mark.parametrize("text", [
    "```\n#incode\n```\n",
    "~~~python\n#incode\n~~~\n",
    "Inline `#incode` only\n",
    "    #indented code\n",
    "# Heading only\n",
    "## Second heading\n",
    "See https://example.com/page#anchor\n",
    "Issue #123 is a number\n",
    "mid#word is not a tag\n",
    "[[Note#Heading]] is a link anchor\n",
], ids=["fence", "tilde-fence", "inline-code", "indented-code", "h1", "h2", "url-fragment",
        "number", "mid-word", "wikilink-anchor"])
def test_text_that_is_not_a_tag(text, tmp_path):
    assert _tags(tmp_path, text) == []


def test_tags_are_deduplicated_keeping_the_first_spelling(tmp_path):
    assert _tags(tmp_path, "---\ntags: [Exam]\n---\n#exam #EXAM #Exam\n") == ["Exam"]


# -- links -----------------------------------------------------------------

@pytest.fixture
def linked(tmp_path):
    return _notes_vault(tmp_path, {
        "Course/Source.md": (
            "[[Target]] [[Target|Shown]] [[Target#Heading]] [[Target#^block1]] ![[diagram.png]]\n"
            "[md link](Target.md) [up](../Root.md) [web](https://example.com) [[Missing]]\n"
            "[[Dup]] [[Course/Sub/Deep]] [[Outside]] [[Local]]\n"
            "```\n[[InCode]]\n```\n`[[InlineCode]]`\n"
        ),
        "Course/Target.md": "target",
        "Course/Local.md": "same folder wins",
        "Course/Sub/Deep.md": "deep",
        "Course/diagram.png": b"\x89PNG not read",
        "Elsewhere/Local.md": "same name, other folder",
        "A/Dup.md": "dup one",
        "B/Dup.md": "dup two",
        "Other/Outside.md": "outside",
        "Root.md": "root",
    })


@pytest.fixture
def source(linked):
    return _by_path(obsidian.list_notes(linked, folders=["Course"]))["Course/Source.md"]


def test_links_keep_source_order_and_skip_code(source):
    targets = [link["target"] for link in source["links"]]

    assert targets[:5] == ["Target", "Target", "Target", "Target", "diagram.png"]
    assert "InCode" not in targets and "InlineCode" not in targets


def test_alias_anchor_and_embed_are_kept(source):
    links = source["links"]

    assert links[0] == {**links[0], "alias": None, "anchor": None, "embedded": False}
    assert links[1]["alias"] == "Shown"
    assert links[2]["anchor"] == "Heading"
    assert links[3]["anchor"] == "^block1"
    assert links[4]["embedded"] is True and links[4]["raw"] == "![[diagram.png]]"
    assert links[1]["raw"] == "[[Target|Shown]]"


def test_resolved_link_points_at_the_in_scope_note(source):
    link = _link(source, "Target")

    assert (link["resolution"], link["resolved_path"], link["target_kind"]) == \
        ("resolved", "Course/Target.md", "note")


def test_markdown_links_resolve_relative_to_the_source(source):
    md = next(link for link in source["links"] if link["raw"] == "[md link](Target.md)")
    up = next(link for link in source["links"] if link["raw"] == "[up](../Root.md)")

    assert (md["resolution"], md["resolved_path"]) == ("resolved", "Course/Target.md")
    assert md["alias"] == "md link"
    assert (up["resolution"], up["resolved_path"]) == ("out_of_scope", "Root.md")


def test_attachment_links_are_attachments_and_not_read(source):
    link = _link(source, "diagram.png")

    assert link["target_kind"] == "attachment"
    assert (link["resolution"], link["resolved_path"]) == ("resolved", "Course/diagram.png")


def test_pdf_page_link_with_alias_is_an_attachment(tmp_path):
    vault = _notes_vault(tmp_path, {"a.md": "[[slides.pdf#page=3|Slides]]", "slides.pdf": b"%PDF not read"})

    link = obsidian.list_notes(vault, folders=["."])[0]["links"][0]

    assert (link["target"], link["anchor"], link["alias"]) == ("slides.pdf", "page=3", "Slides")
    assert (link["target_kind"], link["resolution"], link["resolved_path"]) == ("attachment", "resolved", "slides.pdf")


def test_external_links_are_external(source):
    assert _link(source, "https://example.com")["resolution"] == "external"


@pytest.mark.parametrize("target,resolution,resolved", [
    ("Missing", "unresolved", None),
    ("Dup", "ambiguous", None),
    ("Course/Sub/Deep", "resolved", "Course/Sub/Deep.md"),
    ("Outside", "out_of_scope", "Other/Outside.md"),
    ("Local", "resolved", "Course/Local.md"),
], ids=["unresolved", "ambiguous", "root-path", "out-of-scope", "same-folder-wins"])
def test_link_resolution_rules(target, resolution, resolved, source):
    link = _link(source, target)

    assert (link["resolution"], link["resolved_path"]) == (resolution, resolved)


def test_a_unique_name_anywhere_in_the_vault_resolves(tmp_path):
    vault = _notes_vault(tmp_path, {"A/src.md": "[[Far]]", "Z/deep/Far.md": "far"})

    link = _link(_by_path(obsidian.list_notes(vault, folders=["."]))["A/src.md"], "Far")

    assert (link["resolution"], link["resolved_path"]) == ("resolved", "Z/deep/Far.md")


def test_links_into_system_folders_do_not_resolve(tmp_path):
    vault = _notes_vault(tmp_path, {"a.md": "[[secret]]", ".obsidian/secret.md": "x", ".trash/secret.md": "y"})

    assert obsidian.list_notes(vault, folders=["."])[0]["links"][0]["resolution"] == "unresolved"


# -- backlinks -------------------------------------------------------------

def test_backlinks_count_in_scope_note_links_with_their_index(linked):
    notes = _by_path(obsidian.list_notes(linked, folders=["Course"]))
    source = notes["Course/Source.md"]

    backlinks = notes["Course/Target.md"]["backlinks"]

    assert {b["source_path"] for b in backlinks} == {"Course/Source.md"}
    for backlink in backlinks:
        assert source["links"][backlink["link_index"]]["resolved_path"] == "Course/Target.md"
    assert len(backlinks) == 5           # four wiki links and one Markdown link
    assert notes["Course/Sub/Deep.md"]["backlinks"] == [
        {"source_path": "Course/Source.md", "link_index": next(
            i for i, link in enumerate(source["links"]) if link["target"] == "Course/Sub/Deep")}]


def test_links_from_outside_the_scope_are_not_backlinks(tmp_path):
    vault = _notes_vault(tmp_path, {"In/target.md": "t", "Out/source.md": "[[target]]"})

    assert obsidian.list_notes(vault, folders=["In"])[0]["backlinks"] == []


# -- read_note() -----------------------------------------------------------

def test_read_by_relative_path(course):
    note = obsidian.read_note(course, "Course/Week1/Logic.md", folders=["Course"])

    assert note["path"] == "Course/Week1/Logic.md"
    assert note["content"] == (course / "Course/Week1/Logic.md").read_text(encoding="utf-8")


def test_read_by_title_matches_the_listed_record(course):
    listed = _by_path(obsidian.list_notes(course, folders=["Course"]))["Course/Week1/Sets.md"]

    assert obsidian.read_note(course, "Sets", folders=["Course"]) == listed


def test_read_carries_backlinks_from_the_same_scope(course):
    note = obsidian.read_note(course, "Sets", folders=["Course"])

    assert [b["source_path"] for b in note["backlinks"]] == ["Course/Week1/Logic.md"]


def test_read_by_a_duplicated_title_is_refused_with_the_paths(tmp_path):
    vault = _notes_vault(tmp_path, {"A/Same.md": "a", "B/Same.md": "b"})

    with pytest.raises(obsidian.ObsidianError) as caught:
        obsidian.read_note(vault, "Same", folders=["."])

    assert "A/Same.md" in str(caught.value) and "B/Same.md" in str(caught.value)


@pytest.mark.parametrize("ref", ["Nope", "Course/Week1/Nope.md"])
def test_read_of_a_missing_note_is_an_error(ref, course):
    with pytest.raises(obsidian.ObsidianError):
        obsidian.read_note(course, ref, folders=["Course"])


@pytest.mark.parametrize("ref", ["Other/Outside.md", "Outside", "Root.md"],
                         ids=["path-outside", "title-outside", "root-outside"])
def test_read_never_reaches_outside_the_folders(ref, course):
    with pytest.raises((ValueError, obsidian.ObsidianError)):
        obsidian.read_note(course, ref, folders=["Course"])


@pytest.mark.parametrize("ref", ["", "   ", "../escape.md", "Course/../Root.md", "/etc/passwd.md",
                                 "Course/notes.txt", ".obsidian/hidden.md", "Course\\Week1\\Logic.md"],
                         ids=["empty", "blank", "dotdot", "inner-dotdot", "absolute", "not-markdown",
                              "system-folder", "backslashes"])
def test_read_refuses_unsafe_or_wrong_references(ref, course):
    with pytest.raises(ValueError):
        obsidian.read_note(course, ref, folders=["."])


def test_read_of_an_unsafe_path_loads_no_note(course, monkeypatch):
    monkeypatch.setattr(obsidian, "_read_markdown", lambda *a: pytest.fail("read a note"))

    with pytest.raises(ValueError):
        obsidian.read_note(course, "../escape.md", folders=["Course"])


# =========================================================================
# F13DBREAD-7: search_notes()
# =========================================================================

HIT_FIELDS = {"note_key", "path", "title", "modified_at", "matched_fields", "excerpt"}


@pytest.fixture
def library(tmp_path):
    return _notes_vault(tmp_path, {
        "Logic Lecture.md": "Opening words.\n",
        "a/propositions.md": "---\nstatus: draft\ncourse: COMP4418\n---\nThe logic lecture covers proofs.\n",
        "b/reversed.md": "A lecture about something, then logic later.\n",
        "c/tagged.md": "---\ntags: [COMP4418/logic]\n---\nNothing else here.\n",
        "d/linking.md": "See [[Logic Lecture|the talk]] for details.\n",
        "e/chinese.md": "今天复习机器学习的笔记。\n",
        "f/long.md": ("x" * 300) + " needle " + ("y" * 300) + "\n",
        "Other/logic.md": "logic outside the folders\n",
    })


def _search(vault, query, folders=(".",)):
    return obsidian.search_notes(vault, query, folders=list(folders))


def _paths(hits):
    return [hit["path"] for hit in hits]


def test_hit_has_exactly_the_contract_fields(library):
    hits = _search(library, "logic")

    assert hits
    for hit in hits:
        assert set(hit) == HIT_FIELDS
        assert hit["note_key"] == hit["path"]
    assert json.loads(json.dumps(hits)) == hits


def test_search_is_case_insensitive(library):
    assert _paths(_search(library, "LOGIC")) == _paths(_search(library, "logic"))


def test_all_terms_must_match_but_not_in_the_same_field(library):
    hits = {hit["path"]: hit for hit in _search(library, "draft proofs")}

    assert list(hits) == ["a/propositions.md"]
    assert {"frontmatter", "body"} <= set(hits["a/propositions.md"]["matched_fields"])


def test_a_note_matching_only_some_terms_is_not_a_hit(library):
    assert _search(library, "logic zzzz-not-there") == []
    assert _paths(_search(library, "opening logic")) == ["Logic Lecture.md"]


def test_quoted_phrase_must_appear_together(library):
    phrase = _paths(_search(library, '"logic lecture"'))
    words = _paths(_search(library, "logic lecture"))

    assert "a/propositions.md" in phrase
    assert "b/reversed.md" not in phrase
    assert "b/reversed.md" in words


@pytest.mark.parametrize("query,path,field", [
    ("opening", "Logic Lecture.md", "body"),
    ("status", "a/propositions.md", "frontmatter"),
    ("COMP4418", "a/propositions.md", "frontmatter"),
    ("#COMP4418", "c/tagged.md", "tags"),
    ("comp4418/logic", "c/tagged.md", "tags"),
    ("talk", "d/linking.md", "links"),
], ids=["body", "property-key", "property-value", "nested-tag-prefix", "full-tag", "link-alias"])
def test_each_field_can_match(query, path, field, library):
    hit = next(hit for hit in _search(library, query) if hit["path"] == path)

    assert field in hit["matched_fields"]


def test_link_targets_match(library):
    hit = next(hit for hit in _search(library, "lecture") if hit["path"] == "d/linking.md")

    assert "links" in hit["matched_fields"]


def test_chinese_matches_as_a_substring(library):
    assert _paths(_search(library, "学习")) == ["e/chinese.md"]


def test_tag_prefix_does_not_match_inside_a_tag_segment(tmp_path):
    vault = _notes_vault(tmp_path, {"t.md": "---\ntags: [COMP4418/logic]\n---\nbody\n"})

    assert _search(vault, "#COMP44") == []


def test_title_matches_come_first_then_path_order(library):
    hits = _search(library, "logic")

    assert hits[0]["path"] == "Logic Lecture.md"
    assert "title" in hits[0]["matched_fields"]
    rest = [hit["path"] for hit in hits if "title" not in hit["matched_fields"]]
    assert rest == sorted(rest)


def test_a_title_hit_outranks_an_earlier_path(tmp_path):
    vault = _notes_vault(tmp_path, {"a/body.md": "mentions zebra", "z/Zebra.md": "nothing else"})

    assert _paths(_search(vault, "zebra")) == ["z/Zebra.md", "a/body.md"]


def test_one_hit_per_note_even_when_many_fields_match(library):
    paths = _paths(_search(library, "logic"))

    assert len(paths) == len(set(paths))


def test_search_stays_inside_the_folders(library):
    assert "Other/logic.md" not in _paths(_search(library, "logic", folders=["a", "b", "c", "d"]))
    assert "Other/logic.md" in _paths(_search(library, "logic"))


def test_excerpt_surrounds_the_first_body_hit(library):
    hit = _search(library, "needle")[0]

    assert "needle" in hit["excerpt"]
    assert len(hit["excerpt"]) <= 80 + len("needle") + 80 + 2
    assert hit["excerpt"].startswith("x") and hit["excerpt"].rstrip("\n").endswith("y")


def test_excerpt_falls_back_to_the_matching_field(library):
    hit = next(hit for hit in _search(library, "status") if hit["path"] == "a/propositions.md")

    assert "status" in hit["excerpt"]


def test_no_match_is_an_empty_list(library):
    assert _search(library, "zzzz-not-there") == []


@pytest.mark.parametrize("query", ["", "   ", '""', '"unclosed'], ids=["empty", "blank", "empty-quotes", "unclosed-quote"])
def test_bad_queries_are_refused_before_reading(query, library, monkeypatch):
    monkeypatch.setattr(obsidian, "_read_markdown", lambda *a: pytest.fail("read a note"))

    with pytest.raises(ValueError):
        _search(library, query)


def test_search_changes_nothing_in_the_vault(library):
    before = _disk(library)

    _search(library, "logic lecture")

    assert _disk(library) == before
