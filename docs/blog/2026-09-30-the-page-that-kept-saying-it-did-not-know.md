# The page that kept saying it did not know

On 30 September the owner ran co rem 1.9.0a2 on his own notebook and read the
pages the way anyone would: open one, look at the first screen, scroll. The
facts were right. Six of them were checked against the mail and all six held.
The pages still read badly, and the reason was in the rules we had written
for the model.

A person's page opened on eight contact fields. Email, phone, company, role,
signing entity, handles, language, aliases. The one thing he opened the page
to find, that this person was waiting on him for a signed document, was on
line 33. There was no date of last contact anywhere. The page was complete and
told him nothing on its first screen.

Every person page also said the same sentence under `Uncertainties`: "web:
not searched; co rem runs are offline". Five pages out of five. It was there
because the Skill told the model to write it, word for word. The same Skill
said, twenty lines earlier, that `Uncertainties` is about the subject only.
The model obeyed both, and the page carried a line about our runner on every
person in the notebook. Other lines leaked the same way: "8 bodies read" in
`History`, a phone number "searched in the supplied mail and the web; not
found". Each one had its own instruction.

The project pages were worse. A project page written from the owner's own
messages to Codex and Claude Code had between 24 and 38 sentences saying "the
material does not say whether this was done". `Where it stands` was eleven
bullets of history. The connectonion page described co rem under `What it is`,
because co rem was what most of that month's messages were about. And the
body was Chinese under English headings.

That last group had one cause, and it was a rule we were proud of. The
messages are the user's own; the assistant's replies are not in the material.
So "a request is a request": "add a --json flag" means he asked, not that it
exists. The rule is right. Applied to every line, it turns a page into a
request log with a disclaimer after each entry. The model was not being
careless. It was being exactly as careful as we asked, once per sentence.

The fixes are small, and most of them move a sentence rather than add one.

A person's page now starts with a lead: two or three cited sentences under the
title, before `Contact`. Who they are to the user, what is open between them
and who owes it, and `Last contact: <date>`. The mapper writes an empty slot
for it, so a new page already has the place. It has no heading, so the
validator and the roster needed nothing new. The roster already took the first
line of prose as a person's summary, so the lead is now what the maintainer
sees when it has to decide whether "Mia" in a session is this Mia. The reader
ranks people by the lead's last-contact date instead of the file's
modification time.

Every rule that sent coverage to `Uncertainties` now sends it to the final
reply. The runner already records what was searched, in the task record and
on the page's `Investigation:` line. The page says nothing about the web.

The project skill says the thing once. One line in `Uncertainties`: the page
is written from the user's own messages, and whether requests were carried
out is not in them. Every other line just says what he asked, reported or
decided, with the date. `Where it stands` is three to five bullets about now.
`What it is` is the repository's product, and the loudest thread in the
messages goes under `Open threads`. The page is written in English, and a
short quote can stay in the language it was typed in.

The new benchmark cases check the parts a count can see without a judge. A
person page with no lead, or with no last-contact date, fails. A page that
mentions the web not being searched fails. A project page with more than five
bullets in `Where it stands`, more than three hedges above `Uncertainties`, or
Chinese text outside quotation marks fails. The same checks, run read-only
over the owner's notebook, flag the coverage line 11 times on his 5
investigated people, the missing lead on all 5, and the language on one of
his two project pages. Run on the new Skill text, the person case and three
new project cases each wrote a page that passed both the judge and those
checks. One run per case shows which way a change goes. It is not a rate.

The lesson is about where a sentence goes. A rule that is true about the
material can still be wrong to write on the page. "Outcomes are not in the
user's messages" is true of every line, which is the reason to say it only
once.
