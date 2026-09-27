"""Each rule in `co audit` fails the page it exists to catch, in the layouts real CLIs print (#1735).

`co audit` only reads what a program prints, so these rules are tested on
printed pages: one well-formed page, then one page per defect, then the
listing layouts of Typer, click/uv, gh and argparse. A rule that stops firing
turns this red instead of turning a real audit silently green.
"""

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
    wiki_page = "co wiki — a notebook.\n\nRead\n  list          List pages.\n  show          Print one page.\n"
    table_page = "Show or change settings. Changing validates and never\nstarts a run.\n\nKeys:     model        gpt\n          runner       codex\n"
    assert audit.listed_commands(typer_page) == ["send"]
    assert audit.listed_commands(uv_page) == ["run", "init"]
    assert audit.listed_commands(gh_page) == ["auth", "pr"]
    assert audit.listed_commands(argparse_page) == ["build", "serve"]
    assert audit.listed_commands(wiki_page) == ["list", "show"]
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
