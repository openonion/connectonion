"""Obsidian vault discovery and folder scope (F13DBREAD-2): registry location, registry
validation, discover_vaults() records, and _validate_scope() selections.

Only synthetic registries and vaults under tmp_path are used; no test reads a real
Obsidian installation, and discovery is checked to open no note and list no folder.
"""

import builtins
import io
import json
import os
import sys
from contextlib import contextmanager
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
