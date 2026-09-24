# Let initialization start

The user ran `co wiki init` and reached two questions before seeing a map: may it read Gmail correspondent metadata, then may it read Outlook? Both accounts were already connected. The feedback was direct: start the work, and put authentication instructions in tips.

Our earlier design used a terminal prompt to choose mail sources. That made the same command behave differently in a terminal and a script. It also put a setup decision ahead of the local project and skill maps, which need neither mailbox.

The revised default discovers connected mailboxes and maps their correspondent metadata. A missing connection produces a tip after the local work: run `co auth google` or `co auth microsoft`, then rerun initialization. Explicit `--mail` arguments restrict the selection. Authentication itself stays a separate user action; initialization does not launch a login or install a background schedule.

We kept a distinction that matters when this runs unattended: disconnected is different from failed. A connected or explicitly selected mailbox that fails still produces a partial-failure result, with completed maps preserved. Otherwise a network failure could look like a successful search that found no people.

While checking the new flow, we found another small trap: a setup tip could send someone back to the default notebook instead of the one they had just initialized. Carrying the selected directory into the suggested command makes the tip a continuation of their work. It should not quietly begin a different task.

The feedback changed where setup belongs. The map can already provide value before every source is available. Showing that partial result first gives the person a reason to connect another source, and the remaining setup becomes a next step rather than an entrance exam. The command still has to tell the truth about what it could not read. Starting promptly and reporting incomplete evidence are compatible choices.
