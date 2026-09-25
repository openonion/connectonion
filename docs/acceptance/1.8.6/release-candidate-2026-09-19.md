# 1.8.6 release-candidate acceptance — 19 September 2026

Candidate: **1.8.6a9**, the package installed from PyPI, not this checkout.
Every command below was run with `PYTHONSAFEPATH=1` so `python -c` could not
prepend the working directory and import the source tree instead:

```
/Users/you/.../.venv/lib/python3.14/site-packages/connectonion/__init__.py
1.8.6a9
```

Times are UTC. The two earlier records in this directory
(`whatsapp-live-2026-09-17.md`, `calendar-live-2026-09-18.md`) were run against
`8cd13f2e` and `b4a73c0f`. This one exists because #1555 asks for acceptance
**on the release candidate**, and a7, a8 and a9 changed `check`, added `edit`
and `delete`, changed what `send` puts on the wire, and made an empty send a
usage error.

---

## 1. WhatsApp existing-group access (#1543)

Required: real device linking, inbound group messages, sender/group identity,
mention-only triggering, replies, reconnect behaviour.

### Device linking

```
$ co whatsapp check
✓ whatsapp configured · listener pid 83467 · 0 unread · /Users/you/.co/inbox/whatsapp
✓ connected as 61410724095 since 2026-09-19T04:00:47Z
```

The account carries both identities — phone `61410724095` and LID
`132754033377342` — and the listener records both.

### Inbound group messages, identity, mention gating

Measured from `received.jsonl`, 19 September traffic only:

| | count |
|---|---|
| messages received | 11 |
| from groups | 11 |
| flagged `mentioned: true` | 5 |
| flagged `mentioned: false` | 6 |

Sender identity resolves to names, not just ids: `aaronplus1996`, `Han (John)`.

The gating was checked case by case rather than by count. Two of the five are
`@132754033377342 …`. One is a `joined` record, which a6 decided is addressed
to the bot. The fifth carries no `@` at all —

> 好的，改短吧

— and is correctly flagged, because its `quoted.sender` is
`132754033377342@lid`, our own LID: **a reply to the bot is addressed to the
bot.** That was the one worth opening; a count alone would have hidden it.

The six `false` rows are two `senderkeydistribution` records and group chatter
addressed to other people, including Han's *"You mean I can message One AI
anything if I have any update?"* — in the room, not to us.

### Replies, and the new verbs

Happy path on a9, after the empty-send refusal changed that code path:

```
$ co whatsapp send 126121882435737@lid '… the happy path still works …'
3EB055F40811284173EC44
```

`edit` and `delete` were accepted on a8 and re-checked on a9 — see §5.

### Reconnect

Two unattended disconnect/reconnect cycles on the real account, from the
listener's own log:

```
2026-09-19T00:48:02Z disconnected; waiting for the socket to come back
2026-09-19T00:48:43Z connected as 61410724095 (also 132754033377342)
2026-09-19T01:12:36Z disconnected; waiting for the socket to come back
2026-09-19T01:12:39Z connected as 61410724095 (also 132754033377342)
```

41 seconds and 3 seconds. Nothing was lost across either: the messages either
side of both gaps are in `received.jsonl`.

**PASS.**

---

## 2. Ollama / local endpoints (#103, #1538)

Required: installed-package acceptance for local text, structured output and a
tool-capable round trip, without cloud keys or silent fallback.

Model `ollama/qwen3.5:9b`, served by the Ollama on this machine.

| gate | result |
|---|---|
| local text | `llm_do("Reply with exactly the word: pong")` → `'pong'` |
| structured output | `Port(service='postgres', port=5432)` from a sentence |
| tool round trip | `room_temperature(room="kitchen")` called; answer *"The current temperature in the kitchen is 21.5 degrees."* |

Cost reported `$0.0000` and the model line read `qwen3.5:9b` throughout.

### "Without cloud keys" — what was actually shown

I deleted every hosted-provider key from the environment before importing
connectonion, then printed them again afterwards:

```
cloud keys in env: ['OPENONION_API_KEY', 'GEMINI_API_KEY']
```

They were back: connectonion loads `keys.env` at import. **So the absence of
keys was never demonstrated and is not offered as evidence here.**

The property that matters is no *silent fallback*, and that was tested
directly instead — point the local endpoint at a closed port and see whether an
answer still arrives:

```
OLLAMA_BASE_URL=http://127.0.0.1:1/v1
→ LLMConnectionError: Connection Failed / Model: qwen3.5:9b
```

It failed and named the model and the server, with hosted keys sitting right
there in the environment. An answer would have been the failure.

**PASS**, with the scope of the claim narrowed to what was measured.

---

## 3. Gmail / Outlook CLI (#1521, #1522)

Required: date-window queries and machine-readable output, composing with the
existing JSON/pagination contract, preserving caps, account context and
completeness reporting.

### Outlook

```
$ co outlook inbox --since 3d --json
rows: 10   oldest 2026-09-18T19:23:31Z (0.55 days ago)   newest 2026-09-19T03:31:20Z
```

Every row inside the window. Widened, it reaches further back:

```
$ co outlook inbox --since 10d --json -n 40
rows: 40   oldest 2026-09-17T22:38:56Z (1.42 days ago)
```

**Limit of this measurement:** the mailbox has enough recent mail that the
40-row cap binds before the 10-day boundary, so no row near the far edge of the
window was observed. The window was shown not to leak (nothing outside it) and
to reach further when widened (1.42 days vs 0.55). The far edge itself is
untested here for want of old enough mail, not for want of trying.

### Gmail

```
$ co gmail inbox --since 5d --json -n 20
status: success | complete: True | account: openonionai@gmail.com
rows: 20   oldest 2026-09-17T10:31:39-05:00 (1.71 days ago)
```

The envelope survives the date window: `schema_version`, `status`, `complete`
and `account` all present, which is the contract #1521 asked the window to
compose with rather than replace.

**PASS**, with the caveat above recorded rather than rounded off.

---

## 4. Calendar invitations (#1547, #1548, #1550, #1552)

The full journey — invitation, acceptance, adding an attendee, rescheduling,
cancellation — was run on 18 September against `b4a73c0f` and is written up in
`calendar-live-2026-09-18.md`.

Rather than re-run it, I checked whether it still describes this candidate:

```
$ git diff --stat b4a73c0f 01c5bafb -- \
    connectonion/cli/commands/gcalendar_commands.py \
    connectonion/cli/commands/outlook_calendar_commands.py \
    connectonion/useful_plugins/calendar_plugin.py \
    connectonion/useful_tools/google_calendar.py \
    connectonion/useful_tools/microsoft_calendar.py
(no output)
```

**Every calendar source file is byte-identical between the acceptance
candidate and this one.** The only calendar-related file that changed in
between is the acceptance record itself. The 18 September result therefore
applies to a9 unchanged — a verifiable statement, not an assumption that
"nothing important changed".

**PASS by inheritance, with the inheritance proved.**

---

## 5. The verbs added after the earlier records

| verb | evidence |
|---|---|
| `delete` | four revocations on the real account — `3EB00EEA…`, `3EB01F4E…`, `3EB051DF…` in a group and `3EB038D3…` direct. WhatsApp returned a revocation id for each; the listener logged all four |
| `edit` | `3EB038D329E6B3F39E8892` replaced in place — one bubble, no second message |
| Markdown | sent `**bold**` / `# Heading` / `- item` / `[label](url)`; read back from `sent.jsonl` as `*bold*` / `*Heading*` / `• item` / `label: url` |
| empty send refused | `co whatsapp send <chat> </dev/null` → `nothing to send: the text was empty`, **exit 2**, and no `sent.jsonl` written at all |

The deletions were not a drill. Three of them removed messages the bot had
already put into a customer's group, one of which had posted a profile of the
customer back to the customer.

---

## Summary

| workstream | verdict |
|---|---|
| WhatsApp group access | PASS, on the candidate |
| Ollama / local endpoints | PASS, on the candidate, claim narrowed to what was measured |
| Gmail / Outlook CLI | PASS, on the candidate, cap-vs-window limit recorded |
| Calendar invitations | PASS, inherited from 18 September with the source proved identical |

The suite is 10,431 tests. It reported none of the twelve defects this release
fixed; every one was found by somebody using the software. That is the reason
this file exists in the shape it does — the gates above are things that were
done to a running system, not assertions about one.
