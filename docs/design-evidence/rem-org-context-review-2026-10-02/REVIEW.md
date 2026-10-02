# Organization context review — 2026-10-02

An independent AI reviewer used a technology-founder perspective with marketing
and UI experience. This is a role-based review, not human-founder participation.
Private mail, notebook names, paths and screenshots remain local.

## Scope

Two actual organization pages were investigated through the CLI. Their primary
mail was checked for distinct offers, acceptance, scheduling and unresolved
identity. Rendered pages were checked at desktop (1440px), phone (375px) and tablet
(768px): six full-page captures, twelve source/private-dialog captures and three
targeted original-source captures. Source open, private hide, restore and close
passed in six viewport/page sequences, with zero JavaScript errors, external
requests or horizontal overflow.

## Findings and rechecks

| Priority | Problem and user impact | Correction | Recheck |
| --- | --- | --- | --- |
| P1 | An unverified related-domain date became an unconditional target-organization Last contact. This made candidate context look like confirmed entity history. | The private page uses its last direct target-domain contact, with primary citation; related-domain activity stays explicitly qualified. Prompt requires the same boundary. | Primary headers and rendered Facts/header agree on the target-domain date. The related request remains visible with its scope. |
| P2 | A credits/tier acceptance could be confused with a separate free-month offer or completed provisioning. | Both pages distinguish the offers and state that meeting/setup outcomes are not recorded. | Independently compared dated primary offers/reply, then inspected distinct original-source popups. |
| P2 | Scheduling language became a technical broken-link claim; shared subject/signature became a verified exchange/person identity. | Manually removed those overclaims from the trial pages; tightened the investigation prompt. | Reviewer reread the original messages and corrected pages. Common person/domain/legal identity remains unverified. |
| P2 | Available archived original mail appeared unavailable because hashed citations did not match native indexed IDs. | Reader resolves a unique provider/hash archive pointer and verifies the native-ID digest, retaining direct-ID lookup. | Five cited originals recovered; separate offer and acceptance popups display their own originals. Mismatched-pointer regression rejects a false match. |
| P2 | Phone clipping hid the main uncertainty, and a related-domain call lost its scope in Next exchanges. | Shortened the private page lead and kept related-contact wording in the open thread itself. | Final phone lead exposes acceptance plus unconfirmed outcomes; rendered thread retains candidate scope. |

## Pipeline changes

Mapped target domains remain search handles after the title becomes a brand name.
Exact addresses on another organization page sharing a contact candidate can add
primary correspondence, marked as related context. Shared display names/map rows
are leads, not identity proof. Unrelated contacts on the candidate domain and
prose-only domain matches are excluded. Scoped attachment/evidence metadata stays
visible to the investigator. Previously cited target mail is retained when newly
gathered related mail requires comparison of distinct dated offers.

## Verification and limits

- Current full REM unit gate: **1,678 passed in 77.06s**, with `TERM=xterm`.
- Focused reader/context/first-run gate: **52 passed in 22.51s**; overlaps the full gate.
- Earlier run under `TERM=dumb`: 1,674 passed, two terminal-render tests failed.
  No test was removed or relaxed; the final gate used terminal capabilities.
- These two trial pages required manual source-backed precision corrections.
  Prompt edits and passing structural tests do not establish automatic semantic
  reliability or all-page usefulness.
- Remaining P2 items: mechanical Connected context explanations, repeated mobile
  activity/state information, background-update wording and lower-page action placement. Existing #2065
  tracks the broader reader experience work.
- This review does not cover all organization/person/project/skill pages,
  live account provisioning, actual meeting outcomes or external legal identity.
  No release or package publication was performed.

Related issues: #2157 (cross-domain context), #2164 (brand-title domain loss),
#2165 (hashed source lookup). Separately discovered voice-input coverage gap
#2166 is outside this organization review.

The reviewer inspected all 21 final captures. Targeted commercial-source images
were desktop samples; phone/tablet private-dialog checks used a later scheduling
source. Full-note field-by-field interaction, dark/search/error states, linked
pages and keyboard/screen-reader behavior were not retested in this round.
