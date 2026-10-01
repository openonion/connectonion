# The phone number was in the signature

The owner had said it several times: co rem's pages find too few facts and
too little insight. This time he named one. On Ody's page he could not find
Ody's phone number. The Phone field said `Unknown`, and further down, under
Uncertainties, the page said "no phone number appears in the material".

That sentence was false. We gathered the same mail again into a copy of the
notebook and searched it with a regular expression and no model. Ody's number
was in his signature block. The investigation had paid for a long turn over
that mail and still wrote that the number was not there.

## How a model misses a line it was given

Nothing was hidden. Ody's material was too large for one turn: 392 items,
including 101 attachments. So it went into files, and the turn searched them
for each field still marked `Unknown`. A search only finds what you think to
search for. The turn looked for the topics of the relationship and never read
the four lines under "Regards". It then wrote the absence of a result as a
fact about the mail.

The other pages had the same problem with less obvious fields. Tamara's and
Richard's pages had no first or last contact date anywhere, although every
message carries one. When we measured the four pages the owner reads most,
they filled 6 or 7 of the 14 fields a contact card needs.

Tamara's mail added a second problem. Outlook had delivered every message from
her as a single line, with her mobile number in the middle and the next word
attached to its last digit. The extractor's first version looked for a
signature in the last lines of a message, so it found nothing. A model reading
that line might also have missed the number.

## The turn

We had been asking the model to do two jobs at once: copy facts and interpret
them. Copying is what code does well. A From address, a phone number after
"M:", a LinkedIn link and the dates of the first and last message can be read
exactly. Choosing which signature line is a job title, deciding whether a
domain is the employer, and saying what has changed in a relationship need
judgement.

So the work is now split. Before the turn, `fact_extract.py` reads every
gathered mail, including mail the page already cites. It passes the certain
facts to the turn in one item, with the source id each fact came from. Lines
that need judgement, such as signature blocks, invitation lines that name the
person, and the address domain, are passed as text for the model to read.
After the turn, a phone number, address, link or contact date that the
extractor found but the page does not contain is written back into its field,
with a citation. The model may correct a fact when the material contradicts
it. It may not leave one out. When nothing new has arrived for a page, the
missing phone number is still restored, without a model call.

The page now starts with that data: a `## Facts` block with one field per
line, each value cited, and `Unknown` written out when a value is missing. The
reader displays it as a card. Below it is `## Insight`, with two to four lines,
each beginning `Now:`, `Changed:`, `At stake:` or `Pattern:`. The labels force
each line to say something of that kind. Without them, the same slot was
filled with "a key stakeholder who maintains regular communication", which
says nothing the inbox had not already shown.

## What it bought

We re-ran two of the pages on the copy, using the owner's Codex plan. Ody's
page went from 6 of 14 fields filled to 8. It also gained three Insight lines,
each tied to a specific date or commitment. That run used a bounded quick pass,
which reads only the newest dozen mails per mailbox, so the extractor never saw
the signature. The step that restores facts after the turn would have put the
number back from the full window; on its own it raises the page to 9.

Tamara's page cost the most to learn from. The first two candidates were
refused, one for a single line each time. One wrote a company as two values
followed by one citation. The other put a full stop after its citation. The
model was right both times, and our grammar was too strict. We changed two
rules: a citation at the end of a line now covers the values before it, and an
uncited new value is removed from the page instead of causing the whole page to
be refused. With those rules the third candidate passes and moves Tamara from 7
to 11 of 14 fields, including her mobile number. It also has three Insight
lines of 16 to 28 words each. The three runs used 725 thousand input tokens.
Two of them were refusals we should not have issued.

## The lesson

"Not found in the material" is a claim about the search, not about the
material, and a page should not record it as a fact. If a regular expression
can read a fact, read it with code first, give the model the result with its
source, and do not let the model drop it.
