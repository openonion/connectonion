# PDF dependency repair — candidate, 2026-10-22

Issue #2631. Base main e9bc54d1285d104715bcfa62b985f0f4cd5b8191.
Current published/installed preview remains 1.9.3rc12; this change is unreleased.

The exact-head release audit of the temporal-provenance candidate reported five
pypdf advisories in 6.19.0, plus 24 separate Pillow advisories. An earlier
Pillow-only description of the gate was incomplete. PDF text is one input to REM
memory; resolving this supported dependency failure is necessary before publishing
another preview, and is not proof of the correctness of generated memories.

Official PyPI 6.21.1 metadata requires Python >=3.9, is not yanked, and supplies a
universal wheel. We preserve the repository's Python >=3.10 promise, raise the
pypdf floor to >=6.21.1 and regenerate its package entry with uv 0.6.16. Only the
project requirement and matching pypdf lock metadata/hash change. No extraction,
privacy, pointer, error policy, other dependency, version or advisory-ignore code
changes. Source: https://pypi.org/pypi/pypdf/6.21.1/json

## Evidence

- Before: exact CI lock audit reports five pypdf advisories (issue #2631).
- After: frozen non-development lock export and strict pip-audit 2.10.1 report
  pypdf 6.21.1 with zero advisories; the audit still exits nonzero for **24 Pillow
  advisories**. This is a partial security repair, not a clean overall audit.
- `uv lock --check` passes, 118 resolved packages.
- Existing attachment, read-file, reader-model and warning tests run against the
  patched library: **64 passed in 10.50s** on Python 3.11. This includes actual
  invented PDF body extraction, empty page, annotation text/stamp limitations,
  attachment previews and original-file link context; not only mocked imports.
- The same 64 related tests pass on **Python 3.10.21 with installed pypdf
  6.21.1**, in 22.11s (one upstream Google Python-support warning). This is a
  separate frozen-lock disposable environment, not metadata-only compatibility.
- Full offline suite under patched pypdf 6.21.1: **16,969 passed, 334 skipped,
  7 warnings in 182.80s** (Python 3.11, four workers, excluding slow, real_api
  and network markers).
- Independent AI source/copy review approved 62f37c1; final committed-head
  confirmation pending after the requested extraction-code wording clarification. No real mail, model, provider or init run, no notebook write,
  and no browser/render/screenshot attempt.

Pillow compatibility, native desktop/phone evidence and the normal reviewed
immutable release process remain independent gates. No new version is assigned.
