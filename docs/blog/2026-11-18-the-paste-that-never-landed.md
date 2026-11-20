# The paste that never landed

This morning `keyboard_type` started pasting. On a Mac, 1,402 characters went
into a React textarea in 2 seconds. The same command on a Windows dev box ran
for 121.7 seconds and left 920 characters in the box.

The Windows box was driven over OpenSSH, with headless Chrome running in
session 0. The clipboard itself worked in that session: `Set-Clipboard`
followed by `Get-Clipboard` returned the same text. But Ctrl+V into headless
Chrome never changed the field. The check that a paste landed saw no change,
so the command fell back to typing one key at a time, and the 120 s timeout
cut it off. The command still said `Typed:` and nothing else.

## A second fast path

Chrome's DevTools protocol has `Input.insertText`. It is how an input method
commits text: one call that fires the field's input event and needs no OS
clipboard. The Chinese fallback already uses it one character at a time. Now,
when the paste does not land, the whole text goes in through it in one call.
Key-by-key typing is left for a field that takes neither.

A real headless Chrome test runs with the clipboard taken away. It enters
1,402 characters in under 10 seconds, and the page's own input handler counts
1,402.

## Saying which path ran

The result now has a second line: `Entered by paste.`, `Entered by CDP
insertText: the field did not take the paste.`, or `Entered key by key.` A
caller no longer has to work it out from how long the command took.

When typing key by key does run past the timeout, the message says so. Part of
the text is already in the field, so clear the field before retrying. See #2901.
