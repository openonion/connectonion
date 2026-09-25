# The invitation with no link

A university student asked us for a meeting link. That was the entire request:
send me the link for Monday. So we ran

```
co outlook calendar teams "Kickoff call" 2026-09-28T16:00:00+10:00 2026-09-28T16:30:00+10:00 \
    --attendees student@example.edu --yes
```

and got back an error: `Event created (ID: AQMk...), but its Teams link is not
confirmed. Inspect this event; do not repeat creation.`

The error was honest, as far as it went. An earlier fix had taught the command
not to claim success unless Graph handed back a usable HTTPS join URL, and it
did not claim success. But by the time it said anything, the student already had
an invitation in their inbox: a calendar entry for Monday at four, from us, with
no link in it. The one thing they had asked for was the one thing missing.

## What Graph actually did

Reading the event back showed `isOnlineMeeting: False` and
`onlineMeetingProvider: unknown`. We had asked for a Teams meeting and Graph had
quietly created a plain event instead. It returned 201, it saved the event, and
Outlook mailed the attendees as it always does. It did not report an error.

The reason was the account. It was a personal outlook.com account, and Graph can
create Teams meetings only for work or school accounts. The calendar says so if
you ask it:

```
GET /me/calendar?$select=allowedOnlineMeetingProviders
→ allowedOnlineMeetingProviders: ['unknown']
```

A work account lists `teamsForBusiness` there. A personal one does not, and on
such an account `isOnlineMeeting: true` is ignored without complaint.

## Why checking afterwards could never be enough

The earlier fix checked the result, which is usually the right instinct: don't
believe a request worked until the response proves it. It fails here because
the harm happens inside the request. The POST that creates the event is also
the POST that sends the invitations. By the time the response arrives, the
attendees have already been mailed. Checking the response carefully can make
the error message more accurate, but it cannot unsend the invitation.

That changes where the check has to go. If the outcome can't be undone, the
command has to know it will succeed before it writes anything. Here that is
cheap: one GET on the calendar. `co outlook calendar teams` now reads
`allowedOnlineMeetingProviders` first, and if `teamsForBusiness` is not in the
list it stops with "This Microsoft account can't create Teams meetings ... No
event was created and no invitation was sent." A personal account can't
create Teams meetings through Graph at all, so the message doesn't suggest
retrying or investigating, because neither would help. It points to `create`
for anyone who wants to book the time with a link from another service.

The post-create check stays. An account that allows Teams can still, in
principle, come back without a link, and the command should still refuse to
call that a success. It is now the second check, and the first one runs before
anyone gets an email.

## The test

The regression test fakes Graph with a calendar that reports `['unknown']`,
records every call, and asserts that nothing except the GET went out: no POST,
so no event and no invitation. It failed on the old code with exactly the POST
the student received.

What we could not verify here is the live behaviour on a real personal account
or a real work tenant; the test fakes both. The field and its values come from
Microsoft's documented calendar resource and from the issue's own reading of an
outlook.com account.
