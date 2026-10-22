# REM PDF dependency repair — unreleased candidate

Issue #2631 raises the minimum pypdf version from 6.19.0 to 6.21.1 and updates
its resolver-generated lock entry. This addresses the five pypdf advisories
reported by the current release audit while preserving Python >=3.10 support.
PDF body/annotation extraction and unreadable-file policy are unchanged.

The candidate is not a published release and has not been installed over the
user's preview. The complete dependency audit still fails on Pillow; no advisory
ignore or compatibility promise is changed. Native REM desktop/phone acceptance
and actual document/claim verification remain outstanding. Tests of invented
PDFs are not proof that every real attachment or generated memory is correct.

See [review evidence](../design-evidence/rem-pypdf-2026-10-22/REVIEW.md). Public
versioned release notes and installation guidance follow only after an eligible
reviewed immutable tag and public artifacts exist.
