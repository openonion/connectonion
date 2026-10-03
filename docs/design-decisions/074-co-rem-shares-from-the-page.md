# DD-074 — co rem shares from the page: a Share section, one email per person per day

Status: proposed for 1.9.0, 2026-09-30. Decided with the owner in conversation;
nothing here is built yet. Change this record when building proves a part wrong.

## The problem

co rem keeps pages on the people and projects in the owner's work. Much of what
it knows matters to someone else too. Take the students on the owner's
projects:

- one group follows the frontend, because their Android app depends on it;
- another follows the thinking behind co rem itself.

A partner on an Airbnb pricing page needs the pricing rules and the decision
waiting on them. Today any of that reaches them only when the owner writes a
message by hand.

The goal: the owner says once, on the page, what goes to whom. From then on co
rem sends it in the background, only on days something changed. The people it
goes to need nothing installed.

## Decision in one paragraph

Any page (a project, an organisation, a person) may carry a **Share** section
that the owner writes. Each line names email addresses, how often, and what
the readers care about. Each night, after maintenance, co rem collects every
Share line across the notebook and groups them by recipient. For each
recipient with something new, it writes one **brief**: one model call, one
section per page. The brief goes by **email, sent separately to each
person**, at most once a day. Replies come back to the owner's mailbox, where
co rem already reads. A question becomes an open thread on that person's page;
"stop" removes that address from the line.

## The Share section

```markdown
## Share
- to: vicky@uni.edu, tom@uni.edu, ann@uni.edu · every: day · about: frontend components and API changes; not costs or accounts
- to: lee@uni.edu, max@uni.edu · every: day · about: why investigation and upkeep work the way they do; no code details
- to: partner@example.com · every: week · from: agent · about: overall progress
```

- **`to` and `every` are fixed-format** and read by code, never by a model.
  Who gets mail and how often cannot be misread or invented.
  - `every` is `day` or `week`.
  - `from` is optional: `gmail` or `outlook` (the owner's own account, the
    default) or `agent` (the agent's own address).
- **`about` is free text:** the lens the brief is written through. The same
  day's changes read differently for the Android students and the co rem
  students.
- **There are no groups.** A line lists addresses. Several lines give several
  audiences their own lens.
- **The section is the owner's.** Maintenance must leave it byte-for-byte as it
  was. A model candidate that changes it is rejected, the same way a candidate
  that breaks the page's structure is rejected today. Otherwise one "tidy-up"
  could change who receives mail.
- **Derived lines are read-only.** Under each Share line the page shows "last
  sent: 30 Sep". The person pages show which pages' briefs that person
  receives. Both are generated, never written twice.

## Sending: grouped by person, one email a day

1. The nightly round runs after maintenance, so briefs read the updated pages.
2. It collects every Share line and groups the lines by address. An address on
   two pages gets one email with two sections, not two emails.
3. For each address, it checks whether anything changed on those pages since
   the last brief sent to that address. If nothing changed, it sends nothing
   and calls no model. This is the #1846 rule: a quiet night costs nothing.
4. Otherwise it makes one model call per recipient to write the brief:

   ````markdown
   Subject: <topic>: this week's progress (needs you: …)  ← "needs you" only when there is something

   ## Needs you            (only when there is something)
   ## Since last time
   ## Where it stands
   ## Decided, and why
   ## Open questions
   ````

   Each brief is whole: the current state plus what changed since the last
   one. A missed email loses nothing.
5. The brief is sent to that one address, from the line's `from`.
6. It is recorded in `.state/shares/`: address, pages, time, and the exact text.

Sending to each person separately keeps their addresses private from each
other. Each reply is its own thread, attributed to one person's page, and each
person can stop without affecting the rest.

## Replies close the loop

Replies land in the owner's mailbox, which co rem already reads.

- **A question.** "When can we use this API?" becomes an open thread on that
  student's page. The next brief answers it first.
- **"Stop" or "unsubscribe".** That address is removed from the Share line, and
  the owner is told once. This is the only change co rem makes to a Share
  section, and it only ever removes the sender's own address.
- **A correction.** "That date is wrong" is filed as a reflection on the page
  (#1611).

## What never goes in a brief

Mail bodies, other people's affairs, credentials, and anything the redaction
already strips (`[secret-shaped text removed]`) never go in. The brief draws
only on the pages named in the recipient's Share lines. `about` narrows the
material; it can never widen it.

## Consent and control

- **The first brief to a new address is shown to the owner before it goes.**
  Every later brief to that address goes automatically, unless it would draw
  on a kind of material the earlier briefs did not, for example the first time
  a mail-derived fact would appear. That asks again.
- `co rem shares` lists every Share line in the notebook, when each address was
  last sent a brief, and the text sent. `co rem share preview <address>` shows
  tomorrow's brief now.
- **Adding a line:** edit the page, run
  `co rem share projects/frontend --to a@x,b@y --every day --about "…"`, or tell
  co ai "send the frontend updates to the Android students every day". Each one
  writes the same line.
- **The reader** shows the Share section as a card on the page. Pause and
  preview buttons wait for #1835, which lets the page talk to the local host.

## Later: when both sides run co (1.9.1)

The same Share lines, with a better transport and a receiver that asks for
itself:

- **Relay mailbox.** Between two co installs, briefs travel through an oo-api
  relay mailbox keyed by 0x address:
  - signed by the sender and sealed to the receiver's key (Ed25519 to X25519,
    NaCl sealed box, the same keys as `network/sealed.py` but offline);
  - stored as ciphertext only (#1172);
  - one slot per sender and receiver, holding only the latest brief, plus
    "needs you" messages kept for 15 days.

  The receiver collects in its nightly round, and the brief becomes
  `~/.co/rem/shared/<sender>/<page>.md`, installed as a Skill. Its coding
  agents load it when relevant and cite it: "from Aaron's notes, two days ago".
  Received briefs enter the shared inbox as an `oo` provider under the
  three-verb contract (#1389).
- **Card and subscription.** Each notebook can send its contacts a card: the
  topics it is willing to share, coarse and with no content. The receiving
  notebook matches cards against its own open questions (the `Unknown` fields
  on its pages, #1523) and writes the subscription request itself. Its owner
  approves once, and the sender's owner approves once. The approved request
  becomes a new line in the sender's Share section, so there is still one
  place that says who gets what.
- **Repositories.** For a shared repository, co rem writes the owner's brief to
  `.co/context/<owner>.md`, and AGENTS.md carries one line: "read `.co/context/`
  first".

## What we rejected, and why

| Option | Why not |
|---|---|
| Separate share configuration pages (`shares/<name>.md`) | A second place to keep in step with the page it describes. The page is where the owner looks when the project changes. |
| Groups (`groups/<name>.md`, or tags) | Nothing a group adds that a line of addresses does not. Several lines give several audiences. |
| One email to all recipients | It exposes every student's address to the others, mixes replies, and makes "stop" all-or-nothing. |
| Writing into the other person's AGENTS.md or CLAUDE.md | It is their file: our writes collide with theirs and blur who said what. It loads on every turn, relevant or not. Another person's text also becomes their agent's instructions. |
| The sender guessing interests with no configuration | Less accurate than the owner's own line, or than the receiver's open questions (1.9.1). |
| `co call` for delivery | It runs one allow-listed command on a live remote host. It is an operation, not a message. |
| An always-online host answering questions | It needs uptime and costs a call per question. Worth adding later for depth (#1835); the brief stays the default. |

## Phasing

| Release | Scope |
|---|---|
| 1.9.0 | The Share section, protected from maintenance. A nightly share step grouped by address, with the no-change skip, one model call per recipient, and one email per person per day from `gmail`, `outlook` or `agent`. `.state/shares/` records, `co rem shares`, `share preview`, and the `share` command. Replies: questions become open threads, "stop" removes the address. The Share card in the reader, read-only. |
| 1.9.1 | The oo-api relay mailbox, offline sealing, the `oo` inbox provider, and installing received briefs as Skills. Cards and receiver-written subscriptions that land as Share lines. `.co/context/` for repositories. |
| Later | Answering a contact's agent directly (#1835). Private `co sub` over #1210. |

## Open questions

- The default sender: the owner's Gmail or Outlook (students know the owner,
  and replies come back to where co rem reads), or the agent's address. Current
  lean: the owner's account, overridable per line with `from: agent`.
- Whether `every: day` should skip weekends by default.
- The maximum number of addresses a single line may name before co rem asks
  whether this is really a mailing list.

Related: #1968 (tracking), #1580 (handing context to someone else), #1611,
#1833, #1846, #1172, #1210, #1835, #1523, #1939.
