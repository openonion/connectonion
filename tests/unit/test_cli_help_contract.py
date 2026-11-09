"""`co` passes `co audit co`, plus its own house style, judged from printed pages (#1657, #1721, #1735).

`co audit` holds every CLI to the same rules; this test runs that engine on
`co` itself. On top, three conventions that are ours rather than universal:
each page says what it changes in a fixed word, names its way back, and every
command `co commands` lists can be reached from `co --help`.

`co rem` prints reviewed pages word for word and is held to them by
tests/e2e/cli/test_rem_help_contract.py; it is being rewritten (#1667).
It is held to the look rule (#1997) all the same, except for LOOK_PENDING.

CI audits the tree in parallel jobs: CO_AUDIT_SHARD=i/N audits the
top-level commands that fall to shard i, each walked exactly as the whole
walk would, and writes the pages it audited to CO_AUDIT_PAGES_DIR. The
whole-tree checks (how many pages, what `co commands` lists that no page
reaches) then run once over every shard's list. Without the variables one
run does all of it.
"""

import os
import re
import time
from collections import Counter
from pathlib import Path

import pytest

from connectonion.cli import audit

LABELS = re.compile(r"\b(Read-only|Writes|Sends|Deletes|Removes|Creates|Changes|Charges|"
                    r"Deploys|Installs|Uploads|Publishes|Starts|Stops|Runs)\b")
OWN_PAGES = "co rem"
# co rem pages that fail the look rule today: plain in a terminal, because
# rem_help.py prints them verbatim. Their rewrite onto connectonion/cli/style.py
# is #1996, and this set must shrink to empty when it lands. It can only
# shrink: a page here that passes (or is gone) fails the test until it is taken
# out, and nothing outside co rem may wait here.
LOOK_PENDING: set = set()


def look_problems(findings: list, pending: set = LOOK_PENDING) -> list:
    """co rem's look findings beyond the baseline, and baseline entries that no longer fail."""
    failing = {f.path for f in findings if f.check == "look"}
    problems = [f"{path}  look: only co rem may wait on #1996" for path in sorted(pending)
                if not path.startswith(OWN_PAGES)]
    problems += [f"{f.path}  look: {f.fix}" for f in findings
                 if f.check == "look" and f.path.startswith(OWN_PAGES) and f.path not in pending]
    problems += [f"{path}  look: passes now; take it out of LOOK_PENDING" for path in sorted(pending - failing)]
    return problems


def test_the_look_baseline_can_only_shrink():
    plain = audit.Finding("co rem list", "look", "help has no colour in a terminal")
    new = audit.Finding("co rem new", "look", "help has no colour in a terminal")
    assert look_problems([plain], {"co rem list"}) == []
    assert [p.split()[2] for p in look_problems([plain, new], {"co rem list"})] == ["new"]
    assert "passes now" in " ".join(look_problems([], {"co rem list"}))
    assert "only co rem" in " ".join(look_problems([plain], {"co rem list", "co gmail"}))


def test_shards_together_find_what_one_audit_finds():
    # mail send's example runs chat post, another shard's command; mail read
    # repeats its parent word for word, so it is not a page.
    tree = {
        "co": "Usage: co COMMAND\n\nCommands:\n  mail   Mail. Read-only.\n  chat   Chat. Read-only.\n\nExample: co mail\n",
        "co mail": "Usage: co mail COMMAND\n\nCommands:\n  send   Send. Sends.\n  read   Read.\n\nExample: co mail send\n",
        "co mail send": "Usage: co mail send\nSends.\nExample: co chat post --to bob\nBack: co mail\n",
        "co chat": "Usage: co chat COMMAND\n\nCommands:\n  post   Post. Sends.\n\nExample: co chat post --to bob\n",
        "co chat post": "Usage: co chat post\n\nOptions:\n  --to TEXT   who gets it\n\nExample: co chat post --to bob --cc\n",
    }
    tree["co mail read"] = tree["co mail"]

    def runner(argv, terminal=False):
        return audit.Page(0, tree[" ".join(argv)]) if " ".join(argv) in tree else audit.Page(2, "")

    whole_findings, whole = audit.audit(["co"], runner=runner, output=runner)
    listed = {"co mail send", "co mail read", "co chat post"}
    for shards in (1, 2, 3):
        audited, findings = [], []
        for shard in range(1, shards + 1):
            found, within = audit_shard(shard, shards, listed, runner)
            audited += within
            findings += found
        assert sorted(audited) == sorted(whole)
        assert sorted(map(str, findings)) == sorted(map(str, whole_findings))
    assert any(f.path == "co chat post" and f.check == "flags" for f in whole_findings)


SHARD = os.environ.get("CO_AUDIT_SHARD", "1/1")
PAGES_DIR = os.environ.get("CO_AUDIT_PAGES_DIR")
REGISTERED = re.compile(r"^(co(?: [a-z][a-z0-9_-]*)*)(?:\s{2,}|$)", re.M)


def registered() -> set:
    return set(REGISTERED.findall(audit.run(["co", "commands"]).text))


def shard_groups(root: audit.Page, listed: set, shard: int, shards: int) -> set:
    """The top-level commands shard `shard` audits: largest first onto the lightest shard, sized by `co commands`."""
    groups = audit.listed_commands(root.text)
    size = {group: 1 + sum(path.startswith(f"co {group} ") for path in listed) for group in groups}
    loads, mine = [0] * shards, [set() for _ in range(shards)]
    for group in sorted(groups, key=lambda group: (-size[group], group)):
        lightest = loads.index(min(loads))
        loads[lightest] += size[group]
        mine[lightest].add(group)
    return mine[shard - 1]


def walk(groups: set, runner=audit.help_page) -> dict:
    """`co` and every page under these top-level commands, found by audit.pages itself."""
    elsewhere = audit.Page(code=-2, text="")

    def only_these(argv, terminal=False):
        return elsewhere if len(argv) > 1 and argv[1] not in groups else runner(argv, terminal)

    return {path: page for path, page in audit.pages(["co"], only_these).items() if page is not elsewhere}


def with_references(found: dict, within: dict, runner=audit.help_page) -> dict:
    """`found` plus every page an example on `within` runs, reached as the whole walk reaches it.

    check() resolves each example against the pages it is given; another
    shard's command must resolve here exactly as it does on the whole tree.
    """
    found, same = dict(found), set()
    for path, page in within.items():
        for words in audit.examples(page.text, "co"):
            here = words[0]
            for before, word in zip(words, words[1:]):
                child, parent = f"{here} {word}", found.get(here)
                if (child not in found and child not in same and parent and parent.code == 0
                        and word in audit.listed_commands(parent.text)):
                    fetched = runner(child.split())
                    if fetched.text == parent.text:   # audit.pages drops a child that repeats its parent
                        same.add(child)
                    else:
                        found[child] = fetched
                if child in found:
                    here = child
                elif not word.startswith("-") and not before.startswith("-"):
                    break
    return found


def audit_shard(shard: int, shards: int, listed: set, runner=audit.help_page, output=audit.run) -> tuple:
    """audit.audit(["co"]) for one shard's share of the tree: (findings, pages audited)."""
    found = walk(shard_groups(runner(["co"]), listed, shard, shards), runner)
    within = {path: page for path, page in found.items() if path != "co" or shard == 1}
    resolvable = with_references(found, within, runner)
    findings = [f for path, page in within.items() for f in audit.check(path, page, resolvable)]
    return findings + audit.looks(within, findings, runner, output), within


def timed(run, spent: list):
    """`run`, appending (top-level command, seconds) to `spent` for each process it starts."""
    def wrapper(argv, terminal=False):
        start = time.monotonic()
        page = run(argv, terminal)
        spent.append((" ".join(argv[:2]), time.monotonic() - start))
        return page
    return wrapper


def page_problems(findings: list, within: dict) -> list:
    ours = {path: page for path, page in within.items() if not path.startswith(OWN_PAGES)}
    problems = [f"{f.path}  {f.check}: {f.fix}" for f in findings if not f.path.startswith(OWN_PAGES)]
    problems += look_problems(findings, LOOK_PENDING & set(within))
    problems += [f"{path}  side_effect: say what it changes with one of: {LABELS.pattern}"
                 for path, page in ours.items() if not LABELS.search(page.text)]
    problems += [f"{path}  back: no Back: line" for path, page in ours.items()
                 if path != "co" and not re.search(r"\b(Back|Next):", page.text)]
    return problems


def tree_problems(audited: set, listed: set) -> list:
    """The checks that need the whole tree: run once, over every page audited."""
    ours = [path for path in audited if not path.startswith(OWN_PAGES)]
    problems = [] if len(ours) > 200 else [f"the walk reached only {len(ours)} pages"]
    problems += [f"{path}  unreachable: co commands lists it, no page from co --help does"
                 for path in sorted(listed - audited) if not path.startswith(OWN_PAGES + " ")]
    problems += [f"{path}  look: gone; take it out of LOOK_PENDING" for path in sorted(LOOK_PENDING - audited)]
    return problems


@pytest.mark.timeout(900)
@pytest.mark.slow
def test_co_meets_the_contract_and_its_house_style():
    shard, shards = map(int, SHARD.split("/"))
    listed = registered()
    spent = []
    findings, within = audit_shard(shard, shards, listed, timed(audit.help_page, spent), timed(audit.run, spent))
    seconds = Counter()
    for group, took in spent:
        seconds[group] += took
    print(f"{len(spent)} processes, {sum(seconds.values()):.0f} s; slowest commands:",
          ", ".join(f"{group} {took:.0f} s" for group, took in seconds.most_common(8)))
    problems = page_problems(findings, within)
    if shards == 1:
        problems += tree_problems(set(within), listed)
    if PAGES_DIR:
        Path(PAGES_DIR, f"shard-{shard}.txt").write_text("\n".join([SHARD, *sorted(within)]))
    assert not problems, "\n".join(problems) + "\nRun: co audit co"


@pytest.mark.slow
@pytest.mark.skipif(not PAGES_DIR, reason="CI's last audit job; a run without CO_AUDIT_SHARD checks the tree itself")
def test_the_shards_together_audit_every_page_once():
    lists = [path.read_text().splitlines() for path in sorted(Path(PAGES_DIR).glob("shard-*.txt"))]
    shards = {int(lines[0].split("/")[1]) for lines in lists}
    assert len(shards) == 1, f"the shards disagree on how many there are: {shards}"
    assert sorted(int(lines[0].split("/")[0]) for lines in lists) == list(range(1, shards.pop() + 1))
    audited = Counter(path for lines in lists for path in lines[1:])
    problems = [f"{path}  audited by {count} shards" for path, count in sorted(audited.items()) if count > 1]
    problems += tree_problems(set(audited), registered())
    assert not problems, "\n".join(problems)
