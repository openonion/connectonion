# Let initialization start

The user ran `co wiki init` and reached two questions before seeing a map: may it read Gmail correspondent metadata, then may it read Outlook? Both accounts were already connected. The feedback was direct: start the work, and put authentication instructions in tips.

Our earlier design used a terminal prompt to choose mail sources. That made the same command behave differently in a terminal and a script. It also put a setup decision ahead of the local project and skill maps, which need neither mailbox.

The revised default discovers connected mailboxes and maps their correspondent metadata. A missing connection produces a tip after the local work: run `co auth google` or `co auth microsoft`, then rerun initialization. Explicit `--mail` arguments restrict the selection. Authentication itself stays a separate user action; initialization does not launch a login or install a background schedule.

We kept a distinction that matters when this runs unattended: disconnected is different from failed. A connected or explicitly selected mailbox that fails still produces a partial-failure result, with completed maps preserved. Otherwise a network failure could look like a successful search that found no people.

The regression suite checks that neither startup path calls the confirmation function, that disconnected mail is not read, and that setup commands preserve notebook paths containing spaces and apostrophes. All 243 Wiki unit tests and 10,794 offline tests passed. Those checks establish the command contract; they do not establish that a user's remote mailbox is reachable.
