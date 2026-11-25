# Jira live CLI acceptance — #2872 / #3249

Use an authorized read-only test account. Do not paste tokens, personal issue
content, or credentials into PR evidence. Synthetic fixtures cover writes.

1. Run `co jira verify --help`, configure site/email and enter a token with hidden
   input following that help. Record the package version and current Git SHA.
2. Run `co jira verify` and `co jira projects`; choose one accessible project and
   one non-sensitive test issue. Capture redacted terminal output.
3. Run `co jira changes --project ALPHA --issues ALPHA-1 --since
   2026-11-01T00:00:00Z --json` with real selected IDs/time, then
   `co jira show ALPHA-1 --project ALPHA --json`. Record exit codes, JSON validity,
   scope and visible ID/time/version. Expect no local source files.
4. Run `co jira show BETA-1 --project ALPHA --json` using a cross-project example;
   it must fail locally without reading BETA. Test empty change results with a
   valid recent time. Avoid any source-side modifications for this validation.
5. Run synthetic tests for auth/rate failure, pagination, malformed responses,
   scope enforcement, JSON-only stdout, changed versions and no content writes.
6. Keep generic nightly-stage and Reader citation acceptance separately marked
   unverified until the generic CLI caller/audit can exercise Jira. CLI unit tests
   are not evidence of full REM acceptance.

On 2026-11-25 the assistant exercised the previously user-selected CSBE project
and CSBE-1 through the actual CLI, using saved credentials. Verification and
project access succeeded; changes returned exactly CSBE-1 for the selected scope;
show returned CSBE-1. Both CLI processes exited 0, their stdout parsed as JSON,
and their Next lines were on stderr. No issue body or credential was printed.
The working tree was uncommitted, so this is local working-tree evidence, not
evidence for a new pushed commit. The GitHub Tests and blog-gate results must
still be checked on the revised pushed head.
