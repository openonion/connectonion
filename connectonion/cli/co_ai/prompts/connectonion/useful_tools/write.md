# write

Create a file, or replace one entirely.

Writing goes through `DiffWriter`, which shows the change and — depending on the
approval mode — asks before it lands. That is why writing a file is not the same
as `bash("cat > f")`: the user sees what is about to happen.

## Use it for

New files, and rewrites large enough that a diff of the whole file is easier to
read than a series of edits.

## Do not use it for

Changing a few lines in an existing file. That is `edit`, and a full rewrite
loses the reviewer's ability to see what actually changed.

Overwriting a file you have not read: you cannot know what you are destroying.

## Approval

In `safe` mode each write is confirmed. In `accept_edits` they land and are
shown. `ulw` runs unattended for a bounded number of turns. The tool is the same
in all three; only the gate moves.
