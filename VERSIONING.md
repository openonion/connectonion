# ConnectOnion Versioning Rules

## Version Format
We follow semantic versioning, with PEP 440 pre-release suffixes:
`MAJOR.MINOR.PATCH`, `aN`, `bN`, and `rcN`.

Example: `0.0.2`

## Update Rules

### 1. **PATCH Version (X.Y.Z)**
- Increment by 1 for each release. That is the whole rule.
- It does not roll over. `1.5.9 → 1.5.10 → 1.5.11 → …` for as long as the work
  takes. Two digits are not a problem; a milestone nobody earned is.

### 2. **A whole number is earned, never reached**

`X.Y.0` and `X.0.0` do not arrive because a counter filled up. They are cut,
deliberately, when there is something to say — a body of work that is finished
and has been exercised end to end, not merely merged.

So there is no automatic `0.0.9 → 0.1.0`, and no automatic `0.9.9 → 1.0.0`.
If the next release is not that kind of release, it is another patch.

This rule exists because the alternative was tried. 1.5.9 was followed by a
1.6.0 bump on the mechanical reading — a minor, the version people are meant to
sit on — for a scheduler that had not been tested yet. Testing it immediately
found four bugs, including a weekly job that was silently skipped for a whole
week after any downtime. It shipped as **1.5.10** instead, and 1.6.0 stayed
available for a release that has earned it.

### 3. **What a `X.Y.0` claims**

That the work in it is done being stabilised, and that someone has run it, not
only that its tests pass. While a feature is still being proven it ships in
patch releases; the minor is the statement that it no longer needs to be.

### 4. **MAJOR Version (X.0.0)**
- Reserved for breaking changes, or for a stable release worth naming
- Same rule as any whole number: earned, not reached

Stable users remain on 1.6.0 while the 1.7.0 feature train is exercised through
alpha, beta, and release-candidate builds. Pre-releases are opt-in and must be
marked as pre-releases on PyPI and GitHub.

## Current Version: 1.7.0a1

### Version History
- 1.7.0a1 (**the first 1.7 preview**: audience-scoped HTTP routes let an agent expose visibly public, contacts-only, and admin-only endpoints beside its existing WebSocket transport; ACP gains resumable sessions, ordered updates, official SDK conformance, tool approvals, MCP tools, and stable agent messages; Telegram messaging and safer attachment handling arrive; and billed operations now fail closed when ambient credentials belong to a different account. This is an opt-in preview; 1.6.0 remains the stable recommendation.)
- 1.6.4 (**`co gmail` reads malformed or unexpected HTML mail defensively** instead of letting one ordinary message break inbox listing.)
- 1.6.3 (**`co status` names the account commands actually use** and the source of each credential; billed boundaries refuse an inherited key that belongs to another project.)
- 1.6.2 (**an agent reads its own project trust configuration**: project discovery stops at the repository and home boundaries instead of silently treating global `~/.co` state as project state.)
- 1.6.1 (**the CLI fails closed instead of acting as the wrong account** when a working-directory `.env` shadows this machine's identity; Outlook HTML reads retain their links and malformed tokens no longer crash every command.)
- 1.6.0 (**safer remote agents and a cleaner credential boundary**: host identity and temporary session-status probes are signed consistently; relay profile updates reject stale or conflicting state; Microsoft OAuth credentials and refresh-token rotation stay on the CLI machine instead of being stored by the backend; project invite credentials are private and no shared default invite code is documented; email sending has traceable, tenant-scoped idempotency and resilient provider-error handling; paid mailbox upgrades can preserve the existing address and are charged atomically; portable skills, dependency floors, cross-platform tests, and exact-artifact release verification are hardened for a stable release.)
- 0.0.1b1 → 0.0.1b8 (Beta releases)
- 0.0.2 → 0.0.9 (Early production releases)
- 0.1.0 → 0.1.9 (Added multi-model support, CLI improvements)
- 0.2.0 → 0.2.9 (Documentation improvements, LLM refactoring, test coverage, CLI enhancements and fixes)
- 0.3.0 → 0.3.8 (Enhanced debugger, CLI status/reset, Windows support, email refactoring, network features, pytest migration)
- 0.4.0 → 0.4.1 (Automatic .env loading, event system, email API fixes, comprehensive CLI help)
- 1.0.0 → 1.1.0 (Stable release; cancelable scheduled email, scheduled replies)
- 1.2.0 (co browser multi-agent tab CLI: -t targeting, tab lifecycle, contention guard, exit-code contract, daemon race hardening; graceful interrupt; Patchright stealth pin)
- 1.2.1 (native Windows co browser via named-pipe transport; zero-setup chromium auto-install without admin; offline first-run hardening; windows-e2e CI)
- 1.3.0 (remote tool execution: remote.call / co call; codex tool via native app-server; agent balance in ANNOUNCE profile + /info; humanized browser input + stealth; Gemini 3.6 Flash; bash description optional; browser-workflow-skill-builder; security: tightened default remote-exec whitelist)
- 1.4.0 (co gmail and co gdrive: your own Gmail and Google Drive from the terminal, plus the GDrive tool; co skills link publishes bundled skills to Claude Code and Codex; Outlook contacts; OAuth fixes: both .env and ~/.co/keys.env are loaded, rotated tokens persist, Gmail refreshes every session; credentials no longer printed in CLI tracebacks; Gemini 3.6 Flash everywhere)

- 1.5.0 (agent Home pages: the host pushes `dashboard.html` over the agent WebSocket and chat clients render it beside the conversation, with a built-in dashboard skill; `co syno` for Synology NAS; `co ai` YOLO mode; `co ai` and the templates drive the browser through `co browser` instead of 40 in-process tools; agents can declare how long they need a tab; deploy polls the full build window and validates project names locally; hermetic unit tests)
- 1.5.1 (`co status` says where every API key comes from and flags keys defined in more than one place, with an opt-in `--reveal`; the project states Apache-2.0 everywhere, matching the LICENSE file)
- 1.5.3 (servers you own: `co server new/add/ls/check/ssh/forget/destroy` and `co deploy --to`, with an SSH key derived from the same recovery phrase; a deploy no longer reissues the agent's address, keeps its logs, seeds the deploying key as admin, and serves it over https on its own hostname; the agent's full picture now travels over the authenticated socket instead of the open `/info`, which had been publishing the operator's personal skills to anyone; `co skills list` and `co doctor` say which tier a skill came from and which ones will not survive a deploy)
- 1.5.5 (**the recovery phrase now derives a standard key**: identity moves from a bare `seed[:32]` slice to SLIP-0010/SLIP-0013, so the twelve words mean something to any wallet rather than only to ConnectOnion — existing installs keep working from `.co/keys/agent.key`, but recovering from the phrase now lands on a different address, and `co status` says so; `co deploy --to` stops rsyncing the project's `.env` as ordinary source and sends it as a root-owned 0600 file systemd reads, which had been putting the operator's OAuth tokens on the server in plaintext; a model whose name starts with "o" is no longer assumed to be OpenAI's; a tool schema keeps the constraints its function declares; passing a class where an instance was meant fails at registration instead of at call time; the skill in your project wins over the bundled one of the same name; `xray.trace()` prints again; and a malformed trust policy names the file it is in)
- 1.5.6 (**a project stops being tied to the machine that made it**: `AGENT_CONFIG_PATH` no longer travels as an absolute path into a file that gets deployed, cloned and handed to colleagues; an agent answers to the name you gave it rather than the template's; `co server new` declines instead of crashing when there is no terminal to ask; a server you were charged for reaches the registry even if the rest of provisioning fails; a second agent no longer takes the first one's hostname; and `co server fix-key` makes a machine that will not take your key recoverable)
- 1.5.7 (**a per-server SSH key derived from the recovery phrase**, installed beside the old one rather than replacing it; the relay heartbeat never sends a frame it cannot sign, which it had been doing with a monotonic clock the freshness check reads as decades off; and a released fix reaches the agent on the next deploy instead of the one after)
- 1.5.8 (**paid onboarding could not succeed, and failed open when it could not run** — the two halves of the same gate; a token that names another account is refreshed rather than reused; the deploy stamp follows what was installed rather than what was asked for; and the pin test asserts the real version instead of one it hardcoded)
- 1.5.9 (**Home becomes a control panel**: the page says what the agent has been doing, shows its address and trust, and is the starter itself rather than a copy that drifts from it; **an agent keeps its own schedule** in `.co/schedule.yaml`, run by the host every minute; and `<co-table>` is documented for agents that write their own Home)
- 1.5.10 (**a schedule that will never fire says so** — a hand-written file reaches production, and a dropped entry is otherwise indistinguishable from one that is not due yet; Recent stops saying the same sentence three times. Released as 1.5.10 rather than the 1.6.0 that was prepared: see the rule at the top of this file)
- 1.5.20 (**paid quota without an address change**: `co email upgrade plus --keep-address` raises an existing `@mail.openonion.ai` mailbox to the Plus monthly quota while preserving the exact sender address, so a mailbox that has reached the free limit does not have to abandon the address its users already know.)
- 1.5.19 (**OAuth and status calls cannot wait forever on a broken network**: every Google and Microsoft authorization request, including polling and credential retrieval, now has a bounded timeout; `co status` likewise stops waiting after 15 seconds instead of hanging indefinitely. This patch is cut directly from the exercised 1.5.18 release and does not include the unreviewed 1.6.0 candidate.)
  Published on [PyPI](https://pypi.org/project/connectonion/1.5.19/) and as [GitHub release `v1.5.19`](https://github.com/openonion/connectonion/releases/tag/v1.5.19); both carry the exact artifacts preserved by the release build.
- 1.5.18 (**the wheel acceptance test installs the wheel it was given**: the build environment already contains ConnectOnion while it runs the artifact test, so pip must force-reinstall the candidate into the child virtualenv instead of treating the outer copy as satisfying it; this carries the same email retry fix through the corrected release gate)
- 1.5.17 (**the artifact job uses package metadata that actually exists**: 1.5.16 referenced a nonexistent `requirements.txt`; this installs the declared `.[dev]` dependencies and builds the safe-send candidate successfully, then stops before PyPI when the wheel acceptance child environment incorrectly reuses that outer build copy)
- 1.5.16 (**the email retry candidate passes the full cross-platform suite**: every send uses a traceable request id and tenant-scoped idempotency key so retrying an uncertain response cannot send the same message twice; publication stopped safely before PyPI because the artifact job referenced a `requirements.txt` that this project does not have)
- 1.5.15 (**the release runner can exercise what it built**: the tag job installs pytest and the package's runtime dependencies before running the wheel acceptance suite; 1.5.14 stopped safely before PyPI when that runner dependency was missing, so this carries the same email retry and security-hardening candidate through the repaired release path)
- 1.5.14 (**safe retries for email and a security-hardening test release**: every send carries a traceable request id and a tenant-scoped idempotency key through Connect, oo-api and Resend, so retrying an uncertain response does not send a duplicate; provider failures return stable JSON instead of hiding behind an HTML/JSON parsing crash; relay profiles and remote control frames are authenticated more strictly; credentials, deploy control files and generated projects are handled more defensively; dependency security floors are raised; and the release workflow now tests, preserves and verifies the exact artifacts it publishes; its first automated publish attempt stopped before PyPI because the artifact job itself had not installed pytest)
- 1.5.13 (**the Sent mailbox**: `co email sent` / `co email sent read <#>` and the `get_sent()` tool read back what the agent sent — recipient, status, provider message id, and the body — against oo-api's new /email/sent endpoints, closing the write-only asymmetry (#662) and making "did the server accept it?" answerable before a retry; `co syno login` probes past a candidate that answers 200 with an HTML page instead of dying on it (#736); and the relay imports websockets.exceptions explicitly, which websockets ≥ 14 no longer re-exports — the except that handles a dropped connection had been raising AttributeError at exactly that moment)
- 1.5.12 (**a backend blip is reported, not raised**: `send_email` and `co init`/`co auth` no longer crash with a JSONDecodeError when the gateway answers 5xx with an HTML page — the tool returns `HTTP <status> (the reply was not JSON)` so the caller sees the real status (#628, reported in production against 1.5.11); model pricing corrections including co/gpt-5 and the model our own agent runs on, and /cost totals now cover what the cost covers; `co browser` provisions a browser when a warm daemon says none is installed, runs headless where there is no display, and `co browser status` stops paying a second per call and says whether a browser actually exists; `co sub sync` survives a real published agent and no longer deletes a directory it did not create; reading an agent's logs no longer needs the key that pays for its models (#670); first run on a HOME that does not exist no longer ends in a traceback; a schedule entry can run a command, not only a prompt)
- 1.5.11 (**the dashboard stops claiming work succeeded when it does not know that**: `done` no longer covers a turn that failed, a failed entry says why, and an entry running right now says so; a turn that died with its process is not reported as running; a schedule entry does not start a second copy of itself while the first is still going; a relay reconnect no longer leaks a socket in CLOSE-WAIT; and the eval plugin stops billing a hardcoded provider)
- 1.5.4 (a deployed agent is reachable and controllable: it runs as the user that owns its files rather than root, `co` is on its PATH so `co call <address> co status` works, and the operator's own key is recognised by their agent's trust gate instead of being asked to onboard; a deploy that leaves the agent crash-looping now says so and prints the traceback, where it used to report success and a URL; `co server new` waits until the machine actually accepts your key before calling it ready, and clears the stale host key when a cloud address is reused; skills carry their own files but never their secrets, and `co skills copy --to-project` puts one where a deploy will find it; the test suite can no longer write to the operator's real ~/.co, which had silently replaced a live Outlook session with test credentials)
- 1.5.2 (Claude calls carry the system prompt again — Anthropic requests had been dropping it entirely and silently; `.co/docs/` is no longer empty on a PyPI install, the 194 docs files now ship inside the wheel)

## Files to Update When Versioning

Four files carry the package version, and `test_the_version_agrees_with_itself.py`
fails if they disagree — so a release that misses one is caught rather than
shipped.

1. `connectonion/_version.py` — `__version__ = "X.Y.Z"`. **The only literal.**
   `connectonion/__init__.py` reads it (`from ._version import __version__`)
   so that `co --version` need not import the package; there is nothing to edit
   there.
2. `pyproject.toml` — the `version` field. This is what the wheel carries.
3. `## Current Version:` at the top of this file.
4. `uv.lock` — the editable root package metadata; refresh it after a bump.

And one in the sibling docs repo, checked by the same test when it is beside
this one: `docs-site/lib/version.ts`. Stable releases update `STABLE_VERSION`;
pre-releases update `PREVIEW_VERSION` while the public site keeps advertising
the stable channel through `VERSION`.

The entry in the release list below is not optional either: a version with no
entry fails `test_every_release_has_an_entry.py`.

## Version Update Checklist

When releasing a new version:

- [ ] Update `__version__` in `connectonion/_version.py`
- [ ] Update `version` in `pyproject.toml`
- [ ] Update `## Current Version:` and add the release line in this file
- [ ] Refresh `uv.lock`
- [ ] Update the matching stable or preview channel in the docs site's `lib/version.ts`
- [ ] Draft or substantially update a Design Journal post for a feature-train
      launch, first beta, first RC, stable release, or material architecture or
      workflow decision. Maintenance-only patches need release notes unless
      they contain a reusable design lesson.
- [ ] Run the suite: `pytest tests/ -m "not slow and not real_api and not network"`
- [ ] Commit changes: `git commit -m "Release vX.Y.Z: Description"`
- [ ] Create git tag: `git tag vX.Y.Z`
- [ ] Push commits: `git push`
- [ ] Push tag: `git push origin vX.Y.Z`
- [ ] Remove artifacts from older releases: `rm -rf dist/`
- [ ] Build package: `python -m build`
- [ ] Validate both current-version artifacts: `python -m twine check dist/connectonion-X.Y.Z.tar.gz dist/connectonion-X.Y.Z-py3-none-any.whl`
- [ ] Check what you built: `pytest tests/e2e/test_the_wheel_works_when_installed.py -m slow`
- [ ] Upload only the two artifacts just validated: `python -m twine upload dist/connectonion-X.Y.Z.tar.gz dist/connectonion-X.Y.Z-py3-none-any.whl`
- [ ] After PyPI and the GitHub Release are visible, publish the docs-site
      version state and Design Journal. Verify the canonical URL, social and
      structured metadata, sitemap, AI-readable indexes, internal links, and
      mobile layout.

Replace `X.Y.Z` with the version being released. Do not upload the whole dist
directory with a wildcard: build does not remove older artifacts, so that can
mix a previous release into the current upload. PyPI uploads are not an atomic
transaction; one file can succeed before a stale or duplicate file fails.

The suite above it runs against the source tree, where every file is present
whether or not it is packaged. Nothing else looks at the artifact that goes to
PyPI, and a wheel has shipped without the documentation before — `co init`
reported ".co/docs/ (full documentation)" over an empty folder, which is what
the force-include note in pyproject.toml is about. That step installs the wheel
into a throwaway venv, outside the repo, and checks the data files the runtime
loads: the trust policies, the co_ai prompts, the project template, the docs,
and the `co` entry point.

## What Triggers Each Version Type

### PATCH (0.2.X)
Increment PATCH for:
- Bug fixes
- Documentation updates
- Small refactorings
- Test improvements
- Performance improvements (no API changes)

**Examples:**
- Fix authentication bug → 0.2.0 → 0.2.1
- Update wiki documentation → 0.2.1 → 0.2.2
- Refactor internal LLM code → 0.2.2 → 0.2.3

### MINOR (X.Y.0)
Cut a MINOR when:
- a body of work is finished being stabilised, and someone has run it end to end
- OR the API gained something worth announcing, backward compatible

Never because the patch counter got long. `1.5.11` is a fine version number.

**Examples:**
- Scheduler proven on a real deployment → 1.5.10 → 1.6.0
- Add new model provider → 0.2.5 → 0.3.0

### MAJOR (X.0.0)
Cut a MAJOR when:
- the API breaks
- OR the architecture changed enough that the old mental model no longer fits

**Examples:**
- Remove deprecated functions → 0.5.0 → 1.0.0 (breaking change)
- Complete API redesign → 0.7.0 → 1.0.0 (breaking change)

## Example Version Progression

```
1.5.7 → 1.5.8 → 1.5.9 → 1.5.10 → 1.5.11 → …
                                    ↓
                        proven end to end, so:
                                  1.6.0
```

The patch line runs as long as the work does. The whole number is a separate
decision, made by a person, about whether there is something to stand behind.

## Notes
- We moved from beta (0.0.1bX) to production (0.0.2)
- Each release increments the last digit by 1
- Nothing rolls over automatically — see rule 2
