# The cards under the card

Today shows one person's card at a time. Under it, two thin edges stick out, as if the
next cards were waiting in a pile. We noticed them while testing a notebook with
twenty-five things waiting: we clicked the edges, then scrolled over them. Nothing moved.

The edges were drawn by the style sheet alone. They said "there is more here" and offered
no way to get to it. The ways that did work were elsewhere: the faces in the strip above,
J and K, the palette, and a "Next card" word in the card's head. On a phone that word is
always there. On a desktop it shows only while the pointer is over the card, so at rest
the one visible sign of the next card was the one thing that could not deal it.

## What changed

Nothing new is drawn. The edges are now a button in the same place, with the same look:
a click or a tap deals the next card, as J and "Next card" do, and the next card rises out
of the pile as it already did. A pointer over the edges sinks them a little and names whose
card is next. They take no tab stop, because the keyboard already has J and K. With one card
there are no edges, as before.

## A direction we did not take

We first also let a finger swipe the card sideways on a phone. It worked, but it pointed
the wrong way: the pile sits below the card and the next card rises from it, so a sideways
gesture told a different story from the picture. Up and down is the page scrolling, so the
gesture that would match the pile is not free. The phone already shows "Next card", so we
kept the pile's own direction and dropped the swipe.

## What we measured

At rest, the deck looks the same as before; in a pixel comparison the only difference was the
overdue dot's animation frame. On the reader's fixture notebook, a click and a tap on the
edges each raise the card J would, and the faces above follow. The browser suites around
Today pass as on `main`, apart from one test that fails on `main` too, about half the time.

The lesson is small: a thing that looks like it can be pulled should move when pulled, and
it should move the way it looks.
