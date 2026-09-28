---
title: "The section was a number"
date: 2026-09-28
---

# The section was a number

OneNote finally opened in the terminal, but the next step was still hard to
type. `co onenote ls` printed a notebook, a section name, and a long Graph ID.
To read a page, someone had to copy the section name exactly, quote it, list
its pages, then copy another long ID. Two sections can have the same name, and
so can two pages. Access was fixed; navigation was not.

The obvious answer was to put `1`, `2`, `3` beside the rows. That answer has a
history here. An Outlook command once treated `1` from an inbox as if it were
`1` from a scheduled-message list. A short reference is safe only when the
list that gave it meaning travels with it.

Now `co onenote ls` numbers sections across notebooks. `co onenote pages 2`
opens the second section and numbers its pages. `co onenote read 1` reads the
first page from that list. The terminal saves IDs, not page text or titles,
for fifteen minutes under the selected Microsoft account. Section and page
lists are separate. An empty refresh clears the old numbers, and `--listing`
can pin a particular displayed list if another terminal refreshes the default.
Exact names and IDs continue to work.
The long IDs stay out of the default list and are available with `--ids`.

The write path gets an extra pause: `co onenote create 2 ...` shows the
notebook and section and asks for confirmation. A script must provide the
section ID or a listing token. A timeout after a create request is reported as
uncertain, because blindly retrying may produce a duplicate page.

The numbered journey passed a CLI test with duplicate page titles and a
read-only run against a connected notebook. No live page was created. The
remaining tradeoff is deliberate: a number is quicker to type, but it expires
and changes when the list changes. For durable automation, keep the full ID.
