# Sprint 9 ordered integration

Fixture-only integration on the new Mac, starting from `ce727ddc` on
`release/1.9.3rc60`. No owner notebook used; no push.

## Ordered merge decisions

1. `sprint9/people-person` (`0f363a42`): reader merged automatically. Browser
   test append conflict resolved by retaining rc60 task receipt/deliverable
   cases and all new person/People cases. Shared unit JavaScript harness uses
   personSub/personOrg/personProject for the new layout and retains taskResult
   for rc60 task cards; contactLine was removed by the intentional redesign.
   Independent AI source review caught a prepared-draft CTA pointing at Today;
   repaired using the existing review card and its live/static/privacy guards.

## Verification

Each merge runs Node syntax checks for every reader script block and the
complete unit command requested by the owner. Logs are retained outside pytest
basetemp; basetemp is removed after each complete suite. Browser full suite
will be invoked once with two workers after all six merges.

### Initial environment and coverage repairs

Initial full unit run: `6 failed, 18512 passed, 19 skipped, 2944 warnings in 137.17s (0:02:17)`.
The merge's lazy startup harness lacked `peopleMode`, `notDoneKeys` and
`notDoneStorageKey`; its fixture now represents the new storage state.
Four terminal color failures came from inherited `TERM=dumb`; SIGHUP shutdown
failed because this harness inherits `SIG_IGN` for SIGHUP. Later suite launches
use `TERM=xterm-256color` and restore default SIGHUP before executing the exact
requested uv/pytest arguments. No product or test assertions changed for those
five environment failures. Focused ordinary-terminal recheck: 93 passed, with
only the ignored-SIGHUP case still failing before signal normalization.

The empty-between-you and person-lead browser cases retain their original names
with the new owed-card/full-memory assertions. Removed person-lead punctuation
and privacy cases and active/old/no-index metric cases were restored in
`test_rem_person_integration.py` against current rendered paths. The existing
no-reply reason coverage remains, and a new primary-action regression prevents
asking for another reply where the draft explicitly says none is needed.
