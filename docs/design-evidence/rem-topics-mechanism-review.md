# Topic mechanism review — 2026-11-08

Independent AI role-based review: technology founder with marketing/UI experience
and engineering review. This is not a claim of human participation.

| Priority | Problem and user impact | Evidence and improvement | Recheck criterion |
| --- | --- | --- | --- |
| P1 | Missing reader imports crashed the topic snapshot. | `reader.snapshot` now imports its state readers. | Fictional topic snapshot renders successfully. |
| P1 | Private topics leaked through incoming relationship titles, lists/search and review subjects. | Reader filters and whole-topic curtain cover each route; shared snapshots omit private topics and their reviews. | With the curtain hidden, neither a direct topic route nor the related person's page reveals the private title/body; toggle restores it. |
| P1 | Negated/unrelated remember statements bypassed qualification. | `topic_map._requested` binds an affirmative owner request to that candidate's alias. | Both negated and unrelated requests remain below threshold. |
| P1 | An owner pronoun near somebody else's health was treated as owner health. | Require explicit owner-health attribution, leave ambiguous health out. | “I discussed Mara's asthma” and “my friend has asthma” never create a health topic. |
| P2 | A topic's first finding was its alias field. | `recordFocus` uses Where you stand for topics. | Current position appears as the first finding; aliases stay metadata. |
| P2 | Merging topic pages could lose aliases from the other header. | Reuse `merge_into`, then preserve the grouped aliases. | Either old record resolves to the survivor, with both histories and aliases retained. |
| P1 | Conflicting dates on copies of one source could invent a fourteen-day span. | Conflicting date evidence is excluded per source. | Copies with January 1 and January 15 dates cannot qualify a one-day topic. |
| P1 | Topic mail searches passed the domain pagination limit to a single-page API. | Bound topic text searches to 500 results per alias and report the bound. | Provider fixture rejects limits over 500; body-only alias still yields one deduplicated message. |
| P1 | Duplicate page evidence could erase an explicit owner remember request. | Retain structured speaker attribution and calculate owner intent before deduplication. | One user request still qualifies after the maintained page cites the same source. |
| P2 | Knowledge records were absent from census/name resolution. | Census counts knowledge; investigation resolves topic aliases. | Topic queue, status overview and alias selection all reach the same record. |

Actual browser coverage: public topic; private topic with curtain hidden/shown;
incoming topic relationships on a fictional person page; desktop 1280×900 and
phone 390×900. Supporting sentence and citation remained visible on public
relations. No horizontal overflow observed. A final direct DOM relationship check
showed Thermal storage while Family plans was absent behind the curtain.
Temporary browser artifacts were isolated outside the repository.

Remaining gaps: no live model investigation or paid-source trial. Knowledge uses
the existing generic reader layout. Dedicated topic anatomy, local graph and the
settled global canvas UI are separate reader work, not validated by these samples.
Historical extractions may need new Topics evidence to supply missing explicit
topic identities. Owner-notebook trial results are reported separately.

## Final validation

The post-fix REM selection passed 580 tests, including search identity, all reader
unit projections, topic scanning, graph data, instruction budgets, census and
investigation composition. The fictional CLI scan/queue smoke check passed.

The full unit command was run before the final isolated-JavaScript harness fixes:
44 failed, 18521 passed, 18 skipped, 2948 warnings, 2 errors in 2177.52s (0:36:17).
The helper was then added to the common reader test harness; related tests are
in the 580-test passing selection. The full suite has not been rerun afterward.

A separate 14-case rerun of other full-run failures gave 8 passed and 6 failed.
The same six failures reproduce on untouched HEAD ce727ddc: terminal ANSI styling
(four cases), SIGHUP host shutdown, and the sibling docs-site version mismatch.
They are outside the topic mechanism change. No full-suite pass is claimed.
