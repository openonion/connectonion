# Changing Directory Must Not Change Your Account

Draft for 1.8.4; publish after release acceptance.

A mailbox command worked in one directory and asked for authorization in
another. Both commands used the same computer and the same intended account.
There was already a global credential file. Why did walking into a project
change what the command could do?

The obvious place to look was the mail command's loader. It could read the
global file first. But tracing the import path showed that this was too late:
package startup had already discovered the project's `.env` and copied its
values into the process. To the mail command, an old project token now looked
like something the operator had deliberately inherited from the shell.

That moved the fix out of the mailbox handler. The source had to be selected
before package startup loaded any file. The owner wanted the global setup by
default, so the project choice became explicit: `co --env-file PATH ...`.
Ordinary `co gmail inbox` no longer lets the working directory choose its
settings. The same rule had to reach the other provider clients, or changing
from mail to calendar could reproduce the surprise.

Following that source through refresh exposed a second problem. A token could
come from the process while the email and scopes came from the file. In an
account-switch regression, those fields could describe two different people.
Loading the right file was insufficient if the resolver then assembled a
credential one field at a time. It now selects the provider record as a whole.

The record also had to survive the trip back to disk. Two commands can begin
with the same refresh token; one refresh can rotate it while the other is
still running. The concurrent-refresh tests exercise that collision. A lock
now covers reading, refreshing and saving, and the waiting writer must prove
it is still updating the same account. It cannot overwrite a newly selected
account merely because it started first.

The installed-wheel check returned to the original symptom: run provider reads
from the checkout, a nested directory and an unrelated directory. Gmail and
Outlook kept the same account fingerprints. No email was sent to establish
that result.

The cost is a visible migration for applications that relied on implicit
project loading. They must name the file or inherit their settings explicitly.
That choice belongs where the command starts, while the operator can still
see it. Once a project value has become an ordinary process variable, the
mailbox client cannot recover the intent that put it there.
