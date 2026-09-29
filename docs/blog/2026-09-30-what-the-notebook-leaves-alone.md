# What the notebook leaves alone

After the map learned to find names, the owner's notebook still had 43 people
pages titled with a bare email address. The day before, 176 others had been
named from the name they write under, a saved contact or the owner's own
greeting. These 43 were what no evidence could name, most of them automated
or one-way senders: notices, receipts, mailers. They sat at the bottom of the
investigation queue, below about six hundred real pages. A long enough first
pass would still have reached them and paid a model to research a mailing
robot.

The quick fix was to delete them. It was also the wrong one, because among 43
nameless senders there can be a person who has simply not introduced
themselves yet. A deleted page stays deleted. A page that should not be there
only wastes attention.

What separates a mailer from a quiet person is not the address. It is what the
owner has done with it. A correspondent is someone the owner has written to at
least once, and a mailer almost never is. So the rule does not judge the
sender. It looks at the owner's own side of the conversation. A page titled with an address the owner has never
written to is **held for review**:

- it stays on disk and links to it still work;
- it is left out of the investigation queue, `co wiki list` and the reader's
  contents;
- it comes back on its own when a later map finds a name or a reply, or as
  soon as the owner investigates it.

`co wiki list people --review` shows what is held.

Two things this rule never touches. An address the owner has written to,
even without a name, is a correspondent and stays listed. The agent's own
mailbox is one of those. A page that has already been investigated is someone's
work, and it is left exactly as it is.

The lesson is small and easy to forget. When a system cannot tell what
something is, it should not delete it or spend money finding out. It should
set it aside where the owner can see it.
