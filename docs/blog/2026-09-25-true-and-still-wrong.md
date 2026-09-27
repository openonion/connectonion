# True, and still wrong

The audit's fake Sydney user had a client call at 4 pm. Their Microsoft
calendar, read through ConnectOnion, said:

```
- 2026-09-28 06:00 AM: Client call
```

Every character of that line was accurate. Graph returns event times as a bare
wall clock in UTC, and 06:00 UTC is 4 pm in Sydney. The line just did not say
UTC, so it was read the only way a person reads a time with no zone: as their
own. Then they booked a dentist at "16:00", and the confirmation came back
`Start: 04:00 PM` — which looked like agreement, while Graph had been sent
16:00 *UTC*, 2 am the next morning at home.

The Google side had fixed exactly this weeks earlier. Its comment says it
plainly: the event was fine, the sentence about it was not. `_format_datetime`
labels every time with its zone, and `_confirmed_time` echoes a create in the
offset the caller typed, so `16:00+10:00` comes back as `04:00 PM +10:00` and
can be checked character for character. The Microsoft tool had never been given
either. It now has both, and its free-slot list says its times are UTC too.

The same audit found Gmail's `reply()` making the same kind of mistake with
addresses. It always answered `From:`. Web forms and booking sites send from
`noreply@…` and put the actual person in `Reply-To:`, so a reply to "Jane
Customer via Website Forms" went to a mailbox nobody reads, and reported
success. Replying to your own sent message wrote to yourself. And it looked up
`Message-ID` with that exact capitalisation; a sender that writes `Message-Id`
— perfectly legal, header names are case-insensitive — produced a reply with no
`In-Reply-To`, which most clients show as a new conversation.

Now `reply()` reads headers case-insensitively, keeps the `References` chain,
answers `Reply-To` when there is one, and follows up to the original
recipients when the message was yours.

Both bugs are the same lesson: output can be true and still wrong, because the
reader fills in whatever it leaves out. A time without a zone gets the reader's
zone. A reply without a look at `Reply-To` gets whoever happened to press send.
The tests now fake Graph's zoneless strings and a noreply form exactly as they
arrive, and check the words a person would actually read.
