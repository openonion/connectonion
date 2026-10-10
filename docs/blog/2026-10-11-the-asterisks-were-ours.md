---
description: Feishu replies went out as text messages, so a model's **bold** arrived with the asterisks on. Feishu renders Markdown itself; we were sending it to the wrong message type.
tags: [Feishu, Inbox]
---

# The asterisks were ours

A hosted agent listening on Feishu was asked, in a group, how many people
had applied for each role. It answered the way models answer: `**237 位**`,
then a little table with pipes. The group saw exactly that. Asterisks around
the number, pipes down the side, a reply that looked broken even though every
word in it was right.

The first fix people reached for was the prompt. One agent's skill now tells
the model to write plain lines with `·` bullets when it talks to Feishu. That
worked for that agent. Every other agent on the channel still wrote Markdown,
because that is what a model writes, and every one of them would have to
learn the same rule from the same complaint.

## Where the mistake actually was

Our docs already had a sentence about this, and it was wrong in an
interesting way. For WhatsApp, `send` and `reply` translate Markdown into
WhatsApp's own marks. For Feishu, the docs said, there was nothing to
translate into: the `text` message has no inline formatting, and rich text is
"a different message type".

All true, and it pointed the wrong way. The question was never how to
translate Markdown for Feishu. Feishu's `post` message has an `md` element,
and Feishu renders Markdown inside it on its own: bold, italics, lists, links,
code blocks. We were choosing the one message type that cannot show
formatting, and then explaining in the docs why formatting could not be shown.

## The change

`send` and `reply` now put the text in a `post` with a single `md` element:

```json
{"zh_cn": {"content": [[{"tag": "md", "text": "**237 位**"}]]}}
```

`--plain` still means "the characters exactly as typed", and now it does
something on Feishu: it sends the old `text` message. Before, it was a flag
that was accepted and ignored.

One thing does not come through. Feishu's `md` element has no tables, so a
pipe table still arrives as its lines. That is written down in
`docs/cli/feishu.md` now rather than left for the next person to find. A card
could render a table, but that would mean a different message type again, and
nobody has asked for that yet.

The regression test sends `**237 位**` as a reply and as a fresh message and
checks both bodies are `post` with that `md` element, and that `--plain`
still sends `text`. On the old code it failed on the first assertion: the
reply went out as `text`, the same way it did in that group.
