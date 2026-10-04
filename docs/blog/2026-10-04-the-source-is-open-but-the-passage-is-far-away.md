---
publishedAt: 2026-10-03T21:30:58Z
description: A long Skill run source needs a way to reach the cited words without losing the archived excerpt or its limits.
tags: [REM, Design, Evidence]
---

# The source is open, but the passage is far away

A citation beside a Skill finding gave the reader a way to open its archived
run. One real trial exposed the next obstacle: a phone source dialog could be
about 31,800 pixels tall. The full retained excerpt was available, but checking
a sentence meant scanning a long block of session JSON.

Long source dialogs now have a small Find control above the excerpt. Type a word
or phrase from the nearby finding to jump to the first occurrence; **Next
match** moves to the next one. The controls stay available as the excerpt
scrolls. Clear the search and the original text is still there. On a phone,
that preserves a short path from claim to passage without reducing the source
to a selected snippet.

Find searches what the notebook actually retained. If the stored excerpt is
truncated, the dialog says so. A highlighted word is a navigation aid, not a
validated claim span, and a match does not prove the surrounding finding.
The search sits inside the private source section, so hiding labelled passages
hides it as well.

An invented long Skill source was checked at 375 and 1440 pixels with two
matches, Next, privacy hide/show and close/focus. The [preview notes](/releases/1.9.0a38)
set out the limits. This reader change leaves existing memory and archived
source bodies untouched.
