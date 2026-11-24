"""User-facing Obsidian CLI tests for discovery and scoped reads.

The command is invoked through the root app, as a user would. Registries and vaults are
synthetic, under tmp_path; discovery is pointed at them through obsidian._registry_path.
"""

import json
import os
import re
import shlex
import sys

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

def test_obsidian_group_lists_every_registered_vault(cli, registry, tmp_path, monkeypatch):
    monkeypatch.setenv("COLUMNS", "200")
    vaults = [_vault(tmp_path, f"Course {index:02d}", notes=()) for index in range(24)]
    gone = tmp_path / "vaults" / "Gone"
    registry(_entries(*vaults, gone, open_index=0))

    result = cli(["obsidian"])

    assert result.exit_code == 0, result.output
    assert "25 registered Obsidian vaults" in result.stdout
    lines = _vault_lines(result, [path.name for path in [*vaults, gone]])
    assert all(str(path.resolve()) in result.stdout for path in [*vaults, gone])
    assert "unavailable" in lines["Gone"]
    assert "not open" not in lines["Course 00"]
    assert "not open" in lines["Course 01"]
    assert "Usage:" not in result.stdout
    _assert_one_next(result, "stdout")


@pytest.mark.parametrize("command", [[], ["vaults"], ["ls"], ["read"], ["search"], ["create"], ["append"]])
def test_help_needs_no_registry(command, cli, monkeypatch):
    monkeypatch.setattr(obsidian, "_registry_path",
                        lambda: pytest.fail("help must not look for the registry"))
    result = cli(["obsidian", *command, "--help"])

    assert result.exit_code == 0, result.output
    assert "Usage:" in result.stdout


@pytest.mark.parametrize("command", ["notes"])
def test_removed_notes_alias_is_not_exposed(command, cli, monkeypatch):
    monkeypatch.setattr(obsidian, "_registry_path",
                        lambda: pytest.fail("an unknown command must not read the registry"))

    result = cli(["obsidian", command])

    assert result.exit_code == 2, result.output
    assert "No such command" in result.stderr


@pytest.mark.parametrize("args", [["--unknown-option"], ["unexpected-argument"], ["--vault", "x"]])
def test_vaults_rejects_unknown_arguments(args, cli, registry):
    result = cli([*VAULTS, *args])

    assert result.exit_code == 2, result.output


# -- human output ----------------------------------------------------------

def test_vaults_lists_name_path_availability_and_open(cli, registry, tmp_path, monkeypatch):
    monkeypatch.setenv("COLUMNS", "200")
    course, personal = _vault(tmp_path, "Course"), _vault(tmp_path, "Personal")
    gone = tmp_path / "vaults" / "Gone"
    registry(_entries(personal, gone, course, open_index=2))

    result = cli(VAULTS)

    assert result.exit_code == 0, result.output
    assert "3" in result.stdout.splitlines()[0]
    lines = _vault_lines(result, ["Course", "Personal", "Gone"])
    assert str(course.resolve()) in result.stdout
    assert str(personal.resolve()) in result.stdout
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


@pytest.mark.parametrize("command", [["obsidian"], VAULTS], ids=["bare", "vaults"])
def test_vault_rows_are_numbered_and_status_columns_align_at_80_columns(command, cli, monkeypatch):
    monkeypatch.setenv("COLUMNS", "80")
    vaults = [
        {"name": "Personal", "path": "/Users/example/Desktop/obsidian/Personal", "available": True, "open": True},
        {"name": "Unavailable-Notes-Archive", "path": "/Users/example/Desktop/Unavailable-Notes-Archive",
         "available": False, "open": False},
    ]
    monkeypatch.setattr(obsidian, "discover_vaults", lambda: vaults)

    result = cli(command)

    assert result.exit_code == 0, result.output
    first, second = _vault_lines(result, [vault["name"] for vault in vaults]).values()
    assert first.split()[0] == "1" and second.split()[0] == "2"
    assert first.index("available") == second.index("unavailable")
    assert first.index("open") == second.index("not open")
    for vault in vaults:
        assert vault["path"] in result.stdout
    assert "Listing:" not in result.stdout


def test_names_with_rich_markup_are_shown_literally(cli, registry, tmp_path):
    registry(_entries(_vault(tmp_path, "[bold]Vault[/bold]")))

    result = cli(VAULTS)

    assert result.exit_code == 0, result.output
    assert "[bold]Vault[/bold]" in result.stdout


@pytest.mark.parametrize("command", [["obsidian"], VAULTS], ids=["bare", "vaults"])
def test_no_registry_is_an_empty_success_that_offers_a_path(command, cli, registry):
    result = cli(command)

    assert result.exit_code == 0, result.output
    assert "0" in result.stdout
    assert _next(result) == ["co", "obsidian", "ls", "--vault", "<vault-path>"]


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


def test_obsidian_group_reports_an_unreadable_registry(cli, registry):
    registry(raw=b"{broken")

    _assert_safe_failure(cli(["obsidian"]), 1)


# -- read-only -------------------------------------------------------------

def test_vaults_only_caches_row_references(cli, registry, tmp_path, config, no_note_reads):
    vault = _vault(tmp_path, "Course", notes=("a.md", "Week1/b.md"))
    path = registry(_entries(vault))
    def snapshot():
        # The test's own directory walk is not counted as a read by the command.
        with no_note_reads.paused():
            watched = [tmp_path / "vaults", path.parent]
            return sorted((str(p), p.stat().st_mtime_ns) for root in watched for p in root.rglob("*"))

    before = snapshot()
    assert cli([*VAULTS, "--json"]).exit_code == 0
    assert not (config / "obsidian-listings").exists()
    for args in (["obsidian"], VAULTS):
        assert cli(args).exit_code == 0

    assert snapshot() == before
    assert path.exists()


def test_vaults_command_is_registered_for_next_tips():
    from connectonion.cli.commands import command_tips

    assert "co obsidian vaults" in command_tips.NEXT


# =========================================================================
# Notes, read and search over --vault and --folder
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


# -- ls -----------------------------------------------------------------

def test_ls_lists_filenames_newest_first(cli, vault):
    result = cli(["obsidian", "ls", *_scope(vault)])

    assert result.exit_code == 0, result.output
    assert _rows(result.stdout) == [(1, "New.md"), (2, "Mid.md"), (3, "Old.md")]
    assert "Outside" not in result.stdout


def test_duplicate_filenames_show_distinguishing_folders_and_keep_their_rows(cli, tmp_path):
    library = _notes_vault(tmp_path, {
        "Course/Week1/Review/Summary.md": "Week one\n",
        "Course/Week2/Review/Summary.md": "Week two\n",
        "Course/Welcome.md": "Welcome\n",
    })
    result = cli(["obsidian", "ls", *_scope(library)])

    assert result.exit_code == 0, result.output
    rows = {label: number for number, label in _rows(result.stdout)}
    assert set(rows) == {"Summary.md  …/Week1/Review/", "Summary.md  …/Week2/Review/", "Welcome.md"}
    listing = _listing_token(result.stdout)
    for label, body in [("Summary.md  …/Week1/Review/", "Week one\n"),
                        ("Summary.md  …/Week2/Review/", "Week two\n")]:
        read = cli(["obsidian", "read", str(rows[label]), "--listing", listing])
        assert read.exit_code == 0, read.output
        assert read.stdout == body


def test_ls_does_not_print_note_bodies(cli, vault):
    result = cli(["obsidian", "ls", *_scope(vault)])

    assert "old note about logic" not in result.stdout
    assert "middle note" not in result.stdout


@pytest.mark.parametrize("flag", ["-n", "--last"])
def test_ls_last_limits_the_rows(cli, vault, flag):
    result = cli(["obsidian", "ls", *_scope(vault), flag, "2"])

    assert result.exit_code == 0, result.output
    assert [number for number, _ in _rows(result.stdout)] == [1, 2]
    assert "Old.md" not in result.stdout


@pytest.mark.parametrize("last", ["0", "251"])
def test_ls_last_out_of_range_is_a_usage_error(last, cli, vault):
    assert cli(["obsidian", "ls", *_scope(vault), "-n", last]).exit_code == 2


def test_ls_next_reads_row_one_in_the_same_scope_and_listing(cli, vault):
    result = cli(["obsidian", "ls", *_scope(vault)])

    args = _next(result)
    assert args == ["co", "obsidian", "read", "1", "--listing", _listing_token(result.stdout)]
    read = cli(args[1:])
    assert read.exit_code == 0, read.output
    assert read.stdout_bytes == (vault / "Course/New.md").read_bytes()


def test_ls_ids_show_paths_instead_of_row_numbers(cli, vault):
    result = cli(["obsidian", "ls", *_scope(vault), "--ids"])

    assert result.exit_code == 0, result.output
    assert _rows(result.stdout) == []
    assert "Course/New.md" in result.stdout


def test_ls_json_is_the_full_records_newest_first_and_saves_no_rows(cli, vault, config):
    from connectonion.useful_tools import obsidian as api
    result = cli(["obsidian", "ls", *_scope(vault), "--json"])

    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)
    assert [note["path"] for note in data] == ["Course/New.md", "Course/Week1/Mid.md", "Course/Old.md"]
    expected = {note["path"]: note for note in api.list_notes(vault, folders=["Course"])}
    assert data == [expected[note["path"]] for note in data]
    assert not _last_notes(config).exists()
    _assert_one_next(result, "stderr")


@pytest.mark.parametrize("command", [["obsidian"], VAULTS], ids=["bare", "vaults"])
def test_vault_and_folder_next_commands_can_be_copied_through_to_read(command, cli, registry, tmp_path):
    gone = tmp_path / "vaults" / "Absent"
    personal = _vault(tmp_path, "Personal", notes=("Course/First.md", "Projects/Other.md", "Welcome.md"))
    later = _vault(tmp_path, "Reference")
    registry(_entries(gone, personal, later))
    (personal / ".copilot").mkdir()
    (personal / "Welcome.md").write_bytes(b"\xff\xfe")
    (personal / "Projects" / "Other.md").write_bytes(b"\xff\xfe")

    folders = _next(cli(command))
    assert folders == ["co", "obsidian", "ls", "--vault", "2"]
    listing = cli(folders[1:])
    assert listing.exit_code == 0, listing.output
    assert _rows(listing.stdout)[:2] == [(1, "Course/"), (2, "Projects/")]
    assert "Welcome.md" in listing.stdout
    assert "First.md" not in listing.stdout
    assert ".obsidian/" not in listing.stdout

    notes = _next(listing)
    assert notes == ["co", "obsidian", "ls", "--vault", "Personal", "--folder", "1"]
    result = cli(notes[1:])
    assert result.exit_code == 0, result.output
    read = cli(_next(result)[1:])
    assert read.exit_code == 0, read.output
    assert read.stdout == "# Course/First.md\nbody\n"


def test_vault_row_stays_bound_when_registry_order_changes(cli, registry, tmp_path):
    personal = _vault(tmp_path, "Personal", notes=("Course/One.md",))
    earlier = _vault(tmp_path, "Earlier", notes=("Other/Two.md",))
    registry(_entries(personal))
    command = _next(cli(VAULTS))[1:]
    registry(_entries(earlier, personal))

    result = cli(command)

    assert result.exit_code == 0, result.output
    assert "Course/" in result.stdout
    assert "Other/" not in result.stdout
    registry(_entries(earlier))
    _assert_safe_failure(cli(command), 1)


def test_folder_rows_stay_bound_to_the_vault_and_displayed_order(cli, vault, registry, tmp_path):
    another = _vault(tmp_path, "Second", notes=("Other/Private.md",))
    registry(_entries(vault, another))
    browse = cli(["obsidian", "ls", "--vault", str(vault)])
    command = _next(browse)[1:]
    (vault / "Alpha").mkdir()
    _assert_safe_failure(cli(["obsidian", "ls", *_scope(another, "1")]), 2)
    assert cli(["obsidian", "ls", "--vault", str(another)]).exit_code == 0

    result = cli(command)

    assert result.exit_code == 0, result.output
    assert _rows(result.stdout) == [(1, "New.md"), (2, "Mid.md"), (3, "Old.md")]


def test_json_browsing_offers_literal_next_commands_without_caching(cli, registry, config, tmp_path):
    personal = _vault(tmp_path, "Personal", notes=("1/One.md", "Welcome.md"))
    registry(_entries(personal))
    vaults = cli([*VAULTS, "--json"])
    assert _next(vaults, "stderr") == ["co", "obsidian", "ls", "--vault", str(personal.resolve())]

    result = cli(["obsidian", "ls", "--vault", str(personal), "--json"])

    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout) == {"vault": str(personal.resolve()), "folders": ["1"], "notes": ["Welcome.md"]}
    assert not (config / "obsidian-listings").exists()
    command = _next(result, "stderr")
    assert command[-2:] == ["--folder", "./1"]
    assert _rows(cli(command[1:]).stdout) == [(1, "One.md")]


def test_navigation_uses_paths_when_the_row_cache_points_inside_a_vault(cli, registry, config, vault):
    registry(_entries(vault))
    inside = vault / ".obsidian" / "cache"
    inside.mkdir()
    config.mkdir()
    (config / "obsidian-listings").symlink_to(inside, target_is_directory=True)

    command = _next(cli(VAULTS))
    assert command[-2:] == ["--vault", str(vault.resolve())]
    folders = cli(command[1:])

    assert folders.exit_code == 0, folders.output
    command = _next(folders)
    assert command[-3:] == ["--folder", "Course", "--json"]
    notes = cli(command[1:])
    assert notes.exit_code == 0, notes.output
    assert "Course/New.md" in notes.stdout
    assert list(inside.iterdir()) == []


@pytest.mark.parametrize("kind", ["vault", "folder"])
def test_numbered_vault_and_folder_rows_expire(kind, cli, registry, vault, monkeypatch):
    from connectonion.cli.commands import gmail_listings

    registry(_entries(vault))
    now = [1000.0]
    monkeypatch.setattr(gmail_listings.time, "time", lambda: now[0])
    command = _next(cli(VAULTS))[1:]
    if kind == "folder":
        command = _next(cli(command))[1:]

    now[0] += 900
    _assert_safe_failure(cli(command), 2)


def test_vault_and_folder_browsing_preserves_a_pinned_note_listing(cli, registry, vault, monkeypatch):
    from connectonion.cli.commands import gmail_listings

    monkeypatch.setattr(gmail_listings, "MAX_LISTINGS", 1)
    registry(_entries(vault))
    notes = cli(["obsidian", "ls", *_scope(vault)])
    read = _next(notes)[1:]
    folders = _next(cli(VAULTS))[1:]
    assert cli(folders).exit_code == 0

    result = cli(read)

    assert result.exit_code == 0, result.output
    assert result.stdout_bytes == (vault / "Course/New.md").read_bytes()


@pytest.mark.parametrize("folder", ["..", "/abs", ".obsidian"])
def test_ls_with_an_unsafe_folder_is_a_usage_error(folder, cli, vault):
    _assert_safe_failure(cli(["obsidian", "ls", *_scope(vault, folder)]), 2)


def test_ls_with_a_missing_folder_exits_1(cli, vault):
    _assert_safe_failure(cli(["obsidian", "ls", *_scope(vault, "Nope")]), 1)


def test_ls_in_an_empty_folder_succeed_with_no_rows(cli, vault):
    (vault / "Empty").mkdir()
    result = cli(["obsidian", "ls", *_scope(vault, "Empty")])

    assert result.exit_code == 0, result.output
    assert _rows(result.stdout) == []
    assert _next(result) == ["co", "obsidian", "ls", "--vault", str(vault.resolve())]


def test_ls_with_a_bad_file_exits_1_naming_it(cli, vault):
    (vault / "Course" / "Broken.md").write_bytes(b"\xff\xfe bad")
    result = cli(["obsidian", "ls", *_scope(vault)])

    _assert_safe_failure(result, 1)
    assert "Course/Broken.md" in result.stderr


# -- choosing the vault ----------------------------------------------------

def test_the_only_available_vault_is_used_without_vault(cli, vault, registry, tmp_path):
    registry(_entries(vault, tmp_path / "vaults" / "Gone"))
    result = cli(["obsidian", "ls", "--folder", "Course"])

    assert result.exit_code == 0, result.output
    assert len(_rows(result.stdout)) == 3


def test_several_available_vaults_need_vault(cli, vault, registry, tmp_path):
    registry(_entries(vault, _notes_vault(tmp_path, {"a.md": "a"}, name="Second")))
    result = cli(["obsidian", "ls", "--folder", "."])

    _assert_safe_failure(result, 2)
    assert "co obsidian vaults" in result.stderr


def test_no_registered_vault_without_vault_exits_1(cli, registry):
    _assert_safe_failure(cli(["obsidian", "ls", "--folder", "."]), 1)


def test_vault_can_be_named_as_registered(cli, vault, registry):
    registry(_entries(vault))
    result = cli(["obsidian", "ls", "--vault", "Notes", "--folder", "Course"])

    assert result.exit_code == 0, result.output
    assert len(_rows(result.stdout)) == 3


def test_vault_row_requires_a_recent_listing(cli, vault, registry):
    registry(_entries(vault))

    _assert_safe_failure(cli(["obsidian", "ls", "--vault", "1", "--folder", "."]), 2)


# -- read ------------------------------------------------------------------

def test_read_row_prints_the_original_markdown_only(cli, vault):
    cli(["obsidian", "ls", *_scope(vault)])
    result = cli(["obsidian", "read", "1", *_scope(vault)])

    assert result.exit_code == 0, result.output
    assert result.stdout_bytes == (vault / "Course/New.md").read_bytes()      # CRLF kept
    assert "Next:" not in result.stdout
    _assert_one_next(result, "stderr")


def test_read_next_starts_on_its_own_line_and_searches_the_listed_folder(cli, vault, registry):
    registry(_entries(vault))
    content = b"logic in a note with no final newline"
    (vault / "Course/New.md").write_bytes(content)
    listed = cli(["obsidian", "ls", *_scope(vault)])

    read = cli(_next(listed)[1:])

    assert read.exit_code == 0, read.output
    assert read.stdout_bytes == content
    tip = _assert_one_next(read, "stderr")
    assert read.output.splitlines() == [content.decode(), tip]
    args = _next(read, "stderr")[1:]
    assert args == ["obsidian", "search", "<query>", "--vault", vault.name, "--folder", "Course"]
    args[2] = "logic"
    search = cli(args)
    assert search.exit_code == 0, search.output
    assert "Course/New.md" in search.stdout
    assert "Other/Outside.md" not in search.stdout


@pytest.mark.parametrize("registry_state", ["duplicate", "unreadable"])
def test_read_next_keeps_the_path_when_the_vault_name_cannot_be_used(registry_state, cli, vault, registry, tmp_path):
    if registry_state == "duplicate":
        other = _vault(tmp_path / "second", vault.name)
        registry(_entries(vault, other))
    else:
        registry(raw=b"{broken")

    read = cli(["obsidian", "read", "Course/Old.md", *_scope(vault)])

    assert read.exit_code == 0, read.output
    assert read.stdout == "old note about logic\n"
    assert _next(read, "stderr")[3:] == ["<query>", *_scope(vault.resolve())]


def test_terminal_read_formats_the_note_and_raw_can_still_show_the_source(vault, isolated_home, capsysbinary, monkeypatch):
    from connectonion.cli.commands.obsidian_commands import handle_obsidian_read

    content = (
        b"---\r\nstatus: ready\r\n---\r\n## Details\r\n\r\n- **Checked** the note\r\n\r\n"
        b"```python\r\nprint('ready')\r\n```\r\n\r\n<div>\r\nKeep this embedded text.\r\n</div>"
    )
    (vault / "Course/New.md").write_bytes(content)
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
    monkeypatch.setenv("NO_COLOR", "1")

    handle_obsidian_read("Course/New.md", vault=str(vault), folders=("Course",))

    shown = capsysbinary.readouterr()
    display = re.sub(rb"\x1b\[[0-9;]*m", b"", shown.out)
    assert display.startswith(b"New\nCourse/New.md\n\n")
    assert b"Properties\nstatus: ready\n" in display
    assert b"Details" in display and b"## Details" not in display
    assert b"Checked the note" in display and b"**Checked**" not in display
    assert b"print('ready')" in display
    assert b"Keep this embedded text." in display
    assert shown.err.startswith(b"Next: co obsidian search ")

    handle_obsidian_read("Course/New.md", vault=str(vault), folders=("Course",), raw=True)

    raw = capsysbinary.readouterr()
    assert raw.out == content
    assert raw.err.startswith(b"\nNext: co obsidian search ")


@pytest.mark.parametrize("ref", ["2", "#2"])
def test_read_row_number_with_or_without_hash(ref, cli, vault):
    cli(["obsidian", "ls", *_scope(vault)])
    result = cli(["obsidian", "read", ref])

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
    first = cli(["obsidian", "ls", *_scope(vault)])
    cli(["obsidian", "ls", *_scope(vault, "Other")])  # row 1 is now Outside.md

    result = cli(_next(first)[1:])

    assert result.exit_code == 0, result.output
    assert result.stdout_bytes == (vault / "Course/New.md").read_bytes()
    assert cli(["obsidian", "read", "1"]).stdout == "logic outside the folder\n"


def test_legacy_listing_still_reads_with_its_explicit_scope(cli, vault, config):
    from connectonion.cli.commands.gmail_listings import save_listing
    from connectonion.cli.commands.obsidian_commands import _listing_context

    context = _listing_context(vault, ("Course",))
    token = save_listing(_last_notes(config).parent, context, "notes", ["Course/New.md"], provider="obsidian")

    _assert_safe_failure(cli(["obsidian", "read", "1", "--listing", token]), 2)
    read = cli(["obsidian", "read", "1", *_scope(vault), "--listing", token])
    assert read.exit_code == 0, read.output
    assert read.stdout_bytes == (vault / "Course/New.md").read_bytes()


@pytest.mark.parametrize("field,value", [
    ("expires_at", 0),
    ("expires_at", "later"),
    ("scope", []),
    ("scope", {"folders": ["Course"]}),
], ids=["expired", "invalid-expiry", "invalid-scope", "missing-vault"])
def test_numbered_read_reports_an_expired_or_invalid_scope(field, value, cli, vault, config):
    listing = cli(["obsidian", "ls", *_scope(vault)])
    token = _listing_token(listing.stdout)
    cache = _last_notes(config).parent / f"{token}.scope"
    data = json.loads(cache.read_text(encoding="utf-8"))
    data[field] = value
    cache.write_text(json.dumps(data), encoding="utf-8")

    result = cli(["obsidian", "read", "1", "--listing", token])

    _assert_safe_failure(result, 2)
    assert "Note listing unavailable or expired" in result.stderr


@pytest.mark.parametrize("error_type", [KeyError, TypeError])
def test_numbered_read_surfaces_unexpected_scope_errors(error_type, cli, monkeypatch):
    from connectonion.cli.commands import obsidian_commands

    error = error_type("unexpected lookup error")

    def broken_scope(listing):
        raise error

    monkeypatch.setattr(obsidian_commands, "_read_note_scope", broken_scope)

    result = cli(["obsidian", "read", "1", "--listing", "0" * 32])

    assert result.exception is error


@pytest.mark.skipif(sys.platform == "win32", reason="symlinks require privileges on Windows")
@pytest.mark.parametrize("command", ["row", "read", "ls", "search"])
@pytest.mark.parametrize("redirect", ["folder", "vault", "ancestor"])
def test_cli_keeps_the_validated_scope_when_paths_redirect(command, redirect, cli, vault, tmp_path, monkeypatch):
    from connectonion.cli.commands import obsidian_commands as commands

    listing = cli(["obsidian", "ls", *_scope(vault)])
    token = _listing_token(listing.stdout)
    alternate = _notes_vault(tmp_path / "replacement", {"Course/New.md": "UNSELECTED secret"}, name=vault.name)
    target = {"folder": vault / "Course", "vault": vault, "ancestor": vault.parent}[redirect]
    replacement = {"folder": alternate / "Course", "vault": alternate, "ancestor": alternate.parent}[redirect]
    hook = "_resolve_row" if command == "row" else "_selection"
    original = getattr(commands, hook)

    def redirect_after_validation(*args, **kwargs):
        result = original(*args, **kwargs)
        target.rename(target.with_name(target.name + "-preserved"))
        target.symlink_to(replacement, target_is_directory=True)
        return result

    monkeypatch.setattr(commands, hook, redirect_after_validation)
    args = {"row": ["read", "1", "--listing", token],
            "read": ["read", "Course/New.md", *_scope(vault)],
            "ls": ["ls", *_scope(vault)],
            "search": ["search", "secret", *_scope(vault)]}[command]
    result = cli(["obsidian", *args, "--json"])

    assert result.exit_code in (1, 2), result.output
    assert result.stdout.strip() == ""
    assert "UNSELECTED" not in result.output


@pytest.mark.skipif(sys.platform == "win32", reason="symlinks require privileges on Windows")
@pytest.mark.parametrize("command", [["ls"], ["search", "note"]])
def test_listing_cache_keeps_original_scope_if_ancestor_redirects_after_read(command, cli, vault, tmp_path, monkeypatch):
    from connectonion.cli.commands import obsidian_commands as commands
    alternate = _notes_vault(tmp_path / "replacement", {"Course/New.md": "UNSELECTED secret"}, name=vault.name)
    original = commands._save_rows

    def redirect_before_cache(*args, **kwargs):
        vault.parent.rename(vault.parent.with_name("preserved-vaults"))
        vault.parent.symlink_to(alternate.parent, target_is_directory=True)
        return original(*args, **kwargs)

    monkeypatch.setattr(commands, "_save_rows", redirect_before_cache)
    listing = cli(["obsidian", *command, *_scope(vault)])
    assert listing.exit_code == 0, listing.output
    result = cli(["obsidian", "read", "1", "--listing", _listing_token(listing.stdout), "--json"])

    _assert_safe_failure(result, 1)
    assert "vault changed location" in result.stderr
    assert "UNSELECTED" not in result.output


@pytest.mark.skipif(sys.platform == "win32", reason="symlinks require privileges on Windows")
@pytest.mark.parametrize("navigation", ["vault", "folder", "vault-root"])
def test_navigation_rows_keep_the_validated_vault(navigation, cli, vault, registry, tmp_path, monkeypatch):
    from connectonion.cli.commands import obsidian_commands as commands
    registry(_entries(vault))
    cli(["obsidian", "vaults"])
    cli(["obsidian", "ls", "--vault", str(vault)])
    alternate = _notes_vault(tmp_path / "replacement", {"Course/New.md": "UNSELECTED secret"}, name=vault.name)
    hook = "_resolve_list_folders" if navigation == "folder" else "_resolve_list_vault"
    original = getattr(commands, hook)

    def redirect_after_navigation(*args, **kwargs):
        result = original(*args, **kwargs)
        vault.parent.rename(vault.parent.with_name("preserved-vaults"))
        vault.parent.symlink_to(alternate.parent, target_is_directory=True)
        return result

    monkeypatch.setattr(commands, hook, redirect_after_navigation)
    args = ["--vault", str(vault), "--folder", "1"] if navigation == "folder" else ["--vault", "1"]
    if navigation == "vault":
        args += ["--folder", "Course"]
    result = cli(["obsidian", "ls", *args, "--json"])

    assert result.exit_code in (1, 2), result.output
    assert result.stdout.strip() == ""
    assert "UNSELECTED" not in result.output


def test_read_row_without_a_recent_list_is_a_usage_error(cli, vault):
    _assert_safe_failure(cli(["obsidian", "read", "1", *_scope(vault)]), 2)
    _assert_safe_failure(cli(["obsidian", "read", "1"]), 2)


def test_read_row_from_another_scope_is_refused(cli, vault):
    """Rows belong to the vault and folders they were listed from."""
    cli(["obsidian", "ls", *_scope(vault, ".")])

    _assert_safe_failure(cli(["obsidian", "read", "1", *_scope(vault, "Course")]), 2)


def test_read_row_out_of_range_is_refused(cli, vault):
    cli(["obsidian", "ls", *_scope(vault)])

    _assert_safe_failure(cli(["obsidian", "read", "9", *_scope(vault)]), 2)


@pytest.mark.parametrize("ref", ["Other/Outside.md", "../x.md"], ids=["outside-folder", "dotdot"])
def test_read_outside_the_folders_is_refused(ref, cli, vault):
    _assert_safe_failure(cli(["obsidian", "read", ref, *_scope(vault)]), 2)


def test_read_missing_note_exits_1(cli, vault):
    _assert_safe_failure(cli(["obsidian", "read", "Nope", *_scope(vault)]), 1)


# -- search ----------------------------------------------------------------

def test_search_lists_hits_with_fields_and_excerpt(cli, vault, monkeypatch):
    monkeypatch.setenv("COLUMNS", "60")
    note = vault / "Course/项目与协作验证.md"
    note.write_text("logic links the selected notes to REM so the team can check every cited source.", encoding="utf-8")

    result = cli(["obsidian", "search", "logic", *_scope(vault)])

    assert result.exit_code == 0, result.output
    results = result.stdout.split("Listing:", 1)[0].rstrip()
    lines = [line.rstrip() for line in results.splitlines()]
    assert [row.strip() for _, row in _rows(results)] == ["Old", "项目与协作验证"]
    assert "   Course/Old.md" in lines
    assert "Matched body" in results
    assert "old note about logic" in results
    assert re.search(r"\b\d{4}-\d{2}-\d{2} \d{2}:\d{2} UTC\b", results)
    excerpt = next(index for index, line in enumerate(lines) if "logic links the selected notes" in line)
    assert lines[excerpt + 1].startswith("   ")
    assert "every cited source." in lines[excerpt + 1]
    assert "Outside" not in result.stdout


def test_search_hits_become_the_rows_read_takes(cli, vault):
    search = cli(["obsidian", "search", "note", *_scope(vault)])
    row, title = _rows(search.stdout)[0]

    result = cli(["obsidian", "read", str(row), *_scope(vault)])

    path = next(path for path in (vault / "Course").rglob("*.md") if path.stem == title.strip())
    assert result.stdout_bytes == path.read_bytes()


def test_search_next_reads_row_one_with_its_listing(cli, vault):
    result = cli(["obsidian", "search", "logic", *_scope(vault)])

    args = _next(result)
    assert args == ["co", "obsidian", "read", "1", "--listing", _listing_token(result.stdout)]
    read = cli(args[1:])
    assert read.exit_code == 0, read.output
    assert read.stdout == "old note about logic\n"


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

@pytest.mark.parametrize("args", [
    ["ls"], ["read", "Course/Old.md"], ["search", "logic"],
], ids=["ls", "read", "search"])
def test_selected_folder_commands_do_not_scan_other_directories(args, cli, vault, monkeypatch):
    selected = vault.resolve() / "Course"
    walk_files = obsidian._walk_files

    def walk_selected(path, descriptor=None):
        if not path.is_relative_to(selected):
            raise PermissionError("Directory outside the selection is inaccessible")
        return walk_files(path, descriptor)

    monkeypatch.setattr(obsidian, "_walk_files", walk_selected)

    result = cli(["obsidian", *args, *_scope(vault), "--json"])

    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)


def test_ls_read_and_search_never_change_the_vault(cli, vault, config):
    before = _disk(vault)

    for args in (["ls"], ["read", "1"], ["read", "Old", "--json"], ["search", "logic"],
                 ["search", "note", "--json"]):
        assert cli(["obsidian", *args, *_scope(vault)]).exit_code == 0

    assert _disk(vault) == before
    assert _last_notes(config).exists()
    assert not (vault / ".co").exists()


@pytest.mark.parametrize("command", ["ls", "read", "search"])
def test_note_commands_are_registered_for_next_tips(command):
    from connectonion.cli.commands import command_tips

    assert f"co obsidian {command}" in command_tips.NEXT
