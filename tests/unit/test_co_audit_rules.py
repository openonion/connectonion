"""Each rule in `co audit` fails the page it exists to catch, in the layouts real CLIs print (#1735).

`co audit` only reads what a program prints, so these rules are tested on
printed pages: one well-formed page, then one page per defect, then the
listing layouts of Typer, click/uv, gh and argparse. A rule that stops firing
turns this red instead of turning a real audit silently green.
"""

import sys

from connectonion.cli import audit
from connectonion.cli.audit import Page

GOOD = """ Usage: co mail send [OPTIONS] TO

 Send one message. Sends it now.

╭─ Options ─────────────╮
│ --cc   TEXT  Copy to  │
╰───────────────────────╯
 Example:  co mail send you@example.com --cc boss@example.com
"""
GROUP = """ Usage: co mail [OPTIONS] COMMAND

╭─ Send ────────────────╮
│ send   Send one message.  │
╰───────────────────────╯
╭─ Options ─────────────╮
│ --help   Show this.   │
╰───────────────────────╯
 Example:  co mail send you@example.com
"""
FOUND = {"co": Page(0, ""), "co mail": Page(0, GROUP), "co mail send": Page(0, GOOD)}


def rules(text, path="co mail send", **page):
    return {f.check for f in audit.check(path, Page(page.get("code", 0), text, page.get("wrote", ""),
                                                     page.get("hung", False)), FOUND)}


def test_a_well_formed_page_passes():
    assert rules(GOOD) == set()


def test_each_rule_fails_the_page_it_is_for():
    assert rules(GOOD, code=2) == {"prints"}
    assert rules("", hung=True) == {"hangs"}
    assert rules(GOOD, wrote=".local/state/device-id") == {"writes"}
    assert rules(GOOD.replace(" Usage:", " Use:")) == {"usage"}
    assert rules(GOOD.replace(" Example:  co mail send you@example.com --cc boss@example.com", "")) == {"example"}
    assert rules(GOOD.replace("--cc boss", "--bcc boss")) == {"flags"}
    assert rules(GOOD.replace("you@example.com", "/Users/aaron/notes.txt")) == {"private"}
    full_address = "0x" + "3f5a" * 16
    assert rules(GOOD.replace("you@example.com", full_address)) == {"private"}
    assert rules(GOOD.replace("you@example.com", "0x3f5a...c9e1")) == set()


def test_an_option_or_argument_without_a_description_is_caught():
    bare = GOOD.replace("│ --cc   TEXT  Copy to  │", "│ --cc   TEXT           │")
    assert rules(bare) == {"params"}
    ranged = GOOD.replace("│ --cc   TEXT  Copy to  │", "│ --days   INTEGER RANGE [1<=x<=365]  [default: 30] │")
    assert rules(ranged) == {"params"}
    plain = ("usage: tool [-h] [--fast]\n\noptions:\n  -h, --help  show help\n  --fast\n"
             "  --slow      Take the slow path, as you did two weeks\n              ago\n\nExample:  tool --fast\n")
    assert audit.undocumented(plain) == ["--fast"]
    continued = GOOD.replace("│ --cc   TEXT  Copy to  │", "│ --cc   TEXT  Copy to  │\n│               [default: none] │")
    assert rules(continued) == set()


def test_an_example_for_another_command_is_caught():
    other = GOOD.replace("Example:  co mail send you@example.com --cc boss@example.com", "Example:  co mail you@example.com")
    assert rules(other) == {"self_example"}


def test_subcommands_are_read_from_every_common_layout():
    typer_page = GROUP
    uv_page = "Usage: uv [OPTIONS] <COMMAND>\n\nCommands:\n  run      Run a command\n  init     Create a project\n\nOptions:\n  -q, --quiet   Quiet\n"
    gh_page = "USAGE\n  gh <command>\n\nCORE COMMANDS\n  auth:          Log in\n  pr:            Pull requests\n\nHELP TOPICS\n  environment:   Variables\n\nFLAGS\n  --version   Show version\n"
    argparse_page = "usage: tool [-h] {build,serve} ...\n\npositional arguments:\n  {build,serve}\n"
    rem_page = "co rem — a notebook.\n\nRead\n  list          List pages.\n  show          Print one page.\n"
    table_page = "Show or change settings. Changing validates and never\nstarts a run.\n\nKeys:     model        gpt\n          runner       codex\n"
    assert audit.listed_commands(typer_page) == ["send"]
    assert audit.listed_commands(uv_page) == ["run", "init"]
    assert audit.listed_commands(gh_page) == ["auth", "pr"]
    assert audit.listed_commands(argparse_page) == ["build", "serve"]
    assert audit.listed_commands(rem_page) == ["list", "show"]
    assert audit.listed_commands(table_page) == []


def test_a_word_whose_page_is_its_parents_page_is_not_a_command():
    printed = {"tool": "Usage: tool\n\nCommands:\n  cp   Copy\n", "tool cp": "Usage: tool cp\n\nModes:\n  sum   Checksum\n"}
    found = audit.pages(["tool"], lambda argv: Page(0, printed.get(" ".join(argv), printed["tool cp"])))
    assert set(found) == {"tool", "tool cp"}


def test_an_example_that_spells_the_command_by_an_alias_is_this_command():
    here = "gh extension search"
    found = {"gh": Page(0, ""), "gh extension": Page(0, ""), here: Page(0, ""), "gh search": Page(0, "")}
    assert audit._runs(["gh", "ext", "search", "--limit", "3"], found, here) == here
    assert audit._runs(["co", "--nas", "home", "logout"], {"co": 0, "co logout": 0}, "co logout") == "co logout"


def test_user_site_command_remains_reachable_with_isolated_home(tmp_path, monkeypatch):
    """A pip --user CLI must remain importable when auditing its help in a fresh HOME."""
    userbase = tmp_path / "user-site"
    userbase.mkdir()
    monkeypatch.delenv("PYTHONUSERBASE", raising=False)
    monkeypatch.setattr(audit.site, "getuserbase", lambda: str(userbase))
    script = tmp_path / "co"
    script.write_text(
        "import os, sys\n"
        f"assert os.environ.get('PYTHONUSERBASE') == {str(userbase)!r}\n"
        "assert os.environ.get('HOME') != os.environ['PYTHONUSERBASE']\n"
        "if len(sys.argv) > 1 and sys.argv[1] == 'onenote':\n"
        "    print('Usage: co onenote [OPTIONS]')\n"
        "else:\n"
        "    print('Usage: co [OPTIONS] COMMAND')\n"
        "    print('\\nCommands:\\n  onenote   List pages')\n"
    )
    monkeypatch.setattr(audit, "program", lambda _: [sys.executable, str(script)])

    _, checked = audit.audit(["co", "onenote"])
    assert list(checked) == ["co onenote"]


def test_review_flags_a_list_item_that_requires_a_long_reference(monkeypatch):
    import connectonion

    def verdict(prompt, *, output, model):
        assert "refer to that item briefly" in prompt
        assert output is audit.Review
        return audit.Review(
            clear=True,
            effects_match=True,
            example_realistic=True,
            simple=True,
            short_reference=False,
            suggestion="Show how to use a numbered row after listing pages.",
        )

    monkeypatch.setattr(connectonion, "llm_do", verdict)
    finding = audit.review("co notes read", "Usage: co notes read LONG_ID", "test-model")
    assert finding is not None
    assert finding.check == "review"
    assert "short_reference" in finding.detail


def test_rendered_help_describes_short_references_with_sequential_examples():
    from typer.testing import CliRunner

    from connectonion.cli.main import app

    runner = CliRunner()
    audit_help = runner.invoke(app, ["audit", "--help"], env={"COLUMNS": "200"})
    one_note_help = {
        name: runner.invoke(app, ["onenote", name, "--help"], env={"COLUMNS": "200"})
        for name in ("ls", "pages", "read", "create")
    }
    assert audit_help.exit_code == 0
    assert all(result.exit_code == 0 for result in one_note_help.values())
    assert "short reference" in audit_help.output
    assert "listed item" in audit_help.output
    assert "Example:  co onenote ls" in one_note_help["ls"].output
    assert "Example:  co onenote pages" in one_note_help["pages"].output
    assert "Example:  co onenote read 1" in one_note_help["read"].output
    assert "Use pages first" in one_note_help["read"].output
    assert "Example:  co onenote create 2" in one_note_help["create"].output
    assert "numbered by ls" in one_note_help["create"].output
    assert all(" | " not in result.output for result in one_note_help.values())


# -- look (#1997): what a person's terminal shows beside what an agent reads --

def styled(text):
    """A page as a terminal prints it: coloured, and wrapped at 100 columns instead of 200."""
    return text.replace(" Usage:", " \x1b[1;33mUsage:\x1b[0m").replace("Send one message. ", "Send one\n message. ")


def look(plain, terminal, path="co mail send", **kind):
    return [f.detail for f in audit.look(path, Page(0, plain), Page(0, terminal), **kind)]


def test_a_page_styled_in_a_terminal_and_plain_in_a_pipe_with_the_same_words_passes():
    assert look(GOOD, styled(GOOD)) == []


def test_a_co_page_with_no_colour_in_a_terminal_is_caught():
    [detail] = look(GOOD, GOOD)
    assert "no colour in a terminal" in detail and "connectonion/cli/style.py" in detail


def test_another_program_may_be_plain_in_a_terminal_on_purpose():
    tool = GOOD.replace("co mail", "tool mail")
    assert look(tool, tool, path="tool mail send") == []


def test_colour_in_a_pipe_is_caught_for_any_program():
    coloured = styled(GOOD).replace("co mail", "tool mail")
    [detail] = look(coloured, coloured, path="tool mail send")
    assert "colour codes under NO_COLOR" in detail


def test_different_words_in_a_terminal_are_caught_and_named():
    cut = styled(GOOD).replace("Copy to", "Copy …")
    [detail] = look(GOOD, cut)
    assert "different words" in detail and "shows … where an agent reads to" in detail


def test_a_frame_redrawn_at_another_width_is_the_same_words():
    narrow = styled(GOOD).replace("╭─ Options ─────────────╮", "╭─ Options ─╮").replace("╰───────────────────────╯", "╰─╯")
    assert look(GOOD, narrow) == []


def test_a_table_cell_folded_beside_its_description_is_the_same_words():
    folded = styled(GOOD).replace("│ --cc   TEXT  Copy to  │", "│ --cc   TE  Copy to  │\n│        XT           │")
    assert look(GOOD, folded) == []


def test_a_terminal_run_that_fails_is_caught():
    [finding] = audit.look("co mail send", Page(0, GOOD), Page(1, ""))
    assert finding.check == "look" and "exit 1" in finding.detail


def next_line_as_printed(command):
    import io

    from rich.console import Console

    from connectonion.cli import style

    buffer = io.StringIO()
    Console(file=buffer, theme=style.THEME, force_terminal=True, color_system="256").print(style.next_line(command))
    return buffer.getvalue()


def test_a_status_next_line_must_have_the_shared_shape():
    plain, balance = "Balance 3\nNext: co keys\n", "\x1b[1mBalance\x1b[0m 3\n"
    assert look(plain, balance + next_line_as_printed("co keys"), path="co status", output=True) == []
    [detail] = look(plain, balance + "\x1b[2mNext: co keys\x1b[0m\n", path="co status", output=True)
    assert detail.startswith("output") and "Next:" in detail
    why = next_line_as_printed("co keys").replace("Next:\x1b[0m ", "Next:\x1b[0m Show them:  ")
    assert look("Balance 3\nNext: Show them:  co keys\n", balance + why, path="co status", output=True) == []


def test_a_run_lends_the_command_no_credential_from_the_environment(tmp_path, monkeypatch):
    # With a key set, `co doctor` calls its backend, and the two runs look
    # compares could get different answers.
    script = tmp_path / "tool"
    script.write_text("import os\nprint(os.environ.get('OPENONION_API_KEY'), os.environ.get('LANG_KEEP'))\n")
    monkeypatch.setattr(audit, "program", lambda _: [sys.executable, str(script)])
    monkeypatch.setenv("OPENONION_API_KEY", "test-key")
    monkeypatch.setenv("LANG_KEEP", "kept")
    assert audit.run(["tool"]).text.split() == ["None", "kept"]
    assert audit.run(["tool"], terminal=True).text.split() == ["None", "kept"]


def test_the_status_commands_include_co_rem_status_now_that_it_is_a_dashboard():
    assert {"co status", "co doctor", "co commands", "co rem status"} <= set(audit.STATUS)


def test_the_audit_runs_each_page_and_each_status_command_both_ways():
    ran = []
    top = " Usage: co [OPTIONS] COMMAND\n\nCommands:\n  status   Show status. Read-only.\n\n Example:  co status\n"
    leaf = " Usage: co status [OPTIONS]\n\n Example:  co status\n"

    def runner(argv, terminal=False):
        ran.append(("help", " ".join(argv), terminal))
        text = top if argv == ["co"] else leaf
        return Page(0, styled(text) if terminal else text)

    def output(argv, terminal=False):
        ran.append(("output", " ".join(argv), terminal))
        return Page(0, "Balance \x1b[1m3\x1b[0m\n" if terminal else "Balance 3\n", err="Next: co keys\n")

    findings, checked = audit.audit(["co", "status"], runner=runner, output=output)
    assert set(checked) == {"co status"}
    assert ("help", "co status", True) in ran and ("help", "co", True) not in ran
    assert {("output", "co status", False), ("output", "co status", True)} <= set(ran)
    assert [(f.path, f.check) for f in findings] == [("co status", "look")]
    assert "Next:" in findings[0].detail
    assert dict((rule, passing) for rule, passing, _ in audit.score(findings, checked))["look"] == 0


# -- what #2008 found the look rule missing --

def test_a_line_repeated_at_the_top_is_caught():
    noise = "[env] ~/.co/keys.env\n"
    details = look(GOOD, noise * 2 + styled(GOOD))    # also different words: the pipe never had it
    assert any("twice at the top" in d and "[env] ~/.co/keys.env" in d for d in details)
    assert look(noise * 2 + GOOD, noise * 2 + styled(GOOD)) == [
        "help prints `[env] ~/.co/keys.env` twice at the top"]


def test_the_terminal_run_gives_stderr_a_terminal(tmp_path, monkeypatch):
    # `[env]` printed only when stderr was a TTY, and the audit piped stderr.
    script = tmp_path / "tool"
    script.write_text("import sys\nprint(sys.stdout.isatty(), sys.stderr.isatty())\n"
                      "print('err', file=sys.stderr)\n")
    monkeypatch.setattr(audit, "program", lambda _: [sys.executable, str(script)])
    page = audit.run(["tool"], terminal=True)
    assert page.text.split() == ["True", "True"] and page.err.strip() == "err"
    assert audit.run(["tool"]).text.split() == ["False", "False"]


def test_a_word_coloured_in_pieces_is_caught():
    # Rich's highlighter: `co 1.9.0a5` with `1.9` alone in bold cyan.
    [detail] = look(GOOD + "co 1.9.0a5\n", styled(GOOD) + "co \x1b[1;36m1.9\x1b[0m.0a5\n")
    assert "coloured in pieces" in detail and "1.9.0a5" in detail


def test_a_word_in_one_colour_beside_punctuation_is_not_pieces():
    shown = styled(GOOD) + "Run (\x1b[1;36mco auth\x1b[0m) or \x1b[2m~/.co/keys.env\x1b[0m.\n"
    assert look(GOOD + "Run (co auth) or ~/.co/keys.env.\n", shown) == []


def test_an_emoji_in_a_panel_title_is_caught():
    titled = styled(GOOD).replace("╭─ Options ─", "╭─ 📊 Options ─")
    [detail] = look(GOOD.replace("╭─ Options ─", "╭─ 📊 Options ─"), titled)
    assert "emoji in a panel title" in detail


def test_a_status_command_without_a_next_line_is_caught():
    [detail] = look("Balance 3\n", "\x1b[1mBalance\x1b[0m 3\n", path="co status", output=True)
    assert "no Next: line" in detail


def test_the_status_commands_include_the_ones_2008_found():
    assert {"co auth status", "co whatsapp check"} <= set(audit.STATUS)
