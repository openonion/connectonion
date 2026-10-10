# Project source identity and availability review — 2026-10-02

## Scope

Independent AI review from the perspective of a technology founder with marketing and UI experience. This describes a role-based review, not participation by a human founder. The notebook, source bodies, identifiers and screenshots remain private. No new model investigation or quota override was performed.

## Findings and fixes

| Priority | Finding and user impact | Evidence | Fix and recheck criterion |
| --- | --- | --- | --- |
| P1 | A citation could display unrelated input with the old source metadata, undermining source trust. | Independent SQL + JSONL audit: 927 identity mismatches among 1,454 indexed session rows; 75 mismatched IDs were cited by project pages. | Require exact archived source identity when reading JSONL. Rewrite project material and refresh its index under one maintenance lock. Test older insertions with both lock ownership modes, and refuse stale bodies in source and conversation reads. |
| P1 | A contact link could abort rebuilding the index, leaving unrelated project sources stale. | A real refresh failed in URL parsing on a Markdown link. | Recognize LinkedIn by anchored host, support Markdown links, and reject lookalike hosts. Test malformed, Markdown and disguised URLs without adding exception suppression. |
| P2 | Ordinary coding inputs could be mistaken for full conversations or completed work. | Most archived coding inputs had no explicit input scope. | Add a reader default explaining that assistant replies and tool results are absent; preserve existing voice and older Desktop limitations and mail/instruction scope. |

Accepted project and investigation checkpoints also refresh derived page state under their existing maintenance locks.

## Source audit after repair

- The derived index was rebuilt, and the real reader snapshot regenerated.
- An independent direct SQL + current JSONL audit found **4,185/4,185** indexed native inputs with matching identities, zero missing bodies and zero mismatches across 20 project material files.
- **14 project pages** now have native original source access, versus five before repair. Availability is not claim validation.
- The reviewer compared **206 native source-context excerpts** from the actual HTML with exact archived text prefixes; all matched. These excerpts include citations outside project pages, so 206 is not a project-only count.
- Previously generated HTML embeds old text. Regenerating a snapshot fixes that generated reader; this change does not retroactively update every historical HTML file or open tab.

## Actual rendered review

The independent reviewer inspected all 42 initial after images and two before images, then all nine targeted conversation rechecks after the scope-repetition fix. These are actual rendered pages from the real private notebook and default reader snapshot:

- Two fixed citation cases: one previously mismatched original and one previously unindexed archived original.
- Two project pages at desktop 1440px, tablet 768px and phone 375px: initial page, expanded full note, source shown/hidden/restored, and close behavior.
- One separate available native cited conversation at the same widths: project page, conversation shown/hidden/restored, and close behavior.
- Nine interaction sequences report zero JavaScript errors, external requests and horizontal overflow. These checks do not replace independent inspection of structure, content and design.

The review found that repeating the common input limit before every message displaced short inputs on a phone. It now appears once in a private conversation-level paragraph; per-message voice/older Desktop exceptions remain. Three final real conversation sequences and nine screenshots rechecked this change across all three widths, including hidden/restored/close behavior.

The two fixed source threads were outside the default bounded conversation selection; they were not injected into the snapshot for this review. The conversation case is explicitly separate.

## Verification

- Three reproducing source/index tests failed before the fix and passed after it, including both lock modes.
- **199 focused unit tests passed in 32.80s**, covering store, projects, workspace attribution, investigations, first run, reader and facts, before the final default input-scope change.
- **41 final source/reader/facts unit tests passed in 2.55s** after the input-scope change.
- **Three final source/conversation privacy and mixed-input browser tests passed**, 16 deselected, in 8.26s. The mixed-input test uses a synthetic fixture to verify a single common limit, preserved voice limitations and hidden private content. The real conversation recheck contains ordinary inputs, not mixed voice inputs. The earlier two-test run passed in 6.38s before the repetition fix.
- These gates overlap and are not added together. The initial broad run had two environment-dependent terminal rendering failures and two incorrect new fixture assumptions; `TERM=xterm` and corrected fixtures passed without removing assertions.

## Remaining useful-insight review

The reviewer read all 19 written project Insight sections, but did not validate every finding against every primary source. Several foreground checkout/release verification and give the user another checking task. Some contain concrete findings about defaults, price conflicts, project direction or data format changes. One temporary test page contains only an unknown Insight and needs classification review.

Recheck: a project lead should surface a concrete source-established progress, choice or change and its user impact, then state necessary unknowns. User requests alone cannot establish completed work. The all-page semantic and usefulness audit remains incomplete; four prepared project investigations still await the user's resource choice.

| Remaining priority | User impact and observed evidence | Concrete recheck |
| --- | --- | --- |
| P2 — project activity scope/date | One rendered project has an older mapped activity date in its header/cards and a newer request date in the full note. The newer source came from that workspace but asked about backend work; it cannot automatically establish progress on the page's project. | Separately verify where input was supplied, which repository tools touched and what the request concerns. Make the lead and dates consistent about that scope without inventing completed work. |
| P2 — old requests foregrounded | Old unresolved requests occupy the lead/open-thread hierarchy, but absence of assistant/tool evidence cannot establish that they still need action. | Compare request-specific follow-up/outcome evidence and distinguish confirmed pending work from status unknown; surface the most useful current source-established finding first. |
| P2 — connected context hierarchy | Mechanical relationship cards occupy much of the phone page before the useful cited evidence. | Review each relationship's concrete value, keep the most useful links visible and disclose incidental connections progressively; recheck initial and expanded phone states. |

These semantic and hierarchy issues remain open. The rendered sample covers two project pages and one separate conversation case, not every page type or every record.

Tracked in #2177 and #2122. No release or package publication is included.
