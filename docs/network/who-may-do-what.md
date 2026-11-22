# Who may do what

An agent has one access policy, whether a person reaches it through its Host
(web, O Chat, another agent) or through WhatsApp. The policy is two things in
the project's `.co/`:

- **`trust:` in `host.yaml`**: `open`, `careful` (the default) or `strict`. It
  decides who is let in.
- **The lists** (`admins.txt`, `whitelist.txt`, `contacts.txt`,
  `blocklist.txt`): who is who. Edit them with `co trust`.

## Who is an entry

| Who | How they appear in the lists |
|---|---|
| An agent or a web user signed in with a key | `0x` and 64 hex digits |
| A WhatsApp person | `whatsapp:+<country code><number>`, e.g. `whatsapp:+61400000000` |
| A WhatsApp group | `whatsapp:<id>@g.us` (the chat id `co whatsapp ls` prints) |

```bash
co trust admin add whatsapp:+61400000000           # may do everything an admin may
co trust add whatsapp:+61400000001 --whitelist     # full trust
co trust add whatsapp:120363000000000000@g.us      # every member of the group is a contact
co trust block whatsapp:+61400000002
co trust list
```

A WhatsApp sender is identified by the linked-device session, never by the
message text or the display name, which anyone can set.

- A sender that WhatsApp addresses by LID (`…@lid`) is looked up in the
  session's own LID map to find the phone number. If there is not exactly one
  number, the sender is a stranger.
- A number that changes is a new identity. The old entry stays until you
  remove it.

## Levels

From most to least trusted: `admin`, `whitelist`, `contact`, `stranger`. In a
group:

1. `blocked` wins over everything, whether the person or the group is blocked.
2. A person's own entry wins over the group's, so an admin is admin in any group.
3. A member with no entry of their own gets the group's level.
4. A sender with no known phone number is a stranger, even in a listed group.

## Who is answered

`trust:` decides this the same way on every path:

| `trust:` | Answered |
|---|---|
| `open` | everyone except blocked |
| `careful` | admin, whitelist, contact |
| `strict` | admin, whitelist |

On WhatsApp, `careful`'s "ask" has nobody to ask, and no invite code or payment
travels over chat, so a stranger is not answered.

- **`co whatsapp consume`** checks a sender before running your command. It
  gives the command the result as `CO_CALLER_ADDRESS` and `CO_CALLER_TRUST`
  (and `CO_CHAT` for the group). These are the same two variables a restricted
  Host turn gets. Without a `.co/host.yaml`, consume checks nobody and says so
  when it starts.
- **A Host with `listen:` WhatsApp channels** checks the same way, and records
  the caller on the turn.

## What each level may run

In a `restricted:` Host (`model: claude-code/<model>`), `allowed_tools` is what
everyone who is let in may run. A level can add to it:

```yaml
restricted:
  allowed_tools: ["Bash(python read_ticket.py:*)"]       # everyone admitted
  admin:
    allowed_tools: ["Bash(python write_contact.py:*)"]   # added for admins
```

`admin`, `whitelist` and `contact` may each add `allowed_tools`, and nothing
else: a level cannot change the prompt or the environment. The Host's own
operator turn gets no level's extras. The same file applies to a web caller and
to a WhatsApp sender answered by the Host.

## What it does not cover yet

- **Earlier messages in a group thread.** With `--context`, messages from
  other members are fed to the model too. `CO_CALLER_TRUST` is the sender of
  this message only, so a tool that changes something should confirm with that
  sender rather than act on text from the thread.
- **One person, one entry.** A WhatsApp number cannot yet be linked to the
  same person's `0x` address.
