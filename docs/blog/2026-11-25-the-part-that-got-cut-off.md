# The part that got cut off

The `Shell` tool answers with one string: what the command printed, then `STDERR:` if there was any, then `Exit code:` at the end. When the string was longer than ten thousand characters it was cut there — at the end. So the exit status was the first thing to go, and the agent read a loud failure as a truncated success.

The fix is an ordering decision disguised as a length check. The command's own output is what grows without bound; the lines the tool adds are at most a few dozen characters. So the budget is calculated for the tool's lines first, stderr is fitted into what remains, and stdout gets what is left. Stderr goes before stdout because stderr is the part a caller acts on: an error message explains the failure, while the ten thousand characters before it usually do not.

Two smaller consequences fell out. Empty output with a non-zero code used to produce a line starting with a newline; now it produces exactly `Exit code: 7`. And `run_in_dir` shares the same formatter, so it inherits the fix without a second code path.

A truncation message is a promise that everything important fits. Cutting the end of a report is acceptable; cutting the verdict off the end is not.
