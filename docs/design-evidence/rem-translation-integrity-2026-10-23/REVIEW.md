# REM translation source integrity — issue #2656

Candidate based on main fad11f62; public installed preview remains 1.9.3rc16.
No all-page, semantic translation, native accessibility or maturity acceptance.

## Reproduction and decision

A synthetic translation kept [n] counts but changed a gmail source target. Other
red cases swapped targets, changed path/revision/hash/query/fragment, moved
citations between claim lines, or supplied a matching-digest bad cache/header.
Fix deterministic identity at cache write/read and canonical reader routing.
Keep valid version-2 caches, retain invalid bytes, never translate on read.
Unknown definition syntax stays literal; duplicates/multiple sections refuse
translation before execution. Source captions require matching privacy state and
use the existing privacy class; other source identity/privacy surfaces are not
claimed fixed.

## Verification so far

- Backend original red: 13 failed, 2 control cases passed. Backend first green
  including existing translation tests: 63 passed.
- Reader routing original red: 6 failed, 15 passed. Composed reader/backend
  existing related green: 300 passed.
- Boundary red: 4 failed, 22 passed (ambiguous canonical pre-call and changed
  caption privacy state). Corrected broader related suite: 554 passed.
- Specialized Sources caption concealment corrected original-base red: 1 failed
  on missing private class. An earlier fixture lacked sourceLabel, so its
  ReferenceError was discarded as product evidence. A later empty-source branch
  needed a markdown fixture stub; that dependency failure was also corrected.
- Final affected reader/model/page-review/translation suite: 558 passed, 8.95s.
  Includes synthetic backend snapshot JSON cache exclusion and byte preservation.
- Independent AI working-tree review found reader ambiguity when an Unknown
  definition was filtered before duplicate counting, or another Sources section
  was ignored. Both new regressions failed before repair (2 failed, 30 deselected,
  1.09s). Count definitions before filtering and refuse multiple sections.
- After review repairs: final affected suite 560 passed, 10.95s.
- Full CI scope, independent final exact-head review and remote CI: pending.

Actual reader functions use logical element/document/panel stubs. They check
canonical routing, source identity/label/selector/excerpt data flow, captions and
privacy-class emission. They do not establish real DOM behavior, styling, layout,
focus, privacy-toggle concealment, popup usability or desktop/mobile/accessibility.
No browser, alternate renderer, screenshot workaround, real init/model/provider,
scheduler or real notebook/cache mutation was performed. No visual before/after
image exists for this candidate. Native evidence remains an explicit gate.
