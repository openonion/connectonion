# GitHub listener preview evidence

Branch: `feat/github-inbox-2147`, based on `016589a4` (1.9.0a18).
Target: the next unassigned 1.9.0 alpha preview after review; not published.

## Authentication and real reads

Used the owner's existing gh login through the adapter's GET calls. Read a real
issue/PR from `openonion/connectonion`, repository comments and PR reviews. No
GitHub mutations, copied tokens or credential-store reads were performed.

A complete scan of `wu-changxing/connect-onion-landingpage` from
2026-09-25T00:00:00Z produced 61 records (PRs and conversation comments), committed
its checkpoint, and took 58.09 seconds. New review submission, inline comments,
pagination, interrupted delivery and replay are additionally covered by fakes.
No live issue/PR was created just to test the listener.

The cost is material: polling reads every PR's reviews. This implementation is
experimental for small repositories. A large-repository scan and a production
GitHub Enterprise instance were not exercised. REST polling cannot recover
intermediate edits or content that was deleted before collection.

## Three-surface command audit

The README, docs-site and landing-page walls now carry GitHub (upcoming preview)
and TikTok plans. The Memory entry says `co rem`; `co wiki` was an older alias.
The docs wall also gains the existing Slack, Feishu/Lark, issues/feedback,
models and local/remote capability entries that were absent there.

Every top-level command is represented in the landing-page command inventory,
regenerated from the Typer command tree (50 commands). Commands such as auth,
keys, setup, status, reset, doctor and commands are setup/inspection operations
for those existing feature entries, rather than additional external services.
Copy/link operations map to skills; deploy/announce/call operations map to
remote agents and servers; transfer maps to credits; benchmark/eval map to
evaluations. A duplicate brand logo for each subcommand would obscure the wall.

The logo inventory is 53 cards on each website; README combines Feishu and Lark
into one card. Each README documentation target and each docs wall target is
checked against an actual source page. The landing page exports the same
inventory through `connections.md` and individual `logos/*.svg` endpoints.

Companion PRs will carry screenshots and build/lint results. The landing-page
logo endpoint must be published before the README's new hosted images are
expected to render on GitHub. The GitHub guide and card remain explicitly
unpublished until the feature is released.

## Final validation

The related inbox, consumer, listener, Host, CLI-help, CLI-discovery and command
tip tests passed: **1341 passed, 1 warning in 554.19s**. The warning was an
existing class-scoped fixture deprecation in `test_cli_discovery.py`. This run uses `TERM=xterm-256color`
because two existing color assertions depend on a color-capable terminal.
After the Host routing addition, the final GitHub and Host tests passed again:
**25 passed in 6.99s**.

```bash
TERM=xterm-256color PYTHONPATH=$PWD python -m pytest \
  tests/unit/test_inbox_github.py tests/unit/test_inbox_store.py \
  tests/unit/test_listen_commands.py tests/unit/test_inbox_settings.py \
  tests/unit/test_inbox_consumer.py tests/unit/test_listener_keeps_its_flags.py \
  tests/unit/test_listener_upgrade_and_autostart.py tests/unit/test_inbox_check_look.py \
  tests/unit/test_host_inbox.py tests/unit/test_cli_help_contract.py \
  tests/unit/test_the_inbox_skill_matches_the_cli.py tests/unit/test_cli_discovery.py \
  tests/unit/test_cli_tips_name_real_commands.py -q
python -m pytest tests/unit/test_host_inbox.py tests/unit/test_inbox_github.py -q
uv build
```

GitHub help audit: **12 pages, 0 findings**. The locally built wheel contains
the GitHub provider, commands and guide. No artifact was published and no
release tag/version was created.

Docs lint: 0 errors, 155 existing warnings. Docs production build uses
`npm run build -- --webpack` because this isolated worktree's node_modules is
symlinked to the existing installation outside the Turbopack root. Landing
`npm run lint:cli` and normal production build passed. Both walls were measured
at 1440×1200 and 390×844 with no horizontal overflow, and screenshots are
attached in the companion PRs. The Design Journal uses the docs site's existing
Markdown publication pipeline and its source/build checks.
