# Release channels

ConnectOnion has two release channels:

- **Stable** is the default `pip install connectonion` channel for production.
- **Preview** contains opt-in alpha, beta, and release-candidate builds.

Preview releases never replace the stable recommendation. Install one by
pinning the exact version shown below. The pin alone lets pip take that one
preview. Do not add `--pre`: it applies to
every dependency too, and under it 1.8.8b7 resolved httpx 1.0.dev6, which has
no `AsyncClient`, and every remote agent call crashed.

## Unreleased fixes

- `co browser import` reads Chrome's encrypted cookies as bytes even when SQLite
  stores them as TEXT. Target-cookie replies are scoped to one imported domain
  at a time, including subdomains and all paths, so unrelated cookies no longer
  overflow the OIP frame limit. If a target read fails, the command says
  "nothing was written" and stops before loading any cookies ([#2887](https://github.com/openonion/connectonion/issues/2887)).

## Current preview

Release candidate **1.9.7rc25**: privacy: a private relation reason, and any page line drawn outside the passage renderer, is curtained at 遮敏感 like a passage, so no raw [sensitive]/[personal] token or private reason shows; on rc24 a person page's 提到它的页面 card showed a private reason's words and its raw mark, and citation words showed a bare mark (#3427, #3425). See [1.9.7rc25 notes](releases/1.9.7rc25.md).
Before it, release candidate **1.9.7rc24**: a queued page says its place in the night's queue and the pace the night really keeps, and says 今晚 only when it falls inside tonight's run (#3421, #3420); a Today card's time says 已过 once it passes, with a countdown before it and job titles that read as titles, and an organisation's website and connection reasons say only what is true (#3423, #3422). See [1.9.7rc24 notes](releases/1.9.7rc24.md).
Before it, release candidate **1.9.7rc23**: privacy: a line that opens with a privacy mark is curtained in place at 遮敏感 in every section kind; on rc22 such a line showed in full with its raw mark, and a Chinese reader says its own labels in Chinese and shows a page's English as its original (#3416, #3410); once the fix for a stuck page is installed, Today and status say the next round skips it, in local time, over one night window (#3414, #3413); the owner's side of a client organisation is found from what real pages say, so 你这边对接的人 appears on real client orgs (#3415, #3397). See [1.9.7rc23 notes](releases/1.9.7rc23.md).
Before it, release candidate **1.9.7rc22**: a tag or search view never scrolls sideways: a privacy curtain's cap is a length, not a width (#3407, #3404); Today says when before how old, says each event once, and fits a phone without a caption running off the card (#3408, #3406, #3379); a facts card keeps a short value whole and its labels speak Chinese (#3409, #3405). See [1.9.7rc22 notes](releases/1.9.7rc22.md).
Before it, release candidate **1.9.7rc21**: a draft the page check refused says the page is unchanged, in the owner's words, and what happens next from the night's own retry ledger: 今晚会再试一次, or 已暂停 after N tries (#3398, #2235); one night, one count: Today's 昨夜 heading adds up the curve's own stretches, the side line says 待办, and the Codex line no longer sounds like one task both running and stopped (#3399, #3396); an organisation's connections give the line that links the pair, or say plainly which page names which, and the owner's own people are no longer drawn inside a client's org tree (#3400, #3397); a job that can never be prepared is set aside and the round goes on: a skill page whose skill is no longer installed stopped every background round from 06:15, and Today now says when one error keeps stopping the night (#3403, #3402). See [1.9.7rc21 notes](releases/1.9.7rc21.md).
Before it, release candidate **1.9.7rc20**: the tag-page title never carries a privacy mark: a page check refuses one, the page build moves an old mark onto the page's passages once, and a masked page reads 个人事项 1, 2 …, numbered once in the order it was first masked (#3386, #3385); course and team codes read 课程 3900 / 团队 … wherever an organisation's name shows (#3389, #3388); a mail Outlook or Gmail says is gone is asked for once more a day later, then the night stops waiting and says so instead of promising 会再试 (#3393, #3392); Today's night curve carries the whole night, not the last 21 runs, a stuck stretch keeps its own caption and the axis ends after the last run (#3394, #3391). See [1.9.7rc20 notes](releases/1.9.7rc20.md).
Before it, release candidate **1.9.7rc19**: the night's sleep curve tells the truth: a parked or stuck stretch draws as 清醒, captioned 卡住 N 分钟 · 已自动跳过, and the phone names the highest level the night reached; the desk title counts what the cards show (#3382, #3379); an uninvestigated WeChat friend's facts card no longer prints the raw WeChat id and says the rest comes with investigation (#3381, #3372); the upgrade backfill is versioned, so the retitle and the first/last-chat fields reach notebooks already backfilled on rc17 (#3380, #3368). See [1.9.7rc19 notes](releases/1.9.7rc19.md).
Before it, release candidate **1.9.7rc18**: the night can no longer loop on one task: a tag page that cannot be tagged alone waits instead of raising after the others were written, and a scheduled next parks a task whose input changed (#3377, #3376); Today opens with the night as a sleep curve, the night's work under it and one primary action per card (#3371); a WeChat-only person page says when you last talked, the 90-day count and who wrote last, with the raw WeChat id moved into ⋯ (#3374, #3372); the People filters are labelled 来源 and 标签 and course codes read as names (#3373); `co wechat` and `co rem` help speak to the AI that runs them (#3361). See [1.9.7rc18 notes](releases/1.9.7rc18.md).
Before it, release candidate **1.9.7rc17**: WeChat works on an upgraded notebook without waiting for a night run: the first page build backfills each source's chat activity and onboarding record, `co rem map` records them like the night, status counts the pages a source already holds, punctuation-only WeChat names fall back to the remark or 微信好友（无名字 · …1234）, and the People row marks only the minority source (#3369, #3368). See [1.9.7rc17 notes](releases/1.9.7rc17.md).
Before it, release candidate **1.9.7rc16**: REM gets faster and WeChat-complete: the same-person check and the whole-notebook scans run once per build (`co rem status` ~20 s → ~11 s on 1,352 people, #3365); every WeChat friend gets a page, chats are read from the full-text index too, and the People table counts WeChat activity, folds friends without recent chats and labels the id 微信 (#3357, #3346); a wrong-channel reply is rewritten on the thread's own channel and full screen holds send until it is (#3358); every source reports its coverage and Today names what REM can't read with one button (#3354, #3356); opening the reader no longer asks for translation status (#3352); one token sheet for states and motion (#3362); 3D graph fit and search refinements (#3342). See [1.9.7rc16 notes](releases/1.9.7rc16.md).
Before it, release candidate **1.9.7rc15**: the agent's page is the Control Center everywhere: `.co/control_center.html` (an existing `dashboard.html` is still served, with a rename hint), the `CONTROL_CENTER_SNAPSHOT` frame (the old frame name is sent alongside for one preview cycle) and the `control-center` skill ([#3336](https://github.com/openonion/connectonion/issues/3336)). See [1.9.7rc15 notes](releases/1.9.7rc15.md).
Before it, release candidate **1.9.7rc14**: owner-facing text names pages, not raw `[[…md]]` paths, and the breadcrumb is only as wide as its text ([#3338](https://github.com/openonion/connectonion/pull/3338)); the knowledge graph is alive — 3D in the live reader, a live draggable 2D graph on phone ([#3330](https://github.com/openonion/connectonion/pull/3330)); 不是人 works on WeChat-only people from the ⋯ menu, and the map and the night honour it ([#3341](https://github.com/openonion/connectonion/pull/3341)). See [1.9.7rc14 notes](releases/1.9.7rc14.md).
Before it, release candidate **1.9.7rc13**: adding a source onboards it — `co rem map [people|orgs|projects] --source NAME [--dry-run]` builds pages from one source with no model, each source declaring the kinds it yields ([#3334](https://github.com/openonion/connectonion/pull/3334)); `co rem sources add` maps it at once, the night re-maps WeChat and new or widened local sources, and per-source status shows in `co rem sources` / `co rem status` ([#3335](https://github.com/openonion/connectonion/pull/3335)). See [1.9.7rc13 notes](releases/1.9.7rc13.md).
Before it, release candidate **1.9.7rc12**: the Keys page lists the vault grouped by site (above 30 keys every site folds to one row with its count, searchable, a two-line list on phone) and co's own keys grouped by service with settings folded ([#3327](https://github.com/openonion/connectonion/pull/3327)); tags render as quiet chips on every page kind ([#3313](https://github.com/openonion/connectonion/pull/3313)). See [1.9.7rc12 notes](releases/1.9.7rc12.md).
Before it, release candidate **1.9.7rc11**: the Today reply card and its full-screen compose, rebuilt to one spec: one filled 发送, the letter in full, a line naming the message REM read, ‹ i/n ›, honest channels (a draft on a channel the person is not on is refused and offered 改写成邮件), send states with undo and retry, and a full screen with × top-right and clickable open questions ([#3324](https://github.com/openonion/connectonion/pull/3324)). See [1.9.7rc11 notes](releases/1.9.7rc11.md).
Before it, release candidate **1.9.7rc10**: the Keys page imports with one 一键导入 (Chrome, Edge, Brave, the macOS Keychain, Apple Passwords via its CSV export, or a CSV), shows a waiting step while the system asks to 允许, and says why when the REM Host cannot show that prompt; co's own keys from `~/.co/keys.env` are listed by name ([#3316](https://github.com/openonion/connectonion/pull/3316)). See [1.9.7rc10 notes](releases/1.9.7rc10.md).
Before it, release candidate **1.9.7rc9**: `co discord` as your own account (experimental), a system Chrome fallback that keeps other sessions' tabs, a bare `co host` that no longer stops serving silently, and `co call` that names the address it signed with. See [1.9.7rc9 notes](releases/1.9.7rc9.md).
Before it, release candidate **1.9.7rc8**: rc7's reworded topic link reviews no longer re-ask the stored ones; the stale path questions migrate to page titles ([#3292](https://github.com/openonion/connectonion/pull/3292)). See [1.9.7rc8 notes](releases/1.9.7rc8.md).
Before it, release candidate **1.9.7rc7**: a reader polish batch (record pages open at one width, a project page's "in Today" opens the filtered Waiting view, calendar titles clamp, the empty Keys page leads with one-click import, a topic link review names the page not its file path) and the WeChat upgrade fix — an existing install's stale wechat source now implies consent once keys are captured, and seeding matches the reader's gate, so the night both seeds and fills WeChat people. See [1.9.7rc7 notes](releases/1.9.7rc7.md).
Before it, release candidate **1.9.7rc6**: WeChat as a co rem source that seeds people into the map and the night. See [1.9.7rc6 notes](releases/1.9.7rc6.md).
Before it, release candidate **1.9.7rc5**: the Control Center has an admin section, shown only to admins: who joined, Remove/Block, rotate the invite without a restart, activity, health and the log. See [1.9.7rc5 notes](releases/1.9.7rc5.md).
Before it, release candidate **1.9.7rc4**: WeChat as a co rem source, and one-click key import from Chrome/Edge/Brave. See [1.9.7rc4 notes](releases/1.9.7rc4.md).
Before it, release candidate **1.9.7rc3**: `restricted: env` passes named Host variables to the tools, and the caller as `CO_CALLER_ADDRESS` / `CO_CALLER_TRUST`. See [1.9.7rc3 notes](releases/1.9.7rc3.md).
Before it, release candidate **1.9.7rc2**: `co wechat` reads WeChat 4.1 for Mac with one command to get the keys; bare `co wechat` lists your chats. See [1.9.7rc2 notes](releases/1.9.7rc2.md).
Before it, release candidate **1.9.7rc1**: a restricted claude-code Host from host.yaml, no silent co/ model, `co obsidian`
and `co asana`. See [1.9.7rc1 notes](releases/1.9.7rc1.md).

```bash
python -m pip install --upgrade 'connectonion==1.9.7rc25'
```

## Current release

Stable **1.9.6** is the default production channel. `co init` starts the Host and leaves it running on
macOS, Linux and Windows, and the model is one line in host.yaml: `model: claude-code` answers through
your logged-in Claude Code with no API key. REM gets the new desk, a knowledge graph, three privacy
levels and hand-offs you can watch; `co send` / `co receive` move files between agents; `co wechat`
reads your own WeChat for Mac history locally. See [1.9.6 notes](releases/1.9.6.md) and the
[GitHub release](https://github.com/openonion/connectonion/releases/tag/v1.9.6).

```bash
python -m pip install --upgrade 'connectonion==1.9.6'
```

## Previous stable

Stable **1.9.5**: A fresh install works again (typer 0.29.0
broke every `co` command; it is capped below 0.29); REM reads each slot's mail while the Codex weekly
floor holds investigation work; nothing in the reader asks you to copy a command. See
[1.9.5 notes](releases/1.9.5.md) and the
[GitHub release](https://github.com/openonion/connectonion/releases/tag/v1.9.5).

Stable **1.9.4** was a hotfix on 1.9.3, in which the first
`co rem open` after upgrading from 1.9.3rc64 could wait minutes for a rebuild. The reader now never
waits on a build; a saved page opens at once marked "Updating…". See
[1.9.4 notes](releases/1.9.4.md) and the
[GitHub release](https://github.com/openonion/connectonion/releases/tag/v1.9.4).

## Previous previews

The candidates for 1.9.6:

Release candidate **1.9.6rc48**: REM related cards drop the writer's prefix; the page foot says Copy the file path. See [1.9.6rc48 notes](releases/1.9.6rc48.md).
Before it, release candidate **1.9.6rc47**: on a phone, a linked page named by a long question wraps instead of widening the page. See [1.9.6rc47 notes](releases/1.9.6rc47.md).
Before it, release candidate **1.9.6rc46**: a Windows background Host counts as running only when it answers, and a Host the relay refuses stops with the reason. See [1.9.6rc46 notes](releases/1.9.6rc46.md).
Before it, release candidate **1.9.6rc45**: on a phone, Today no longer zooms out when a finished hand-off has a long summary; a `claude-code` Host names a missing Claude login. See [1.9.6rc45 notes](releases/1.9.6rc45.md).
Before it, release candidate **1.9.6rc44**: global `co init` on Windows from an elevated shell starts a working Host, `claude-code` by default when it is logged in. See [1.9.6rc44 notes](releases/1.9.6rc44.md).
Before it, release candidate **1.9.6rc43**: the Windows logon Host starts when co was set up from an elevated shell. See [1.9.6rc43 notes](releases/1.9.6rc43.md).
Before it, release candidate **1.9.6rc42**: rc39 to rc41, published. See [1.9.6rc42 notes](releases/1.9.6rc42.md).
Before it, release candidate **1.9.6rc41** (tagged, not published): See [1.9.6rc41 notes](releases/1.9.6rc41.md).
Before it, release candidate **1.9.6rc40** (tagged, not published): rc39's changes, published, plus `co init` that skips the background Host on Linux
without a systemd user session. See [1.9.6rc40 notes](releases/1.9.6rc40.md).
Before it, release candidate **1.9.6rc39** (tagged, not published): `co init` starts the Host on macOS, Linux and Windows, and `model: claude-code` in
host.yaml answers through your logged-in Claude Code. See [1.9.6rc39 notes](releases/1.9.6rc39.md).
Before it, release candidate **1.9.6rc38**: REM's rc36 bug-hunt fixes: one header across person, organisation and project pages that says each fact once, organisation names that are never a code or a bare domain, a 不是人 control that moves an assistant out of People, dates in their own sentence's language, no stray space or lowercase after a hidden passage, words at the 13px floor, hex ids left whole inside links, Today that shows an event under way as now and a repeated code error as a bug an update fixes, writers that never call an organisation 实体, and translate and tag that go on past the Codex floor up to a small ceiling. See [1.9.6rc38 notes](releases/1.9.6rc38.md).
Before it, release candidate **1.9.6rc37**: a hotfix: scheduled REM turns that reach a tag page are served again, instead of crashing in `_source_view` and leaving the night empty since rc35. See [1.9.6rc37 notes](releases/1.9.6rc37.md).
Before it, release candidate **1.9.6rc36**: REM's rc35 bug-hunt fixes: web sources open with their page, Today's side column never
pushes the page sideways, the phone agenda folds deadlines into one line per day, a worded translation count, privacy
curtains that flow inside a sentence and a terminal that hides private text, and the remaining dates and hex ids said
once. See [1.9.6rc36 notes](releases/1.9.6rc36.md).
Before it, release candidate **1.9.6rc35**: REM's rc34 bug-hunt fixes: an open tab survives an upgrade and lands on the new build, Today's first screen
shows the next events, facts and dates said once, dates in the reader's own form, raw ids as named chips, a compact top
bar, and night stages that drain. See [1.9.6rc35 notes](releases/1.9.6rc35.md).
Before it, release candidate **1.9.6rc34**: REM's knowledge graph (a tag links pages and gets its own page), a closed item
that stays closed, three privacy levels that cover every place a passage shows, and the bug hunt's fixes. See
[1.9.6rc34 notes](releases/1.9.6rc34.md).
Before it, release candidate **1.9.6rc33**: `co wechat` reads your own WeChat for Mac history locally (read-only) — a
SQLCipher-4 decryption engine with `doctor`, `key`, `chats`, `decrypt` and `export`. See
[1.9.6rc33 notes](releases/1.9.6rc33.md).
Before it, release candidate **1.9.6rc32**: `co browser` starts headless on a Windows machine with no desktop (SSH,
services, scheduled tasks). See [1.9.6rc32 notes](releases/1.9.6rc32.md).
Before it, release candidate **1.9.6rc30**: hand-offs you can watch and pick up, enrich that writes career timelines and
links organisations, one language control, and a person page that leads with what happened. See
[1.9.6rc30 notes](releases/1.9.6rc30.md).
Before it, release candidate **1.9.6rc29**: a source's title opens its original in the side card, a calendar event shows
its meeting link, organiser and notes, and the Investigate popovers float over the page. See
[1.9.6rc29 notes](releases/1.9.6rc29.md).
Before it, release candidate **1.9.6rc28**: REM's night runs again, Investigate appends to long pages by archiving their
oldest History, the live reader recovers by itself after an upgrade, and a person's reply policy is one click.
See [1.9.6rc28 notes](releases/1.9.6rc28.md).
Before it, release candidate **1.9.6rc27**: the person page's header and profile card are redesigned: three lines under
the name, one action column, and every fact one line with its sources a hover away. See
[1.9.6rc27 notes](releases/1.9.6rc27.md).
Before it, release candidate **1.9.6rc26**: REM sprint 22. Send on a Today reply always answers, full-screen writing is
back in sight, a person's profile card comes first, full memory opens with a short named sources band, and
`co rem investigate` appends to an existing page with one Investigate button on record pages. See
[1.9.6rc26 notes](releases/1.9.6rc26.md).
Before it, release candidate **1.9.6rc25**: a Windows PC can run `co host` and answer `co call`. See [1.9.6rc25 notes](releases/1.9.6rc25.md).
Before it, release candidate **1.9.6rc24**: `co whatsapp` works on Windows: `check` and `consume` run beside a live listener,
incoming messages are kept, and `consume` replies in UTF-8. See [1.9.6rc24 notes](releases/1.9.6rc24.md).
Before it, release candidate **1.9.6rc23**: `co whatsapp listen --phone <number>` links a device with an 8-character code
typed on the phone, instead of a QR that has to be seen. See [1.9.6rc23 notes](releases/1.9.6rc23.md).
Before it, release candidate **1.9.6rc22**: when `co browser keyboard_type` cannot paste, as in headless Chrome on Windows over
SSH, the whole text goes in through CDP in one call, and the result says how it went in. See
[1.9.6rc22 notes](releases/1.9.6rc22.md).
Before it, release candidate **1.9.6rc21**: when `co send` cannot reach the receiver directly, a file of up to 10 MB waits on the
server for 7 days, encrypted to the receiver, and `co receive` there takes it; `co browser keyboard_type` pastes text
in one event instead of typing it key by key. See [1.9.6rc21 notes](releases/1.9.6rc21.md).
Before it, release candidate **1.9.6rc20**: REM's night workers run at the configured reasoning effort, `co rem catchup` and the
scheduled turn can no longer work one notebook at the same time, and a worker turn that times out parks its page
instead of ending the night. See [1.9.6rc20 notes](releases/1.9.6rc20.md).
Before it, release candidate **1.9.6rc19**: `co send` sends files to another agent byte for byte, verified by sha256, and
an interrupted send continues from where it stopped; `co receive` lists what arrived. See [1.9.6rc19 notes](releases/1.9.6rc19.md).
Before it, release candidate **1.9.6rc18**: a page whose preparation passes the ten-minute deadline is parked and the
next call serves other work, a turn that only stalled is no longer recorded as completed, and a person's page no
longer reads every coding-session log again. See [1.9.6rc18 notes](releases/1.9.6rc18.md).
Before it, release candidate **1.9.6rc17**: a session that names a folder REM may not read no longer stops every
background round, and a round that could not be prepared is recorded as failed. See [1.9.6rc17 notes](releases/1.9.6rc17.md).
Before it, release candidate **1.9.6rc16**: the Organisations table never prints the not-investigated placeholder as a
fact, a company's page renders, and long locations clamp to two lines. See [1.9.6rc16 notes](releases/1.9.6rc16.md).
Before it, release candidate **1.9.6rc15**: the Organisations table shows its tree expanded, «Talk it over» shows its
conversation, facts on people and projects are corrected, and the reader's Chrome suite is green. See [1.9.6rc15 notes](releases/1.9.6rc15.md).
Before it, release candidate **1.9.6rc14**: the REM reader shows organisations as a sortable table and a page that reads
like a book, keeps one Knowledge place, and opens Projects on a board by state. See [1.9.6rc14 notes](releases/1.9.6rc14.md).
Before it, release candidate **1.9.6rc13**: a Host records every automatic run in `co approvals`, and a revoked
requester's turn stops before its next step even after they disconnect. See [1.9.6rc13 notes](releases/1.9.6rc13.md).
Before it, release candidate **1.9.6rc12**: `co whatsapp` connects again on a fresh install (neonize 0.10.0;
WhatsApp refused the old client), reads a group's history when the account is added to it, and
`co whatsapp download <id>` fetches older media. See [1.9.6rc12 notes](releases/1.9.6rc12.md).

Before it, release candidate **1.9.6rc11**: in the REM reader, People opens on a sortable table, Ignore is a word on
every open row, Agenda is a calendar of your saved events, and one button translates every page. See
[1.9.6rc11 notes](releases/1.9.6rc11.md).

Before it, release candidate **1.9.6rc10**: the default model is `co/gemini-4-hydrogen`, the cheapest Gemini 4
model. Name `co/gemini-3.8-flash` to roll back. See [1.9.6rc10 notes](releases/1.9.6rc10.md).

Before it, release candidate **1.9.6rc9**: REM's night goes on when one mailbox fails and says why on Today; Today
has one count and one primary action per card; record pages lead with open threads; drafts, the reader
and translation agree on your language. See [1.9.6rc9 notes](releases/1.9.6rc9.md).

Before it, release candidate **1.9.6rc8**: `co server new` charges the first month of a server now and each next
month as it starts, and `co server destroy` refunds the unused part with a credit note. rc7 described
the other way round and cannot create a server. See [1.9.6rc8 notes](releases/1.9.6rc8.md).

Before it, release candidate **1.9.6rc7**: every Today row in the REM reader closes with Mark done, Not now and
Ignore in words, and Ignore can keep an advertiser out of Today for good. Records carry real names,
record pages show the record, and the Skills page fits on one screen. See
[1.9.6rc7 notes](releases/1.9.6rc7.md).

Before it, release candidate **1.9.6rc6**: in the REM reader, Mark done sits with the other row actions and one
button switches the reader between 中文 and English. After an upgrade the reader is served by the
installed version: the old Host co rem started is replaced on its port when nothing is running. See
[1.9.6rc6 notes](releases/1.9.6rc6.md).

Before it, release candidate **1.9.6rc5**: the REM reader's rail names every place under its picture (Today,
Waiting on you, People, Organisations, Projects, Skills, All records), Skills has its own place on it, and
REM has its own mark and tab icon. See [1.9.6rc5 notes](releases/1.9.6rc5.md).

Before it, release candidate **1.9.6rc4**: in the REM reader, Done, Undo and Skip reach the notebook however
much mail it holds, and a refused mark says "Not saved". Organisations, Projects, All records and
Skills load while REM builds a newer reader. See [1.9.6rc4 notes](releases/1.9.6rc4.md).

Before it, release candidate **1.9.6rc3**: on macOS co's own WTF Browser start and a double-click share one
profile and one Keychain, so a login made in either works in both (sign in once in the app; old
logins are not moved). On a phone the Send bar sits on the tab bar. See
[1.9.6rc3 notes](releases/1.9.6rc3.md).

Before it, release candidate **1.9.6rc2**: the REM reader's new desk, phase 1 of 3. An icon rail and one search
pill on a desktop, a floating tab bar on a phone; Today opens on a night chart, the count of people
waiting and one raised reply card; a person's record is a card with their face and a grid of what REM
knows. Lists and the other records keep their old layouts until phases 2 and 3. Before it,
**1.9.6rc1** made Today's open reply show whole lines on a desktop and start on screen on a phone.
Stable remains **1.9.5**. See [1.9.6rc2 notes](releases/1.9.6rc2.md) and
[1.9.6rc1 notes](releases/1.9.6rc1.md).

Release candidate **1.9.5rc1**: nothing in the reader asks you to copy a command any more; a page that
waited while you typed says "Updates waiting" and keeps your words; a headless `co claude run`
edits files in its folder by default. See [1.9.5rc1 notes](releases/1.9.5rc1.md).

Stable **1.9.3** is the default production channel. REM does the work: overnight it reads new
mail, drafts the replies you owe and runs the tasks you approved through `co claude` or Codex; in
the reader any unfinished item can be handed to Codex or Claude, or talked over with them in a
conversation that resumes the agent's own session. Replies to people you trust can go through a
10-minute hold, and `co rem open` serves the last page at once. See
[1.9.3 notes](releases/1.9.3.md) and the
[GitHub release](https://github.com/openonion/connectonion/releases/tag/v1.9.3).

Release candidate **1.9.3rc64** is the candidate for stable 1.9.3: owed tasks run through `co claude` or Codex with Hand to Codex / Hand to Claude on every pending item, direct send for people you trust, no count caps, translation into the languages you write, four model levels, a designed morning email, and a reader that opens at once in the Fuse design. Before it, **1.9.3rc63** is 1.9.3rc62 republished: rc62 was tagged but never published, because its release workflow's coverage leg ran past its time limit. Before it, **1.9.3rc62** (tagged, never published) keeps REM reading new mail at every slot and through the night, lets replies to people you trust go through the 10-minute hold, makes Today a front page of who waits and what REM did, gives projects a timeline, list and board, adds a knowledge graph with topic pages and an opt-in morning message; approved owed work is recorded but not run in this version. Before it, **1.9.3rc61** redesigns Today as one card per person with one statement and one green action, a Cmd-K palette and keyboard keys; makes organisation and person pages records of who they are, leaving to-dos to Today; and adds topics, named weekly by the summary model and filed only on evidence. Before it, **1.9.3rc60** makes the night round give every owed item an outcome, adds Approve all with a 10-minute hold, dispatches owed work to Codex with receipts, redesigns People, Organisations, Projects and Sessions, and runs REM on the top model with only summaries on the small one. Before it, **1.9.3rc59** was a hotfix on 1.9.3rc58: the claim audit completes when a cited original is not in the archive, naming the unverified citation instead of retrying forever (#2879). Before it, **1.9.3rc58** was a hotfix on 1.9.3rc57: a page task was refused on every retry because a mail source id had been rewritten to its digest form and the retention check compared spellings (#2877). Before it, **1.9.3rc57** was a hotfix on 1.9.3rc56 (tagged, never published: offline `co init` waited 80 s on npm): installer fallback stops when there is no network. Before it, **1.9.3rc56** makes Done and Skip decisions persist in the notebook, opens the reader before the whole notebook is parsed, gives dates and labels one plain grammar, ends overrunning scheduled turns with their process tree, and lets `co init` proceed without a browser login (#2861, #2864, #2865, #2870). Before it, **1.9.3rc55** (tagged, never published: its release workflow failed on a `co init` that waited for a browser login) made the reader's front page one queue of actions and shows each reply as the mail it becomes, drafted on a fixed skill in your own voice with the background beside it, with Send, a full-screen writer and a channel switch (#2861, #2862); it also carries attachments, browser history, relationship statistics, run memory, tidy, the sessions page and `co init` installing Codex (#2844). Before it, **1.9.3rc54** was a hotfix: on 1.9.3rc53 every scheduled `codex exec` turn stopped at its first mail read because Codex's sandbox blocked the network; turns now run with network access. Before it, **1.9.3rc53** ran scheduled REM on macOS through `codex exec`, so one session keeps working across a round, lets `co init` set REM up without questions, and fills basic contact facts from the mail itself (#2844, #2856). Before it, **1.9.3rc52** kept scheduled REM working after its saved time: 15-minute follow-ups continue the pending task, refusals say exactly what to fix, and schedule changes no longer invalidate a pending task (#2814). Before it, **1.9.3rc51** made REM investigations research beyond the mailbox (web search, `co browser`, `gh`, Feishu) and lead each page with what they found (#2810), keeps the native schedule from losing a slot while `co rem next` prepares (#2812), and limits mailbox consent to `--mail` (#2809). Before it, **1.9.3rc50** replaced real people's names and addresses in tests, docs and examples with fictional ones and adds a test that keeps them out (#2804); there is no behaviour change. Before it, **1.9.3rc49** closed the remaining REM audit items before stable: a run whose PID was reused after a reboot no longer shows as running, dates follow the notebook's zone, page merges keep their sections, and sync, status and the guide say what actually happened (#2802, #2803). Before it, **1.9.3rc48** made `co rem doctor` name an install command that fixes the running co, keeping a uv tool's companion packages (#2798), and steadies the macOS release checks (#2797). Before it, **1.9.3rc47** stopped old translations from holding the native REM schedule: a new scheduled slot logs an old round's untranslated pages as skipped and starts reading new material, where before one translation per slot kept new mail and sessions waiting for days (#2794). Before it, **1.9.3rc46** gave REM a background schedule on Linux: `co rem start` installs a systemd user timer that runs `co rem sync --scheduled` every five minutes, where before it stopped with "macOS-only" after the first batch and no slot ever ran (#2790). Before it, **1.9.3rc45** made the native REM schedule survive a cold start: the wake job opened Codex hidden and a hidden Codex runs no automations, so every slot was missed until the window was shown; it now opens Codex visible but not in front (#2785). A scheduled `co rem next` that stops at the daily cap now leaves a run record, so `co rem logs` shows the slot was visited (#2786), and the `co rem` help pages were rewritten plainly after `co audit --review` (#2782). Users on rc44 or earlier with the native schedule run `co rem start` once after upgrading. Before it, **1.9.3rc44** made the native REM path work on a real notebook: `co rem submit` accepts what `co rem next` prepared, because later-in-thread mail is now ordered deterministically instead of following each process's hash seed (#2778). Before it, **1.9.3rc43** was a hotfix: on 1.9.3rc42, `co rem tidy`, every scheduled sync and `co rem next` stopped at once on a notebook whose pages link to a path outside notebook content; tidy now leaves such links alone (#2773). Before it, **1.9.3rc42** carried the four pre-stable audit fixes (#2754, #2771): scheduled-round writes wait for the lock, the daily cap is "daily cap reached" rather than a failure, the same-person stage charges the week once, archives are never overwritten; and `co rem logs` reads a dead run as interrupted (#2770). Before it, **1.9.3rc41** made the first run honest and short: a one-screen consent summary, an estimate that follows the material and says Nothing to write yet on an empty map, skip reasons for sessions, and `co rem show NAME` across every page kind (#2765, #2766). Before it, **1.9.3rc40** ran one scheduled REM sync at a time (a second tick says busy and keeps its slot) and lets the same-person stage skip a page that vanished (#2763). Before it, **1.9.3rc39** let the native Codex Scheduled session do REM's work itself (`co rem next` / `co rem submit`, #2756) and makes a scheduler error at the end of `co init` a one-line message with a launchd fallback (#2759). Before it, **1.9.3rc38** made `co init` set REM up in one go: mailbox offer, one consent question, upkeep installed and named, then the first notebook after a pause at the estimate; `--yes` and non-tty runs create storage only, `--no-rem` skips it (#2755). Before it, **1.9.3rc37** made stopping `co host` stop the agent: on macOS and
Linux `co host` becomes `agent.py`, so no orphan is left holding the port. Stable
remains **1.9.2**.

See [the candidate notes](releases/1.9.3rc64.md), [1.9.3rc63](releases/1.9.3rc63.md), [1.9.3rc62](releases/1.9.3rc62.md), [1.9.3rc61](releases/1.9.3rc61.md) and [1.9.3rc60](releases/1.9.3rc60.md).

Release candidate **1.9.3rc36** lets a scheduled REM run that Codex fires a few
minutes early serve its slot. Stable remains **1.9.2**.

After publication, install its exact pin:

```bash
python -m pip install --upgrade 'connectonion==1.9.3rc36'
```

See [the candidate notes](releases/1.9.3rc36.md).

Release candidate **1.9.3rc35** counts REM's same-person judgements like every
other model call, and lets a pair that fails wait a day. Stable remains **1.9.2**.

After publication, install its exact pin:

```bash
python -m pip install --upgrade 'connectonion==1.9.3rc35'
```

See [the candidate notes](releases/1.9.3rc35.md).

Release candidate **1.9.3rc34** folds REM people pages that are one person: code
finds lookalike pages and a model decides from both pages and their own mail.
Stable remains **1.9.2**.

After publication, install its exact pin:

```bash
python -m pip install --upgrade 'connectonion==1.9.3rc34'
```

See [the candidate notes](releases/1.9.3rc34.md).

Release candidate **1.9.3rc33** opens a closed Codex desktop 15 minutes before each
scheduled REM run, so an early-firing slot is no longer missed. Stable remains **1.9.2**.

After publication, install its exact pin:

```bash
python -m pip install --upgrade 'connectonion==1.9.3rc33'
```

See [the candidate notes](releases/1.9.3rc33.md).

Release candidate **1.9.3rc32** keeps the REM owner's own page current: the daily
round now refreshes it once a day from what they sent. Stable remains **1.9.2**.

After publication, install its exact pin:

```bash
python -m pip install --upgrade 'connectonion==1.9.3rc32'
```

See [the candidate notes](releases/1.9.3rc32.md).

Release candidate **1.9.3rc31** adds Outlook drafts (`--draft`, `co outlook drafts`,
`send-draft`, `delete-draft`), keeps REM pages free of filler hedges, and opens
business-card sources from their citations. Stable remains **1.9.2**.

After publication, install its exact pin:

```bash
python -m pip install --upgrade 'connectonion==1.9.3rc31'
```

See [the candidate notes](releases/1.9.3rc31.md).

Release candidate **1.9.3rc30** makes REM pages say only what their sources say:
related-page cards keep their own citations, translations keep their Sources,
quote checks keep word boundaries, overdue items stay overdue, and a name shared
by several people picks none. Stable remains **1.9.2**.

After publication, install its exact pin:

```bash
python -m pip install --upgrade 'connectonion==1.9.3rc30'
```

See [the candidate notes](releases/1.9.3rc30.md).

Release candidate **1.9.3rc29** keeps paid WTF Browser sessions on macOS alive
past their first fifteen-minute period: the runtime now asks for Chromium
154.0.8037.100, which renews every period. Linux stays on 154.0.8037.58.
Stable remains **1.9.2**.

After publication, install its exact pin:

```bash
python -m pip install --upgrade 'connectonion==1.9.3rc29'
```

See [the candidate notes](releases/1.9.3rc29.md).

Release candidate **1.9.3rc28** repairs REM's sync rotation and native
schedule. A failed source is recorded and the round continues with the next one;
a queued message deleted from the mailbox leaves the queue and is counted; Outlook
reads use immutable ids. A small launchd job opens a closed Codex desktop at each
saved REM time. Stable remains **1.9.2**.

After publication, install its exact pin:

```bash
python -m pip install --upgrade 'connectonion==1.9.3rc28'
```

See [the candidate notes](releases/1.9.3rc28.md).

Release candidate **1.9.3rc27** is a backend repair candidate for retained
quotation context and Claude loopback bridge startup. Literal words in an extended
quote require the same immediately bound originals to count as retained. Genuinely
missing introductory prose stays introductory. The scoped Claude Hook receiver
uses its numeric address without reverse DNS. No global DNS or permissions change.
Stable remains **1.9.2**. Matching public package and prerelease are required.

After publication, install its exact pin:

```bash
python -m pip install --upgrade 'connectonion==1.9.3rc27'
```

See [the candidate notes](releases/1.9.3rc27.md).

Release candidate **1.9.3rc26** repairs old REM investigation conversations in
Codex's active history and fixes initialization omissions. Approved REM startup
archives proven old internal traces through Codex's native API. Bundled skill
links into older installations are refreshed, incomplete profiles are repaired,
and malformed metadata reports an actionable error. Stable remains **1.9.2**.

```bash
python -m pip install --upgrade 'connectonion==1.9.3rc26'
```

See [the candidate notes](releases/1.9.3rc26.md).

Release candidate **1.9.3rc25** is the freeze candidate for 1.9.3: rc24 plus
one release-blocking fix. `co lark listen` no longer loses messages silently:
history recovery is bounded and runs only at start and reconnect, a rejected
conversation is skipped instead of stopping recovery, a message that reached
another client on the same app is reported by `co lark check`, and reactions,
recalls and group events reach the inbox. If rc25 holds up end to end it is
promoted unchanged to 1.9.3. Stable remains **1.9.2**.

Opt-in installation:

```bash
python -m pip install --upgrade 'connectonion==1.9.3rc25'
```

See [the candidate notes](releases/1.9.3rc25.md).


Release candidate **1.9.3rc24** froze the 1.9.3 line: after it, only
release-blocking fixes land. It adds the REM citation, translation, company-scope and
diary-folder privacy fixes merged after rc23, a macOS user service for
`co host`, and an error for `co email inbox --address` with an address you do
not own. Stable remains **1.9.2**.

```bash
python -m pip install --upgrade 'connectonion==1.9.3rc24'
```

See [the candidate notes](releases/1.9.3rc24.md).

Release candidate **1.9.3rc23** adds generic `co asr` and Python `asr()`.
Codex is the default provider; existing co configuration can select
ConnectOnion. Long files are prepared locally in resumable windows. Both
providers upload audio; the Codex endpoint is unofficial. No Watch connector
or automatic REM ingestion is included. Stable remains **1.9.2**.

```bash
python -m pip install --upgrade 'connectonion==1.9.3rc23'
```

See [the candidate notes](releases/1.9.3rc23.md) and
[ASR configuration and recovery](asr.md).

Release candidate **1.9.3rc22** activates Codex Scheduled after native registration
and confirms timer changes before handing off the old clock. Normal-profile
execution and automatic initialization after a desktop restart passed; newer
account-managed registration and exact requested-minute timing remain unverified.
All initialization entry points now repair the profile, skill links and command
index together. Stable remains **1.9.2**; Python **3.11+** is required.

```bash
python -m pip install --upgrade 'connectonion==1.9.3rc22'
```

See [the preview notes](releases/1.9.3rc22.md) and their acceptance boundaries.

Release candidate **1.9.3rc21** moves eligible Codex notebooks on macOS to
Codex desktop Scheduled, verifies registration before replacing the old clock,
and archives completed maintenance conversations. Other timezones, headless Macs
and other runners retain launchd. Keep the app open and computer awake.
Stable remains **1.9.2**; this preview requires Python **3.11+**.

```bash
python -m pip install --upgrade 'connectonion==1.9.3rc21'
```

See [the preview notes](releases/1.9.3rc21.md) and their native execution evidence.

Release candidate **1.9.3rc20** recognizes already-owned addresses during
repeat email setup even if that domain no longer accepts new purchases. It
retains multi-address setup, domain discovery, account-wide defaults and the
merged inbox. Stable remains **1.9.2**; Python 3.11+ is required.

```bash
python -m pip install --upgrade 'connectonion==1.9.3rc20'
```

See [the preview notes](releases/1.9.3rc20.md). Currently enabled choices come
from the cloud; unready reserved domains are not offered for new purchases.


Release candidate **1.9.3rc19** strengthens mailbox setup regression coverage:
no purchase after authentication/settings failures or for domains the backend
has not enabled. It includes rc18's multi-address setup and the corrected quota
examples. Stable remains **1.9.2**; Python 3.11+ is required.

```bash
python -m pip install --upgrade 'connectonion==1.9.3rc19'
```

See [the preview notes](releases/1.9.3rc19.md). At rc19 publication,
steadmail.com and oakinbox.com had not passed incoming delivery. They were
enabled after live tests on 2026-10-23; the cloud lists all four hosted domains.

Release candidate **1.9.3rc18** exposes hosted-domain discovery and setup of
additional email aliases on the same cloud account. It retains sender selection,
account defaults and mailbox filtering. Stable remains **1.9.2**.

```bash
python -m pip install --upgrade 'connectonion==1.9.3rc18'
```

See [the preview notes](releases/1.9.3rc18.md). Domain infrastructure acceptance
is recorded separately from package tests.

Release candidate **1.9.3rc17** processes eligible explicit feedback when
there is no new raw material, narrows inherited-claim audit exemptions and keeps
supplied argument names in tool error hints. Synthetic retry tests avoid real
waiting. Stable remains 1.9.2; Python 3.11+ and existing dependency floors remain.
This backend preview does not establish current REM model or native UI acceptance.
See [1.9.3rc17 notes](releases/1.9.3rc17.md).

After publication, install its exact pin:

```bash
python -m pip install --upgrade 'connectonion==1.9.3rc17'
```

Release candidate **1.9.3rc16** skips stale click-approach waypoints under slow
pointer dispatch, lets supervised local browser jobs pin their existing daemon, and
keeps isolated project Hosts from inheriting a global handoff watcher. This
preview requires Python 3.11+ and retains rc15's security dependency floors.
See [1.9.3rc16 notes](releases/1.9.3rc16.md).

After publication, install its exact pin:

```bash
python -m pip install --upgrade 'connectonion==1.9.3rc16'
```


Release candidate **1.9.3rc15** preserves file and image references, message kinds
and typed sender IDs through Feishu/Lark inbox consumption and Host input.
Recovery includes conversations remembered before an interrupted first journal
write. See [1.9.3rc15 notes](releases/1.9.3rc15.md).

Release candidate **1.9.3rc14** updates the optional Synology dependency to
Paramiko 5.1.0+ and audits all extras, retaining rc13 security and compatibility
requirements. See [1.9.3rc14 notes](releases/1.9.3rc14.md).

Release candidate **1.9.3rc13** archives REM's internal Codex calls while preserving
explicit resume and raises the Python floor to 3.11 with updated security
dependencies. See [1.9.3rc13 notes](releases/1.9.3rc13.md).

Release candidate **1.9.3rc12**: rounds keep what they had. A round keeps every quote the page
already had and repairs a dropped quote before it is refused; open threads say who owes whom and
keep overdue promises open; a dropped mail connection no longer stops the first run; the reader's
home is a morning brief with Copy prompt and Mark done; docs and blog posts use invented names
only. See [1.9.3rc12 notes](releases/1.9.3rc12.md).

```bash
python -m pip install --upgrade 'connectonion==1.9.3rc12'
```

Release candidate **1.9.3rc11**: upkeep keeps its quotes. Daily upkeep checks a rewrite against
the page it replaces and asks for dropped quotes back; pronoun repair only touches the owner; project
pages get a quote round; deepen weighs activity above emptiness; the reader shows pages in Chinese
after `co rem translate --all --to zh`. See
[1.9.3rc11 notes](releases/1.9.3rc11.md).

```bash
python -m pip install --upgrade 'connectonion==1.9.3rc11'
```

Release candidate **1.9.3rc10**: 1.9.3rc9 with one correction. The packaged handoff blog post
now tells its story with a fictional sender instead of a real person; the code is unchanged. See
[1.9.3rc10 notes](releases/1.9.3rc10.md).

```bash
python -m pip install --upgrade 'connectonion==1.9.3rc10'
```

Release candidate **1.9.3rc9**: pages that quote people. The quote floor, first contact, History
order and owner pronouns are enforced in code (mean quotes per person page 6.8 to 22.4 on notebook
copies); enrich reads long histories period by period; gathering at 16 workers is about twice as
fast; the reader shows quotes and the owner's language. A handoff pasted into a conversation about
other work now stops and asks for a new one. See [1.9.3rc9 notes](releases/1.9.3rc9.md).

```bash
python -m pip install --upgrade 'connectonion==1.9.3rc9'
```

Release candidate **1.9.3rc8**: a changed person or organisation without retained
routing continuity no longer regains the old subject's contact dates. The next
successful pass compacts the Investigation footer to the latest of each known
kind. These fixes do not repair old claims or establish reader maturity.
See [1.9.3rc8 notes](releases/1.9.3rc8.md). After publication:

```bash
python -m pip install --upgrade 'connectonion==1.9.3rc8'
```

Release candidate **1.9.3rc7**: REM excludes internal Windows task sessions from new
context imports, skill invocation counts and cached evidence samples. This prevents
model probes and repair instructions from being treated as the owner's words. It does
not purge old messages or repair existing claims. See [1.9.3rc7 notes](releases/1.9.3rc7.md).

After this candidate is published, install its exact pin:

```bash
python -m pip install --upgrade 'connectonion==1.9.3rc7'
```

Release candidate **1.9.3rc6**: a forwarded link no longer takes the name. A handoff addressed to
one agent's mailbox and accepted by another agent is saved under the acceptor's own name, the
addressed name keeps its own key, and names rc5 already re-pointed read as mail contacts again. See
[1.9.3rc6 notes](releases/1.9.3rc6.md).

```bash
python -m pip install --upgrade 'connectonion==1.9.3rc6'
```


Release candidate **1.9.3rc5**: handoffs are end-to-end encrypted. `send` seals the handoff on
your machine and the key travels after `#` in the link; after acceptance every message between the
two agents is boxed to the other's key. The backend holds ciphertext. See
[1.9.3rc5 notes](releases/1.9.3rc5.md).

Release candidate **1.9.3rc4**: enrich and muse, fixed. A Codex sub-agent finishing no longer
ends the main turn; enrich's ledger for a project page holds its coding sessions, GitHub issues and
pull requests and the git log, and the review gate accepts what the ledger lists. On a test project
page, enrich then muse took quotes from 3 to 15 and cited sources from 10 to 40. See
[1.9.3rc4 notes](releases/1.9.3rc4.md).

Release candidate **1.9.3rc3**: deepen one page. `co rem enrich PAGE` follows the leads a page has
not followed (links, attachments, older threads) and adds what they establish; `co rem muse PAGE`
asks many questions of a page, studies the five best and writes only on insight. Both pass
investigate's review gate. See [1.9.3rc3 notes](releases/1.9.3rc3.md).

Release candidate **1.9.3rc2**: Agent sessions. `co rem import sessions` keeps one page per
Codex or Claude Code conversation you typed in, with what it produced and its project;
`--summarise` adds a title, summary, topics and outcome, and the reader lists them by topic with one
search. Also reader fixes from the first rc. See [1.9.3rc2 notes](releases/1.9.3rc2.md).

Release candidate **1.9.3rc1**: `co rem` you can show. The reader opens on what is waiting on
you, a person page opens on what is between you, and every citation names who, where and when and
opens the original beside the line. On a real 180-day first run, 66 pages were accepted with none
refused or lost to the notebook lock. See [1.9.3rc1 notes](releases/1.9.3rc1.md).

Beta **1.9.3b5**: `co rem` pages you can trust on the first run. Quotes and contact facts are
checked against their sources, review repairs a page instead of refusing it, and `co rem open`
serves a live reader that can show a page in your language. See
[1.9.3b5 notes](releases/1.9.3b5.md).

Beta **1.9.3b4**: the line a recipient pastes, the mail and the help now say a handoff passes on
the context of a session, not a task. See [1.9.3b4 notes](releases/1.9.3b4.md).

Beta **1.9.3b3**: the thread a handoff adds in Codex now shows in `/resume` and the app's
sidebar in a Codex that had been used before, and the receiving agent names it when it
reports. See [1.9.3b3 notes](releases/1.9.3b3.md).

Release candidate **1.9.2rc1**: handing a session to someone else's agent, checked end to end
between Claude Code and Codex in both directions. See [1.9.2rc1 notes](releases/1.9.2rc1.md).

Beta **1.9.2b31**: accepting a handoff gives the other side nothing but messages about that
handoff; using your agent stays your own decision. See [1.9.2b31 notes](releases/1.9.2b31.md).

Beta **1.9.2b30**: hand off a session from Gemini CLI, opencode, droid, Cursor or Grok, not
only Codex and Claude Code. See [1.9.2b30 notes](releases/1.9.2b30.md).

Beta **1.9.2b29**: before you see a handoff's preview, your own Codex or Claude Code takes
out the private sentences, in the page and in the session copy, and tells you where. See
[1.9.2b29 notes](releases/1.9.2b29.md).

Beta **1.9.2b28**: what you change in a handoff's draft is what goes, in the session copy
too, and the preview points at messages about health, visas, the law or money. See
[1.9.2b28 notes](releases/1.9.2b28.md).

Beta **1.9.2b27**: the copy of your session that goes with a handoff is only the
conversation you approved, never commands or their output, and only the person who accepts
it can read it. See [1.9.2b27 notes](releases/1.9.2b27.md).

Beta **1.9.2b26**: a handoff no longer carries anyone else's email address, phone
number or IP, and you can take its page down at once; status says where it stands in one
line. See [1.9.2b26 notes](releases/1.9.2b26.md).

Beta **1.9.2b25**: the handoff mail reads like a note from you, in your own voice and
language; the conversation shows up in the recipient's Codex app with your name on each
message; only the code you worked on goes. See [1.9.2b25 notes](releases/1.9.2b25.md).

Beta **1.9.2b24**: the person you hand work to reads it on a web page first, then
copies one line into a new Codex conversation. Accepting someone's handoff lets
them send you handoffs, not run tools on your machine. See
[1.9.2b24 notes](releases/1.9.2b24.md).

Beta **1.9.2b23**: the handoff mail is a short note from the sender's own mailbox
(their AI's mail tool, their Gmail or Outlook, the agent mailbox only last), in the
language they wrote in, and `co handoff open` keeps the session going until it is
done. See [1.9.2b23 notes](releases/1.9.2b23.md).

Beta **1.9.2b22**: everything arrives with `co handoff accept`: the code the
recipient cannot fetch and the sender's session copy, and the pasted block tells
their agent to do the work without waiting. See
[1.9.2b22 notes](releases/1.9.2b22.md).

Beta **1.9.2b21**: a handoff opens on what the sender discussed and concluded.
The mail is a reminder and a three-line paste; `co handoff accept` fetches the
handoff, and a question the sender left open reaches them by mail. See
[1.9.2b21 notes](releases/1.9.2b21.md).

Beta **1.9.2b20**: a `co handoff` runs without the person stepping in. The
recipient's agent accepts, does the work and says when it is done; the result
comes back to the sender's `co handoff status`. See
[1.9.2b20 notes](releases/1.9.2b20.md).

Beta **1.9.2b19**: one host serves the agent, REM and your channels however you
start it, and the new `co host` works right after the one-line installer. See
[1.9.2b19 notes](releases/1.9.2b19.md).

Beta **1.9.2b18**: a `co handoff` starts cleanly on a machine that has never
seen co, inside Codex's sandbox too, and the sender sees each question's state
every time. See [1.9.2b18 notes](releases/1.9.2b18.md).

Beta **1.9.2b17**: the session copy sent with a handoff answer also drops
credentials the AI wrote through a tool call. See [1.9.2b17 notes](releases/1.9.2b17.md).

Beta **1.9.2b16**: the first `co handoff` mail reads like an introduction:
who sent it, the task, three steps and one block to paste, in every inbox. See
[1.9.2b16 notes](releases/1.9.2b16.md).

Beta **1.9.2b15**: in `co handoff`, every question is answered exactly once,
including weeks later, when two programs check at once, or when the session is
long or gone. See [1.9.2b15 notes](releases/1.9.2b15.md).

Beta **1.9.2b14**: your agent keeps a record of everything it does for anyone
(`co approvals`), and three kinds of action (credentials and money, anything
that cannot be undone, acting as you in your own accounts) wait for you when
someone else asks and nobody is connected. See [1.9.2b14 notes](releases/1.9.2b14.md).

Beta **1.9.2b13**: when the agent that took over your handoff asks a question,
your agent answers by itself and sends a copy of the session, tool calls
included, with credentials removed. See [1.9.2b13 notes](releases/1.9.2b13.md).

Beta **1.9.2b12**: after the first handoff mail, agents talk through an inbox
on our backend instead of email: questions, answers and later handoffs to a
contact go straight to the other agent. See [1.9.2b12 notes](releases/1.9.2b12.md).

Beta **1.9.2b11**: a handoff carries every message you typed, word for word,
and the AI's replies in summary, across every compaction, plus where the code
is; the recipient's questions come back to `co handoff status --wait`. See
[1.9.2b11 notes](releases/1.9.2b11.md).

Beta **1.9.2b10**: a handoff mail you can read on a phone, whose paste-in block
installs co in its own environment and accepts in one go; one line installs
co; an accepted handoff makes each side the other's contact. See [1.9.2b10 notes](releases/1.9.2b10.md).

Beta **1.9.2b9** adds `co mcp` (Experimental): call the connectors and MCP
servers you already have in Codex, such as Gmail, from the terminal, with no
second login and no model turn. See [1.9.2b9 notes](releases/1.9.2b9.md).

Beta **1.9.2b8**: a handoff now arrives as one prompt to paste into Codex or
Claude Code; the recipient's agent takes it from there, and questions come back
to the sender. See [1.9.2b8 notes](releases/1.9.2b8.md).

Beta **1.9.2b6** makes co rem's second pass go deeper: follow-up searches hand
back mail from people the notebook knows, and one editing turn rewrites the
lines the final round leaves saying what is not known. See
[1.9.2b6 notes](releases/1.9.2b6.md).

Beta **1.9.2b5** adds `co handoff` (Experimental): hand the work in a Codex or
Claude Code session to someone else's agent, which continues it in its own
session. Codex and Claude Code now learn co's commands at `co init`. See
[1.9.2b5 notes](releases/1.9.2b5.md).

Beta **1.9.2b4** hands a session's work to another person or their agent with
the `handoff` skill, and fixes what a real run of 1.9.2b3 found: REM reading
its own sessions, quoted Outlook searches, a background job macOS never
started, and installing on Intel Macs. See [1.9.2b4 notes](releases/1.9.2b4.md).

Beta **1.9.2b3** gives a first run you can read straight away: sources numbered
1, 2, 3, Company filled from the organisation page, probable duplicates named,
and people found by name. See [1.9.2b3 notes](releases/1.9.2b3.md).

Beta **1.9.2b2** was built and tested but not published; its changes are in
1.9.2b3. See [1.9.2b2 notes](releases/1.9.2b2.md).

Beta **1.9.2b1** lets each investigation pass delete as well as add, so pages
improve instead of only growing. See [1.9.2b1 notes](releases/1.9.2b1.md).

Release candidate **1.9.1rc1** waits long enough for its notebook and credential
locks when sixteen workers run at once. See [1.9.1rc1 notes](releases/1.9.1rc1.md).

Beta **1.9.1b5** scans coding sessions once per first run whatever window a page
asks for, and its mail backfill reads only mail. See [1.9.1b5 notes](releases/1.9.1b5.md).

Beta **1.9.1b4** scans your coding sessions once per first run instead of once
per person. See [1.9.1b4 notes](releases/1.9.1b4.md).

Beta **1.9.1b3** writes people's first pages without touching the network,
fetches attachments with the background backfill, and waits out a throttled
mailbox. See [1.9.1b3 notes](releases/1.9.1b3.md).

Beta **1.9.1b2** writes the first pages from mail already on disk, fetches each
person's older mail in the background and deepens those pages, and keeps
project pages that only had a citation wrong. See [1.9.1b2 notes](releases/1.9.1b2.md).

Beta **1.9.1b1** keeps a project page when only one citation is wrong, draws
decisions and principles from the first run, lists a page's documents, and runs
init 16 pages at a time. See [1.9.1b1 notes](releases/1.9.1b1.md).

Alpha **1.9.1a2** reads a large page's whole evidence in rounds, edits pages in
place with a lead-following investigation Skill, enriches organisations from
their own site, shows a person's contact facts first and opens a cited mail as
a message. See [1.9.1a2 notes](releases/1.9.1a2.md).

Alpha **1.9.1a1** maps the last 180 days on the first run and moves co rem's
generated maps and skill run reports from Notes to a Run logs category. See
[1.9.1a1 notes](releases/1.9.1a1.md).

Alpha **1.9.0a43** shows failed investigations on Home and explains the nightly
upkeep offer in init's overview. See [1.9.0a43 notes](releases/1.9.0a43.md).

Alpha **1.9.0a42** keeps completed People discovery after a later mail
connection failure and puts the historical contact directory before the mapped
People roster so a large first run does not bury it. See
[1.9.0a42 notes](releases/1.9.0a42.md).

```bash
python -m pip install --upgrade 'connectonion==1.9.0a42'
co rem init --investigate-all --estimate-only
```

Alpha **1.9.0a41** adds a searchable directory of historical mail contacts,
an all-history first-run cost estimate, and the option to approve nightly REM
upkeep from `co rem init`. Gmail history uses bounded metadata requests. New
notebooks run on Claude Code with Sonnet 5.5 by default. See
[1.9.0a41 notes](releases/1.9.0a41.md).

```bash
python -m pip install --upgrade 'connectonion==1.9.0a41'
co rem init --investigate-all --estimate-only
```

Alpha **1.9.0a40** distinguishes coding-session Skill name matches from
retained evaluation attempts and says explicitly that neither verifies the
installed version or task outcome. Mapped Skill pages put the investigation
command in the phone's first screen; Skill list links are easier to tap. See
[1.9.0a40 notes](releases/1.9.0a40.md).

```bash
python -m pip install --upgrade 'connectonion==1.9.0a40'
co rem open --local
```

Alpha **1.9.0a39** puts direct 44-pixel source links beside a cited Skill
finding, so the specific original remains easy to open on a phone. Labelled
private findings hide those links when the reader hides private passages. See
[1.9.0a39 notes](releases/1.9.0a39.md).

```bash
python -m pip install --upgrade 'connectonion==1.9.0a39'
co rem open --local
```

Alpha **1.9.0a38** adds a within-source find and Next match control to long
archived REM excerpts. It shows when an excerpt was truncated and searches only
the text shown; saved source bodies and memory pages do not change. See
[1.9.0a38 notes](releases/1.9.0a38.md).

```bash
python -m pip install --upgrade 'connectonion==1.9.0a38'
co rem open --local
```

Alpha **1.9.0a37** shows a compact Project purpose on changed Home cards,
keeps the purpose's individual source links openable beside a clipped preview,
and enlarges the desktop privacy control. Saved memories do not change. See
[1.9.0a37 notes](releases/1.9.0a37.md).

```bash
python -m pip install --upgrade 'connectonion==1.9.0a37'
co rem open --local
```

Alpha **1.9.0a36** keeps paragraph and table-field separators when Outlook
HTML mail becomes text. New REM source captures and `co outlook read` can show
event times, reasons and follow-up clauses separately. Already saved excerpts
are not rewritten. See [1.9.0a36 notes](releases/1.9.0a36.md).

```bash
python -m pip install --upgrade 'connectonion==1.9.0a36'
co rem open --live
```

Alpha **1.9.0a35** puts the full-size source action beside the useful lead
on written REM pages. In a five-type 375×812 trial, each action fit within
the first viewport and still opened Sources. See
[1.9.0a35 notes](releases/1.9.0a35.md).

```bash
python -m pip install --upgrade 'connectonion==1.9.0a35'
co rem open --live
```

Alpha **1.9.0a34** speeds scoped REM investigations by reusing a private
parsed window of typed coding-session inputs. On one 90-day notebook, a
source-only repeat in a new process fell from 103.5 to 2.1 seconds while
finding the same 4,957 messages. See
[1.9.0a34 notes](releases/1.9.0a34.md).

```bash
python -m pip install --upgrade 'connectonion==1.9.0a34'
co rem open --live
```

Alpha **1.9.0a33** keeps Person first-contact facts and the People index tied
to evidence, updates first-run token and quota guidance from measured samples,
and shortens the release path without skipping its test gate. See
[1.9.0a33 notes](releases/1.9.0a33.md).

```bash
python -m pip install --upgrade 'connectonion==1.9.0a33'
```

Alpha **1.9.0a32** keeps Skill pages tied to their invocation names, makes
cited run parts and local output files openable in the owner-only reader, and
labels intended outcomes separately from observed work. See
[1.9.0a32 notes](releases/1.9.0a32.md).

The a30 tag did not publish to PyPI after its release CI failed; see
[#2253](https://github.com/openonion/connectonion/issues/2253). Its full-cohort
changes are included in a31.

Earlier alpha previews remain available:

Alpha **1.9.0a31** checks Project claims against their adjacent originals
before replacing a page, supports deliberate retry, and includes the a30
full-cohort onboarding code. See [1.9.0a31 notes](releases/1.9.0a31.md).

Alpha **1.9.0a29** puts the mapped-page investigate action within phone reach
on the first screen. See [1.9.0a29 notes](releases/1.9.0a29.md).

Alpha **1.9.0a28** implements context over control in `co rem investigate`:
pre-authorizes local search and shell tools upfront, supplies live project
repository paths, and records full audit provenance. See
[1.9.0a28 notes](releases/1.9.0a28.md).

Alpha **1.9.0a27** keeps institutional and service desk senders out of the
People notebook and filters dated scratch tasks and prompt fragments from the
Projects notebook unless they have project evidence. See
[1.9.0a27 notes](releases/1.9.0a27.md).

```bash
python -m pip install --upgrade 'connectonion==1.9.0a27'
co rem open --live
```

Earlier alpha previews remain available:

Alpha **1.9.0a26** reopens written `co rem` notebooks faster and makes it clear
when background updates are off while existing memories remain available. The
package README now checks its exact preview pin against the shipped version.
See [1.9.0a26 notes](releases/1.9.0a26.md).

```bash
python -m pip install --upgrade 'connectonion==1.9.0a26'
co rem open --live
```

Alpha **1.9.0a25** shows what a first `co rem init` mapped, reconciles held
contacts, and corrects grouped mail dates on a fresh map. See
[1.9.0a25 notes](releases/1.9.0a25.md).

```bash
python -m pip install --upgrade 'connectonion==1.9.0a25'
co rem open --live
```

Alpha **1.9.0a24** adds `co rem merge` to fold duplicate pages and preserve aliases.
See [1.9.0a24 notes](releases/1.9.0a24.md).

```bash
python -m pip install --upgrade 'connectonion==1.9.0a24'
co rem open --live
```

Alpha **1.9.0a23** clarifies map-derived contact dates in the reader and keeps
table headers visible beside sticky columns on mobile. See
[1.9.0a23 notes](releases/1.9.0a23.md).

```bash
python -m pip install --upgrade 'connectonion==1.9.0a23'
co rem open --live
```

Alpha **1.9.0a22** makes project findings and their evidence easier to check:
the current finding leads, partial session coverage is visible, and every
numbered source can be opened from the reader. See
[1.9.0a22 notes](releases/1.9.0a22.md).

```bash
python -m pip install --upgrade 'connectonion==1.9.0a22'
co rem open --live
```

Alpha **1.9.0a21** shows the complete REM note and citations by default,
puts the note before Facts on phones, and gives investigation more weekly
room while retaining a 10% safety reserve. See
[1.9.0a21 notes](releases/1.9.0a21.md).

```bash
python -m pip install --upgrade 'connectonion==1.9.0a21'
co rem open --live
```

Alpha **1.9.0a20** corrected visible **co rem** reader labels in the morning
overview, recall prompt, empty states and source dialogs. See
[1.9.0a20 notes](releases/1.9.0a20.md).

```bash
python -m pip install --upgrade 'connectonion==1.9.0a20'
co rem open --live
```

Alpha **1.9.0a19** completes the public **co rem** rename: live reader links
use `/rem`, old `/wiki` addresses redirect, and the README, homepage and docs
share the same command name. See [1.9.0a19 notes](releases/1.9.0a19.md).

```bash
python -m pip install --upgrade 'connectonion==1.9.0a19'
co rem init --days 5
```

Alpha **1.9.0a18**: REM's first-run owner page can lead with a cited change
of decision and its next step. The reader shows that change before the full
note and links cited project mentions; extracted fact citations survive the
quick-pass sample. The broader owner and REM maturity gates remain open.
See [1.9.0a18 notes](releases/1.9.0a18.md).

```bash
python -m pip install --upgrade 'connectonion==1.9.0a18'
co rem init --days 5
```

Alpha **1.9.0a17**: REM's first written project page compares the owner's
requests with a bounded local README, package metadata and Git evidence.
Unsupported optional sections disappear after investigation, while supported
claims remain cited. Cross-page links and owner-page history are still open.
See [1.9.0a17 notes](releases/1.9.0a17.md).

```bash
python -m pip install --upgrade 'connectonion==1.9.0a17'
co rem init --days 5
```

Alpha **1.9.0a16**: Gmail scans set a network timeout and avoid fetching
headers twice when a busy week must be split. A private 90-day first run
archived 3,202 messages and completed all 36 selected pages. See
[1.9.0a16 notes](releases/1.9.0a16.md).

Alpha **1.9.0a15**: REM's first run keeps its project list consistent with the
map it just showed. A later session scan prepares evidence for mapped projects
without silently adding project pages; unmatched folders remain private
candidates. This is a focused trust fix, with the broader overnight memory
review still open. See [1.9.0a15 notes](releases/1.9.0a15.md).

```bash
python -m pip install --upgrade 'connectonion==1.9.0a15'
co rem init --days 5
```

Alpha **1.9.0a14**: `co rem init` now investigates the owner's page, recent
important people, active projects and related organizations by default. Its
roughly 20% weekly allowance target is advisory; selected work can finish
beyond it, subject to the configured safety floor. It also adds privacy labels
and a local reader toggle to the connected reader shipped in a13. See
[1.9.0a14 notes](releases/1.9.0a14.md).

```bash
python -m pip install --upgrade 'connectonion==1.9.0a14'
co rem init
```

Alpha **1.9.0a13**: REM's local reader now leads each record with state,
actions, facts and connected context. The home is shorter and task-first;
source-backed field changes are separate from page rewrites. Archived citations
and cited conversations can be inspected in place when source bodies are
available. It remains a read-only preview with known limits. See
[1.9.0a13 notes](releases/1.9.0a13.md).

```bash
python -m pip install --upgrade 'connectonion==1.9.0a13'
co rem open
```

<details>
<summary>The preview line that became 1.8.5</summary>

Beta **1.8.5b11** made the command line name what to run next, and made
calendar invitations actually arrive. `co gcalendar` never passed Google's
`sendUpdates`, so an event with attendees invited nobody — and `Event created`
read the same whether three people were invited or none, so the silent failure
was indistinguishable from success until a client's guest said they got nothing.
Moving or cancelling a meeting told its attendees nothing either, which is worse.
The confirmation now names who was invited, and echoes the time in the zone it
was written in: `16:30+10:00` used to be confirmed as `06:30 AM`.

An audit against `useful_skills/cli-skill-design` fixed four things in the CLI
itself. Every deliberate refusal printed two next steps, one of them useless and
read first by anyone merging streams. A typo ended at `co --help` even when
Click had already worked out the answer — `co larc` now says `Next: co lark`,
and `co like`, which nothing matches, says `Next: co commands` rather than
pointing at a boxed screen of groups. Two failures named no command at all. And
the `co env` skill had never learned about `rotate`, `--secret` or
`--from-console`.

A missing bot permission is now one link away instead of a Developer Console
visit, and #1462's reconnect gate passed: history recovery had never once been
allowed to run, and once it was, a message posted during a 90-second gap came
back exactly once.

It carries `b10`, which makes `co auth lark` create an application and return its
secret — **correcting b9, which shipped a warning saying it could not.** The
cause was one path segment. We printed the URL the SDK hands over,
`<open-host>/page/launcher?user_code=…`, and that page renders "Link expired"
whenever its own acknowledgement call fails, for a code the server reports as
pending in the same second. `lark-cli` discards that URL and builds
`<open-host>/page/cli?user_code=…`; pointed there, the same tenant produced the
creation form, an application, and its secret. Nothing about a tenant, a region,
or a code's lifetime was ever involved. `--app-id` reuse works too.

It carries `b9`, which lets an app secret be stored encrypted. `co env set --secret`
writes ciphertext under a key derived at a SLIP-0013 path and kept nowhere, and
`co env rotate` moves it to the next index. There is no master key, so there is
no keychain to be blocked by a sandbox or a machine with no logged-in human; the
root is `.co/keys/agent.key`, not the optional `recovery.txt`, so writing your
twelve words down and deleting that file cannot orphan a secret — and those
words still reach it, because the agent key is derived from them.

It also carries `co env set --from-console`, which accepts an app credential
copied from the Developer Console — still the right route when you already keep
an application there, though no longer the only way out of a tenant `co auth`
could not serve. And `co auth lark` reports the server's real link lifetime
instead of the SDK's fallback of 600, which is how "it expired after two
minutes" was investigated as a timeout that never existed.

It carries `b8`, which makes `co auth lark` begin on Lark. It used to print an
`open.feishu.cn` link and, on failure, tell a Lark user to run `co auth feishu`;
the accounts domain, the wording, and the reuse command offered from lark-cli's
config all follow the brand now.

It carries `b7`, which lets an agent reach a tab the site opened for itself — a
payment popup, a "view invoice" button, any `target="_blank"` link. Those pages
belong to no session, so they appeared on no board and every `-t` command kept
running in the page before them. `co browser list_pages` shows the browser's
real pages with the session driving each, `switch_page <index>` points a session
at one, and `tab ls` counts what it cannot show and names the verb.

It carries `b6`, which installs the paid browser's driver from PyPI. `onionwright`
held only a name reservation there — one file and a version string — while the
real client travelled a licence-gated endpoint; it is published normally now, so
`pip install 'connectonion[wtf]'` works and the installer is 289 lines shorter.
The browser binary stays licence-gated and the runtime licence is still checked
at launch.

It carries `b5`, which makes asking for the paid engine enough. The route to the WTF
Browser was three commands, and the first one asked the caller to decide nothing —
the engine cannot run without its client. An explicit `--engine wtf` now fetches
it; `auto`, `system` and `--engine wtf help` still install nothing, because
importing ConnectOnion or taking the free engine must never mutate a Python
environment. The paid browser also runs on **Intel Macs** now: its object had
been staged and unpromoted since a gate failure on 2026-09-04, and the re-run
passed on real Intel hardware on 2026-09-13.

It carries `b4`, which fixes what `b3` could not install. `co browser install-onion`
reported `pip could not install Onionwright (exit 1)` when pip had declined by
policy — PEP 668's externally-managed marker, the default on Homebrew and most
distro Pythons — and had named the override itself. pip's output is captured now
so a refusal can be told from a failure, and a policy refusal names the
interpreter and both routes out. The new `--break-system-packages` is opt-in.

It carries everything from `b3`, which fixes two ways the browser could waste an afternoon, both
found by an unattended agent. `co browser wait` takes seconds while every
neighbouring knob is named in milliseconds, so `wait 2500` meant forty-one
minutes holding a tab's lock — every command behind it timed out while
`status` kept answering, so nothing looked broken. It is capped at 60 seconds
now and refuses before taking the lock, naming the value you meant. And a
daemon pinned to an engine refused every bare command, `close` included, while
its own error told you to run `close`: `auto` is no preference now, verbs that
touch no page are never gated, and a refusal names only commands that daemon
would accept. A dead paid session names its recovery, and the paid engine says
it bills before it spends.

It carries everything from `b2`: `co browser config`, the paid engine called
`wtf`, `consume`, and `co auth feishu --app-id`.

The no-loss-across-a-reconnect gate passed on 15 September, against a real
group — the last thing between this line and stable.
See [1.8.5b11 release notes](releases/1.8.5b11.md).

</details>

All eleven 1.8.5 previews (a1 through b11) are superseded by stable 1.8.5;
1.8.4a1 and 1.8.4a2
are historical, and the planned 1.8.4b1 was folded into the stable release. The
tag workflow builds and verifies the public package before documentation is
deployed. Google authorization from 1.8.3 is retained; TikTok remains deferred.
The sections below are historical notes.

## Historical 1.7 preview work

- Stable release: `1.6.10`
- Preview target: `1.7.0a13`
- Browser client: `@connectonion/react@0.4.2-alpha.11`

The preview uses OIP 0.1 as the only first-party browser protocol. The Python
Host serves the authenticated `/ws` connection; `@connectonion/react` owns the
browser client; O Chat consumes the exact React prerelease. Codex and Claude
Code remain native backend provider adapters and publish their normalized
activity through OIP.

Alpha 7 makes explicit Codex requests deterministic: natural-language verbs,
`/codex`, delegation language, and Chinese requests route through the native
Codex adapter before the model chooses a tool. `open Codex` creates or resumes
the provider session without inventing a prompt, and an OIP-visible guard blocks
direct Codex launches through shell tools without affecting ordinary shell text.
The browser continues to use OIP 0.1 and the same shared Work Room card.

Alpha 8 closes the open-only lifecycle found by public browser acceptance.
Codex writes a rollout only after its first turn, so an open-only app-server now
stays alive in a bounded, expiring registry. The first Work Room message claims
that exact provider thread, completes the real turn, persists the rollout, and
then closes the process. The session ID shown when Codex opens is therefore the
same one used by the first task.

Alpha 9 makes reload an authenticated OIP reattach instead of a false second
login. A fresh signed CONNECT that reaches the still-live relay queue is accepted
only when caller, recipient, signed-command capability, OIP protocol, and session
are unchanged. The Host republishes CONNECTED without duplicating a running
forwarder; every mismatch and signature replay remains rejected.

Alpha 10 separates that reattach proof from first-connect authorization. The
same live caller must still present a fresh signature and unchanged recipient,
capability, protocol, session, replay claim, and current blacklist status, but
the Host no longer repeats mutable onboarding/contact/admin policy or rebuilds
permission authority for a connection that is already authorized. It republishes
the existing mode, profile, transcript, and dashboard state. A first Send or
Codex Work Room follow-up racing the eager browser CONNECT now reaches its input
instead of surfacing a local trust-file error.

Alpha 11 makes the OIP 0.1 rolling window explicit. Descriptor-less 0.1 peers
remain readable, Direct and Relay use the same compatibility gate, unsupported
versions fail once without retry, discovery stays uncached, and Host records only
content-free compatibility classifications. DD-053 now defines the release and
time boundary before a reader can be removed.

Alpha 12 closes the production blockers found by real Chrome acceptance. Claude
Code keeps its authenticated macOS CLI environment and publishes a resumable
Work Room lifecycle like Codex. Stop now terminates the complete hosted Bash
process group, and multimodal messages no longer crash slash-command dispatch or
lose their image parts. The release gate includes fresh onboarding, approval,
cancellation with a process-tree check, text and image attachments, reconnect,
both native coding adapters, mobile layout, and session rollback across exact
published React and Host prereleases.

Alpha 13 makes a long native coding run observable while it is still running.
Codex and Claude Code emit their provider lifecycle and child work in a live,
non-persistent presentation lane; their canonical trace remains transactional
until the outer hosted tool commits. A cancellation closes the live provider
card without leaking that uncommitted trace. Native Codex approvals now carry
safe exact provider correlation, so React and O Chat put the decision on the
right Work Room card instead of a generic outer tool. The default UI presents a
bounded semantic activity snapshot; raw commands and outputs stay behind
disclosure.

Normal upgrades stay on stable. Preview testers opt in explicitly:

```bash
python -m pip install connectonion==1.7.0a13
```

## Design Journal

Release notes record what changed. A Design Journal post records the problem,
alternatives, decision, tradeoffs, evidence, and what would make us revisit it.
Meaningful feature-train launches, phase promotions, stable releases, and
material architecture decisions receive a new or substantially updated post.

The OIP-only decision is recorded in
[DD-053](design-decisions/053-oip-only-browser-and-native-coding-adapters.md).
