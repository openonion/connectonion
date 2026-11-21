# Granola complete source feature — current evidence

Branch: `feature/granola-source-20261106`. Team base: `049a74e81c0f347dddf1d2c1378d970d950e481e`.

## Implemented

The existing source CLI feeds opt-in, approved notebook-local records into normal
REM Init inventory, Investigate gathering and Maintain, using the configured
runner. Existing Reader resolves version-pinned citations and safe original URLs.
No mandatory project label, new scheduler or Reader-open synchronization hook.
The source-specific Skill preserves authorship/summary provenance, uncertainty,
semantic categories and source privacy; generic stage/page Skills are unchanged.

## Verification performed this round

- New offline integration regressions cover consent/dry-run, selected identity
  and scope, corrupt/foreign/symlinked rows, first/repeat/same-timestamp body
  changes, model failure/progress, budgets, complete canonical claim packets,
  old-citation-to-latest retrieval, protected project/cooling promotion, Reader
  contexts/aliases and inline free-form citation normalization.
- Six behavioral benchmark cases authored before the source Skill and schema
  checked (3 normal, 3 counterexample). This is not a six-case agent eval pass.
- Actual configured **Codex / gpt-6-luna** normal CLI trial, **synthetic evidence**:
  no project label; first sync assessed 1 note and wrote 1 Knowledge page;
  repeat assessed 0 and made 0 model calls. A changed body with the same source
  timestamp assessed 1, updated the same Knowledge page, and repeat again made
  0 calls. Both old/new citations resolve, 2 Reader contexts; no timer installed.
- Actual OneNote model output exposed inline `Sources: [1] ...` not discoverable
  by Reader. Both note integrations now share equivalent source-specific normalization;
  Granola also fixes provider/link dispatch and labels summary provenance.
  The subsequent normal-model updates produced both resolvable references.
- Independent AI review of both integrations found/fixed source-specific optional-media,
  error help, privacy/canonical resolver, old-version retrieval, protected-page
  and evidence-routing issues.
  This is an AI code/data review, not a human or visual acceptance claim.

Historical authenticated source-CLI evidence remains in `granola-cli-remediation.md`;
it is separate from the new synthetic source-to-model trial. Current model
Knowledge prose was inspected for date/scope/summary attribution. No source
writes or generated source content/credentials are committed.

## PR explanation: notes with no known project

Users may not know which project their notes belong to. Requiring a project label
would make users do the organization this feature should assist with. Therefore
Init does not invent deterministic entities from a notebook/folder/title; normal
Maintain performs semantic organization using the customer's existing Skills.
Useful unclassified material can stay in Knowledge/Notes. Project links need
substantive evidence; uncertain identity/association remains uncertain. This is
also a model-quality acceptance case. This implementation does not claim perfect
automatic project classification, cross-source identity matching or all-note
classification accuracy.

## Remaining acceptance / boundaries

- User-performed selected authenticated import completed: 2 summaries were
  processed under the global source rules, yielding 1 Notes page and 1 assessed
  no-change; the normal repeat used 0 calls. Activity routes to that Notes page.
  Real edited-source updates, source-page clicks and visual acceptance remain pending.
- Explicit Investigate note gathering and canonical audit compatibility are
  tested offline; no new real-model project/person Investigate is claimed here.
- Source CLI still owns remote collection. This does not add remote polling.
- Whole-notebook Maintain uses the customer's existing multi-page templates
  (about 38k instruction characters in this trial), not the 15k one-page turn
  route. Large notebooks/model-quality/cost remain broader platform concerns;
  no global prompt, harness permissions or daily quota was relaxed.
- Team branches inherit shared develop history. Before upstream submission,
  select/refresh the real client base and port a focused complete source diff
  plus needed common dependencies; do not submit inherited sibling work.
- No upstream PR, MR or develop merge is created by this implementation round.

## Validation summary

Final selected regression counts and the known baseline failure are recorded in
the delivery handoff. Existing `test_first_batch_runs_before_the_clock_is_installed`
was already reproduced on the original baseline; it is not hidden or weakened.

Final review: independent AI recheck passed OneNote 75 / Granola 79 selected
checks; reviewed code, actual synthetic before/after prose and Reader structure.
No remaining significant blocker in the reviewed scope; no visual/click claim.

Selected broad regressions: 1,042 passed / 1 existing baseline failure. Final source/Reader/help focused reruns are separately recorded; no tests or scheduler gates were weakened.
Final CLI help/source checks: 108 passed; scoped existing audit walker/checker reaches all 3 sources/add/remove pages and passes all 10 rules. Initial standard co audit ran before discoverability repair and checked only its parent page; the final scoped check is recorded separately.

## Latest taxonomy decision and citation compatibility

The user explicitly chose the customer's **global** rules. The eight main Reader
sections are not a whitelist for every generated page. Legitimate Notes/Activity
and auxiliary organisation workflows remain available. Temporary integration-only
folder gates, source-first overrides and org-gather exclusions were withdrawn
before publication; source/stage/page Skills and the runner are unchanged by this
follow-up. A Notes page should be located through Activity, not All records.

This follow-up only normalizes this source's singular/bare Source(s) heading when
followed by its numbered pinned definitions. The existing canonical Sources
format is preserved. Actual Reader sourceList/citationId tests cover all four
observed spellings, plus positive regressions proving source-derived Notes can
still be promoted and relevant organisation investigations can still gather them.
The body/category is not manually rewritten. Earlier constrained-classification
model experiments do not define current behavior or customer requirements.

Final customer-global-scope independent recheck: 85 selected import/source-link/Reader-section tests pass; runner/source Skills/global Reader remain unchanged. No additional classification model run was required by the rollback.
The original real-account Notes output used `## Source`: backend lookup worked
but the Reader JS list did not. Re-applied the same source-specific promotion
normalizer to that heading only, asserting body and category unchanged, then
regenerated Reader. Actual JS now recognizes one Granola citation in the existing
Notes page; All records remains 0 and Activity contains 1, as the global rules
specify. No source API/model call or forced recategorization occurred.
