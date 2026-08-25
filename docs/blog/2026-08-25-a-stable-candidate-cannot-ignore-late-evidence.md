# A Stable Candidate Cannot Ignore Late Evidence

RC11 had completed the broad 1.7 acceptance journey. Then two narrower reports
arrived while Stable was being prepared.

One report showed that a shortened `data:image/...;base64,...` excerpt could be
mistaken for an uploadable image. The decode failed inside the post-tool
formatter and ended an otherwise successful agent run. The other showed that
an unattended Auto session denied `co browser status` even though the operator
had already granted that command in configuration. A live dialog could recover;
a cron or CI process could not.

Neither finding changes the feature train. Both change whether the candidate is
safe to promote.

RC12 therefore replaces the unchanged-RC11 premise. Image candidates now need
strict base64 decoding and a complete supported file structure. Headless Auto
can honor deliberate ordinary-command grants, while the historical broad
`Bash(co *)` entry restores only `co status` and `co browser ...`; publishing,
deployment, credentials, deletion, and unknown effects keep their stronger
verdicts.

The release rule is simple: late evidence is still evidence. A candidate that
changes after acceptance needs a new name, new immutable artifacts, and focused
acceptance of the changed boundary before Stable can inherit it.
