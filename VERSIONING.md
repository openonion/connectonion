# ConnectOnion Versioning Rules

## Version Format
We follow semantic versioning: `MAJOR.MINOR.PATCH`

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

## Current Version: 1.5.10

### Version History
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
- 1.5.4 (a deployed agent is reachable and controllable: it runs as the user that owns its files rather than root, `co` is on its PATH so `co call <address> co status` works, and the operator's own key is recognised by their agent's trust gate instead of being asked to onboard; a deploy that leaves the agent crash-looping now says so and prints the traceback, where it used to report success and a URL; `co server new` waits until the machine actually accepts your key before calling it ready, and clears the stale host key when a cloud address is reused; skills carry their own files but never their secrets, and `co skills copy --to-project` puts one where a deploy will find it; the test suite can no longer write to the operator's real ~/.co, which had silently replaced a live Outlook session with test credentials)
- 1.5.2 (Claude calls carry the system prompt again — Anthropic requests had been dropping it entirely and silently; `.co/docs/` is no longer empty on a PyPI install, the 194 docs files now ship inside the wheel)

## Files to Update When Versioning

When updating version, these files must be changed:

### Python Package Files
1. `/connectonion/__init__.py` - `__version__` variable
2. `/setup.py` - `version` parameter

### Documentation Files
3. `/docs-site/app/page.tsx` - Version badge
4. `/README.md` - Any version references
5. `/docs-site/README.md` - Any version references

### Configuration Files (if present)
6. `/pyproject.toml` - version field (if exists)
7. `/package.json` - version field (if exists)

## Version Update Checklist

When releasing a new version:

- [ ] Update `__version__` in `/connectonion/__init__.py`
- [ ] Update `version` in `/setup.py`
- [ ] Update version badge in `/docs-site/app/page.tsx` (if exists)
- [ ] Update any version references in README files
- [ ] Commit changes: `git commit -m "Release vX.Y.Z: Description"`
- [ ] Create git tag: `git tag vX.Y.Z`
- [ ] Push commits: `git push`
- [ ] Push tag: `git push origin vX.Y.Z`
- [ ] Build package: `python setup.py sdist bdist_wheel`
- [ ] Upload to PyPI: `twine upload dist/*`

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
