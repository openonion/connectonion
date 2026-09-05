# YouTube and TikTok first slice — draft design journal, 2026-09-05

This draft accompanies the implementation PR. It is not a release announcement
and should not be published as a shipped-feature claim before acceptance.

## Repository and design audit

The verified remote is `git@github.com:openonion/connectonion.git`. Work started
from `origin/main` at `74a54b4d` in an isolated worktree. The main development
checkout contained unrelated changes and was left intact. Existing `co`
conventions are Typer groups, lazy command handlers, reusable `useful_tools`,
Rich terminal output, numbered listings with full IDs under pipes, and one
literal next-command tip. No native YouTube/TikTok implementation or matching
PR existed in the repository search at the start of this task.

- [#261](https://github.com/openonion/connectonion/issues/261) requests YouTube
  upload, recent uploads, basic metadata updates and an own-video download idea.
  The useful first API slice is list/read, resumable upload and snippet update.
  Official Data API references do not provide a general video-file download
  operation, so no invented `get` media-download command is added.
- [#262](https://github.com/openonion/connectonion/issues/262) explicitly proposes
  a user-driven browser upload workflow for TikTok because the unaudited Content
  Posting API is unsuitable for the shared-client use case. Browser automation
  is not evidence of platform policy approval; this slice reaches only local
  planning and observed-page inspection.
- [#1426](https://github.com/openonion/connectonion/issues/1426) is a separate
  read-only creator-data proposal with new purpose-scoped OAuth grants,
  Analytics, and TikTok Display API prerequisites. It explicitly does not
  replace #261/#262. This PR does not close it, claim production app approvals,
  or implement its proposed command names/managed-auth contract.

## Decisions

YouTube uses the official Data API exclusively. Its CLI and reusable `YouTube()`
tool use the Google login saved by `co auth google`, with automatic
refresh through the same account-bound broker as Gmail. There is no YouTube
browser adapter or per-command token input.

The companion [oo-api #228](https://github.com/openonion/oo-api/pull/228) includes
YouTube in the standard Google consent bundle, with no separate CLI switch.
It records actual granted scopes, including partial consent, and reports
them on credentials/refresh responses. Legacy Gmail grants do not become
YouTube grants merely by upgrading the client: existing users run `co auth google`
once more to approve the added scope. A partial grant still connects the granted
Google tools and reports missing full YouTube access. This reuses the current
Google credential store; it is not #1426's separately namespaced read-only grant design.

Writes preview by default. Exact plan digests bind account, operation, file
bytes and metadata; updates also bind the current ETag. A private file snapshot
prevents a path change between confirmation and upload from changing the bytes
sent. Each plan is claimed atomically before a request, and a failed/uncertain
attempt remains consumed. Status is not part of metadata updates. This is a
CLI confirmation mechanism, not proof of human authorization; callers and
agents must still obtain the user's approval of the concrete plan.

TikTok's real upload URL redirected to login. Guessing a hidden upload form
would violate the required save-context/semantic-selector/verify workflow.
The delivered post command therefore makes an actual local plan, while the
confirmed path explicitly refuses submission. The login scanner verifies the
observed heading and still returns an overall failure. Upload and publish
remain unimplemented pending authorized form discovery and dedicated-account
acceptance. No Content Posting/Display/Research API is called.

## Current acceptance boundary

Automated tests use synthetic media, mocked YouTube responses, static discovery
request construction and jsdom fixtures. Only TikTok login state detection was exercised live. No test read a user's API credentials or
uploaded, changed, published, deleted or commented on content. Raw authenticated
screenshots/DOM captures remain local because sidebars can contain private data.

Before an actual YouTube write: connect an approved dedicated test account, verify
the target channel, review the exact plan, and explicitly authorize the single
upload/update. Verify returned visibility and processing separately. Before
TikTok upload: manually log in, capture the real form, implement/test exact
identity/file/caption/settings checks, obtain file-upload approval, then obtain
approval for the verified final publish plan. Final publish must be one-shot;
ambiguous outcomes stop for inspection.

Search/analytics/comments/captions/playlists/media download, TikTok Display API
and actual TikTok publishing remain
separate work. No package release or production deployment occurs in this PR.


## Verification recorded for review

- Client focused suite after unifying Google login: 580 passed, 3 skipped,
  covering creators, Google auth, Gmail, Drive, packaging and executable
  documentation examples. Minimum supported Typer 0.20 auth/CLI/help compatibility:
  84 passed.
- TikTok jsdom: 4 passed. Installed-wheel pipe checks and pinned text-only
  `co/gemini-3.7-flash` next-command checks: 9/9 each, covering seven creator
  leaves plus Google login's full and partial grants.
  The first harness incorrectly accepted three help-seeking replies; those
  results are superseded. Preview tips now name the exact confirmed operation,
  and TikTok planning points to the tab board. Model-returned commands were
  recorded, never executed. Nine exit cases and both help/skill comparisons
  are included in the PR audit tables.
- Backend complete mocked suite: 844 passed, 167 skipped; focused OAuth/state/
  migration suite: 74 passed.
- Client full suite after unifying Google login, under
  `PYTHON_DOTENV_DISABLED=1`: 7,369 passed, 660 failed,
  8 errors, 22 skipped, 182 deselected. The previous candidate had 659 failures;
  the additional failure is the missing 1.8.2 entry in VERSIONING.md and was
  reproduced on the untouched baseline. Existing environment/browser-loop
  failures remain. The previously documented Onionwright Artifact mismatch was
  also reproduced on both baseline and candidate. No creator/auth regression
  remains in the focused checks. The complete suite is not green.

The installed wheel contains the creator skill, two TikTok scripts and Google
refresh helper, with no YouTube browser scripts. No production deployment,
credential inspection or real API content write was part of this verification.
