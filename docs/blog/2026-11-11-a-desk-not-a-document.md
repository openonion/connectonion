---
title: "A desk, not a document"
date: 2026-11-11
tags: [rem, reader, design]
---

# A desk, not a document

The owner of co rem opened his Today page one evening and said the thing designers dread: it was fine, it worked, and it was "all words". The page told him three people were waiting, drew a red fuse for each, and then laid out every card, every row, every quiet link, every button underneath. It read like a report about his day. He wanted something that felt like sitting down at a desk.

We had spent a week making that page *correct*. Every number was honest, every red mark meant overdue and nothing else, every function had a test. None of that was the problem. The problem was that the page had no depth: everything was printed at the same distance from the reader, so everything competed.

## What changed

We tried four art directions on his real notebook and he picked one: a white desk with cards on it. The rules are short.

- **Depth means attention.** Only one card on Today is raised: the person you are dealing with now. Everyone else waiting is a face along the top, wearing a ring that burns red with the days overdue. Click a face and that card is dealt onto the desk. J and K do the same from the keyboard.
- **The night is a picture.** REM works while you sleep. Instead of a paragraph about the last pass, a small hypnogram shows the runs it actually logged — reading mail near the surface, rewriting and translating pages deeper — and a face on each rise where it drafted a reply or prepared a task. Where the log has nothing, the line stays flat. We did not draw sleep it did not have.
- **Functions wait until you reach for them.** Hand a row to Codex or Claude, talk it over, mark it done: those appear when you hover or tap the row. Writing full screen, editing in the mail app and skipping sit behind one "more". The green Send is the only colour on the card.
- **A person is a record.** Their page is a hero card with their face, how to reach them on hover, and a bento of widgets: how often you talk, the last thing they said to you, the history, the people and projects around them. What you owe them stays on Today; the record has one quiet link there.

## The awkward part

A redesign of a page this tested is mostly a redesign of its tests. Two hundred browser checks described the old structure: the poster headline, the fuse lanes, the sidebar's text links. Each one had to be read for what it protected, not what it selected. "The headline counts people" survived as "the night card counts people". "The sidebar shows one number" survived as "the rail shows one badge". A few did not survive: the old phone menu lived in the header because Send owned the bottom of the screen. Now a floating tab bar owns it, and Send sits just above.

One habit paid for itself again. Before trusting a mock, we rendered the owner's real notebook and ran a probe that clicks every control and records whether anything changed. The first pass found rows that expanded on click but were not buttons — controls that looked real to a mouse and did not exist for a keyboard. They became plain "show all" chips.

## What we measured

On the owner's notebook, at 1440 pixels, Today's first screen went from 112 pieces of text and 40 controls to 55 and 16, with one green action. Small text (12px and under) fell from two thirds of what you read to under half. The probe found no control without an effect, other than buttons a snapshot disables on purpose because sending needs the live reader.

This is the first of three parts. The lists and the remaining records move onto the desk next.
