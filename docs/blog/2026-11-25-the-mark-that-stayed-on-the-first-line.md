# The mark that stayed on the first line

A byte-order mark is three bytes that say "this file is UTF-8". Readers are supposed to consume it. Ours did not: `read_file` opened every file as plain UTF-8, so the mark survived decoding and arrived on the first line as an invisible U+FEFF. The line looked right in a terminal and matched nothing in an edit.

The same assumption failed louder on UTF-16. A file saved by an older Windows editor was decoded as UTF-8 with replacement characters, and the agent was handed NUL-separated noise instead of the text it asked for. Nothing raised. The tool answered confidently with the wrong content, which is the worst way for a reader to be wrong.

Text files state their own encoding in the first two or four bytes, so there is no reason to guess. We now check for the UTF-32 marks before UTF-16 (the little-endian UTF-32 mark begins with the UTF-16 one), then the UTF-8 mark, then fall back to plain UTF-8 for everything unmarked. Undecodable bytes still become replacement characters: half a line is worth more to an agent than an exception.

The lesson is not about encodings. It is that a tool which reformats what it reads must first understand what it read. A reader that silently substitutes is indistinguishable from one that works, until the agent tries to edit the line it was shown.
