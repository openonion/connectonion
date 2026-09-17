---
title: The mention our own test could not make
date: 2026-09-17
---

# The mention our own test could not make

The owner typed `@` in a WhatsApp group, picked the bot, and sent `测试`. This
is what the bot wrote down:

```json
{
  "text": "@132754033377342 测试",
  "sender": "126121882435737@lid",
  "mentioned": false
}
```

The message arrived. It was parsed. Every field is right except the one that
decides whether the bot answers — and a group channel with `mention_only` reads
`mentioned: false` and stays silent. From the group's side: you @ the bot, and
nothing happens, forever.

## What `@132754033377342` is

Not a phone number. It is the account's **LID** — WhatsApp's newer internal
identifier, which is migrating accounts away from phone-number addressing.
Here is the linked device's own row:

```
jid              = 61410724095:2@s.whatsapp.net
lid              = 132754033377342:2@lid
lid_migration_ts = 1789610758          → 2026-09-17 01:25 UTC
```

One account, two ids, sharing no digits. Six hours before the test, WhatsApp
migrated this number. In a migrated group the mention carries the LID.

We read `Device.JID` and compared against that. `Device` has carried a `LID`
field all along; nobody read it. The comparison was not wrong — it was
*complete against a definition of identity the platform had stopped using*.

## The part worth sitting with

We have an end-to-end suite for exactly this. It links real numbers, sends real
messages over the real socket, and it has a test named
`test_in_a_group_only_a_message_naming_the_number_is_mentioned`. It asserts
`mentioned is True`. It passes.

It passes because of this line:

```python
driver.co("send", group, f"@{bot.number} {ping}")
```

The driver sends the *text* `@61410724095 ping`. Our matcher has three ways to
decide a group message is for us — a real `mentionedJID`, a reply to something
we said, and **our number written in the text**. The third one caught it. The
first one, the one a human being actually produces when they tap a name out of
the mention picker, was never exercised.

So the live suite and the broken behaviour agreed with each other. Not because
the test was careless: typing `@` plus a number into a message is a completely
reasonable way to write that test, and it *is* one of the three paths. It is
just not the path a person uses. The only way to produce a real `mentionedJID`
is to pick the name from WhatsApp's own picker, which is to say: by hand, which
is the thing the suite exists to stop needing.

This is the second time this week a stand-in agreed with a bug. The other was
`(tmp_path / "session.db").write_bytes(b"linked")` — seven bytes standing in
for a paired device, green throughout a bug about unpaired devices. Both are
the same mistake at different scales: **the fake satisfied the check instead of
reproducing the thing.**

## The fix, and what it refuses to do

Identity stops being a string:

```python
phone = _user_of(_jid_str(getattr(me, "JID", None)))
lid   = _user_of(_jid_str(getattr(me, "LID", None)))
return phone, frozenset(i for i in (phone, lid) if i)
```

All three matching paths now test membership in that set. Both ids stay live —
groups migrate at different times and older ones still address us by number, so
this is a set, not a replacement.

It would have been tempting to convert incoming LIDs to phone numbers instead;
neonize exposes `get_pn_from_lid` and it would have made the comparison a
one-liner against the identity we already had. That resolution hits a store
that can be empty, on a path that runs for every group message, and its failure
mode is precisely the one being fixed: a mention that silently does not
register. Reading two fields off a struct we already hold has no failure mode
at all.

The connect line now says both:

```
2026-09-17T04:26:17Z connected as 61410724095 (also 132754033377342)
```

That is deliberate. The whole investigation would have been one glance if the
listener had ever said which ids it was answering to.

## The rule underneath

Ask what a real actor produces, not what the code accepts. Our matcher accepted
three kinds of mention; our test produced the one that was easiest to type, and
so it measured a path no person walks.

Six new unit tests hold the LID cases now, four of them red first, and the
first one carries the owner's actual message — `@132754033377342 测试` — so the
regression is pinned to the thing that really happened rather than to a shape I
invented afterwards. The live suite's group test still sends text, and that is
now written down as a known gap rather than a passing assertion.
