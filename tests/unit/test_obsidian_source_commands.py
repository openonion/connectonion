"""Source CLI contract: synthetic vaults, live reads, no saved source material."""

import json
import os
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlsplit

import pytest

from connectonion.useful_tools import obsidian as api
from connectonion.useful_tools import obsidian_changes as source
from tests.unit.test_obsidian import _entries, _vault, isolated_home, registry  # noqa: F401
from tests.unit.test_obsidian_commands import cli, _assert_one_next, _assert_safe_failure  # noqa: F401

NOW = datetime(2026, 11, 21, 12, tzinfo=timezone.utc)
START = "2026-11-20T00:00:00+00:00"
DAY = int(datetime(2026, 11, 20, tzinfo=timezone.utc).timestamp())


@pytest.fixture(autouse=True)
def clock(monkeypatch):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW
    monkeypatch.setattr(source, "datetime", Clock)


def _note(vault, key, text="hello", seconds=DAY + 10, extra_ns=0):
    path = vault / key
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="")
    stamp = seconds * 1_000_000_000 + extra_ns
    os.utime(path, ns=(stamp, stamp))
    return path


def _args(command, vault, *words, folders=("Course",)):
    return ["obsidian", command, *words, "--vault", str(vault),
            *(word for folder in folders for word in ("--folder", folder)), "--json"]


def _changes(cli, vault, since=START, folders=("Course",)):
    result = cli(_args("changes", vault, "--since", since, folders=folders))
    assert result.exit_code == 0, result.output
    _assert_one_next(result, "stderr")
    return json.loads(result.stdout)


def _id(cli, vault, key="Course/Note.md"):
    return next(item["id"] for item in _changes(cli, vault)["items"] if item["path"] == key)


def test_changes_envelope_order_overlap_and_metadata_only(cli, tmp_path, monkeypatch):
    vault = _vault(tmp_path, "Personal", notes=())
    _note(vault, "Course/Z.md", seconds=DAY + 20)
    _note(vault, "Course/A.md", seconds=DAY + 10)
    _note(vault, "Course/nested/B.md", seconds=DAY + 10)
    _note(vault, "Course/old.md", seconds=DAY - 1)
    _note(vault, "Course/future.md", seconds=int(NOW.timestamp()) + 1)
    _note(vault, "Private/Secret.md")
    monkeypatch.setattr(api, "_read_markdown", lambda *a: pytest.fail("changes must not read bodies"))

    batch = _changes(cli, vault, folders=("Course", "Course/nested"))

    assert batch["since"] == START
    assert batch["until"] == NOW.isoformat()
    assert [i["path"] for i in batch["items"]] == ["Course/A.md", "Course/nested/B.md", "Course/Z.md"]
    first = batch["items"][0]
    assert first["title"] == "A" and first["folder"] == "Course"
    assert {"id", "time", "title", "link"} <= first.keys()
    assert "text" not in first
    assert parse_qs(urlsplit(first["link"]).query)["path"] == [str(vault / "Course/A.md")]


def test_cursor_repeat_then_edit_and_live_show(cli, tmp_path):
    vault = _vault(tmp_path, "Personal", notes=())
    path = _note(vault, "Course/Note.md", "first")
    batch = _changes(cli, vault)
    identifier = batch["items"][0]["id"]
    assert _changes(cli, vault, batch["until"])["items"] == []
    _note(vault, "Course/Note.md", "second", seconds=int(NOW.timestamp()))
    repeated = _changes(cli, vault, batch["until"])["items"]
    assert repeated[0]["id"] == identifier
    result = cli(_args("show", vault, identifier))
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["text"] == "second"
    path.unlink()
    result = cli(_args("show", vault, identifier))
    _assert_safe_failure(result)
    assert _changes(cli, vault)["items"] == []


def test_show_metadata_and_author_are_evidence_not_user_identity(cli, tmp_path):
    vault = _vault(tmp_path, "Personal", notes=())
    text = ("---\ntags: [planning]\nauthor: Alex\nproject: Atlas\n---\r\n"
            "# Decision\r\nUse blue. #design [[../Private/Secret]] ![[image.png]]\r\n")
    _note(vault, "Course/Note.md", text)
    # A broken sibling must not stop a live read of the selected note.
    _note(vault, "Course/Broken.md", "---\nbad: [\n---\n")
    _note(vault, "Private/Secret.md", "must not be followed")

    result = cli(_args("show", vault, _id(cli, vault)))

    assert result.exit_code == 0, result.output
    item = json.loads(result.stdout)
    assert item["text"] == text
    assert item["title"] == "Note" and item["author"] == "Alex"
    assert item["properties"]["project"] == "Atlas"
    assert item["tags"] == ["planning", "design"]
    assert [link["target"] for link in item["links"]] == ["../Private/Secret", "image.png"]
    assert all(link["resolved_path"] is None for link in item["links"])
    assert "must not be followed" not in result.stdout
    _assert_one_next(result, "stderr")


@pytest.mark.parametrize("author", [None, ["Alex", "Bob"], 123])
def test_unknown_or_non_text_author_is_null(cli, tmp_path, author):
    vault = _vault(tmp_path, "Personal", notes=())
    _note(vault, "Course/Note.md", f"---\nauthor: {json.dumps(author)}\n---\nBody")
    result = cli(_args("show", vault, _id(cli, vault)))
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["author"] is None
    assert json.loads(result.stdout)["properties"]["author"] == author


@pytest.mark.parametrize("use_path", [False, True], ids=["id", "path"])
def test_show_reads_only_the_requested_file(cli, tmp_path, monkeypatch, use_path):
    vault = _vault(tmp_path, "Personal", notes=())
    selected = _note(vault, "Course/Note.md")
    _note(vault, "Course/Other.md")
    identifier = _id(cli, vault)
    original = api._read_markdown
    reads = []

    def read(scope, path):
        reads.append(path)
        return original(scope, path)

    monkeypatch.setattr(api, "_read_markdown", read)
    monkeypatch.setattr(api, "_build_scope_index", lambda *a: pytest.fail("show must not scan siblings"))
    result = cli(_args("show", vault, "Course/Note.md" if use_path else identifier))
    assert result.exit_code == 0, result.output
    assert reads == [selected]


@pytest.mark.parametrize("key", ["Course/Note.md", "Course/空 格.md", "Course/colon:name.md"])
def test_short_path_returns_the_same_live_record_and_stable_id(cli, tmp_path, key):
    if os.name == "nt" and ":" in key:
        pytest.skip("colon is not a Windows filename")
    vault = _vault(tmp_path, "Personal", notes=())
    _note(vault, key, "Current text")
    identifier = _id(cli, vault, key)
    by_path = cli(_args("show", vault, key))
    by_id = cli(_args("show", vault, identifier))
    assert by_path.exit_code == by_id.exit_code == 0, (by_path.output, by_id.output)
    assert json.loads(by_path.stdout) == json.loads(by_id.stdout)
    assert json.loads(by_path.stdout)["id"] == identifier
    _assert_one_next(by_path, "stderr")


@pytest.mark.parametrize("since", ["bad", "2026-11-20", "2026-11-20T01:00:00", "2999-01-01T00:00:00Z"])
def test_invalid_since_fails_before_source_access(cli, monkeypatch, since):
    monkeypatch.setattr(api, "discover_vaults", lambda: pytest.fail("must validate since first"))
    result = cli(["obsidian", "changes", "--since", since, "--folder", "Course", "--json"])
    _assert_safe_failure(result, 2)


def test_since_accepts_offsets_and_equal_boundary(cli, tmp_path):
    vault = _vault(tmp_path, "Personal", notes=())
    _note(vault, "Course/Boundary.md", seconds=DAY)
    batch = _changes(cli, vault, "2026-11-20T11:00:00+11:00")
    assert len(batch["items"]) == 1
    assert datetime.fromisoformat(batch["since"]).timestamp() == DAY


def test_nanosecond_boundaries_do_not_round_into_previous_window(cli, tmp_path):
    vault = _vault(tmp_path, "Personal", notes=())
    # A file 1 ns after until belongs to the next call, not the first call.
    path = _note(vault, "Course/Note.md", seconds=int(NOW.timestamp()), extra_ns=1)
    if path.stat().st_mtime_ns != int(NOW.timestamp()) * 1_000_000_000 + 1:
        pytest.skip("filesystem does not preserve nanosecond mtimes")
    assert _changes(cli, vault)["items"] == []
    start, until = source.read_window(START)
    later = until.replace(second=1)
    item = source.changes(api._validate_scope(vault, ("Course",)), until, later)["items"][0]
    assert item["path"] == "Course/Note.md"


def test_edit_during_scan_waits_for_the_next_window(cli, tmp_path, monkeypatch):
    vault = _vault(tmp_path, "Personal", notes=())
    _note(vault, "Course/Note.md", "old")
    original = source._modified_ns
    edited = False

    def modify(scope, key):
        nonlocal edited
        if not edited:
            _note(vault, key, "new", seconds=int(NOW.timestamp()) + 1)
            edited = True
        return original(scope, key)

    monkeypatch.setattr(source, "_modified_ns", modify)
    first = _changes(cli, vault)
    assert first["items"] == []

    class Later(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW.replace(second=2)

    monkeypatch.setattr(source, "datetime", Later)
    second = _changes(cli, vault, first["until"])
    assert [i["path"] for i in second["items"]] == ["Course/Note.md"]


@pytest.mark.parametrize("command,words", [("changes", ["--since", START]), ("show", ["not-an-id"])])
def test_scope_is_required_even_with_one_registered_vault(cli, registry, tmp_path, command, words):
    vault = _vault(tmp_path, "Personal")
    registry(_entries(vault))
    result = cli(["obsidian", command, *words, "--json"])
    assert result.exit_code == 2
    assert "--folder" in result.stderr


def test_identity_binds_vault_and_path_but_not_file_content(cli, tmp_path):
    vault = _vault(tmp_path, "Personal", notes=())
    other = _vault(tmp_path, "Other", notes=())
    _note(vault, "Course/Note.md")
    _note(other, "Course/Note.md")
    identifier = _id(cli, vault)
    assert _id(cli, other) != identifier
    _assert_safe_failure(cli(_args("show", other, identifier)), 2)
    (vault / "Course/Note.md").rename(vault / "Course/Renamed.md")
    assert _id(cli, vault, "Course/Renamed.md") != identifier
    _assert_safe_failure(cli(_args("show", vault, identifier)))


@pytest.mark.parametrize("key", ["Course/空 格 #100%.md", "Course/colon:name.md"])
def test_ids_round_trip_special_names(cli, tmp_path, key):
    if os.name == "nt" and ":" in key:
        pytest.skip("colon is not a Windows filename")
    vault = _vault(tmp_path, "Personal", notes=())
    _note(vault, key)
    result = cli(_args("show", vault, _id(cli, vault, key)))
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["path"] == key


@pytest.mark.parametrize("path", ["../escape.md", "/tmp/escape.md", "Course/../Private/Secret.md",
                                  "Private/Secret.md", "Course/.obsidian/Hidden.md", "Course/file.txt"])
@pytest.mark.parametrize("use_path", [False, True], ids=["id", "path"])
def test_reference_cannot_expand_scope(cli, tmp_path, monkeypatch, path, use_path):
    vault = _vault(tmp_path, "Personal", notes=())
    _note(vault, "Course/Note.md")
    _note(vault, "Private/Secret.md")
    scope = api._validate_scope(vault, ("Course",))
    identifier = path if use_path else source._note_id(scope, path)
    monkeypatch.setattr(api, "_read_markdown", lambda *a: pytest.fail("unsafe ID must fail before read"))
    _assert_safe_failure(cli(_args("show", vault, identifier)), 2)


@pytest.mark.parametrize("identifier", ["1", "#1", "obsidian:anything", "a" * 64 + ":%FF"])
def test_row_numbers_and_malformed_references_are_refused(cli, tmp_path, identifier):
    vault = _vault(tmp_path, "Personal", notes=("Course/Note.md",))
    _assert_safe_failure(cli(_args("show", vault, identifier)), 2)


@pytest.mark.parametrize("use_path", [False, True], ids=["id", "path"])
def test_exclusions_and_symlink_swap(cli, tmp_path, use_path):
    vault = _vault(tmp_path, "Personal", notes=())
    target = _note(vault, "Course/Note.md")
    secret = _note(vault, "Private/Secret.md", "PRIVATE")
    identifier = _id(cli, vault)
    for name in (".obsidian", ".trash", ".git"):
        _note(vault, f"Course/{name}/Hidden.md")
    try:
        (vault / "Course/Link.md").symlink_to(secret)
    except OSError:
        pytest.skip("symlinks unavailable")
    assert [i["path"] for i in _changes(cli, vault)["items"]] == ["Course/Note.md"]
    target.unlink()
    target.symlink_to(secret)
    _assert_safe_failure(cli(_args("show", vault, "Course/Note.md" if use_path else identifier)), 2)


@pytest.mark.parametrize("command,use_path", [("changes", False), ("show", False), ("show", True)])
def test_validated_ancestor_cannot_be_redirected(cli, tmp_path, monkeypatch, command, use_path):
    from connectonion.cli.commands import obsidian_commands as commands
    vault = _vault(tmp_path, "Personal", notes=())
    _note(vault, "Course/Note.md", "safe")
    other = _vault(tmp_path, "Other", notes=())
    _note(other, "Course/Note.md", "PRIVATE")
    identifier = _id(cli, vault)
    original = commands._selection

    def redirect(*args):
        scope = original(*args)
        vault.rename(vault.with_name("Moved"))
        vault.symlink_to(other, target_is_directory=True)
        return scope

    monkeypatch.setattr(commands, "_selection", redirect)
    reference = "Course/Note.md" if use_path else identifier
    result = cli(_args(command, vault, *(["--since", START] if command == "changes" else [reference])))
    assert result.exit_code in (1, 2), result.output
    assert result.stdout == "" and "PRIVATE" not in result.output


def test_show_parse_failure_is_not_partial_json(cli, tmp_path):
    vault = _vault(tmp_path, "Personal", notes=())
    _note(vault, "Course/Note.md", "---\nbad: [\n---\n")
    _assert_safe_failure(cli(_args("show", vault, _id(cli, vault))))


def test_metadata_failure_does_not_return_partial_batch(cli, tmp_path, monkeypatch):
    vault = _vault(tmp_path, "Personal", notes=())
    _note(vault, "Course/A.md")
    _note(vault, "Course/B.md")
    original = source._modified_ns

    def denied(scope, key):
        if key.endswith("B.md"):
            raise PermissionError("denied")
        return original(scope, key)

    monkeypatch.setattr(source, "_modified_ns", denied)
    _assert_safe_failure(cli(_args("changes", vault, "--since", START)))


def test_human_output_shows_cursor_and_next_preserves_the_scope(cli, tmp_path):
    import shlex

    vault = _vault(tmp_path, "Personal", notes=())
    _note(vault, "Course/Note.md", "# Text\nBody\n")
    result = cli(_args("changes", vault, "--since", START)[:-1])
    assert result.exit_code == 0, result.output
    assert f"Until: {NOW.isoformat()}" in result.stdout
    tip = _assert_one_next(result, "stdout")
    words = shlex.split(tip.removeprefix("Next: "))
    assert words[:3] == ["co", "obsidian", "show"]
    assert words[3] == "./Course/Note.md"
    assert words[words.index("--vault") + 1] == str(vault)
    assert words[words.index("--folder") + 1] == "Course"
    shown = cli(words[1:])
    assert shown.exit_code == 0, shown.output
    assert shown.stdout == "# Text\nBody\n"
    _assert_one_next(shown, "stderr")


@pytest.mark.parametrize("name", ["-Note.md", "obsidian:Note.md", "a" * 64 + ":Note.md"])
def test_human_next_escapes_option_and_id_like_filenames(cli, tmp_path, name):
    import shlex

    if os.name == "nt" and ":" in name:
        pytest.skip("colon is not a Windows filename")
    vault = _vault(tmp_path, "Personal", notes=())
    _note(vault, name, "Current note\n")
    result = cli(_args("changes", vault, "--since", START, folders=(".",))[:-1])
    assert result.exit_code == 0, result.output
    words = shlex.split(_assert_one_next(result, "stdout").removeprefix("Next: "))
    assert words[3] == "./" + name
    shown = cli([*words[1:], "--json"])
    assert shown.exit_code == 0, shown.output
    record = json.loads(shown.stdout)
    assert record["path"] == name and record["text"] == "Current note\n"
    _assert_one_next(shown, "stderr")


def test_future_mtime_show_has_a_working_next_command(cli, tmp_path):
    import shlex

    vault = _vault(tmp_path, "Personal", notes=())
    _note(vault, "Course/Note.md")
    identifier = _id(cli, vault)
    _note(vault, "Course/Note.md", "future file", seconds=int(NOW.timestamp()) + 100)
    result = cli(_args("show", vault, identifier))
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["text"] == "future file"
    tip = _assert_one_next(result, "stderr")
    next_result = cli(shlex.split(tip.removeprefix("Next: "))[1:])
    assert next_result.exit_code == 0, next_result.output
    assert json.loads(next_result.stdout)[0]["content"] == "future file"


@pytest.mark.parametrize("use_path", [False, True], ids=["id", "path"])
def test_success_and_failure_do_not_save_bodies_cursors_or_rows(cli, tmp_path, isolated_home, use_path):
    vault = _vault(tmp_path, "Personal", notes=())
    note = _note(vault, "Course/Note.md", "unchanged")
    before = note.stat().st_mtime_ns
    identifier = _id(cli, vault)
    result = cli(_args("show", vault, "Course/Note.md" if use_path else identifier))
    assert result.exit_code == 0, result.output
    _assert_safe_failure(cli(_args("show", vault, "bad")), 2)
    assert note.read_text() == "unchanged" and note.stat().st_mtime_ns == before
    assert not list(isolated_home.rglob("*"))
    assert not (tmp_path / "config").exists()


@pytest.mark.parametrize("command", ["changes", "show"])
def test_help_is_reachable_without_registry_or_notes(cli, monkeypatch, command):
    monkeypatch.setattr(api, "discover_vaults", lambda: pytest.fail("help must not read sources"))
    result = cli(["obsidian", command, "--help"])
    assert result.exit_code == 0, result.output
    assert "Read-only" in result.stdout and "--folder" in result.stdout
    assert "Example:" in result.stdout and "Back:" in result.stdout
