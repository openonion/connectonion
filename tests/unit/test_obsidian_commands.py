"""`co obsidian` CLI: `vaults` (F13DBREAD-2), `notes` and `read` (F13DBREAD-3), `search` (F13DBREAD-7).

The command is invoked through the root app, as a user would. Registries and vaults are
synthetic, under tmp_path; discovery is pointed at them through obsidian._registry_path.
"""

import json
import os
import re
import shlex

import pytest
from typer.testing import CliRunner

from connectonion.useful_tools import obsidian
from tests.unit.test_obsidian import (  # noqa: F401
    _disk, _entries, _notes_vault, _vault, isolated_home, no_note_reads, registry)

VAULTS = ["obsidian", "vaults"]


@pytest.fixture
def cli(isolated_home):
    from connectonion.cli.main import app
    runner = CliRunner()
    return lambda args: runner.invoke(app, args)


def _next_lines(text):
    return [line for line in text.splitlines() if line.startswith("Next: ")]


def _assert_one_next(result, stream):
    """Exactly one Next line, on the stream the mode uses, naming a co command."""
    other = result.stderr if stream == "stdout" else result.stdout
    tips = _next_lines(getattr(result, stream))
    assert len(tips) == 1, result.output
    assert tips[0].startswith("Next: co ")
    assert _next_lines(other) == []
    return tips[0]


def _assert_safe_failure(result, code=1):
    assert result.exit_code == code, result.output
    assert result.stdout.strip() == ""
    assert "✗" in result.stderr
    _assert_one_next(result, "stderr")
    assert "Traceback (most recent call last)" not in result.output


def _vault_lines(result, names):
    """The line that shows each vault, by its name."""
    lines = result.stdout.splitlines()
    return {name: next(line for line in lines if name in line) for name in names}


# -- help and arguments ----------------------------------------------------

def test_obsidian_group_shows_help(cli, registry):
    result = cli(["obsidian"])

    assert result.exit_code in (0, 2), result.output
    assert "Usage:" in result.output
    assert "vaults" in result.output


@pytest.mark.parametrize("args", [["obsidian", "--help"], [*VAULTS, "--help"]])
def test_help_needs_no_registry(args, cli, monkeypatch):
    monkeypatch.setattr(obsidian, "_registry_path",
                        lambda: pytest.fail("help must not look for the registry"))
    result = cli(args)

    assert result.exit_code == 0, result.output
    assert "Usage:" in result.stdout
    assert "vaults" in result.stdout


@pytest.mark.parametrize("args", [["--unknown-option"], ["unexpected-argument"], ["--vault", "x"]])
def test_vaults_rejects_unknown_arguments(args, cli, registry):
    result = cli([*VAULTS, *args])

    assert result.exit_code == 2, result.output


# -- human output ----------------------------------------------------------

def test_vaults_lists_name_path_availability_and_open(cli, registry, tmp_path):
    course, personal = _vault(tmp_path, "Course"), _vault(tmp_path, "Personal")
    gone = tmp_path / "vaults" / "Gone"
    registry(_entries(personal, gone, course, open_index=2))

    result = cli(VAULTS)

    assert result.exit_code == 0, result.output
    assert "3" in result.stdout.splitlines()[0]
    lines = _vault_lines(result, ["Course", "Personal", "Gone"])
    assert str(course.resolve()) in lines["Course"]
    assert str(personal.resolve()) in lines["Personal"]
    assert "unavailable" in lines["Gone"]
    assert "unavailable" not in lines["Course"]
    assert "available" in lines["Course"]
    assert "not open" not in lines["Course"] and "open" in lines["Course"]
    assert "not open" in lines["Personal"]
    _assert_one_next(result, "stdout")


def test_vaults_are_shown_in_name_order(cli, registry, tmp_path):
    registry(_entries(*(_vault(tmp_path, n) for n in ("Zeta", "Alpha", "Mid"))))

    result = cli(VAULTS)

    positions = [result.stdout.index(name) for name in ("Alpha", "Mid", "Zeta")]
    assert positions == sorted(positions)


def test_vaults_have_no_row_numbers(cli, registry, tmp_path):
    """Sprint 1 gives vaults no numbers: adding or renaming a vault would shift them."""
    registry(_entries(_vault(tmp_path, "Alpha"), _vault(tmp_path, "Beta")))

    result = cli(VAULTS)

    for line in _vault_lines(result, ["Alpha", "Beta"]).values():
        assert not line.lstrip().split(" ")[0].rstrip(".").isdigit()
    assert "Listing:" not in result.stdout


def test_names_with_rich_markup_are_shown_literally(cli, registry, tmp_path):
    registry(_entries(_vault(tmp_path, "[bold]Vault[/bold]")))

    result = cli(VAULTS)

    assert result.exit_code == 0, result.output
    assert "[bold]Vault[/bold]" in result.stdout


def test_no_registry_is_an_empty_success_that_offers_a_path(cli, registry):
    result = cli(VAULTS)

    assert result.exit_code == 0, result.output
    assert "0" in result.stdout
    tip = _assert_one_next(result, "stdout")
    assert "--vault" in tip


def test_empty_vaults_object_is_an_empty_success(cli, registry):
    registry({"vaults": {}})

    result = cli(VAULTS)

    assert result.exit_code == 0, result.output
    assert "--vault" in _assert_one_next(result, "stdout")


# -- --json ----------------------------------------------------------------

def test_json_prints_the_discovered_records_only(cli, registry, tmp_path):
    vault = _vault(tmp_path, "Course")
    registry(_entries(vault, tmp_path / "vaults" / "Gone", open_index=0))

    result = cli([*VAULTS, "--json"])

    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)
    assert data == obsidian.discover_vaults()
    assert data[0] == {"name": "Course", "path": str(vault.resolve()), "available": True, "open": True}
    assert data[1]["available"] is False
    _assert_one_next(result, "stderr")


def test_json_with_no_vaults_is_an_empty_list(cli, registry):
    result = cli([*VAULTS, "--json"])

    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout) == []
    _assert_one_next(result, "stderr")


# -- failures --------------------------------------------------------------

@pytest.mark.parametrize("as_json", [False, True], ids=["human", "json"])
@pytest.mark.parametrize("raw", [b"{broken", b'{"vaults": {"a": {"path": "relative"}}}', b"\xff\xfe"],
                         ids=["bad-json", "bad-entry", "not-utf8"])
def test_broken_registry_exits_1_with_nothing_on_stdout(raw, as_json, cli, registry):
    registry(raw=raw)

    result = cli([*VAULTS, *(["--json"] if as_json else [])])

    _assert_safe_failure(result, 1)


def test_unsupported_platform_exits_1(cli, monkeypatch):
    def unsupported():
        raise obsidian.ObsidianError("Obsidian vault discovery supports macOS, Linux and Windows.",
                                     "co obsidian vaults --help")
    monkeypatch.setattr(obsidian, "_registry_path", unsupported)

    _assert_safe_failure(cli(VAULTS), 1)


# -- read-only -------------------------------------------------------------

def test_vaults_reads_no_note_and_writes_nothing(cli, registry, tmp_path, isolated_home, no_note_reads):
    vault = _vault(tmp_path, "Course", notes=("a.md", "Week1/b.md"))
    path = registry(_entries(vault))
    def snapshot():
        # The test's own directory walk is not counted as a read by the command.
        with no_note_reads.paused():
            watched = [tmp_path / "vaults", path.parent]
            return sorted((str(p), p.stat().st_mtime_ns) for root in watched for p in root.rglob("*"))

    before = snapshot()
    for args in (VAULTS, [*VAULTS, "--json"]):
        assert cli(args).exit_code == 0

    assert snapshot() == before
    assert not (isolated_home / ".co" / "obsidian-listings").exists()
    assert path.exists()


def test_vaults_command_is_registered_for_next_tips():
    from connectonion.cli.commands import command_tips

    assert "co obsidian vaults" in command_tips.NEXT


# =========================================================================
# F13DBREAD-3 / -7: notes, read and search over --vault and --folder
# =========================================================================

ROW_LINE = re.compile(r"^\s*(\d+)\.?\s+(.*)$")


@pytest.fixture
def vault(tmp_path):
    """Oldest first: Old.md, then Mid.md, then New.md; one CRLF note and one note outside the folder."""
    return _notes_vault(tmp_path, {
        "Course/Old.md": "old note about logic\n",
        "Course/Week1/Mid.md": "---\ntags: [exam]\n---\nmiddle note, see [[Old]]\n",
        "Course/New.md": "newest note\r\nwith CRLF\r\n",
        "Other/Outside.md": "logic outside the folder\n",
    })


def _scope(vault, *folders):
    return ["--vault", str(vault), *[arg for folder in (folders or ("Course",)) for arg in ("--folder", folder)]]


def _rows(stdout):
    """(number, rest of line) for each numbered row a list printed."""
    lines = stdout.splitlines()[1:]          # the first line is the count ("3 Obsidian notes")
    return [(int(m[1]), m[2]) for m in map(ROW_LINE.match, lines) if m]


def _next(result, stream="stdout"):
    tip = _assert_one_next(result, stream)
    return shlex.split(tip.removeprefix("Next: "))


def _listing_token(stdout):
    found = re.search(r"Listing: (\S+)", stdout)
    assert found, stdout
    return found[1]


def _last_notes(config):
    return config / "obsidian-listings" / "last-notes"


@pytest.fixture
def config(tmp_path):
    return tmp_path / "config"


# -- notes -----------------------------------------------------------------

def test_notes_lists_newest_first_with_title_and_path(cli, vault):
    result = cli(["obsidian", "notes", *_scope(vault)])

    assert result.exit_code == 0, result.output
    rows = _rows(result.stdout)
    assert [number for number, _ in rows] == [1, 2, 3]
    for (_, line), (title, path) in zip(rows, [("New", "Course/New.md"), ("Mid", "Course/Week1/Mid.md"),
                                                 ("Old", "Course/Old.md")]):
        assert title in line and path in line
    assert "Outside" not in result.stdout


def test_notes_does_not_print_note_bodies(cli, vault):
    result = cli(["obsidian", "notes", *_scope(vault)])

    assert "old note about logic" not in result.stdout
    assert "middle note" not in result.stdout


def test_notes_last_limits_the_rows(cli, vault):
    result = cli(["obsidian", "notes", *_scope(vault), "-n", "2"])

    assert result.exit_code == 0, result.output
    assert [number for number, _ in _rows(result.stdout)] == [1, 2]
    assert "Course/Old.md" not in result.stdout


@pytest.mark.parametrize("last", ["0", "251"])
def test_notes_last_out_of_range_is_a_usage_error(last, cli, vault):
    assert cli(["obsidian", "notes", *_scope(vault), "-n", last]).exit_code == 2


def test_notes_next_reads_row_one_in_the_same_scope_and_listing(cli, vault):
    result = cli(["obsidian", "notes", *_scope(vault)])

    token = _listing_token(result.stdout)
    args = _next(result)
    assert args[:4] == ["co", "obsidian", "read", "1"]
    assert args[args.index("--vault") + 1] == str(vault.resolve())
    assert args[args.index("--folder") + 1] == "Course"
    assert args[args.index("--listing") + 1] == token


def test_notes_ids_show_paths_instead_of_row_numbers(cli, vault):
    result = cli(["obsidian", "notes", *_scope(vault), "--ids"])

    assert result.exit_code == 0, result.output
    assert _rows(result.stdout) == []
    assert "Course/New.md" in result.stdout


def test_notes_json_is_the_full_records_newest_first_and_saves_no_rows(cli, vault, config):
    from connectonion.useful_tools import obsidian as api
    result = cli(["obsidian", "notes", *_scope(vault), "--json"])

    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)
    assert [note["path"] for note in data] == ["Course/New.md", "Course/Week1/Mid.md", "Course/Old.md"]
    expected = {note["path"]: note for note in api.list_notes(vault, folders=["Course"])}
    assert data == [expected[note["path"]] for note in data]
    assert not _last_notes(config).exists()
    _assert_one_next(result, "stderr")


def test_notes_without_folder_is_a_usage_error(cli, vault):
    result = cli(["obsidian", "notes", "--vault", str(vault)])

    assert result.exit_code == 2, result.output


@pytest.mark.parametrize("folder", ["..", "/abs", ".obsidian"])
def test_notes_with_an_unsafe_folder_is_a_usage_error(folder, cli, vault):
    _assert_safe_failure(cli(["obsidian", "notes", *_scope(vault, folder)]), 2)


def test_notes_with_a_missing_folder_exits_1(cli, vault):
    _assert_safe_failure(cli(["obsidian", "notes", *_scope(vault, "Nope")]), 1)


def test_notes_in_an_empty_folder_succeed_with_no_rows(cli, vault):
    (vault / "Empty").mkdir()
    result = cli(["obsidian", "notes", *_scope(vault, "Empty")])

    assert result.exit_code == 0, result.output
    assert _rows(result.stdout) == []
    _assert_one_next(result, "stdout")


def test_notes_with_a_bad_file_exits_1_naming_it(cli, vault):
    (vault / "Course" / "Broken.md").write_bytes(b"\xff\xfe bad")
    result = cli(["obsidian", "notes", *_scope(vault)])

    _assert_safe_failure(result, 1)
    assert "Course/Broken.md" in result.stderr


# -- choosing the vault ----------------------------------------------------

def test_the_only_available_vault_is_used_without_vault(cli, vault, registry, tmp_path):
    registry(_entries(vault, tmp_path / "vaults" / "Gone"))
    result = cli(["obsidian", "notes", "--folder", "Course"])

    assert result.exit_code == 0, result.output
    assert len(_rows(result.stdout)) == 3


def test_several_available_vaults_need_vault(cli, vault, registry, tmp_path):
    registry(_entries(vault, _notes_vault(tmp_path, {"a.md": "a"}, name="Second")))
    result = cli(["obsidian", "notes", "--folder", "."])

    _assert_safe_failure(result, 2)
    assert "co obsidian vaults" in result.stderr


def test_no_registered_vault_without_vault_exits_1(cli, registry):
    _assert_safe_failure(cli(["obsidian", "notes", "--folder", "."]), 1)


def test_vault_can_be_named_as_registered(cli, vault, registry):
    registry(_entries(vault))
    result = cli(["obsidian", "notes", "--vault", "Notes", "--folder", "Course"])

    assert result.exit_code == 0, result.output
    assert len(_rows(result.stdout)) == 3


def test_vault_is_not_a_row_number(cli, vault, registry):
    registry(_entries(vault))

    _assert_safe_failure(cli(["obsidian", "notes", "--vault", "1", "--folder", "."]), 2)


# -- read ------------------------------------------------------------------

def test_read_row_prints_the_original_markdown_only(cli, vault):
    cli(["obsidian", "notes", *_scope(vault)])
    result = cli(["obsidian", "read", "1", *_scope(vault)])

    assert result.exit_code == 0, result.output
    assert result.stdout_bytes == (vault / "Course/New.md").read_bytes()      # CRLF kept
    assert "Next:" not in result.stdout
    _assert_one_next(result, "stderr")


@pytest.mark.parametrize("ref", ["2", "#2"])
def test_read_row_number_with_or_without_hash(ref, cli, vault):
    cli(["obsidian", "notes", *_scope(vault)])
    result = cli(["obsidian", "read", ref, *_scope(vault)])

    assert result.exit_code == 0, result.output
    assert result.stdout_bytes == (vault / "Course/Week1/Mid.md").read_bytes()


@pytest.mark.parametrize("ref", ["Course/Old.md", "Old"], ids=["path", "title"])
def test_read_by_path_or_title_needs_no_list(ref, cli, vault, config):
    result = cli(["obsidian", "read", ref, *_scope(vault)])

    assert result.exit_code == 0, result.output
    assert result.stdout == "old note about logic\n"
    assert not _last_notes(config).exists()


def test_read_json_is_the_full_record(cli, vault):
    result = cli(["obsidian", "read", "Mid", *_scope(vault), "--json"])

    assert result.exit_code == 0, result.output
    note = json.loads(result.stdout)
    assert note["path"] == "Course/Week1/Mid.md"
    assert note["tags"] == ["exam"]
    assert note["links"][0]["resolved_path"] == "Course/Old.md"
    _assert_one_next(result, "stderr")


def test_read_listing_pins_an_older_list(cli, vault):
    first = cli(["obsidian", "notes", *_scope(vault)])
    token = _listing_token(first.stdout)
    cli(["obsidian", "search", "logic", *_scope(vault)])          # a newer list: row 1 is Old.md now

    result = cli(["obsidian", "read", "1", *_scope(vault), "--listing", token])

    assert result.exit_code == 0, result.output
    assert result.stdout_bytes == (vault / "Course/New.md").read_bytes()


def test_read_row_without_a_recent_list_is_a_usage_error(cli, vault):
    _assert_safe_failure(cli(["obsidian", "read", "1", *_scope(vault)]), 2)


def test_read_row_from_another_scope_is_refused(cli, vault):
    """Rows belong to the vault and folders they were listed from."""
    cli(["obsidian", "notes", *_scope(vault, ".")])

    _assert_safe_failure(cli(["obsidian", "read", "1", *_scope(vault, "Course")]), 2)


def test_read_row_out_of_range_is_refused(cli, vault):
    cli(["obsidian", "notes", *_scope(vault)])

    _assert_safe_failure(cli(["obsidian", "read", "9", *_scope(vault)]), 2)


@pytest.mark.parametrize("ref", ["Other/Outside.md", "../x.md"], ids=["outside-folder", "dotdot"])
def test_read_outside_the_folders_is_refused(ref, cli, vault):
    _assert_safe_failure(cli(["obsidian", "read", ref, *_scope(vault)]), 2)


def test_read_missing_note_exits_1(cli, vault):
    _assert_safe_failure(cli(["obsidian", "read", "Nope", *_scope(vault)]), 1)


# -- search ----------------------------------------------------------------

def test_search_lists_hits_with_fields_and_excerpt(cli, vault):
    result = cli(["obsidian", "search", "logic", *_scope(vault)])

    assert result.exit_code == 0, result.output
    rows = _rows(result.stdout)
    assert len(rows) == 1 and "Course/Old.md" in rows[0][1]
    assert "body" in result.stdout
    assert "old note about logic" in result.stdout
    assert "Outside" not in result.stdout


def test_search_hits_become_the_rows_read_takes(cli, vault):
    search = cli(["obsidian", "search", "note", *_scope(vault)])
    first = _rows(search.stdout)[0][1]

    result = cli(["obsidian", "read", "1", *_scope(vault)])

    path = next(p for p in ("Course/New.md", "Course/Week1/Mid.md", "Course/Old.md") if p in first)
    assert result.stdout_bytes == (vault / path).read_bytes()


def test_search_next_reads_row_one_with_its_listing(cli, vault):
    result = cli(["obsidian", "search", "logic", *_scope(vault)])

    args = _next(result)
    assert args[:4] == ["co", "obsidian", "read", "1"]
    assert args[args.index("--listing") + 1] == _listing_token(result.stdout)


def test_search_json_is_the_hits_and_saves_no_rows(cli, vault, config):
    from connectonion.useful_tools import obsidian as api
    result = cli(["obsidian", "search", "note", *_scope(vault), "--json"])

    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout) == api.search_notes(vault, "note", folders=["Course"])
    assert not _last_notes(config).exists()
    _assert_one_next(result, "stderr")


def test_search_with_no_hits_succeeds(cli, vault):
    result = cli(["obsidian", "search", "zzzz", *_scope(vault)])

    assert result.exit_code == 0, result.output
    assert _rows(result.stdout) == []
    _assert_one_next(result, "stdout")


@pytest.mark.parametrize("query", ["   ", '"unclosed'])
def test_search_bad_query_is_a_usage_error(query, cli, vault):
    _assert_safe_failure(cli(["obsidian", "search", query, *_scope(vault)]), 2)


def test_search_quoted_phrase_from_the_shell(cli, vault):
    phrase = cli(["obsidian", "search", '"about logic"', *_scope(vault)])
    reversed_words = cli(["obsidian", "search", '"logic about"', *_scope(vault)])

    assert "Course/Old.md" in phrase.stdout
    assert _rows(reversed_words.stdout) == []


# -- read-only ---------------------------------------------------------------

def test_notes_read_and_search_never_change_the_vault(cli, vault, config):
    before = _disk(vault)

    for args in (["notes"], ["read", "1"], ["read", "Old", "--json"], ["search", "logic"],
                 ["search", "note", "--json"]):
        assert cli(["obsidian", *args, *_scope(vault)]).exit_code == 0

    assert _disk(vault) == before
    assert _last_notes(config).exists()
    assert not (vault / ".co").exists()


@pytest.mark.parametrize("command", ["notes", "read", "search"])
def test_note_commands_are_registered_for_next_tips(command):
    from connectonion.cli.commands import command_tips

    assert f"co obsidian {command}" in command_tips.NEXT
