# The release that could not find itself

*2026-10-13*

Publish finished. The wheel was on PyPI. Then finalize asked PyPI for the
version's JSON metadata and got a 404. Twice — 1.9.2b16 and 1.9.2b20 — someone
had to rerun the failed job a minute later so the GitHub release could attach
the same bytes the index finally admitted.

The job already waited for `pip install connectonion==$VERSION` to succeed. The
next step did not wait. `verify_published_artifacts.py` read
`/pypi/connectonion/<version>/json` once, wrapped the 404 as `ArtifactError`,
and stopped. install.sh had learned the same lag for strangers' first installs
(#2457). Finalize had not learned it for its own metadata check.

It now retries that JSON read for a couple of minutes when the answer is 404,
and still fails immediately on anything else. A missing digest or a wrong host
is not a race. A brand-new version that publish just uploaded often is.
