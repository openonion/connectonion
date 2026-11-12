# rc14 optional dependency security acceptance

The default-only rc13 audit was clean, but GitHub retained a low-severity
Paramiko 4.0.0 SHA-1 alert in the optional Synology extra. The advisory's empty
patched-version field was not evidence that no release existed: primary PyPI
metadata and upstream changelog confirm Paramiko 5.1.0 is available and removes
SHA-1-era behavior. Remove our <5 cap and require >=5.1.0.

Audit scope is expanded to all extras in CI, including optional dependencies.
The local all-extras pip-audit 2.10.1 run reports no known vulnerabilities, with
no ignored advisories. Tests and an isolated loopback SSH check are recorded
separately after completion. No actual NAS or production scheduler is touched.

Upstream: https://www.paramiko.org/changelog.html
Advisory: https://github.com/advisories/GHSA-r374-rxx8-8654

The isolated loopback check passed using actual Paramiko 5.1.0 SSHClient,
RSA private-key loading, a dedicated known-host file and RejectPolicy. Public
key authentication succeeded and the default RSA signature was rsa-sha2-512.
Temporary keys were removed. This does not certify a real Synology NAS or a
legacy SHA-1-only server. Reproducer and result are in the adjacent evidence
directory.

Focused validation passed 99 tests covering security floors, optional audit
scope, Synology adapters, handoff release pinning and version consistency.
The rc14 wheel and sdist passed twine checks. Native Schedule acceptance is
unchanged and remains unverified. Full CI and publication are separate gates.

Independent AI code review (founder/marketing/UI role) found no code blocker
for the scoped dependency update, while requiring the legacy SHA-1 NAS
compatibility boundary to be documented. Independent rendered-phone/trial
review flagged P1 hardware-coverage ambiguity: release notes now explicitly
state loopback-only validation and no NAS-model certification. P1 native
scheduling acceptance stays open and is explicitly excluded from this
release. P2 dense italic callout text is readable at 390px, though only this
page and viewport were inspected. Recheck: modern SSH requirements and the
no-native-migration boundary must appear before installation; do not infer a
NAS or native scheduler pass from the loopback or MCP initialization tests.
