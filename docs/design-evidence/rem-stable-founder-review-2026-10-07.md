# co rem 1.9.0 reader review

An independent AI reviewer took the role of a technology founder with marketing
and UI experience. This is a role-based review, not a claim that a human founder
participated. The reviewer inspected the rendered, owner-only 90-day trial in
Chrome at 1440px and 390px. Ten private screenshots covered Today desktop and
phone, People list and detail, Projects list and detail, Skills list and detail,
and Organisations list and detail. Five follow-up captures rechecked repaired
Person, People, Project, Skill and Organisation views. Private screenshots stay
local; the checked-in [invented examples](../releases/assets/v1.9.0/manifest.yml)
show the visual changes without disclosing contacts or source content.

| Priority | Finding and user impact | Evidence | Resolution and recheck |
| --- | --- | --- | --- |
| P1 | People list columns overlapped on a phone, making contact facts hard to read. | Real 390px People list. | Let the contact cell wrap and adjust the table width. Rechecked at 390px without horizontal overflow; compare invented before and after People screenshots. |
| P1 | Bare numbered source buttons made evidence difficult to recognize, and a clipped lead hid part of the next action. | Real Person and Project detail leads. | Name buttons “Source 1” etc. and put “Read complete finding/relationship” before the citation action. Rechecked the expanded detail and evidence dialog in Chrome. |
| P2 | A Skill status pill implied that source mentions proved a completed investigation. | Real Skill list/detail. | Label it “Source reviewed”; rechecked the rendered Skill detail. |
| P2 | Persistent phone chrome takes roughly 215px before the first useful finding. | Real 390px Today and detail views. | Deferred to [#2309](https://github.com/openonion/connectonion/issues/2309) for 1.9.1. Recheck at 390×844: useful lead and citation should be available before nonessential chrome pushes them away. |
| P3 | Generic “Some findings” on a Project does not say why evidence is partial. | Real Project list/detail. | Deferred to [#2309](https://github.com/openonion/connectonion/issues/2309) for 1.9.1. Recheck list and detail for an interrupted or partial Project: state and next action should agree. |
| P1 | The stable release note's review and screenshot links, and two CLI detail links, returned 404 in the local docs preview. Readers could not verify release claims. | `/releases/1.9.0` and `/cli/rem` at 1440px and 390px. | Publish the linked review, manifest, and two CLI reference files with the site; recheck all four URLs return 200 and match their link text. |
| P1 | CLI still called itself a preview and said aliases worked only until 1.9.0; the site release note still promised future trial results. This obscured the release state. | `/cli/rem`, `/releases/1.9.0`, and the Design Journal article. | Align 1.9.0 labels and trial facts across all three pages; recheck their rendered text after the final source sync. |
| P2 | The 390px CLI guide is about 66,569px tall and its command section starts far below the first screen. | `/cli/rem` on a 390px phone. | Put the first command and a short jump list above the long reference; recheck the first viewport and links to the sections. |
| P2 | “Review failed runs” opened the maintenance section above completed and running rows, leaving the failure out of view. | Default reader Today on a 390px phone. | Focus and scroll the first failed run row; recheck the action on a rendered reader. |

The review checked value clarity, cited claims, next actions, hierarchy,
navigation, typography, spacing, state labels, phone layout and progressive
disclosure in those selected views and the five named docs pages. It did not
inspect every generated page or every possible interaction state. The trial's
aggregate page outcomes and source coverage belong in the release acceptance
record, not in this visual sample. After the fixes, local Chrome rechecked the
four formerly broken links at 390px: each target returned 200. The stable CLI
title, quick command, and jump links rendered without horizontal overflow;
the first two jump links began at y=624px in a 390×844 viewport. On the real
reader, clicking “Review failed runs” focused the failed row at y=405px in the
same viewport. The release note and blog no longer promise future trial
results. These are local preview checks; public deployment links still need a
post-release check.
