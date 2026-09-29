# An investigator with a folder

The notebook's most expensive page was a person. On 2026-09-24 it wrote the
page of the owner's busiest correspondent, a man he had exchanged 157 mails
with in three months. The run gathered 1.78 million characters of mail, cut it
into 30 pieces, had a model summarise every piece, and then had a last turn
read the 30 summaries and write the page. It took 3 hours 24 minutes and 8.2
million input tokens. The daily round, which has a budget of calls rather than
hours, never reached people like him at all: their pages never fit a day
(#1723).

The obvious fix was to make the summaries cheaper, and we did that first
(#1884). Each piece dropped to one or two tool rounds. The total barely moved,
because every mail was still summarised whether or not it mattered to the
page. Nobody investigates a person that way. You open the folder, look at the
list, search for the signature, read the first mail and the last three, and
write down what you found.

The owner's design said exactly that: an agent that knows where the saved
material lives and how to use the command line, `co gmail`, `co outlook`,
`co whatsapp`, and researches the person on its own. Here we hit the first
wall. Every notebook run is sandboxed, with no network, and on purpose. The
material is mail, and anyone can send the owner mail. A model with a shell,
the network and the owner's logged-in mailbox is precisely what a hostile
message would ask for. So the agent could not call `co gmail`.

The turn was to split the job where the sandbox already splits it. A script,
which is our code and may use the network, runs first. It searches each
mailbox for the person's addresses, fetches every body the notebook has not
saved, reads the WhatsApp chats the owner chose and the coding messages that
name the person, and writes one folder: an index with one line per item, and
one file per mail that starts with the id a page must cite. Then the model
runs, offline, with the index in its prompt and `rg` and `sed` in its hands.
The skill tells it to work from questions, to read the first contact and the
newest mails, and to stop after about thirty tool calls.

We ran it on the same man. The script took 92 seconds and saved 265 items.
The model call took five minutes and forty seconds, used 0.67 million input
tokens (0.57 million cached) instead of 8.2 million, and wrote a page that
passed review with 52 citations. His role, which appears in only two of the
265 mails, was found and cited. The phone field stayed `Unknown`. We checked:
nothing he wrote in those five months carries one.

The first attempt failed in under a second, and the reason was ours, not the
product's. The measuring shell set `PYTHONPATH=.`, and the runner starts
`co ai` from the task folder, where `.` is not the checkout. An older `co`
answered and did not know `--harness`. The evidence the script had saved was
reused by the second attempt, which is the incremental design paying for
itself on day one.

With a person costing one call, the daily round can finally be what the owner
asked for. The first run of the day works through unfinished pages, most
recent correspondent first. Every later run lists the mailbox since the run
before, and updates only the people who wrote, from only what they wrote.

The lesson is about where the thinking goes. We spent a week making it
cheaper to read everything. What was needed was to stop reading everything,
and to put the network work where the network is allowed.
