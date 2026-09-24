# Three of the issues were already fixed

The ask for this preview was short: fix the multi-device bug, then write PRs
for the CLI issues we had filed. There were fifty-odd open issues mentioning a
`co` command. The first useful hour went into reading them, not writing code.

Most of the list was not a list of bugs. RFCs, epics, and features scheduled
for 1.9 look the same in an issue tracker as a broken exit code, and a PR
"for" an RFC decides something nobody asked me to decide. Nineteen were
concrete defects or small gaps. Of those, three were already fixed. `co ai`
had exited 1 on the iteration cap since 30 August. `co browser list_pages` had
shipped the tab hand-off in 1.8.5b7. `co gmail send --attach` had been in the
product since 1.7.0a1. Each issue was still open because nobody closed it when
the fix landed — so the tracker described a CLI worse than the one people had
installed. They were closed with the commit and release that fixed them.

The other thing worth writing down is what caught my mistakes. My tests for
the `co browser close` fix passed. The fix used `psutil`, which is in our dev
extra and nowhere else, so every ordinary install would have crashed on the
command the fix was meant to make reliable. The unit tests could not see that;
they run in the dev environment. The Windows and macOS end-to-end jobs install
connectonion the way a user does, and both went red within minutes. The fix now
uses one `ps` call on macOS and Linux, and we reran the real daemon with
`psutil` made unimportable before calling it done.

The same thing happened with the WhatsApp group tests, which imported the SDK
that CI does not install, and with a React release number another session had
taken a few minutes earlier. None of those were found by reading the diff. They
were found by the parts of the process that run the code somewhere other than
the machine that wrote it.

So this release note ends with a script instead of a sentence:
`scripts/two_device_acceptance.py` starts a real Host and three signed clients
and checks eight things, directly and through the production relay. The
pictures in the release are that script, run against the release commit.
