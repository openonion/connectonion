# The page that read five months

The first run of `co rem` on the owner's mailbox finished, and one page in it
was wrong in a way no check could catch. It described a contact at a university
startup program as the person who had recently written a support letter. Every
sentence on it was true and cited. It was still the wrong picture: this was the
person who had introduced the owner to investors, reviewed the white paper, and
backed the company through an accelerator. None of that was on the page.

The cause was not the model. The page had read the last 150 days of mail with
him: 13 of 38 messages. The relationship had started 15 months earlier. A page
can only be as old as the window it reads, and five months made a long
relationship look like a recent favour.

The same run had spent about one point of the owner's Codex week, against a
ceiling the owner was happy to set at twenty. The budget was not the limit; the
window was. And the window did not have to be small, because a wider window does
not mean a bigger prompt. Mail is written to evidence files that the model
searches, so two years of mail widens what it can find, not what every turn reads.

Getting there took more than changing one number. A first run that investigates
everything had three ways to stop early, each found by running it on real mail:

- One refused page ended the whole run.
- One mail body that timed out, 1 of 1,880, skipped every investigation.
- Every person re-read 1,300 coding sessions inside one Python process, so twelve
  threads queued behind each other at 13 minutes a person.

Each now has a test that failed before the fix.

With those out of the way, the first run writes the owner's page, then every
person, project and organisation, twelve at a time. When the material leaves a
gap, the model may ask for up to five mail searches. It still has no network:
our code runs the searches read-only and gives it one more turn with the results.

Measured on the same mailbox, against a checklist of the key threads with three
contacts:

| | before | after |
|---|---|---|
| key threads on the three pages | 3/8, 3/10, 4/7 | 7/8, 6/10, 6/7 |
| pages written on the first run | 82% | 86% |
| wall clock | 31 min | 35 min |
| Codex week used | one point | under one point |

The lesson: a page that is accurate sentence by sentence can still be wrong
about the whole, and only a reader who knows the whole notices. A spot-check
against the real history found it. The page's own checks could not.
