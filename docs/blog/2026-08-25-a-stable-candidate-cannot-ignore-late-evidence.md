# A Stable Candidate Cannot Ignore Late Evidence

The Stable pull request already had a comforting sentence: promote RC11
unchanged. The long browser and provider journey had passed, the artifact was
public, and the remaining work looked administrative.

Then a scheduled agent stopped before its first browser command.

It was not waiting for a person. There was no person: this run came from cron.
The operator had already granted `co browser status`, but Auto asked for live
approval anyway and then denied the command because stdin was closed. The same
job had worked on 1.6. Calling this a future patch would make the first Stable
1.7 upgrade knowingly break unattended users.

While reproducing that boundary, a second report removed the easier escape.
A browser result contained a shortened `data:image/...;base64,...` excerpt.
The text merely looked like an image, yet the formatter tried to upload it and
ended an otherwise successful run. It was small, local, and tempting to defer.
It was also another way for ordinary tool output to kill automation without a
useful recovery path.

That changed the release decision. We restored configured headless commands,
but did not let the historical broad `Bash(co *)` rule authorize publishing or
deployment. We required image candidates to decode strictly and reach the real
end of a supported file, rather than trusting a familiar prefix. The focused
tests then proved both halves: the intended browser command proceeds, while
stronger effects and truncated images remain safely outside the fast path.

RC11 could no longer be called unchanged, so it could no longer be the Stable
source. RC12 gives those fixes new immutable bytes and a new acceptance run.
That is the useful meaning of a release candidate: not that testing is over,
but that any late evidence is allowed to change the answer.
