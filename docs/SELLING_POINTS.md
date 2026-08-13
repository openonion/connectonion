# Selling points

What is genuinely unusual about ConnectOnion, with the proof attached.

Produced by the `find-selling-points` skill. Read that skill before adding to this
file — the rules are the point. In short: every claim ends in `file:line` or it
gets deleted, no framework comparisons, no line counts, and each entry states the
limit a buyer would otherwise discover later and feel misled by.

Line numbers drift. If one no longer matches, re-verify the claim rather than
just fixing the number — a moved line is often a changed behaviour.

---

## Run 2026-08-13

**Read:** `connectonion/network/host/ws_router/`, `connectonion/network/host/server.py`,
`connectonion/useful_plugins/skills.py`, `connectonion/cli/commands/skills_commands.py`,
`connectonion/cli/main.py`, `connectonion/useful_skills/`, `connectonion/useful_tools/`,
`connectonion/cli/browser_agent/`, `connectonion/cli/co_ai/`, and the front end at `../oo-chat`.

**Survived:** 15. **Cut:** 10 (see the bottom — that list is the more useful half).

---

### `co ai` is the product. One command, and a chat opens in your browser.

**Claim.** You do not build an agent to get an agent. Type `co ai` and a browser
opens onto a working chat — with the dashboard beside it — talking to an agent
running on your own machine. Nothing is written, nothing is deployed.
**Proof.** `cli/commands/ai_commands.py:33-46` builds the agent and calls
`start_server()`; `cli/co_ai/main.py:59-69` opens
`https://chat.openonion.ai/{your 0x address}` and calls
`host(agent, port=port, trust="careful", co_dir=~/.co)`. `host()` serves
`POST /input`, `WS /ws`, `/health`, `/info` and joins the relay at
`wss://oo.openonion.ai` by default (`network/host/server.py:415-449`).
**Default or opt-in.** Default. `co ai "do X"` instead runs once and prints the
answer (`ai_commands.py:40-43`).
**Limit.** The agent runs on your machine; close the laptop and it stops. There
is no terminal TUI — the interface is the web chat.
**Why it is unusual.** The install does not give you a library to build a product
with. It gives you the product, and the address to share it.

### `co deploy` takes it off your laptop

**Claim.** When the agent needs to outlive your laptop lid, one command packages
the project, uploads it, and gives you back a hosted agent URL.
**Proof.** `cli/main.py:207` wires the command; `cli/commands/deploy_commands.py`
validates `.co/host.yaml`, packages git-tracked files into a tarball (merging any
`--skills` paths into `.co/skills/`), POSTs to `/api/v1/deploy`, polls
`/api/v1/deploy/{id}/status` until running, and prints the agent URL.
**Default or opt-in.** Opt-in. Needs `.co/host.yaml` and an `OPENONION_API_KEY`.
**Limit.** It deploys to ConnectOnion Cloud, not to your own infrastructure, and
the relay caveat above still applies to the hosted agent. Build budget is up to
about 20 minutes.
**Why it is unusual.** Nothing here — hosting an app is ordinary. It is on this
list because **every reviewer asked "what happens when I close the laptop?"
before any other question**, and a page that shows a laptop-hosted agent without
answering it reads as a toy. This is the answer, and it was missing from both the
site and this file.

### Permission patterns are checked per subcommand, not against the whole string

**Claim.** A permission for `git *` does not let a chained command through.
`git log; curl evil.com` is rejected, because every subcommand in a chain must be
independently permitted.
**Proof.** `useful_plugins/tool_approval/bash_parser.py:162-202` —
`check_bash_chain_permitted()` calls `_extract_subcommands()` and requires a match
for each one; any unpermitted subcommand rejects the whole chain.
**Default or opt-in.** Default, wherever the approval plugin is loaded.
**Limit.** Matching within a subcommand is still fnmatch rather than a full shell
parser, so patterns should be written tightly.
**Why it is unusual.** It is here because a reviewing engineer named the opposite
as a dealbreaker — "fnmatch against a command string is a bypass waiting to
happen" — and was wrong, but only findably wrong. If a careful reader assumes the
naive implementation, the page should say which one we built.

### It is reachable from anywhere, not just the tab that opened

**Claim.** Because `co ai` hosts the agent on the relay with its own address, the
chat link works for other people, on other machines — while it runs on yours.
**Proof.** `host()` joins `wss://oo.openonion.ai` and the opened URL is keyed by
the agent's `0x` address (`cli/co_ai/main.py:59-69`, `network/host/server.py:415-449`).
**Default or opt-in.** Default.
**Limit.** The relay is an intermediary and terminates TLS, so traffic is
encrypted in transit and readable at the relay. This is **not** end-to-end
encryption and must never be described as such.
**Why it is unusual.** Handing someone a working link to software running on your
laptop normally means a tunnel, a deploy, or both.

### Your existing Claude Code setup is picked up as-is

**Claim.** Point `co ai` at a repo you already work in and it reads the context you
already wrote — `CLAUDE.md`, `README.md`, git status, and the skills in
`.claude/skills/`.
**Proof.** `cli/co_ai/context.py:57-95` for the project context;
`useful_plugins/skills.py:123-130` for the `.claude/skills/` load path.
**Default or opt-in.** Default.
**Limit.** As above, Claude Code's `allowed-tools` key is not read, so a skill's
auto-approvals do not carry over.
**Why it is unusual.** Adoption cost is usually a migration. Here the setup someone
already did counts.

### You can talk to it while it is working

**Claim.** You do not have to wait for the agent to finish to redirect it. Type
mid-run and the message is folded in at the next iteration.
**Proof.** `useful_plugins/runtime_input.py:22-28`.
**Default or opt-in.** Default in `co ai` (`cli/co_ai/agent.py:107-118`).
**Limit.** It lands at the next iteration boundary, not instantly.
**Why it is unusual.** The normal choice is to let a wrong run finish or kill it.

### The agent redraws its own interface, mid-conversation

**Claim.** The agent changes what its users see by writing an HTML file. The new
version is in their browser at the end of that run — no deploy, no build, no release.
**Proof.** The agent edits `dashboard.html` with the same file tools it uses for
anything else — `connectonion/cli/co_ai/skills/builtin/dashboard/SKILL.md:9-16`.
The host notices by mtime+size (`ws_router/dashboard.py:77-99`) and pushes a
`DASHBOARD_SNAPSHOT` after any run that changed it (`ws_router/agent_io.py:70-74`);
the pane re-renders (`../oo-chat/components/dashboard/dashboard-pane.tsx:52-53`).
There is no polling and no fetch.
**Default or opt-in.** Default.
**Limit.** 2 MB. Over that, no dashboard is sent at all rather than a truncated one
(`dashboard.py:22-31,57-63`). Images must be inlined as `data:` URIs.
**Why it is unusual.** Changing a normal product's UI is a pull request. Here it is
something the agent can do because a customer asked it to, while they are talking.

### Every agent has a dashboard on day zero, with its skills already as buttons

**Claim.** You do not build the dashboard. If the agent has no `dashboard.html`,
one is written for it — the agent's name, and up to four of its skills as working
buttons.
**Proof.** `ensure_dashboard()` and `render_starter()` —
`ws_router/dashboard.py:102-155,136-207`; wired in at `network/host/server.py:494-496,616-618`.
**Default or opt-in.** Default, on first connect.
**Limit.** Four skills, and only ones published as `project`/`claude-project`;
personal and builtin skills are deliberately not exposed (`useful_plugins/skills.py:96`,
`server.py:155-167`).
**Why it is unusual.** The starting point is a working control panel, not an empty one.

### A button on the dashboard runs a real skill, and you can see it happen

**Claim.** Dashboard buttons are wired to the agent's actual skills. Clicking one
produces a visible turn in the chat next to it, so there is no hidden action.
**Proof.** `<button data-ochat-skill="daily-brief" data-ochat-args="today">` →
bridge `postMessage` (`../oo-chat/components/dashboard/build-srcdoc.ts:64-82`) →
parent validates and sends `/daily-brief today` as an ordinary chat message
(`dashboard-pane.tsx:55-71`, `../oo-chat/app/[address]/[sessionId]/page.tsx:174-177`).
**Default or opt-in.** Default.
**Limit.** The click is untrusted intent, and is treated that way: source-frame
check, name must match `^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$`, must be in the agent's
published skill list, **fails closed while that list is loading**, args collapsed
and cut to 500 chars (`dashboard-pane.tsx:26,56-67`).
**Why it is unusual.** Most dashboards report. This one is the remote control, and
every press leaves an auditable line in the conversation.

### Agent-written HTML runs with no network access at all

**Claim.** The agent authors the page, and that page cannot phone anywhere,
cannot run the agent's own scripts, and cannot navigate away.
**Proof.** `sandbox="allow-scripts"` without `allow-same-origin`, so an opaque
origin with no access to the host page's storage or keys (`dashboard-pane.tsx:110`).
CSP `default-src 'none'; style-src 'unsafe-inline'; img-src data:; font-src data:;
script-src 'nonce-…'` (`build-srcdoc.ts:52-62,107-111`) — the agent's `<script>`
and inline `onclick` never execute. Non-fragment `<a href>` clicks are cancelled
and a second iframe load is treated as navigation-away and blocked
(`build-srcdoc.ts:78-79`, `dashboard-pane.tsx:40-48,77-88`).
**Default or opt-in.** Default, not configurable.
**Limit.** This is also a real constraint on what you can build: no external
images, fonts, stylesheets, or API calls from the dashboard.
**Why it is unusual.** "LLM-generated UI" normally means trusting generated markup.
Here the HTML is wrapped in a document we own rather than edited or sanitised
(`build-srcdoc.ts:92-105`), because string-matching someone else's `<head>` is
defeatable and a sanitiser that is wrong once is wrong forever.

### There is no account. A link is the whole onboarding.

**Claim.** The person you send it to installs nothing and signs up for nothing.
They open a link — or scan a QR code — and start talking.
**Proof.** Shareable `https://chat.openonion.ai/{address}` plus a client-side QR
(`../oo-chat/components/qr-share.tsx:9,30,70`). Identity is generated silently on
first load: BIP39 phrase → Ed25519 keypair in localStorage, signed for a JWT
(`../oo-chat/hooks/use-identity.ts:107-141,16-40`). No email, no password.
**Default or opt-in.** Default.
**Limit.** Because the key is in that browser's localStorage, a different browser
is a different identity unless the recovery phrase is imported
(`use-identity.ts:159-176`). The phrase is shown once and re-exportable from
Settings (`:104-118,197-207`).
**Why it is unusual.** No signup form is a conversion story, but the sharper part
is that the *credential* is generated locally and never handed to us.

### Strangers can be gated by an invite code or a payment — not a login

**Claim.** An agent exposed to the public can require something before it will
work for someone new, and that something can be money.
**Proof.** `onboard_required` card offering invite code or payment
(`../oo-chat/components/chat/messages/onboard-required.tsx:19-31`); server side,
`invite_code` and `payment` onboard methods, with payment verified against
oo-api `/api/v1/onboard/verify`.
**Default or opt-in.** Opt-in, configured per agent.
**Limit.** Payment verification depends on the OpenOnion API.
**Why it is unusual.** The usual answer to "how do I stop strangers draining my
credits" is an auth provider and a billing integration. Here it is a setting.

### Skills written in Claude Code or Codex are the same files

**Claim.** A skill is a `SKILL.md`. ConnectOnion reads the ones already in
`.claude/skills/`, and `co skills discover` also finds Codex, Cursor and Kiro ones.
`co skills link` pushes ours the other way, into Claude Code and Codex.
**Proof.** Runtime load path includes `.claude/skills/<name>/SKILL.md` and
`~/.claude/skills/…` (`useful_plugins/skills.py:117-136`, tagged at `:207-212`).
Discovery additionally scans `~/.codex/skills`, `~/.cursor/rules` (`.mdc`),
`~/.kiro/steering` (`skills_commands.py:36-43,95-139`). `link` symlinks bundled
skills into `~/.claude/skills` and `~/.codex/skills` (`:334-391`).
**Default or opt-in.** The `.claude/` runtime paths are default. Codex/Cursor/Kiro
are `co skills discover` + `copy`, not the runtime path.
**Limit — state this one.** Permissions come from the `tools:` key
(`skills.py:346,393`). Claude Code's `allowed-tools` is **not** read — grepping
`connectonion/` for it returns nothing. So a Claude Code skill runs its
instructions unchanged but grants no auto-approvals. Say **"reads the same
SKILL.md files"**, never "runs identically".
**Why it is unusual.** The work someone already did in another tool is not thrown
away, and it is a file rather than an export.

### A skill's extra permissions expire when the turn ends

**Claim.** A skill can widen what the agent may do while it runs, and the widening
is withdrawn automatically afterwards.
**Proof.** On invocation the plugin snapshots `session['permissions']`, grants each
pattern with `source: 'skill'` and `expires: {'type': 'turn_end'}` — `Bash(git *)`
becoming `when: {'command': 'git *'}` (`skills.py:246-287`). `cleanup_scope`
restores the snapshot at `on_complete` (`:290-296,359-362`).
**Default or opt-in.** Default, for any agent loading the skills plugin.
**Limit.** Patterns are fnmatch, not a shell parser
(`useful_plugins/tool_approval/__init__.py:104-132,146`). Write them tightly.
**Why it is unusual.** The usual choice is a permanent allowlist or approving the
same command forever. This is neither.

### A logged-in browser that stays logged in, driven from the terminal

**Claim.** `co browser` runs a persistent daemon that owns one real browser. Log in
once by hand; every later command reuses that session. No Python.
**Proof.** Daemon over a Unix socket / named pipe, browser stays open until
`co browser close` (`cli/commands/browser_commands.py:20-40`,
`cli/browser_agent/daemon.py:2-8`). ~40 operations including
`wait_for_manual_login`, `upload_file_by_selector`, `extract_items_by_selector`,
`take_screenshot`, `run_page_script` (`useful_tools/browser_tools/browser.py:667-2002`).
`co browser do "<instruction>"` puts an LLM agent on that same live browser
(`daemon.py:6`).
**Default or opt-in.** Available immediately after install.
**Limit.** One browser, with multi-agent tab contention signalled by exit code 4
(`browser_commands.py:24-41`).
**Why it is unusual.** It dissolves the usual blocker for automating a customer's
internal system: the login. You do it yourself, once, and hand the session over.

---

## What was cut, and why

Keeping this list is the point. It stops the same false claim being rediscovered
and shipped next quarter.

| Candidate | Why it was cut |
|---|---|
| "Calendar from the command line" | No `co calendar` command exists. Calendar is Python-only (`useful_tools/google_calendar.py`, `microsoft_calendar.py`). `co auth google` unlocks Gmail/Drive/Outlook on the CLI, not calendar. |
| "Claude Code skills run identically" | `allowed-tools` is not read, so auto-approvals do not carry. Downgraded to "reads the same SKILL.md files" and kept with the limit attached. |
| "Native mobile apps" | Responsive web only. No native client, and no PWA manifest in `../oo-chat/public/`. |
| "We list the OAuth scopes we request" | Scope list is server-supplied and not in this repo (`commands/auth_commands.py:191,285`). Cannot cite it, so cannot claim it. |
| "End-to-end encrypted" | Still false, still worth repeating. No payload encryption exists anywhere. Transport is TLS to a relay that terminates it — encrypted in transit, plaintext to the relay. |
| Anything counting lines of code | Retired on purpose. Nobody writes those lines; the CLI writes the project. |
| "`co ai` has slash commands `/init /help /cost /compact /tasks /export /sessions /new /resume /undo /redo`" | Defined in `cli/co_ai/commands/__init__.py:39-52`, but `BUILTIN_COMMANDS` is imported nowhere at runtime. **Not wired today.** The slash commands that do work are skill names — `/commit`, `/review-pr`, `/ship-feature`, `/dashboard`. |
| "`co ai` keeps a session history you can resume" | `cli/co_ai/sessions.py` (SQLite at `~/.co-ai/sessions.db`) is only used by those unwired commands. What is real is host-side `SessionStorage` and `GET /sessions/{id}` (`network/host/server.py:445-447,514`), plus logs and evals under `~/.co`. |
| "`co ai` can send email" | Email is not a wired tool on that agent. It is reachable as a CLI command (`co email send`, `co gmail`) after `co auth google` — a separate, opt-in path. |
| "`co ai` ships explore and plan subagents from its own registry" | The live subagents come from `useful_plugins/builtin_agents/`. `cli/co_ai/agents/registry.py:26-39` defines the same two but is imported only by its own `__init__` and tests — the running agent never imports it. Claim the capability, not that file. |
