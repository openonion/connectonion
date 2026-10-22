# Three clocks in a memory

Candidate design for [issue #2629](https://github.com/openonion/connectonion/issues/2629), not yet released. Preview availability is unchanged.

A contact page can carry three different times: when someone last wrote, when REM last worked on the page, and when a run recorded a rewrite. A recent date looks reassuring. It becomes misleading when the interface quietly swaps one clock for another.

A read-only notebook scan flagged two People candidates. A recheck with the canonical census confirmed one whose projected activity came only from an investigation footer; the other had a source activity date and was excluded. An invented regression fixture separately covers explicit unknown contact. The reader could still display the maintenance date as Last contact. Offline tests reproduced that substitution, plus a second problem: a recent or even future footer could make a page appear in the latest run's rewrite list without that run recording the page.

The candidate keeps source activity separate from maintenance. Unknown contact stays unknown unless a genuine source or existing mail map supplies activity. Original maintenance footers remain readable. Latest-pass attribution requires recorded changed paths. A dated summary and first-build wording replace assumptions that work happened last night or today.

We considered file modification time and a rolling 24-hour night label. Mapping can rewrite files without new contact, and daytime work is not overnight. We also dropped the quiet-state claim that every rewrite was merely rewording: missing claim-change records do not prove the world stayed the same. The page says what was recorded.

The tradeoff is fewer attributed updates when old logs lack changed paths. The current pass still groups runs within 18 hours; first build means the first retained run group, not verified original account history. If a durable run-to-page ledger becomes available, it can replace that grouping without borrowing dates from prose.

Offline parser and JavaScript contracts check temporal attribution. They do not certify rendered desktop, phone or accessibility behavior. Native acceptance, independent review and exact-head CI remain required. No new real init, model or provider trial was run; no private source content is published here. Package security and compatibility gates still apply before release.
