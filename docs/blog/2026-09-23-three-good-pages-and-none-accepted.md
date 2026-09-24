# Three good pages, none accepted

We ran `co wiki investigate` on three real people from a real mailbox. The
model wrote three person pages worth keeping: a university coordinator's role
and phone number, every booking and access-card exchange from April to
September, a colleague's Chinese name found in a signature. The runner
refused all three.

The model had done the diligent thing. It searched the mailbox itself and cited
what it found as "Outlook message 39" and "listing rows 2, 4, 7". The check
that stands between a candidate and the notebook accepts a citation only when
it names something the run was given: a message id, a URL that was opened, a
file that was read. A row number in a listing that changes every time you list
names nothing a week later. The check was right. The design was asking the
model to do the part a program should do.

So the program does it now. Before the model starts, the collector asks Outlook
and Gmail on the server for every message to, from or copying each address of
the person over the window, and follows every page of results. For one person
that takes about a second. Every message arrives with an id the page can cite.
The instructions tell the model the mail is already there, and list the three
things it may cite.

Retesting on eleven more people found seven more failures of the same kind.
In each one the page was fine and the plumbing was not:

- A digest of a long history kept only the label "gmail +4", so anyone with
  enough mail to need a digest could not cite a single message. One page cited
  44 real ids, every one present in the digests, and was refused.
- A page listed the user's own Outlook address as someone else's email,
  because every message between two people carries both addresses. The
  program already knows which addresses are the user's, so it removes them
  itself.
- A digest chunk was larger than a whole investigation, and timed out.
- A source listed but never cited was treated as an error and threw away a
  fully cited page.

After these fixes every page in the retest passed review. The best of them
lists what is still open between two people: what one owes the other, which
meeting has no recorded outcome, which name might be a nickname or a mistake.

Mechanical things now happen in the program: finding the mail, keeping ids
through a digest, knowing which addresses are yours. Everything that needs
judgment stays in the Skill. When a page is wrong now, the Skill is the place
to fix it.
