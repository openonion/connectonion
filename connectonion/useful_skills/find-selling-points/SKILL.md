---
name: find-selling-points
description: Mine the codebase for capabilities worth telling people about — the surprising, user-facing ones — and prove each against source before it may be published. Use when writing or auditing marketing copy, a landing page, a README, a launch post, or when asked "what is actually good about this" / "找卖点" / "提炼宣传点".
tools:
  - read_file
  - glob
  - grep
  - write_file
  - edit_file
  - Bash(git *)
  - Bash(ls *)
  - Bash(cat *)
---

# Find Selling Points

Find what is genuinely unusual about this project, prove it, and write it down in a
form someone can publish without lying.

This skill exists because the failure mode is not "we could not think of anything".
It is the opposite: it is easy to generate plausible marketing sentences, and
plausible marketing sentences about software are wrong most of the time. Everything
below is built to make a claim expensive to assert and cheap to check.

## The two rules

**Rule 1 — a claim you cannot cite does not exist.** Every point ends in
`file:line`. If you cannot cite it, you delete it. Not soften it, not hedge it —
delete it. A missing selling point costs nothing. A false one costs a customer.

**Rule 2 — say what someone can DO, not how the code looks.** "Functions become
tools automatically" is a fact about our source. "You can hand a client a link and
they talk to the agent in a browser with nothing installed" is a fact about their
day. Only the second kind ships.

## What does not count

Reject these on sight. They are the reflexes to suppress, not options to weigh:

- **Comparisons to other frameworks.** "Fewer lines than LangChain", "unlike
  AutoGPT", any table with a competitor column. Comparing files us in their
  category and dates instantly. We are not a better framework; we are not a
  framework.
- **Line counts.** "2 lines", "3 lines", "8 lines". Nobody writes those lines —
  the CLI writes the project. The number was retired on purpose; do not
  resurrect it in a new costume.
- **Developer ergonomics as the headline.** Type hints, decorators, no
  boilerplate, clean API. Real, and nobody outside the repo cares. These are
  supporting detail at best.
- **Anything an LLM could write about any agent library.** If the sentence
  survives find-and-replacing our name with a competitor's, it says nothing.
- **Adjectives standing in for facts.** "Powerful", "seamless", "production-ready",
  "enterprise-grade". Replace with the specific thing, or cut.

## What counts

A point qualifies when it passes all four:

1. **True** — cited to `file:line`.
2. **Surprising** — someone who has evaluated three agent libraries this year did
   not expect it.
3. **User-facing** — it changes what a person can do, see, sell, or hand over.
   Prefer things the *end customer* experiences over things the *developer*
   experiences.
4. **Not available elsewhere** — or not available without assembling four
   services.

The strongest points usually answer one of:

- What do you get **before writing anything**?
- What can you use **standalone**, without adopting the rest?
- What does the **person you are selling to** see?
- What would normally require a **backend, a frontend, a deploy pipeline, and an
  auth provider** — and here does not?
- What is **on the machine** rather than in someone's cloud?

## Procedure

### Step 1 — Read the ground

Do not start from memory or from existing marketing copy; existing copy is the
thing most likely to be wrong. Start from source.

Cover at minimum, and in parallel where possible:

- `connectonion/cli/main.py` — the whole command surface. Every command is a
  capability someone can use with no Python at all.
- `connectonion/cli/co_ai/` — the agent that ships ready to run.
- `connectonion/useful_skills/`, `connectonion/useful_plugins/skills.py` — what a
  skill is and where skills can come from.
- `connectonion/useful_tools/` — what is usable on its own.
- `connectonion/network/` — hosting, addressing, relay, trust, dashboard delivery.
- `connectonion/cli/templates/` — what lands on disk at `co create`.
- The front end, if present in a sibling checkout (`../oo-chat`) — this is what
  the end customer actually sees, and it is routinely the most under-sold part.

### Step 2 — Generate wide, then cut hard

List every candidate, including ones you expect to fail. Twenty candidates that
get cut to five is the intended shape. Five candidates that all survive means you
did not look hard enough.

### Step 3 — Falsify each candidate

For each one, actively try to kill it:

- Grep for the mechanism. Does the code do what the sentence says?
- Is it **on by default**, or does it need configuration? Say which. "Ships with"
  and "can be configured to" are different products.
- Is it **complete**, or a stub with a TODO?
- Is there a **limit** a buyer would feel misled by if they found it later?
  Write the limit down next to the claim. A claim with its limit stated is
  stronger than a claim without, because it survives contact.

This step has caught real, shipped, public falsehoods on our own sites. Keep the
bar where it is:

| Claim that shipped | What was actually true |
|---|---|
| "MIT licensed" | Apache-2.0, wrong in six places at once |
| "End-to-end encrypted" | No payload encryption exists. TLS to a relay that terminates it |
| "Migration tools connect your existing agents in minutes" | No migration tool in the package |
| "Agents test collaboration with dummy data first" | No such mechanism anywhere |
| "Developers report 75% more time for building features" | An invented statistic |

Every one of those was written by someone confident and helpful.

### Step 4 — Write each survivor in this shape

```markdown
### <the capability, as a thing a person can do>

**Claim.** One sentence, plain, no adjectives.
**Proof.** `path/to/file.py:123` — what is there.
**Default or opt-in.** Which, and what turns it on.
**Limit.** The thing a buyer would otherwise discover later and feel misled by.
**Why it is unusual.** One sentence. If you cannot write this one, cut the point.
```

### Step 5 — Rank for a launch post

Order by *how hard it is for a competitor to answer*, not by how much engineering
went in. The point we are proudest of and the point that sells are rarely the
same, and when they differ, the buyer is right.

Then write the top three as they would appear:

- one sentence a person would actually say out loud;
- one screenshot or terminal transcript that proves it — name which, and if it
  does not exist yet, say so, because a claim with a picture beats three without.

### Step 6 — Record it

Write results to `docs/SELLING_POINTS.md` in this repo. If it exists, update it
rather than replacing it, and keep a dated entry per run so drift is visible:
a point that stops being true is itself important news, and the diff is the only
place anyone will notice.

For each run record: date, what was read, what survived, **what was cut and why**.
The cut list is the more valuable half — it stops the same false claim being
rediscovered and shipped every quarter.

## A note on tone

The audience for the output is a person deciding whether to spend twenty minutes
on this. They are tired of agent frameworks. They have read the same launch post
nine times.

Write for the sceptic, not the enthusiast. The sentence that works on them is
almost always a concrete fact stated flatly, with the limit attached — not
enthusiasm. If a point needs excitement to land, it is not a point.
