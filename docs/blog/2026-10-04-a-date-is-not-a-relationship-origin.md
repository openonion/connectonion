---
description: A Person memory turned the earliest retained reply into first contact and a booking time zone into a person's. Both citations opened, but neither proved the claim.
tags: [REM, Memory, Design]
---

# A date is not a relationship origin

The first message in a retained mailbox sample thanked someone for applying.
REM put that message's date in the Person page as `First contact`. A reader could
open the citation, but the message itself pointed backward to an application
whose date was absent. The page made the relationship look older or newer with
more certainty than the evidence allowed.

We compared all five cited messages in an actual Person page, then ran the
investigation again. The revised page left `First contact` Unknown and named
the earlier application as a gap. This exposed a second path for the same
mistake: the fact packet had automatically named the oldest retained mail
`First contact`, and the People index could fill an empty date from the map.
We removed that packet fact and made the index read only an explicit page fact,
including when an older index file is still present.

The new page still made another plausible leap. A booking displayed the
meeting in Australia/Sydney and listed the two participants. Its uncertainty
sentence assigned that time zone to one participant. The booking established
the event's display time, not anyone's own time zone. The Person instruction
now keeps those two claims separate unless an original labels the person's
time zone directly.

On a 375-pixel phone the same page hid the last word of its decisive outcome:
the role had been filled. We gave the Person summary room for five shorter
lines. In the sampled 375×812 render, the whole reason appears and the source
link remains a 44-pixel target within the first screen.

A second fresh investigation kept first contact and the target person's own
time zone Unknown. This time the page cited a calendar attachment that
explicitly labeled the invitee's time zone. But the reviewer found that its
short `Now` sentence, used by Home and the Person first fold, omitted the
sourced reason the thread had closed. We made that reason part of the Person
instruction. In a third fresh run, `Now` said the position was filled and the
intro canceled before saying no follow-up was proposed. An independent
role-based AI reviewer reopened all three displayed sources, Home and the
Person page at desktop and phone widths, and found no remaining P1 or P2 in
that sample. This is one protected Person, not a claim that every page is
accurate. The wider audit of claims that borrow authority from adjacent
originals remains open.

To try the change, use the [a33 preview notes](https://docs.connectonion.com/releases/1.9.0a33)
for the exact version and limits, then follow the
[REM first-run guide](https://docs.connectonion.com/rem#start).
