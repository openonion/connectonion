"""Each hard rule in `co audit` fails the page it exists to catch (#1735).

`co audit` only reads what `co` prints, so these rules are tested on printed
pages: one well-formed page, then one page per defect. A rule that stops
firing turns this red instead of turning the real audit silently green.
"""

from connectonion.cli import audit

GOOD = """ Usage: co mail send [OPTIONS] TO

 Send one message. Sends it now.

╭─ Options ─────────────╮
│ --cc   TEXT  Copy to  │
╰───────────────────────╯
 Example:  co mail send you@example.com --cc boss@example.com

 Back: co mail --help
"""
GROUP = """ Usage: co mail [OPTIONS] COMMAND

 Mail. Read-only unless you send.

╭─ Send ────────────────╮
│ send   Send one message.  │
╰───────────────────────╯
╭─ Read ────────────────╮
│ inbox  List mail.      │
╰───────────────────────╯
 Example:  co mail inbox

 Back: co --help
"""
FOUND = {"co": (0, "", False), "co mail": (0, GROUP, False),
         "co mail send": (0, GOOD, False), "co mail inbox": (0, GOOD, False)}


def rules(page_text, path="co mail send", code=0, wrote=False):
    return {f.check for f in audit.check(path, (code, page_text, wrote), FOUND)}


def test_a_well_formed_page_passes():
    assert rules(GOOD) == set()


def test_each_rule_fails_the_page_it_is_for():
    assert rules(GOOD, code=2) == {"exit0"}
    assert rules(GOOD, wrote=True) == {"writes"}
    assert rules(GOOD.replace(" Usage:", " Use:")) == {"usage"}
    assert rules(GOOD.replace(" Example:  co mail send you@example.com --cc boss@example.com", "")) == {"example"}
    assert rules(GOOD.replace("co mail send you@", "co mail inbox you@")) == {"self_example"}
    assert rules(GOOD.replace("--cc boss", "--bcc boss")) == {"flags"}
    assert rules(GOOD.replace("Back: co mail --help", "Back: co mailbox --help")) == {"refs"}
    assert rules(GOOD.replace("Sends it now.", "Deliver it.")) == {"side_effect"}
    assert rules(GOOD.replace(" Back: co mail --help", "")) == {"back"}
    assert rules(GOOD.replace("you@example.com", "/Users/aaron/notes.txt")) == {"private"}


def test_commands_are_read_from_any_panel_but_options_and_arguments():
    assert audit.listed_commands(GROUP) == ["send", "inbox"]
    assert audit.listed_commands(GOOD) == []


def test_the_walk_follows_printed_names_and_reports_what_it_cannot_reach():
    printed = {"co": " Usage: co\n╭─ Commands ─╮\n│ mail   Mail. │\n╰────╯\n", "co mail": GROUP,
               "co mail send": GOOD, "co mail inbox": GOOD}
    found = audit.pages("co", lambda words: (0, printed[" ".join(["co", *words])], False))
    assert set(found) == set(printed)

    def register(words):
        return 0, "co mail            Mail.\nco mail archive    Hidden from every page.\n", False

    assert [f.path for f in audit.unreachable(found, register)] == ["co mail archive"]
