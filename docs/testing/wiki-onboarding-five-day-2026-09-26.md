# Wiki five-day onboarding acceptance, 2026-09-26

This was an isolated local run against the user's already connected sources. No
private correspondence, contact names, prompts, or generated personal pages are
committed with this report. The notebook lived under a temporary, private root.

## Acceptance route

1. Run `co wiki doctor`, then `co wiki init --days 5` in a new notebook.
2. Check that People, Organizations, Projects and Skills have deterministic map
   pages, source coverage, a useful next command, and progress during the run.
3. Investigate one person and one project with `--days 5`; inspect run records,
   candidate pages, citations, model tool behavior, and reported usage.
4. Open the local reader and exercise its opt-in Chrome regression suite.

## Observed issues and changes

| Finding | Reproduction | Change |
| --- | --- | --- |
| Custom window lost in the next/retry command | A five-day init suggested an unscoped investigation; partial retries lost `--days` and selected mailboxes. | Keep the selected window and mailboxes in the printed commands. |
| No useful foreground progress | A map or investigation could appear stuck during mailbox reads and extraction. | Emit map/source stages and persist investigation stages, chunk counts, and completed-chunk usage. |
| First-run terminal dump | One map printed 4,800 lines and 244 KB, including contact metadata. | Human output is a short count and next step; full detail remains in the private map and JSON mode. |
| Expensive owner investigation | A full five-day owner run was stopped after 45 minutes, four completed extraction chunks and one interrupted chunk, before a candidate existed. The underlying Codex records showed about 4.26 million input tokens (3.84 million cached) and 128 thousand output tokens; these are usage counters, not billed cost. | Init now suggests a clearly partial `investigate me --quick` first pass. The quick pass bounds recent mail-body reads, session items and model input to one synthesis turn. Full runs checkpoint completed extraction chunks for safe retry. |
| Project prompt and discovery ambiguity | A project with two session files but no relevant typed user turns produced a candidate only after many local search/read calls. | The runner and Skill agree on a bounded exception for recorded project Paths; a file-name inventory gives leads without claiming their contents. |
| Generated projects in the map | Nine same-name `notebook` entries came from other Wiki task copies and test fixtures. | Exclude these execution workspaces during project scanning. |
| Partial category outcome reported success | Category investigation could return exit zero after a failed page. | Return a nonzero status while preserving per-page outcomes. |
| Project page can hide the chosen window | The fresh candidate cited older project files but did not say that both coding-session sources had zero relevant messages in the requested five days. After a page gained a citation on its `Paths` line, the next scan also treated `[1]` as part of the directory name. | Pass the requested window into coverage, add a sourced no-relevant-session notice to project pages, and strip citation markers before later path reads or session matching. |

The interrupted full owner run produced no candidate and did not replace a page.
Its prior preview version had no chunk checkpoint or live aggregate usage. The
new behavior has unit coverage for checkpoint reuse and interrupted-run usage.

## Verification status

The first five-day map completed with 46 People, 68 Organizations and 16 Projects
before the generated-workspace exclusion. The final fresh map has 46 People,
68 Organizations, 5 Projects and 159 skill names represented by 400 installed
copies, with 519 newly created pages overall. The corrected scanner finds no generated `notebook` entry,
workspace-container page, or duplicate project display name. The terminal
summary initially miscounted the Skills report object as six skills; its
renderer now distinguishes skill names from installed copies and includes
skill pages in the new-page total. A project investigation completed with a
structurally valid, source-linked candidate and replaced its page in the
isolated test notebook. It was not published to the user's main Wiki or
independently certified factually correct. The local reader's eleven opt-in Chrome cases
passed. The Wiki unit and CLI suite passed after the first group of fixes.

The full-suite shell-sandbox run hit browser-daemon socket failures. These are
environment-bound and must be rerun with local socket permission before release.
The source-checkout trial of one person initially delegated to an older `co ai`
because a relative `PYTHONPATH=.` no longer pointed to the checkout from the
task directory. The rerun uses an absolute source path. Neither failure
produced or promoted a candidate page.

The separate person investigation completed in 770.7 seconds with 43 supplied
items, 98,456 input characters, 1,647,649 reported input tokens (1,494,016
cached) and 38,575 output tokens. Its candidate used the person template,
defined 15 sources, and explicitly marked unsupported facts unknown. Sampled
claims about the relationship, a recent request and the reply were checked
against their saved source messages. It was promoted only inside the isolated
test notebook; the logged source path mismatch on the first attempt had not
promoted a candidate.

The bounded owner first pass completed in 535.7 seconds with one synthesis
turn and no extraction chunks. It read 24 of 60 already bounded gathered
items, used 21,396 input characters, and reported 429,022 input tokens
(369,408 cached) and 23,341 output tokens. The accepted page includes a clear
24-of-60 partial-coverage warning. It changed only the owner page. The large
reported model usage means this is a functioning first pass, not yet a cheap
one; cost is an explicit beta limitation.

After changing the quick prompt to read the already-bounded `material.json`
once rather than reconstructing split strings through repeated tool reads, a
fresh isolated owner first pass completed in 499.7 seconds. It again used 24
of 60 gathered items (21,404 source characters), generated a source-linked
page with an explicit 24-of-60 warning, and reported 169,548 input tokens
(112,640 cached) plus 20,852 output tokens. The input-token count is about
60% lower than the prior quick trial; elapsed time fell only about 7%.
Structural review accepted the page, but `factual_quality` remains `not
automatically assessed`. Three sampled source references were checked against
the supplied items. No claim of comprehensive factual approval follows from
this limited spot check.

The actual 519-page, 6.1 MB local reader snapshot loaded in Chrome in 0.18
seconds. Search returned results, a 375px viewport had no horizontal overflow,
and the run had zero script errors or external HTTP requests. Screenshots of
the private notebook remain in the temporary test directory and are not part
of the repository.

The fresh project investigation with the bounded local-Paths prompt also
completed, in 1,041.8 seconds. The model received the mapped page, source
coverage and a 61-line candidate-file inventory; there were no relevant
typed user turns in the five-day session sources. It read six distinct local
file bodies and wrote a 7,655-byte candidate with ten source definitions.
Structural review accepted it and promoted it only in the isolated notebook.
The page distinguishes dated fix-report claims from tests actually rerun, and
marks unverified platforms and ownership unknown. This is useful but costly:
1,120,354 reported input tokens (1,022,720 cached) and 30,854 output tokens.
The bounded file search prevents uncontrolled source expansion; it does not
yet make a deep project investigation fast. This remains a beta limitation,
not evidence that the first map or bounded owner pass failed.
The project's candidate omitted the zero-relevant-session window. After that
finding, the deterministic coverage notice was exercised against the saved
candidate and passed structural/citation review without repeating the model
call. The cited-path parser now recovers the actual directory on a subsequent
investigation; focused regressions cover both changes. These post-run fixes
have not yet been exercised by a second live project model call.

The full non-network repository suite first reported 12,351 passed, 31
skipped, 267 deselected, and six failures. One was this change's stale quick
material-count assertion, fixed immediately. Five other tests constructed a
gateway agent without `OPENONION_API_KEY`; all six passed in a targeted rerun
with a deliberately nonfunctional local test value. The full non-network suite
then passed with that test value: 12,357 passed, 31 skipped, 267 deselected in
570.54 seconds. PR review and public
preview smoke check remain pending at the time of this report update.
