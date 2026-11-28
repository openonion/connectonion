# The two bytes an edit did not mean to touch

Editing one line of a file should leave the other lines alone. Ours did not. `edit` read the file in text mode, which turns every `\r\n` into `\n`, and wrote it back in text mode, which turns every `\n` into the platform's line separator. On Windows an LF file came back as CRLF. On Linux a CRLF file came back as LF. One changed sentence produced a diff of the whole file.

Nothing in the change was wrong in isolation. Text mode is the right default for reading what a person typed; it is the wrong default for rewriting a file you were only asked to change in one place. Line endings are part of the bytes on disk, and the bytes belong to whoever wrote the file — an editor on Windows, a generator on Linux, a git checkout with `core.autocrlf` set either way.

So the tool now decodes the bytes exactly as they are, does the replacement in the file's own style, and writes the bytes back. `old_string` may still be written with plain `\n`: it is translated to the file's endings before matching, so a caller does not have to know what the file uses. A file that is not UTF-8 is reported as a tool error instead of raising through the agent.

The lesson is not "avoid text mode". It is that a tool asked to change one thing should have a story for the things it was not asked to change. Here the story is now the byte.
