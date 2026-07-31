# ConnectOnion Versioning Rules

## Version Format
We follow semantic versioning: `MAJOR.MINOR.PATCH`

Example: `0.0.2`

## Update Rules

### 1. **PATCH Version (0.0.X)**
- Increment by 1 for each release
- When PATCH reaches 10, roll over to MINOR version
- Examples: 
  - 0.0.1 → 0.0.2 → 0.0.3 ... → 0.0.9 → 0.1.0

### 2. **MINOR Version (0.X.0)**
- Increment when PATCH reaches 10
- Reset PATCH to 0
- When MINOR reaches 10, roll over to MAJOR version
- Examples:
  - 0.0.9 → 0.1.0
  - 0.9.9 → 1.0.0

### 3. **`X.Y.0` is the stable release**

A minor is not just where the patch counter rolls over — it is the version people are
meant to sit on. So features do **not** ship straight into one:

- while a feature is being stabilised it ships in **patch** releases (1.5.3, 1.5.4, …)
- `X.Y.0` is cut once that work has actually been exercised end to end

Merged features on `main` therefore do not force the next release to be a minor bump.
That is semver's rule, not this project's.

### 4. **MAJOR Version (X.0.0)**
- Increment when MINOR reaches 10
- Reset MINOR and PATCH to 0
- Reserved for major breaking changes or stable releases

## Current Version: 1.5.3

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

### MINOR (0.X.0)
Increment MINOR when:
- PATCH reaches 10 (automatic rollover)
- OR adding new features (backward compatible)
- OR significant improvements

**Examples:**
- 0.2.9 → 0.3.0 (automatic rollover)
- Add new model provider → 0.2.5 → 0.3.0 (new feature)
- New CLI commands → 0.2.3 → 0.3.0 (new feature)

### MAJOR (X.0.0)
Increment MAJOR when:
- MINOR reaches 10 (automatic rollover)
- OR breaking API changes
- OR major architecture changes

**Examples:**
- 0.9.9 → 1.0.0 (automatic rollover or stable release)
- Remove deprecated functions → 0.5.0 → 1.0.0 (breaking change)
- Complete API redesign → 0.7.0 → 1.0.0 (breaking change)

## Example Version Progression

```
0.0.1 → 0.0.2 → 0.0.3 → 0.0.4 → 0.0.5 →
0.0.6 → 0.0.7 → 0.0.8 → 0.0.9 → 0.1.0 →
0.1.1 → 0.1.2 → ... → 0.1.9 → 0.2.0 →
...
0.9.9 → 1.0.0 (Major release)
```

## Notes
- We moved from beta (0.0.1bX) to production (0.0.2)
- Each update increments the last digit by 1
- When last digit reaches 10, it rolls over to the next level
- This ensures predictable, incremental versioning
