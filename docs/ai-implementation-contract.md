# The AI Implementation Contract

An issue that describes only the code change makes an AI session guess the
operating contract: which release line owns the work, whether a real browser
journey is required, what evidence must be attached, whether publication is
authorized. Guessed contracts fail in the same places every time — backend
unit tests pass while invitation onboarding, Host ↔ React ↔ O Chat
integration, mobile UI, approvals, reconnect, release artifacts, or
documentation were never exercised.

The fix is a scoped, configurable section embedded in each feature/bug
issue. It is not a prompt asking an AI to "finish everything"; it is the
contract the session executes against. The canonical section lives in
`.github/ISSUE_TEMPLATE/feature_request.md` (the bug template carries the
smaller relevant subset). Repository-specific templates may add detail but
must retain the same vocabulary. Tracked in #1123.

## Repository-specific defaults

### ConnectOnion Core

- Start stable work from the exact stable tag; never back-merge preview `main`.
- Test protocol writers, permission authority, migration, packaging,
  Windows/Linux, and installed artifacts.
- If a change can alter browser-visible behavior, Core unit tests are
  insufficient: require the React/O Chat consumer journey.
- Every stable patch opens a dedicated `forward-port-required` tracking issue
  before its PR merges. After verified publication, forward-port every
  applicable fix, regression test, migration, documentation change, and
  operational contract into every active higher line, at minimum the current
  preview. Keep the tracker open until each PR merges and passes CI.
- Do not copy stable version/channel metadata into a preview merely to create
  ancestry. Resolve the product commits against the newer architecture.
- A newer preview, RC, or next-minor Stable cannot publish while any
  `forward-port-required` tracker remains open.

### `@connectonion/react`

- Own typed OIP normalization, compatibility, acknowledgement, reconnect,
  and browser authority.
- Pack the exact candidate tarball and install it as a consumer would.
- Run the O Chat journey against that tarball before publication.
- No browser storage or optimistic UI state can increase Host authority.

### O Chat

- Begin at invite-code onboarding and continue through a real connected prompt.
- Exercise Default/Safe/Full access, approvals, reconnect/error, Work Room,
  Stop, resume, and Control Center when relevant.
- Run desktop and phone layouts with no overflow or hidden essential controls.
- Attach changed-surface screenshots directly to the PR in addition to CI
  artifacts.

## Default complex acceptance task

For native Codex/Claude Code Work Room changes, use a task long enough to
exercise multiple states:

1. inspect a clean workspace;
2. design a C sorting algorithm;
3. write `sort.c` and a non-trivial `test_sort.c`;
4. compile with strict warnings;
5. run normal, duplicate, sorted, reverse, empty, and large inputs;
6. trigger at least one genuine approval when the selected profile requires it;
7. fix a discovered issue;
8. rerun compilation/tests;
9. finish with a concise result.

The purpose is UI/state coverage — not artificial step inflation. The
evidence should include several meaningful provider activities, approval,
terminal success/failure, files, reconnect/Stop where in scope, and the
final result.

## Upstream UI learning

For coding-agent UI work, perform a fresh audit of the current public Codex
UI and other explicitly named references at implementation time. Extract
transferable interaction principles — progressive disclosure, semantic
summaries, approval placement, status hierarchy — not private assets,
branding, or provider protocol.

Happy Coder may inform the native-provider → normalized-event → frontend
translation pattern. OIP remains our protocol and authority boundary.

## Guardrails

- A template checkbox does not authorize a release, deployment, destructive
  action, or repository-setting change; the issue must select the exact
  allowed release action.
- "Fix all issues" means all issues in the named acceptance scope, not
  unrelated repository backlog.
- Do not claim an expert audit occurred without recording findings and
  evidence.
- Do not hide failures by replacing real integrations with mocks; mocks
  support deterministic coverage, and a named real journey supplies
  acceptance.
- Do not put raw prompts, secrets, credentials, private local paths, or
  reasoning traces in screenshots or protocol fixtures.
- Comments and file headers explain non-obvious boundaries; they must not
  restate the code or become stale duplicate documentation.
