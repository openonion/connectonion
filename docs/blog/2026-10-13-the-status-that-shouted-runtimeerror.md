# The status that shouted RuntimeError

*2026-10-13*

Someone ran `co rem status` after a first init. They were not starting a model
turn. They wanted a dashboard. What they got was a Codex week line that named
`RuntimeError` in plain sight — the meter had failed, the failure was caught,
and then the exception type was pasted into the sentence a first-time user
reads.

The meter already knew how to fail quietly. `quota.read` never raises; it
returns `{"unknown": …}` with the reason. Status took that reason and printed
it verbatim, so a path problem or a quota refusal looked like a crash that had
somehow half-survived. `--json` still needs the detailed reason. The dashboard
does not.

Status now says the quota is unavailable and that Codex-backed pages will be
skipped, points at `co rem doctor` for the reason, and keeps the raw `unknown`
string on the structured quota field. The exception stays for machines. The
person asking for status gets a line they can act on.
