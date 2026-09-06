# Google 1.8.3 publication checklist

The owner authorized publication on 2026-09-07. Stable remains 1.8.2 until
the immutable-tag workflow publishes and verifies 1.8.3.

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
- SDK #1440 merged at `968dcd10991b62ca4e0cefd5c8ebf2a5d5f9fc3b` with
  all hosted Python/platform checks green.
- Local full regression after fixture correction: **8,121 passed, 22 skipped,
  211 deselected** (`not slow and not real_api and not network`). The synthetic
  Onionwright fixture now supplies the inert Linux metadata accepted by the
  installed version. No real paid session is started by this test.
- Existing-account production reads on 2026-09-05: `co gmail inbox`,
  `co gdrive list` and `co gcalendar list` exited 0. `co youtube channel`
  exited 1 with a `co auth google` recovery hint. Only outcomes were retained,
  not account content. The new consent attempt ended without completing;
  existing credentials were preserved.

## Before publication

- [x] Confirm SDK #1440 is merged with all CI checks green.
- [x] Resolve the local Onionwright fixture/dependency mismatch and rerun it.
- [x] Verify deployed oo-api revision contains #230 and its health check passes:
  `1ee5af128f0f1bf620719b161bbc0ae1b944c380`, deployment run `33963449009`.
  Service active and public relay health healthy on 2026-09-05.
- [x] Reuse the already completed Google consent. On 2026-09-07 a fresh
  candidate process successfully refreshed the existing local grant and read
  YouTube; another consent prompt was unnecessary. No consent was auto-accepted.
- [x] Run read-only `co gmail inbox`, `co gdrive list`, `co gcalendar list`,
  `co youtube channel` against the consenting account. Record only outcomes,
  not mail bodies, file names, calendar details or tokens. All four commands
  exited 0 from the installed candidate on 2026-09-07.
- [x] Confirm actual granted scopes and token-file permissions locally without
  printing secret values: all six supported Gmail/Calendar/Drive/YouTube scopes
  were present, both token types existed, and the credential file was mode 0600.
  Separate fresh processes reused that local login successfully.
- [x] Review desktop/mobile/CLI captures and include the prior installed CLI
  help for before/after comparison; the prior CLI has no YouTube group.
- [ ] Merge the reviewed version-only release preparation PR.
- [x] Obtain explicit publication go-ahead (2026-09-07).
- [ ] Create the immutable `v1.8.3` tag and let `.github/workflows/release.yml`
  publish through Trusted Publishing.
- [ ] Verify public package bytes and GitHub release, then update docs-site's
  stable version and publish its prepared Google documentation.

No real send, draft mutation, upload, event creation or delete was authorized
for acceptance. These paths use isolated regression fixtures, not an assertion
that production writes were exercised. TikTok and new messaging adapters are
outside this release and deferred until after 1.8.5.

## Final CLI audit correction — 2026-09-07

The consolidation had retained help-only tips for YouTube write previews.
Restored the full shell-quoted confirmation command for upload and update.
Operational goals now pass for all six YouTube entry paths with the pinned
`co/gemini-3.7-flash` text-only audit; no model-selected command is executed.
Focused regression: 57 passed, including quote preservation, explicit empty
descriptions, pipe output, help/skill parity, auth and confirmation binding.
