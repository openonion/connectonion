"""`co obsidian vaults` (F13DBREAD-2): rows, --json, empty and broken registries, exit codes.

The command is invoked through the root app, as a user would. Registries and vaults are
synthetic, under tmp_path; discovery is pointed at them through obsidian._registry_path.
"""

import json
import os

import pytest
from typer.testing import CliRunner

from connectonion.useful_tools import obsidian
from tests.unit.test_obsidian import _entries, _vault, isolated_home, no_note_reads, registry  # noqa: F401

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
