# Desktop and voice input review — 2026-10-02

An independent AI reviewer used a marketing/UI technology-founder perspective.
This is a role-based review, not human-founder participation. Private inputs,
source paths and record names remain local.

## Findings and changes

| Priority | Observed problem and impact | Correction | Recheck |
| --- | --- | --- | --- |
| P1 | Ordinary older native Desktop requests were discarded because client content kinds were not recorded. Mapped pages stayed empty. | Recognize the observed turn-id-only shape in native Desktop/vscode and interactive CLI sessions. Exclude bare imports, exec wrappers, subagents, injected context and scheduled automation prompts. | Four target pages retain 10, 25, 5 and 8 inputs. Reviewer compared all 48 stored inputs to original session ids/byte offsets. |
| P1 | Explicit voice input was lost with its wrapper. Importing the whole wrapper would misattribute assistant replies and duplicated context. | Extract only the observed explicit input segment; omit mixed transcript delta, tail-flush summaries and unknown wrappers. Preserve voice recognition limits. | 25 voice inputs match primary input segments exactly; two tail-flush summaries and worker copies remain excluded. |
| P2 | Provenance limits could disappear after extraction or look like verbatim typed input in the reader. | Preserve input_scope through project state, material, searchable evidence, cited source context and conversations. Display the limit inside the private content block. | Storage/reader regressions pass; an invented voice fixture shows scope, hides it, restores it and closes the source dialog at three widths. |
| P2 | An empty write queue claimed every project page had been written. | Say no new retained input is available; pages without usable evidence remain uninvestigated. | Inspected current command copy; this does not remove unwritten pages from the usefulness audit. |

Older Desktop language-frequency assumptions were removed: English/Chinese
frequency cannot establish authorship. Skill mention caches use version 4 so
unchanged source files are recounted. The prompt distinguishes unrelated topics
inside a voice workspace and requested work from verified implementation.

## Actual source evidence

The 180-day private project refresh retained 5,245 inputs from 5,515 session files,
with zero unfamiliar formats reported and no new mapped pages created. This
includes more than the four target pages. Zero unfamiliar formats does not mean
every user-slot row was read. An automation container has eight independent
manual corrections/confirmations, which are distinct from 113 excluded scheduled
or injected rows. The initial issue's plain-prefix classification was refined by
reading these originals; not every plain prefix was an automated run.

## Rendered verification

An invented voice workspace was stored and indexed through the actual pipeline
and rendered with the actual template. Nine captures cover page, source dialog
and private-source state at desktop 1440px, phone 375px and tablet 768px. All three
sequences show input scope, hide it with private content, restore it and close the
dialog; zero JavaScript errors, external requests or page overflow.

This is synthetic UI coverage. It does not establish that the four real generated
pages have useful findings. The independent reviewer also checked the new source
and reader code, primary inputs and exact artifact coverage.

## Gates and remaining work

- Source-round full unit gate: **1,682 passed in 267.70s**, before subsequent reader additions.
- Source/project focused gate: **88 passed in 9.84s**.
- Source/instruction checks: **63 passed in 3.75s**.
- Subsequent reader/store/source/instruction gate: **87 passed in 12.28s**.
- Browser gate before the final copy refinement: **27 passed in 190.14s**.
- These suites overlap; they are not summed as distinct tests.

The initial three-page generation attempt finished **zero** pages: the configured
weekly quota guard refused new model work. Four candidate pages remain unwritten. A resource
choice is pending with the user. No guard override, alternate model switch,
publication or release is included. Four bounded prompts contain 48 retained
inputs; estimated initial input is about 32,825 tokens, with agent rereads adding
billed context.

Still required: generate the four real pages when model resources are authorized,
check every conclusion against the retained primary input, review rendered
structure/content/design and fix/recheck significant findings. The wider
person/project/skill usefulness audit remains incomplete. Synthetic scope/privacy
checks are not full-page anonymization, speech-recognition accuracy validation or
an all-record semantic pass. Background state wording, repeated mobile metadata
and mechanical Connected context remain in the earlier reader backlog.

Related issues: #2166 (voice wrapper), #2167 (older native Desktop inputs).

Independent review found that the scope wording exposed internal client terms.
The UI now explains voice transcription, omitted conversation context and possible
recognition errors in plain language; older Desktop input also has a short source
limitation. Detailed original scope remains in source data. The independent reviewer inspected all nine refreshed synthetic captures. Plain-language
voice scope and the excerpt remain readable at all three widths; private mode hides
both. The targeted source/conversation scope-and-privacy test passed: **1 passed,
14 deselected, 4.86s**. Older Desktop wording was checked in code; this fixture
does not provide real-page generation or older-Desktop/conversation screenshot
coverage.
