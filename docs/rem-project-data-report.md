# REM project data — implementation and evidence report

Date: 2026-11-08. Branch: `sprint9/project-data`; HEAD descends from
`origin/release/1.9.3rc60`. No commits made. Owner notebook was read-only.

## Dataset discrepancy — target validation is incomplete

The three design briefs describe 43 projects and 145 open items in
`rem-trials/v192b3-all-fixes-codex-luna-180d-20261010`. On this machine,
`/home/onion/.co/rem` is a real directory (not that symlink) containing **5 project
pages and 29 project obligations**. A directory-name search under `/home/onion`
found no copy of the named trial. The owner was asked for its location.

Consequently **accuracy on the requested 145 items is unavailable**. The figures
below are measured against the available 29 items and must not be presented as
145-item results. Fifteen samples cannot be supplied for a class with zero items;
no synthetic samples are substituted into the real-data report.

The audit read Markdown projects/people/orgs/sessions and 81 cited retained
contexts, then applied the pure in-memory projection with date 2026-11-08.
No mail was sent, no notebook or state file was changed, and nothing was merged.
The five available project pages name local repository paths or Unknown, with
no canonical GitHub slug. No live issue count was invented for them. The read-only
gh adapter is independently tested with fictional paginated responses.

## Final real-data counts

| Kind | Count | Available samples below |
|---|---:|---:|
| owed | 0 | 0 |
| waiting | 0 | 0 |
| agent | 29 | 15 |
| answerable | 0 | 0 |

Manual AI inspection of all 29 page obligations agrees that they are owner-to-agent
instructions or requests to verify agent work: **29/29 direction-label agreement
on this available dataset**. This is an in-session qualitative audit, not a blind
human benchmark. It tests only the agent class; precision/recall for the other
three classes is not measurable here. It does not establish whether the work is
still open in the outside world. One pre-fix item was wrongly labelled owed
because an organisation was mentioned as a publishing destination; the final
rule checks the addressee, and a fictional regression now covers that error.

| Project | Open | Priority | Score | Health | Started | Last activity |
|---|---:|---:|---:|---|---|---|
| Codex ACP web control | 0 | 0 | 0 | quiet | 2026-08-11 | 2026-08-12 |
| Projects workspace | 17 | 4 | 4.5 | on_track | 2026-08-09 | 2026-10-25 |
| short-term-rental-agent | 5 | 4 | 4.5 | at_risk | 2026-08-17 | 2026-10-01 |
| social-media-management-skills | 4 | 4 | 4.5 | on_track | 2026-05-31 | 2026-10-15 |
| wr | 3 | 4 | 2.5 | on_track | unknown | 2026-11-07 |

## Real samples (original text and citation)

### owed — 0 total

No available items; cannot provide 15 real samples.

### waiting — 0 total

No available items; cannot provide 15 real samples.

### agent — 29 total

1. **Projects workspace** — 2026-10-25 — The user asked: “我的意思是，预览啊，我要看正式的 Co email open 的那个页面。我想看看 10 分钟拆了，或者你那个已经设计好的页面。 我就想看看我们当前这个 agent email 账号真实的邮箱记录之类的。” [25] — outcome unknown.

   Rule: owner instruction to a coding session or named agent. Source: `codex:01a16bf2-b40c-7140-bd65-a95ee8949ad2:29358398-8f449370`; page `projects/projects-ccabcb4080.md`.

2. **Projects workspace** — 2026-10-25 — The user asked: “这个域名是不是不对啊 你重新检查一下看一下吧” [24] — outcome unknown.

   Rule: owner instruction to a coding session or named agent. Source: `codex:01a16bf2-b40c-7140-bd65-a95ee8949ad2:29263744-805cdda3`; page `projects/projects-ccabcb4080.md`.

3. **Projects workspace** — 2026-10-25 — The user asked: “可能是辽宁那边的话 搞一个新 PR 合并到主分支 然后发一个新的预览版本吧” [23] — outcome unknown.

   Rule: owner instruction to a coding session or named agent. Source: `codex:01a16bf2-b40c-7140-bd65-a95ee8949ad2:28176206-fb25f1c4`; page `projects/projects-ccabcb4080.md`.

4. **Projects workspace** — 2026-10-24 — The user asked: “你用当前的邮箱登录一下，和后端联合调试，保证后端和前端的联动是正常的。后端的 API 和命令行里的 email 是一样的，所以应该可以复用。” [21] — outcome unknown.

   Rule: owner instruction to a coding session or named agent. Source: `codex:01a16bf2-b40c-7140-bd65-a95ee8949ad2:5154194-1ddbd888`; page `projects/projects-ccabcb4080.md`.

5. **Projects workspace** — 2026-10-24 — The user asked: “另外，顺便把命令行里面有些没有实现的功能，全部都实现一下吧。” [21] — outcome unknown.

   Rule: owner instruction to a coding session or named agent. Source: `codex:01a16bf2-b40c-7140-bd65-a95ee8949ad2:5154194-1ddbd888`; page `projects/projects-ccabcb4080.md`.

6. **Projects workspace** — 2026-10-24 — The user asked: “你持续的研究啊 然后把把这个项目给做一做” about the underwater follow-camera concept and a crowdfunding plan [22] — outcome unknown.

   Rule: owner instruction to a coding session or named agent. Source: `codex:01a16cca-9a89-7f23-a7cf-b567781c3830:1526771-541e1c90`; page `projects/projects-ccabcb4080.md`.

7. **Projects workspace** — 2026-10-21 — The user asked: “既然安卓端我们默认用的就是 Codex，所以你把这个研究一下，然后做一下吧。” about using Codex's built-in schedule for REM [14][15] — outcome unknown.

   Rule: owner instruction to a coding session or named agent. Source: `codex:01a15c1c-a8e1-78b3-870a-1110295566ef:91167-b041a6a5`; page `projects/projects-ccabcb4080.md`.

8. **Projects workspace** — 2026-10-15 — The user asked: “然后我要保证所有的 skills，所有 video 的 skills，我们都一个一个全部都放到我们的个人仓库里面，然后 system link 链接到本地的仓库里面，然后 commit push。” [13] — outcome unknown.

   Rule: owner instruction to a coding session or named agent. Source: `codex:01a04a19-6ae2-7102-b735-bf9ab1fa0db3:499405093-8cf4175b`; page `projects/projects-ccabcb4080.md`.

9. **Projects workspace** — 2026-10-10 — The user requested sustained iteration toward production quality: “然后对比一下音乐、节奏等，看看哪一个综合效果是最好的。” [11] — outcome unknown.

   Rule: owner instruction to a coding session or named agent. Source: `codex:01a12338-635b-7e12-8c4b-da4bf4e12f05:78651-80467e11`; page `projects/projects-ccabcb4080.md`.

10. **Projects workspace** — 2026-10-07 — The user asked: “添加一些 skills” and supplied prompt-motion.com [10] — outcome unknown.

   Rule: owner instruction to a coding session or named agent. Source: `codex:01a04a19-6ae2-7102-b735-bf9ab1fa0db3:481188225-2f723e0d`; page `projects/projects-ccabcb4080.md`.

11. **Projects workspace** — 2026-09-26: Review and improve property scrapers, check recent inventory and regional coverage, and consider broader Sydney coverage and Airbnb-suitable properties [29][30].

   Rule: session source with no human counterparty. Source: `codex:01a0375a-b6c1-7532-9502-f9de0cdc67ee:9020514`; page `projects/projects-ccabcb4080.md`.

12. **Projects workspace** — 2026-09-22: Review crawler failures, including HouGarden Sydney’s reported 1,920 readable listings with zero passing, and inspect logs after each run; a separate phone-number collection script was also suggested [31].

   Rule: session source with no human counterparty. Source: `codex:01a0375a-b6c1-7532-9502-f9de0cdc67ee:6488668`; page `projects/projects-ccabcb4080.md`.

13. **Projects workspace** — 2026-09-10: Develop the camera accessory concept around the preferred owl direction, matching camera-like eyes, accurate fit, safe attachment and quick release; physical validation and later manufacturing remain under discussion [7][32].

   Rule: session source with no human counterparty. Source: `codex:01a08340-3e19-7340-a5c9-c254cf358249:156857713`; page `projects/projects-ccabcb4080.md`.

14. **Projects workspace** — 2026-09-10: Continue developing and checking the Studio bot workflow for video and article tasks; the user requested end-to-end tests, but the supplied messages do not report their results [33].

   Rule: owner instruction to a coding session or named agent. Source: `codex:01a089d5-4e04-7cd2-99c5-c8abee2552ed:3625100`; page `projects/projects-ccabcb4080.md`.

15. **Projects workspace** — 2026-08-15 to 2026-09-09: Improve reusable live-video editing templates and skills, including framing, subtitles, transitions, sound, quality checks and repeatable workflows [34][35].

   Rule: session source with no human counterparty. Source: `claude-code:6ae0dda3-6461-4b29-be0e-012278668d45:32867201`; page `projects/projects-ccabcb4080.md`.


### answerable — 0 total

No available items; cannot provide 15 real samples.

## Rules and contract

The exact ordered classification rules, score constants, priority thresholds,
state format, source conventions, health decisions and date/tree limitations are
in [rem-project-data.md](rem-project-data.md). The implementation is Python only;
the existing reader snapshot receives new fields and retains its other fields.
Project `last_activity` now means evidence of activity, not investigation/file
mtime. Views must handle missing dates, zero priority and suggestions explicitly.

Schema per project: `{priority, score, reasons, health, health_reason, kind_counts,
parent, same_as, promised, started, last_activity}`, plus `open`, `date_sources`,
`pinned`, and all existing fields. `open` and `kind_counts` also cover people/orgs.
No answerable item is automatically closed; no suggested duplicate is merged.

## Red → green evidence

- Initial missing-module run: **1 collection error**; initial implementation:
  **13 passed** (`/tmp/rem-project-red.log`, `/tmp/rem-project-green.log`).
- Human names, historical answers, milestone health, retained issues and parent
  citations: **5 failed, 14 passed** before fixes.
- Closed invoices, task-scoped mail promises and exact deadline evidence:
  **6 failed, 16 passed** before the combined fixes.
- Reader integration/regression checkpoint: **386 passed in 29.02s**
  (`/tmp/rem-project-targeted.log`).
- Organisation mentions and unresolved blockers: **2 failed, 22 passed**, then
  **24 passed**.
- Task/date-specific answers: **1 failed, 26 passed**, then **27 passed**.
- Grouped source IDs and named component parents: **2 failed, 27 passed**, then
  **29 passed**.
- Review counterexamples (date digits as quantity, pronoun matching unrelated
  mail): **2 failed, 29 passed** before fixes; **31 passed in 4.25s** after fixes (`/tmp/rem-project-green6.log`).

All test fixtures use fictional people/projects. No owner names were copied into
source code or tests.

## Independent review

A separate AI reviewer applied the product/technology-founder perspective required
by AGENTS.md. Coverage: data contracts and fictional scenarios only; **no rendered
desktop/mobile UI was changed or reviewed**. This is not a real human founder review.

High-priority findings were false answerable classifications, named-human direction,
missed GitHub milestone risk, closed-invoice money pressure, and unrelated mail
deadlines. Medium-priority findings were role/deadline/tree citation provenance.
Each has a behavioral regression and a fix. The second pass independently ran the
29-test checkpoint and raised the final two boundary regressions listed above.
The final independent recheck confirmed both boundary counterexamples are fixed and found no remaining P1 issue in those reviewed scenarios. The requested 145-item audit remains the material validation gap.

## Census compatibility regression

The first complete full-suite run exposed one introduced regression: the project
projection dropped the existing mapped Last seen date. Red-first coverage also
caught broader session times overriding an explicit project Last activity fact.
The fix preserves mapped activity and gives explicit scoped activity precedence,
while still rejecting file/investigation times as project activity.

The independent reviewer verified the date fix and independently reran both new date regressions: **2 passed in 7.47s**; no significant issue in that scope.

Red: **3 failed, 31 passed** (`/tmp/rem-project-dates-red.log`). Green: **414 passed in 33.10s** across all new tests and the reader/census regressions (`/tmp/rem-project-final-targeted.log`).

## Full unit suite

Exact requested command:

```sh
uv run --quiet --python 3.13 --extra dev python -m pytest -q -p no:cacheprovider tests/unit -n 8 --dist=worksteal 2>&1 | grep -E "^FAILED|passed|failed"
```

The existing `tests/unit/test_rem_map.py::test_map_keeps_an_existing_document_page_reused_by_attribution`
fails because attribution creates a new page instead of reusing
`projects/documents.md`. It reproduces independently on an untouched `git archive
HEAD` export under `/tmp/rem-project-baseline`: **1 failed in 7.75s**
(`/tmp/rem-project-baseline-test.log`). The map implementation is not changed by
this task. This is a pre-existing failure, not a passing full-suite claim.

The remaining 14 failures from that run also reproduce on the clean HEAD archive:
**14 failed, 144 passed, 1 warning in 32.27s**
(`/tmp/rem-project-baseline-regressions.log`). They cover project identity/material
attribution (9), terminal styling/discovery (4), and host SIGHUP shutdown (1).
The baseline census test passes. Combined with the independently confirmed map
failure, this establishes **15 pre-existing failures**; the introduced census
regression was fixed before the final run.

The final run also exposed
`test_rem_investigate.py::test_scoped_sessions_reuse_disk_window_and_find_new_input`:
it assumes an ordering of filesystem reads. It fails identically in isolation on
the working branch (**1 failed in 5.59s**) and clean HEAD (**1 failed in 5.65s**),
recorded in `/tmp/rem-project-session-window-current.log` and
`/tmp/rem-project-session-window-baseline.log`. Thus **all 16 final failures are
independently reproduced on unchanged baseline code**. The suite is not green;
the introduced census regression is fixed, and the focused reader/census suite
is green.

Exact last line from the final requested command:

```text
16 failed, 18546 passed, 20 skipped, 2948 warnings in 1114.03s (0:18:34)
```
