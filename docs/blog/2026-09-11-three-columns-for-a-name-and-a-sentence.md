# Three columns for a name and a sentence

The Control Center starter puts an Agent's first three skills in a card called
Quick actions. Each one shows its name and the first sentence of its description,
which is exactly the right thing to show. The card laid them out in three
columns.

The card is about 460 pixels wide. Three columns, minus gaps and the chevron each
tile needs, leaves roughly 150 pixels per action. So this is what an Agent with
ordinary skill names actually got:

```text
email-client          generate-      reconcile-
Write a concise c…    invoice        payments
                      Create and…    Match incom…
```

Two of the three names wrapped. All three descriptions were cut, and not cut
politely — `white-space: nowrap` with an ellipsis cuts wherever the pixel budget
runs out, which is usually the middle of a word. "Write a concise c…" is not a
short description. It is a description that has been destroyed and then given a
character that implies the rest is available somewhere. It is not.

Underneath the three short tiles sat a band of empty card, because the tiles were
one row and the card had been stretched to match the taller card beside it.

## The layout was not a style choice

It is tempting to treat this as taste — someone preferred a grid, someone else
prefers a list. It isn't. A layout that cannot fit the content it is given is
wrong in the same way a function that cannot hold its return value is wrong. The
question to ask of a column count is not whether it looks tidy in a mock with
three short words in it, but how many characters it gives you and how many the
real data has. 150 pixels is about 20 characters at this size. Skill names alone
run past that, and every one of them is followed by a sentence.

One action per row gives the same card about 420 usable pixels: the full name on
its own line and two readable lines of description under it. Three rows also fill
the card, so the dead band goes away by itself rather than by being padded out.

## The other half of the same mistake

The two cards in the top row had been given each other's height. Whichever card
had less to say grew a hole at the bottom. The fix that suggests itself is to let
each card be its own height, and that trades the hole for an L-shaped gap beside
the shorter card, which is not better. What the extra height is *for* is the
answer: the composer spends it on the textarea. The person typing gets more room,
which is the one thing in that card anybody wants more of.

A masthead column was empty for a different reason. The header declared two
columns at desktop width and put every line into the first one, so the connection
state sat as a fourth stacked line of text under the tagline — the only live fact
on the page, styled like a footnote. It is a pill in the second column now, which
is what the second column was declared for.

## The twin had it too, and one thing besides

`starter.html` — the canonical page `co host` serves — carries the same three
columns and the same nowrap ellipsis. Its docstring says it is written for a
440px pane, where the columns have already collapsed to one; at desktop width
they had not, and it truncated exactly the same way. Rendering it through
`render_starter` rather than guessing showed the identical damage, so it gets the
identical row.

One rule deliberately differs. The Control Center's two cards keep a shared
height because its composer can spend the difference. The starter's Workspace is
a two-line note with nothing to spend it on, so there each card keeps its own
height; forcing them equal would only inflate the note.

Rendering the starter also turned up something that has nothing to do with
columns. It declares two overview columns at desktop width, and an Agent that has
published no skills renders no Quick actions card — so the Workspace note sat at
40% width beside an empty half. Day zero is precisely when an Agent has published
nothing, which means that lopsided page was the first thing `co host` showed most
people. `.overview:not(:has(.quick))` collapses it to one column. The Control
Center never had this bug because its bridge script sets a class when the skill
list is empty; the starter has no script, and nobody had rendered the empty case.

## What is checked

The starter is the interactive twin of the canonical `starter.html`, and a test
asserts that the eleven colour tokens appear in both files with the same values in
the same order. None of them changed here; nothing about this is a repaint. The
same test lists the landmarks and the identifiers the bridge script queries, and
those are unchanged too, because this is the same page with its content given
room.

Light, dark, and a 390-pixel viewport were each rendered and looked at, which is
the only way to know that a two-line clamp behaves and a pill in a grid cell does
not stretch to the column.
