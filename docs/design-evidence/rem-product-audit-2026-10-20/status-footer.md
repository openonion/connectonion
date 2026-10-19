# A bounded status footer — #1988

## Observed

Read-only inspection of the current saved notebook found308 pages with an Investigation footer. Eleven have repeated known dated pass kinds;74 carry the old not-investigated placeholder and3 mention an obsolete requested-window note. These groups may overlap. This is footer evidence, not a semantic review of308 pages. No names, paths, source IDs or page text are published.

The existing note_pass appends on every successful pass. Fifty repeated passes reproduce the growing footer deterministically. A separate regression exposes that a page already ending in a newline loses its terminal newline when stamped.

## Change

On the next successful pass, keep the latest date for each recognized kind: mapped, written, investigated, enriched. On equal dates, keep the last supplied segment. Preserve unrecognized metadata, including dated custom notes. Remove the standalone not-investigated placeholder and exact or colon-prefixed Requested investigation window notes. Other historical window-note variants are retained unless a newer pass replaces their known operation. Prose, citations and sources remain unchanged; a terminal newline is consistently written. No bulk migration of the real notebook was performed.

The footer is a compact status summary, not a lifetime counter. The legacy unfinished JSON field investigated_passes counts visible stamps, as before; it no longer implies the number of historical passes on compacted pages. The operational queue sorts by recency, mapped volume and Unknown count, and reads the latest investigated/written date; it does not use that count. Existing run records keep the separate execution history. This repair does not invent missing run records or change a run's outcome.

## Verification and limits

Three new tests failed before implementation: repetition across dates/kinds, legacy cleanup, and a first footer's terminal newline. Independent review caught arbitrary dated metadata being classified as a pass. A fourth regression reproduced that loss before recognition was restricted to the four known kinds.

The final file/queue tests pass54 cases. The broader files, queue, investigation, project pages, map, terminal, daily round and census suite passes343 tests on the final code (8.78 seconds). Applying the helper in memory to current footer strings leaves no repeated recognized pass kinds. Real pages were not written.

No new init, provider collection, model call or scheduled run. No browser screenshot or visual acceptance is claimed: the existing file-preview security restriction still applies. The raw status summary changes, not reader layout. #1988 stays open for its separate page-length/content-quality requirement; a character cap alone cannot establish that supported facts survived.
