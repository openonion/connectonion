"""An entry page's model (#3097): the text once, every Sources block gathered into one list, marks renumbered.

Invented pages only. The functions are the reader's own, run in Node.
"""

import json
import re

from connectonion.rem.reader import TEMPLATE
from tests.unit.test_rem_reader import _run_reader_js

OLD = """- Also known as: Checking a tick

A saved schedule does not show whether the job ran. [1]
Mara said on 2026-02-03:
“The calendar trigger never fired.” [2]

## Drawn from
- [Trigger choice](../decisions/trigger.md)
- [Scheduler trial](../projects/trial.md)

## Sources
- [1] codex:s1:12 — originating page: `decisions/trigger.md`.
- [2] codex:s2:31 — originating page: `projects/trial.md`.

## Receipts after the due time
Check the receipt. [1] The tick wrote one. [2]

### Drawn from
- [Receipts](../decisions/receipts.md)

### Sources
- [1] codex:s3:7 — originating page: `decisions/receipts.md`
- [2] codex:s1:12 — originating page: `decisions/trigger.md`.

## Retries
Retry once, then stop. [5][6] Nobody defined this one. [9]

### Sources
- [5] gmail:m1 — 2026-02-04
- [6] gmail:m2 — 2026-02-05
"""

NEW = """Plain pages made diagnosis possible. [2]

## Drawn from
- [Storage](../decisions/storage.md)

## Recovery
Search stayed linear. [7]

### Drawn from
- [Recovery](../decisions/recovery.md)

## Sources
- [2] codex:a:1 — originating page: `decisions/storage.md`.
- [7] codex:b:2 — originating page: `decisions/recovery.md`.
"""

PRINCIPLE = """Pattern: measure the behaviour.

Drawn from:
- [Tick](./tick.md): the calendar lied.
- [Login](./login.md): the status lied.

Reach for it when a check says it is fine.
"""


def model(body):
    page = TEMPLATE.read_text()
    functions = "\n".join(re.search(r"function " + name + r"\(.*?\n\}", page, re.S).group(0)
                          for name in ["entryParse", "entryNumbers", "entryModel", "sourceId"])
    return _run_reader_js(functions + "\nconsole.log(JSON.stringify(entryModel(" + json.dumps(body) + ")));")


def test_every_sources_block_is_gathered_into_one_list_numbered_continuously():
    result = model(OLD)
    assert [s["n"] for s in result["sources"]] == ["1", "2", "3", "4", "5"]
    assert [s["text"].split(" ")[0] for s in result["sources"]] == ["codex:s1:12", "codex:s2:31", "codex:s3:7", "gmail:m1", "gmail:m2"]


def test_marks_follow_their_own_sections_definitions_and_a_shared_source_is_listed_once():
    lead, receipts, retries = model(OLD)["sections"]
    assert "ran. [1]" in lead["text"] and "fired.” [2]" in lead["text"]
    # The second section's [1] was its own source; its [2] is the lead's first source again.
    assert "Check the receipt. [3] The tick wrote one. [1]" in receipts["text"]
    assert "Retry once, then stop. [4][5]" in retries["text"]


def test_a_mark_nothing_defines_is_left_as_words_and_never_borrows_a_number():
    retries = model(OLD)["sections"][2]
    assert not re.search(r"\[9\]", retries["text"]) and "[9​]" in retries["text"]


def test_sources_and_drawn_from_leave_the_text_and_drawn_from_stays_with_its_section():
    result = model(OLD)
    assert [s["title"] for s in result["sections"]] == ["", "Receipts after the due time", "Retries"]
    assert all("Sources" not in s["text"] and "Drawn from" not in s["text"] and "codex:" not in s["text"] for s in result["sections"])
    assert [len(s["drawn"]) for s in result["sections"]] == [2, 1, 0]
    assert result["sections"][1]["drawn"] == ["[Receipts](../decisions/receipts.md)"]


def test_the_alias_line_is_taken_out_of_the_text():
    result = model(OLD)
    assert result["aka"] == ["Checking a tick"]
    assert "Also known as" not in result["sections"][0]["text"]


def test_a_quoted_line_becomes_a_quote_block_with_its_mark():
    lead = model(OLD)["sections"][0]["text"]
    assert "\n\n> “The calendar trigger never fired.” [2]" in lead


def test_a_page_with_one_sources_block_keeps_the_numbers_it_was_written_with():
    result = model(NEW)
    assert [s["n"] for s in result["sources"]] == ["2", "7"]
    assert "possible. [2]" in result["sections"][0]["text"] and "linear. [7]" in result["sections"][1]["text"]
    assert [len(s["drawn"]) for s in result["sections"]] == [1, 1]


def test_a_principles_inline_drawn_from_is_one_block_and_the_closing_line_stays_text():
    result = model(PRINCIPLE)
    section, = result["sections"]
    assert section["drawn"] == ["[Tick](./tick.md): the calendar lied.", "[Login](./login.md): the status lied."]
    assert "Pattern: measure the behaviour." in section["text"] and "Reach for it when" in section["text"]
    assert "Drawn from" not in section["text"] and result["sources"] == []
