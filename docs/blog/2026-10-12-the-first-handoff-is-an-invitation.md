---
description: The first handoff email asked a new recipient to understand a package manager, a long prompt and an encoded bundle before they could see the task. We put the task and one action first.
tags: [Handoff, Onboarding]
---

# The first handoff is an invitation

Someone sent me a handoff this morning. I knew there was a useful task inside,
but the email looked like a Markdown file poured into an inbox: a long prompt,
install branches for several Python tools, and a block of encoded data. It did
contain an installation path and a way for my agent to answer the sender. That
did not help me find the first thing to do.

The first mail has to serve two readers. A person needs to know who sent the
work, what it is, where it stands and what to do next. `co handoff open` needs
the intact bundle, including its content hash. Putting both in one visible
column made the machine's needs feel like the product.

We kept one email, but gave its first screen to the person. It now opens with
the sender, task, status and open questions. Below them is one labelled block
to select and paste into Codex or Claude Code. The prompt checks for co,
installs the exact preview in an isolated tool environment when needed, saves
the brief, and accepts the handoff. Acceptance introduces the recipient's agent
to the sender; later messages can use the agent inbox. The encoded bundle stays
in the HTML for the CLI but is hidden from the visual message.

We considered a copy button in the email. Mail clients do not reliably run
JavaScript, so a button that works in one reader and silently fails in another
would be worse than a clearly selectable block. A hosted copy page could offer
a real one-click action, but it would also need a secure way to store and
retrieve a private handoff. That is a separate design, not a shortcut to take
inside this preview.

The same principle reaches the repository README: a new user can choose the
stable installer or a pinned preview, and can paste one setup request into a
coding agent instead of learning `uv` first. Gmail and Outlook connections are
optional for receiving a handoff; `co init` creates the agent identity and
mailbox.

We rendered a long sample email at desktop and phone widths, checked that the
summary and next action appear before the long block, and tested saved HTML
and multipart mail parsing. Focused handoff and version tests passed. We have
not yet checked Gmail, Apple Mail and Outlook rendering with real messages.
If those clients strip or expose the hidden bundle, or if selecting a long
prompt on a phone remains a frequent failure, that is the evidence to revisit
the email format or build the hosted copy page.
