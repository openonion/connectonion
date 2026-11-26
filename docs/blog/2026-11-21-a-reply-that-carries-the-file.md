---
description: co gmail reply could only send a plain body, at once. A threaded answer with a colleague copied and a signed PDF attached had to go out as a new thread. Now reply takes --cc, --bcc, --attach, --all and --draft, and stays in the thread.
tags: [Gmail, CLI]
---

# A reply that carries the file

A university partner (call her Dana) asked, in an existing Gmail thread, for a
corrected signed letter by Monday. The answer needed three things:

- the PDF attached;
- a colleague, Sam, copied;
- to stay in the thread.

`co gmail reply` could do only the third. The workaround was `co gmail draft
create` plus `draft attach`. That starts a new conversation with a copied
`Re:` subject, so Dana received the letter without the thread it answered.

Now it is one command:

```bash
co gmail reply <message-id> "Corrected copy attached." --cc sam@example.com --attach letter-signed.pdf
```

Here is what the reply does:

- `--cc`, `--bcc` and `--attach/-a` take the same path as `co gmail send`:
  - the same project-folder check;
  - the same 25MB limit;
  - the same missing-file exit before anything is sent.
- `--all` keeps everyone who was on the original, minus you.
- `--draft` saves the reply unsent, **in the same thread**. You can still
  `draft attach`, `review` and `send` it.

While building `--draft`, we found that staging a file into a reply draft
updated it without its thread id. Gmail can then drop the draft from its
thread. Every draft update now carries the thread id it already had.

There is still no `--at`. Gmail's API has no scheduled send, so a delayed reply
needs the server-side hold tracked in #934. Until then, `--draft` is the way
to hold a reply, and `--help` says so.
