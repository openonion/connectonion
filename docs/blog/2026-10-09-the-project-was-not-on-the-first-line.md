# The project was not on the first line

[Issue #2336](https://github.com/openonion/connectonion/issues/2336) reported
an empty Claude Code project map despite daily work in repositories. The
sessions were present; the scanner was looking for their working directories
in the wrong place.

Project discovery read only the first JSONL record. Claude Code can start a
session with a queue, mode, or bridge record, then put `cwd` on a later message.
The message reader already understood those later rows. Project discovery
stopped before reaching them.

An isolated transcript with a preamble followed by a user message reproduced
the missing project for all three record types. Those three tests failed before
the change; a transcript without a working directory correctly stayed absent.
The scanner now looks forward for the first recorded `cwd`, stopping after
256 records or one megabyte. Other source formats still use their first record.
Decoding Claude's folder name would have been shorter, but hyphens make that
encoding ambiguous: the recorded path is better evidence than a guess.

This repairs discovery, not the meaning of a generated memory page. The tests
use invented session files, not an owner's private history. Existing project
exclusions and repository grouping remain responsible for deciding which
discovered folders belong in the map.
