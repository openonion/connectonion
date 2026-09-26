# The offline agent needed files

On Friday, the Wiki's unattended maintenance run asked Luna to organize a
batch it had already collected. Luna answered that it could not do the job:
the material lived in local files, but the prompt said the run had “no shell”
and forbade commands. It wrote no page. The run record nevertheless called the
attempt completed and advanced past the material.

“Offline” had been stretched too far. The model needed no browser, mailbox or
network to maintain the notebook; it did need to read the staged files and
write to a disposable copy. The prompt now permits bounded local file
operations inside that workspace, while continuing to forbid network calls,
source-app commands and instructions hidden in the material. The maintenance
Skill now makes the same distinction. Investigation received the same wording
because it had repeated the contradiction.

A natural-language response is not proof that the batch was assessed. When a
maintenance pass changes nothing, it now has to leave a small receipt naming
the sources it reviewed and why no update was needed. Without that receipt,
the run fails and the source cursor stays put. A six-case runner evaluation
covers refusal, incorrect source attribution, blocked and missing material,
a real no-change decision and a page update.

Luna then completed a synthetic offline smoke run: it read a one-off request,
left the notebook alone for a reason, and wrote the receipt. That success cost
144,414 input tokens, much of it cached. The broken permission instruction is
fixed; the size of the instruction bundle is now the next visible problem.

Another synthetic run exposed a different edge. Luna correctly treated an
October launch date as unapproved and ignored a command quoted in the source,
but wrote its citations as Markdown list numbers. The strict page reviewer
refused the otherwise useful candidate. The runner now converts those list
labels to the canonical citation spelling before validating the unchanged
source IDs and claims. The refused candidate remains on disk for comparison;
its two citation errors drop to zero after that narrow conversion. On a retest
with the same source messages, the page was accepted with both source IDs and
the date still marked unapproved. The quoted command was never run.
