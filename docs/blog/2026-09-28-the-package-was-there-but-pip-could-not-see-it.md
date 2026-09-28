---
title: "The package was there, but pip could not see it"
date: 2026-09-28
---

# The package was there, but pip could not see it

The b22 release passed its test matrix. PyPI accepted the wheel and source
distribution, and its release JSON listed both files. Then our final release
job tried an exact `pip install` in a clean environment and got *No matching
distribution found*. The GitHub Release never appeared.

That sounded like a failed upload until we compared the two public answers.
PyPI's release JSON knew about b22. Its installer-facing Simple API still
served a project listing from before the upload. Repeating the same final job
three times did not make the two answers agree. A direct install of the public
wheel by its published SHA-256 URL worked, as did the local OneNote journey and
terminal audit.

The release has two separate questions: **were the reviewed bytes published?**
and **can an ordinary user install them by version yet?** Our original final
job treated those as one question. That is a useful gate for normal releases,
but it leaves a published package without GitHub assets when the registry's
index lags behind its file store.

The recovery path does not upload again or build a second package. It checks
that the original tag's tests, build and Trusted Publishing passed; downloads
that run's saved artifacts; compares them with both public PyPI files; installs
the public wheel by its hash; and creates the GitHub prerelease from those
verified public bytes. It is a separately reviewed, manually triggered job
because a release recovery should be more constrained than an ordinary retry.

This does not pretend the normal install command works. We still check the
Simple API and keep the docs site's exact-pin install instruction unpublished
until it sees b22. The distinction matters: a package can exist, be correct,
and still be temporarily undiscoverable to the person trying to install it.
