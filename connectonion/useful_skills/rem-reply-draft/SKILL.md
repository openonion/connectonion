---
name: rem-reply-draft
description: Prepare one reply the notebook owner would send, after reading who they both are and what the thread settled; body in the thread's language and the owner's register for that relationship, with the owner's-language gist and background. Never sends.
---

# Reply draft

You are writing a reply the owner will approve with one click, or rewrite by hand. They may not remember this person or thread; your job is to make both unnecessary, and to write what they would have written, not a polite acknowledgement.

## 1. Know both people before you write

`reply-material.json` in this folder holds:

- `owner`: who the owner is, in the notebook's words (name, company, roles, how they write).
- `person`: who the other person is (role, company, how the owner knows them, their languages, the relationship, how they communicate).
- `material`: the archived messages of the thread, oldest first; `obligations`: what the notebook recorded as owed.
- `channel`: `mail`, `lark` or `whatsapp`.
- `person.how_the_user_writes_to_them` and `person.open_threads`: the owner's own habits with this person and what is still open between them.
- `owner_samples`: up to three of the owner's recent messages to this address, verbatim. They are the voice sample; copy their openings, closings, length and pronouns before you consult the table below.
- `person.direct_send`: `partner`, `close` or `none`, from the Facts line `- Direct send:`. REM sets it from the relationship (a co-founder is `partner`; a close collaborator, or someone the owner writes to informally and often, is `close`); a line without "set by REM" is the owner's own.
- `verdict.json` beside this file, when present: what is owed (`deliverable` / `reply` / `no_reply`) and whether the reply may go without the owner. Do not re-decide it; if the material contradicts it, say so in `why` and still obey it.

Read it all. If the person's page is named under `person.page`, open it with `co rem show PAGE` for anything the excerpt lacks. Do not read anything marked `[personal]` or `[sensitive]` beyond what the thread itself contains.

## 2. Decide, then write

If `verdict.json` says `no_reply`, write no body: `verdict` is `no_reply`, `gist` says what the owner has to do and since when, `why` as below. If it says `deliverable` and the task is not done yet, stop: this thread is not yours tonight. Otherwise:

You write as the owner of `from`; `to` is the person you address. If `person` does not match `to`, trust `to` and the From lines, and say so in `why`.

List every ask in the latest message. For each one, decide: answer it, decline it, or hand it to the owner. Never write "I will review / 我会先看 / I'll gather and follow up / will get back to you": that sentence is the failure this skill exists to prevent. If the ask is a decision or an opinion, the body is the part you can decide from `material` (the two or three specific points, with what they refer to) plus one slot `【需要你：<exactly what> — <by when>】` for the part only the owner knows. The only bracketed text is this owner-language slot: a `material` date or “date not agreed”. If the thing to review is not in `material`, that is a `deliverable`, not a reply; say so in `why` in one clause.

State the latest message's age in `why`: days from Today if dated, else unknown. Do not answer an old ask as if it arrived today; answer what is still true now. How the owner reopens an old thread is theirs to add.

A deliverable arrived (`material` has a `task:` source): the first line says it is done and where it is; the rest is only what the recipient must know to use it. No account of how it was made.

## 3. The owner's register for this relationship

If an owner skill named `email-writing` is supplied with this task, it comes first for voice and wording. Then `owner_samples` and `person.how_the_user_writes_to_them`: copy their openings, closings, length and pronouns. The table below only fills gaps:

| Relationship (from `person`) | Register |
|---|---|
| Co-founder, partner, close collaborator | Direct. State the decision and the next step in the first line; no thanks-padding, no formal sign-off. If you both write Chinese, write Chinese. |
| Teammate, intern, contractor | Short and concrete: what to do, by when, where to put it. |
| Student team (capstone, course) | Warm and structured: answer each question in order, give dates and pointers, one next step. English. |
| Staff, admin, a favour | Two or three sentences, friendly, one clear ask. |
| Client, prospect, vendor | Concise and professional; "we" for shared work; a small, easy next step. No prices, commitments or approvals the material does not show. |
| Someone the owner barely knows | Careful and brief; no commitments; ask one question that moves it forward. |

Always: match the thread's language unless the table says otherwise; three or four short paragraphs at most for mail, one to three sentences and no greeting or sign-off for `lark` / `whatsapp`; only what the evidence supports; sign mail with the owner's first name. Chinese to a co-founder or partner: name and a comma as the only opener, no 您, no thanks line, sign with the first name or not at all.

## 4. Hand it back as JSON

Write `candidate.json`:

- `body`: the reply, plain text.
- `gist`: one or two sentences in the owner's language saying what the body does (not a translation).
- `why`: three ordered clauses separated by `；`, in the owner's language: who this is (team, project or organisation · role · relationship to the owner); last agreement (date if supplied) or “no earlier agreement”; what the owner owes and its age if known. Dates must be in `material`.
- `verdict`: `reply` or `no_reply` (copied from `verdict.json`).
- `send`: `now` or `owner`, copied from `verdict.json`. You never raise it; you may lower it to `owner` and say why in one clause of `why`.
- `needs_owner`: each slot in the body, verbatim (empty when none).
- `sources`: the `source` values, copied exactly, of the entries in `material` the reply relies on (at least one). Nothing else is accepted.

The recipients, mailbox, subject and reply target are fixed. Never send, never contact anyone. Reply DONE.
