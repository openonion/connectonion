# Google 1.8.3 publication checklist

This is release preparation, not permission to publish. Stable remains 1.8.2
until the immutable-tag workflow publishes and verifies 1.8.3.

## Prepared

- SDK implementation and regression coverage: PR #1440.
- Local-only Google token ownership in oo-api: PR #230.
- Matching website documentation: docs-site draft PR #139; publish only after
  the package and GitHub release are public.
- Source version agreement: 19 passed; sibling-site check skipped because
  this isolated worktree has no sibling docs-site checkout. Public docs must
  not advertise an unpublished stable version.
- Candidate wheel and sdist build; both pass `twine check`.
- Disposable wheel installation and packaged runtime checks: 11 passed.
- CLI help and responsive documentation captures in `assets/v1.8.3/`.
- Forward-integration ledger: #1441.

## Before publication

- [ ] Confirm SDK #1440 is merged with all CI checks green.
- [ ] Verify deployed oo-api revision contains #230 and its health check passes.
- [ ] Complete `co auth google` interactively. Consent is the user's action;
  do not auto-accept or put token values into test evidence.
- [ ] Run read-only `co gmail inbox`, `co gdrive list`, `co gcalendar list`,
  `co youtube channel` against the consenting account. Record only outcomes,
  not mail bodies, file names, calendar details or tokens.
- [ ] Confirm actual granted scopes and token-file permissions locally without
  printing secret values; verify a fresh CLI process reuses the local login.
- [ ] Review the captures and complete before/after evidence where necessary.
- [ ] Merge the reviewed version-only release preparation PR.
- [ ] Obtain the explicit publication go-ahead, create the immutable `v1.8.3`
  tag, and let `.github/workflows/release.yml` publish through Trusted Publishing.
- [ ] Verify public package bytes and GitHub release, then update docs-site's
  stable version and publish its prepared Google documentation.

No real send, draft mutation, upload, event creation or delete was authorized
for acceptance. These paths use isolated regression fixtures, not an assertion
that production writes were exercised. TikTok and new messaging adapters are
outside this release and deferred until after 1.8.5.
