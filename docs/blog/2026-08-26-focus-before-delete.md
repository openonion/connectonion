# Focus Before Delete

*2026-08-26*

A browser agent clicked a LinkedIn profile editor, received a successful click
result, and sent the ordinary replace-text sequence: select all, then delete.
The click had not moved focus into the editor. Select all highlighted the page,
delete closed the modal, and every command still returned success.

No individual operation was broken. The sequence was unsafe because the caller
could not observe the state that made the next operation safe.

## A screenshot arrives too late

The browser tools already recommended taking a screenshot after typing. That
can detect text landing in the wrong place, but destructive shortcuts have no
useful “after.” Once the editor closes, the screenshot only records the loss.

The practical workaround was to type a canary, take a screenshot, inspect it,
then replace the canary. Two round trips and an image were being used to answer
a synchronous DOM question: what has focus, and can it accept text?

## Make the precondition observable

`get_focused_element` now returns bounded JSON for the active element: its tag,
role, label, editable state, and a short value preview. Password values are
always redacted. Focus is followed through open shadow roots; iframe and closed
shadow-root boundaries stay opaque and therefore fail safe.

Observation alone still leaves every caller to remember the rule. So
`keyboard_press` enforces it at the dangerous edge: select-all, Backspace, and
Delete are refused when focus is not editable. An explicit override remains for
intentional page-level shortcuts, making the exceptional intent visible in the
call instead of inferred after damage.

## Test the sequence, not only the methods

Unit tests cover shortcut classification, refusal, ordinary keys, and the
override. Daemon tests prove that the new JSON query and boolean flag survive
CLI serialization. A real installed browser then exercises password redaction,
textarea and contenteditable focus, an open shadow root, detached focus, an
iframe boundary, and the original page-wide select-all failure.

The full non-network regression gate passed 7,251 tests. More importantly, the
incident's three individually successful commands can no longer compose into a
silent destructive action: the boundary now checks the state the sequence
depends on.
