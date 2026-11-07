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

Read it all. If the person's page is named under `person.page`, open it with `co rem show PAGE` for anything the excerpt lacks. Do not read anything marked `[personal]` or `[sensitive]` beyond what the thread itself contains.

## 2. Decide, then write

List every ask in the latest message. For each one, decide: answer it, decline it, or defer it with a reason. Where only the owner knows the answer (an opinion, a figure, a date they must check), leave a one-line slot in square brackets saying exactly what goes there. A reply that only says "received, I will look" is a failure unless the thread calls for exactly that. When the ask is to review or decide on something, do not promise to review it later: either give the review here from the material (the two or three specific points), or leave a slot such as `[你的意见：成本假设 / 时间表]` and name the day the owner will answer.

## 3. The owner's register for this relationship

If an owner skill named `email-writing` is supplied with this task, it comes first for voice and wording. On top of it, the relationship sets the register:

| Relationship (from `person`) | Register |
|---|---|
| Co-founder, partner, close collaborator | Direct. State the decision and the next step in the first line; no thanks-padding, no formal sign-off. If you both write Chinese, write Chinese. |
| Teammate, intern, contractor | Short and concrete: what to do, by when, where to put it. |
| Student team (capstone, course) | Warm and structured: answer each question in order, give dates and pointers, one next step. English. |
| Staff, admin, a favour | Two or three sentences, friendly, one clear ask. |
| Client, prospect, vendor | Concise and professional; "we" for shared work; a small, easy next step. No prices, commitments or approvals the material does not show. |
| Someone the owner barely knows | Careful and brief; no commitments; ask one question that moves it forward. |

Always: match the thread's language unless the table says otherwise; three or four short paragraphs at most for mail, one to three sentences and no greeting or sign-off for `lark` / `whatsapp`; only what the evidence supports; sign mail with the owner's first name.

## 4. Hand it back as JSON

Write `candidate.json`:

- `body`: the reply, plain text.
- `gist`: one or two sentences in the owner's language saying what the body does (not a translation).
- `why`: two or three sentences in the owner's language the owner needs because they do not remember: who this person is (team, project or organisation, and role, and the relationship to the owner), what was last agreed, what the owner owes them and since when.
- `sources`: the `source` values, copied exactly, of the entries in `material` the reply relies on (at least one). Nothing else is accepted.

The recipients, mailbox, subject and reply target are fixed. Never send, never contact anyone. Reply DONE.
