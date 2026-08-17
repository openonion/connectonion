# deploy-agent

Deploy and operate a ConnectOnion agent in production. Every rule below was paid
for by a real incident — a wrong deploy, a stale answer, a silently starved
service.

Use when: standing up a new agent, taking over an existing one, or working out
why a deployed agent is misbehaving.

## Project shape

- **One project directory per agent.** `co deploy` deploys the *current
  directory* — a flat layout will happily ship the wrong agent to the wrong
  server, successfully and silently.
- **Skills are the interface, the library is the engine.** All capability lives
  in `.co/skills/<name>/` (scripts + SKILL.md + tests). No parallel CLI, no
  `utils.py` — helpers live in the feature file that uses them.
- `SKILL.md` needs YAML frontmatter (`name:`, `description:`) — without it the
  chat UI shows a "No description" chip to whoever is using the agent.
- `.co/OO.md` goes into the system prompt. Put there: *"for X-related asks, call
  `skill(name=...)` first — don't glob around"*, plus any reply-language rule.
- **Anything under `.co/` ships to the server.** Internal notes — pricing,
  strategy, account quirks — live outside it. Add a test that fails if they
  leak.

## State and data

- **Runtime state lives outside the rsync root** (e.g. `/srv/<agent>-state/`),
  pointed to by an env var set in the systemd unit *and* re-added by your deploy
  script — `co deploy` rewrites the env file every time.
- Local pipeline runs create cache directories that rsync will happily ship; the
  agent then answers from a stale snapshot. Delete them server-side on every
  deploy. Deletions do not sync (rsync protect filters), so deleting locally is
  not enough.
- **Tell the agent where the authoritative data is** — in SKILL.md and in the
  system prompt. Without that pointer, a single "how many records?" question
  cost $1.97 and 1.28M tokens of filesystem rummaging, and still surfaced a
  stale number.

## Writing to user-visible tables

Applies to any hosted table the user also edits by hand — Feishu Base, Airtable,
Notion, Google Sheets.

- **Incremental only.** Read live rows back, diff field by field, write only
  genuinely changed fields. Full rewrites lock the table during every scan.
- **Normalize before diffing.** Values come back shaped differently than they
  went in: numbers as floats, empty text as `None`, url-styled text as
  `[url](url)`, datetimes with an offset. Miss one shape and "incremental"
  silently degrades into a nightly full rewrite. Keep ONE normalization
  implementation shared by every publisher.
- **Row identity is a stable token, never a path.** A folder can hold two files
  with the same name; keying by path merged two distinct records into one
  flip-flopping row.
- **User-owned columns are sacred.** Columns a human fills — status, actual
  amounts, notes — never participate in diffs and are never overwritten.
  Machine-filled figures always carry a provenance column ("this number came
  from file X, rule Y"). An unexplainable auto-filled number is worse than an
  empty cell.
- Migrations happen **inside the normal write path** — legacy rows claimed and
  upgraded on the next run — not as a separate script someone has to remember.

## Identity, billing, monitoring

- **The agent's public address is infrastructure.** Invite links and codes
  reference it; never rotate it casually. Read it from the live `/info`
  endpoint — env files and configs lie.
- **Invite codes are passwords.** Say so on every card that carries one.
- The only deploy check that counts: *take the key the service actually runs
  with, ask the billing ledger who it is and whether it spent anything today.*
  `systemctl active`, local balance displays, and a green deploy have all
  reported healthy while the service was starved for days. Make it a test, prove
  it can go red, and don't assert "spent today" near the UTC midnight reset.
- Wrap `co deploy` in a `deploy.sh` that re-adds env vars, clears cache
  snapshots, re-runs the identity fix, and ends with that test as the verdict.
  Keep the guard even after upstream fixes land — one such guard regressed the
  same afternoon it was removed, because deploys from fresh worktrees lack `.co`
  metadata.

## The control center (dashboard)

- The Control Center iframe is **sandboxed: `<script>` never executes.** A
  fetch()-based dashboard shows empty panels, and even its error message never
  renders. Bake data into the HTML server-side via marker regions
  (`<!-- NAME:BEGIN/END -->`) rewritten by a pipeline script; interactions go
  through `data-ochat-skill` / `data-ochat-args` buttons only.
- Marker rewrites must be idempotent — run twice, get byte-identical output —
  and fail loudly when a marker is missing.
- Dashboard discipline: one hero number; shares drawn as bars rather than left
  as mental arithmetic; drill-down to the concrete detail; every figure labelled
  with its methodology tier, and tiers never summed together.
- Keep a `control-center-audit` skill — hard constraints (no JS, marker
  integrity, brand palette, traceable numbers) plus a design checklist — and run
  it before every dashboard change.

## Communicating with the people using it

- Bot-signed **fact broadcasts** (release notes, ledger updates) can go out
  directly. Anything requiring a decision goes through a human owner first.
- **Release cards carry a screenshot** of the live page: fetch the deployed HTML
  from the server and render it via `file://`. Never screenshot your logged-in
  developer view — it exposes balances and other agents. Upload with the bot
  identity (image keys are per-app).
- Check deep links land where you think. A table link without an explicit table
  parameter opens the default table, and you will be told you sent the wrong
  thing.
