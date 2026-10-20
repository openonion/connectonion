"""An invented notebook shaped like a real one, for the reader's design and browser tests.

Every person, company, project and source id here is made up. The pages follow
the templates the investigation stages write (rem-page-person, -project, -org,
-skill): a cited lead, Contact fields, Open threads naming who owes whom, a
dated History, numbered Sources, an ASCII Overview, a skill's Usage history.
Run logs are written relative to `now`, so "last night" is always last night.
"""

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from connectonion.rem.config import prepare
from connectonion.rem.files import Notebook


def _day(now: datetime, days_ago: int) -> str:
    return (now - timedelta(days=days_ago)).strftime("%Y-%m-%d")


def _people(now: datetime) -> dict:
    d = lambda n: _day(now, n)  # noqa: E731
    mara = f"""# Mara Ostrowski

You owe Mara the signed data-sharing addendum — 9 days [4]. She runs partnerships at [Fernhill Labs](../orgs/fernhill-labs.md) and is your main contact for the pilot [1][2]; she owes you the pilot's usage export [5]. Last contact: {d(1)} [6].

## Facts
- Email: mara@fernhill.example (work); mara.ostrowski@mailbox.example (personal) [1]
- Phone: Unknown
- Company: [Fernhill Labs](../orgs/fernhill-labs.md) [2]
- Role: Head of Partnerships [2]
- Location: Wellington, New Zealand [2]
- Time zone: Unknown
- Links: https://fernhill.example/team/mara [2]
- How we know them: She asked for a pilot after the user's meetup talk on agent memory [3]
- First contact: {d(40)} [3]
- Last contact: {d(1)} [6]
- Signing entity: Unknown
- Handles: mara@fernhill.example
- Language: English; Polish (with colleagues) [3]
- Also known as: M. Ostrowski

## Insight
- Now: the pilot's renewal depends on two things you each owe the other [4][5].
- At stake: the renewal call at the end of the quarter, and a possible fourth seat [6].
- Changed: she moved from feedback calls to asking about expansion in five weeks [4][6].
- Pattern: she sets a deadline in the subject line and follows up within four days [4][5][6].

## Who they are
- Head of Partnerships at Fernhill Labs, a twelve-person climate-data startup in Wellington [2].

## Why they are here
- She approached the user after a meetup talk on agent memory and asked for a pilot of co rem inside Fernhill's research team [3].

## Our relationship
- A paid pilot since {d(40)}: three seats, monthly invoice, renewal decision due at the end of the quarter [3][4]. She is direct, quick to escalate, and generous with feedback.

## History
- {d(40)}: pilot agreed; three seats from the following Monday [3].
- {d(26)}: first feedback call; asked for a shared notebook per team [4].
- {d(9)}: sent the data-sharing addendum for signature [4].
- {d(4)}: promised the usage export "by Friday" [5].
- {d(1)}: asked whether the renewal could include a fourth seat [6].

## Open threads
- **Data-sharing addendum** — the user has not signed it; with the user since {d(9)} [4].
- **Usage export** — she promised it by Friday ({d(4)}); unanswered since [5].

## How they communicate
- Short emails, bullet points, a deadline in the subject line [4][5].

## How the user writes to them
- Warm and brief; the user answers within a day [6].

## Cadence
- Roughly weekly, more often near invoices [4][6].

## Uncertainties
- Whether the fourth seat is budgeted or a wish.
- The fourth seat budget is unknown [6].

## Sources
- [1] outlook:5c1e0a9b72d4 — address and signature; confidence high; observed {d(40)}.
- [2] outlook:9a03f1c2be77 — title and company in signature; confidence high; observed {d(40)}.
- [3] outlook:1b77de0c4f12 — how the pilot began; confidence high; observed {d(40)}.
- [4] outlook:e4a2c1907bd3 — addendum sent for signature; confidence high; observed {d(9)}.
- [5] outlook:77c09ad1e3f0 — export promised by Friday; confidence high; observed {d(4)}.
- [6] gmail:0f9be4c12a55 — fourth-seat question; confidence high; observed {d(1)}.

Investigation: mapped {d(41)} · investigated {d(0)} (outlook, gmail)
"""
    tomas = f"""# Tomás Reyes

Tomás is a former colleague who now reviews the user's conference talks [1]. Nothing open as of {d(3)}; next contact expected before the November deadline [2]. Last contact: {d(3)}, email [2].

## Contact
- Email: tomas.reyes@mailbox.example [1]
- Phone: Unknown
- Company: Unknown
- Role: Programme committee, Agents Summit [2]
- Language: Spanish; English for reviews [1]

## Our relationship
- Friendly and informal; he reads drafts, the user returns the favour [1].

## History
- {d(60)}: reviewed the user's spring talk [1].
- {d(3)}: confirmed he will review the next abstract [2].

## Open threads
- Nothing open as of {d(3)}; the next abstract goes to him before the November deadline [2].

## Sources
- [1] gmail:a1c3e5f7b9d2 — reviews and language; confidence medium; observed {d(60)}.
- [2] gmail:c4e6a8b0d2f1 — confirmation; confidence high; observed {d(3)}.

Investigation: mapped {d(70)} · investigated {d(2)} (gmail)
"""
    ines = f"""# Inès Halvorsen

Inès is the accountant who files the user's company returns [1]. Last contact: {d(12)}, email [1].

## Contact
- Email: ines@ledgerline.example [1]

## Open threads
- She is waiting on the user for the Q3 receipts; the user has owed them since {d(12)} and she files the return by {d(-2)} [1].

## Sources
- [1] outlook:3d5f7b9e1a0c — receipts request; confidence high; observed {d(12)}.

Investigation: mapped {d(30)} · written {d(12)}
"""
    owner = f"""# Avery Lin

This is you: an independent engineer building agent tools, with one paying pilot and two talks this autumn [1]. Last contact: {d(0)} [1].

## Facts
- Email: avery@lin.example [1]
- Phone: +64 21 555 0142 (mobile) [1]
- Company: Unknown
- Role: Independent engineer [1]
- Location: Wellington, New Zealand [1]
- Time zone: Pacific/Auckland [1]
- Links: https://lin.example [1]
- How we know them: Unknown
- First contact: Unknown
- Last contact: {d(0)} [1]

## Insight
- Now: this month you shipped Harbour's nightly read and wrote two talk abstracts [2].
- At stake: two people are waiting on you, the oldest for twelve days [3].

## Sources
- [1] outlook:aa11bb22cc33 — signature; confidence high; observed {d(30)}.
- [2] codex:dd44ee55ff66 — sessions this month; confidence high; observed {d(1)}.
- [3] investigation:page — open threads across pages; confidence medium; observed {d(0)}.

Investigation: mapped {d(60)} · investigated {d(0)} (outlook, codex)
"""
    return {"people/avery-lin.md": owner, "people/mara-ostrowski.md": mara, "people/tomas-reyes.md": tomas, "people/ines-halvorsen.md": ines}


def _projects(now: datetime) -> dict:
    d = lambda n: _day(now, n)  # noqa: E731
    harbour = f"""# Harbour

## What it is
- A command-line tool that turns a team's shared inbox into a weekly brief, built for Fernhill's pilot [1].

## Overview
Mail is read once a night, grouped by thread, and summarised into one brief per team [1][2].

```text
 shared inbox ──read──> threads ──group──> team briefs
      │                                        │
      └──── attachments ──> extract ──┐        v
                                      └──> weekly brief ──> email
```

## Where it stands
- Observed {d(1)}. The nightly read and the grouping work on the pilot inbox; the brief still repeats long threads [2][3].
- Two of three pilot users opened last week's brief [3].

## Open threads
- Decide whether long threads are cut or summarised; the user owes Mara an answer before the renewal call [3].
- Waiting on Fernhill for a second test inbox; promised {d(6)} [4].

## Key decisions
- **{d(20)}:** one brief per team, not per person, to keep the email short [2].

## Paths
- /home/user/code/harbour [1]
- Sessions: 31
- First seen: {d(45)}
- Last seen: {d(1)}

## Sources
- [1] codex:7e1f0a2b3c4d — repository README; confidence high; observed {d(45)}.
- [2] claude-code:1a2b3c4d5e6f — design session; confidence high; observed {d(20)}.
- [3] outlook:9f8e7d6c5b4a — pilot feedback; confidence medium; observed {d(2)}.
- [4] outlook:4b5a6c7d8e9f — test inbox promised; confidence high; observed {d(6)}.

Investigation: mapped {d(45)} · investigated {d(0)} (codex, claude-code, outlook)
"""
    lantern = f"""# Lantern

## What it is
- A static site generator for the user's essays.

## Paths
- /home/user/code/lantern
- Sessions: 4
- Last seen: {d(33)}

Investigation: mapped {d(33)} · not investigated yet
"""
    return {"projects/harbour.md": harbour, "projects/lantern.md": lantern}


def _skill(name: str, count: int, last: str, what: str, mapped: str) -> str:
    usage = (f"- Invoked {count} times in your coding sessions in the last 180 days (412 session files: Codex, Claude Code), "
             f"last on {last} (Claude Code {count}). Counted by co rem from Skill tool calls.") if count else \
        "- No invocation found in your coding sessions in the last 180 days (412 session files: Codex, Claude Code)."
    return f"""# {name}

## What it does
{what}

## When to use
Unknown — not investigated yet

## Usage history
<!-- rem-usage -->
{usage}
<!-- /rem-usage -->

## Source
<!-- rem-installed-copies -->
- File: /home/user/.claude/skills/{name}/SKILL.md
- Discovery: claude-user
<!-- /rem-installed-copies -->

Investigation: mapped {mapped} · not investigated yet
"""


def _orgs_and_skills(now: datetime) -> dict:
    d = lambda n: _day(now, n)  # noqa: E731
    fernhill = f"""# Fernhill Labs

A climate-data startup in Wellington; the user's first paying pilot [1].

## Domains
- fernhill.example [1]

## Who they are
- Twelve people; research and data engineering [1].

## People here
- [Mara Ostrowski](../people/mara-ostrowski.md) — Head of Partnerships; owns the pilot [1]

## Open threads
- Renewal decision due at the end of the quarter; the user should send a proposal first [2].

## Sources
- [1] outlook:2c4e6a8b0d1f — signature and website; confidence high; observed {d(40)}.
- [2] outlook:6e8a0c2e4f6b — renewal timing; confidence high; observed {d(5)}.

Investigation: mapped {d(41)} · investigated {d(5)} (outlook)
"""
    pages = {"orgs/fernhill-labs.md": fernhill,
             "decisions/notebook-format.md": "# Notebook format\n\nPages stay Markdown so they can be read without co rem.\n"}
    for name, count, last, what in [("weekly-brief", 14, 1, "Write the Friday brief from the week's notebook changes."),
                                    ("invoice-check", 3, 9, "Check an invoice against the contract before it is sent."),
                                    ("talk-outline", 0, 0, "Turn an abstract into a talk outline with timings.")]:
        pages[f"skills/catalog/{name}.md"] = _skill(name, count, d(last), what, d(20))
    return pages


def _runs(now: datetime) -> list[dict]:
    """A week of nightly passes: quiet nights, one that stopped early, and last night's."""
    runs = []
    week = [(6, 12, [], "completed"), (5, 0, [], "completed"), (4, 31, ["projects/harbour.md"], "completed"),
            (3, 40, [], "failed"), (2, 18, ["people/tomas-reyes.md"], "completed"), (1, 9, [], "completed")]
    for days_ago, items, changed, outcome in week:
        start = (now - timedelta(days=days_ago)).replace(hour=3, minute=0, second=0, microsecond=0)
        runs.append({"started_at": start.isoformat(), "finished_at": (start + timedelta(minutes=14)).isoformat(),
                     "outcome": outcome, "items": items, "changed": changed, "sources": ["outlook", "gmail"],
                     "usage": {"input_tokens": 41000 * (items // 10 + 1), "output_tokens": 3100}, "seconds": 840})
    start = now - timedelta(hours=5)
    runs.append({"started_at": start.isoformat(), "finished_at": (start + timedelta(minutes=22)).isoformat(),
                 "outcome": "completed", "items": 46, "sources": ["outlook", "gmail", "codex"],
                 "changed": ["people/mara-ostrowski.md", "projects/harbour.md", "orgs/fernhill-labs.md"],
                 "claim_changes": [{"record": "people/mara-ostrowski.md", "field": "role",
                                    "before": "Partnerships lead", "after": "Head of Partnerships",
                                    "sources": ["2"], "kind": "revised record"}],
                 "usage": {"input_tokens": 212000, "output_tokens": 9400}, "seconds": 1320})
    return runs


def _chinese_pages(now: datetime) -> dict:
    """Cached prose translations; source lines and investigation stamps stay canonical."""
    d = lambda n: _day(now, n)  # noqa: E731
    return {
        "people/mara-ostrowski.md": f'''# Mara Ostrowski

你还欠 Mara 一份签好的数据共享补充协议，已过 9 天 [4]。她负责 [Fernhill Labs](../orgs/fernhill-labs.md) 的合作事务，也是试点的主要联系人 [1][2]；她还欠你试点的用量导出 [5]。最近联系：{d(1)} [6]。

## Facts
- Email: mara@fernhill.example (work); mara.ostrowski@mailbox.example (personal) [1]
- Phone: Unknown
- Company: [Fernhill Labs](../orgs/fernhill-labs.md) [2]
- Role: 合作负责人 [2]
- Location: 新西兰惠灵顿 [2]
- Time zone: Unknown
- Links: https://fernhill.example/team/mara [2]
- How we know them: 你在聚会上分享智能体记忆后，她提出开展试点 [3]
- First contact: {d(40)} [3]
- Last contact: {d(1)} [6]
- Signing entity: Unknown
- Handles: mara@fernhill.example
- Language: 英语；与同事交流时用波兰语 [3]
- Also known as: M. Ostrowski

## Insight
- Now: 试点能否续约，取决于你们各自欠对方的两件事 [4][5]。
- At stake: 季末的续约通话，以及可能增加的第四个席位 [6]。
- Changed: 五周内，她从反馈使用体验转向询问扩容 [4][6]。
- Pattern: 她会在邮件主题中写明截止日期，并在四天内跟进 [4][5][6]。

## Who they are
- Fernhill Labs 的合作负责人；这家位于惠灵顿的气候数据初创公司有十二名成员 [2]。

## Why they are here
- 你在聚会上分享智能体记忆后，她主动联系，希望在 Fernhill 的研究团队中试用 co rem [3]。

## Our relationship
- 从 {d(40)} 开始的付费试点：三个席位，按月开票，季末决定是否续约 [3][4]。她沟通直接，遇到问题会迅速提出，也很乐于反馈。

## History
- {d(40)}: 确认试点，从下周一开始使用三个席位 [3]。
- {d(26)}: 第一次反馈通话；提出让团队共用一个笔记本 [4]。
- {d(9)}: 发来数据共享补充协议，请你签署 [4]。
- {d(4)}: 承诺在 "by Friday" 前提供用量导出 [5]。
- {d(1)}: 询问续约时能否增加第四个席位 [6]。

## Open threads
- **数据共享补充协议** — 你还没签；从 {d(9)} 起等你处理 [4]。
- **用量导出** — 她承诺周五（{d(4)}）前提供；仍未回复 [5]。

## How they communicate
- 邮件简短，使用要点，主题中写明截止日期 [4][5]。

## How the user writes to them
- 语气温和、简短；你通常在一天内回复 [6]。

## Cadence
- 大约每周联系，临近开票时更频繁 [4][6]。

## Uncertainties
- 第四个席位是否已有预算，还是仅有意向。
- 第四个席位的预算尚不清楚 [6]。
''',
        "people/ines-halvorsen.md": f'''# Inès Halvorsen

Inès 是负责申报你公司报表的会计 [1]。最近联系：{d(12)}，邮件 [1]。

## Contact
- Email: ines@ledgerline.example [1]

## Open threads
- 她在等你提供第三季度的收据；从 {d(12)} 起尚未交齐，她将在 {d(-2)} 前报税 [1]。
''',
        "people/avery-lin.md": f'''# Avery Lin

这是你：一名开发智能体工具的独立工程师，有一个付费试点，今年秋天有两场演讲 [1]。最近联系：{d(0)} [1]。

## Facts
- Email: avery@lin.example [1]
- Phone: +64 21 555 0142 (mobile) [1]
- Company: Unknown
- Role: 独立工程师 [1]
- Location: 新西兰惠灵顿 [1]
- Time zone: Pacific/Auckland [1]
- Links: https://lin.example [1]
- How we know them: Unknown
- First contact: Unknown
- Last contact: {d(0)} [1]

## Insight
- Now: 本月你上线了 Harbour 的夜间读取功能，并写了两份演讲摘要 [2]。
- At stake: 两个人在等你，最久的一位已等了十二天 [3]。
''',
        "orgs/fernhill-labs.md": '''# Fernhill Labs

一家位于惠灵顿的气候数据初创公司，也是你的第一个付费试点客户 [1]。

## Domains
- fernhill.example [1]

## Who they are
- 十二名成员；从事研究和数据工程 [1]。

## People here
- [Mara Ostrowski](../people/mara-ostrowski.md) — 合作负责人；负责试点 [1]

## Open threads
- 季末决定是否续约；你应先发一份方案 [2]。
''',
        "projects/harbour.md": f'''# Harbour

## What it is
- 一款将团队共享收件箱整理成每周简报的命令行工具，为 Fernhill 的试点开发 [1]。

## Overview
每晚读取一次邮件，按会话分组，为每个团队汇总成一份简报 [1][2]。

```text
 shared inbox ──read──> threads ──group──> team briefs
      │                                        │
      └──── attachments ──> extract ──┐        v
                                      └──> weekly brief ──> email
```

## Where it stands
- 观察于 {d(1)}。夜间读取和会话分组已能处理试点收件箱；简报仍会重复较长的会话 [2][3]。
- 三位试点用户中，有两位打开了上周的简报 [3]。

## Open threads
- 决定长会话要截短还是概括；你欠 Mara 一个答复，需在续约通话前给出 [3]。
- 等 Fernhill 提供第二个测试收件箱；承诺于 {d(6)} [4]。

## Key decisions
- **{d(20)}:** 每个团队一份简报，而非每人一份，让邮件保持简短 [2]。

## Paths
- /home/user/code/harbour [1]
- Sessions: 31
- First seen: {d(45)}
- Last seen: {d(1)}
''',
    }


def build(root: Path, now: datetime | None = None, zh: bool = False) -> Path:
    """Write the invented notebook at root and return it."""
    now = now or datetime.now(timezone.utc)
    prepare(root)
    notebook = Notebook(root)
    pages = {**_people(now), **_projects(now), **_orgs_and_skills(now)}
    for record, text in pages.items():
        notebook.write(record, text)
    if zh:
        from connectonion.rem import translate
        for record, prose in _chinese_pages(now).items():
            original = notebook.read(record)
            translated = prose.rstrip() + "\n\n## Sources" + original.partition("\n## Sources")[2]
            path = translate.translation_path(root, record, "zh")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f"<!-- co rem translation of {record} sha256:{translate.digest(original)} -->\n" + translated, encoding="utf-8")
    notebook.stub_person("people/quinn-alder.md", "Quinn Alder", handles=["quinn@alder.example"])
    notebook.stub_person("people/noor-bakhtiar.md", "Noor Bakhtiar", handles=["noor@bakhtiar.example"])
    # The map's correspondent rows: where the People table's mail columns come from.
    mail = [("mara@fernhill.example", "people/mara-ostrowski.md", 38, 21, 41, 1), ("tomas.reyes@mailbox.example", "people/tomas-reyes.md", 6, 4, 60, 3),
            ("ines@ledgerline.example", "people/ines-halvorsen.md", 9, 2, 30, 12), ("quinn@alder.example", "people/quinn-alder.md", 3, 2, 20, 15),
            ("noor@bakhtiar.example", "people/noor-bakhtiar.md", 2, 1, 50, 44)]
    rows = [{"address": address, "record": record, "name": record, "mails": sent + received, "sent": sent, "received": received,
             "first": _day(now, first), "last": _day(now, last), "one_way": False}
            for address, record, received, sent, first, last in mail]
    (root / ".state").mkdir(exist_ok=True)
    other = [{"address": "leah@old-friends.example", "name": "Leah Bell", "mails": 1,
              "sent": 1, "received": 0, "last": _day(now, 610)},
             {"address": "ivy@fieldwork.example", "name": "Ivy Chen", "mails": 1,
              "sent": 0, "received": 1, "last": _day(now, 390)},
             {"address": "hello@single-note.example", "name": "", "mails": 1,
              "sent": 1, "received": 0, "last": _day(now, 950)}]
    (root / ".state" / "map.json").write_text(json.dumps({
        "people": rows, "without_page": other, "all_history": True,
        "automated_correspondents": [{"address": "notice@robot.example"}],
        "owner": {"record": "people/avery-lin.md", "languages": {"languages": ["zh", "en"] if zh else ["en"], "english_terms": []}}}))
    runs = root / ".state" / "runs"
    runs.mkdir(parents=True, exist_ok=True)
    for i, run in enumerate(_runs(now)):
        run["id"] = f"run_{i:032x}"
        (runs / f"{run['id']}.json").write_text(json.dumps(run))
    # An invented archived conversation exercises source and thread drilldown.
    # Other fixture citations deliberately have no archived body.
    from connectonion.rem.store_build import SCHEMA, SCHEMA_VERSION
    evidence = root / ".state" / "evidence"
    evidence.mkdir()
    messages = [
        ("outlook:e4a2c1907bd3", "Mara", _day(now, 9), "Please sign the addendum before the renewal call."),
        ("outlook:77c09ad1e3f0", "Mara", _day(now, 4), "I will send the usage export by Friday."),
        ("gmail:0f9be4c12a55", "Mara", _day(now, 1), "Could the renewal include a fourth seat?"),
    ]
    with sqlite3.connect(root / ".state" / "rem.db") as db:
        db.executescript(SCHEMA)
        db.execute("insert into meta (key, value) values ('schema_version', ?)", (SCHEMA_VERSION,))
        for number, (source, sender, day, body) in enumerate(messages):
            path = evidence / f"message-{number}.json"
            provider, native = source.split(":", 1)
            path.write_text(json.dumps({"provider": provider, "id": native, "body": body,
                                       "body_format": "provider-rendered text, not original MIME"}))
            db.execute("insert into messages (id, source, thread, sender, recipients, time, subject, body_path) "
                       "values (?, ?, ?, ?, ?, ?, ?, ?)",
                       (source, source.split(":")[0], "mail:fixture:harbour-renewal", sender,
                        json.dumps(["Avery"]), day + "T09:00:00+00:00", "Harbour renewal", str(path.relative_to(root / ".state"))))
    return root
