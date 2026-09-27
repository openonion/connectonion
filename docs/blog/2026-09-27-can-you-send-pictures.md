# "Can you send pictures?"

The agent was planning a trip in a WhatsApp group. It had shortlisted
restaurants with their Google Maps ratings and drafted a day-by-day plan.
Then someone in the group asked "你可以发图片吗？", can you send pictures, and
the honest answer was no. `co whatsapp send` took text, and only text. So the
rating card became a wall of numbers, and a wall of numbers in a group chat is
the thing everybody scrolls past.

Our first answer was right but small: add `--image` to `send`. We wrote the
doc first. Writing the doc forced the questions a quick patch would have
skipped. WhatsApp shows a picture inline only as JPEG, PNG or WebP, so a GIF
sent as an "image" arrives as something nobody can see. So the type is checked
from the file's first bytes, not its name, and a GIF is pointed at `--file`.
A caption is optional, but `send` read stdin when the text was missing. A
script that sent only a picture would have hung waiting for a caption that was
never coming. So with an attachment, a missing caption means no caption.

Then the owner asked the better question: from real use, what else is
missing? We read their inbox (334 messages received, 193 sent), counting
rather than reading. The first finding went straight back into this change.
The agent does not answer with `send`; it answers with `reply`, which still
took only text. A picture you can send but not reply with is half a feature.
So `reply --image` is in this PR too.

The inbox had more to say, and each finding got its own issue. Almost half the
group messages carried the wrong kind. The listener had been running six-day-old
code, so none of the images anyone sent it had been downloaded.

The lesson: when someone asks for a feature, look at how they would really use
it before you decide where it ends.
