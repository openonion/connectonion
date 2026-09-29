# Twenty minutes to learn nothing about Tamara

Tamara's page was already good. It had her role, her phone number and a
source for each. The 1.9.0a1 acceptance run investigated her again anyway,
on a copy of the owner's notebook, to see what the new evidence path would add.

It took 20.6 minutes. It gathered 10.96 million characters, wrote 977 evidence
files and downloaded 250 attachments: event invitations, app store receipts,
a conference newsletter. The page that came back said nothing new. It was
reworded and renumbered, and it cost almost a million input tokens.

Outlook had found the right 50 mails, so Outlook was not the problem. Gmail
had found 677, and the query explained why. The investigation takes its
search terms from the page itself, from the `Handles` and `Also known as`
lines, so that a name learned last time is searched next time. After the
first investigation those lines read like this:

```
- Also known as: Tamara Berryman; tamara.berryman@unsw.edu.au [2]
```

That is written for a reader: a name, an address, and a citation to the mail
that showed them. Split on commas, it is one handle. It contains an `@`, so it
was sent to Gmail as an address, citation and all. Gmail does not refuse a
query like that. Inside the query's braces, which mean OR, the stray words
became search terms of their own, and they matched almost anything.

So the better a page got, the worse its next investigation became. Every
investigated page carries citations on its identity lines, and every one of
them would have searched this way.

The fix has two parts. A handle is read without its citation and split on
semicolons as well as commas. And only a whole, well-formed address goes to a
mail server as an address; a name stays a name. The test is Tamara's line,
exactly as the model wrote it.

The lesson is about where inputs come from. The page is the investigation's
output, and here it had quietly become the next investigation's input too.
Text written for people was being parsed as if it were written for a
machine, and nothing complained until someone read the query.

The same run found five smaller problems, fixed in the same change. The most
concrete was 75 MB of private mail copies left in finished task folders, now
removed when a task ends.
