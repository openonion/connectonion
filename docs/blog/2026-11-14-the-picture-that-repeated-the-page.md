---
title: "The picture that repeated the page"
date: 2026-11-14
tags: [rem, reader, design]
---

# The picture that repeated the page

On a person's page in the co rem reader there is a small picture of who they are connected to. We opened it on an invented notebook of sixty people and looked at what it drew: a grey dot in the middle, a black square for the organisation, a hollow diamond for the project. Three marks, drawn three different ways, in a widget that was mostly white.

The marks were not wrong. They were redundant. The organisation and the project were already sitting at the top of the same page as chips under the person's name. Across those sixty people nobody had more than three direct links, and most had two. The picture was telling the reader what the top of the page had already told them.

## The fix that made it worse

Our first answer was the responsible-looking one. Issue #2066 asks that a reader can see *why* two records are connected, so we put a list under the picture: each neighbour's name, the sentence that links them, and when they were last active.

It looked thorough. Then someone asked the obvious question: is this not the same thing again? It was. The names were the chips. The sentences were already in Related pages, inside the full note. The dates were in the graph's side panel. We had answered "the picture says nothing new" by writing down, a third time, things the page already said.

The list went. What stayed was the question it had tried to answer.

## One ring cannot step back

The interaction we wanted is the one Obsidian's graph is known for: point at a mark, and it and what it touches stay while everything else steps back. We built it and pointed at an organisation. Nothing stepped back. With one ring, every mark touches the record in the middle, so there is nothing left to dim.

That is what the second ring is for. Past the organisation are the other people who work there; past the project, the other people linked to it. They are drawn small and nameless until they are lit. Now pointing at an organisation shows something the hero card cannot: who else you reach through it.

Why they connect lives in a card that appears with the light. It is not new writing. It is Related pages' own entry, the same sentence with the same citations, floated beside the picture. The first version of that card sat directly under the mark, which put it on top of exactly the neighbours it had just lit. It now docks to whichever edge of the widget covers less of what is lit, and hangs below when the widget is too short for either.

## What the notebooks found

Two things only showed up on the large notebook. An organisation with ten people had their names printed over each other; names are now placed best-linked first, and one that would overlap waits until it is lit. And a rule meant for the page's icons was drawing a ring around every mark.

The third came from the opposite direction, a notebook of a dozen records written for the tests. A person whose page happened to contain the word "depot" got a card saying the page *mentions* the Depot project, when the line between them was drawn by two coding sessions. The card now explains the line: a link first, then the sessions, and a bare name match only when there is nothing better.

We also built a switch between one ring and two, and then removed it. On a person, one ring is the view that repeats the page. For anything deeper, Open in graph already has a depth control.

## What we measured

On the invented notebook we pointed at every mark on every record that has the widget: 854 marks on 86 pages. Each one lit its neighbours and showed a card, with no page errors. On one person's first screen at 1440 pixels, text of 12 pixels and under went from 14.7% of what you read to 13.9%, and the number of controls rose from 23 to 29, because every mark in the outer ring is a link to a record.

One rule changed under us while this was in review: the reader stopped drawing a line for a link written inside a sentence labelled personal. The widget follows that rule rather than working around it, and its tests now say so.

The lesson is small. A picture earns its place by saying something the page has not said, and when it needs words, the page usually has them already.
