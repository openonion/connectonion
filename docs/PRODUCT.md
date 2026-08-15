# ConnectOnion — what it actually is

The foundation document. Every public page — connectonion.com, docs.connectonion.com,
a README, a launch post — gets written **from this file**, not from memory and not
from a directory listing.

It exists because the alternative kept failing. Writing marketing from an
impression of the codebase produced four false claims that shipped publicly this
year (MIT instead of Apache-2.0; end-to-end encryption that does not exist;
migration tools that do not exist; an invented 75% statistic), and a landing page
that quietly dropped eleven of fifteen real capabilities because they were hard to
fit. Both failures have the same cause: no single place said what the product is.

**How to use it.** Every entry states what a person can *do*, whether it is on by
default, and the limit they would feel misled by if they found it later. A page may
compress an entry. A page may not contradict one, and may not claim something that
is not here. Section 11 is the standing list of things that are not true — check it
before writing, not after.

Line numbers drift. If one does not match, re-verify the behaviour rather than just
fixing the number: a moved line is often a changed behaviour.

Companion: `docs/SELLING_POINTS.md` is the audit ledger — claim, proof, limit, and
a record of what was cut and why. This file is the narrative. They must agree.

---

## 1. The first sixty seconds

```
pip install connectonion
co ai
```

`co ai` builds a coding agent, hosts it, and **opens a browser onto a chat UI**
talking to that agent on your machine (`cli/commands/ai_commands.py:33-46`,
`cli/co_ai/main.py:59-69`). There is no terminal TUI — the interface is the web
chat at `chat.openonion.ai/{your 0x address}`, with the agent's dashboard beside it.

`co ai "do X"` instead runs once and prints the answer (`ai_commands.py:40-43`).

**Default.** **Limit:** it runs on your machine and stops when you close it; §6
covers what changes that.

What the agent has on day one (`cli/co_ai/agent.py:76-118`): file read/edit/write,
glob, grep, bash, plan mode, a todo list, background tasks, subagents, skills, and
`ask_user`. Browsing is via bash calling `co browser`. Email is **not** a wired tool
on this agent — it is a separate CLI path (§3).

**Default model** for `co ai` is `co/gemini-3.7-flash` (`cli/main.py:224`; note
`ai_commands.py:13` carries `co/claude-opus-4-5` as a Python-level default that the
CLI always overrides — do not quote that one). `Agent()` and the `co create`
template also default to `co/gemini-3.7-flash` (`core/agent.py:41`).

---

## 2. What you get without writing anything

### A working project, not a blank file

`co create my-agent` writes the project (`cli/commands/create.py:236-357`):

- `agent.py` — eleven lines, six tools and an approval plugin already wired
  (`cli/templates/minimal/agent.py:12-24`)
- `prompt.md` — the system prompt, as a file you edit
- `.co/docs/` — **the entire documentation tree, copied into your project**, so
  Claude Code, Cursor or Codex can read it while helping you (`create.py:293-295`)
- `.co/host.yaml` — hosting config: trust level, port, permission whitelist
  (`project_cmd_lib.py:918-946`)
- `.env` — copied from your global `~/.co/keys.env` (`create.py:302-348`)
- a master Ed25519 keypair in `~/.co/`, chmod 600 (`project_cmd_lib.py:1045-1090`)

**Default.** **Limit:** `co create` makes a network call to authenticate for managed
keys unless you are already authenticated (`create.py:71-81`).

### Six templates

`minimal` (default), `coder` (adds a REPL, `max_iterations=50`, **no approval
plugin** — bash and write run unguarded), `browser`, `hosted-browser` (the serious
one: shared browser, idle reaper, per-request agents, Docker), `co-ai` (deploy the
built-in coding agent as a service, 7 lines), `web-research`.

**Limit:** `web-research` ships a **placeholder `search_web` that returns fake
results** and says so in its own header (`cli/templates/web-research/agent.py:30-31`).
Do not advertise it. `custom` is not a directory but a code path that asks an LLM to
write your agent; if that call fails there is a hardcoded stub that only echoes
`Processing: {query}` (`project_cmd_lib.py:745-760`), and the generated code is never
executed or validated.

### $5 of credit, no API key

Managed models via the `co/` prefix point an OpenAI client at
`https://oo.openonion.ai/v1` with your OpenOnion JWT (`core/llm.py:998-1015`), so the
generated project runs without an OpenAI, Anthropic or Google key.

**Default.** **Limit:** those requests route through OpenOnion's proxy. Put your own
key in `.env` and change the model string at any time.

---

## 3. What you can do without writing Python

These are commands. No project, no imports, no framework to adopt — the strongest
answer to "do I have to buy into all of this?" is that you do not.

| Command | What it does |
|---|---|
| `co browser` | a persistent daemon owning **one real browser**. Log in by hand once — including 2FA — and every later command reuses that session. ~40 operations: click, type, upload, extract a table, screenshot, run a script. `co browser do "…"` puts an LLM on the same live browser (`cli/commands/browser_commands.py:20-40`, `useful_tools/browser_tools/browser.py`) |
| `co gmail` | inbox, read, reply, send, sent, search (`cli/main.py:498-569`) |
| `co outlook` | mail plus contacts, deferred and scheduled send |
| `co gdrive` | list, search, get, put, rm |
| `co syno` | a Synology NAS: login, ls, search, get, put, share |
| `co email` | the agent's **own** mailbox — see the limit below |
| `co call <addr> <cmd>` | run one command on a *remote* agent, no LLM in the loop, gated by that agent's whitelist (`cli/commands/call_commands.py:51-135`) |
| `co copy <name>` | vendor any built-in into your project to edit: 16 tools, 13 plugins, 10 TUI components, trust policies, skills (`cli/commands/copy_commands.py:20-104`) |
| `co skills` | discover, copy, link and list skills across tools (§8) |
| `co eval` | replay recorded runs and score them (§7) |

**`co browser` limit:** one browser at a time; a second agent asking for the same tab
gets exit code 4. `bash` itself is **Unix and macOS only — it raises on Windows**
(`useful_tools/bash.py:9`).

**There is no `co calendar`.** Calendar exists only as Python tools
(`useful_tools/google_calendar.py`, `microsoft_calendar.py`). Do not claim calendar
from the CLI.

**Email, precisely.** Every address deterministically yields
`{address[:10]}@mail.openonion.ai` at key generation (`address.py:69-70`) — so "it
ships with an email address" is literally true of the identity. But it is **inert
until `co auth`** (`address.py:76`), send and receive are **hosted OpenOnion API
calls**, not agent-local (`useful_tools/send_email.py:98`), and custom names and
higher tiers cost credits (`cli/commands/email_commands.py:127-183`). Say "an
OpenOnion-hosted mailbox", never "your agent runs its own mail server".

---

## 4. Three levels of changing it

The product's real shape. Most users never reach level 3.

**Level 1 — edit `prompt.md`.** A file. No code.

**Level 2 — write a skill.** A skill is a `SKILL.md`: YAML frontmatter (`name`,
`description`, `tools`) and markdown instructions (`useful_plugins/skills.py:31-47`).
Drop it beside the agent, type `/its-name`. While it runs it can widen what the agent
may do, and **the widening is revoked when the turn ends** — granted with
`expires: turn_end`, snapshot restored on complete (`skills.py:246-287`).

**Level 3 — edit the generated Python**, or `co copy` any built-in into your project
and edit that. It is your repository; there is no hosted build step.

---

## 5. What your customer sees

This is the half that gets under-sold, because it lives in a different repo.

**No account.** They open a link — or scan a QR — and start talking. Identity is
generated silently in their browser: BIP39 phrase → Ed25519 keypair in localStorage,
signed for a JWT (`oo-chat/hooks/use-identity.ts:107-141`). No email, no password,
nothing installed. **Limit:** the key lives in that browser, so a different browser is
a different identity unless the recovery phrase is imported.

**A dashboard the agent maintains.** Every agent gets one on day zero — with no
`dashboard.html`, one is written for it carrying up to four of its skills as working
buttons (`network/host/ws_router/dashboard.py:102-155`). The agent changes it by
**editing the file with ordinary file tools**; the host notices by mtime and size and
pushes a snapshot after any run that changed it; the pane re-renders. No polling, no
fetch, no deploy (`ws_router/dashboard.py:77-99`, `agent_io.py:70-74`). Buttons run
real skills and leave a visible line in the chat, so nothing happens off-screen.
**Limit:** 2 MB with images inlined; over that no dashboard is sent rather than a
broken one. Agent-authored HTML runs under `default-src 'none'` in an opaque-origin
iframe — its own scripts never execute and it cannot call out or navigate away.

**The agent can stop and ask.** Approval cards (allow once / for the session / three
kinds of rejection), a plan to review, a typed form including password fields, and a
checkpoint when an autonomous run hits its turn budget.

**Voice input** is real, in the web chat (`oo-chat/components/chat/chat-input.tsx:43-51`).
**Limit:** it needs the OpenOnion API key; input only, no speech output.

**Gate strangers with an invite code or a payment** instead of a login. **Limit — read
§11:** the verified path and an unverified path both exist today.

---

## 6. Where it runs

**On your machine by default.** The model calls, the file writes, the logs, the
dashboard file. Close the laptop and it stops.

**Reachable anyway.** `host()` dials `wss://oo.openonion.ai` so the agent answers on
its `0x` address without port-forwarding (`network/host/server.py:377,388`).
**Limit, and state it plainly:** the relay sees everything. All frames traverse it as
cleartext JSON (`network/relay.py:139-154`). It is TLS in transit, terminated at the
relay. **It is not end-to-end encryption and must never be described as such.**
Hosting also publishes your summary, tool names, model, project skills, balance and
**all local and public IP endpoints** unless you pass `relay_url=None`
(`network/announce.py:25-51`).

**`co deploy`** packages git-tracked files, ships `.env` separately as secrets, POSTs
to `https://oo.openonion.ai/api/v1/deploy`, polls, and prints the agent URL and
container logs (`cli/commands/deploy_commands.py:250-474`). Requires `.co/host.yaml`,
a DNS-safe name, an entrypoint containing a `host(...)` call, and `co auth`.
**Limit: cloud only.** There is no `--to <server>` flag and no self-host automation —
self-hosting means running `host()` yourself.

**Your logs are files.** `.co/logs/{agent}.log` plain text, and `.co/evals/{slug}.yaml`
per unique input with tokens, cost, duration and the full message array
(`logger.py:228-405`). Nothing to sign into to read your own run.

**Identity.** The `0x` address **is** the Ed25519 public key — no hash, so signatures
verify with no key exchange (`address.py:62-64`). Recoverable from twelve words. The
reasoning, including what was rejected and at what cost, is in
`docs/design-decisions/006-agent-address-format.md`. **Limit:** the format has no
checksum, so a mistyped address is not caught.

---

## 7. For the engineer evaluating it

**`auto_debug_exception()`** installs an excepthook; on any uncaught exception a debug
agent receives the **live crashed frame** and can execute code in it, inspect objects,
validate assumptions and test fixes against the real frozen state
(`debug/auto_debug_exception.py:26+`, `debug/runtime_inspector/`). This is the most
unusual thing in the package. **Limit:** it fires on exceptions, never on wrong answers.

**`@xray`** exposes `xray.agent/.task/.messages/.iteration/.previous_tools` inside any
tool; context is now injected for all tools automatically, so the decorator's real job
is auto-printing the trace. **`xray.trace()`** prints numbered steps with per-tool
timings and truncated in/out, and finds the agent by stack inspection so it works from
a breakpoint anywhere. **`@replay`** re-runs the same tool call with overridden
arguments from that breakpoint.

**Thirteen lifecycle hooks** (`core/events.py`). Cancel a tool by raising in
`before_each_tool`; inject messages safely after a whole batch with `after_tools`;
restart the agent from `on_complete` — which is how autonomous mode works.

**Cost is tracked per call** — `agent.total_cost`, `agent.last_usage`,
`agent.context_percent`, and cost written into every eval file (`core/usage.py`).
**Limit:** pricing is a static table; an unlisted model silently falls back to
$1/$3 per 1M and a 128k context assumption, so both the cost figure and the
auto-compaction trigger become estimates.

**`co eval`** loads recorded runs, replays each input against your agent, records
output, tools, tokens and cost back into the YAML, and LLM-judges any turn with an
`expected` field (`cli/commands/eval_commands.py:102-228`). **Limit:** the judge is an
LLM instructed to be lenient, not an assertion.

**Approval modes:** `safe` (default), `plan`, `accept_edits`, and an autonomous mode.
Rejection has three flavours — hard stops the run, soft makes the model offer
alternatives, explain makes it justify itself. Bash chains are split and **every
subcommand must be permitted independently**, so `git log; curl evil` is refused
(`useful_plugins/tool_approval/bash_parser.py:162-202`). **Two limits worth stating:**
only a fixed set of tool names counts as dangerous, so a custom `deploy_to_prod` tool
is auto-approved (`tool_approval/constants.py:50-63`); and approvals only exist when
`agent.io` is set — with no frontend attached, everything runs
(`tool_approval/approval.py:485-486`).

---

## 8. It meets the tools people already use

**Skills are the same files.** ConnectOnion reads `.claude/skills/<name>/SKILL.md` and
`~/.claude/skills/` at runtime (`useful_plugins/skills.py:117-136`). `co skills
discover` also scans Codex, Cursor and Kiro; `co skills link` pushes ours the other
way, into Claude Code and Codex. **Limit:** we read the `tools:` key, not Claude
Code's `allowed-tools`, so a skill's auto-approvals do not carry across — issue #967.
Say "reads the same SKILL.md files", never "runs identically".

**Codex runs as a subprocess, today.** ConnectOnion spawns `codex app-server` and
speaks OpenAI's native JSON-RPC over stdio from its own Python client, no Node adapter
(`useful_tools/codex.py`). Sandbox levels read-only / workspace-write /
danger-full-access; per-action approvals route to the human through the existing
approval card. **Limit:** requires the `codex` binary. **There is no Claude Code
equivalent** — Claude is available only as a model provider.

**Nine model providers**, all implementing both tool calling and structured output
through each provider's native mechanism: OpenAI, Anthropic, Gemini, Groq, Grok,
OpenRouter, Mistral, and OpenOnion managed keys (`core/llm.py`).

---

## 9. The front end

`oo-chat` is the web chat — Next.js, self-hostable with `npm install && npm run dev`
and one optional environment variable.

**⚠️ Do not call it open source yet.** There is **no LICENSE file** in the repo and
`package.json` sets `"private": true`, while its README already says "an open-source
web chat client". The Python package is Apache-2.0; the front end currently has no
licence at all. Either add a licence or drop the claim — right now the README is
writing a cheque the repo does not honour.

`chat-ui` / `@connectonion/chat-ui` is referenced by both CLAUDE.md and the README as
a component registry. It is **not present** and unverified.

---

## 10. Two honest sentences about the shape of this

Worth saying out loud on any page that sells to a business:

1. **It is a local-first tool with a hosted spine.** Execution is yours; identity,
   relay, managed models, email and deploy are OpenOnion services. That is a real
   trade, not a flaw, but a buyer who discovers it later feels sold to.
2. **The relay can read agent traffic.** Stated first, by us, every time.

---

## 11. Not true — check before writing

| Do not write | What is actually true |
|---|---|
| "end-to-end encrypted" | No payload encryption exists anywhere. TLS to a relay that terminates it |
| "MIT licensed" | Apache-2.0 (Python package). The front end has **no licence at all** |
| "the front end is open source" | No LICENSE, `"private": true`. Fix the repo or drop the claim |
| "migration tools" | None exist |
| "agents test with dummy data first" | No such mechanism |
| any adoption or time-saved statistic | We have no survey. The "75% more time" figure was invented |
| "native iOS / Android apps" | No such repo is present. Web, Python and CLI only |
| "calendar from the CLI" | Python-only; there is no `co calendar` |
| "deploy to your own server with `co deploy --to`" | Does not exist. Cloud only |
| "self-host the relay" | You can point `relay_url` elsewhere, but **the relay server is not in this repo** — you would reimplement the protocol |
| "one agent can call another as a tool, out of the box" | `connect()` returns a `RemoteAgent`; you can pass `remote.input` into `tools=[]` yourself, but nothing ships wired |
| "browse a directory of agents" | Discovery is by known address. There is no search endpoint |
| "2 lines" / "3 lines" / any line count | Retired. Nobody writes those lines; the CLI writes the project |
| a comparison to LangChain, AutoGPT or CrewAI | Files us in their category. Never |

### Written but not wired — do not market

- `co ai`'s built-in slash commands `/init /help /cost /compact /tasks /export
  /sessions /new /resume /undo /redo` are defined and imported nowhere — issue #965.
  Working slash commands are skill names.
- `cli/co_ai/sessions.py` and its SQLite store are reachable only from those commands.
- `cli/co_ai/agents/registry.py` duplicates the explore and plan subagents; the running
  agent uses `useful_plugins/builtin_agents/` — issue #966.
- `create_app()` advertises `sha256(agent.name)` as the agent address — a fake
  unrelated to the Ed25519 key, inconsistent with `host()`.
- `@expose` has a design document and no implementation.
- `logger.load_messages()` has no callers, so "replay a past run" is a data format,
  not a feature. `co eval` is the real replay path.

### One security finding, not a marketing note

Payment onboarding has two paths. The WebSocket `ONBOARD_SUBMIT` path really verifies
a transfer against the OpenOnion API (`network/trust/trust_agent.py:239-334`). The
fast-rule path promotes anyone whose **self-declared** `payment` field meets the number,
with no verification (`network/trust/fast_rules.py:98-102`). Until that is resolved, do
not market paid access on the default `careful` trust level.
