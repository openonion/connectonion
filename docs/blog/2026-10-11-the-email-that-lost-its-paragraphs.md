---
description: co email send wrote three paragraphs and Gmail showed one, because the mail service sends every body as HTML. A plain-text body is now escaped and wrapped in paragraphs before it leaves.
tags: [Email]
---

# The email that lost its paragraphs

While testing a release this morning we sent ourselves an ordinary email:

```
co email send openonionai@gmail.com "[TEST]" "First paragraph, line one.
First paragraph, line two.

Second paragraph: 1 < 2 & 3 > 2.

Third paragraph, the end."
```

Gmail showed it like this:

```
First paragraph, line one. First paragraph, line two. Second paragraph: 1 < 2 & 3 > 2. Third paragraph, the end.
```

Three paragraphs went in and one came out. Every line break was gone.

## Where the newlines went

Nothing in the client removed them. The mail service puts every body into
the message's HTML part, and it has no plain-text part to fall back on. In
HTML a newline is just whitespace, so the browser joins all the lines into
one run of text.

We had already hit this once. `co handoff` mails a prompt that someone pastes
into Codex, and the layout of that prompt matters, so it wraps the prompt in
`<pre>` itself. That fixed handoff, but not the command most people and
agents actually send with. Plain `co email send` had the same problem the
whole time. Most messages are a line or two, so nobody noticed.

There was also an old comment in `send_email.py` about a variable called
`is_html`. It was computed, never used, and then deleted. The function's
header still said it "detects HTML vs plain text", when in fact it did
nothing with the difference.

## The fix

`send_email` now checks the body. If it has no HTML tags, it escapes the
text, puts each block between blank lines into a `<p>`, and turns each
single newline into a `<br>`. If the body already has tags, as handoff's
`<pre>` does, it is sent unchanged, so handoff keeps working as before.

The escaping matters more than it seems. The test line `1 < 2 & 3 > 2` has
both angle brackets in it. A tag check that only looked for `<` and `>` would
have sent it as HTML, and a converter that skipped escaping would have turned
`< 2 & 3 >` into something the browser tries to read as markup. The tag check
needs a letter right after the `<`, so this line counts as plain text, and
escaping makes it display exactly as typed.

We also checked whether oo-api could take a real `text/plain` part next to
the HTML one. It can't: the send endpoint takes a single `body` and puts it
in the HTML part. Changing that would need a server change, and for now the
client-side conversion is enough to fix what people see.

## Measured

We sent the same three-paragraph body again with the fix and read it back
through the Gmail API:

```
First paragraph, line one.
First paragraph, line two.

Second paragraph: 1 < 2 & 3 > 2.

Third paragraph, the end.
```
