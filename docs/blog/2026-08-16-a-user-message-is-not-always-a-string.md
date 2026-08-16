# A User Message Is Not Always a String

Text-file attachments worked. Image attachments crashed before the model ran.

The browser rendered an image preview and OIP delivered one image to the Host.
Then the skills plugin called `.startswith('/')` on the newest user message and
raised `AttributeError: 'list' object has no attribute 'startswith'`.

The assumption was easy to miss because ordinary user content is a string. A
multimodal user message is an ordered list of content parts: one text part plus
one or more image parts. The Agent already supported that representation, but an
`after_user_input` plugin at the edge of the execution loop still assumed the old
shape.

Returning early for every list would have stopped the crash. It would also have
made `/skill` commands silently stop working whenever the user attached an image.
Replacing the entire list with skill instructions would be worse: the command
would run, but the attachment it was meant to inspect would disappear.

The skills plugin now locates the text part without flattening the message. A
normal image prompt passes through untouched. A multimodal slash command replaces
only its text part with the loaded instructions and arguments, preserving the
remaining image parts and their order. Plain string behavior is unchanged.

The regression covers both sides of that boundary: a non-command image prompt
must not load a skill or raise, and a slash command with an image must load the
skill while keeping the exact image part. The real browser retest then confirmed
the stronger result: OIP reported one image, the LLM completed, and the chat
remained live.

The lesson applies to every message event handler. Plugins should reason about
message semantics — text, images, files, tool calls — rather than treating the
wire representation as permanently scalar.
