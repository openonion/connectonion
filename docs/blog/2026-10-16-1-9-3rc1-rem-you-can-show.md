# 1.9.3rc1: REM you can show

*2026-10-16*

Before calling `co rem` a release candidate we gave it the run a new user
gets: an empty notebook, `co rem init` over six months of real mail and coding
sessions, sixteen workers, overnight. Then we read the pages it wrote, claim
by claim.

The first thing the run found was not a wrong fact. It was pages that were
never kept. A page would finish its paid turns, then ask for the notebook lock
to save its sources, without waiting. Init's background import takes that
lock for every mail it saves, so the page failed with "busy" and its work was
thrown away: 26 of 63 pages, about half the tokens spent until then. No test
had both running at once. A finished page now waits for the lock.

On the fixed code the run kept 66 pages and refused none. Of the claims we
sampled, 17% were misleading, against 45% on the first notebook we audited a
week earlier, and none of the 14 project claims. No wrong phone numbers, no
invented quotes in 314 checked.

The other half of this release is the reader, because a page you trust still
has to be one you can find your way through. The home now opens on what is
waiting on you. A person page opens on what is between you: what you owe them,
what they owe you. Every citation says who, where and when, and opens the
original next to the line, with the quoted words marked. The longest person
page from the run went from 16,471 pixels on a phone to 3,183.

What is left is mostly judgement. A model still sometimes infers more than the
mail says, some finished threads are still shown open, and the same person can
end up with two pages. Those are the work between this candidate and 1.9.3.

```bash
python -m pip install --upgrade 'connectonion==1.9.3rc1'
```

See the [release notes](../releases/1.9.3rc1.md).
