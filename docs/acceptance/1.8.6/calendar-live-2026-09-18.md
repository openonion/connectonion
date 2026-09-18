# Calendar full journey — 18 September 2026

Candidate: `main` at `b4a73c0f` (published as **1.8.6a2**). Run against the real
Google account `openonionai@gmail.com`, inviting our own Outlook mailbox
`xietianle@outlook.com` so that **delivery is verifiable from the other side**
without involving anybody outside the company. Times are UTC.

> #1547 asks for one thing above all the others: *distinguish API acceptance
> from confirmed email delivery.* That distinction is the reason the issue
> exists — the original bug returned a well-formed success for an invitation
> that reached nobody. So every step below is confirmed twice: once from
> Google's own record of the event, and once from the invited mailbox.

## Setup

- Organiser: `openonionai@gmail.com`, through `co gcalendar`.
- Invitee: `xietianle@outlook.com`, read back with `co outlook inbox`.
- Event `9k1cv3k3229p75hus8q2ltcm4g`, titled `ACCEPT-cal-133803`.

## The journey

**1 — Invite.** `co gcalendar create … --attendees xietianle@outlook.com --yes`

```
Event created: ACCEPT-cal-133803
Start: 2026-09-25 10:00 AM +10:00
Invitations sent: xietianle@outlook.com
```

Two merged fixes are visible in those three lines: the confirmation *names who
was notified* (#1548), and the time is shown with its real offset rather than
converted to UTC (#1550/#1552) — an event at 10:00 +10:00 used to print as
06:30 AM and read as the wrong meeting.

**Delivery confirmed** in the invited mailbox 10 seconds later:

```
From:    openonion ai <openonionai@gmail.com>
Subject: Invitation: ACCEPT-cal-133803 @ Fri Sep 25, 2026 10am - 10:30am (AEST)
Date:    2026-09-18T03:38:21Z
```

**2 — Accept.** The attendee's `responseStatus` was set to `accepted`.

*This half is synthetic and is labelled as such.* A genuine accept is a click in
somebody's mail client. What #1558 fixed is whether **adding a second attendee**
wipes an existing RSVP, and that code reads the field, not the gesture that set
it — so a field set through the API exercises the same path. The click itself
remains unexercised.

**3 — Add an attendee.** `co gcalendar update … --attendees "xietianle@outlook.com,aaron@openonion.ai" --yes`

Read back from Google:

```
xietianle@outlook.com -> accepted
aaron@openonion.ai    -> needsAction
```

**This is the bug #1558 fixed, confirmed live.** Before it, the edit sent bare
`{'email': …}` records, which replace the stored attendee and reset
`responseStatus`: the person who had accepted was silently un-accepted by
somebody else being added.

**4 — Reschedule.** `co gcalendar update … --start 15:00 --end 15:30 --yes`

```
status: confirmed | start: 2026-09-25T15:00:00+10:00
xietianle@outlook.com -> needsAction
aaron@openonion.ai    -> needsAction
```

The accepted RSVP went back to `needsAction`, and that is **correct, not a
regression**. This call passed no attendee list at all — only `--start` and
`--end` — so the only actor that could have changed the field is Google, which
resets responses when the time moves because an acceptance was for the old time.
Recorded here explicitly so the next person reading a reset does not go looking
for #1558 again.

**Delivery confirmed:**

```
Subject: Updated invitation: ACCEPT-cal-133803 @ Fri Sep 25, 2026 3pm - 3:30pm
Date:    2026-09-18T03:40:23Z
```

**5 — Cancel.** `co gcalendar delete … --yes`

**Delivery confirmed** — the step the issue calls out as worse than never
inviting, because a meeting nobody was told about cancelling is one people still
attend:

```
Subject: Canceled event: ACCEPT-cal-133803 @ Fri Sep 25, 2026 3pm - 3:30pm
Date:    2026-09-18T03:40:49Z
```

## Result

| step | API accepted it | an email arrived |
| --- | --- | --- |
| invite | yes | yes, 03:38:21Z |
| accept | n/a — set through the API, see above | n/a |
| add attendee | yes, existing RSVP preserved | not separately checked |
| reschedule | yes | yes, 03:40:23Z |
| cancel | yes | yes, 03:40:49Z |

Every notifying step reached a real mailbox. The failure this issue was opened
for — `sendUpdates` defaulting to `none`, so the API succeeds and nobody hears
about it — does not reproduce on any of them.

## Not exercised

- **A real accept.** Clicking Accept in a mail client, and the organiser's copy
  updating from it. The RSVP-preservation path around it is covered; the click
  is not.
- **Whether the add-attendee step sent its own notification.** The event was
  correct and the later steps both delivered, but no separate email was looked
  for between steps 3 and 4.
- **External domains.** Both addresses are ours. A recipient on a domain that
  greylists or rewrites invitations is a different test.
