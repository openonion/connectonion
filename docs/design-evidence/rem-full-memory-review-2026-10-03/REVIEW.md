# REM full memory and mobile reader review — 2026-10-03

An independent AI reviewer took the role of a technology founder with marketing
and UI experience. This is a role-based review; no human founder participated.
The reviewer opened the actual local reader at 1440px and 375px and inspected
person, project, skill, organisation and owner records. Checks covered the
focused opening, full note, source jumps and dialogs, the privacy control, the mobile
navigation menu, search, status and the first phone viewport. Private notebook
content and screenshots remain local. The images here use an invented fixture:

- [Desktop person, full memory](person-desktop-full-memory.png)
- [Phone person, opening and navigation](person-phone-navigation.png)
- [Phone person, full memory](person-phone-full-memory.png)
- [Phone skill, full memory](skill-phone-full-memory.png)

| Priority | Problem and user impact | Evidence | Change and recheck |
| --- | --- | --- | --- |
| P1 | The complete note and its sources required an extra expansion click, hiding the very material people opened the page to read. | The previous reader used a closed `details.deep-note` on every record. | Full memory is a permanent, labelled section. Reopened all five record types at both widths: original prose and citations are visible without a toggle; source links still land on visible headings. |
| P1 | On phones, the Full memory heading led into long Facts/Usage panels before the original prose. This made the new visible section feel empty of memory. | Heading-to-prose gap on the five sampled record types was 440–895px at 375px. | Placed original prose before auxiliary panels below 1180px. The recheck measured a 77px gap on all five types; no horizontal overflow. |
| P1 | A merged project view promoted a later `Now` update over its lasting `Pattern` finding. The first screen lost its useful takeaway. | Browser regression fixture showed “A release was requested in July” instead of its earlier, cited send rule. | Project leads now prefer `Pattern`, then `Now` and `Changed`; the targeted desktop/phone browser test passes. |
| P2 | Phone search, Browse notebook and the category back link were hard to tap. | Their hit boxes measured 36px, 37px and 16px high. | Each measures 44px in the final 375px render; a browser test checks the boxes and page width. |
| P1 | Phone freshness and next-pass information disappeared with the navigation menu closed. | The snapshot/state line lived only at the foot of the opened rail, near the viewport fold. | A compact line now appears below Browse notebook. The final 375px view shows it in two lines and keeps `co rem start` together. |
| P2 | “Hide private” implied broader redaction than it provided, risking mistaken screen-sharing expectations. | Labelled sentences and raw excerpts were hidden, while identifiers and unlabelled prose remained visible; the scope was only in a tooltip. | The control now says “Hide labelled passages” and the visible footnote says raw excerpts also hide while other details stay visible. On desktop and 375px phone, its `aria-pressed` state toggled correctly, seven marked owner nodes hid/restored, and both source and conversation dialogs showed the matching restore instruction. |

Citation and privacy spot-checks: 38 same-page citation links on the sampled
person page and 39 on the sampled project page resolved to rendered source IDs;
sampled links opened their source dialogs. In the final owner phone view, privacy
mode removed seven marked nodes, and an already-open source dialog showed
the hidden-content notice. A synthetic browser check also verifies that a
cited, private owner next step remains linked when shown and disappears when
privacy mode is on.

Local browser evidence: the two reader files first reported 49 passed and two
failures from the merged project lead and an obsolete collapsed-state test; both
were corrected and their focused recheck passed. Subsequent focused browser
checks passed for the mobile hierarchy, tap targets, 15 phone routes in both
themes, owner citation/privacy, source jumps and navigation. The broader
offline Python suite and release CI are separate gates.

This is five sampled record types and their tested states, not an all-page
acceptance. The sampled owner record had no natural Next step block, so that
specific source/privacy case was tested with invented content. Historical
contact discovery and the usefulness of every written page remain open in
[#2176](https://github.com/openonion/connectonion/issues/2176) and
[#2190](https://github.com/openonion/connectonion/issues/2190).
