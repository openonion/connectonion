# Let it look it up

The first time we investigated the owner's own page on a real notebook, it
took 40 model calls, 16.2 million input tokens and about 75 minutes. The page
that came out was good. The way it got there was not.

Thirty days of mail and coding sessions came to 2.2 million characters. One
turn holds far less, so the investigation cut the material into chunks and
asked a model to summarise each one, 39 times, before the one call that wrote
the page. Every chunk was paid for whether or not anything in it mattered to
the page, and what the page most needed were single needles: the owner's
legal name for contracts, a phone number, a course's dates.

The turn that writes the page is an agent. It has `rg`, `sed` and `ls`, and it
knows exactly what it is missing: the page in front of it says `Unknown` next
to every gap. Summarising everything first answers a question nobody asked
("what is in all of this?") instead of the one the page asks ("where does it
say her phone number?").

So the material now goes where an agent looks for things. When it does not fit
one turn, the investigation writes it out as files, one per mail and one per
coding session or chat, with an `index.md` that lists them by date, sender and
subject. Every entry starts with its source id, which is what the page cites
and what the validator accepts. The prompt carries the page, the coverage and
the index path, and says: search for what each field needs; read only that.
The files are deleted when the run ends, so copies of private mail do not
collect in the notebook.

Summarising everything is still the right job for maintenance, which must read
every new item. Investigation is different: it goes looking for answers.

The same branch fixed three smaller things found while measuring the
investigation. An organisation's page was being given every page template plus
the CLI reference, 63.7k characters instead of 31k, because the map from folder
to page kind had no entry for `orgs`. The budget that sizes the material was
measured against that same worst case on every page, which took about 33k
characters of room from the material. `co wiki list people` sorted by file
name, so an agent's `0x…` mailbox came before the colleagues the owner mails
most. And a single-page investigation now reads the WhatsApp chats the owner
chose, not only sessions and mail.

What we have not done yet is re-run the four measured subjects on the same
data. That comparison is the acceptance for #1850, and the number to beat is
the one this post started with.
