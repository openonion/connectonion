# fde-client-agent

Deploy and operate a ConnectOnion agent for a real client (Forward-Deployed
Engineering). Distilled from the NatureWill engagement: a contract-ledger agent
and a candidate-mapping agent, both in production with a non-technical Chinese
client — every rule below was paid for by a real incident.

Use when: starting a new client agent, taking over an existing one, or reviewing
why a deployed agent is misbehaving.

## Project shape

- **One repo per client, one project directory per agent.** `co deploy` deploys
  the *current directory* — a flat layout once shipped the wrong agent to the
  wrong server, successfully and silently.
- **Skills are the interface, the library is the engine.** All capability lives
  in `.co/skills/<name>/` (scripts + SKILL.md + tests). No parallel CLI, no
  utils.py — helpers live in the feature file that uses them.
- `SKILL.md` needs YAML frontmatter (`name:`, `description:`) — without it the
  chat UI shows a "No description" chip to the client.
- `.co/OO.md` goes into the system prompt. Put there: *"for X-related asks, call
  skill(name=...) first — don't glob around"* and the client-language rule
  (first character of every reply in the asker's language).
- Internal notes (pricing, client quirks, strategy) live **outside** `.co/` —
  everything under `.co/` rsyncs to the client's server. Add a leak test.

## State and data

- **Runtime state lives outside the rsync root** (e.g. `/srv/<agent>-state/`),
  pointed to by an env var (`NW_WORK=`) set in the systemd unit *and* re-added
  by your deploy script — `co deploy` rewrites the env file every time.
- Local pipeline runs create cache dirs (`work/`) that rsync will happily ship;
  the agent then answers from a stale snapshot. Delete them server-side on every
  deploy. Deletions never sync (rsync protect filters), so deleting locally is
  not enough.
- **The agent must be told where the authoritative data is** (SKILL.md +
  system-prompt pointer). Without it, one "how many contracts?" question cost
  $1.97 / 1.28M tokens of filesystem rummaging and surfaced a stale number.

## Writing to client-visible tables (Feishu Base or similar)

- **Incremental only.** Read live rows back, diff field-by-field, write only
  genuinely changed fields. Full rewrites lock the table during every scan.
- **Normalize before diffing.** Values come back shaped differently than
  written: numbers as float, empty text as None, url-styled text as
  `[url](url)` markdown, datetimes with `+08:00`. Miss one shape and
  "incremental" silently degrades to a nightly full rewrite. Keep ONE
  normalization implementation shared by all publishers.
- **Row identity = file token, never path.** A drive folder can hold two files
  with the same name; keying by path merged two real contracts into one
  flip-flopping row.
- **Client-owned columns are sacred.** Columns humans fill (payment status,
  actual amounts, notes) never participate in diffs and are never overwritten.
  Machine-filled figures always carry a provenance column ("this number came
  from file X, rule Y") — an unexplainable auto-filled number is worse than an
  empty cell.
- Migrations happen **inside the normal write path** (legacy rows claimed and
  upgraded on the next run), not as a separate script someone must remember.

## Identity, money, monitoring

- **The agent's public address is client-facing infrastructure.** Invite links
  and codes reference it; never rotate it casually. Read it from the live
  `/info` endpoint — env files and configs lie.
- **Invite codes are passwords.** Say so on every card that carries one.
- The only deploy check that counts: *take the key the service actually runs
  with, ask the billing ledger who it is and whether it spent money today.*
  `systemctl active`, local balance displays, and deploy ✓ have all reported
  healthy while the service starved for days. Make it a test; prove it can go
  red (`--破坏` flag); don't assert "spent today" near the UTC midnight reset.
- Wrap `co deploy` in a `deploy.sh` that re-adds env vars, clears cache
  snapshots, re-runs the identity fix, and ends with that test as the verdict.
  Keep the guard even after upstream fixes land — ours regressed the same
  afternoon it was removed (deploys from fresh worktrees lack `.co` metadata).

## The control center (dashboard)

- The Control Center iframe is **sandboxed: `<script>` never executes**. Any
  fetch()-based dashboard shows empty panels and even its error message never
  renders. Data must be baked into the HTML server-side via marker regions
  (`<!-- NAME:BEGIN/END -->`) rewritten by a pipeline script; interactions go
  through `data-ochat-skill` / `data-ochat-args` buttons only.
- Marker rewrites must be idempotent (run twice → byte-identical) and fail
  loudly when a marker is missing.
- BI discipline: one hero number, shares drawn as bars (not mental math),
  drill-down to the concrete money (which contract, until when), every figure
  labeled with its methodology tier, tiers never summed together.
- Keep a `control-center-audit` skill: hard constraints (no JS, marker
  integrity, brand palette, traceable numbers) + a design checklist, run before
  every dashboard change.

## Client communication

- Bot-signed **fact broadcasts** (release cards, ledger updates) go out
  directly; anything needing a client decision goes through the human owner
  first.
- **Release cards carry a screenshot** of the live page — fetch the deployed
  HTML from the server, render via file:// (never screenshot your logged-in
  developer view; it shows balances and other agents), upload with the bot
  identity (`--as bot`; image keys are per-app).
- Deep-link buttons: a Base link without `?table=` lands on the default table —
  the client will tell you "you sent me the wrong thing".
- Answer in the client's language from the first character; report conclusions
  and numbers, never file paths or script names.

## Verification culture

- New regression tests must fail on the unpatched code first.
- Test fixtures must use the **real shapes** (markdown links, tz-suffixed
  datetimes) — bare-url fixtures kept a table-rebuilding bug green in tests.
- After every deploy, verify at the layer the change protects: run the pipeline
  twice on the server and expect zero writes; open the real page as the client
  would; screenshot as evidence.
- Every discovered problem becomes an issue in the client repo the moment it's
  found; every fix updates its issue with evidence. Repo work flows
  worktree → PR → tests → merge → deploy — never on a shared checkout.
