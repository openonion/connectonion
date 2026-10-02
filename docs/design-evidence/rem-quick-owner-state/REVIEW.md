# Quick owner page state

## Observation

An isolated five-day init finished a quick owner pass and was stopped before the full pass by the configured 70% weekly quota floor. The old page footer said `investigated`, the JSON outcome implied completion, and the next command was `co rem open`. The page was still a sample. Private notebook content and source identifiers are omitted.

## Synthetic browser review

- [Desktop after](quick-owner-desktop.png), 1440×900
- [Phone after](quick-owner-phone.png), 390×844

The fixture uses invented people, dates and sources. Both widths show `Quick sample`, the incomplete-coverage notice and the resume command. The browser test checks for no horizontal overflow, JavaScript errors or external requests, then simulates a completed full pass and checks that the notice disappears.

## Scope

This branch makes saved and displayed coverage truthful and lets a later init reuse the accepted quick sample. It preserves the existing 70% quota floor. It does not establish that a quick page has a consequential finding or that any private claim is supported by its citation. Those remain open in #2172 and related owner-quality work.
